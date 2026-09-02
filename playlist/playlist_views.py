import os
from .playlist_scanner import PlaylistScanner
from .playlist_helpers import PlaylistHelpers
from .playlist_widgets import (ROLE_ITEM_TYPE, ROLE_SUBTITLE, ROLE_INFO, ROLE_ART_PATH,
                               ROLE_IS_CURRENT, ROLE_ART_SOURCE_PATH)
from PyQt6.QtWidgets import QMenu, QGraphicsOpacityEffect, QListWidgetItem, QApplication
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize, QTimer, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QPixmap, QImageReader, QImage


class _HeaderArtSignals(QObject):
    loaded = pyqtSignal(int, str, QImage, bool)


class _HeaderArtLoadJob(QRunnable):
    def __init__(self, request_id, art_path, update_background):
        super().__init__()
        self.request_id = request_id
        self.art_path = art_path
        self.update_background = update_background
        self.signals = _HeaderArtSignals()

    def run(self):
        image = QImage(self.art_path) if self.art_path and os.path.exists(self.art_path) else QImage()
        self.signals.loaded.emit(self.request_id, self.art_path or "", image, self.update_background)

class _FolderScanSignals(QObject):
    finished = pyqtSignal(list)


class _FolderScanJob(QRunnable):
    """ Scaneaza recursiv un folder (os.walk + citire CUE/mutagen) pe un
    thread separat, ca "Play folder"/"Queue folder" sa nu inghete UI-ul
    pentru foldere mari. """
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = _FolderScanSignals()

    def run(self):
        files = PlaylistScanner.get_all_songs_recursive(self.path)
        self.signals.finished.emit(files)


