import os
import hashlib
import mutagen
import re
import unicodedata
from mutagen.easyid3 import EasyID3
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt

class PlaylistScanner:
    AUDIO_EXT = ('.mp3', '.flac', '.wav', '.ogg', '.m4a')
    CUE_EXT = ('.cue',)
    IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
    COVER_NAMES = ['cover', 'folder', 'front', 'album', 'artwork', 'thumb']
    MAX_ARTWORK_SCAN_DEPTH = 2
    CUE_MARKER = "::CUE::"
    _cue_cache = {}

    @staticmethod
    def get_all_songs_recursive(root_folder):
        songs = []
        for root, dirs, files in os.walk(root_folder):
            cue_tracks, cue_sources = PlaylistScanner._get_cue_tracks_for_folder(root)
            songs.extend([t['virtual_path'] for t in cue_tracks])

            # Collect actual audio files in folder (excluding cue sources)
            audio_files = []
            for file in sorted(files):
                full_path = os.path.join(root, file)
                lower = file.lower()
                if lower.endswith(PlaylistScanner.AUDIO_EXT):
                    if full_path in cue_sources:
                        continue
                    audio_files.append(full_path)

            # Filter out full-source files when folder contains split tracks (heuristic)
            audio_files = PlaylistScanner._filter_out_full_sources(audio_files)
            songs.extend(audio_files)
        songs.sort() # 🔥 IMPORTANT: Sortăm pentru a avea o coadă stabilă în MainApp
        return songs

    @staticmethod
    def get_folder_content(path):
        try: items = sorted(os.listdir(path))
        except OSError: return [], []

        folders = []
        files = []

        for name in items:
            if name.startswith('.'): continue
            full_path = os.path.join(path, name)
            if os.path.isdir(full_path):
                folders.append(full_path)

        cue_tracks, cue_sources = PlaylistScanner._get_cue_tracks_for_folder(path)
        files.extend([t['virtual_path'] for t in cue_tracks])

        # Build list of audio files (excluding cue_sources) then filter
        audio_files = []
        for name in items:
            if name.startswith('.'):
                continue
            full_path = os.path.join(path, name)
            if not os.path.isfile(full_path):
                continue
            if name.lower().endswith(PlaylistScanner.AUDIO_EXT):
                if full_path in cue_sources:
                    continue
                audio_files.append(full_path)

        audio_files = PlaylistScanner._filter_out_full_sources(audio_files)
        files.extend(audio_files)

        files.sort()
        return folders, files

    @staticmethod
    def get_folder_stats(folder_path):
        """ 
        OPTIMIZAT: Returnează doar numărul de piese rapid.
        Nu mai calculăm durata recursivă deschizând fișierele (prea lent).
        Durata va fi 0 dacă nu e în DB, dar interfața nu va îngheța.
        """
        count = 0
        # Nu calculăm total_seconds aici prin os.walk + mutagen pentru că blochează UI-ul
        # la foldere mari. Lăsăm Logic-ul să facă SUM din DB dacă există.
        
        try:
            for root, dirs, files in os.walk(folder_path):
                cue_tracks, cue_sources = PlaylistScanner._get_cue_tracks_for_folder(root)
                count += len(cue_tracks)

                for file in files:
                    if file.lower().endswith(PlaylistScanner.AUDIO_EXT):
                        full_path = os.path.join(root, file)
                        if full_path in cue_sources:
                            continue
                        count += 1
        except: pass
        
        return count, 0 # Returnăm 0 secunde (safe fallback)

    @staticmethod
    def get_track_metadata(filepath):
        cue_track = PlaylistScanner.get_cue_track_info(filepath)
        if cue_track:
            title = cue_track.get('title') or os.path.basename(cue_track['source_path'])
            artist = cue_track.get('artist') or "Unknown Artist"
            album = cue_track.get('album') or "Unknown Album"
            duration_seconds = cue_track.get('duration', 0.0) or 0.0
            if duration_seconds == 0:
                duration_seconds = 1.0
            ext = os.path.splitext(cue_track['source_path'])[1].lower()
            return title, artist, album, duration_seconds, ext

        filename = os.path.basename(filepath)
        title = filename
        artist = "Unknown Artist"
        album = "Unknown Album"
        duration_seconds = 0.0
        ext = os.path.splitext(filename)[1].lower()

        try:
            audio = mutagen.File(filepath)
            if audio:
                if audio.info:
                    duration_seconds = audio.info.length
                    # Safety: Dacă durata e 0, punem 1 secundă
                    if duration_seconds == 0: duration_seconds = 1.0

                tags = audio.tags
                if tags:
                    if 'title' in tags: title = tags['title'][0]
                    elif 'TIT2' in tags: title = str(tags['TIT2'])
                    
                    if 'artist' in tags: artist = tags['artist'][0]
                    elif 'TPE1' in tags: artist = str(tags['TPE1'])
                    
                    if 'album' in tags: album = tags['album'][0]
                    elif 'TALB' in tags: album = str(tags['TALB'])
        except: pass
        
        return title, artist, album, duration_seconds, ext

    @staticmethod
    def get_folder_artwork(folder_path):
        try:
            levels = PlaylistScanner._collect_folder_levels(
                folder_path,
                max_depth=PlaylistScanner.MAX_ARTWORK_SCAN_DEPTH,
            )

            # Prioritate: interior -> exterior (mic -> mijlociu -> mare)
            for level_dirs in reversed(levels):
                for root in level_dirs:
                    files = PlaylistScanner._safe_sorted_files(root)
                    if not files:
                        continue

                    # 1) Imagini cu nume de cover
                    for file in files:
                        if file.lower().endswith(PlaylistScanner.IMAGE_EXT):
                            name_no_ext = os.path.splitext(file)[0].lower()
                            if name_no_ext in PlaylistScanner.COVER_NAMES:
                                return QPixmap(os.path.join(root, file))

                    # 2) Fallback: orice imagine
                    for file in files:
                        if file.lower().endswith(PlaylistScanner.IMAGE_EXT):
                            return QPixmap(os.path.join(root, file))

                    # 3) Embedded: primul audio din folder
                    for file in files:
                        if file.lower().endswith(PlaylistScanner.AUDIO_EXT):
                            art = PlaylistScanner._extract_embedded_art(os.path.join(root, file))
                            if art:
                                return art
        except: pass
        return None

    @staticmethod
    def _safe_sorted_files(folder_path):
        try:
            return sorted(os.listdir(folder_path))
        except:
            return []

    @staticmethod
    def _collect_folder_levels(folder_path, max_depth=2):
        levels = [[folder_path]]
        current_level = [folder_path]

        for _ in range(max_depth):
            next_level = []
            for current in current_level:
                try:
                    entries = sorted(os.listdir(current))
                except:
                    continue

                for name in entries:
                    if name.startswith('.'):
                        continue
                    child = os.path.join(current, name)
                    if os.path.isdir(child):
                        next_level.append(child)

            if not next_level:
                break

            levels.append(next_level)
            current_level = next_level

        return levels

    @staticmethod
    def extract_art(filepath):
        embedded = PlaylistScanner._extract_embedded_art(filepath)
        if embedded: return embedded

        try:
            source_path = PlaylistScanner.resolve_audio_path(filepath)
            parent_dir = os.path.dirname(source_path)
            for file in os.listdir(parent_dir):
                if file.lower().endswith(PlaylistScanner.IMAGE_EXT):
                    name_no_ext = os.path.splitext(file)[0].lower()
                    if name_no_ext in PlaylistScanner.COVER_NAMES:
                        return QPixmap(os.path.join(parent_dir, file))
        except: pass
        return None

    @staticmethod
    def get_cache_path(filepath, cache_dir):
        """ Returnează calea teoretică a fișierului cache pentru o piesă """
        try:
            source_path = PlaylistScanner.resolve_audio_path(filepath)
            file_hash = hashlib.md5(source_path.encode('utf-8')).hexdigest()
            return os.path.join(cache_dir, f"{file_hash}.jpg")
        except:
            return None

    @staticmethod
    def cache_artwork(filepath, cache_dir, small_cache_dir=None):
        """ 
        Extrage artwork-ul, îl redimensionează la max 1200x1200px și îl salvează în cache.
        Returnează (large_path, small_path).
        """
        large_path = None
        small_path = None
        
        try:
            cue_track = PlaylistScanner.get_cue_track_info(filepath)
            source_path = cue_track['source_path'] if cue_track else filepath
            file_hash = hashlib.md5(source_path.encode('utf-8')).hexdigest()
            large_path = os.path.join(cache_dir, f"{file_hash}.jpg")
            
            if small_cache_dir:
                small_path = os.path.join(small_cache_dir, f"{file_hash}_small.jpg")
            
            # 1. Verificăm dacă există deja ambele
            has_large = os.path.exists(large_path)
            has_small = small_path and os.path.exists(small_path)
            
            if has_large and (not small_cache_dir or has_small):
                return large_path, small_path

            # Extragem datele brute
            art_data = None
            
            # Optimizare: Dacă avem deja imaginea mare, o folosim pe aia ca sursă
            if has_large:
                img = QImage(large_path)
            else:
                # Altfel citim din fișierul audio
                audio = mutagen.File(source_path)
                if audio and audio.tags:
                    if hasattr(audio.tags, 'getall'): # ID3
                        for key in audio.tags.keys():
                            if 'APIC' in key:
                                art_data = audio.tags[key].data
                                break
                    elif hasattr(audio, 'pictures') and audio.pictures: # FLAC
                        art_data = audio.pictures[0].data
                
                if art_data:
                    img = QImage.fromData(art_data)
                else:
                    # Dacă nu avem embedded art pentru fișierul curent, încercăm să găsim
                    # artwork embedded în oricare alt fișier audio din același folder.
                    img = QImage()
                    try:
                        parent_dir = os.path.dirname(source_path)
                        for other in sorted(os.listdir(parent_dir)):
                            other_path = os.path.join(parent_dir, other)
                            if not other.lower().endswith(PlaylistScanner.AUDIO_EXT):
                                continue
                            if other_path == source_path:
                                continue
                            pix = PlaylistScanner._extract_embedded_art(other_path)
                            if pix:
                                img = pix.toImage()
                                break
                    except:
                        img = QImage()
                    if img.isNull():
                        external_image_path = PlaylistScanner._find_external_art_image(os.path.dirname(source_path))
                        if external_image_path:
                            img = QImage(external_image_path)
            
            if not img.isNull():
                # Save Large (dacă nu există)
                if not has_large:
                    if img.width() > 1200 or img.height() > 1200:
                        img_large = img.scaled(1200, 1200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        img_large.save(large_path, "JPG", 90)
                    else:
                        img.save(large_path, "JPG", 90)
                
                # Save Small (52x52)
                if small_cache_dir and not has_small:
                    # Scalăm la 52x52 (IgnoreAspectRatio pentru a umple pătratul, bun pentru blur background)
                    img_small = img.scaled(52, 52, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    img_small.save(small_path, "JPG", 90)
                    
                return large_path, small_path
                
        except: pass
        return None, None

    @staticmethod
    def _extract_embedded_art(filepath):
        filepath = PlaylistScanner.resolve_audio_path(filepath)
        try:
            audio = mutagen.File(filepath)
            art_data = None
            if audio and audio.tags:
                if hasattr(audio.tags, 'getall'): 
                    for key in audio.tags.keys():
                        if 'APIC' in key:
                            art_data = audio.tags[key].data
                            break
                elif hasattr(audio, 'pictures') and audio.pictures:
                    art_data = audio.pictures[0].data
            
            if art_data:
                img = QImage.fromData(art_data)
                if not img.isNull():
                    return QPixmap.fromImage(img)
        except: pass
        return None

    @staticmethod
    def is_cue_virtual_path(filepath):
        return isinstance(filepath, str) and PlaylistScanner.CUE_MARKER in filepath

    @staticmethod
    def make_cue_virtual_path(source_audio_path, cue_path, track_number):
        return f"{source_audio_path}{PlaylistScanner.CUE_MARKER}{cue_path}::{int(track_number):03d}"

    @staticmethod
    def parse_cue_virtual_path(filepath):
        if not PlaylistScanner.is_cue_virtual_path(filepath):
            return None
        try:
            source_path, payload = filepath.split(PlaylistScanner.CUE_MARKER, 1)
            cue_path, track_str = payload.rsplit("::", 1)
            return {
                'source_path': source_path,
                'cue_path': cue_path,
                'track_number': int(track_str)
            }
        except:
            return None

    @staticmethod
    def resolve_audio_path(filepath):
        parsed = PlaylistScanner.parse_cue_virtual_path(filepath)
        if parsed:
            track = PlaylistScanner.get_cue_track_info(filepath)
            if track and track.get('source_path'):
                return track['source_path']
            return parsed['source_path']
        return filepath

    @staticmethod
    def canonicalize_track_path(filepath):
        track = PlaylistScanner.get_cue_track_info(filepath)
        if track and track.get('virtual_path'):
            return track['virtual_path']
        return filepath

    @staticmethod
    def canonicalize_track_list(filepaths):
        normalized = []
        cue_source_paths = set()

        for filepath in filepaths or []:
            canonical = PlaylistScanner.canonicalize_track_path(filepath)
            if not canonical:
                continue
            normalized.append(canonical)
            if PlaylistScanner.is_cue_virtual_path(canonical):
                cue_source_paths.add(PlaylistScanner.resolve_audio_path(canonical))

        filtered = []
        seen = set()
        for filepath in normalized:
            if not PlaylistScanner.is_cue_virtual_path(filepath) and filepath in cue_source_paths:
                continue
            if filepath in seen:
                continue
            seen.add(filepath)
            filtered.append(filepath)
        return filtered

    @staticmethod
    def get_cue_track_info(filepath):
        parsed = PlaylistScanner.parse_cue_virtual_path(filepath)
        if not parsed:
            return None

        tracks = PlaylistScanner._load_cue_tracks(parsed['cue_path'])
        for track in tracks:
            if track['virtual_path'] == filepath:
                return track
        parsed_track_number = parsed.get('track_number')
        if parsed_track_number is not None:
            for track in tracks:
                if track.get('track_number') == parsed_track_number:
                    return track
        return None

    @staticmethod
    def get_playback_target(filepath):
        track = PlaylistScanner.get_cue_track_info(filepath)
        if not track:
            return filepath, 0.0, None
        return track['source_path'], track['start_sec'], track.get('end_sec')

    @staticmethod
    def _safe_read_text_file(filepath):
        encodings = ('utf-8-sig', 'utf-8', 'cp1250', 'cp1252', 'latin-1')
        for enc in encodings:
            try:
                with open(filepath, 'r', encoding=enc, errors='strict') as f:
                    return f.read()
            except:
                continue
        return ""

    @staticmethod
    def _parse_quoted_value(text):
        text = text.strip()
        m = re.match(r'^"(.*)"$', text)
        if m:
            return m.group(1)
        return text

    @staticmethod
    def _cue_time_to_seconds(time_str):
        try:
            mm, ss, ff = [int(x) for x in time_str.strip().split(':')]
            return (mm * 60.0) + ss + (ff / 75.0)
        except:
            return None

    @staticmethod
    def _get_audio_duration(filepath):
        try:
            audio = mutagen.File(filepath)
            if audio and audio.info and getattr(audio.info, 'length', 0):
                return float(audio.info.length)
        except:
            pass
        return 0.0

    @staticmethod
    def _normalize_name_for_match(name):
        base = os.path.splitext(os.path.basename(name))[0].lower()
        normalized = unicodedata.normalize('NFKD', base)
        ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
        compact = re.sub(r'[^a-z0-9]+', '', ascii_only)
        return compact or ascii_only or base

    @staticmethod
    def _resolve_cue_source_path(cue_dir, file_rel):
        source_path = os.path.normpath(os.path.join(cue_dir, file_rel))
        if os.path.exists(source_path):
            return source_path

        alt = os.path.normpath(os.path.join(cue_dir, os.path.basename(file_rel)))
        if os.path.exists(alt):
            return alt

        try:
            audio_candidates = []
            for name in sorted(os.listdir(cue_dir)):
                full_path = os.path.join(cue_dir, name)
                if os.path.isfile(full_path) and name.lower().endswith(PlaylistScanner.AUDIO_EXT):
                    audio_candidates.append(full_path)

            if len(audio_candidates) == 1:
                return audio_candidates[0]

            target_name = PlaylistScanner._normalize_name_for_match(file_rel)
            for candidate in audio_candidates:
                candidate_name = PlaylistScanner._normalize_name_for_match(candidate)
                if candidate_name == target_name:
                    return candidate
        except:
            pass

        return source_path

    @staticmethod
    def _load_cue_tracks(cue_path):
        try:
            mtime = os.path.getmtime(cue_path)
        except:
            return []

        cached = PlaylistScanner._cue_cache.get(cue_path)
        if cached and cached.get('mtime') == mtime:
            return cached.get('tracks', [])

        cue_dir = os.path.dirname(cue_path)
        text = PlaylistScanner._safe_read_text_file(cue_path)
        if not text:
            PlaylistScanner._cue_cache[cue_path] = {'mtime': mtime, 'tracks': []}
            return []

        lines = text.splitlines()

        album_title = None
        album_artist = None
        current_file_rel = None
        current_track = None
        raw_tracks = []

        for raw in lines:
            line = raw.strip()
            if not line:
                continue

            upper = line.upper()

            if upper.startswith('FILE '):
                rest = line[5:].strip()
                if '"' in rest:
                    parts = rest.split('"')
                    if len(parts) >= 2:
                        current_file_rel = parts[1]
                else:
                    current_file_rel = rest.split(' ')[0]
                continue

            if upper.startswith('TRACK '):
                if current_track and current_track.get('index01') is not None:
                    raw_tracks.append(current_track)

                track_no = None
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        track_no = int(parts[1])
                    except:
                        track_no = None

                current_track = {
                    'track_number': track_no,
                    'title': None,
                    'artist': None,
                    'file_rel': current_file_rel,
                    'index01': None,
                }
                continue

            if upper.startswith('INDEX 01') and current_track:
                parts = line.split()
                if len(parts) >= 3:
                    current_track['index01'] = PlaylistScanner._cue_time_to_seconds(parts[2])
                continue

            if upper.startswith('TITLE '):
                value = PlaylistScanner._parse_quoted_value(line[6:])
                if current_track:
                    current_track['title'] = value
                else:
                    album_title = value
                continue

            if upper.startswith('PERFORMER '):
                value = PlaylistScanner._parse_quoted_value(line[10:])
                if current_track:
                    current_track['artist'] = value
                else:
                    album_artist = value
                continue

        if current_track and current_track.get('index01') is not None:
            raw_tracks.append(current_track)

        if not raw_tracks:
            PlaylistScanner._cue_cache[cue_path] = {'mtime': mtime, 'tracks': []}
            return []

        grouped = {}
        for tr in raw_tracks:
            file_rel = tr.get('file_rel')
            if not file_rel:
                continue

            source_path = PlaylistScanner._resolve_cue_source_path(cue_dir, file_rel)

            grouped.setdefault(source_path, []).append(tr)

        resolved_tracks = []
        for source_path, tracks in grouped.items():
            tracks.sort(key=lambda x: x.get('index01') or 0)
            total_length = PlaylistScanner._get_audio_duration(source_path)

            for i, tr in enumerate(tracks):
                start_sec = tr.get('index01') or 0.0
                if i + 1 < len(tracks):
                    end_sec = tracks[i + 1].get('index01') or total_length
                else:
                    end_sec = total_length if total_length > 0 else None

                if end_sec is not None and end_sec < start_sec:
                    end_sec = start_sec

                duration = (end_sec - start_sec) if end_sec is not None else 0.0
                if duration <= 0:
                    duration = 1.0

                track_number = tr.get('track_number') or (i + 1)
                title = tr.get('title') or f"Track {int(track_number):02d}"
                artist = tr.get('artist') or album_artist or "Unknown Artist"
                album = album_title or os.path.splitext(os.path.basename(cue_path))[0]

                virtual_path = PlaylistScanner.make_cue_virtual_path(source_path, cue_path, track_number)

                resolved_tracks.append({
                    'virtual_path': virtual_path,
                    'source_path': source_path,
                    'cue_path': cue_path,
                    'track_number': int(track_number),
                    'title': title,
                    'artist': artist,
                    'album': album,
                    'start_sec': float(start_sec),
                    'end_sec': float(end_sec) if end_sec is not None else None,
                    'duration': float(duration),
                })

        resolved_tracks.sort(key=lambda t: (t['source_path'].lower(), t['start_sec'], t['track_number']))
        PlaylistScanner._cue_cache[cue_path] = {'mtime': mtime, 'tracks': resolved_tracks}
        return resolved_tracks

    @staticmethod
    def _get_cue_tracks_for_folder(folder_path):
        cue_tracks = []
        cue_sources = set()
        try:
            items = sorted(os.listdir(folder_path))
        except:
            return cue_tracks, cue_sources

        for name in items:
            if name.startswith('.'):
                continue
            if not name.lower().endswith(PlaylistScanner.CUE_EXT):
                continue

            cue_path = os.path.join(folder_path, name)
            tracks = PlaylistScanner._load_cue_tracks(cue_path)
            if tracks:
                cue_tracks.extend(tracks)
                cue_sources.update([t['source_path'] for t in tracks])

        cue_tracks.sort(key=lambda t: (t['source_path'].lower(), t['start_sec'], t['track_number']))
        return cue_tracks, cue_sources

    @staticmethod
    def _find_external_art_image(folder_path):
        files = PlaylistScanner._safe_sorted_files(folder_path)
        if not files:
            return None

        for file in files:
            if file.lower().endswith(PlaylistScanner.IMAGE_EXT):
                name_no_ext = os.path.splitext(file)[0].lower()
                if name_no_ext in PlaylistScanner.COVER_NAMES:
                    return os.path.join(folder_path, file)

        for file in files:
            if file.lower().endswith(PlaylistScanner.IMAGE_EXT):
                return os.path.join(folder_path, file)

        return None

    @staticmethod
    def _filter_out_full_sources(file_paths):
        """
        Heuristic: dacă există un fișier audio a cărui durată e aproximativ egală cu suma duratelor celorlalte
        fișiere din același folder (p.ex. un album FLAC și track-urile separate WAV), eliminăm fișierul lung
        din listă pentru a afișa doar piesele sectionate.
        """
        try:
            if not file_paths or len(file_paths) < 2:
                return file_paths

            durations = {}
            total = 0.0
            for p in file_paths:
                try:
                    audio = mutagen.File(p)
                    d = float(audio.info.length) if audio and audio.info and getattr(audio.info, 'length', 0) else 0.0
                except:
                    d = 0.0
                durations[p] = d
                total += d

            # Dacă avem total > 0, căutăm un fișier care domină (aprox egal cu restul)
            if total <= 0:
                return file_paths

            for p, d in durations.items():
                others = total - d
                # Condiție: fișierul e suficient de lung față de rest (80% sau mai mult) și are minim 30s
                if others > 0 and d >= max(30.0, others * 0.8):
                    return [f for f in file_paths if f != p]
        except:
            pass
        return file_paths