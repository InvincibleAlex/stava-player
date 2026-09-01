import sys
import os
import platform
import hashlib

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty, QUrl, QMetaType
from PyQt6.QtGui import QImage

# ==========================================
# 🐧 LINUX DEPENDENCIES (DBus)
# ==========================================
HAS_DBUS = False
try:
    if platform.system() == "Linux":
        from PyQt6.QtDBus import (
            QDBusConnection, QDBusAbstractAdaptor, QDBusVariant, 
            QDBusMessage, QDBusObjectPath, QDBusArgument
        )
        HAS_DBUS = True
except ImportError:
    pass

# ==========================================
# 🍎 MACOS DEPENDENCIES (PyObjC)
# ==========================================
HAS_OBJC = False
try:
    if platform.system() == "Darwin":
        from Foundation import NSDictionary, NSNumber, NSString
        from MediaPlayer import (
            MPNowPlayingInfoCenter, MPMediaItemPropertyTitle, 
            MPMediaItemPropertyArtist, MPMediaItemPropertyAlbumTitle, 
            MPMediaItemPropertyArtwork, MPMediaItemArtwork, 
            MPNowPlayingInfoPropertyPlaybackRate, MPNowPlayingInfoPropertyElapsedPlaybackTime,
            MPMediaItemPropertyPlaybackDuration, MPRemoteCommandCenter, MPRemoteCommandHandlerStatusSuccess
        )
        from AppKit import NSImage
        HAS_OBJC = True
except ImportError:
    if platform.system() == "Darwin":
        print("⚠️ macOS Integration disabled. Missing 'pyobjc'. Install with: pip install pyobjc")

# ==========================================
# 🪟 WINDOWS DEPENDENCIES (Native Media Keys)
# ==========================================
HAS_WINDOWS_API = False
try:
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes
        from PyQt6.QtCore import QCoreApplication, QAbstractNativeEventFilter
        HAS_WINDOWS_API = True
except ImportError:
    pass

if HAS_WINDOWS_API:
    WM_APPCOMMAND = 0x0319
    WM_HOTKEY = 0x0312

    APPCOMMAND_MEDIA_NEXTTRACK = 11
    APPCOMMAND_MEDIA_PREVIOUSTRACK = 12
    APPCOMMAND_MEDIA_STOP = 13
    APPCOMMAND_MEDIA_PLAY_PAUSE = 14
    APPCOMMAND_MEDIA_PLAY = 46
    APPCOMMAND_MEDIA_PAUSE = 47

    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_MEDIA_STOP = 0xB2
    VK_MEDIA_PLAY_PAUSE = 0xB3

    HOTKEY_MEDIA_PLAY_PAUSE = 0x2001
    HOTKEY_MEDIA_STOP = 0x2002
    HOTKEY_MEDIA_NEXT = 0x2003
    HOTKEY_MEDIA_PREV = 0x2004

    class POINT(ctypes.Structure):
        _fields_ = [
            ("x", wintypes.LONG),
            ("y", wintypes.LONG),
        ]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", POINT),
        ]

    class WindowsMediaEventFilter(QAbstractNativeEventFilter):
        def __init__(self, integration):
            super().__init__()
            self.integration = integration

        def nativeEventFilter(self, event_type, message):
            if event_type not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                return False, 0

            try:
                msg = MSG.from_address(int(message))
            except Exception:
                return False, 0

            if msg.message == WM_APPCOMMAND:
                command = (int(msg.lParam) >> 16) & 0x0FFF
                handled = self.integration._handle_windows_media_command(command)
                return handled, 0

            if msg.message == WM_HOTKEY:
                handled = self.integration._handle_windows_hotkey(int(msg.wParam))
                return handled, 0

            return False, 0

