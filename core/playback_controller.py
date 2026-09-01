import os
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPixmap
from playlist.playlist_scanner import PlaylistScanner

class PlaybackController:
    def __init__(self, main_app):
        self.main = main_app
        self.is_loading = False
        self.eos_counter = 0
        self._stats_tracked_path = None
        self._stats_last_position = 0.0
        self._stats_pending_seconds = 0.0
        self._stats_flush_threshold = 5.0

    def play_file(self, filepath, switch_to_player=True, is_auto_nav=False, mark_previous_skip=True):
        filepath = PlaylistScanner.canonicalize_track_path(filepath)
        current_path = PlaylistScanner.canonicalize_track_path(self.main.current_path) if self.main.current_path else None
        if current_path and current_path != filepath:
            self._finalize_current_track_stats(mark_skip=bool(mark_previous_skip))

        is_queue_view = (self.main.ui_playlist.view_mode == "queue")
        
        if is_auto_nav or is_queue_view:
            self.main.qm.update_history_for_new_song(filepath)
        else:
            current_visible = self.main.ui_playlist.playlist_files
            if current_visible:
                self.main.qm.set_queue(current_visible, filepath)
            else:
                self.main.qm.update_history_for_new_song(filepath)
        
        self.main.current_path = filepath
        self.is_loading = True 
        self.eos_counter = 0

        # Hide waveform during transition (will fade in after load)
        self.main.ui_player.waveform.opacity_factor = 0.0
        self.main.ui_player.waveform.update()

        if switch_to_player and self.main.navbar.currentIndex() != 0:
            self.main.anim_manager.animate_transition_to_player(filepath)
            anim = getattr(self.main, 'anim_group', None)
            if anim is not None:
                anim.finished.connect(lambda fp=filepath: self._deferred_load(fp))
                return
        self._deferred_load(filepath)

    def _deferred_load(self, filepath):
        try:
            success = self.main.audio.load_and_play(filepath)
            if success:
                self.main._refresh_wider_knob_tooltips()
                if hasattr(self.main.ui_playlist, 'logic'):
                    self.main.ui_playlist.logic.increment_play_count(filepath)
                    self._notify_statistics_changed()

                self._begin_track_statistics(filepath)

                self.main.ui_player.set_playing_state(True)
                art_path = self.extract_album_art(filepath)
                
                if hasattr(self.main.ui_playlist, 'logic'):
                    raw = self.main.ui_playlist.logic.get_metadata_raw(filepath)
                    title, artist, album, _, ext = raw
                else:
                    title, artist, album, duration_sec, ext = PlaylistScanner.get_track_metadata(filepath)
                
                duration_sec = self.main.audio.get_raw_length() 
                
                display_path = os.path.dirname(filepath)
                if hasattr(self.main.ui_playlist, 'logic') and self.main.ui_playlist.logic.library_root:
                    root = self.main.ui_playlist.logic.library_root
                    if filepath.startswith(root):
                        try:
                            folder_only = os.path.dirname(filepath)
                            rel_path = os.path.relpath(folder_only, root)
                            if rel_path == ".":
                                rel_path = os.path.basename(root) 
                            display_path = rel_path
                        except ValueError: pass

                if hasattr(self.main.ui_player, 'set_track_info'):
                    self.main.ui_player.set_track_info(title, artist, display_path)

                lyrics_text = self.main.ui_playlist.logic.get_lyrics(filepath)
                if hasattr(self.main.ui_player, 'set_lyrics'):
                    self.main.ui_player.set_lyrics(lyrics_text)

                self.main.os_integration.update_metadata(
                    title, artist, album, art_path, 
                    duration=duration_sec, 
                    track_path=filepath, 
                    is_playing=True 
                )
                if hasattr(self.main, 'discord_presence'):
                    self.main.discord_presence.update_metadata(
                        title,
                        artist,
                        album,
                        art_path,
                        duration=duration_sec,
                        track_path=filepath,
                        is_playing=True,
                        elapsed=0,
                    )
                cached_peaks = self.main.ui_playlist.logic.get_waveform_data(filepath)
                if cached_peaks:
                    self.main.ui_player.waveform.load_data(cached_peaks, self.main.audio.get_raw_length())
                else:
                    if PlaylistScanner.is_cue_virtual_path(filepath):
                        source_path = PlaylistScanner.resolve_audio_path(filepath)
                        self.main.ui_player.waveform.load_song_async(source_path)
                    else:
                        self.main.ui_player.waveform.load_song_async(filepath)

                total_sec = self.main.audio.get_raw_length()
                self.main.ui_player.update_timers(0, total_sec)
                
                if self.main.audio.master_dsp_enabled:
                    self.main.apply_master_ui_state()
                
                if self.main.ui_playlist.view_mode == "queue" and self.main.ui_playlist.isVisible():
                    self.handle_queue_request()
                    
                def trigger_preload():
                    next_song = self.main.qm.peek_next_song()
                    prev_song = self.main.qm.peek_prev_song()
                    keep_set = {filepath, next_song, prev_song}
                    keep_set.discard(None) 
                    self.main.audio.manage_cache(keep_set)
                
                QTimer.singleShot(100, trigger_preload)
        finally:
            self.is_loading = False 

    def toggle_play_ui(self):
        is_playing = self.main.audio.toggle_play()
        self.main.ui_player.set_playing_state(is_playing)
        
        pos, _ = self.main.audio.get_position_info()
        if is_playing:
            self._stats_last_position = max(0.0, float(pos or 0.0))
        else:
            self._accumulate_listened_progress(pos)
            self._flush_pending_listened_seconds()
        self.main.os_integration.update_state(is_playing, elapsed=pos) 
        if hasattr(self.main, 'discord_presence'):
            self.main.discord_presence.update_state(is_playing, elapsed=pos)

    def update_ui_loop(self):
        if self.is_loading: return 

        curr, total = self.main.audio.get_position_info()
        if total > 0:
            is_playing = self.main.audio.is_playing()

            fft_data = self.main.audio.get_fft() if is_playing else None

            if getattr(self.main, 'ui_eq', None) and self.main.right_stack.currentWidget() == self.main.ui_eq:
                self.main.ui_eq.visualizer_canvas.set_fft_data(fft_data)

            if getattr(self.main, 'ui_player', None) and self.main.ui_player.waveform.mode == "visualizer":
                self.main.ui_player.waveform.set_fft_data(fft_data)

            if not is_playing:
                if abs(curr - total) < 0.5:
                    self.eos_counter += 1
                else:
                    self.eos_counter = 0

                if self.eos_counter >= 3:
                    self.eos_counter = 0
                    if self.main.qm.repeat_mode == 1:
                        self._finalize_current_track_stats(mark_skip=False, current_position=total, total_duration=total)
                        self.main.audio.seek(0)
                        self.main.audio.toggle_play()
                        self.main.ui_player.set_playing_state(True)
                        self._begin_track_statistics(self.main.current_path)
                    else:
                        self.play_next(manual_skip=False)
                return

            self._accumulate_listened_progress(curr)
            self.main.ui_player.waveform.set_position(curr)
            self.main.ui_player.update_timers(curr)
            self.eos_counter = 0

    def seek_music(self, seconds):
        self.main.audio.seek(seconds)
        self._stats_last_position = max(0.0, float(seconds or 0.0))
        self.main.ui_player.update_timers(seconds)
        self.main.os_integration.update_state(self.main.audio.is_playing(), elapsed=seconds) 
        if hasattr(self.main, 'discord_presence'):
            self.main.discord_presence.update_state(self.main.audio.is_playing(), elapsed=seconds)

    def play_next(self, manual_skip=True):
        next_file = self.main.qm.get_next_song()
        if next_file:
            self.play_file(next_file, switch_to_player=False, is_auto_nav=True, mark_previous_skip=manual_skip)
            if self.main.ui_playlist.view_mode == "queue" and self.main.ui_playlist.isVisible():
                self.handle_queue_request()

    def play_prev(self, manual_skip=True):
        prev_file = self.main.qm.get_prev_song()
        if prev_file:
            self.play_file(prev_file, switch_to_player=False, is_auto_nav=True, mark_previous_skip=manual_skip)
            if self.main.ui_playlist.view_mode == "queue" and self.main.ui_playlist.isVisible():
                self.handle_queue_request()
            
    def locate_current_song(self):
        if not self.main.current_path: return
        self.main.navbar.buttons[2].setChecked(True)
        self.main.on_tab_changed(2)
        self.main.ui_playlist.locate_file(self.main.current_path)

    def extract_album_art(self, filepath):
        if hasattr(self.main, 'ui_playlist') and hasattr(self.main.ui_playlist, 'logic'):
            cache_path = self.main.ui_playlist.logic.get_cached_art_path(filepath)
            small_cache_path = self.main.ui_playlist.logic.get_cached_small_art_path(filepath)
            
            if not cache_path or not os.path.exists(cache_path):
                 self.main.ui_playlist.logic.ingest_metadata(filepath)
                 cache_path = self.main.ui_playlist.logic.get_cached_art_path(filepath)
                 small_cache_path = self.main.ui_playlist.logic.get_cached_small_art_path(filepath)

            if cache_path and os.path.exists(cache_path):
                self.main.ui_player.set_album_art(cache_path)
                if small_cache_path:
                     self.main.bg_manager.set_track_pixmap(QPixmap(small_cache_path))
                return cache_path

        self.main.ui_player.set_album_art(None)
        self.main.bg_manager.set_track_pixmap(None)
        return None

    def force_shuffle_state(self, enable):
        new_state = 1 if enable else 0
        self.main.qm.is_shuffle = new_state
        if hasattr(self.main.ui_player, 'btn_shuffle'):
             self.main.ui_player.btn_shuffle.current_index = new_state
             self.main.ui_player.btn_shuffle.refresh_look()
        
        self.main.os_integration.update_player_properties(self.main.qm.repeat_mode, self.main.qm.is_shuffle)
        if enable: self.main.qm._regenerate_shuffle()

    def on_ui_shuffle_changed(self, state_int):
        self.main.qm.is_shuffle = state_int
        if state_int == 1: self.main.qm._regenerate_shuffle()
        self.main.os_integration.update_player_properties(self.main.qm.repeat_mode, self.main.qm.is_shuffle)

    def on_ui_repeat_changed(self, state_int):
        self.main.qm.repeat_mode = state_int
        self.main.os_integration.update_player_properties(self.main.qm.repeat_mode, self.main.qm.is_shuffle)

    def set_shuffle_from_os(self, active):
        state = 1 if active else 0
        self.main.qm.is_shuffle = state
        if state == 1: self.main.qm._regenerate_shuffle()
        if hasattr(self.main.ui_player, 'btn_shuffle'):
            self.main.ui_player.btn_shuffle.current_index = state
            self.main.ui_player.btn_shuffle.refresh_look()
            
    def set_loop_from_os(self, loop_str):
        mode = 0
        if loop_str == "Track": mode = 1
        elif loop_str == "Playlist": mode = 2
        self.main.qm.repeat_mode = mode
        if hasattr(self.main.ui_player, 'btn_repeat'):
            self.main.ui_player.btn_repeat.current_index = mode
            self.main.ui_player.btn_repeat.refresh_look()

    def handle_queue_request(self):
        if self.main.qm.is_shuffle:
            active_queue = []
            if self.main.current_path:
                active_queue.append(self.main.current_path)
            active_queue.extend(self.main.qm.shuffled_queue)
        else:
            active_queue = self.main.qm.queue
        self.main.ui_playlist.load_queue_view(active_queue, self.main.current_path)

    def update_queue_order(self, new_queue):
        if self.main.qm.is_shuffle:
            self.main.qm.shuffled_queue = [x for x in new_queue if x != self.main.current_path]
        else:
            self.main.qm.queue = new_queue

    def add_songs_to_queue_next(self, files):
        if not files: return
        if self.main.qm.is_shuffle:
            self.main.qm.shuffled_queue = list(files) + self.main.qm.shuffled_queue
            q_idx = len(self.main.qm.queue)
            if self.main.current_path in self.main.qm.queue:
                q_idx = self.main.qm.queue.index(self.main.current_path) + 1
            self.main.qm.queue = self.main.qm.queue[:q_idx] + list(files) + self.main.qm.queue[q_idx:]
        else:
            insert_idx = len(self.main.qm.queue)
            if self.main.current_path in self.main.qm.queue:
                insert_idx = self.main.qm.queue.index(self.main.current_path) + 1
            self.main.qm.queue = self.main.qm.queue[:insert_idx] + list(files) + self.main.qm.queue[insert_idx:]
        if self.main.ui_playlist.view_mode == "queue" and self.main.ui_playlist.isVisible():
            self.handle_queue_request()

    def play_files_now(self, files):
        if not files: return
        self.main.qm.set_queue(files, files[0])
        self.play_file(files[0], switch_to_player=True, is_auto_nav=True)

    def _begin_track_statistics(self, filepath):
        self._stats_tracked_path = PlaylistScanner.canonicalize_track_path(filepath) if filepath else None
        self._stats_last_position = 0.0
        self._stats_pending_seconds = 0.0

    def _accumulate_listened_progress(self, current_position):
        if not self._stats_tracked_path:
            return
        try:
            current_position = max(0.0, float(current_position or 0.0))
        except Exception:
            return

        delta = current_position - self._stats_last_position
        if 0.0 < delta <= 5.0:
            self._stats_pending_seconds += delta

        self._stats_last_position = current_position
        if self._stats_pending_seconds >= self._stats_flush_threshold:
            self._flush_pending_listened_seconds()

    def _flush_pending_listened_seconds(self):
        if not self._stats_tracked_path or self._stats_pending_seconds <= 0.0:
            return
        if hasattr(self.main.ui_playlist, 'logic'):
            self.main.ui_playlist.logic.add_listened_seconds(self._stats_tracked_path, self._stats_pending_seconds)
            self._notify_statistics_changed()
        self._stats_pending_seconds = 0.0

    def _finalize_current_track_stats(self, mark_skip=False, current_position=None, total_duration=None):
        if not self._stats_tracked_path:
            return

        if current_position is None or total_duration is None:
            current_position, total_duration = self.main.audio.get_position_info()

        self._accumulate_listened_progress(current_position)
        self._flush_pending_listened_seconds()

        if mark_skip and self._should_count_skip(current_position, total_duration):
            if hasattr(self.main.ui_playlist, 'logic'):
                self.main.ui_playlist.logic.increment_skip_count(self._stats_tracked_path)
                self._notify_statistics_changed()

    def _should_count_skip(self, current_position, total_duration):
        try:
            current_position = float(current_position or 0.0)
            total_duration = float(total_duration or 0.0)
        except Exception:
            return False

        if total_duration <= 0.0:
            return False
        if current_position >= max(total_duration - 3.0, total_duration * 0.85):
            return False
        return True

    def _notify_statistics_changed(self):
        try:
            self.main._refresh_statistics_panel()
        except Exception:
            pass

    def flush_statistics(self):
        self._finalize_current_track_stats(mark_skip=False)