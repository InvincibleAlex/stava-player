import sys
import os
import shutil
from PyQt6.QtCore import QTimer, QProcess
from PyQt6.QtWidgets import QApplication

class EventsCoordinator:
    def __init__(self, main_app):
        self.main = main_app

    def setup_all_connections(self):
        """ Conectează semnalele pentru UI-ul principal (apelate la pornire) """
        self._connect_player()
        self._connect_playlist()
        self._connect_volume()

    def setup_deferred_connections(self):
        """ Conectează semnalele pentru UI-ul ascuns (EQ & Settings) """
        if getattr(self.main, 'ui_eq', None): self._connect_eq()
        if getattr(self.main, 'ui_settings', None): self._connect_settings()

    def _connect_player(self):
        # Connect player UI signals to the PlaybackController
        self.main.ui_player.play_clicked.connect(self.main.playback.toggle_play_ui)
        self.main.ui_player.next_clicked.connect(self.main.playback.play_next)
        self.main.ui_player.prev_clicked.connect(self.main.playback.play_prev)
        self.main.ui_player.shuffle_state_changed.connect(self.main.playback.on_ui_shuffle_changed)
        self.main.ui_player.repeat_state_changed.connect(self.main.playback.on_ui_repeat_changed)
        self.main.ui_player.seek_requested.connect(self.main.playback.seek_music)
        self.main.ui_player.switch_to_player_requested.connect(lambda: self.main.navbar.buttons[0].click())

        if hasattr(self.main.ui_player, 'path_clicked'):
            self.main.ui_player.path_clicked.connect(self.main.playback.locate_current_song)

    def _connect_eq(self):
        # Knob-urile pentru Bass/Treble: boost-only pe intervalele configurate în Settings
        self.main.ui_eq.bass_changed.connect(lambda v: self.main.audio.set_bass_knob(v if self.main.knobs_on else 0.0))
        self.main.ui_eq.treble_changed.connect(lambda v: self.main.audio.set_treble_knob(v if self.main.knobs_on else 0.0))
        self.main.ui_eq.band_changed.connect(self.main.update_graphic_eq)
        
        self.main.ui_eq.toggle_eq_bands.connect(lambda v: setattr(self.main, 'eq_bands_on', v) or self.main.force_refresh_eq())
        def _on_toggle_knobs(v):
            setattr(self.main, 'knobs_on', v)
            # If enabling Tone, apply saved thresholds then refresh knob gains
            if v:
                try:
                    bass_thresh = int(self.main.settings.value("bass_shelf_freq", 90, type=int))
                    treble_thresh = int(self.main.settings.value("treble_shelf_freq", 17000, type=int))
                    self.main.audio.set_bass_threshold(bass_thresh)
                    self.main.audio.set_treble_threshold(treble_thresh)
                except:
                    pass
            self.main.force_refresh_knobs()

        self.main.ui_eq.toggle_knobs.connect(_on_toggle_knobs)
        self.main.ui_eq.toggle_limiter.connect(self.main.audio.set_limiter)

        def _on_toggle_master_dsp(v):
            self.main.audio.set_master_dsp(v)
            if not v:
                return
            try:
                self.apply_master_ui_state()
            except Exception as e:
                print(f"DEBUG: Master DSP reapply failed: {e}")

        self.main.ui_eq.toggle_master_dsp.connect(_on_toggle_master_dsp)
        self.main.ui_eq.btn_master.toggled.connect(lambda _: QTimer.singleShot(0, self.main._refresh_wider_knob_tooltips))
        self.main.ui_eq.preamp_changed.connect(self.main.audio.set_preamp) 
        
        self.main.ui_eq.toggle_spatial.connect(self.on_spatial_toggled)
        self.main.ui_eq.toggle_reverb.connect(self.on_reverb_toggled)

        # Spatial & Reverb
        self._connect_eq_knobs()
        
    def apply_master_ui_state(self):
        self.main.force_refresh_knobs()
        self.main.force_refresh_eq()

        spatial = self.main.ui_eq.page_spatial
        self.main.audio.set_tempo(spatial.knob_tempo.value() if getattr(self.main, 'spatial_on', True) else 1.0)
        self.main.audio.set_balance(spatial.knob_balance.value() if getattr(self.main, 'spatial_on', True) else 50.0)
        self.main.audio.set_stereo_expand(spatial.knob_stereo.value() if getattr(self.main, 'spatial_on', True) else 0.0)
        self.main.audio.set_stereo_low_bypass(spatial.knob_low_bypass.value() if getattr(self.main, 'spatial_on', True) else 0.0)

        reverb = self.main.ui_eq.page_reverb
        if getattr(self.main, 'reverb_on', True):
            self.main.audio.set_reverb(
                reverb.knob_damp.value(),
                reverb.knob_filter.value(),
                reverb.knob_fade.value(),
                reverb.knob_size.value(),
                reverb.knob_predelay.value(),
                reverb.knob_predelay_mix.value(),
            )
        else:
            self.main.audio.set_reverb(0, 0, 0, 0, 0, 0)

    def on_spatial_toggled(self, checked):
        self.main.spatial_on = checked
        if not checked:
            self.main.audio.set_tempo(1.0)
            self.main.audio.set_balance(50.0)
            self.main.audio.set_stereo_expand(0.0)
            self.main.audio.set_stereo_low_bypass(0.0)
        else:
            spatial = self.main.ui_eq.page_spatial
            self.main.audio.set_tempo(spatial.knob_tempo.value())
            self.main.audio.set_balance(spatial.knob_balance.value())
            self.main.audio.set_stereo_expand(spatial.knob_stereo.value())
            self.main.audio.set_stereo_low_bypass(spatial.knob_low_bypass.value())

    def on_reverb_toggled(self, checked):
        self.main.reverb_on = checked
        if not checked:
            self.main.audio.set_reverb(0, 0, 0, 0, 0, 0)
        else:
            reverb = self.main.ui_eq.page_reverb
            self.main.audio.set_reverb(
                reverb.knob_damp.value(),
                reverb.knob_filter.value(),
                reverb.knob_fade.value(),
                reverb.knob_size.value(),
                reverb.knob_predelay.value(),
                reverb.knob_predelay_mix.value(),
            )

    def _connect_eq_knobs(self):
        # 1. Spatial Page (Tempo & Balance)
        self.main.ui_eq.page_spatial.knob_tempo.value_changed.connect(lambda v: self.main.audio.set_tempo(v if self.main.spatial_on else 1.0))
        self.main.ui_eq.page_spatial.knob_balance.value_changed.connect(lambda v: self.main.audio.set_balance(v if self.main.spatial_on else 50.0))
        self.main.ui_eq.page_spatial.knob_stereo.value_changed.connect(lambda v: self.main.audio.set_stereo_expand(v if self.main.spatial_on else 0.0))
        self.main.ui_eq.page_spatial.knob_low_bypass.value_changed.connect(lambda v: self.main.audio.set_stereo_low_bypass(v if self.main.spatial_on else 0.0))

        # 2. Reverb Page
        def update_reverb_params(_):
            if not self.main.reverb_on:
                self.main.audio.set_reverb(0, 0, 0, 0, 0, 0)
                return
            damp = self.main.ui_eq.page_reverb.knob_damp.value()
            filt = self.main.ui_eq.page_reverb.knob_filter.value()
            fade = self.main.ui_eq.page_reverb.knob_fade.value()
            size = self.main.ui_eq.page_reverb.knob_size.value()
            predelay = self.main.ui_eq.page_reverb.knob_predelay.value()
            predelay_mix = self.main.ui_eq.page_reverb.knob_predelay_mix.value()

            self.main.audio.set_reverb(damp, filt, fade, size, predelay, predelay_mix)

        self.main.ui_eq.page_reverb.knob_damp.value_changed.connect(update_reverb_params)
        self.main.ui_eq.page_reverb.knob_filter.value_changed.connect(update_reverb_params)
        self.main.ui_eq.page_reverb.knob_fade.value_changed.connect(update_reverb_params)
        self.main.ui_eq.page_reverb.knob_size.value_changed.connect(update_reverb_params)
        self.main.ui_eq.page_reverb.knob_predelay.value_changed.connect(update_reverb_params)
        self.main.ui_eq.page_reverb.knob_predelay_mix.value_changed.connect(update_reverb_params)

    def _connect_playlist(self):
        self.main.ui_playlist.file_selected.connect(self.main.playback.play_file)
        self.main.ui_playlist.shuffle_requested.connect(self.main.playback.force_shuffle_state)
        self.main.ui_playlist.request_queue_data.connect(self.main.playback.handle_queue_request) 
        self.main.ui_playlist.add_to_queue_requested.connect(self.main.playback.add_songs_to_queue_next) 
        self.main.ui_playlist.play_files_requested.connect(self.main.playback.play_files_now) 
        self.main.ui_playlist.background_update_requested.connect(self.main.bg_manager.set_playlist_pixmap) 
        self.main.ui_playlist.queue_reordered.connect(self.main.playback.update_queue_order)

    def _connect_settings(self):
        self.main.ui_settings.theme_changed.connect(self.main.change_theme_user)
        self.main.ui_settings.debug_toggled.connect(self.main.toggle_debug_mode)
        self.main.ui_settings.eq_bands_changed.connect(self.main.ui_eq.regenerate_bands)
        self.main.ui_settings.zoom_changed.connect(self.main.set_app_zoom)
        self.main.ui_settings.statistics_refresh_requested.connect(self.main._refresh_statistics_panel)
        self.main.ui_settings.setting_changed.connect(self.on_setting_changed)
        self.main.ui_settings.open_wider_ui_requested.connect(self.main.open_wider_editor_window)
        self.main.ui_settings.reset_limiter_debug_requested.connect(self.reset_limiter_debug)
        self.main.ui_settings.reset_effects_debug_requested.connect(self.reset_effects_debug)
        self.main.ui_settings.reset_all_settings_debug_requested.connect(self.reset_all_settings_debug)

    def _connect_volume(self):
        self.main.volume_slider.valueChanged.connect(lambda v: self.main.audio.set_volume(v / 100.0))

    # --- HANDLERE PENTRU SETĂRI ȘI DEBUG ---
    def on_setting_changed(self, key, value):
        if key == "ui_refresh_ms":
            try: refresh_ms = int(value)
            except: refresh_ms = 0
            if refresh_ms <= 0: refresh_ms = self.main._detect_ui_refresh_interval_ms()
            refresh_ms = max(6, min(50, refresh_ms))
            self.main.timer.setInterval(refresh_ms)
        elif key == "fft_bars":
            try:
                bars = int(value)
                if getattr(self.main, 'ui_eq', None): self.main.ui_eq.visualizer_canvas.set_fft_bars(bars)
                if getattr(self.main, 'ui_player', None): self.main.ui_player.waveform.set_fft_bars(bars)
            except: pass
        elif key == "animation_speed_ms":
            try:
                self.main._apply_animation_speed_settings(value)
            except:
                pass
        elif key == "fade_speed_ms":
            try:
                self.main._apply_fade_speed_settings(value)
            except:
                pass
        elif key in {
            "playlist_overscroll_enabled",
            "playlist_overscroll_max_px",
            "playlist_overscroll_return_ms",
            "playlist_overscroll_global_strength",
            "playlist_overscroll_spread_strength",
            "playlist_overscroll_falloff_ratio",
        }:
            try:
                if getattr(self.main, 'ui_playlist', None):
                    self.main.ui_playlist.apply_playlist_overscroll_settings()
            except:
                pass
        elif key in {"discord_presence_enabled", "discord_client_id", "discord_online_artwork_enabled", "discord_large_image_key", "discord_small_status_icons_enabled", "discord_play_small_image_key", "discord_pause_small_image_key", "discord_activity_type", "discord_pause_behavior"}:
            try:
                self.main._refresh_discord_presence_settings()
            except:
                pass
        elif key == "theme":
            pass # Tratat separat de theme_changed
        elif key == "volume":
            try:
                vol = max(0, min(100, int(value)))
                self.main.volume_slider.setValue(vol)
            except: pass
        elif key == "bass_shelf_freq":
            try:
                if hasattr(self.main.ui_eq, 'btn_tone') and not self.main.ui_eq.btn_tone.isChecked(): return
                self.main.audio.set_bass_threshold(int(value))
                if getattr(self.main, 'ui_eq', None):
                    self.main.ui_eq.set_tone_freqs(int(value), self.main.ui_eq.visualizer_canvas.treble_freq)
            except: pass
        elif key == "treble_shelf_freq":
            try:
                if hasattr(self.main.ui_eq, 'btn_tone') and not self.main.ui_eq.btn_tone.isChecked(): return
                self.main.audio.set_treble_threshold(int(value))
                if getattr(self.main, 'ui_eq', None):
                    self.main.ui_eq.set_tone_freqs(self.main.ui_eq.visualizer_canvas.bass_freq, int(value))
            except: pass
        elif key == "eq_master":
            if getattr(self.main, 'ui_eq', None): self.main.ui_eq.btn_master.setChecked(bool(value))
        elif key == "eq_tone":
            if getattr(self.main, 'ui_eq', None): self.main.ui_eq.btn_tone.setChecked(bool(value))
        elif key == "eq_limit":
            if getattr(self.main, 'ui_eq', None): self.main.ui_eq.btn_limit.setChecked(bool(value))
        elif key == "debug_vst_ui_on_start":
            self.main._apply_vst_debug_settings()
        elif key == "shuffle":
            try:
                state = max(0, min(1, int(value)))
                self.main.playback.on_ui_shuffle_changed(state)
                if hasattr(self.main.ui_player, 'btn_shuffle'):
                    self.main.ui_player.btn_shuffle.current_index = state
                    self.main.ui_player.btn_shuffle.refresh_look()
            except: pass
        elif key == "repeat":
            try:
                state = max(0, min(2, int(value)))
                self.main.playback.on_ui_repeat_changed(state)
                if hasattr(self.main.ui_player, 'btn_repeat'):
                    self.main.ui_player.btn_repeat.current_index = state
                    self.main.ui_player.btn_repeat.refresh_look()
            except: pass

    def reset_limiter_debug(self):
        if not getattr(self.main, 'ui_eq', None): return
        try:
            if hasattr(self.main.ui_eq, 'btn_limit') and self.main.ui_eq.btn_limit.isChecked(): return
            self.main.audio.debug_reset_limiter_if_off()
        except: pass

    def reset_effects_debug(self):
        if not getattr(self.main, 'ui_eq', None): return
        try:
            self.main.audio.debug_reset_all_effects_to_neutral()
            controls = [
                self.main.ui_eq.btn_master, self.main.ui_eq.btn_limit, self.main.ui_eq.btn_tone,
                self.main.ui_eq.slider_preamp, self.main.ui_eq.knob_bass, self.main.ui_eq.knob_treble,
                self.main.ui_eq.page_spatial.knob_tempo, self.main.ui_eq.page_spatial.knob_balance,
                self.main.ui_eq.page_spatial.knob_stereo, self.main.ui_eq.page_spatial.knob_low_bypass,
                self.main.ui_eq.page_reverb.knob_damp, self.main.ui_eq.page_reverb.knob_filter,
                self.main.ui_eq.page_reverb.knob_fade, self.main.ui_eq.page_reverb.knob_predelay,
                self.main.ui_eq.page_reverb.knob_predelay_mix, self.main.ui_eq.page_reverb.knob_size,
            ] + self.main.ui_eq.sliders
            
            for c in controls:
                try: c.blockSignals(True)
                except: pass
            
            self.main.ui_eq.btn_master.setChecked(False)
            self.main.ui_eq.btn_limit.setChecked(False)
            self.main.ui_eq.btn_tone.setChecked(True)
            self.main.eq_bands_on = True
            self.main.spatial_on = True
            self.main.reverb_on = True
            
            if hasattr(self.main.ui_eq, 'btn_bands'): self.main.ui_eq.btn_bands.setChecked(True)
            if hasattr(self.main.ui_eq, 'btn_spatial'): self.main.ui_eq.btn_spatial.setChecked(True)
            if hasattr(self.main.ui_eq, 'btn_reverb'): self.main.ui_eq.btn_reverb.setChecked(True)
            
            self.main.ui_eq.slider_preamp.setValue(0)
            self.main.ui_eq.knob_bass.setValue(0)
            self.main.ui_eq.knob_treble.setValue(0)
            for s in self.main.ui_eq.sliders: s.setValue(0)
            self.main.ui_eq.page_spatial.knob_tempo.setValue(1.0)
            self.main.ui_eq.page_spatial.knob_balance.setValue(50)
            self.main.ui_eq.page_spatial.knob_stereo.setValue(0)
            self.main.ui_eq.page_spatial.knob_low_bypass.setValue(0)
            self.main.ui_eq.page_reverb.knob_damp.setValue(0)
            self.main.ui_eq.page_reverb.knob_filter.setValue(0)
            self.main.ui_eq.page_reverb.knob_fade.setValue(0)
            self.main.ui_eq.page_reverb.knob_predelay.setValue(0)
            self.main.ui_eq.page_reverb.knob_predelay_mix.setValue(0)
            self.main.ui_eq.page_reverb.knob_size.setValue(0)
            
            for c in controls:
                try: c.blockSignals(False)
                except: pass
            
            self.main.audio.set_master_dsp(False)
            self.main.audio.set_preamp(0.0)
            self.main.audio.set_limiter(False)
            self.main._refresh_wider_knob_tooltips()
        except Exception as e:
            print(f"DEBUG: Failed reset effects debug: {e}")

    def reset_all_settings_debug(self):
        try:
            self.main.settings.clear()
            self.main.settings.sync()
            if getattr(self.main, 'ui_settings', None) and hasattr(self.main.ui_settings, 'settings'):
                self.main.ui_settings.settings.clear()
                self.main.ui_settings.settings.sync()
            
            # Curățare cache app
            try:
                if hasattr(self.main, 'ui_playlist') and hasattr(self.main.ui_playlist, 'logic'):
                    self.main.ui_playlist.logic.db.close()
            except: pass
            
            app_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(self.main.__class__.__module__))
            cache_root = os.path.join(app_dir, "cache")
            if os.path.isdir(cache_root):
                shutil.rmtree(cache_root, ignore_errors=True)
            
            # Restart app
            program = sys.executable
            args = [] if getattr(sys, 'frozen', False) else [os.path.abspath(sys.modules['__main__'].__file__)]
            self.main._skip_settings_save_once = True
            QProcess.startDetached(program, args)
            QTimer.singleShot(100, QApplication.instance().quit)
        except Exception as e:
            print(f"DEBUG: Failed reset all settings: {e}")
