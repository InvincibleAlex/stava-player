import queue
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

from core.discord_artwork_lookup import DiscordArtworkLookup

try:
    from pypresence import Presence
    HAS_DISCORD_RPC = True
except ImportError:
    Presence = None
    HAS_DISCORD_RPC = False

try:
    from pypresence.types import ActivityType
except ImportError:
    ActivityType = None


class DiscordPresenceManager(QObject):
    artwork_resolved = pyqtSignal(int, str)
    DEFAULT_PLAY_ICON_URL = "play"
    DEFAULT_PAUSE_ICON_URL = "pause"
    DEFAULT_ACTIVITY_TYPE = "listening"
    DEFAULT_PAUSE_BEHAVIOR = "show_paused_position"

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.rpc = None
        self.connected = False

        self.enabled = False
        self.client_id = ""
        self.large_image_key = ""
        self.online_artwork_enabled = False
        self.small_status_icons_enabled = True
        self.play_small_image_key = self.DEFAULT_PLAY_ICON_URL
        self.pause_small_image_key = self.DEFAULT_PAUSE_ICON_URL
        self.activity_type = self.DEFAULT_ACTIVITY_TYPE
        self.pause_behavior = self.DEFAULT_PAUSE_BEHAVIOR

        self.title = ""
        self.artist = ""
        self.album = ""
        self.art_path = ""
        self.duration = 0.0
        self.track_path = ""
        self.is_playing = False
        self.elapsed = 0.0

        self._last_payload = None
        self._last_error_log = ""
        self._artwork_lookup_generation = 0
        self._resolved_large_image = ""
        self._artwork_lookup = DiscordArtworkLookup()
        self.artwork_resolved.connect(self._on_artwork_resolved)

        # The actual Discord connect/update/clear calls are blocking IPC and
        # used to run directly on the Qt main thread (called from Play/Pause,
        # Seek, track-change handlers), so a slow or unresponsive Discord
        # client could freeze the UI. They now run on this single background
        # thread instead; the main thread only ever enqueues commands.
        self._command_queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker_loop, name="DiscordPresenceWorker", daemon=True)
        self._worker_thread.start()

        self.refresh_from_settings()

    def refresh_from_settings(self):
        new_enabled = self.settings.value("discord_presence_enabled", False, type=bool)
        new_client_id = str(self.settings.value("discord_client_id", "", type=str) or "").strip()
        new_large_image_key = str(self.settings.value("discord_large_image_key", "", type=str) or "").strip()
        new_online_artwork_enabled = self.settings.value("discord_online_artwork_enabled", True, type=bool)
        new_small_status_icons_enabled = self.settings.value("discord_small_status_icons_enabled", True, type=bool)
        new_play_small_image_key = str(self.settings.value("discord_play_small_image_key", self.DEFAULT_PLAY_ICON_URL, type=str) or "").strip()
        new_pause_small_image_key = str(self.settings.value("discord_pause_small_image_key", self.DEFAULT_PAUSE_ICON_URL, type=str) or "").strip()
        new_activity_type = str(self.settings.value("discord_activity_type", self.DEFAULT_ACTIVITY_TYPE, type=str) or "").strip().lower()
        new_pause_behavior = str(self.settings.value("discord_pause_behavior", self.DEFAULT_PAUSE_BEHAVIOR, type=str) or "").strip().lower()

        reconnect_needed = new_client_id != self.client_id

        self.client_id = new_client_id
        self.large_image_key = new_large_image_key
        self.online_artwork_enabled = bool(new_online_artwork_enabled)
        self.small_status_icons_enabled = bool(new_small_status_icons_enabled)
        self.play_small_image_key = new_play_small_image_key or self.DEFAULT_PLAY_ICON_URL
        self.pause_small_image_key = new_pause_small_image_key or self.DEFAULT_PAUSE_ICON_URL
        self.activity_type = new_activity_type if new_activity_type in {"playing", "listening"} else self.DEFAULT_ACTIVITY_TYPE
        self.pause_behavior = new_pause_behavior if new_pause_behavior in {"show_paused_position", "keep_running_timer", "hide_presence"} else self.DEFAULT_PAUSE_BEHAVIOR
        self.enabled = bool(new_enabled) and HAS_DISCORD_RPC and bool(self.client_id)

        if reconnect_needed:
            self._enqueue_command("disconnect")

        if not self.enabled:
            if new_enabled and not HAS_DISCORD_RPC:
                self._log_debug("pypresence is not installed; Discord Rich Presence is disabled.")
            elif new_enabled and not self.client_id:
                self._log_debug("Discord Rich Presence is enabled, but no client ID is configured.")
            self.clear()
            return

        self._request_publish()

    def update_metadata(self, title, artist, album, art_path, duration=0, track_path="", is_playing=None, elapsed=0):
        self.title = title or "Unknown Title"
        self.artist = artist or "Unknown Artist"
        self.album = album or ""
        self.art_path = art_path or ""
        self.duration = float(duration or 0.0)
        self.track_path = track_path or ""
        self.elapsed = max(0.0, float(elapsed or 0.0))
        self._artwork_lookup_generation += 1
        self._resolved_large_image = ""

        if is_playing is not None:
            self.is_playing = bool(is_playing)

        self._start_artwork_lookup_if_needed(self._artwork_lookup_generation)
        self._request_publish()

    def update_state(self, is_playing, elapsed=None):
        self.is_playing = bool(is_playing)
        if elapsed is not None:
            self.elapsed = max(0.0, float(elapsed or 0.0))
        self._request_publish()

    def clear(self):
        self._last_payload = None
        self._enqueue_command("clear")

    def shutdown(self):
        self._enqueue_command("shutdown")
        # Give the worker a short window to actually clear/close the Discord
        # connection before the app exits, but never block shutdown forever.
        self._worker_thread.join(timeout=1.5)

    def _build_payload(self):
        if not self.title and not self.artist:
            return None
        if not self.is_playing and self.pause_behavior == "hide_presence":
            return None

        details = (self.title or "Unknown Title")[:128]
        state_parts = [part for part in (self.artist, self.album) if part]
        state = " - ".join(state_parts)[:128] if state_parts else "Listening"

        payload = {
            "activity_type": self._get_activity_type_value(),
            "details": details,
            "state": state,
            "large_text": (self.album or self.artist or self.title or "STAVA Player")[:128],
        }

        large_image = self._select_large_image()
        if large_image:
            payload["large_image"] = large_image

        small_image = self._select_small_image()
        if small_image:
            payload["small_image"] = small_image
            payload["small_text"] = self._build_small_text()

        if self.duration > 0 and (self.is_playing or self.pause_behavior == "keep_running_timer"):
            start_ts = int(time.time() - self.elapsed)
            payload["start"] = start_ts
            payload["end"] = start_ts + int(self.duration)

        return payload

    def _select_large_image(self):
        manual_value = str(self.large_image_key or "").strip()
        if self._is_remote_url(manual_value):
            return manual_value
        if self._resolved_large_image:
            return self._resolved_large_image
        if manual_value:
            return manual_value
        return None

    def _select_small_image(self):
        if not self.small_status_icons_enabled:
            return None
        candidate = self.play_small_image_key if self.is_playing else self.pause_small_image_key
        candidate = str(candidate or "").strip()
        return candidate or None

    def _build_small_text(self):
        if self.is_playing:
            return "Playing"
        if self.pause_behavior == "show_paused_position" and self.duration > 0:
            return f"Paused at {self._format_time(self.elapsed)} / {self._format_time(self.duration)}"
        return "Paused"

    def _get_activity_type_value(self):
        if ActivityType is None:
            return 0 if self.activity_type == "playing" else 2
        try:
            value = ActivityType.PLAYING if self.activity_type == "playing" else ActivityType.LISTENING
            return int(value.value if hasattr(value, "value") else value)
        except Exception:
            return 0 if self.activity_type == "playing" else 2

    def _format_time(self, seconds):
        total_seconds = max(0, int(seconds or 0))
        minutes, secs = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _start_artwork_lookup_if_needed(self, generation):
        if not self.online_artwork_enabled:
            return
        if self._is_remote_url(self.large_image_key):
            return
        if not self.artist or (not self.album and not self.title):
            return

        title = self.title
        artist = self.artist
        album = self.album

        def worker():
            resolved = self._artwork_lookup.resolve(title=title, artist=artist, album=album) or ""
            self.artwork_resolved.emit(generation, resolved)

        thread = threading.Thread(target=worker, name="DiscordArtworkLookup", daemon=True)
        thread.start()

    def _on_artwork_resolved(self, generation, artwork_url):
        if generation != self._artwork_lookup_generation:
            return
        self._resolved_large_image = str(artwork_url or "").strip()
        self._request_publish()

    def _is_remote_url(self, value):
        text = str(value or "").strip()
        return text.startswith("https://") or text.startswith("http://")

    def _build_payload_override(self, payload):
        activity_type = payload.get("activity_type", self._get_activity_type_value())
        activity = {
            "type": int(activity_type),
            "details": payload.get("details"),
            "state": payload.get("state"),
            "timestamps": {
                "start": payload.get("start"),
                "end": payload.get("end"),
            },
            "assets": {
                "large_image": payload.get("large_image"),
                "large_text": payload.get("large_text"),
                "small_image": payload.get("small_image"),
                "small_text": payload.get("small_text"),
            },
            "instance": True,
        }
        return {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": None,
                "activity": self._strip_empty(activity),
            },
            "nonce": f"{time.time():.20f}",
        }

    def _strip_empty(self, value):
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                item = self._strip_empty(item)
                if item is None or item == {} or item == []:
                    continue
                cleaned[key] = item
            return cleaned
        return value

    def _publish_payload(self, payload):
        if self._supports_payload_override():
            override = self._build_payload_override(payload)
            override["args"]["pid"] = self._get_process_id()
            self.rpc.update(payload_override=override)
            return

        update_payload = dict(payload)
        update_payload.pop("activity_type", None)
        self.rpc.update(**update_payload)

    def _supports_payload_override(self):
        try:
            return "payload_override" in self.rpc.update.__code__.co_varnames
        except Exception:
            return False

    def _get_process_id(self):
        try:
            import os
            return os.getpid()
        except Exception:
            return 0

    def _log_debug(self, message):
        if message == self._last_error_log:
            return
        self._last_error_log = message
        print(f"Discord Presence: {message}")

    def _request_publish(self):
        """ Builds the payload here (cheap, no I/O) and hands it to the
        background worker thread, which owns the actual Discord connection
        and does the blocking connect/update calls. """
        if not self.enabled:
            return

        payload = self._build_payload()
        if not payload:
            self.clear()
            return

        self._enqueue_command("publish", payload)

    def _enqueue_command(self, kind, payload=None):
        self._command_queue.put((kind, payload))

    def _worker_loop(self):
        """ Runs on the background thread for the app's lifetime, processing
        connect/publish/clear/disconnect commands in the order they were
        requested, so it never blocks the UI. """
        while True:
            kind, payload = self._command_queue.get()
            if kind == "shutdown":
                self._worker_clear()
                self._worker_disconnect()
                return
            elif kind == "clear":
                self._worker_clear()
            elif kind == "disconnect":
                self._worker_disconnect()
            elif kind == "publish":
                self._worker_publish(payload)

    def _worker_ensure_connection(self):
        if not self.enabled or not HAS_DISCORD_RPC:
            return False
        if self.connected and self.rpc is not None:
            return True

        try:
            self.rpc = Presence(self.client_id)
            self.rpc.connect()
            self.connected = True
            return True
        except Exception as e:
            self.rpc = None
            self.connected = False
            self._log_debug(f"Discord RPC connection failed: {e}")
            return False

    def _worker_disconnect(self):
        if self.rpc is not None:
            try:
                self.rpc.close()
            except Exception:
                pass
        self.rpc = None
        self.connected = False

    def _worker_clear(self):
        self._last_payload = None
        if self.connected and self.rpc is not None:
            try:
                self.rpc.clear()
            except Exception:
                pass

    def _worker_publish(self, payload):
        if not self.enabled:
            return
        if not self._worker_ensure_connection():
            return

        try:
            self._publish_payload(payload)
            self._last_payload = dict(payload)
        except Exception as e:
            self.connected = False
            self._log_debug(f"Discord RPC update failed: {e}")