# ==========================================
# 🐧 LINUX ADAPTOR CLASS
# ==========================================
if HAS_DBUS:
    class Mpris2Adaptor(QDBusAbstractAdaptor):
        def __init__(self, parent):
            super().__init__(parent)
            self.setAutoRelaySignals(True)

        @pyqtProperty(str)
        def Identity(self): return "STAVA Player"
        @pyqtProperty(str)
        def DesktopEntry(self): return "stava-player"
        @pyqtProperty(bool)
        def CanQuit(self): return True
        @pyqtProperty(bool)
        def CanRaise(self): return False
        @pyqtProperty(bool)
        def HasTrackList(self): return False
        @pyqtProperty("QStringList")
        def SupportedUriSchemes(self): return ["file"]
        @pyqtProperty("QStringList")
        def SupportedMimeTypes(self): return ["audio/mpeg", "audio/x-wav", "audio/flac"]

        @pyqtProperty(str)
        def PlaybackStatus(self):
            return "Playing" if self.parent()._is_playing else "Paused"

        @pyqtProperty(str)
        def LoopStatus(self):
            return self.parent()._loop_status
        @LoopStatus.setter
        def LoopStatus(self, value):
            self.parent()._loop_status = value
            self.parent().loop_triggered.emit(value)

        @pyqtProperty(bool)
        def Shuffle(self):
            return self.parent()._shuffle_status
        @Shuffle.setter
        def Shuffle(self, value):
            self.parent()._shuffle_status = value
            self.parent().shuffle_triggered.emit(value)

        @pyqtProperty("QVariantMap")
        def Metadata(self):
            title = str(self.parent()._title)
            artist = str(self.parent()._artist)
            album = str(self.parent()._album)
            duration_us = int(self.parent()._duration * 1_000_000)
            art_path_raw = self.parent()._art_path
            art_path = os.path.abspath(art_path_raw) if art_path_raw else ""

            meta = {}
            unique_source = self.parent()._track_path or f"{title}-{artist}-{album}"
            track_hash = hashlib.md5(unique_source.encode('utf-8')).hexdigest()
            
            meta["mpris:trackid"] = QDBusObjectPath(f"/org/mpris/MediaPlayer2/Track/track_{track_hash}")
            meta["xesam:title"] = title
            meta["xesam:album"] = album

            if HAS_DBUS:
                artist_arg = QDBusArgument()
                artist_arg.beginArray(QMetaType.Type.QString.value) 
                artist_arg.add(artist)
                artist_arg.endArray()
                meta["xesam:artist"] = artist_arg

                length_arg = QDBusArgument()
                length_arg.add(duration_us, QMetaType.Type.LongLong.value) 
                meta["mpris:length"] = length_arg

            if art_path and os.path.exists(art_path):
                try:
                    url_bytes = QUrl.fromLocalFile(art_path).toEncoded()
                    meta["mpris:artUrl"] = str(url_bytes, 'utf-8')
                except: pass
            
            return meta

        @pyqtProperty("qlonglong") 
        def Position(self): 
            return 0 

        @pyqtProperty(float)
        def Volume(self): return 1.0
        @Volume.setter
        def Volume(self, val): pass
        @pyqtProperty(float)
        def Rate(self): return 1.0
        @Rate.setter
        def Rate(self, val): pass
        @pyqtProperty(float)
        def MinimumRate(self): return 1.0
        @pyqtProperty(float)
        def MaximumRate(self): return 1.0
        @pyqtProperty(float)
        def Position(self): return 0.0 
        @pyqtProperty(bool)
        def CanGoNext(self): return True
        @pyqtProperty(bool)
        def CanGoPrevious(self): return True
        @pyqtProperty(bool)
        def CanPlay(self): return True
        @pyqtProperty(bool)
        def CanPause(self): return True
        @pyqtProperty(bool)
        def CanControl(self): return True
        @pyqtProperty(bool)
        def CanSeek(self): return False

        @pyqtSlot()
        def Play(self): self.parent().play_triggered.emit()
        @pyqtSlot()
        def Pause(self): self.parent().pause_triggered.emit()
        @pyqtSlot()
        def PlayPause(self): self.parent().toggle_triggered.emit()
        @pyqtSlot()
        def Next(self): self.parent().next_triggered.emit()
        @pyqtSlot()
        def Previous(self): self.parent().prev_triggered.emit()
        @pyqtSlot()
        def Stop(self): self.parent().pause_triggered.emit()
        @pyqtSlot()
        def Quit(self): sys.exit(0)
        @pyqtSlot()
        def Raise(self): pass 
        @pyqtSlot(str, str, result='QDBusVariant')
        def Get(self, interface_name, property_name): return QDBusVariant("") 