class PlaylistViewManager:
    def __init__(self, tab):
        """ 
        Primește referința către PlaylistTab pentru a avea acces la UI și Logică.
        """
        self.tab = tab
        self.ui = tab.ui
        self.logic = tab.logic
        self.file_list = tab.file_list
        
        # 🔥 Activăm meniul de context
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.on_context_menu)

        # Animații
        self.anim_out = None
        self.anim_in = None
        self._stats_generation = 0
        self._populate_generation = 0
        self._header_art_request = 0
        self._header_background_delays = {}
        self._defer_background_updates = False
        self._deferred_background_update = object()
        self._no_deferred_background_update = self._deferred_background_update
        self._header_art_pool = QThreadPool()
        self._header_art_pool.setMaxThreadCount(2)

        # Pool separat pentru scanarea recursiva de foldere (Play/Queue folder),
        # ca sa nu concureze cu incarcarea artwork-ului din header.
        self._folder_scan_pool = QThreadPool()
        self._folder_scan_pool.setMaxThreadCount(1)

        # Debounce pentru căutare: evită un LIKE '%...%' full-scan la fiecare tastă apăsată
        self._search_debounce_timer = QTimer()
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(200)
        self._search_debounce_timer.timeout.connect(self._execute_pending_search)
        self._pending_search_text = ""

    def _animate_list_change(self, update_func, total_duration=250):
        """ Execută Fade Out -> Callback -> Fade In pe listă """
        # Oprim animațiile anterioare dacă rulează
        if self.anim_out and self.anim_out.state() == QPropertyAnimation.State.Running:
            self.anim_out.stop()
        if self.anim_in and self.anim_in.state() == QPropertyAnimation.State.Running:
            self.anim_in.stop()

        effect = self.file_list.graphicsEffect()
        # Optimizare: Reutilizăm efectul existent dacă este de tipul corect
        if not effect or not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.file_list)
            self.file_list.setGraphicsEffect(effect)
        
        effect.setOpacity(1.0) # Reset

        # Împărțim timpul egal: 50% Fade Out, 50% Fade In
        half_time = int(total_duration / 2)

        self.anim_out = QPropertyAnimation(effect, b"opacity")
        self.anim_out.setDuration(half_time)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        def on_fade_out_finished():
            update_func() # Actualizăm conținutul cât timp e invizibil
            self.anim_in = QPropertyAnimation(effect, b"opacity")
            self.anim_in.setDuration(half_time)
            self.anim_in.setStartValue(0.0)
            self.anim_in.setEndValue(1.0)
            self.anim_in.setEasingCurve(QEasingCurve.Type.InQuad)
            self.anim_in.start()
            
        self.anim_out.finished.connect(on_fade_out_finished)
        self.anim_out.start()

    def _art_pixel_area(self, path):
        if not path or not os.path.exists(path):
            return 0
        try:
            reader = QImageReader(path)
            size = reader.size()
            if size.isValid():
                return max(0, size.width()) * max(0, size.height())
        except Exception:
            pass
        return 0

    def _best_candidate_path(self, candidates):
        best_path = None
        best_score = None
        seen = set()

        for path, kind_bonus, depth_bonus in candidates:
            if not path or path in seen or not os.path.exists(path):
                continue
            seen.add(path)
            area = self._art_pixel_area(path)
            if area <= 0:
                continue
            score = (area, kind_bonus, depth_bonus)
            if best_score is None or score > best_score:
                best_score = score
                best_path = path

        return best_path

    def _folder_info_text(self, folder_path):
        stats = self.logic.get_folder_stats_fast(folder_path)
        if not stats:
            return "... | ..."
        count, total_sec = stats
        return f"{count} | {self.logic.format_seconds(total_sec)}"

    def _cancel_folder_stats_hydration(self):
        self._stats_generation += 1

    def _next_population_generation(self):
        self._populate_generation += 1
        return self._populate_generation

    def _populate_rows_chunked(self, rows, make_item, first_chunk=90, chunk_size=260):
        """
        Adds rows in small UI-friendly chunks. The first chunk appears immediately;
        the rest is scheduled through the event loop so large libraries do not freeze clicks.
        """
        generation = self._next_population_generation()
        total = len(rows)
        index = 0

        self.tab.list_virtualizer.set_enabled(False)
        self.tab.list_virtualizer.bump_generation()
        self._cancel_folder_stats_hydration()
        self.file_list.clear()

        def add_until(limit):
            nonlocal index
            self.file_list.setUpdatesEnabled(False)
            try:
                end = min(total, index + limit)
                while index < end and generation == self._populate_generation:
                    item = make_item(rows[index])
                    if item:
                        self.file_list.addItem(item)
                    index += 1
            finally:
                self.file_list.setUpdatesEnabled(True)

        add_until(first_chunk)
        self.tab.list_virtualizer.set_enabled(True)

        def continue_later():
            if generation != self._populate_generation:
                return
            if index >= total:
                if self.tab.list_virtualizer._enabled:
                    self.tab.list_virtualizer.load_visible()
                return
            add_until(chunk_size)
            QTimer.singleShot(0, continue_later)

        if index < total:
            QTimer.singleShot(0, continue_later)

    def _scroll_to_row_when_available(self, row, attempts=20):
        if row < self.file_list.count():
            item = self.file_list.item(row)
            if item:
                self.file_list.scrollToItem(item, self.file_list.ScrollHint.PositionAtCenter)
                QApplication.processEvents()
                return
        if attempts > 0:
            QTimer.singleShot(16, lambda: self._scroll_to_row_when_available(row, attempts - 1))

    def _emit_background_update(self, pixmap, delay_ms=0):
        if self._defer_background_updates:
            self._deferred_background_update = pixmap
            return

        if delay_ms and delay_ms > 0:
            QTimer.singleShot(int(delay_ms), lambda pix=pixmap: self.tab.background_update_requested.emit(pix))
        else:
            self.tab.background_update_requested.emit(pixmap)

    def defer_background_updates(self):
        self._defer_background_updates = True
        self._deferred_background_update = self._no_deferred_background_update

    def flush_deferred_background_update(self):
        pending = self._deferred_background_update
        self._defer_background_updates = False
        self._deferred_background_update = self._no_deferred_background_update
        if pending is not self._no_deferred_background_update:
            self._emit_background_update(pending)

    def cancel_deferred_background_update(self):
        self._defer_background_updates = False
        self._deferred_background_update = self._no_deferred_background_update

    def settle_playlist_layout(self):
        header = getattr(self.ui, 'header', None)
        if header and hasattr(header, 'update_geometry_state'):
            header.update_geometry_state()
            header.updateGeometry()
            parent = header.parentWidget()
            if parent:
                parent.updateGeometry()

        page2_header = getattr(self.tab, 'page2_header', None)
        if page2_header:
            page2_header.updateGeometry()

        page_browser = getattr(self.tab, 'page_browser', None)
        if page_browser:
            page_browser.updateGeometry()
            layout = page_browser.layout()
            if layout:
                layout.invalidate()
                layout.activate()

        tab_layout = self.tab.layout()
        if tab_layout:
            tab_layout.invalidate()
            tab_layout.activate()

    def _load_header_art_async(self, art_path, fallback_pixmap=None, update_background=True, background_delay_ms=0):
        self._header_art_request += 1
        request_id = self._header_art_request
        self._header_background_delays[request_id] = max(0, int(background_delay_ms or 0))

        if fallback_pixmap and not fallback_pixmap.isNull():
            self.ui.header.set_image(fallback_pixmap)
            self.ui.header.set_compact(False)
            if update_background:
                self._emit_background_update(fallback_pixmap, background_delay_ms)
        elif not art_path:
            self.ui.header.set_image(None)
            self.ui.header.set_compact(False)
            if update_background:
                self._emit_background_update(None, background_delay_ms)
            return

        if not art_path or not os.path.exists(art_path):
            return

        job = _HeaderArtLoadJob(request_id, art_path, update_background)
        job.signals.loaded.connect(self._on_header_art_loaded)
        self._header_art_pool.start(job)

    def _cancel_header_art_async(self):
        self._header_art_request += 1
        self._header_background_delays.clear()

    def _on_header_art_loaded(self, request_id, art_path, image, update_background):
        if request_id != self._header_art_request or image.isNull():
            return
        delay_ms = self._header_background_delays.pop(request_id, 0)
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        self.ui.header.set_image(pixmap, source_path=art_path)
        self.ui.header.set_compact(False)
        if update_background:
            self._emit_background_update(pixmap, delay_ms)

    def _hydrate_folder_stats_later(self):
        self._stats_generation += 1
        generation = self._stats_generation
        rows = []
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            if item and item.data(ROLE_ITEM_TYPE) == "dir" and item.data(ROLE_SUBTITLE) == "... | ...":
                rows.append(row)

        def process_next():
            if generation != self._stats_generation or not rows:
                return
            row = rows.pop(0)
            if row < self.file_list.count():
                item = self.file_list.item(row)
                if item and item.data(ROLE_ITEM_TYPE) == "dir":
                    path = item.data(Qt.ItemDataRole.UserRole)
                    count, total_sec = self.logic.get_folder_stats(path)
                    item.setData(ROLE_SUBTITLE, f"{count} | {self.logic.format_seconds(total_sec)}")
            if rows and generation == self._stats_generation:
                QTimer.singleShot(8, process_next)

        if rows:
            QTimer.singleShot(0, process_next)

    def _find_dir_art(self, path):
        """Search folder hierarchy candidates and prefer the sharpest usable artwork."""
        cached = self.logic.folder_art_paths_cache.get(path)
        if cached is not None:
            return cached or None

        try:
            levels = PlaylistScanner._collect_folder_levels(
                path,
                max_depth=PlaylistScanner.MAX_ARTWORK_SCAN_DEPTH,
            )
            candidates = []

            for depth, level_dirs in enumerate(levels):
                depth_bonus = -depth
                for root in level_dirs:
                    files = PlaylistScanner._safe_sorted_files(root)
                    if not files:
                        continue

                    named_image = None
                    fallback_image = None
                    audio_files = []

                    for fname in files:
                        lower = fname.lower()
                        full_path = os.path.join(root, fname)
                        if lower.endswith(PlaylistScanner.IMAGE_EXT):
                            if fallback_image is None:
                                fallback_image = full_path
                            name_no_ext = os.path.splitext(lower)[0]
                            if named_image is None and name_no_ext in PlaylistScanner.COVER_NAMES:
                                named_image = full_path
                        elif lower.endswith(PlaylistScanner.AUDIO_EXT):
                            audio_files.append(full_path)

                    if named_image:
                        candidates.append((named_image, 3, depth_bonus))
                    if fallback_image and fallback_image != named_image:
                        candidates.append((fallback_image, 1, depth_bonus))

                    for audio_path in audio_files:
                        cache_path = self.logic.get_cached_art_path(audio_path)
                        if cache_path and os.path.exists(cache_path):
                            candidates.append((cache_path, 2, depth_bonus))
                            break

            best_path = self._best_candidate_path(candidates)
            if best_path:
                self.logic.folder_art_paths_cache[path] = best_path
                return best_path
        except OSError:
            pass

        self.logic.folder_art_paths_cache[path] = ""
        return None

    def _get_art_cache_path(self, path, type_):
        """Return the on-disk artwork cache path (if any) without loading the image."""
        if not path:
            return None

        if type_ == "album_group":
            if os.path.exists(path):
                return self._get_art_cache_path(path, "file")
            data = self.logic.get_albums_grouped().get(path) if path else None
            art_file = data.get('art_file') if data else None
            return self._get_art_cache_path(art_file, "file") if art_file else None

        if type_ == "artist_group":
            if os.path.exists(path):
                return self._get_art_cache_path(path, "file")
            songs = self.logic.get_songs_by_artist(path) if path else []
            art_file = songs[0][-1] if songs else None
            return self._get_art_cache_path(art_file, "file") if art_file else None

        if type_ == "dir":
            result = self._find_dir_art(path)
            if result:
                return result
            # Fallback: check first sub-folder (albums-of-albums)
            try:
                for fname in sorted(os.listdir(path)):
                    sub = os.path.join(path, fname)
                    if os.path.isdir(sub):
                        result = self._find_dir_art(sub)
                        if result:
                            return result
            except OSError:
                pass
            return None
        # For files — use cached/extracted artwork from DB or cache dir
        cache_path = self.logic.get_cached_art_path(path)
        if cache_path and os.path.exists(cache_path):
            return cache_path
        return None

    def _load_best_dir_header_art(self, path, fallback_pixmap=None):
        art_path = self._get_art_cache_path(path, "dir")
        if art_path and os.path.exists(art_path):
            pixmap = QPixmap(art_path)
            if not pixmap.isNull():
                return pixmap, art_path

        pixmap = PlaylistScanner.get_folder_artwork(path)
        if pixmap and not pixmap.isNull():
            return pixmap, None

        return fallback_pixmap, None

    def _load_best_file_header_art(self, path, fallback_pixmap=None):
        art_path = self.logic.get_cached_art_path(path)
        if art_path and os.path.exists(art_path):
            pixmap = QPixmap(art_path)
            if not pixmap.isNull():
                return pixmap, art_path

        pixmap = PlaylistScanner.extract_art(path)
        if pixmap and not pixmap.isNull():
            return pixmap, None

        return fallback_pixmap, None

    def load_directory_view(self, path, header_pixmap=None, target_file=None, animate=True, duration=250, background_delay_ms=0):
        # Disable virtualizer during population, re-enable after
        self.tab.list_virtualizer.set_enabled(False)
        self.tab.list_virtualizer.bump_generation()
        self._cancel_folder_stats_hydration()
        self._next_population_generation()

        # 1. Actualizăm Header-ul (Instant, pentru feedback vizual rapid)
        rel_path = self.logic.get_relative_path()
        is_root = (path == self.logic.library_root)
        
        if is_root:
            # --- PAGINA 2: FOLDERS HIERARCHY ROOT ---
            self._cancel_header_art_async()
            self.ui.header.show()
            self.ui.header.set_compact(True)
            self.ui.header.set_image(None)
            self.tab.nav_container.hide()
            self.ui.update_page2_header("Folders Hierarchy", "more_folders-solid-full.svg", "#7986CB", "📂")
            self.tab.page2_header.show()
            self._emit_background_update(None, background_delay_ms)
            QTimer.singleShot(0, self.settle_playlist_layout)
        else:
            self.ui.header.show()
            self.tab.nav_container.show()
            self.tab.btn_back.show()
            self.tab.btn_play_folder.show()
            self.tab.btn_shuffle_folder.show()
            self.tab.page2_header.hide()
            
            if rel_path == "." or not rel_path: rel_path = os.path.basename(path)
            self.tab.lbl_path.setText(rel_path)

            folder_art_path = self._get_art_cache_path(path, "dir")
            self._load_header_art_async(folder_art_path, fallback_pixmap=header_pixmap, background_delay_ms=background_delay_ms)
        
        # 2. Definim funcția de populare a listei
        def populate_content():
            self.file_list.clear()
            row_h = int(84 * self.tab.global_zoom)
            
            folders, files = self.logic.get_current_folder_content()

            for f in folders:
                info_text = self._folder_info_text(f)
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, os.path.basename(f))
                item.setData(Qt.ItemDataRole.UserRole, f)
                item.setData(ROLE_ITEM_TYPE, "dir")
                item.setData(ROLE_SUBTITLE, info_text)
                item.setSizeHint(QSize(100, row_h))
                self.file_list.addItem(item)

            for f in files:
                title, artist, album, duration, ext = self.logic.get_metadata(f)
                info_tech = f"{duration} | {ext}"
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, title)
                item.setData(Qt.ItemDataRole.UserRole, f)
                item.setData(ROLE_ITEM_TYPE, "file")
                item.setData(ROLE_SUBTITLE, artist)
                item.setData(ROLE_INFO, info_tech)
                item.setSizeHint(QSize(100, row_h))
                self.file_list.addItem(item)

            if target_file:
                for i in range(self.file_list.count()):
                    item = self.file_list.item(i)
                    if item and item.data(Qt.ItemDataRole.UserRole) == target_file:
                        self.file_list.scrollToItem(item, self.file_list.ScrollHint.PositionAtCenter)
                        QApplication.processEvents()
                        break

            # Activate virtualizer to load artwork for visible rows
            self.tab.list_virtualizer.set_enabled(True)
            self._hydrate_folder_stats_later()

        # 3. Executăm popularea (cu sau fără animație)
        if animate:
            self._animate_list_change(populate_content, total_duration=duration)
        else:
            populate_content()

    def open_all_songs_view(self):
        self.tab.view_mode = "all_songs"
        self._cancel_header_art_async()
        self.ui.header.show()
        self.ui.header.set_compact(True) 
        self.ui.header.set_image(None)
        self.tab.nav_container.hide()
        
        self.ui.update_page2_header("All Songs", "music-solid-full.svg", "#64B5F6", "🎵")
        self.tab.page2_header.show()
        
        if not self.logic.library_root:
            self.tab.lbl_path.setText("Please select a folder from the menu first!")
            return

        self.tab.stack.setCurrentIndex(1)
        self.tab.btn_back.show()
        self.tab.btn_play_folder.show()
        self.tab.btn_shuffle_folder.show()

        songs_data = self.logic.get_all_songs_metadata()
        row_h = int(84 * self.tab.global_zoom)
        
        def make_song_item(row):
            title, artist, duration, ext, f = row
            info_tech = f"{duration} | {ext}"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, title)
            item.setData(Qt.ItemDataRole.UserRole, f)
            item.setData(ROLE_ITEM_TYPE, "file")
            item.setData(ROLE_SUBTITLE, artist)
            item.setData(ROLE_INFO, info_tech)
            item.setSizeHint(QSize(100, row_h))
            return item

        self._populate_rows_chunked(songs_data, make_song_item)

    def open_albums_view(self, focus_album=None):
        self.tab.view_mode = "albums_root"
        self._cancel_header_art_async()
        self.ui.header.show()
        self.ui.header.set_compact(True)
        self.ui.header.set_image(None)
        self.tab.nav_container.hide()
        
        self.ui.update_page2_header("Albums", "disc-solid-full.svg", "#4DB6AC", "💿")
        self.tab.page2_header.show()
        
        if not self.logic.library_root:
            self.tab.lbl_path.setText("Please select a folder from the menu first!")
            return

        self.tab.stack.setCurrentIndex(1)
        self.tab.btn_back.show()
        self.tab.btn_play_folder.show()
        self.tab.btn_shuffle_folder.show()

        albums_data = self.logic.get_albums_grouped()
        sorted_albums = sorted(albums_data.keys())
        row_h = int(84 * self.tab.global_zoom)

        def make_album_item(album_name):
            data = albums_data[album_name]
            count = len(data['songs'])
            art_file = data['art_file']
            info_text = f"{count} songs"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, album_name)
            item.setData(Qt.ItemDataRole.UserRole, album_name)
            item.setData(ROLE_ITEM_TYPE, "album_group")
            item.setData(ROLE_SUBTITLE, info_text)
            if art_file:
                item.setData(ROLE_ART_SOURCE_PATH, art_file)
            item.setSizeHint(QSize(100, row_h))
            return item

        self._populate_rows_chunked(sorted_albums, make_album_item)

        if focus_album and focus_album in sorted_albums:
            QTimer.singleShot(0, lambda: self._scroll_to_row_when_available(sorted_albums.index(focus_album)))

    def load_album_content(self, album_name, header_pixmap=None, animate=True):
        self.tab.view_mode = "album_content"
        self.tab.page2_header.hide()
        self.ui.header.show()
        self.tab.nav_container.show()
        self.tab.btn_play_folder.show()
        self.tab.btn_shuffle_folder.show()

        self.tab.list_virtualizer.set_enabled(False)
        self.tab.list_virtualizer.bump_generation()
        self._cancel_folder_stats_hydration()
        self._next_population_generation()
        
        self.tab.lbl_path.setText(album_name)
        
        albums_data = self.logic.get_albums_grouped()
        if album_name in albums_data:
            songs = albums_data[album_name]['songs']
            if songs:
                header_art_path = self.logic.get_cached_art_path(songs[0])
                self._load_header_art_async(header_art_path, fallback_pixmap=header_pixmap)
            
            def populate_album():
                self.tab.current_album_songs = songs
                row_h = int(84 * self.tab.global_zoom)
                
                def make_album_song_item(f):
                    title, artist, album, duration, ext = self.logic.get_metadata(f)
                    info_tech = f"{duration} | {ext}"
                    item = QListWidgetItem()
                    item.setData(Qt.ItemDataRole.DisplayRole, title)
                    item.setData(Qt.ItemDataRole.UserRole, f)
                    item.setData(ROLE_ITEM_TYPE, "file")
                    item.setData(ROLE_SUBTITLE, artist)
                    item.setData(ROLE_INFO, info_tech)
                    item.setSizeHint(QSize(100, row_h))
                    return item

                self._populate_rows_chunked(songs, make_album_song_item)

            if animate:
                self._animate_list_change(populate_album)
            else:
                populate_album()

    def open_artists_view(self, focus_artist=None):
        self.tab.view_mode = "artists_root"
        self._cancel_header_art_async()
        self.ui.header.show()
        self.ui.header.set_compact(True)
        self.ui.header.set_image(None)
        self.tab.nav_container.hide()
        
        self.ui.update_page2_header("Artists", "microphone-solid-full.svg", "#FFB74D", "🎤")
        self.tab.page2_header.show()
        
        if not self.logic.library_root:
            self.tab.lbl_path.setText("Please select a folder from the menu first!")
            return

        self.tab.stack.setCurrentIndex(1)
        self.tab.btn_back.show()

        # 🔥 OPTIMIZARE: Folosim GROUP BY din SQL
        artists_rows = self.logic.get_artists_list()
        row_h = int(84 * self.tab.global_zoom)

        def make_artist_item(row):
            artist_name = row['artist']
            count = row['cnt']
            art_file = row['art_file']
            info_text = f"{count} songs"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, artist_name)
            item.setData(Qt.ItemDataRole.UserRole, artist_name)
            item.setData(ROLE_ITEM_TYPE, "artist_group")
            item.setData(ROLE_SUBTITLE, info_text)
            if art_file:
                item.setData(ROLE_ART_SOURCE_PATH, art_file)
            item.setSizeHint(QSize(100, row_h))
            return item

        self._populate_rows_chunked(artists_rows, make_artist_item)

        if focus_artist:
            for idx, row in enumerate(artists_rows):
                if row['artist'] == focus_artist:
                    QTimer.singleShot(0, lambda i=idx: self._scroll_to_row_when_available(i))
                    break

    def load_artist_content(self, artist_name, animate=True):
        self.tab.view_mode = "artist_content"
        self.tab.page2_header.hide()
        self.ui.header.show()
        self.tab.nav_container.show()
        self.tab.btn_play_folder.show()
        self.tab.btn_shuffle_folder.show()

        self.tab.list_virtualizer.set_enabled(False)
        self.tab.list_virtualizer.bump_generation()
        self._cancel_folder_stats_hydration()
        self._next_population_generation()
        
        self.tab.lbl_path.setText(artist_name)
        
        # 🔥 OPTIMIZARE: Luăm piesele artistului direct din DB (Instant)
        songs_data = self.logic.get_songs_by_artist(artist_name)
        
        if songs_data:
            first_song_path = songs_data[0][-1] # Ultimul element din tuplu e path-ul
            header_art_path = self.logic.get_cached_art_path(first_song_path)
            self._load_header_art_async(header_art_path)
            
            def populate_artist():
                row_h = int(84 * self.tab.global_zoom)
                
                def make_artist_song_item(row):
                    title, artist, album, duration, ext, f = row
                    info_tech = f"{duration} | {ext}"
                    item = QListWidgetItem()
                    item.setData(Qt.ItemDataRole.DisplayRole, title)
                    item.setData(Qt.ItemDataRole.UserRole, f)
                    item.setData(ROLE_ITEM_TYPE, "file")
                    item.setData(ROLE_SUBTITLE, artist)
                    item.setData(ROLE_INFO, info_tech)
                    item.setSizeHint(QSize(100, row_h))
                    return item

                self._populate_rows_chunked(songs_data, make_artist_song_item)

            if animate:
                self._animate_list_change(populate_artist)
            else:
                populate_artist()

    def load_queue_view(self, queue_list, current_song_path):
        self.tab.view_mode = "queue"
        self._cancel_header_art_async()
        self.ui.header.show()
        self.ui.header.set_compact(True)
        self.ui.header.set_image(None)
        self.tab.nav_container.hide()
        
        # Header specific pentru Queue
        self.ui.update_page2_header("Current Queue", "list-solid-full.svg", "#FFD54F", "⏳")
        self.tab.page2_header.show()
        
        self.tab.stack.setCurrentIndex(1)
        self.tab.btn_back.show()
        # Ascundem butoanele de play folder/shuffle folder pentru că suntem deja în coadă
        self.tab.btn_play_folder.hide()
        self.tab.btn_shuffle_folder.hide()

        self.tab.list_virtualizer.set_enabled(False)
        self.tab.list_virtualizer.bump_generation()
        self._cancel_folder_stats_hydration()
        self._next_population_generation()
        self.file_list.clear()
        
        if not queue_list:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, "Queue is empty")
            item.setData(ROLE_ITEM_TYPE, "separator")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setSizeHint(QSize(100, int(28 * self.tab.global_zoom)))
            self.file_list.addItem(item)
            return

        row_h = int(28 * self.tab.global_zoom)
        for f in queue_list:
            title, artist, album, duration, ext = self.logic.get_metadata(f)
            info_tech = f"{duration} | {ext}"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, title)
            item.setData(Qt.ItemDataRole.UserRole, f)
            item.setData(ROLE_ITEM_TYPE, "file")
            item.setData(ROLE_SUBTITLE, artist)
            item.setData(ROLE_INFO, info_tech)
            if f == current_song_path:
                item.setData(ROLE_IS_CURRENT, True)
            item.setSizeHint(QSize(100, row_h))
            self.file_list.addItem(item)

        self.tab.list_virtualizer.set_enabled(True)

    def open_most_replayed_view(self):
        self.tab.view_mode = "most_replayed"
        self._cancel_header_art_async()
        self.ui.header.show()
        self.ui.header.set_compact(True)
        self.ui.header.set_image(None)
        self.tab.nav_container.hide()

        self.ui.update_page2_header("Most Replayed", "fire-solid-full.svg", "#E57373", "🔥")
        self.tab.page2_header.show()

        if not self.logic.library_root:
            self.tab.lbl_path.setText("Please select a folder from the menu first!")
            return

        self.tab.stack.setCurrentIndex(1)
        self.tab.btn_back.show()
        self.tab.btn_play_folder.show()
        self.tab.btn_shuffle_folder.show()

        songs_data = self.logic.get_most_played_songs_metadata()

        if not songs_data:
            songs_data = self.logic.get_all_songs_metadata()

        row_h = int(84 * self.tab.global_zoom)

        def make_song_item(row):
            title, artist, duration, ext, f = row
            info_tech = f"{duration} | {ext}"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, title)
            item.setData(Qt.ItemDataRole.UserRole, f)
            item.setData(ROLE_ITEM_TYPE, "file")
            item.setData(ROLE_SUBTITLE, artist)
            item.setData(ROLE_INFO, info_tech)
            item.setSizeHint(QSize(100, row_h))
            return item

        self._populate_rows_chunked(songs_data, make_song_item)

    def on_search_text_changed(self, text):
        if not self.logic.library_root: return
        if not text.strip():
            # Curățarea căutării trebuie să fie instant, nu are rost să o amânăm.
            self._search_debounce_timer.stop()
            if self.tab.stack.currentIndex() == 1:
                self.load_directory_view(self.logic.current_path, animate=False)
            return

        self._pending_search_text = text
        self._search_debounce_timer.start()

    def _execute_pending_search(self):
        text = self._pending_search_text
        if not text.strip():
            return

        if self.tab.stack.currentIndex() == 0:
            self.tab.stack.setCurrentIndex(1)
            self.tab.btn_back.show()

        self.tab.list_virtualizer.set_enabled(False)
        self.tab.list_virtualizer.bump_generation()
        self._cancel_folder_stats_hydration()
        self._next_population_generation()
        self.file_list.clear()
        self.tab.lbl_path.setText(f"Searching: '{text}'")
        matched_songs, matched_albums, matched_folders = self.logic.search_items(text)
        row_h = int(84 * self.tab.global_zoom)
        
        # Înălțime redusă (Textul stă sus, deci restul spațiului e paddingul spre piesa de jos)
        sep_h = int(18 * self.tab.global_zoom) 

        def _add_sep(title):
            s = QListWidgetItem()
            s.setData(Qt.ItemDataRole.DisplayRole, title)
            s.setData(ROLE_ITEM_TYPE, "separator")
            s.setFlags(Qt.ItemFlag.NoItemFlags)
            s.setSizeHint(QSize(100, sep_h))
            self.file_list.addItem(s)

        if matched_albums:
            _add_sep("Albums")
            for folder in sorted(list(matched_albums)):
                info_text = self._folder_info_text(folder)
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, os.path.basename(folder))
                item.setData(Qt.ItemDataRole.UserRole, folder)
                item.setData(ROLE_ITEM_TYPE, "dir")
                item.setData(ROLE_SUBTITLE, info_text)
                item.setSizeHint(QSize(100, row_h))
                self.file_list.addItem(item)
        
        if matched_folders:
            pure_folders = [f for f in matched_folders if f not in matched_albums]
            if pure_folders:
                _add_sep("Folders")
                for folder in sorted(pure_folders):
                    info_text = self._folder_info_text(folder)
                    item = QListWidgetItem()
                    item.setData(Qt.ItemDataRole.DisplayRole, os.path.basename(folder))
                    item.setData(Qt.ItemDataRole.UserRole, folder)
                    item.setData(ROLE_ITEM_TYPE, "dir")
                    item.setData(ROLE_SUBTITLE, info_text)
                    item.setSizeHint(QSize(100, row_h))
                    self.file_list.addItem(item)

        if matched_songs:
            _add_sep("All Songs")
            for f in matched_songs[:100]:
                title, artist, album, duration, ext = self.logic.get_metadata(f)
                info_tech = f"{duration} | {ext}"
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, title)
                item.setData(Qt.ItemDataRole.UserRole, f)
                item.setData(ROLE_ITEM_TYPE, "file")
                item.setData(ROLE_SUBTITLE, artist)
                item.setData(ROLE_INFO, info_tech)
                item.setSizeHint(QSize(100, row_h))
                self.file_list.addItem(item)

        self.tab.list_virtualizer.set_enabled(True)
        self._hydrate_folder_stats_later()

    # --- CONTEXT MENU LOGIC ---
    def on_context_menu(self, position):
        item = self.file_list.itemAt(position)
        if not item: return
        
        # Creăm meniul
        menu = QMenu()
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Stil modern, rotunjit (15px), consistent cu restul aplicației
        menu.setStyleSheet(f"""
            QMenu {{ 
                background-color: rgba(30, 30, 30, 0.95); 
                color: {self.tab.current_fg_color}; 
                border: 1px solid rgba(255, 255, 255, 0.1); 
                border-radius: 15px; 
                padding: 8px; 
            }}
            QMenu::item {{ 
                padding: 8px 25px; 
                border-radius: 10px; 
                margin: 3px 0px; 
                font-weight: 500;
            }}
            QMenu::item:selected {{ 
                background-color: {self.tab.current_primary_color}; 
                color: white; 
            }}
        """)
        
        act_play = menu.addAction("Play")
        PlaylistHelpers.set_action_icon_colored(act_play, "player/play-solid-full.svg", self.tab.current_fg_color)
        
        act_queue = menu.addAction("Queue")
        PlaylistHelpers.set_action_icon_colored(act_queue, "playlist/list-solid-full.svg", self.tab.current_fg_color)
        
        action = menu.exec(self.file_list.mapToGlobal(position))
        
        if action:
            path = item.data(Qt.ItemDataRole.UserRole)
            type_ = item.data(Qt.ItemDataRole.UserRole + 1)
            is_play = (action == act_play)

            if type_ == "dir":
                # Foldere mari pot avea sute de fisiere - scanam pe un thread
                # separat in loc sa inghetam UI-ul cat timp asteapta userul.
                job = _FolderScanJob(path)
                job.signals.finished.connect(
                    lambda files, is_play=is_play: self._on_folder_scan_finished(files, is_play)
                )
                self._folder_scan_pool.start(job)
                return

            files = self._get_files_from_item(path, type_)

            if not files: return

            if is_play:
                self.tab.play_files_requested.emit(files)
            else:
                self.tab.add_to_queue_requested.emit(files)

    def _on_folder_scan_finished(self, files, is_play):
        if not files: return
        if is_play:
            self.tab.play_files_requested.emit(files)
        else:
            self.tab.add_to_queue_requested.emit(files)

    def _get_files_from_item(self, path, type_):
        """ Returnează lista de fișiere audio asociată elementului selectat """
        if type_ == "file":
            return [path]
        elif type_ == "dir":
            return PlaylistScanner.get_all_songs_recursive(path)
        elif type_ == "album_group":
            data = self.logic.get_albums_grouped().get(path)
            return data['songs'] if data else []
        elif type_ == "artist_group":
            # 🔥 OPTIMIZARE: Luăm piesele din DB
            songs = self.logic.get_songs_by_artist(path)
            return [s[-1] for s in songs] # Returnăm doar path-urile
        return []
