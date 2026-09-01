import os
import sys
import ctypes
import math
import struct

# --- PERMITE RULAREA DIRECTĂ A SCRIPTULUI PENTRU DEBUG ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from playlist.playlist_scanner import PlaylistScanner
from audio.bass_wrapper import (BassLoader, BASS_CHANNELINFO, BASS_BFX_PEAKEQ, 
                          BASS_BFX_COMPRESSOR2, 
                          BASS_BFX_REVERB, BASS_BFX_FREEVERB,
                          BASS_BFX_BQF, BASS_BFX_BQF_LOWSHELF, BASS_BFX_BQF_HIGHSHELF,
                          BASS_ATTRIB_TEMPO, BASS_ATTRIB_PAN, BASS_ATTRIB_VOL,
                          BASS_FX_BFX_PEAKEQ, BASS_FX_BFX_BQF, BASS_FX_BFX_COMPRESSOR2,
                          BASS_FX_BFX_REVERB, BASS_FX_BFX_FREEVERB, BASS_FX_FREESOURCE,
                          BASS_STREAM_DECODE, BASS_SAMPLE_FLOAT, BASS_DATA_FLOAT, BASS_DATA_FFT256,
                          BASS_UNICODE)

class AudioEngine:
    def __init__(self):
        self.stream = 0
        self.stream_cache = {} # {filepath: stream_handle} - Cache pentru Next/Prev
        self._cached_length = 0.0 # 🔥 OPTIMIZARE: Cache durata curentă (nu se schimbă în timpul redării)
        self.play_window_start = 0.0
        self.play_window_end = None
        self.fx_eq_handle = 0
        self.fx_limit_handle = 0
        self.fx_reverb_handle = 0
        self.fx_vst_handle = 0
        self.fx_stereo_handle = 0 # Fallback handle

        self.wider_vst_path = ""
        self.vst_plugin_path = None # Cache pentru calea plugin-ului
        self.stereo_expand_value = 0.0
        self.stereo_low_bypass_hz = 0.0
        self.reverb_damp = 0.0
        self.reverb_filter = 0.0
        self.reverb_fade = 0.0
        self.reverb_size = 0.0
        self.reverb_predelay = 0.0
        self.reverb_predelay_mix = 0.0
        
        # Setări interne
        self.master_dsp_enabled = False
        self.preamp_db = 0.0
        self.limiter_on = False
        self.master_volume = 1.0 # 0.0 la 1.0
        self.format_gain_db = 0.0 # Gain automat bazat pe format
        self.balance_pan = 0.0
        self.debug_vst_ui_on_start = False
        self.debug_vst_open_wider = True
        self.vst_editor_parent_hwnd = 0
        self._debug_vst_ui_opened_once = False
        # Tempo factor: 1.0 means no tempo processing (default)
        self.tempo_factor = 1.0
        # Bass/Treble knob state and shelf frequencies
        self._last_bass_knob = 0.0
        self._last_treble_knob = 0.0
        self.bass_shelf_freq = 90.0
        self.treble_shelf_freq = 10000.0
        self._last_bass_shelf_log = None
        self._last_treble_shelf_log = None
        self._wider_inactive_logged = False
        self._eq_unavailable_logged = False
        self._fx_type_ids = {}
        self._eq_bands_gains = {i: 0.0 for i in range(20)}
        self._limiter_handles = set()
        self._last_reverb_debug_state = None

        self.bass, self.bass_fx, self.bass_vst = BassLoader.load_libraries()
        try:
            version = int(self.bass.BASS_GetVersion())
            print(f"BASS version loaded: 0x{version:08X}")
        except:
            pass
        self._find_vst_plugin()

    def _find_vst_plugin(self):
        """Caută plugin-uri VST disponibile (Wider și dearVR) o singură dată la inițializare."""
        this_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(this_dir)

        if os.name == 'nt':
            wider_candidates = [
                os.path.join(project_root, 'libs', 'VST', 'Windows', 'Wider', 'Wider.dll'),
                os.path.join(project_root, 'libs', 'VST', 'Windows', 'Wider.dll'),
                os.path.join(project_root, 'libs', 'plugins', 'Wider.dll'),
            ]
            for candidate in wider_candidates:
                if os.path.exists(candidate):
                    self.wider_vst_path = candidate
                    self.vst_plugin_path = candidate
                    break

        else:
            wider_candidates = [
                os.path.join(project_root, 'libs', 'VST', 'Mac', 'Wider.vst'),
                os.path.join(project_root, 'libs', 'VST', 'Mac', 'Wider.vst3'),
                os.path.join(project_root, 'libs', 'plugins', 'Wider.vst'),
                os.path.join(project_root, 'libs', 'plugins', 'Wider.vst3'),
                os.path.join(project_root, 'libs', 'plugins', 'Wider.dylib'),
            ]
            for candidate in wider_candidates:
                if os.path.exists(candidate):
                    self.wider_vst_path = candidate
                    self.vst_plugin_path = candidate
                    break

    def _canonical_path(self, path):
        """Normalizează path-ul pentru chei stabile în cache (important pe Windows)."""
        if not path:
            return ""
        try:
            resolved = PlaylistScanner.resolve_audio_path(path)
        except:
            resolved = path
        return os.path.normcase(os.path.normpath(resolved))

    def _to_bass_unicode_filename(self, path):
        """Convertește calea într-un șir UTF-16LE nul-terminat pentru BASS_UNICODE."""
        return (str(path) + "\0").encode('utf-16le')

    # --- WAVEFORM DATA GENERATOR (NOU) ---
    def get_waveform_data(self, filepath):
        """
        Creează un stream de decodare și extrage punctele de amplitudine.
        Returnează: (lista_peaks, durata_secunde)
        """
        filepath = self._canonical_path(filepath)
        if not os.path.exists(filepath):
            print(f"Waveform: Fișier inexistent: {filepath}")
            return [], 0

        # BASS_UNICODE funcționează cu UTF-16LE pentru căile trimise către BASS.
        file_bytes = self._to_bass_unicode_filename(filepath)
        
        # Flag-urile de bază pentru decodare
        flags = BASS_STREAM_DECODE | BASS_SAMPLE_FLOAT | BASS_UNICODE
        if not filepath.lower().endswith('.wav'):
            flags |= 131072 # Adaugă BASS_STREAM_PRESCAN doar dacă NU e WAV
        
        decode_stream = self.bass.BASS_StreamCreateFile(False, file_bytes, 0, 0, flags)
        
        if not decode_stream:
            try:
                err = self.bass.BASS_ErrorGetCode()
                print(f"Waveform: Nu s-a putut deschide stream-ul de decodare: {filepath} (BASS err={err})")
            except:
                print(f"Waveform: Nu s-a putut deschide stream-ul de decodare: {filepath}")
            return [], 0
        
        # Obținem lungimea și informațiile canalului
        len_bytes = self.bass.BASS_ChannelGetLength(decode_stream, 0)
        duration = self.bass.BASS_ChannelBytes2Seconds(decode_stream, len_bytes)
        chan_info = BASS_CHANNELINFO()
        self.bass.BASS_ChannelGetInfo(decode_stream, ctypes.byref(chan_info))
        
        # 🔥 FIX: Sanity check pentru a preveni OverflowError la fișiere corupte/ciudate
        # Frecvențele audio rezonabile sunt între 8kHz și 192kHz. Canalele între 1 și 8.
        if not (8000 <= chan_info.freq <= 192000 and 1 <= chan_info.chans <= 8):
            print(f"Waveform: Invalid channel info for {filepath} (freq: {chan_info.freq}, chans: {chan_info.chans}). Skipping.")
            self.bass.BASS_StreamFree(decode_stream)
            return [], 0

        if duration <= 0 or chan_info.freq == 0:
            self.bass.BASS_StreamFree(decode_stream)
            return [], 0

        # --- ALGORITM NOU: Citire pe bucăți (Robust la durate eronate) ---
        # Citim bucăți de date corespunzătoare a 1/30 secunde
        samples_per_second = 30
        bytes_per_second = chan_info.freq * chan_info.chans * 4 # 4 bytes per float
        
        # Calculăm dimensiunea unei bucăți (chunk) de citit
        chunk_size_bytes = bytes_per_second // samples_per_second
        
        # Asigurăm că e multiplu de "sample frame" (un sample pe toate canalele)
        sample_frame_size = chan_info.chans * 4
        if sample_frame_size > 0:
            chunk_size_bytes = (chunk_size_bytes // sample_frame_size) * sample_frame_size
        
        # Fallback pentru fișiere foarte scurte sau cu rate ciudate
        if chunk_size_bytes == 0:
            chunk_size_bytes = sample_frame_size * 256 if sample_frame_size > 0 else 1024
        
        peaks = []
        
        # Buffer pentru citire
        num_floats_in_chunk = chunk_size_bytes // 4
        data_buffer = (ctypes.c_float * num_floats_in_chunk)()

        while True:
            try:
                read_bytes = self.bass.BASS_ChannelGetData(decode_stream, data_buffer, chunk_size_bytes | BASS_DATA_FLOAT)
                
                # BASS_ChannelGetData returnează (DWORD)-1 la eroare (adică 4294967295)
                # Verificăm dacă e 0 (EOF) sau o valoare foarte mare (Eroare)
                if read_bytes == 0 or read_bytes > 0x7FFFFFFF: 
                    break
                
                max_val = 0.0
                count = read_bytes // 4 # 4 bytes per float
                # Safety: Nu citim mai mult decât buffer-ul alocat
                count = min(count, num_floats_in_chunk)
                
                # Python 3.14 nu mai acceptă fiabil memoryview pe acest buffer ctypes (<f).
                # Parcurgem rar buffer-ul (pas 5), suficient pentru waveform și stabil cross-version.
                if count > 0:
                    for index in range(0, count, 5):
                        sample = float(data_buffer[index])
                        abs_sample = abs(sample)
                        if abs_sample > max_val:
                            max_val = abs_sample
                
                peaks.append(max_val)
            except Exception as e:
                print(f"Waveform Loop Error: {e}")
                break

        # Curățăm stream-ul de decodare
        self.bass.BASS_StreamFree(decode_stream)
        
        return peaks, duration

    def get_waveform_bytes(self, filepath):
        """ Generează waveform-ul și îl returnează ca bytes (BLOB) pentru DB """
        peaks, _ = self.get_waveform_data(filepath)
        if not peaks: return None
        
        # Împachetăm lista de float-uri în bytes
        # 'f' = float (4 bytes)
        try:
            return struct.pack(f'{len(peaks)}f', *peaks)
        except Exception as e:
            print(f"Waveform Pack Error: {e}")
            return None

    @staticmethod
    def unpack_waveform_bytes(blob):
        """ Convertește bytes din DB înapoi în listă de float-uri """
        if not blob: return []
        count = len(blob) // 4
        return list(struct.unpack(f'{count}f', blob))

    # --- PLAYBACK ---
    def _create_stream(self, filepath):
        """ Helper intern pentru crearea unui stream nou """
        filepath = self._canonical_path(filepath)
        if not os.path.exists(filepath):
            print(f"FAILED to load (missing file): {filepath}")
            return 0
        
        # BASS_UNICODE funcționează cu UTF-16LE pentru căile trimise către BASS.
        file_bytes = self._to_bass_unicode_filename(filepath)

        # Flag-uri de bază, fără PRESCAN pentru WAV-uri pentru o mai bună compatibilitate
        base_flags = BASS_STREAM_DECODE | BASS_UNICODE
        if not filepath.lower().endswith('.wav'):
            base_flags |= 131072 # BASS_STREAM_PRESCAN

        def _build_stream(decode_flags, tempo_flags, request_tempo=False):
            decode_handle = self.bass.BASS_StreamCreateFile(False, file_bytes, 0, 0, decode_flags)
            if not decode_handle:
                return 0
            try:
                info_dec = BASS_CHANNELINFO()
                self.bass.BASS_ChannelGetInfo(decode_handle, ctypes.byref(info_dec))
                print(f"DEBUG: decode_stream handle={decode_handle}, chans={info_dec.chans}, freq={info_dec.freq}, flags={info_dec.flags}")
            except Exception:
                pass

            # If tempo processing is requested, wrap decode in a tempo handle.
            if request_tempo:
                out_handle = self.bass_fx.BASS_FX_TempoCreate(decode_handle, tempo_flags)
                if not out_handle:
                    try:
                        self.bass.BASS_StreamFree(decode_handle)
                    except:
                        pass
                    return 0
            else:
                # Use the decode_handle as the playback handle by creating a normal stream.
                # Create a playback stream directly from file (no tempo wrapper).
                try:
                    play_flags = BASS_SAMPLE_FLOAT | BASS_UNICODE
                    out_handle = self.bass.BASS_StreamCreateFile(False, file_bytes, 0, 0, play_flags)
                    if not out_handle:
                        # Fall back to using the decode handle if creating playback stream failed
                        out_handle = decode_handle
                except Exception:
                    out_handle = decode_handle
            try:
                info = BASS_CHANNELINFO()
                # Verificăm informațiile canalului pe handle-ul final
                self.bass.BASS_ChannelGetInfo(out_handle, ctypes.byref(info))
                print(f"DEBUG: Created stream handle={out_handle}, chans={info.chans}, freq={info.freq}, flags={info.flags}")
            except Exception:
                pass
            # Keep mapping from tempo/out handle -> decode handle for diagnostics
            try:
                if not hasattr(self, '_decode_for_out'):
                    self._decode_for_out = {}
                # Only map when we actually created a tempo wrapper
                if request_tempo and decode_handle != out_handle:
                    self._decode_for_out[out_handle] = decode_handle
            except:
                pass
            return out_handle

        # Decide whether we need tempo processing based on current tempo factor
        use_tempo = bool(getattr(self, 'tempo_factor', 1.0) != 1.0)
        tempo_flags = BASS_FX_FREESOURCE
        out_handle = _build_stream(base_flags, tempo_flags, request_tempo=use_tempo)
        if out_handle:
            return out_handle

        fallback_decode_flags = BASS_STREAM_DECODE | BASS_UNICODE # Fallback fără PRESCAN
        fallback_tempo_flags = BASS_FX_FREESOURCE
        out_handle = _build_stream(fallback_decode_flags, fallback_tempo_flags)
        if out_handle:
            print(f"DEBUG: Stream fallback used for {os.path.basename(filepath)}")
            return out_handle

        try:
            err = self.bass.BASS_ErrorGetCode()
            print(f"FAILED to create stream: {os.path.basename(filepath)} (BASS err={err})")
        except:
            print(f"FAILED to create stream: {os.path.basename(filepath)}")
        return 0

    def _get_window_length(self):
        total = self._cached_length
        if self.play_window_end is not None:
            total = min(total, self.play_window_end)
        return max(0.0, total - self.play_window_start)

    def manage_cache(self, keep_paths):
        """ 
        Păstrează în memorie doar stream-urile din keep_paths. 
        Încarcă ce lipsește, șterge ce e în plus.
        """
        # 1. Ștergem stream-urile vechi (care nu mai sunt necesare)
        resolved_keep_paths = set()
        for path in keep_paths:
            if not path:
                continue
            resolved_keep_paths.add(self._canonical_path(path))

        current_cached = list(self.stream_cache.keys())
        for path in current_cached:
            if path not in resolved_keep_paths:
                handle = self.stream_cache[path]
                # Safety: Nu ștergem stream-ul care cântă acum (chiar dacă logica zice altceva)
                if handle != self.stream:
                    self.bass.BASS_StreamFree(handle)
                    del self.stream_cache[path]

        # 2. Încărcăm stream-urile noi (Preload)
        for path in resolved_keep_paths:
            if path and path not in self.stream_cache:
                handle = self._create_stream(path)
                if handle:
                    self.stream_cache[path] = handle

    def _invalidate_stream_handle(self, handle):
        if not handle:
            return
        cache_keys = [path for path, cached_handle in self.stream_cache.items() if cached_handle == handle]
        for path in cache_keys:
            try:
                del self.stream_cache[path]
            except:
                pass
        try:
            self.bass.BASS_StreamFree(handle)
        except:
            pass

    def _current_stream_may_have_effects(self):
        return bool(
            self.master_dsp_enabled or
            self.fx_eq_handle or
            self.fx_limit_handle or
            self.fx_reverb_handle or
            self.fx_vst_handle or
            self.fx_stereo_handle or
            self._limiter_handles
        )

    def load_and_play(self, filepath, play_now=True):
        source_path, start_sec, end_sec = PlaylistScanner.get_playback_target(filepath)
        source_path = self._canonical_path(source_path)
        
        print(f"Loading: {os.path.basename(source_path)}")

        # 1. Oprim stream-ul curent; dacă are/poate avea FX, îl invalidăm ca să nu intre murdar în cache.
        if self.stream:
            current_handle = self.stream
            self.bass.BASS_ChannelStop(current_handle)
            if self._current_stream_may_have_effects():
                self._remove_master_fx_handles()
                self._invalidate_stream_handle(current_handle)
                self.stream = 0
            
        # 2. Verificăm Cache-ul
        if source_path in self.stream_cache:
            self.stream = self.stream_cache[source_path]
            # Resetăm poziția la 0 (în caz că a mai fost cântată)
            self.bass.BASS_ChannelSetPosition(self.stream, 0, 0)
        else:
            self.stream = self._create_stream(source_path)
            if self.stream:
                self.stream_cache[source_path] = self.stream
            else:
                print(f"FAILED to load: {os.path.basename(source_path)}")
                return False

        self.play_window_start = max(0.0, float(start_sec or 0.0))
        self.play_window_end = float(end_sec) if end_sec is not None else None

        # 🔥 AUTO-GAIN: Amplificăm MP3-urile cu 7dB pentru a egala FLAC-urile
        if source_path.lower().endswith('.mp3'):
            self.format_gain_db = 7.0
        else:
            self.format_gain_db = 0.0

        if self.stream:
            # Resetăm handle-urile FX (ele sunt legate de stream-ul vechi)
            self.fx_eq_handle = 0
            self.fx_limit_handle = 0
            self.fx_reverb_handle = 0
            self.fx_vst_handle = 0
            self.fx_stereo_handle = 0
            
            # 🔥 OPTIMIZARE: Cache-uim durata stream-ului (nu se schimbă în timpul redării)
            len_bytes = self.bass.BASS_ChannelGetLength(self.stream, 0)
            self._cached_length = max(0, self.bass.BASS_ChannelBytes2Seconds(self.stream, len_bytes))

            if self.play_window_end is not None:
                self.play_window_end = min(self.play_window_end, self._cached_length)
                if self.play_window_end < self.play_window_start:
                    self.play_window_end = self.play_window_start

            if self.play_window_start > 0:
                start_bytes = self.bass.BASS_ChannelSeconds2Bytes(self.stream, ctypes.c_double(self.play_window_start))
                self.bass.BASS_ChannelSetPosition(self.stream, start_bytes, 0)
            
            self.apply_preamp_volume()
            self.bass.BASS_ChannelSetAttribute(self.stream, BASS_ATTRIB_PAN, self.balance_pan)
            if self.master_dsp_enabled:
                self.init_effects()
            self._maybe_open_debug_vst_ui()
            if play_now:
                self.bass.BASS_ChannelStart(self.stream)
            print(f"OK: Playing {os.path.basename(source_path)}")
            return True
        return False

    def toggle_play(self):
        if not self.stream: return False
        state = self.bass.BASS_ChannelIsActive(self.stream)
        if state == 1: # Playing
            self.bass.BASS_ChannelPause(self.stream)
            return False 
        elif state == 3: # Paused
            self.bass.BASS_ChannelStart(self.stream)
            return True 
        elif state == 0: # Stopped
            # Verificăm dacă suntem la final pentru a decide comportamentul
            pos_bytes = self.bass.BASS_ChannelGetPosition(self.stream, 0)
            pos_sec = self.bass.BASS_ChannelBytes2Seconds(self.stream, pos_bytes)
            at_end = pos_sec >= max(0.0, self._cached_length - 0.01)
            
            if at_end:
                # Dacă e la final -> Restart de la început
                if self.play_window_start > 0:
                    start_bytes = self.bass.BASS_ChannelSeconds2Bytes(self.stream, ctypes.c_double(self.play_window_start))
                    self.bass.BASS_ChannelSetPosition(self.stream, start_bytes, 0)
                    self.bass.BASS_ChannelStart(self.stream)
                else:
                    self.bass.BASS_ChannelPlay(self.stream, True)
            else:
                # Dacă nu e la final (ex: seek înapoi) -> Continuă
                self.bass.BASS_ChannelStart(self.stream)
            return True
        return False

    def seek(self, seconds):
        if self.stream:
            target = float(seconds)
            if self.play_window_start > 0 or self.play_window_end is not None:
                window_total = self._get_window_length()
                target = max(0.0, min(target, window_total)) + self.play_window_start
            pos_bytes = self.bass.BASS_ChannelSeconds2Bytes(self.stream, ctypes.c_double(target))
            self.bass.BASS_ChannelSetPosition(self.stream, pos_bytes, 0)

    def get_position_info(self):
        # 🔥 OPTIMIZARE: Folosim durata cache-uită (2 apeluri BASS în loc de 4)
        if self.stream:
            total = self._cached_length
            pos_bytes = self.bass.BASS_ChannelGetPosition(self.stream, 0)
            current = self.bass.BASS_ChannelBytes2Seconds(self.stream, pos_bytes)

            if self.play_window_end is not None and current >= self.play_window_end:
                end_bytes = self.bass.BASS_ChannelSeconds2Bytes(self.stream, ctypes.c_double(self.play_window_end))
                self.bass.BASS_ChannelSetPosition(self.stream, end_bytes, 0)
                self.bass.BASS_ChannelStop(self.stream)
                current = self.play_window_end

            if self.play_window_start > 0 or self.play_window_end is not None:
                total = self._get_window_length()
                current = max(0.0, current - self.play_window_start)
                if current > total:
                    current = total

            return max(0, current), total
        return 0, 0

    def get_raw_length(self):
        # 🔥 OPTIMIZARE: Folosim cache-ul
        if self.stream:
            if self.play_window_start > 0 or self.play_window_end is not None:
                return self._get_window_length()
            return self._cached_length
        return 0

    def get_fft(self):
        """ Returnează spectrele de frecvență în timp real (128 de float-uri) """
        if not self.stream: return None
        buffer = (ctypes.c_float * 128)()
        res = self.bass.BASS_ChannelGetData(self.stream, buffer, BASS_DATA_FFT256)
        if res == 0xFFFFFFFF: # BASS_ERROR
            return None
        return list(buffer)

    def is_playing(self):
        if not self.stream: return False
        return self.bass.BASS_ChannelIsActive(self.stream) == 1

    # --- DSP & EFECTE ---
    def _remove_master_fx_handles(self):
        if not self.stream:
            return
        for attr in (
            'fx_eq_handle',
            'fx_limit_handle',
            'fx_reverb_handle',
            'fx_vst_handle',
            'fx_stereo_handle',
        ):
            handle = getattr(self, attr, 0)
            if handle:
                try:
                    self.bass.BASS_ChannelRemoveFX(self.stream, handle)
                except:
                    pass
                setattr(self, attr, 0)
        if self._limiter_handles:
            for handle in list(self._limiter_handles):
                try:
                    self.bass.BASS_ChannelRemoveFX(self.stream, handle)
                except:
                    pass
            self._limiter_handles.clear()

    def _attach_fx_with_fallback(self, priority, candidate_types, label):
        if not self.stream:
            return 0
        tried = set()
        for fx_type in candidate_types:
            if fx_type in tried:
                continue
            tried.add(fx_type)
            try:
                print(f"DEBUG EQ: attempting attach {label} fx_type={fx_type} priority={priority} on stream={self.stream}")
                handle = self.bass.BASS_ChannelSetFX(self.stream, int(fx_type), int(priority))
                if handle:
                    self._fx_type_ids[label] = int(fx_type)
                    return handle
            except:
                pass
        try:
            err = self.bass.BASS_ErrorGetCode()
            print(f"DEBUG EQ: failed to attach {label} FX (err={err}, tried={sorted(list(tried))})")
        except:
            print(f"DEBUG EQ: failed to attach {label} FX")
        return 0

    def init_effects(self):
        if not self.stream: return
        # Evităm stacking accidental de FX pe același stream
        self._remove_master_fx_handles()
        
        if self.limiter_on: 
            self._apply_limiter_internal()
        print("DEBUG EQ: post init -> chain cleanly reset for dynamic attachment")
        try:
            print(f"DEBUG EQ: fx types mapping -> {self._fx_type_ids}")
        except:
            pass
        # Run a quick diagnostic to verify FX parameter application
        try:
            self._diagnose_fx()
        except Exception:
            pass

    def set_parametric_eq(self, band, freq, gain, bandwidth=2.5):
        if not self.stream or not self.master_dsp_enabled:
            return

        # Clamp band index to a safe range. Some builds of the BASS PEAK EQ support only 0-9.
        try:
            band_int = int(band)
        except:
            band_int = 0
        if band_int < 0:
            band_int = 0
        if band_int > 19:
            print(f"DEBUG EQ: requested band {band_int} out of range, clamping to 19")
            band_int = 19
            
        self._eq_bands_gains[band_int] = float(gain)
        
        # Verificăm dacă absolut TOATE benzile EQ sunt la 0
        all_zero = all(abs(g) < 0.001 for g in self._eq_bands_gains.values())
        
        if all_zero:
            if self.fx_eq_handle:
                try: self.bass.BASS_ChannelRemoveFX(self.stream, self.fx_eq_handle)
                except: pass
                self.fx_eq_handle = 0
            return
            
        if not self.fx_eq_handle:
            self.fx_eq_handle = self._attach_fx_with_fallback(0, [BASS_FX_BFX_PEAKEQ], "parametric_eq")
            if not self.fx_eq_handle:
                if not self._eq_unavailable_logged:
                    print("DEBUG EQ: parametric handle unavailable; slider changes ignored")
                    self._eq_unavailable_logged = True
                return

        self._eq_unavailable_logged = False
        eq = BASS_BFX_PEAKEQ()
        eq.lBand = band_int
        eq.fCenter = float(freq)
        eq.fBandwidth = float(bandwidth)
        eq.fGain = float(gain)
        eq.lChannel = -1
        ok = self.bass_fx.BASS_FXSetParameters(self.fx_eq_handle, ctypes.byref(eq))
        if not ok:
            try:
                err = self.bass.BASS_ErrorGetCode()
                print(f"DEBUG EQ: BASS_FXSetParameters(parametric) failed -> err={err}")
            except:
                print("DEBUG EQ: BASS_FXSetParameters(parametric) failed")

    def set_master_dsp(self, enabled):
        prev_enabled = bool(self.master_dsp_enabled)
        self.master_dsp_enabled = enabled
        if not self.stream: return
        if enabled:
            # Dacă se reaplică ON peste ON, reinițializăm curat ca să nu rămână FX duplicate
            if prev_enabled:
                self._remove_master_fx_handles()
            self.apply_preamp_volume()
            self.init_effects()
            self._apply_bass_shelf()
            self._apply_treble_shelf()
            self.bass.BASS_ChannelSetAttribute(self.stream, BASS_ATTRIB_PAN, self.balance_pan)
        else:
            self._remove_master_fx_handles()
            self.apply_preamp_volume()

    def set_preamp(self, db_value):
        self.preamp_db = db_value
        self.apply_preamp_volume()

    def set_volume(self, value_0_to_1):
        """ Setează volumul master (0.0 - 1.0) """
        self.master_volume = max(0.0, min(1.0, float(value_0_to_1)))
        self.apply_preamp_volume()

    def apply_preamp_volume(self):
        if not self.stream: return
        base_vol = 0.8
        
        # Calculăm gain-ul total (Preamp Slider + Format Auto-Gain)
        total_db = self.preamp_db + self.format_gain_db
        preamp_factor = math.pow(10, total_db / 20.0)
        
        # Aplicăm și volumul master definit de slider
        final_vol = max(0.0, min(1.0, base_vol * preamp_factor * self.master_volume))
        self.bass.BASS_ChannelSetAttribute(self.stream, BASS_ATTRIB_VOL, final_vol)

    def configure_vst_debug(self, open_on_start=False, open_wider=True):
        self.debug_vst_ui_on_start = bool(open_on_start)
        self.debug_vst_open_wider = bool(open_wider)

    def open_wider_ui_debug(self, host_hwnd=None, prefer_popup=None):
        if not self.stream:
            print("DEBUG: Cannot open Wider UI: no active stream")
            return False
        if not self._ensure_wider_vst_loaded():
            print("DEBUG: Cannot open Wider UI: Wider VST not loaded")
            return False
        if prefer_popup is None:
            prefer_popup = (os.name == 'nt' and not host_hwnd)
        return self._open_vst_editor(self.fx_vst_handle, "Wider", host_hwnd=host_hwnd, prefer_popup=prefer_popup)

    def set_vst_editor_parent_hwnd(self, hwnd):
        try:
            self.vst_editor_parent_hwnd = int(hwnd or 0)
        except:
            self.vst_editor_parent_hwnd = 0

    def _open_vst_editor(self, fx_handle, name, host_hwnd=None, prefer_popup=False):
        if not fx_handle or not self.bass_vst:
            return False
        if not hasattr(self.bass_vst, 'BASS_VST_EmbedEditor'):
            print(f"DEBUG: VST editor API not available for {name}")
            return False
        try:
            target_hwnd = None
            if host_hwnd:
                target_hwnd = int(host_hwnd)
            elif not prefer_popup and self.vst_editor_parent_hwnd:
                target_hwnd = self.vst_editor_parent_hwnd

            parent = ctypes.c_void_p(target_hwnd) if target_hwnd else None
            ok = self.bass_vst.BASS_VST_EmbedEditor(fx_handle, parent)
            if not ok and parent is not None:
                ok = self.bass_vst.BASS_VST_EmbedEditor(fx_handle, None)
            print(f"DEBUG: Open VST editor {name} popup={prefer_popup} host_hwnd={target_hwnd or 0} -> {ok}")
            return bool(ok)
        except Exception as e:
            print(f"DEBUG: Failed to open VST editor {name}: {e}")
            return False

    def _ensure_wider_vst_loaded(self):
        if not self.stream:
            return False
        if not self.bass_vst:
            return False
        if self.fx_vst_handle:
            return True

        plugin_path = self.wider_vst_path or self.vst_plugin_path
        if not plugin_path or not os.path.exists(plugin_path):
            return False
        try:
            path_bytes = plugin_path.encode('utf-8')
            self.fx_vst_handle = self.bass_vst.BASS_VST_ChannelSetDSP(self.stream, path_bytes, 0, 1)
            if self.fx_vst_handle:
                self._apply_wider_params()
                print(f"DEBUG: Wider VST loaded: {os.path.basename(plugin_path)}")
                return True
        except:
            pass
        return False

    def _apply_wider_params(self):
        if not self.bass_vst or not self.fx_vst_handle:
            return
        # Wider UI ajunge la ~400% la param=1.0; limităm la 200% => param max 0.5
        width = max(0.0, min(0.5, float(self.stereo_expand_value) / 200.0))
        low_bypass = max(0.0, min(1.0, float(self.stereo_low_bypass_hz) / 20000.0))
        self.bass_vst.BASS_VST_SetParam(self.fx_vst_handle, 0, ctypes.c_float(width))
        self.bass_vst.BASS_VST_SetParam(self.fx_vst_handle, 1, ctypes.c_float(low_bypass))
        
        # Bypassed (Power OFF) dacă lățimea e 0%
        is_bypassed = (self.stereo_expand_value <= 0.0)
        if hasattr(self.bass_vst, 'BASS_VST_SetBypass'):
            self.bass_vst.BASS_VST_SetBypass(self.fx_vst_handle, is_bypassed)
            
        print(f"DEBUG WIDER: SetParam width={width:.4f} low_bypass={low_bypass:.4f} bypassed={is_bypassed} handle={self.fx_vst_handle}")

    def _log_wider_inactive_once(self, reason):
        if not self._wider_inactive_logged:
            print(f"DEBUG: Wider not loaded, Stereo Expand inactive ({reason})")
            self._wider_inactive_logged = True

    def get_wider_availability(self):
        """Returnează (disponibil, motiv) pentru Wider VST, folosit de indicatorul UI."""
        if not self.bass_vst:
            return False, "BASS_VST library missing"

        plugin_path = self.wider_vst_path or self.vst_plugin_path
        if not plugin_path or not os.path.exists(plugin_path):
            return False, "Wider plugin file missing"

        return True, ""

    def _maybe_open_debug_vst_ui(self):
        if not self.debug_vst_ui_on_start or self._debug_vst_ui_opened_once:
            return
        if not self.stream:
            return

        opened_any = False
        if self.debug_vst_open_wider and self._ensure_wider_vst_loaded():
            opened_any = self._open_vst_editor(self.fx_vst_handle, "Wider", prefer_popup=(os.name == 'nt')) or opened_any

        if opened_any:
            self._debug_vst_ui_opened_once = True

    # --- Bass / Treble Knobs (true low-shelf/high-shelf) ---
    def _apply_bass_shelf(self):
        if not self.stream or not self.master_dsp_enabled:
            return
            
        gain = float((self._last_bass_knob / 100.0) * 15.0)
        
        # 🔥 CLOPOT BASS: Centrul la ~0Hz (20Hz limită BASS), marginea dreaptă la Hz din setări
        center_freq = 20.0 
        upper_edge = max(21.0, float(self.bass_shelf_freq))
        
        # Calculăm matematic lățimea (în octave) ca clopotul să se închidă exact la marginea setată
        bw_octaves = 2.0 * math.log2(upper_edge / center_freq)
        
        # Aplicăm pe Band 0
        self.set_parametric_eq(0, center_freq, gain, bandwidth=bw_octaves)
        
        log_state = (round(center_freq, 2), round(gain, 3), round(bw_octaves, 2))
        if log_state != self._last_bass_shelf_log:
            self._last_bass_shelf_log = log_state
            print(f"DEBUG TONE: Bass mapped to PeakEQ Band 0: center={center_freq}Hz gain={gain}dB bw={bw_octaves:.2f}oct")

    def _diagnose_fx(self):
        if not self.stream:
            print("DEBUG EQ DIAG: no stream to diagnose")
            return
        try:
            info = BASS_CHANNELINFO()
            self.bass.BASS_ChannelGetInfo(self.stream, ctypes.byref(info))
            print(f"DEBUG EQ DIAG: stream info -> chans={info.chans} freq={info.freq} flags={info.flags} ctype={info.ctype}")
        except Exception as e:
            print(f"DEBUG EQ DIAG: failed to get channel info: {e}")

        if not self.fx_eq_handle:
            print("DEBUG EQ DIAG: no fx_eq_handle")
            return

        try:
            # Attempt to read current params
            cur = BASS_BFX_PEAKEQ()
            ok_read = False
            try:
                ok_read = bool(self.bass_fx.BASS_FXGetParameters(self.fx_eq_handle, ctypes.byref(cur)))
            except Exception:
                ok_read = False
            if ok_read:
                print(f"DEBUG EQ DIAG: readback OK -> band={cur.lBand} center={cur.fCenter} gain={cur.fGain} bw={cur.fBandwidth}")
            else:
                try:
                    err = self.bass.BASS_ErrorGetCode()
                    print(f"DEBUG EQ DIAG: readback failed -> err={err}")
                except:
                    print("DEBUG EQ DIAG: readback failed (no err)")

            # Try applying an extreme test param (non-destructive band 0)
            test = BASS_BFX_PEAKEQ()
            test.lBand = 0
            test.fCenter = 1000.0
            test.fBandwidth = 1.0
            test.fGain = 15.0
            test.lChannel = -1
            ok_set = bool(self.bass_fx.BASS_FXSetParameters(self.fx_eq_handle, ctypes.byref(test)))
            if ok_set:
                print("DEBUG EQ DIAG: test set succeeded")
                # readback after set
                try:
                    post = BASS_BFX_PEAKEQ()
                    if bool(self.bass_fx.BASS_FXGetParameters(self.fx_eq_handle, ctypes.byref(post))):
                        print(f"DEBUG EQ DIAG: post-read -> band={post.lBand} center={post.fCenter} gain={post.fGain} bw={post.fBandwidth}")
                    else:
                        err2 = self.bass.BASS_ErrorGetCode()
                        print(f"DEBUG EQ DIAG: post-read failed -> err={err2}")
                except Exception as e:
                    print(f"DEBUG EQ DIAG: exception during post-read: {e}")
            else:
                try:
                    err3 = self.bass.BASS_ErrorGetCode()
                    print(f"DEBUG EQ DIAG: test set failed -> err={err3}")
                except:
                    print("DEBUG EQ DIAG: test set failed (no err)")
                # Try attaching same FX type to the original decode handle (if available) and set params there
                try:
                    decode_h = None
                    if hasattr(self, '_decode_for_out'):
                        decode_h = self._decode_for_out.get(self.stream)
                    if decode_h:
                        print(f"DEBUG EQ DIAG: attempting attach/set on decode handle {decode_h}")
                        alt_handle = self.bass.BASS_ChannelSetFX(decode_h, int(self._fx_type_ids.get('parametric_eq', BASS_FX_BFX_PEAKEQ)), 0)
                        if alt_handle:
                            ok_alt_set = bool(self.bass_fx.BASS_FXSetParameters(alt_handle, ctypes.byref(test)))
                            if ok_alt_set:
                                print("DEBUG EQ DIAG: test set succeeded on decode handle")
                                try:
                                    self.bass.BASS_ChannelRemoveFX(decode_h, alt_handle)
                                except:
                                    pass
                            else:
                                try:
                                    err4 = self.bass.BASS_ErrorGetCode()
                                    print(f"DEBUG EQ DIAG: test set on decode handle failed -> err={err4}")
                                except:
                                    print("DEBUG EQ DIAG: test set on decode handle failed (no err)")
                                try:
                                    self.bass.BASS_ChannelRemoveFX(decode_h, alt_handle)
                                except:
                                    pass
                        else:
                            print("DEBUG EQ DIAG: failed to attach FX on decode handle")
                except Exception as e:
                    print(f"DEBUG EQ DIAG: exception during decode-handle probe: {e}")
        except Exception as e:
            print(f"DEBUG EQ DIAG: unexpected error: {e}")

    def _apply_treble_shelf(self):
        if not self.stream or not self.master_dsp_enabled:
            return
            
        gain = float((self._last_treble_knob / 100.0) * 15.0)
        
        # 🔥 CLOPOT TREBLE: Centrul la 20000Hz (maxim dreapta), marginea stângă la Hz din setări
        center_freq = 20000.0
        lower_edge = min(19999.0, float(self.treble_shelf_freq))
        
        # Calculăm matematic lățimea (în octave) ca clopotul să se deschidă exact de la marginea setată
        bw_octaves = 2.0 * math.log2(center_freq / lower_edge)
        
        # Aplicăm pe Band 1
        self.set_parametric_eq(1, center_freq, gain, bandwidth=bw_octaves)
        
        log_state = (round(center_freq, 2), round(gain, 3), round(bw_octaves, 2))
        if log_state != self._last_treble_shelf_log:
            self._last_treble_shelf_log = log_state
            print(f"DEBUG TONE: Treble mapped to PeakEQ Band 1: center={center_freq}Hz gain={gain}dB bw={bw_octaves:.2f}oct")

    def set_bass_knob(self, value_0_to_100):
        """Knob pentru Bass: 0 = 0dB, 100 = +15dB (boost-only)."""
        try:
            v = float(value_0_to_100)
        except:
            return
        self._last_bass_knob = max(0.0, min(100.0, v))
        self._apply_bass_shelf()

    def set_treble_knob(self, value_0_to_100):
        """Knob pentru Treble: 0 = 0dB, 100 = +15dB (boost-only)."""
        try:
            v = float(value_0_to_100)
        except:
            return
        self._last_treble_knob = max(0.0, min(100.0, v))
        self._apply_treble_shelf()

    def set_bass_threshold(self, freq_hz):
        try:
            f = float(freq_hz)
        except:
            return
        # clamp reasonable range 0-500
        f = max(0.0, min(500.0, f))
        self.bass_shelf_freq = f
        # reapply current knob value
        self._apply_bass_shelf()

    def set_treble_threshold(self, freq_hz):
        try:
            f = float(freq_hz)
        except:
            return
        # clamp to a wider reasonable range 2000-20000
        f = max(2000.0, min(20000.0, f))
        self.treble_shelf_freq = f
        self._apply_treble_shelf()

    def set_limiter(self, active):
        self.limiter_on = active
        self._apply_limiter_internal()

    def debug_reset_limiter_if_off(self):
        """Reset hard al stării limiter, util pentru recuperare dacă a rămas efect rezidual."""
        if self.limiter_on:
            print("DEBUG: Limiter reset skipped (limiter_on=True)")
            return False

        if not self.stream:
            return True

        if self._limiter_handles:
            for handle in list(self._limiter_handles):
                try:
                    self.bass.BASS_ChannelRemoveFX(self.stream, handle)
                except:
                    pass
            self._limiter_handles.clear()
        if self.fx_limit_handle:
            try:
                self.bass.BASS_ChannelRemoveFX(self.stream, self.fx_limit_handle)
            except:
                pass
            self.fx_limit_handle = 0

        if self.master_dsp_enabled:
            self.init_effects()
            self.apply_preamp_volume()
        else:
            self._remove_master_fx_handles()
            self.apply_preamp_volume()

        return True

    def debug_reset_all_effects_to_neutral(self):
        """Resetează lanțul DSP la stare neutră și invalidează cache-ul pentru stream-uri potențial murdare."""
        self.limiter_on = False
        self.preamp_db = 0.0
        self._last_bass_knob = 0.0
        self._last_treble_knob = 0.0
        self.stereo_expand_value = 0.0
        self.stereo_low_bypass_hz = 0.0
        self.reverb_damp = 0.0
        self.reverb_filter = 0.0
        self.reverb_fade = 0.0
        self.reverb_size = 0.0
        self.reverb_predelay = 0.0
        self.reverb_predelay_mix = 0.0
        self.balance_pan = 0.0
        current_handle = self.stream
        if current_handle:
            self._remove_master_fx_handles()
            try:
                self.bass.BASS_ChannelSetAttribute(current_handle, BASS_ATTRIB_TEMPO, 0.0)
            except:
                pass
            try:
                self.bass.BASS_ChannelSetAttribute(current_handle, BASS_ATTRIB_PAN, 0.0)
            except:
                pass

        for path, handle in list(self.stream_cache.items()):
            if handle != current_handle:
                self._invalidate_stream_handle(handle)

        if current_handle:
            self.apply_preamp_volume()

        return True

    def _apply_limiter_internal(self):
        if not self.stream or not self.master_dsp_enabled:
            return
            
        if not self.limiter_on:
            if self.fx_limit_handle:
                try: self.bass.BASS_ChannelRemoveFX(self.stream, self.fx_limit_handle)
                except: pass
                self.fx_limit_handle = 0
                print("DEBUG EQ: Limiter bypassed (OFF)")
            if self._limiter_handles:
                for handle in list(self._limiter_handles):
                    try: self.bass.BASS_ChannelRemoveFX(self.stream, handle)
                    except: pass
                self._limiter_handles.clear()
            return
            
        if self.fx_limit_handle == 0:
            self.fx_limit_handle = self._attach_fx_with_fallback(1, [BASS_FX_BFX_COMPRESSOR2], "limiter")
        if self.fx_limit_handle:
            self._limiter_handles.add(self.fx_limit_handle)
        comp = BASS_BFX_COMPRESSOR2()
        comp.fGain = 0.0
        comp.fThreshold = -12.0
        comp.fRatio = 10.0
        comp.fAttack = 10.0
        comp.fRelease = 200.0
        comp.lChannel = -1
        self.bass_fx.BASS_FXSetParameters(self.fx_limit_handle, ctypes.byref(comp))

    # --- FUNCȚII NOI PENTRU KNOB-URI ---
    
    def set_tempo(self, factor):
        """ Factor: 0.5 (jumătate) ... 1.0 (normal) ... 3.0 (triplu) """
        try:
            factor = float(factor)
        except:
            return
        prev = getattr(self, 'tempo_factor', 1.0)
        self.tempo_factor = factor
        # If no active stream, nothing else to do now
        if not self.stream:
            return
        # If tempo factor changed between 1.0 and non-1.0, recreate the stream to match capability
        recreate_needed = (prev == 1.0 and factor != 1.0) or (prev != 1.0 and factor == 1.0)
        # BASS_ATTRIB_TEMPO ia procente: 0 = normal, -50 = jumătate, +100 = dublu
        percent = (factor - 1.0) * 100.0
        if recreate_needed:
            # Try to find the source path for current stream in cache
            source_path = None
            for path, handle in self.stream_cache.items():
                if handle == self.stream:
                    source_path = path
                    break
            # Save playback position
            try:
                pos_bytes = self.bass.BASS_ChannelGetPosition(self.stream, 0)
                pos_sec = self.bass.BASS_ChannelBytes2Seconds(self.stream, pos_bytes)
            except:
                pos_sec = 0.0
            was_playing = self.bass.BASS_ChannelIsActive(self.stream) == 1
            if source_path:
                # Reload and play with new stream type
                self.load_and_play(source_path, play_now=False)
                # Seek back to previous position
                try:
                    target_bytes = self.bass.BASS_ChannelSeconds2Bytes(self.stream, ctypes.c_double(max(0.0, pos_sec)))
                    self.bass.BASS_ChannelSetPosition(self.stream, target_bytes, 0)
                except:
                    pass
                # Apply tempo attribute if needed
                try:
                    self.bass.BASS_ChannelSetAttribute(self.stream, BASS_ATTRIB_TEMPO, percent)
                except:
                    pass
                if was_playing:
                    try:
                        self.bass.BASS_ChannelStart(self.stream)
                    except:
                        pass
            else:
                # Fallback: just set attribute on current stream
                try:
                    self.bass.BASS_ChannelSetAttribute(self.stream, BASS_ATTRIB_TEMPO, percent)
                except:
                    pass
        else:
            try:
                self.bass.BASS_ChannelSetAttribute(self.stream, BASS_ATTRIB_TEMPO, percent)
            except:
                pass

    def set_balance(self, value_0_to_100):
        """ 0 = Stânga, 50 = Centru, 100 = Dreapta """
        # BASS_ATTRIB_PAN: -1.0 (Left) ... 0.0 (Center) ... +1.0 (Right)
        pan = (value_0_to_100 - 50.0) / 50.0
        self.balance_pan = max(-1.0, min(1.0, pan))
        if self.stream:
            self.bass.BASS_ChannelSetAttribute(self.stream, BASS_ATTRIB_PAN, self.balance_pan)

    def set_reverb(self, damp, filter_val, fade, size, delay=0, predelay_mix=0):
        """ Parametrii vin 0-100 din UI """
        try:
            damp = float(damp)
        except:
            damp = 0.0
        try:
            filter_val = float(filter_val)
        except:
            filter_val = 0.0
        try:
            fade = float(fade)
        except:
            fade = 0.0
        try:
            size = float(size)
        except:
            size = 0.0
        try:
            delay = float(delay)
        except:
            delay = 0.0

        try:
            predelay_mix = float(predelay_mix)
        except:
            predelay_mix = 0.0

        damp = max(0.0, min(100.0, damp))
        filter_val = max(0.0, min(100.0, filter_val))
        fade = max(0.0, min(100.0, fade))
        size = max(0.0, min(100.0, size))
        delay = max(0.0, min(100.0, delay))
        predelay_mix = max(0.0, min(100.0, predelay_mix))

        self.reverb_damp = damp
        self.reverb_filter = filter_val
        self.reverb_fade = fade
        self.reverb_size = size
        self.reverb_predelay = delay
        self.reverb_predelay_mix = predelay_mix

        # Dacă Fade și Pre-Delay Mix sunt 0, Reverb-ul este inaudibil
        is_bypassed = (fade <= 0.0 and predelay_mix <= 0.0)

        if not self.stream or not self.master_dsp_enabled:
            return

        if is_bypassed:
            if self.fx_reverb_handle:
                try:
                    self.bass.BASS_ChannelRemoveFX(self.stream, self.fx_reverb_handle)
                except:
                    pass
                self.fx_reverb_handle = 0
            return
        
        if self.fx_reverb_handle == 0:
            # FREEVERB este un algoritm modern, mult superior, cu Damp și Size nativ
            self.fx_reverb_handle = self._attach_fx_with_fallback(2, [BASS_FX_BFX_FREEVERB, BASS_FX_BFX_REVERB], "reverb")
            
        if self.fx_reverb_handle == 0:
            return
            
        active_fx = self._fx_type_ids.get("reverb", BASS_FX_BFX_FREEVERB)
        
        if active_fx == BASS_FX_BFX_FREEVERB:
            rev = BASS_BFX_FREEVERB()
            rev.fDryMix = 1.0
            
            # Fade controlează intensitatea efectului
            wet = math.pow(fade / 100.0, 1.5) * 1.5 + (predelay_mix / 100.0 * 0.5)
            rev.fWetMix = float(max(0.0, min(3.0, wet)))
            
            # Size controlează direct Room Size
            rev.fRoomSize = float(max(0.0, min(1.0, size / 100.0)))
            
            # Damp și Filter taie frecvențele înalte (absorbție)
            damp_total = (damp / 100.0) + (filter_val / 100.0 * 0.4)
            rev.fDamp = float(max(0.0, min(1.0, damp_total)))
            
            # Pre-Delay crește Width-ul (dimensiunea stereo a camerei)
            rev.fWidth = float(max(0.0, min(1.0, delay / 100.0)))
            
            rev.lMode = 0
            rev.lChannel = -1
            self.bass_fx.BASS_FXSetParameters(self.fx_reverb_handle, ctypes.byref(rev))
        else:
            # Fallback Legacy
            rev = BASS_BFX_REVERB()
            rev.fLevel = float(max(0.0, min(8.0, (fade / 100.0) * 5.0)))
            rev.lDelay = int(math.pow(delay / 100.0, 1.5) * 1200)
            self.bass_fx.BASS_FXSetParameters(self.fx_reverb_handle, ctypes.byref(rev))

    def set_stereo_expand(self, value_0_to_100):
        """Control Stereo Expand doar prin Wider VST (fără fallback nativ)."""
        self.stereo_expand_value = max(0.0, min(100.0, float(value_0_to_100)))
        if not self.stream or not self.master_dsp_enabled:
            return

        if not self.bass_vst:
            self._log_wider_inactive_once("bass_vst_missing")
            return

        if self.fx_vst_handle == 0:
            if self.stereo_expand_value <= 0.0:
                return # Nu încărcăm VST-ul nou dacă setarea e pe 0 direct
            self._ensure_wider_vst_loaded()

        if self.fx_vst_handle:
            self._wider_inactive_logged = False
            self._apply_wider_params()
        else:
            self._log_wider_inactive_once("wider_vst_unavailable")

    def set_stereo_low_bypass(self, value_hz):
        self.stereo_low_bypass_hz = max(0.0, min(20000.0, float(value_hz)))
        if not self.stream or not self.master_dsp_enabled:
            return
            
        if not self.bass_vst:
            self._log_wider_inactive_once("bass_vst_missing")
            return
            
        if self.fx_vst_handle == 0:
            if self.stereo_expand_value <= 0.0:
                return
            self._ensure_wider_vst_loaded()
            
        if self.fx_vst_handle:
            self._wider_inactive_logged = False
            self._apply_wider_params()
        else:
            self._log_wider_inactive_once("wider_vst_unavailable")

    def free(self):
        # Curățăm tot cache-ul la ieșire
        for handle in self.stream_cache.values():
            self.bass.BASS_StreamFree(handle)
        self.stream_cache.clear()
        if self.bass:
            self.bass.BASS_Free()