# ==========================================
# 🎛️ MAIN CONTROLLER CLASS
# ==========================================
class OSIntegration(QObject):
    play_triggered = pyqtSignal()
    pause_triggered = pyqtSignal()
    toggle_triggered = pyqtSignal()
    next_triggered = pyqtSignal()
    prev_triggered = pyqtSignal()
    shuffle_triggered = pyqtSignal(bool)
    loop_triggered = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.system = platform.system()
        self.enabled = False
        
        self._title = "No Media"
        self._artist = "Unknown"
        self._album = ""
        self._art_path = ""
        self._duration = 0 
        self._track_path = ""
        self._is_playing = False
        self._loop_status = "None"
        self._shuffle_status = False
        
        self.linux_adaptor = None
        self.mac_info_center = None
        self.windows_event_filter = None
        self._registered_hotkeys = []
        
        self._init_platform_specific()

    def _init_platform_specific(self):
        if self.system == "Linux" and HAS_DBUS:
            self._init_linux()
        elif self.system == "Darwin" and HAS_OBJC:
            self._init_mac()
        elif self.system == "Windows" and HAS_WINDOWS_API:
            self._init_windows()

    def _init_linux(self):
        try:
            bus = QDBusConnection.sessionBus()
            self.linux_adaptor = Mpris2Adaptor(self)
            path = "/org/mpris/MediaPlayer2"
            bus.registerObject(path, "org.mpris.MediaPlayer2.Player", self.linux_adaptor, QDBusConnection.RegisterOption.ExportAllContents)
            bus.registerObject(path, "org.mpris.MediaPlayer2", self.linux_adaptor, QDBusConnection.RegisterOption.ExportAllContents)
            if bus.registerService("org.mpris.MediaPlayer2.stava"):
                self.enabled = True
        except Exception as e:
            print(f"OS Integration Linux Error: {e}")

    def _init_mac(self):
        try:
            self.mac_info_center = MPNowPlayingInfoCenter.defaultCenter()
            cmd = MPRemoteCommandCenter.sharedCommandCenter()
            def add_cmd(command_obj, signal):
                def callback(event):
                    signal.emit()
                    return MPRemoteCommandHandlerStatusSuccess
                command_obj.addTargetWithHandler_(callback)

            add_cmd(cmd.playCommand(), self.play_triggered)
            add_cmd(cmd.pauseCommand(), self.pause_triggered)
            add_cmd(cmd.togglePlayPauseCommand(), self.toggle_triggered)
            add_cmd(cmd.nextTrackCommand(), self.next_triggered)
            add_cmd(cmd.previousTrackCommand(), self.prev_triggered)
            cmd.changePlaybackPositionCommand().setEnabled_(False) 
            self.enabled = True
        except: pass

    def _init_windows(self):
        try:
            app = QCoreApplication.instance()
            if not app:
                return

            self.windows_event_filter = WindowsMediaEventFilter(self)
            app.installNativeEventFilter(self.windows_event_filter)
            self._register_windows_hotkeys()
            self.enabled = True
        except Exception as e:
            print(f"OS Integration Windows Error: {e}")

    def _register_windows_hotkeys(self):
        if not HAS_WINDOWS_API:
            return

        user32 = ctypes.windll.user32
        hotkeys = [
            (HOTKEY_MEDIA_PLAY_PAUSE, VK_MEDIA_PLAY_PAUSE),
            (HOTKEY_MEDIA_STOP, VK_MEDIA_STOP),
            (HOTKEY_MEDIA_NEXT, VK_MEDIA_NEXT_TRACK),
            (HOTKEY_MEDIA_PREV, VK_MEDIA_PREV_TRACK),
        ]

        for hotkey_id, vk in hotkeys:
            if user32.RegisterHotKey(None, hotkey_id, 0, vk):
                self._registered_hotkeys.append(hotkey_id)

    def _unregister_windows_hotkeys(self):
        if not HAS_WINDOWS_API:
            return

        user32 = ctypes.windll.user32
        for hotkey_id in self._registered_hotkeys:
            try:
                user32.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass
        self._registered_hotkeys.clear()

    def _handle_windows_hotkey(self, hotkey_id):
        if hotkey_id == HOTKEY_MEDIA_PLAY_PAUSE:
            self.toggle_triggered.emit()
            return True
        if hotkey_id == HOTKEY_MEDIA_NEXT:
            self.next_triggered.emit()
            return True
        if hotkey_id == HOTKEY_MEDIA_PREV:
            self.prev_triggered.emit()
            return True
        if hotkey_id == HOTKEY_MEDIA_STOP:
            self.pause_triggered.emit()
            return True
        return False

    def _handle_windows_media_command(self, command):
        if command == APPCOMMAND_MEDIA_PLAY_PAUSE:
            self.toggle_triggered.emit()
            return True
        if command == APPCOMMAND_MEDIA_PLAY:
            self.play_triggered.emit()
            return True
        if command in (APPCOMMAND_MEDIA_PAUSE, APPCOMMAND_MEDIA_STOP):
            self.pause_triggered.emit()
            return True
        if command == APPCOMMAND_MEDIA_NEXTTRACK:
            self.next_triggered.emit()
            return True
        if command == APPCOMMAND_MEDIA_PREVIOUSTRACK:
            self.prev_triggered.emit()
            return True
        return False

    def shutdown(self):
        if self.system == "Windows" and HAS_WINDOWS_API:
            app = QCoreApplication.instance()
            if app and self.windows_event_filter is not None:
                app.removeNativeEventFilter(self.windows_event_filter)
            self.windows_event_filter = None
            self._unregister_windows_hotkeys()

    # --- HELPER: Empty String List (as) ---
    def _get_empty_string_list(self):
        empty_list = QDBusArgument()
        empty_list.beginArray(QMetaType.Type.QString.value)
        empty_list.endArray()
        return empty_list

    # --- ATOMIC UPDATE (Totul într-un singur semnal) ---
    def update_metadata(self, title, artist, album, art_path, duration=0, track_path="", is_playing=None, elapsed=0):
        self._title = title or "Unknown Title"
        self._artist = artist or "Unknown Artist"
        self._album = album or ""
        self._art_path = art_path
        self._duration = duration 
        self._track_path = track_path
        self._elapsed = elapsed # 🔥 Stocăm poziția curentă
        
        if is_playing is not None:
            self._is_playing = is_playing

        if self.system == "Linux" and self.enabled:
            try:
                changed_props = {}
                
                # 🔥 FIX 1: FĂRĂ QDBusVariant - PyQt face conversia automat
                changed_props["Metadata"] = self.linux_adaptor.Metadata
                
                if is_playing is not None:
                    status_str = "Playing" if self._is_playing else "Paused"
                    # 🔥 FIX 2: FĂRĂ QDBusVariant
                    changed_props["PlaybackStatus"] = status_str

                msg = QDBusMessage.createSignal(
                    "/org/mpris/MediaPlayer2", 
                    "org.freedesktop.DBus.Properties", 
                    "PropertiesChanged"
                )
                msg.setArguments([
                    "org.mpris.MediaPlayer2.Player", 
                    changed_props, 
                    self._get_empty_string_list()
                ])
                QDBusConnection.sessionBus().send(msg)
            except Exception as e:
                print(f"DBUS Bundle Error: {e}")

        elif self.system == "Darwin" and self.enabled:
             self._update_mac_metadata(art_path)

    def _update_mac_metadata(self, art_path):
        try:
            info = {
                MPMediaItemPropertyTitle: self._title,
                MPMediaItemPropertyArtist: self._artist,
                MPMediaItemPropertyAlbumTitle: self._album,
                MPMediaItemPropertyPlaybackDuration: float(self._duration),
                MPNowPlayingInfoPropertyElapsedPlaybackTime: float(self._elapsed), # 🔥 Folosim valoarea corectă
                MPNowPlayingInfoPropertyPlaybackRate: 1.0 if self._is_playing else 0.0
            }
            if art_path and os.path.exists(art_path):
                img = NSImage.alloc().initWithContentsOfFile_(art_path)
                if img:
                    art_obj = MPMediaItemArtwork.alloc().initWithBoundsSize_requestHandler_(
                        (img.size().width, img.size().height), 
                        lambda size: img
                    )
                    info[MPMediaItemPropertyArtwork] = art_obj
            self.mac_info_center.setNowPlayingInfo_(info)
        except: pass

    def update_state(self, is_playing, elapsed=None):
        self._is_playing = is_playing
        if elapsed is not None: self._elapsed = elapsed

        if self.system == "Linux" and self.enabled:
            try:
                status = "Playing" if is_playing else "Paused"
                # 🔥 FIX 3: FĂRĂ QDBusVariant
                changed_props = {"PlaybackStatus": status}
                
                msg = QDBusMessage.createSignal("/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "PropertiesChanged")
                msg.setArguments([
                    "org.mpris.MediaPlayer2.Player", 
                    changed_props, 
                    self._get_empty_string_list()
                ])
                QDBusConnection.sessionBus().send(msg)
            except: pass
        elif self.system == "Darwin" and self.enabled:
            try:
                center = self.mac_info_center
                info = center.nowPlayingInfo()
                
                # 🔥 FIX: Dacă info e None (la startup), îl reconstruim
                if not info:
                    self._update_mac_metadata(self._art_path)
                    info = center.nowPlayingInfo()
                
                if info:
                    info = dict(info) # Facem o copie mutabilă
                    info[MPNowPlayingInfoPropertyPlaybackRate] = 1.0 if is_playing else 0.0
                    
                    # Actualizăm și timpul scurs dacă e furnizat (pentru precizie la Pauză/Seek)
                    if elapsed is not None:
                        info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = float(elapsed)
                    
                    center.setNowPlayingInfo_(info)
            except: pass

    def update_player_properties(self, repeat_mode, is_shuffle):
        loop_str = "None"
        if repeat_mode == 1: loop_str = "Track"
        elif repeat_mode == 2: loop_str = "Playlist"
        self._loop_status = loop_str
        self._shuffle_status = bool(is_shuffle)
        
        if self.system == "Linux" and self.enabled:
            # 🔥 FIX 4: FĂRĂ QDBusVariant
            changed = {
                "LoopStatus": loop_str,
                "Shuffle": bool(is_shuffle)
            }
            msg = QDBusMessage.createSignal("/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "PropertiesChanged")
            msg.setArguments([
                "org.mpris.MediaPlayer2.Player", 
                changed, 
                self._get_empty_string_list()
            ])
            QDBusConnection.sessionBus().send(msg)