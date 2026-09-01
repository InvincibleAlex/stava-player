import os
import time
from .playlist_scanner import PlaylistScanner
from .database import DatabaseManager
from PyQt6.QtGui import QImage
from PyQt6.QtCore import Qt
from audio.audio_engine import AudioEngine # Pentru unpack static
from core.utils import get_cache_root
import mutagen

class PlaylistLogic:
    def __init__(self):
        self.library_root = None
        self.current_path = None
        self.all_songs_cache = []
        self.forward_stack = []
        
        # --- CACHE PENTRU METADATE ---
        self.meta_cache = {}    # {filepath: (title, artist, album, duration, ext)}
        self.albums_cache = {}  # {album_name: {'songs': [], 'art_file': path}}
        self.artists_cache = {} # {artist_name: {'songs': [], 'art_file': path}}
        self.art_paths_cache = {} # {filepath: path_to_cached_jpg}
        self.folder_art_paths_cache = {} # {folder_path: best_art_path or ""}
        self.all_songs_metadata_cache = None
        self.artists_list_cache = None

        # Setup Cache Directory
        self.main_cache_dir = get_cache_root()
        
        self.cache_dir = os.path.join(self.main_cache_dir, "artwork")
        self.cache_small_dir = os.path.join(self.main_cache_dir, "artwork_small") # Folder nou
        self.db_dir = os.path.join(self.main_cache_dir, "databases")

        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.cache_small_dir, exist_ok=True)
        os.makedirs(self.db_dir, exist_ok=True)

        # --- DATABASE ---
        self.db = DatabaseManager(self.db_dir)
        self.migrate_cue_virtual_entries()
        self.sync_cue_artwork_entries()

    def migrate_cue_virtual_entries(self):
        """Normalizează intrările CUE vechi din DB către path-ul virtual canonic curent."""
        rows = self.db.fetch_all(
            """
            SELECT path, title, artist, album, duration, play_count, art_path, art_small_path, lyrics, waveform
            FROM songs
            WHERE path LIKE ?
            """,
            (f"%{PlaylistScanner.CUE_MARKER}%",)
        )

        for row in rows:
            old_path = row['path']
            new_path = PlaylistScanner.canonicalize_track_path(old_path)
            if not new_path or new_path == old_path:
                continue

            existing = self.db.fetch_one(
                """
                SELECT title, artist, album, duration, play_count, art_path, art_small_path, lyrics, waveform
                FROM songs WHERE path = ?
                """,
                (new_path,)
            )

            merged_title = (existing['title'] if existing and existing['title'] else row['title']) or ""
            merged_artist = (existing['artist'] if existing and existing['artist'] else row['artist']) or ""
            merged_album = (existing['album'] if existing and existing['album'] else row['album']) or ""
            merged_duration = (existing['duration'] if existing and existing['duration'] else row['duration']) or 0.0
            merged_play_count = (existing['play_count'] if existing and existing['play_count'] else 0) + (row['play_count'] or 0)
            merged_art = (existing['art_path'] if existing and existing['art_path'] else row['art_path']) or ""
            merged_small_art = (existing['art_small_path'] if existing and existing['art_small_path'] else row['art_small_path']) or ""
            merged_lyrics = (existing['lyrics'] if existing and existing['lyrics'] else row['lyrics']) or ""
            merged_waveform = existing['waveform'] if existing and existing['waveform'] else row['waveform']

            self.db.execute(
                """
                INSERT OR REPLACE INTO songs
                (path, title, artist, album, duration, play_count, art_path, art_small_path, lyrics, waveform)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_path,
                    merged_title,
                    merged_artist,
                    merged_album,
                    merged_duration,
                    merged_play_count,
                    merged_art,
                    merged_small_art,
                    merged_lyrics,
                    merged_waveform,
                )
            )
            self.db.execute("DELETE FROM songs WHERE path = ?", (old_path,))

        if rows:
            self.clear_cache()

    def sync_cue_artwork_entries(self):
        """Asigură că track-urile CUE moștenesc artwork-ul din sursa audio reală."""
        rows = self.db.fetch_all(
            "SELECT path, art_path, art_small_path FROM songs WHERE path LIKE ?",
            (f"%{PlaylistScanner.CUE_MARKER}%",)
        )

        updated = False
        for row in rows:
            cue_path = row['path']
            source_path = PlaylistScanner.resolve_audio_path(cue_path)
            if not source_path:
                continue

            source_large = self.get_cached_art_path(source_path)
            source_small = self.get_cached_small_art_path(source_path)

            if not source_large:
                source_large, source_small = PlaylistScanner.cache_artwork(source_path, self.cache_dir, self.cache_small_dir)

            new_large = source_large or ""
            new_small = source_small or ""
            if row['art_path'] != new_large or row['art_small_path'] != new_small:
                self.db.execute(
                    "UPDATE songs SET art_path = ?, art_small_path = ? WHERE path = ?",
                    (new_large, new_small, cue_path)
                )
                if new_large:
                    self.art_paths_cache[cue_path] = new_large
                updated = True

        if updated:
            self.clear_cache()

    def set_root_folder(self, path):
        self.library_root = path
        self.current_path = path
        self.forward_stack = []
        return os.path.basename(path)

    def rescan_library(self, scan_root=None):
        if not self.library_root:
            return None
        scan_root = scan_root if scan_root and os.path.isdir(scan_root) else self.library_root
        songs = PlaylistScanner.get_all_songs_recursive(scan_root)
        if os.path.normcase(os.path.normpath(scan_root)) == os.path.normcase(os.path.normpath(self.library_root)):
            self.all_songs_cache = songs
        else:
            self.all_songs_cache = []
        return songs

    def ingest_metadata(self, filepath, audio_engine=None):
        """ Citește metadatele și le salvează în Baza de Date """
        meta = PlaylistScanner.get_track_metadata(filepath)
        title, artist, album, duration, ext = meta
        
        # Caching Artwork
        cached_art_path, cached_small_path = PlaylistScanner.cache_artwork(filepath, self.cache_dir, self.cache_small_dir)
        if cached_art_path:
            self.art_paths_cache[filepath] = cached_art_path

        # Generare Waveform (Dacă avem engine-ul disponibil - adică la scanare)
        waveform_blob = None
        if audio_engine:
            # Asta va dura puțin, dar e one-time
            waveform_blob = audio_engine.get_waveform_bytes(filepath)

        # INSERT / UPDATE în DB
        self.db.execute("""
            INSERT OR REPLACE INTO songs (path, title, artist, album, duration, art_path, art_small_path, waveform)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (filepath, title, artist, album, duration, cached_art_path or "", cached_small_path or "", waveform_blob))
        
        return meta

    # --- METODE GRANULARE PENTRU SCANARE ETAPIZATĂ ---
    def scan_metadata(self, filepath):
        """ Etapa 1: Doar metadate (Rapid) """
        meta = PlaylistScanner.get_track_metadata(filepath)
        title, artist, album, duration, ext = meta
        
        # Folosim INSERT OR IGNORE pentru a crea rândul, apoi UPDATE pentru a fi siguri
        # Sau mai simplu: INSERT OR REPLACE dar păstrând NULL la restul dacă e nou
        # Pentru scanare curată (după hard reset), INSERT e suficient.
        self.db.execute("""
            INSERT INTO songs (path, title, artist, album, duration)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                title=excluded.title,
                artist=excluded.artist,
                album=excluded.album,
                duration=excluded.duration
        """, (filepath, title, artist, album, duration))

    def scan_artwork(self, filepath):
        """ Etapa 2: Artwork & Mini Artwork """
        if PlaylistScanner.is_cue_virtual_path(filepath):
            source_path = PlaylistScanner.resolve_audio_path(filepath)

            source_large = self.art_paths_cache.get(source_path)
            source_small = None

            if not source_large or not os.path.exists(source_large):
                source_large, source_small = PlaylistScanner.cache_artwork(source_path, self.cache_dir, self.cache_small_dir)
            else:
                source_small = self.get_cached_small_art_path(source_path)

            if source_large:
                self.art_paths_cache[source_path] = source_large
                self.art_paths_cache[filepath] = source_large

            self.db.execute(
                "UPDATE songs SET art_path=?, art_small_path=? WHERE path=?",
                (source_large or "", source_small or "", filepath)
            )
            return

        cached_art_path, cached_small_path = PlaylistScanner.cache_artwork(filepath, self.cache_dir, self.cache_small_dir)
        if cached_art_path:
            self.art_paths_cache[filepath] = cached_art_path
        self.db.execute("UPDATE songs SET art_path=?, art_small_path=? WHERE path=?", (cached_art_path or "", cached_small_path or "", filepath))

    def scan_waveform(self, filepath, audio_engine):
        """ Etapa 3: Waveform (Lent) """
        if PlaylistScanner.is_cue_virtual_path(filepath):
            return
        waveform_blob = audio_engine.get_waveform_bytes(filepath)
        self.db.execute("UPDATE songs SET waveform=? WHERE path=?", (waveform_blob, filepath))

    def get_metadata(self, filepath):
        """ Returnează metadatele din DB (Rapid) sau scanează (Lent + Save) """
        # 1. Memory Cache (Cel mai rapid)
        if filepath in self.meta_cache:
            cached = self.meta_cache[filepath]
            return (cached[0], cached[1], cached[2], self.format_seconds(cached[3]), cached[4])

        # 2. Verificăm DB
        row = self.db.fetch_one("SELECT title, artist, album, duration, art_path FROM songs WHERE path = ?", (filepath,))
        if row:
            source_path = PlaylistScanner.resolve_audio_path(filepath)
            ext = os.path.splitext(source_path)[1].upper().replace(".", "")
            if row['art_path']:
                self.art_paths_cache[filepath] = row['art_path']
            
            # Salvăm în memory cache (cu durată raw)
            self.meta_cache[filepath] = (row['title'], row['artist'], row['album'], row['duration'] or 0.0, ext)
            dur_str = self.format_seconds(row['duration'])
            return (row['title'], row['artist'], row['album'], dur_str, ext)

        # 3. Fallback: Scanare fizică + Salvare în DB
        meta = self.ingest_metadata(filepath)
        source_path = PlaylistScanner.resolve_audio_path(filepath)
        ext = os.path.splitext(source_path)[1].upper().replace(".", "")
        self.meta_cache[filepath] = (meta[0], meta[1], meta[2], meta[3], ext)
        return (meta[0], meta[1], meta[2], self.format_seconds(meta[3]), meta[4])

    def get_metadata_raw(self, filepath):
        """ Returnează metadatele cu durata ca float (pentru usage intern, fără formatare) """
        if filepath in self.meta_cache:
            return self.meta_cache[filepath]

        # Trigger populare cache prin get_metadata
        self.get_metadata(filepath)
        return self.meta_cache.get(filepath, (os.path.basename(filepath), 'Unknown Artist', 'Unknown Album', 0.0, ''))

    def get_waveform_data(self, filepath):
        """ Returnează lista de peaks din DB (sau None) """
        if PlaylistScanner.is_cue_virtual_path(filepath):
            return None
        row = self.db.fetch_one("SELECT waveform FROM songs WHERE path = ?", (filepath,))
        if row and row['waveform']:
            # Convertim BLOB -> List[float]
            return AudioEngine.unpack_waveform_bytes(row['waveform'])
        return None

    def get_lyrics(self, filepath):
        """ 
        Strategie Hibridă: DB -> Embedded -> None (Urmează Net)
        Returnează textul versurilor sau None.
        """
        # 1. Verificăm Baza de Date (Cel mai rapid)
        row = self.db.fetch_one("SELECT lyrics FROM songs WHERE path = ?", (filepath,))
        if row and row['lyrics']:
            return row['lyrics']

        # 2. Verificăm Embedded Tags (FLAC/MP3)
        lyrics = self._extract_embedded_lyrics(filepath)
        
        if lyrics:
            # Salvăm în DB pentru data viitoare
            self.db.execute("UPDATE songs SET lyrics = ? WHERE path = ?", (lyrics, filepath))
            return lyrics
            
        return None

    def _extract_embedded_lyrics(self, filepath):
        """ Extrage versurile din tag-uri folosind Mutagen """
        try:
            audio = mutagen.File(filepath)
            if not audio: return None
            
            # FLAC / Vorbis (Ogg)
            if 'LYRICS' in audio: return audio['LYRICS'][0]
            if 'UNSYNCEDLYRICS' in audio: return audio['UNSYNCEDLYRICS'][0]
            
            # MP3 (ID3) - USLT frame
            if hasattr(audio, 'tags'):
                for key in audio.tags.keys():
                    if key.startswith('USLT'):
                        return audio.tags[key].text
        except Exception as e:
            print(f"Lyrics extraction error: {e}")
        
        return None

    def get_folder_stats(self, folder_path):
        """ 
        OPTIMIZAT: Încearcă să calculeze durata din DB (Songs table) 
        înainte de a face fallback la scanare fizică.
        """
        # 1. DB Check (Cache direct pe folder)
        row = self.db.fetch_one("SELECT song_count, total_duration FROM folders WHERE path = ?", (folder_path,))
        if row and row['total_duration'] > 0:
            return row['song_count'], row['total_duration']
            
        # 2. SQL Aggregation (Dacă piesele sunt deja scanate în songs)
        # Căutăm toate piesele care încep cu calea folderului
        # Atenție: Asta include și subfoldere, ceea ce e corect pentru stats recursive
        like_path = f"{folder_path}%"
        agg = self.db.fetch_one("SELECT COUNT(*), SUM(duration) FROM songs WHERE path LIKE ?", (like_path,))
        
        db_count = agg[0] if agg else 0
        db_duration = agg[1] if agg and agg[1] else 0
        
        # 3. Physical Scan DOAR dacă DB nu are date (evităm os.walk costisitor)
        if db_count > 0:
            final_count = db_count
        else:
            phy_count, _ = PlaylistScanner.get_folder_stats(folder_path)
            final_count = phy_count
        final_duration = db_duration

        # Salvăm în cache-ul de foldere
        self.db.execute("""
            INSERT OR REPLACE INTO folders (path, song_count, total_duration)
            VALUES (?, ?, ?)
        """, (folder_path, final_count, final_duration))
        
        return final_count, final_duration

    def get_folder_stats_fast(self, folder_path):
        """
        Returneaza statistici doar din cache/DB, fara scanare fizica.
        Folosit la randarea instant; fallback-ul lent se face deferred.
        """
        row = self.db.fetch_one("SELECT song_count, total_duration FROM folders WHERE path = ?", (folder_path,))
        if row and row['song_count'] is not None:
            return row['song_count'] or 0, row['total_duration'] or 0

        like_path = f"{folder_path}%"
        agg = self.db.fetch_one("SELECT COUNT(*), SUM(duration) FROM songs WHERE path LIKE ?", (like_path,))
        db_count = agg[0] if agg else 0
        db_duration = agg[1] if agg and agg[1] else 0
        if db_count > 0:
            return db_count, db_duration

        return None

    def _visible_song_paths(self, paths):
        return set(PlaylistScanner.canonicalize_track_list(paths))

    def get_cached_art_path(self, filepath):
        """ Returnează calea către JPG-ul din cache sau None """
        filepath = PlaylistScanner.canonicalize_track_path(filepath)
        if PlaylistScanner.is_cue_virtual_path(filepath):
            source_path = PlaylistScanner.resolve_audio_path(filepath)
            if source_path and source_path != filepath:
                source_cached = self.get_cached_art_path(source_path)
                if source_cached:
                    self.art_paths_cache[filepath] = source_cached
                    self.db.execute("UPDATE songs SET art_path = ? WHERE path = ?", (source_cached, filepath))
                    return source_cached
        # 1. Verificăm memoria (Rapid)
        if filepath in self.art_paths_cache:
            return self.art_paths_cache[filepath]
        
        # 2. Verificăm DB
        row = self.db.fetch_one("SELECT art_path FROM songs WHERE path = ?", (filepath,))
        if row and row['art_path'] and os.path.exists(row['art_path']):
            self.art_paths_cache[filepath] = row['art_path']
            return row['art_path']

        # 3. Verificăm discul (Legacy / Fallback)
        potential_path = PlaylistScanner.get_cache_path(filepath, self.cache_dir)
        if potential_path and os.path.exists(potential_path):
            self.art_paths_cache[filepath] = potential_path # Actualizăm memoria
            return potential_path
            
        return None
        
    def get_cached_small_art_path(self, filepath):
        """ Returnează calea către imaginea mică (52x52) din cache """
        filepath = PlaylistScanner.canonicalize_track_path(filepath)
        if PlaylistScanner.is_cue_virtual_path(filepath):
            source_path = PlaylistScanner.resolve_audio_path(filepath)
            if source_path and source_path != filepath:
                source_small = self.get_cached_small_art_path(source_path)
                if source_small:
                    self.db.execute("UPDATE songs SET art_small_path = ? WHERE path = ?", (source_small, filepath))
                    return source_small
        row = self.db.fetch_one("SELECT art_small_path FROM songs WHERE path = ?", (filepath,))
        
        # 1. Dacă există în DB și pe disc, o returnăm
        if row and row['art_small_path'] and os.path.exists(row['art_small_path']):
            return row['art_small_path']
            
        # 2. Fallback: Dacă lipsește, o generăm ACUM din imaginea mare și o SALVĂM
        large_path = self.get_cached_art_path(filepath)
        if large_path and os.path.exists(large_path):
            try:
                # Construim calea pentru fișierul mic
                base_name = os.path.splitext(os.path.basename(large_path))[0]
                small_filename = f"{base_name}_small.jpg"
                small_path = os.path.join(self.cache_small_dir, small_filename)

                # Redimensionăm și salvăm fizic
                img = QImage(large_path)
                if not img.isNull():
                    # 52x52px exact cum ai cerut
                    small_img = img.scaled(52, 52, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    if small_img.save(small_path, "JPG", 90):
                        self.db.execute("UPDATE songs SET art_small_path = ? WHERE path = ?", (small_path, filepath))
                        return small_path
            except Exception as e:
                print(f"Error generating small art: {e}")
                
        return None

    def clear_cache(self):
        self.meta_cache.clear()
        self.albums_cache.clear()
        self.artists_cache.clear()
        self.art_paths_cache.clear()
        self.folder_art_paths_cache.clear()
        self.all_songs_metadata_cache = None
        self.artists_list_cache = None

    def invalidate_scan_scope(self, folder_path):
        if not folder_path or not os.path.isdir(folder_path):
            return

        folder_path = os.path.normpath(folder_path)
        child_like = folder_path.rstrip("\\/") + os.sep + "%"
        self.clear_cache()
        self.all_songs_cache = []
        self.db.execute(
            "DELETE FROM songs WHERE path = ? OR path LIKE ?",
            (folder_path, child_like),
        )
        self.db.execute(
            "DELETE FROM folders WHERE path = ? OR path LIKE ?",
            (folder_path, child_like),
        )
        
    def hard_reset_library(self):
        """ Șterge complet cache-ul (DB + Fișiere + Memorie) """
        # 1. Clear Memory
        self.clear_cache()
        self.all_songs_cache = []
        
        # 2. Clear DB
        self.db.execute("DELETE FROM songs")
        self.db.execute("DELETE FROM folders")
        
        # 3. Clear Disk Cache (Artwork)
        if os.path.exists(self.cache_dir):
            for f in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, f)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Error deleting cache file {f}: {e}")
                    
        if os.path.exists(self.cache_small_dir):
            for f in os.listdir(self.cache_small_dir):
                file_path = os.path.join(self.cache_small_dir, f)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except: pass

    def get_albums_grouped(self):
        """ Construiește gruparea albumelor din DB (cu cache în memorie) """
        if self.albums_cache:
            return self.albums_cache

        rows = self.db.fetch_all("SELECT album, path FROM songs WHERE album IS NOT NULL AND album != '' ORDER BY album")
        visible_paths = self._visible_song_paths([row['path'] for row in rows])
        grouped = {}
        for row in rows:
            if row['path'] not in visible_paths:
                continue
            alb = row['album']
            if alb not in grouped:
                grouped[alb] = {'songs': [], 'art_file': row['path']}
            grouped[alb]['songs'].append(row['path'])
        self.albums_cache = grouped
        return grouped

    def get_artists_grouped(self):
        """ Construiește gruparea artiștilor din DB (cu cache în memorie) """
        if self.artists_cache:
            return self.artists_cache

        rows = self.db.fetch_all("SELECT artist, path FROM songs WHERE artist IS NOT NULL AND artist != '' ORDER BY artist")
        visible_paths = self._visible_song_paths([row['path'] for row in rows])
        grouped = {}
        for row in rows:
            if row['path'] not in visible_paths:
                continue
            art = row['artist']
            if art not in grouped:
                grouped[art] = {'songs': [], 'art_file': row['path']}
            grouped[art]['songs'].append(row['path'])
        self.artists_cache = grouped
        return grouped

    def get_all_songs_metadata(self):
        """ Returnează toate piesele direct din DB (Optimizat) """
        if self.all_songs_metadata_cache is not None:
            return self.all_songs_metadata_cache

        # 1. DB Fetch (Rapid)
        query = "SELECT title, artist, duration, path FROM songs ORDER BY title COLLATE NOCASE"
        rows = self.db.fetch_all(query)
        
        if rows:
            visible_paths = self._visible_song_paths([row['path'] for row in rows])
            result = []
            for row in rows:
                if row['path'] not in visible_paths:
                    continue
                source_path = PlaylistScanner.resolve_audio_path(row['path'])
                ext = os.path.splitext(source_path)[1].upper().replace(".", "")
                duration_str = self.format_seconds(row['duration'])
                result.append((row['title'], row['artist'], duration_str, ext, row['path']))
            self.all_songs_metadata_cache = result
            return result

        # 2. Fallback (Dacă DB e gol, folosim metoda veche lentă care și populează DB)
        if not self.all_songs_cache:
            self.rescan_library()
            
        result = []
        for f in self.all_songs_cache:
            title, artist, album, duration, ext = self.get_metadata(f)
            result.append((title, artist, duration, ext, f))
            
        result.sort(key=lambda x: x[0].lower())
        self.all_songs_metadata_cache = result
        return result

    def increment_play_count(self, filepath):
        """ Incrementează contorul de redări pentru o piesă. """
        if not filepath:
            return
        filepath = PlaylistScanner.canonicalize_track_path(filepath)
        self.db.execute(
            """
            UPDATE songs
            SET play_count = COALESCE(play_count, 0) + 1,
                last_played = ?
            WHERE path = ?
            """,
            (time.time(), filepath)
        )

    def increment_skip_count(self, filepath):
        if not filepath:
            return
        filepath = PlaylistScanner.canonicalize_track_path(filepath)
        self.db.execute("UPDATE songs SET skip_count = COALESCE(skip_count, 0) + 1 WHERE path = ?", (filepath,))

    def add_listened_seconds(self, filepath, listened_seconds):
        if not filepath:
            return
        try:
            listened_seconds = float(listened_seconds)
        except Exception:
            return
        if listened_seconds <= 0:
            return
        filepath = PlaylistScanner.canonicalize_track_path(filepath)
        self.db.execute(
            "UPDATE songs SET listened_seconds = COALESCE(listened_seconds, 0) + ? WHERE path = ?",
            (listened_seconds, filepath)
        )

    def get_statistics_summary(self):
        totals = self.db.fetch_one(
            """
            SELECT
                COUNT(*) AS total_tracks,
                SUM(CASE WHEN COALESCE(play_count, 0) > 0 THEN 1 ELSE 0 END) AS unique_played_tracks,
                COALESCE(SUM(play_count), 0) AS total_plays,
                COALESCE(SUM(skip_count), 0) AS total_skips,
                COALESCE(SUM(listened_seconds), 0) AS total_listened_seconds,
                COALESCE(
                    AVG(
                        CASE
                            WHEN duration > 0 AND (COALESCE(play_count, 0) > 0 OR COALESCE(listened_seconds, 0) > 0)
                            THEN MIN(1.0, COALESCE(listened_seconds, 0) / duration)
                            ELSE NULL
                        END
                    ),
                    0
                ) AS avg_completion_rate
            FROM songs
            """
        )

        top_played = self.db.fetch_one(
            """
            SELECT title, artist, album, path, play_count
            FROM songs
            WHERE COALESCE(play_count, 0) > 0
            ORDER BY play_count DESC, COALESCE(listened_seconds, 0) DESC, title COLLATE NOCASE
            LIMIT 1
            """
        )
        top_skipped = self.db.fetch_one(
            """
            SELECT title, artist, album, path, skip_count
            FROM songs
            WHERE COALESCE(skip_count, 0) > 0
            ORDER BY skip_count DESC, title COLLATE NOCASE
            LIMIT 1
            """
        )
        top_artist = self.db.fetch_one(
            """
            SELECT artist, COALESCE(SUM(play_count), 0) AS total_plays, COALESCE(SUM(listened_seconds), 0) AS total_listened_seconds
            FROM songs
            WHERE artist IS NOT NULL AND artist != ''
            GROUP BY artist
            HAVING COALESCE(SUM(play_count), 0) > 0 OR COALESCE(SUM(listened_seconds), 0) > 0
            ORDER BY total_plays DESC, total_listened_seconds DESC, artist COLLATE NOCASE
            LIMIT 1
            """
        )
        top_album = self.db.fetch_one(
            """
            SELECT album, artist, COALESCE(SUM(play_count), 0) AS total_plays, COALESCE(SUM(listened_seconds), 0) AS total_listened_seconds
            FROM songs
            WHERE album IS NOT NULL AND album != ''
            GROUP BY album, artist
            HAVING COALESCE(SUM(play_count), 0) > 0 OR COALESCE(SUM(listened_seconds), 0) > 0
            ORDER BY total_plays DESC, total_listened_seconds DESC, album COLLATE NOCASE
            LIMIT 1
            """
        )
        last_played = self.db.fetch_one(
            """
            SELECT title, artist, album, path, last_played
            FROM songs
            WHERE COALESCE(last_played, 0) > 0
            ORDER BY last_played DESC
            LIMIT 1
            """
        )

        return {
            "total_tracks": int((totals["total_tracks"] if totals else 0) or 0),
            "unique_played_tracks": int((totals["unique_played_tracks"] if totals else 0) or 0),
            "total_plays": int((totals["total_plays"] if totals else 0) or 0),
            "total_skips": int((totals["total_skips"] if totals else 0) or 0),
            "total_listened_seconds": float((totals["total_listened_seconds"] if totals else 0.0) or 0.0),
            "avg_completion_rate": float((totals["avg_completion_rate"] if totals else 0.0) or 0.0),
            "top_played": dict(top_played) if top_played else None,
            "top_skipped": dict(top_skipped) if top_skipped else None,
            "top_artist": dict(top_artist) if top_artist else None,
            "top_album": dict(top_album) if top_album else None,
            "last_played": dict(last_played) if last_played else None,
        }

    def get_most_played_songs_metadata(self, limit=500):
        """ Returnează piesele ordonate descrescător după numărul de redări. """
        query = """
            SELECT title, artist, duration, path, play_count
            FROM songs
            WHERE COALESCE(play_count, 0) > 0
            ORDER BY play_count DESC, title COLLATE NOCASE
            LIMIT ?
        """
        rows = self.db.fetch_all(query, (int(limit),))

        result = []
        for row in rows:
            ext = os.path.splitext(row['path'])[1].upper().replace(".", "")
            artist_display = row['artist'] if row['artist'] else "Unknown Artist"
            artist_display = f"{artist_display} • {int(row['play_count'])} plays"
            duration_str = self.format_seconds(row['duration'])
            result.append((row['title'], artist_display, duration_str, ext, row['path']))
        return result

    def get_artists_list(self):
        """ Returnează lista de artiști cu count și artwork (GROUP BY SQL) """
        if self.artists_list_cache is not None:
            return self.artists_list_cache

        query = """
            SELECT artist, COUNT(path) as cnt, MIN(path) as art_file 
            FROM songs 
            WHERE artist IS NOT NULL AND artist != '' 
            GROUP BY artist 
            ORDER BY artist COLLATE NOCASE
        """
        rows = self.db.fetch_all(query)
        visible_paths = self._visible_song_paths([row['art_file'] for row in rows if row['art_file']])
        self.artists_list_cache = [row for row in rows if not row['art_file'] or row['art_file'] in visible_paths]
        return self.artists_list_cache

    def get_songs_by_artist(self, artist_name):
        """ Returnează piesele unui artist direct din DB """
        query = "SELECT title, artist, album, duration, path FROM songs WHERE artist = ? ORDER BY title COLLATE NOCASE"
        rows = self.db.fetch_all(query, (artist_name,))
        visible_paths = self._visible_song_paths([row['path'] for row in rows])
        result = []
        for row in rows:
            if row['path'] not in visible_paths:
                continue
            ext = os.path.splitext(row['path'])[1].upper().replace(".", "")
            # Format compatibil cu get_metadata: (title, artist, album, duration, ext, path)
            result.append((row['title'], row['artist'], row['album'], row['duration'], ext, row['path']))
        return result

    def get_parent_directory(self):
        if not self.current_path or self.current_path == self.library_root:
            return None
        
        parent = os.path.dirname(self.current_path)
        if parent.startswith(self.library_root):
            self.forward_stack.append(self.current_path)
            self.current_path = parent
            return parent
        return None

    def get_forward_directory(self):
        if self.forward_stack:
            next_path = self.forward_stack.pop()
            if os.path.isdir(next_path):
                self.current_path = next_path
                return next_path
        return None

    def navigate_to(self, path):
        if os.path.isdir(path):
            self.forward_stack = [] 
            self.current_path = path
            return True
        return False

    def get_current_folder_content(self):
        if not self.current_path: return [], []
        return PlaylistScanner.get_folder_content(self.current_path)

    def get_relative_path(self):
        if not self.current_path or not self.library_root: return ""
        return os.path.relpath(self.current_path, os.path.dirname(self.library_root))

    def search_items(self, text):
        if not text: return [], [], []
        
        text_like = f"%{text}%"
        
        # 1. Căutare Piese (Songs) - SQL LIKE
        # Căutăm în titlu, artist, album și path
        query_songs = """
            SELECT path FROM songs 
            WHERE title LIKE ? OR artist LIKE ? OR album LIKE ? OR path LIKE ?
            LIMIT 200
        """
        rows_songs = self.db.fetch_all(query_songs, (text_like, text_like, text_like, text_like))
        matched_songs = [row['path'] for row in rows_songs]
        
        matched_albums = set()
        matched_folders = set()

        # 2. Căutare Albume (Metadata Match)
        # Găsim piesele care au albumul matching și adăugăm folderul lor la albume
        query_albums_meta = "SELECT path FROM songs WHERE album LIKE ? LIMIT 50"
        rows_albums = self.db.fetch_all(query_albums_meta, (text_like,))
        for row in rows_albums:
            folder = os.path.dirname(row['path'])
            matched_albums.add(folder)

        # 3. Căutare Foldere (Path Match)
        query_folders = "SELECT path FROM folders WHERE path LIKE ? LIMIT 50"
        rows_folders = self.db.fetch_all(query_folders, (text_like,))
        
        for row in rows_folders:
            f_path = row['path']
            f_name = os.path.basename(f_path)
            # Dacă numele folderului conține textul -> Album/Folder Principal
            if text.lower() in f_name.lower():
                matched_albums.add(f_path)
            else:
                matched_folders.add(f_path)
                
        return matched_songs, list(matched_albums), list(matched_folders)

    @staticmethod
    def format_seconds(total_seconds):
        s = int(total_seconds)
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        if h > 0: 
            return f"{h}:{m:02d}:{sec:02d}" # Format h:mm:ss (ex: 1:05:20)
        return f"{m}:{sec:02d}" # Format m:ss (ex: 4:30, fără zero în față la minute)
