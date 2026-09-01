import os
import ast
from PyQt6.QtCore import QSettings
from playlist.playlist_scanner import PlaylistScanner
from core.utils import get_settings_path

class SessionManager:
    def __init__(self, main_app):
        self.main = main_app
        
        settings_path = get_settings_path()
        self.settings = QSettings(settings_path, QSettings.Format.IniFormat)
        
        # Legăm settings de MainApp pentru ca restul modulelor să o poată citi dacă au nevoie
        self.main.settings = self.settings

    def restore_geometry(self):
        saved_geometry = self.settings.value("geometry")
        if saved_geometry:
            self.main.restoreGeometry(saved_geometry)
        else:
            self.main.resize(1100, 700) # Dimensiunea default

    def restore_early_session(self):
        """ Restaurăm elementele vizibile la startup (Volum, Coadă, etc) """
        saved_vol = self.settings.value("volume", 40, type=int)
        self.main.volume_slider.setValue(saved_vol)
        self.main.audio.set_volume(saved_vol / 100.0)
        
        saved_eq_master = self.settings.value("eq_master", False, type=bool)
        saved_eq_tone = self.settings.value("eq_tone", True, type=bool)
        saved_eq_limit = self.settings.value("eq_limit", False, type=bool)
        saved_eq_bands = self.settings.value("eq_bands", True, type=bool)

        self.main.audio.set_master_dsp(saved_eq_master)
        self.main.knobs_on = saved_eq_tone 
        self.main.audio.set_limiter(saved_eq_limit) 
        self.main.eq_bands_on = saved_eq_bands

        saved_shuffle = self.settings.value("shuffle", 0, type=int)
        saved_repeat = self.settings.value("repeat", 0, type=int)

        self.main.qm.is_shuffle = saved_shuffle
        self.main.qm.repeat_mode = saved_repeat
        self.main.ui_player.btn_shuffle.current_index = saved_shuffle
        self.main.ui_player.btn_shuffle.refresh_look()
        self.main.ui_player.btn_repeat.current_index = saved_repeat
        self.main.ui_player.btn_repeat.refresh_look()

        saved_queue = self.settings.value("queue")
        saved_shuffled_queue = self.settings.value("shuffled_queue")
        last_song = self.settings.value("last_song", "")
        last_pos = self.settings.value("last_position", 0.0, type=float)

        if hasattr(self.main, 'ui_playlist') and hasattr(self.main.ui_playlist, 'logic'):
            self.main.ui_playlist.logic.migrate_cue_virtual_entries()

        parsed_queue = self._parse_list(saved_queue)
        parsed_shuffled = self._parse_list(saved_shuffled_queue)

        if parsed_queue:
            self.main.qm.queue = PlaylistScanner.canonicalize_track_list([str(x) for x in parsed_queue if x])
        if parsed_shuffled:
            self.main.qm.shuffled_queue = PlaylistScanner.canonicalize_track_list([str(x) for x in parsed_shuffled if x])

        saved_wave_mode = self.settings.value("waveform_mode", 0, type=int)
        if hasattr(self.main.ui_player, 'btn_extra_1'):
            self.main.ui_player.btn_extra_1.current_index = saved_wave_mode
            self.main.ui_player.btn_extra_1.refresh_look()
            self.main.ui_player.toggle_waveform_mode(saved_wave_mode)

        last_song = self._normalize_track_path(last_song)
        self.settings.setValue("queue", self.main.qm.queue)
        self.settings.setValue("shuffled_queue", self.main.qm.shuffled_queue)
        self.settings.setValue("last_song", last_song)
        if last_song and self._playback_path_exists(last_song):
            self.main.current_path = last_song
            if self.main.audio.load_and_play(last_song, play_now=False):
                self.main.audio.seek(last_pos) 
                self.main.ui_player.set_playing_state(False) 
                
                if hasattr(self.main.ui_playlist, 'logic') and self.main.ui_playlist.logic.library_root:
                    raw = self.main.ui_playlist.logic.get_metadata_raw(last_song)
                    title, artist, album, duration_sec, ext = raw
                else:
                    title, artist, album, duration_sec, ext = PlaylistScanner.get_track_metadata(last_song)
                art_path = self.main.playback.extract_album_art(last_song)
                
                display_path = os.path.dirname(last_song)
                if self.main.ui_playlist.logic.library_root and last_song.startswith(self.main.ui_playlist.logic.library_root):
                    try:
                        display_path = os.path.relpath(os.path.dirname(last_song), self.main.ui_playlist.logic.library_root)
                        if display_path == ".": display_path = os.path.basename(self.main.ui_playlist.logic.library_root)
                    except: pass
                
                self.main.ui_player.set_track_info(title, artist, display_path)
                self.main.ui_player.update_timers(last_pos, duration_sec)
                
                lyrics_text = self.main.ui_playlist.logic.get_lyrics(last_song)
                if hasattr(self.main.ui_player, 'set_lyrics'):
                    self.main.ui_player.set_lyrics(lyrics_text)
                
                cached_peaks = self.main.ui_playlist.logic.get_waveform_data(last_song)
                if cached_peaks:
                    self.main.ui_player.waveform.load_data(cached_peaks, duration_sec)
                else:
                    if PlaylistScanner.is_cue_virtual_path(last_song):
                        self.main.ui_player.waveform.load_song_async(PlaylistScanner.resolve_audio_path(last_song))
                    else:
                        self.main.ui_player.waveform.load_song_async(last_song)

                self.main.os_integration.update_metadata(
                    title, artist, album, art_path, 
                    duration=duration_sec, 
                    track_path=last_song, 
                    is_playing=False,
                    elapsed=last_pos 
                )
                if hasattr(self.main, 'discord_presence'):
                    self.main.discord_presence.update_metadata(
                        title,
                        artist,
                        album,
                        art_path,
                        duration=duration_sec,
                        track_path=last_song,
                        is_playing=False,
                        elapsed=last_pos,
                    )

    def restore_deferred_ui_state(self):
        """ Restaurează stările butoanelor de EQ (apelată DUPĂ Lazy Loading) """
        saved_eq_master = self.settings.value("eq_master", False, type=bool)
        saved_eq_tone = self.settings.value("eq_tone", True, type=bool)
        saved_eq_limit = self.settings.value("eq_limit", False, type=bool)
        saved_eq_bands = self.settings.value("eq_bands", True, type=bool)
        saved_eq_spatial = self.settings.value("eq_spatial", True, type=bool)
        saved_eq_reverb = self.settings.value("eq_reverb", True, type=bool)

        self.main.ui_eq.btn_master.setChecked(saved_eq_master)
        self.main.ui_eq.btn_tone.setChecked(saved_eq_tone)
        self.main.ui_eq.btn_limit.setChecked(saved_eq_limit)
        self.main.spatial_on = saved_eq_spatial
        self.main.reverb_on = saved_eq_reverb
        
        try:
            if hasattr(self.main.ui_eq, 'btn_bands'): self.main.ui_eq.btn_bands.setChecked(saved_eq_bands)
            elif hasattr(self.main.ui_eq, 'btn_eq'): self.main.ui_eq.btn_eq.setChecked(saved_eq_bands)
            if hasattr(self.main.ui_eq, 'btn_spatial'): self.main.ui_eq.btn_spatial.setChecked(saved_eq_spatial)
            if hasattr(self.main.ui_eq, 'btn_reverb'): self.main.ui_eq.btn_reverb.setChecked(saved_eq_reverb)
        except Exception:
            pass
        if hasattr(self.main.ui_eq, '_apply_master_visual'):
            self.main.ui_eq._apply_master_visual(saved_eq_master)

        # Restaurează tema în Setări
        saved_theme = self.settings.value("theme", "Dark", type=str)
        idx = self.main.ui_settings.combo_theme.findText(saved_theme)
        if idx >= 0:
            self.main.ui_settings.combo_theme.blockSignals(True)
            self.main.ui_settings.combo_theme.setCurrentIndex(idx)
            self.main.ui_settings.combo_theme.blockSignals(False)
            
        # Sincronizăm Canvas-ul de EQ și FFT-ul (Vizualizatorul)
        b_freq = self.settings.value("bass_shelf_freq", 90, type=int)
        t_freq = self.settings.value("treble_shelf_freq", 10000, type=int)
        fft_bars = self.settings.value("fft_bars", 42, type=int)
        
        if getattr(self.main, 'ui_eq', None):
            self.main.ui_eq.visualizer_canvas.set_fft_bars(fft_bars)
            self.main.ui_eq.set_tone_freqs(b_freq, t_freq)
            self.main.ui_eq.update_visualizer_tone()
        if getattr(self.main, 'ui_player', None) and hasattr(self.main.ui_player, 'waveform'):
            self.main.ui_player.waveform.set_fft_bars(fft_bars)

    def save_session(self):
        self.settings.setValue("volume", self.main.volume_slider.value())
        self.settings.setValue("theme", self.main.last_used_theme)
        self.settings.setValue("geometry", self.main.saveGeometry())
        
        if getattr(self.main, 'ui_eq', None):
            self.settings.setValue("eq_master", self.main.ui_eq.btn_master.isChecked())
            self.settings.setValue("eq_tone", self.main.ui_eq.btn_tone.isChecked())
            self.settings.setValue("eq_limit", self.main.ui_eq.btn_limit.isChecked())
            self.settings.setValue("eq_bands", self.main.eq_bands_on)
            self.settings.setValue("eq_spatial", getattr(self.main, 'spatial_on', True))
            self.settings.setValue("eq_reverb", getattr(self.main, 'reverb_on', True))
            
            # Salvăm setările detaliate ale sliderelor/knoburilor din EQ
            try:
                spatial = self.main.ui_eq.page_spatial
                reverb = self.main.ui_eq.page_reverb

                self.settings.setValue("eq_preamp", int(self.main.ui_eq.slider_preamp.value()))
                self.settings.setValue("eq_bass_knob", float(self.main.ui_eq.knob_bass.value()))
                self.settings.setValue("eq_treble_knob", float(self.main.ui_eq.knob_treble.value()))
                
                bands = [int(s.value()) for s in self.main.ui_eq.sliders]
                self.settings.setValue("eq_bands_values", bands)

                self.settings.setValue("fx_tempo", float(spatial.knob_tempo.value()))
                self.settings.setValue("fx_balance", float(spatial.knob_balance.value()))
                self.settings.setValue("fx_stereo_expand", float(spatial.knob_stereo.value()))
                self.settings.setValue("fx_low_bypass", float(spatial.knob_low_bypass.value()))

                self.settings.setValue("fx_reverb_damp", float(reverb.knob_damp.value()))
                self.settings.setValue("fx_reverb_filter", float(reverb.knob_filter.value()))
                self.settings.setValue("fx_reverb_fade", float(reverb.knob_fade.value()))
                self.settings.setValue("fx_reverb_predelay", float(reverb.knob_predelay.value()))
                self.settings.setValue("fx_reverb_predelay_mix", float(reverb.knob_predelay_mix.value()))
                self.settings.setValue("fx_reverb_size", float(reverb.knob_size.value()))
            except Exception:
                pass

        self.settings.setValue("shuffle", self.main.qm.is_shuffle)
        self.settings.setValue("repeat", self.main.qm.repeat_mode)
        if hasattr(self.main.ui_player, 'btn_extra_1'):
            self.settings.setValue("waveform_mode", self.main.ui_player.btn_extra_1.current_index)

        normalized_queue = PlaylistScanner.canonicalize_track_list(self.main.qm.queue)
        normalized_shuffled = PlaylistScanner.canonicalize_track_list(self.main.qm.shuffled_queue)
        normalized_current = self._normalize_track_path(self.main.current_path) if self.main.current_path else ""

        self.main.qm.queue = normalized_queue
        self.main.qm.shuffled_queue = normalized_shuffled
        self.main.current_path = normalized_current

        self.settings.setValue("queue", normalized_queue)
        self.settings.setValue("shuffled_queue", normalized_shuffled)
        self.settings.setValue("last_song", normalized_current)
        pos, _ = self.main.audio.get_position_info()
        self.settings.setValue("last_position", pos)

    def _parse_list(self, val):
        if isinstance(val, list): return val
        if isinstance(val, tuple): return list(val)
        if isinstance(val, str):
            val = val.strip()
            if val.startswith("['") or val.startswith('["'):
                try: return ast.literal_eval(val)
                except: return []
            elif "," in val:
                return [x.strip() for x in val.split(",") if x.strip()]
            elif val: return [val]
        return []

    def _normalize_track_path(self, path):
        if not path:
            return ""
        return PlaylistScanner.canonicalize_track_path(path)

    def _playback_path_exists(self, path):
        if not path:
            return False
        if PlaylistScanner.is_cue_virtual_path(path):
            source_path = PlaylistScanner.resolve_audio_path(path)
            return bool(source_path and os.path.exists(source_path))
        return os.path.exists(path)