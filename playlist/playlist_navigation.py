import os

from PyQt6.QtCore import Qt, QRect, QEvent, QTimer
from PyQt6.QtGui import QPixmap, QIcon, QPainter
from PyQt6.QtWidgets import QAbstractItemView, QApplication

from .playlist_widgets import ROLE_ITEM_TYPE, ROLE_ART_PATH


class PlaylistTabNavigator:
    def __init__(self, tab):
        self.tab = tab

    def open_folders_view(self):
        if not self.tab.logic.library_root:
            self.tab.lbl_path.setText("Please select a folder from the menu first!")
            return

        def navigate():
            self.tab.view_mode = "browser"
            self.tab._disable_drag_drop()
            self.tab.stack.setCurrentIndex(1)
            self.tab.btn_back.show()
            self.tab.view_manager.load_directory_view(self.tab.logic.library_root, animate=False)

        self.tab.animations.animate_playlist_page_switch(navigate, target_widget=self.tab.page_browser)

    def open_all_songs_view(self):
        def navigate():
            self.tab.view_manager.open_all_songs_view()
            self.tab.background_update_requested.emit(None)

        self.tab.animations.animate_playlist_page_switch(navigate, target_widget=self.tab.page_browser)

    def open_albums_view(self, focus_album=None):
        def navigate():
            self.tab.view_manager.open_albums_view(focus_album=focus_album)
            self.tab.background_update_requested.emit(None)

        self.tab.animations.animate_playlist_page_switch(navigate, target_widget=self.tab.page_browser)

    def load_album_content(self, album_name, header_pixmap=None):
        self.tab.view_manager.load_album_content(album_name, header_pixmap=header_pixmap)
        if header_pixmap:
            self.tab.background_update_requested.emit(header_pixmap)

    def open_artists_view(self, focus_artist=None):
        def navigate():
            self.tab.view_manager.open_artists_view(focus_artist=focus_artist)
            self.tab.background_update_requested.emit(None)

        self.tab.animations.animate_playlist_page_switch(navigate, target_widget=self.tab.page_browser)

    def open_most_replayed_view(self):
        def navigate():
            self.tab.view_manager.open_most_replayed_view()
            self.tab.background_update_requested.emit(None)

        self.tab.animations.animate_playlist_page_switch(navigate, target_widget=self.tab.page_browser)

    def load_artist_content(self, artist_name):
        self.tab.view_manager.load_artist_content(artist_name)

    def request_queue_view(self):
        def navigate():
            self.tab.request_queue_data.emit()

        self.tab.animations.animate_playlist_page_switch(navigate, target_widget=self.tab.page_browser)

    def go_back(self):
        if self.tab.search_bar.text():
            self.tab.search_bar.clear()
            return

        header_pix, header_rect = self._capture_header_back_state()

        if self.tab.view_mode == "artist_content":
            target_id = self.tab.lbl_path.text()
            self.open_artists_view(focus_artist=target_id)
            self.tab.animations.animate_from_header(header_pix, target_id, header_rect)
            return

        if self.tab.view_mode == "album_content":
            target_id = self.tab.lbl_path.text()
            self.open_albums_view(focus_album=target_id)
            self.tab.animations.animate_from_header(header_pix, target_id, header_rect)
            return

        if self.tab.view_mode in ["albums_root", "all_songs", "artists_root", "most_replayed", "queue"]:
            self.go_to_dashboard()
            return

        if self.tab.view_mode == "browser":
            folder_leaving = self.tab.logic.current_path
            parent = self.tab.logic.get_parent_directory()
            if parent:
                # Imaginea corecta pentru header-ul la care ne intoarcem a fost
                # deja retinuta cand am intrat in acest folder (vezi
                # _handle_directory_click) - o scoatem de pe stack aici, o
                # singura data, indiferent pe ce ramura mergem mai jos.
                incoming_header_pix = self._pop_header_pixmap()

                if self.tab.anim_manager and header_pix and parent == self.tab.logic.library_root:
                    self.tab.view_manager.defer_background_updates()
                    self.tab.animations.animate_browser_back_to_root(
                        load_callback=lambda: self.tab.view_manager.load_directory_view(
                            parent,
                            animate=False,
                            target_file=folder_leaving,
                        ),
                        header_pix=header_pix,
                        folder_leaving=folder_leaving,
                        header_rect=header_rect,
                        incoming_header_pix=incoming_header_pix,
                    )
                elif self.tab.anim_manager and header_pix:
                    self.tab.view_manager.defer_background_updates()
                    self.tab.animations.animate_browser_back_to_parent(
                        load_callback=lambda: self.tab.view_manager.load_directory_view(
                            parent,
                            animate=False,
                            target_file=folder_leaving,
                        ),
                        header_pix=header_pix,
                        folder_leaving=folder_leaving,
                        header_rect=header_rect,
                        incoming_header_pix=incoming_header_pix,
                    )
                else:
                    self.tab.view_manager.load_directory_view(parent, target_file=folder_leaving)
            else:
                self.go_to_dashboard()
            return

        self.go_to_dashboard()

    def _push_header_pixmap(self, pixmap):
        stack = getattr(self.tab, '_header_pixmap_stack', None)
        if stack is None:
            stack = []
            self.tab._header_pixmap_stack = stack
        stack.append(pixmap)

    def _pop_header_pixmap(self):
        stack = getattr(self.tab, '_header_pixmap_stack', None)
        if not stack:
            return None
        return stack.pop()

    def go_to_dashboard(self, reset_history=False):
        def navigate():
            self.tab.view_mode = "dashboard"
            self.tab._disable_drag_drop()

            # Iesim din ierarhia de foldere - orice imagini de header retinute
            # pentru un "back" ulterior nu mai au sens (am putea reintra pe alt
            # traseu), le golim ca sa nu ramana date vechi pe stack.
            self.tab._header_pixmap_stack = []

            if reset_history and self.tab.logic.library_root:
                self.tab.logic.current_path = self.tab.logic.library_root
                self.tab.logic.forward_stack = []

            self.tab.stack.setCurrentIndex(0)
            self.tab.btn_back.hide()
            self.tab.btn_play_folder.hide()
            self.tab.btn_shuffle_folder.hide()
            self.tab.ui.header.set_image(None)
            self.tab.nav_container.hide()
            self.tab.ui.header.set_compact(True)
            self.tab.page2_header.hide()
            self.tab.background_update_requested.emit(None)

        # Acelasi fade folosit si la intrarea in sectiuni - se aplica la
        # intoarcerea din oricare dintre ele (Folders, All Songs, Albums,
        # Artists, Most Replayed, Queue) inapoi la dashboard.
        self.tab.animations.animate_playlist_page_switch(navigate, target_widget=self.tab.page_dashboard)

    def go_forward(self):
        path = self.tab.logic.get_forward_directory()
        if path:
            self._animate_forward_to_directory(path)

    def on_item_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        item_type = item.data(ROLE_ITEM_TYPE)

        if item_type == "dir":
            self._handle_directory_click(path, item)
            return

        if item_type == "album_group":
            self._handle_album_click(path, item)
            return

        if item_type == "artist_group":
            self.load_artist_content(path)
            return

        if item_type == "file":
            self._handle_file_click(path, item)

    def locate_file(self, filepath):
        if not filepath or not self.tab.logic.library_root:
            return
        if not filepath.startswith(self.tab.logic.library_root):
            return

        parent_dir = os.path.dirname(filepath)
        if not os.path.exists(parent_dir):
            return

        self.tab.view_mode = "browser"
        self.tab._disable_drag_drop()
        self.tab.stack.setCurrentIndex(1)
        self.tab.btn_back.show()
        self.tab.logic.navigate_to(parent_dir)
        self.tab.view_manager.load_directory_view(parent_dir, target_file=filepath)

        for index in range(self.tab.file_list.count()):
            item = self.tab.file_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == filepath:
                self.tab.file_list.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                item.setSelected(True)
                break

    def _capture_header_back_state(self):
        header_pix = None
        header_rect = None

        if self.tab.ui.header.isVisible() and not self.tab.ui.header.is_compact and self.tab.ui.header.pixmap:
            header_pix = self.tab.ui.header.pixmap.copy()
            if self.tab.anim_manager:
                header_rect = self.tab.anim_manager.get_global_rect(self.tab.ui.header)

        return header_pix, header_rect

    def _capture_current_header_pixmap(self):
        current_header = getattr(self.tab.ui, 'header', None)
        if current_header is None:
            return None

        if hasattr(current_header, 'source_image') and not current_header.source_image.isNull():
            return QPixmap.fromImage(current_header.source_image)
        if current_header.pixmap and not current_header.pixmap.isNull():
            return current_header.pixmap.copy()
        return None

    def _find_visible_item_by_path(self, path):
        if not path:
            return None

        for index in range(self.tab.file_list.count()):
            item = self.tab.file_list.item(index)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                rect = self.tab.file_list.visualItemRect(item)
                if not rect.isValid() or not self.tab.file_list.viewport().rect().intersects(rect):
                    self.tab.file_list.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                    QApplication.processEvents()
                return item
        return None

    def _animate_forward_to_directory(self, path):
        item = self._find_visible_item_by_path(path)
        anim_duration = self.tab.anim_manager.speed_move if self.tab.anim_manager else 250

        if not item or not self.tab.anim_manager:
            self.tab.view_manager.load_directory_view(path)
            return

        start_rect, pixmap = self._build_item_animation_source(item, path)
        static_item_overlay_data = self._build_static_item_overlay_data(item)
        previous_header_pixmap = self._capture_current_header_pixmap()

        if start_rect and pixmap:
            self.tab.ui.header.set_content_opacity(0.0)

        self.tab.animations.animate_browser_forward_to_child(
            load_callback=lambda: self.tab.view_manager.load_directory_view(
                path,
                header_pixmap=pixmap,
                duration=anim_duration,
                animate=False,
            ),
            anim_duration=anim_duration,
            start_rect=start_rect,
            pixmap=pixmap,
            previous_header_pixmap=previous_header_pixmap,
            static_item_overlay_data=static_item_overlay_data,
        )

    def _build_item_animation_source(self, item, path, use_window_target=False, album_art_lookup=None):
        start_rect = None
        pixmap = None

        if not self.tab.anim_manager:
            return start_rect, pixmap

        rect = self.tab.file_list.visualItemRect(item)
        if not rect.isValid():
            return start_rect, pixmap

        icon_size = int(64 * self.tab.global_zoom)
        icon_rect = QRect(
            rect.left() + 10,
            rect.top() + (rect.height() - icon_size) // 2,
            icon_size,
            icon_size,
        )
        target_widget = self.tab.window() if use_window_target else self.tab.anim_manager.main
        top_left = self.tab.file_list.viewport().mapTo(target_widget, icon_rect.topLeft())
        start_rect = QRect(top_left, icon_rect.size())

        item_type = item.data(ROLE_ITEM_TYPE) or "file"
        pixmap = self._load_fullsize_animation_pixmap(item, path, item_type, album_art_lookup)
        if pixmap and not pixmap.isNull():
            return start_rect, pixmap

        icon_data = item.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon_data, QIcon):
            pixmap = icon_data.pixmap(icon_size, icon_size)
        elif isinstance(icon_data, QPixmap):
            pixmap = icon_data

        return start_rect, pixmap

    def _load_fullsize_animation_pixmap(self, item, path, item_type, album_art_lookup=None):
        art_path = self._resolve_animation_art_path(item, path, item_type, album_art_lookup)
        if not art_path:
            return None

        pixmap = QPixmap(art_path)
        if pixmap.isNull():
            return None
        return self._cap_animation_pixmap(pixmap)

    def _resolve_animation_art_path(self, item, path, item_type, album_art_lookup=None):
        candidates = [item.data(ROLE_ART_PATH)]

        if path:
            if album_art_lookup:
                try:
                    candidates.append(album_art_lookup(path))
                except Exception:
                    pass

            view_manager = getattr(self.tab, 'view_manager', None)
            resolver = getattr(view_manager, '_get_art_cache_path', None)
            if callable(resolver):
                try:
                    candidates.append(resolver(path, item_type))
                except Exception:
                    pass

            logic = getattr(self.tab, 'logic', None)
            if logic and hasattr(logic, 'get_cached_art_path'):
                try:
                    candidates.append(logic.get_cached_art_path(path))
                except Exception:
                    pass

        for candidate in candidates:
            try:
                candidate_path = os.fspath(candidate)
            except (TypeError, ValueError):
                continue
            if candidate_path and os.path.exists(candidate_path):
                return candidate_path
        return None

    def _cap_animation_pixmap(self, pixmap):
        max_side = 1800
        if max(pixmap.width(), pixmap.height()) <= max_side:
            return pixmap
        return pixmap.scaled(
            max_side,
            max_side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _build_static_item_overlay_data(self, item):
        rect = self.tab.file_list.visualItemRect(item)
        if not rect.isValid() or not self.tab.file_list.viewport().rect().intersects(rect):
            return None

        item_pixmap = self.tab.file_list.viewport().grab(rect)
        if item_pixmap.isNull():
            return None

        icon_size = int(64 * self.tab.global_zoom)
        icon_rect = QRect(
            10,
            (rect.height() - icon_size) // 2,
            icon_size,
            icon_size,
        )

        painter = QPainter(item_pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(icon_rect, Qt.GlobalColor.transparent)
        painter.end()

        overlay_top_left = self.tab.file_list.viewport().mapTo(self.tab, rect.topLeft())
        overlay_rect = QRect(overlay_top_left, rect.size())
        return {
            'pixmap': item_pixmap,
            'rect': overlay_rect,
        }

    def _clear_hover_highlight_for_capture(self):
        self.tab.set_hover_enabled(False)
        viewport = self.tab.file_list.viewport()
        QApplication.sendEvent(viewport, QEvent(QEvent.Type.Leave))
        viewport.update()
        QApplication.processEvents()

    def _run_after_hover_cleared(self, callback, delay_ms=18):
        self._clear_hover_highlight_for_capture()
        QTimer.singleShot(max(0, int(delay_ms)), callback)

    def _handle_directory_click(self, path, item):
        def continue_after_hover_clear():
            entering_from_root = (self.tab.view_mode == "browser" and self.tab.logic.current_path == self.tab.logic.library_root)
            anim_duration = self.tab.anim_manager.speed_move if self.tab.anim_manager else 250
            start_rect, pixmap = self._build_item_animation_source(item, path)
            static_item_overlay_data = self._build_static_item_overlay_data(item)
            previous_header_pixmap = None

            if not entering_from_root:
                previous_header_pixmap = self._capture_current_header_pixmap()
                # Retinem aceasta imagine pentru cand se revine la acest nivel
                # (go_back) - header-ul isi incarca imaginea asincron, deci daca
                # am recaptura-o abia la intoarcere, am prinde-o adesea neincarcata
                # inca (se vedea imaginea gresita o clipa, apoi un salt instant).
                if previous_header_pixmap and not previous_header_pixmap.isNull():
                    self._push_header_pixmap(previous_header_pixmap)

            if self.tab.logic.navigate_to(path):
                if start_rect and pixmap and self.tab.anim_manager:
                    self.tab.ui.header.set_content_opacity(0.0)

                if entering_from_root:
                    self.tab.animations.animate_browser_enter_from_root(
                        load_callback=lambda: self.tab.view_manager.load_directory_view(
                            path,
                            header_pixmap=pixmap,
                            duration=anim_duration,
                            animate=False,
                        ),
                        anim_duration=anim_duration,
                        start_rect=start_rect,
                        pixmap=pixmap,
                        static_item_overlay_data=static_item_overlay_data,
                    )
                else:
                    self.tab.animations.animate_browser_forward_to_child(
                        load_callback=lambda: self.tab.view_manager.load_directory_view(
                            path,
                            header_pixmap=pixmap,
                            duration=anim_duration,
                            animate=False,
                        ),
                        anim_duration=anim_duration,
                        start_rect=start_rect,
                        pixmap=pixmap,
                        previous_header_pixmap=previous_header_pixmap,
                        static_item_overlay_data=static_item_overlay_data,
                    )

        self._run_after_hover_cleared(continue_after_hover_clear)

    def _handle_album_click(self, path, item):
        def continue_after_hover_clear():
            albums_data = self.tab.logic.get_albums_grouped() if path else {}

            def album_lookup(album_name):
                if album_name in albums_data and albums_data[album_name]['art_file']:
                    return self.tab.logic.get_cached_art_path(albums_data[album_name]['art_file'])
                return None

            start_rect, pixmap = self._build_item_animation_source(item, path, album_art_lookup=album_lookup)
            static_item_overlay_data = self._build_static_item_overlay_data(item)

            if start_rect and pixmap and self.tab.anim_manager:
                self.tab.ui.header.set_content_opacity(0.0)

            self.load_album_content(path, header_pixmap=pixmap)
            static_item_overlay = self.tab.animations.create_static_item_overlay(static_item_overlay_data)

            def finish_album_transition():
                self.tab.animations.cleanup_overlay_widget(static_item_overlay)
                self.tab.set_hover_enabled(True)

            self.tab.animations.animate_to_header(start_rect, pixmap, on_finished=finish_album_transition)

        self._run_after_hover_cleared(continue_after_hover_clear)

    def _handle_file_click(self, path, item):
        def continue_after_hover_clear():
            src = None
            rect = self.tab.file_list.visualItemRect(item)
            if rect.isValid() and self.tab.file_list.viewport().rect().intersects(rect):
                zoom = getattr(self.tab, 'global_zoom', 1.0)
                start_rect, pixmap = self._build_item_animation_source(item, path, use_window_target=True)
                if pixmap and not pixmap.isNull():
                    src = {'rect': start_rect, 'pixmap': pixmap, 'radius': 12.0 * zoom}
            self.tab._pending_anim_source = src
            restore_delay = self.tab.anim_manager.speed_move if self.tab.anim_manager else 250
            QTimer.singleShot(max(120, int(restore_delay)), lambda: self.tab.set_hover_enabled(True))
            self.tab.file_selected.emit(path)

        self._run_after_hover_cleared(continue_after_hover_clear)
