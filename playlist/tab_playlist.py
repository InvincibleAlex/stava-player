import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QStackedWidget, QFileDialog,
                             QLineEdit, QAbstractItemView, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QSettings, QEvent, QAbstractAnimation
from PyQt6.QtGui import QMouseEvent, QColor

from .playlist_widgets import PlaylistDelegate, ListVirtualizer, ROLE_ITEM_TYPE
from .playlist_scanner import PlaylistScanner
from .playlist_ui import PlaylistUI      
from .playlist_logic import PlaylistLogic 
from .playlist_views import PlaylistViewManager
from .playlist_helpers import PlaylistHelpers
from .playlist_animations import GlitterButton, PlaylistTabAnimations
from .playlist_navigation import PlaylistTabNavigator
from core.utils import get_settings_path

from .playlist_worker import LibraryScannerThread

class PlaylistTab(QWidget):
    file_selected = pyqtSignal(str) 
    shuffle_requested = pyqtSignal(bool) # Semnal pentru a cere activarea/dezactivarea shuffle în MainApp
    request_queue_data = pyqtSignal()    # Semnal nou: Cere MainApp să trimită coada curentă
    add_to_queue_requested = pyqtSignal(list) # 🔥 Semnal nou: Adaugă lista în coadă (Play Next)
    play_files_requested = pyqtSignal(list)   # 🔥 Semnal nou: Redă lista imediat
    background_update_requested = pyqtSignal(object) # 🔥 Semnal nou: Cere schimbarea fundalului
    queue_reordered = pyqtSignal(list) # 🔥 Semnal nou: Coada a fost reordonată manual

    def __init__(self):
        super().__init__()
        
        settings_path = get_settings_path()
        self.settings = QSettings(settings_path, QSettings.Format.IniFormat)

        depth = self.settings.value("artwork_scan_depth", PlaylistScanner.MAX_ARTWORK_SCAN_DEPTH, type=int)
        depth = max(0, min(5, depth))
        PlaylistScanner.MAX_ARTWORK_SCAN_DEPTH = depth
        
        self.logic = PlaylistLogic()
        
        # Încărcăm folderul salvat (Persistență)
        saved_root = self.settings.value("library_root", "")
        if saved_root and os.path.exists(saved_root):
            self.logic.set_root_folder(saved_root)
            
        self.current_icon_color = "#CCCCCC"
        self.current_fg_color = "#FFFFFF"
        self.current_primary_color = "#00AAFF"
        self.current_menu_bg = "#252525"
        self.current_border_color = "#333333"
        self.global_zoom = 1.0 # Factor de zoom
        self.hover_preview_disabled = False
        self.anim_manager = None # Va fi setat din MainApp
        self.audio_engine = None # Va fi setat din MainApp

        # Thread-ul de scanare
        self.scanner_thread = None
        self._active_scan_root = None
        self._mouse_nav_locked = False
        self._mouse_nav_filter_installed = False

        # Inițializăm Managerul de View-uri
        # (Atenție: îl vom putea folosi complet doar după ce UI-ul este creat)
        
        self.view_mode = "dashboard" # dashboard, browser, all_songs, albums_root, album_content
        self.current_album_songs = [] # Cache pentru albumul curent deschis

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.main_layout)

        self.ui = PlaylistUI(self)

        # Creăm header-ul unificat
        (self.search_bar, self.act_sel_folder, self.act_rescan, 
         self.btn_back, self.lbl_path, self.nav_container, self.menu_btn,
         self.btn_play_folder, self.btn_shuffle_folder) = self.ui.setup_header_area(self.main_layout)

        # Header-ul este ascuns implicit până decidem ce pagină afișăm
        self.ui.header.hide() 

        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack, 1) # 🔥 FIX: Stretch=1 forțează lista să ocupe tot spațiul rămas

        self.page_dashboard = QWidget()
        self.ui.setup_dashboard(
            self.page_dashboard,
            callback_folders=self.open_folders_view,
            callback_all_songs=self.open_all_songs_view,
            callback_albums=self.open_albums_view,
            callback_artists=self.open_artists_view,
            callback_queue=self.request_queue_view, # Conectăm butonul Queue
            callback_most_replayed=self.open_most_replayed_view
        )
        self.stack.addWidget(self.page_dashboard)

        self.page_browser = QWidget()
        self.file_list = self.ui.setup_browser_list(self.page_browser, self.on_item_clicked)

        # Virtualizer: delegate draws rows, loader fetches artwork async
        self.playlist_delegate = PlaylistDelegate(self.file_list)
        self.file_list.setItemDelegate(self.playlist_delegate)
        self.playlist_delegate.hover_enabled = not self.hover_preview_disabled
        self.list_virtualizer = ListVirtualizer(
            self.file_list,
            self.playlist_delegate,
            art_path_resolver=lambda path, item_type: self.view_manager._get_art_cache_path(path, item_type),
        )
        self.apply_playlist_overscroll_settings()
        
        self.file_list.model().rowsMoved.connect(self.on_rows_moved)

        self.stack.addWidget(self.page_browser)
        
        # --- SETUP TITLU PAGINA 2 (Folders Hierarchy) ---
        # Accesăm layout-ul paginii browser pentru a insera titlul
        browser_layout = self.page_browser.layout()
        self.page2_header = self.ui.setup_page2_header_widget(browser_layout, self.go_back)
        self.page2_header.hide() # Ascuns implicit

        # --- 3. WELCOME PAGE (Index 2) ---
        self.page_welcome = QWidget()
        self.setup_welcome_page()
        self.stack.addWidget(self.page_welcome)

        # Acum că UI-ul este gata, instanțiem View Manager-ul
        self.view_manager = PlaylistViewManager(self)
        self.animations = PlaylistTabAnimations(self)
        self.navigator = PlaylistTabNavigator(self)

        self.connect_signals()

        # --- LOGICA START ---
        if not self.logic.library_root:
            self.stack.setCurrentWidget(self.page_welcome)
            self.ui.header.hide()
        else:
            self.stack.setCurrentWidget(self.page_dashboard)
            self.ui.header.show()
            self.nav_container.hide()
            self.ui.header.set_compact(True)

        self._install_mouse_navigation_filter()

    def _install_mouse_navigation_filter(self):
        app = QApplication.instance()
        if not app or self._mouse_nav_filter_installed:
            return
        app.installEventFilter(self)
        self._mouse_nav_filter_installed = True
        self.destroyed.connect(lambda _=None: self._remove_mouse_navigation_filter())

    def _remove_mouse_navigation_filter(self):
        app = QApplication.instance()
        if app and self._mouse_nav_filter_installed:
            try:
                app.removeEventFilter(self)
            except RuntimeError:
                # Widget-ul e deja distrus la nivel C++ (semnalul destroyed a
                # pornit exact acest cleanup) - Qt scoate deja filtrul automat
                # in acest caz, deci nu mai avem ce sa facem aici.
                pass
        self._mouse_nav_filter_installed = False
        return
        
        # --- LOGICĂ START ---
        if not self.logic.library_root:
            # Prima dată: Arătăm Welcome Screen și ascundem Header-ul
            self.stack.setCurrentWidget(self.page_welcome)
            self.ui.header.hide()
        else:
            # Avem bibliotecă: Arătăm Dashboard și Header-ul (fără cale)
            self.stack.setCurrentWidget(self.page_dashboard)
            self.ui.header.show()
            self.nav_container.hide() # Ascundem tot rândul de navigare (Back + Path)
            self.ui.header.set_compact(True) # Mod compact (doar Search/Menu)

    def _rgba(self, color_hex, alpha):
        color = QColor(color_hex)
        color.setAlphaF(max(0.0, min(1.0, alpha)))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alphaF()})"

    def _refresh_dashboard_button_styles(self):
        if not hasattr(self.ui, 'dashboard_buttons') or not self.ui.dashboard_buttons:
            return

        factor = max(0.6, float(self.global_zoom))
        new_font = max(12, int(16 * factor))
        new_icon = max(18, int(32 * factor))
        new_h = max(52, int(64 * factor))
        new_radius = new_h // 2
        new_padding = max(12, int(15 * factor))
        hover_bg = self._rgba(self.current_menu_bg, 0.82)

        if hasattr(self, 'page_dashboard') and self.page_dashboard.layout():
            layout = self.page_dashboard.layout()
            layout.setSpacing(max(8, int(10 * factor)))
            layout.setContentsMargins(int(20 * factor), int(5 * factor), int(20 * factor), int(20 * factor))

        for btn in self.ui.dashboard_buttons:
            btn.setFixedHeight(new_h)
            btn.setIconSize(QSize(new_icon, new_icon))
            data = btn.property("dashboard_data")
            if data:
                icon = self.ui._create_dashboard_icon_wrapper(data["icon_name"], data["color"], data["emoji"], size=new_h)
                btn.setIcon(icon)

            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    text-align: left;
                    padding-left: {new_padding}px;
                    padding-top: {new_padding}px;
                    padding-bottom: {new_padding}px;
                    border: none;
                    border-radius: {new_radius}px;
                    font-size: {new_font}px;
                    font-weight: bold;
                    color: {self.current_fg_color};
                    outline: none;
                }}
                QPushButton:hover {{
                    background-color: {hover_bg};
                    border: none;
                }}
                QPushButton:pressed {{
                    background-color: {self.current_primary_color};
                    color: black;
                    border: none;
                }}
            """)

    def _refresh_header_controls_theme(self):
        factor = max(0.6, float(self.global_zoom))
        soft_bg = self._rgba(self.current_menu_bg, 0.72)
        hover_bg = self._rgba(self.current_menu_bg, 0.9)
        soft_border = self._rgba(self.current_border_color, 0.22)
        control_h = max(30, int(30 * factor))
        control_radius = control_h // 2
        control_padding = max(12, int(15 * factor))
        circle_size = max(40, int(40 * factor))
        circle_radius = circle_size // 2
        title_size = max(16, int(24 * factor))
        icon_size = max(12, int(self.ui.mini_icon_size))

        self.lbl_path.setStyleSheet(f"""
            QLabel {{
                background-color: {soft_bg};
                color: {self.current_fg_color};
                border-radius: {control_radius}px;
                padding: 0 {control_padding}px;
                font-weight: 500;
                border: 1px solid {soft_border};
                margin-left: {max(6, int(10 * factor))}px;
            }}
            QLabel:hover {{
                background-color: {hover_bg};
            }}
        """)

        btn_style = f"""
            QPushButton {{
                background-color: {soft_bg};
                color: {self.current_fg_color};
                border-radius: {control_radius}px;
                font-size: {max(10, int(12 * factor))}px;
                font-weight: bold;
                border: 1px solid {soft_border};
            }}
            QPushButton:hover {{ background-color: {hover_bg}; }}
        """
        self.btn_back.setStyleSheet(btn_style)
        self.btn_play_folder.setStyleSheet(btn_style)
        self.btn_shuffle_folder.setStyleSheet(btn_style)

        self.ui._set_control_icon(self.btn_back, "playlist/arrow-down-solid-full.svg", self.current_icon_color, icon_size)
        self.ui._set_control_icon(self.btn_play_folder, "player/play-solid-full.svg", self.current_icon_color, icon_size)
        self.ui._set_control_icon(self.btn_shuffle_folder, "player/shuffle-solid-full.svg", self.current_icon_color, icon_size)

        if hasattr(self.ui, 'page2_title_lbl'):
            self.ui.page2_title_lbl.setStyleSheet(
                f"font-size: {title_size}px; font-weight: bold; color: {self.current_fg_color};"
            )

        if hasattr(self.ui, 'page2_back_btn'):
            self.ui.page2_back_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {soft_bg};
                    border-radius: {circle_radius}px;
                    border: 1px solid {soft_border};
                    color: {self.current_fg_color};
                }}
                QPushButton:hover {{ background-color: {hover_bg}; }}
            """)
            self.ui._set_control_icon(self.ui.page2_back_btn, "playlist/arrow-down-solid-full.svg", self.current_icon_color, icon_size)

        if hasattr(self.ui, 'page2_play_btn'):
            self.ui.page2_play_btn.setStyleSheet(btn_style)
            self.ui.page2_shuffle_btn.setStyleSheet(btn_style)
            self.ui._set_control_icon(self.ui.page2_play_btn, "player/play-solid-full.svg", self.current_icon_color, icon_size)
            self.ui._set_control_icon(self.ui.page2_shuffle_btn, "player/shuffle-solid-full.svg", self.current_icon_color, icon_size)

    def on_rows_moved(self, parent, start, end, destination, row):
        if self.view_mode == "queue":
            new_queue = []
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    new_queue.append(path)
            self.queue_reordered.emit(new_queue)

    def set_hover_enabled(self, enabled):
        enabled = bool(enabled) and not getattr(self, 'hover_preview_disabled', False)
        if hasattr(self, 'playlist_delegate') and self.playlist_delegate:
            self.playlist_delegate.hover_enabled = enabled
        if hasattr(self, 'file_list') and self.file_list:
            self.file_list.viewport().update()

    def apply_playlist_overscroll_settings(self):
        if not hasattr(self, 'file_list') or not self.file_list:
            return
        self.file_list.configure_overscroll(
            enabled=self.settings.value("playlist_overscroll_enabled", True, type=bool),
            max_offset=self.settings.value("playlist_overscroll_max_px", 52, type=int),
            return_ms=self.settings.value("playlist_overscroll_return_ms", 620, type=int),
            global_strength=self.settings.value("playlist_overscroll_global_strength", 0.32, type=float),
            spread_strength=self.settings.value("playlist_overscroll_spread_strength", 0.52, type=float),
            falloff_ratio=self.settings.value("playlist_overscroll_falloff_ratio", 0.50, type=float),
        )

    def _enable_drag_drop(self):
        self.file_list.setDragEnabled(True)
        self.file_list.setAcceptDrops(True)
        self.file_list.setDropIndicatorShown(True)
        self.file_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def _disable_drag_drop(self):
        self.file_list.setDragEnabled(False)
        self.file_list.setAcceptDrops(False)
        self.file_list.setDropIndicatorShown(False)
        self.file_list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

    def setup_welcome_page(self):
        pass # (Neschimbat)

    def set_animation_manager(self, manager):
        self.anim_manager = manager

    def set_audio_engine(self, engine):
        self.audio_engine = engine

    def setup_welcome_page(self):
        layout = QVBoxLayout(self.page_welcome)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)
        
        # Folosim noul buton cu efect Glitter
        self.btn_add = GlitterButton("Add Sources")
        self.btn_add.clicked.connect(self.select_root_folder)
        
        layout.addWidget(self.btn_add)

    def connect_signals(self):
        self.search_bar.textChanged.connect(lambda t: self.view_manager.on_search_text_changed(t))
        self.act_sel_folder.triggered.connect(self.select_root_folder)
        self.act_rescan.triggered.connect(self.rescan_library)
        self.btn_back.clicked.connect(self.go_back)
        self.btn_play_folder.clicked.connect(self.on_play_folder_clicked)
        self.btn_shuffle_folder.clicked.connect(self.on_shuffle_folder_clicked)
        self.ui.page2_play_btn.clicked.connect(self.on_play_folder_clicked)
        self.ui.page2_shuffle_btn.clicked.connect(self.on_shuffle_folder_clicked)

    def mousePressEvent(self, event: QMouseEvent):
        if self._handle_mouse_navigation_button(event):
            event.accept()
        else:
            super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and isinstance(obj, QWidget)
            and self._is_playlist_event_target(obj)
            and self._handle_mouse_navigation_button(event)
        ):
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def _is_playlist_event_target(self, obj):
        return obj is self or self.isAncestorOf(obj)

    def _handle_mouse_navigation_button(self, event):
        button = event.button()
        if button == Qt.MouseButton.BackButton:
            self.go_back()
            return True
        if button == Qt.MouseButton.ForwardButton:
            self.go_forward()
            return True
        return False

    def _begin_mouse_navigation(self):
        if self._is_mouse_navigation_busy():
            return False
        self._lock_mouse_navigation()
        return True

    def _lock_mouse_navigation(self):
        self._mouse_nav_locked = True
        duration = 260
        if getattr(self, 'anim_manager', None):
            duration = max(duration, int(getattr(self.anim_manager, 'speed_move', duration)) + 90)
        QTimer.singleShot(duration, self._unlock_mouse_navigation)

    def _unlock_mouse_navigation(self):
        self._mouse_nav_locked = False

    def _is_mouse_navigation_busy(self):
        if self._mouse_nav_locked:
            return True
        animations = getattr(self, 'animations', None)
        if not animations:
            return False
        for name in ('back_anim_group', 'enter_anim_group', '_hierarchy_anim_group', '_enter_snapshot_anim'):
            anim = getattr(animations, name, None)
            if anim and anim.state() == QAbstractAnimation.State.Running:
                return True
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Nu recalculăm header-ul în timpul tranziției de tab (previne salt vizual)
        if getattr(self, '_stabilizing', False):
            return
        if hasattr(self, 'ui') and self.ui.header:
            self.ui.header.update_geometry_state()
            
            # 🔥 FIX PREVENIRE SALT (V2): Asigurăm spațiul corect
            if not self.ui.header.isVisible():
                if hasattr(self.ui, 'header_container'):
                    self.ui.header_container.setFixedHeight(0)
            else:
                if getattr(self.ui.header, 'is_compact', False):
                    min_req = self.ui.header.layout().minimumSize().height() if self.ui.header.layout() else int(80 * getattr(self, 'global_zoom', 1.0))
                    self.ui.header.setFixedHeight(min_req)
                    if hasattr(self.ui, 'header_container'):
                        self.ui.header_container.setFixedHeight(min_req)

    def showEvent(self, event):
        super().showEvent(event)
        self._stabilize_after_show()

    def prepare_for_show(self):
        """ Pregătește geometria înainte ca tab-ul să devină vizibil (folosit de controller). """
        self._stabilize_after_show()

    def _stabilize_after_show(self):
        if not self.isVisible():
            return

        self._stabilizing = True

        self.setUpdatesEnabled(False)
        try:
            # Use scroll saved during hideEvent (most reliable)
            scroll_pos = getattr(self, '_scroll_on_hide', 0)
            if hasattr(self, 'file_list') and self.file_list:
                if hasattr(self.file_list, 'stop_scroll_animation'):
                    self.file_list.stop_scroll_animation(snap_to_end=True)

            # Set header height BEFORE layout.activate()
            if hasattr(self, 'ui') and self.ui.header:
                header = self.ui.header
                container = self.ui.header_container
                
                if not header.isVisible():
                    container.setFixedHeight(0)
                else:
                    if header.pixmap and not header.is_compact:
                        base_h = self.height()
                        if base_h >= 200:
                            target_h = int(base_h * 0.35)
                            target_h = min(target_h, base_h - 150)
                            if header.layout():
                                min_req = header.layout().minimumSize().height()
                                if target_h < min_req:
                                    target_h = min_req
                            header.setFixedHeight(target_h)
                            container.setFixedHeight(target_h)
                    elif header.is_compact:
                        min_req = header.layout().minimumSize().height() if header.layout() else int(80 * getattr(self, 'global_zoom', 1.0))
                        header.setFixedHeight(min_req)
                        container.setFixedHeight(min_req)

            if self.main_layout:
                self.main_layout.activate()

            # Restore scroll position after layout settled
            if hasattr(self, 'file_list') and self.file_list:
                self.file_list.verticalScrollBar().setValue(scroll_pos)
        finally:
            self.setUpdatesEnabled(True)
            self._stabilizing = False

        # Deferred restore: catch any post-event layout drift
        if hasattr(self, 'file_list') and self.file_list:
            QTimer.singleShot(0, lambda: self._deferred_scroll_restore(scroll_pos))

    def _deferred_scroll_restore(self, target):
        if hasattr(self, 'file_list') and self.file_list and self.isVisible():
            self.file_list.verticalScrollBar().setValue(target)

    def hideEvent(self, event):
        # Save scroll position before the widget is hidden (most reliable point)
        if hasattr(self, 'file_list') and self.file_list:
            self._scroll_on_hide = self.file_list.verticalScrollBar().value()
        super().hideEvent(event)

    def select_root_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Music Library Root")
        if folder:
            self.settings.setValue("library_root", folder) # Salvăm calea
            name = self.logic.set_root_folder(folder)
            self.lbl_path.setText(name)
            self.start_background_scan() # 🔥 Pornim scanarea în background
            self.search_bar.clear()
            
            # Dacă eram pe Welcome Screen, trecem la Dashboard
            if self.stack.currentWidget() == self.page_welcome:
                self.stack.setCurrentWidget(self.page_dashboard)
                self.ui.header.show()
                self.nav_container.hide()
                self.ui.header.set_compact(True)
            
            if self.stack.currentIndex() == 1:
                self.view_manager.load_directory_view(folder)

    def rescan_library(self):
        """ Apelat manual din meniu """
        if not self.logic.library_root: return
        scan_root = self._current_rescan_root()
        
        # 1. Oprim scanarea curentă (dacă există) pentru a nu avea conflicte la DB
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.stop()
            self.scanner_thread.wait()
            
        # 2. Ștergem tot (DB + Cache + Memorie)
        is_full_rescan = os.path.normcase(os.path.normpath(scan_root)) == os.path.normcase(os.path.normpath(self.logic.library_root))
        if is_full_rescan:
            self.logic.hard_reset_library()
        else:
            self.logic.invalidate_scan_scope(scan_root)
        
        # 3. Pornim scanarea de la zero
        self.start_background_scan(scan_root=scan_root)

    def _current_rescan_root(self):
        if self.view_mode == "browser" and self.logic.current_path and os.path.isdir(self.logic.current_path):
            return self.logic.current_path
        return self.logic.library_root

    def start_background_scan(self, scan_root=None):
        """ Inițiază procesul de scanare pe thread separat """
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.stop()
            self.scanner_thread.wait()

        self._active_scan_root = scan_root if scan_root and os.path.isdir(scan_root) else self.logic.library_root
        self.scanner_thread = LibraryScannerThread(self.logic, self.audio_engine, scan_root=self._active_scan_root)
        self.ui.progress_bar.show()
        self.ui.progress_bar.setValue(0)
        self.scanner_thread.progress_update.connect(lambda msg: self.lbl_path.setText(msg))
        self.scanner_thread.progress_percent.connect(self.ui.progress_bar.setValue)
        self.scanner_thread.scan_finished.connect(self.on_scan_finished)
        self.scanner_thread.start()

    def on_scan_finished(self):
        """ Când scanarea e gata, actualizăm UI-ul """
        self.ui.progress_bar.hide()
        scan_root = self._active_scan_root
        self._active_scan_root = None
        # Dacă suntem pe o pagină care depinde de date, o reîncărcăm
        if self.view_mode == "browser" and self.logic.current_path:
            self.view_manager.load_directory_view(self.logic.current_path, animate=False)
        elif self.view_mode in ["all_songs", "albums_root", "artists_root", "most_replayed"]:
            # Re-apelăm funcția curentă pentru a popula lista cu noile date
            if self.view_mode == "all_songs": self.open_all_songs_view()
            elif self.view_mode == "albums_root": self.open_albums_view()
            elif self.view_mode == "artists_root": self.open_artists_view()
            elif self.view_mode == "most_replayed": self.open_most_replayed_view()
            
        # Resetăm background-ul la default/curent
        else:
            root_name = os.path.basename(self.logic.library_root) if self.logic.library_root else "Library"
            if scan_root and scan_root != self.logic.library_root:
                root_name = os.path.basename(scan_root) or root_name
            self.lbl_path.setText(root_name)

        if self.view_mode != "browser":
            self.background_update_requested.emit(None)

    def open_folders_view(self):
        self.navigator.open_folders_view()

    def open_all_songs_view(self):
        self.navigator.open_all_songs_view()

    def open_albums_view(self, focus_album=None):
        self.navigator.open_albums_view(focus_album=focus_album)

    def load_album_content(self, album_name, header_pixmap=None):
        self.navigator.load_album_content(album_name, header_pixmap=header_pixmap)

    def open_artists_view(self, focus_artist=None):
        self.navigator.open_artists_view(focus_artist=focus_artist)

    def open_most_replayed_view(self):
        self.navigator.open_most_replayed_view()

    def load_artist_content(self, artist_name):
        self.navigator.load_artist_content(artist_name)

    def request_queue_view(self):
        self.navigator.request_queue_view()

    def go_back(self):
        if not self._begin_mouse_navigation():
            return
        self.navigator.go_back()

    def go_to_dashboard(self, reset_history=False):
        self.navigator.go_to_dashboard(reset_history=reset_history)

    def go_forward(self):
        if not self._begin_mouse_navigation():
            return
        self.navigator.go_forward()

    def on_item_clicked(self, item):
        self.navigator.on_item_clicked(item)

    def locate_file(self, filepath):
        self.navigator.locate_file(filepath)

    def on_play_folder_clicked(self):
        """ Redă folderul curent în ordine (Shuffle OFF) """
        files = self.playlist_files
        if files:
            self.shuffle_requested.emit(False) # Cerem Shuffle OFF
            self.file_selected.emit(files[0])  # Pornim prima piesă

    def on_shuffle_folder_clicked(self):
        """ Redă folderul curent amestecat (Shuffle ON) """
        files = self.playlist_files
        if files:
            import random
            target = random.choice(files)
            self.shuffle_requested.emit(True) # Cerem Shuffle ON
            self.file_selected.emit(target)   # Pornim o piesă aleatorie

    def set_zoom_factor(self, factor):
        """ Primește zoom-ul din MainApp și actualizează lista """
        self.global_zoom = factor
        self.ui.apply_zoom(factor)
        
        # Actualizăm delegate-ul virtualizer
        self.playlist_delegate.set_zoom(factor)
        row_h = self.playlist_delegate._row_height()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item:
                item.setSizeHint(QSize(100, row_h))
        self.file_list.viewport().update()
        if self.list_virtualizer._enabled:
            self.list_virtualizer.load_visible()

        self._refresh_dashboard_button_styles()
        
        self._refresh_header_controls_theme()
        if hasattr(self.ui, 'header'):
            self.ui.header.update_geometry_state()
        
        # Forțăm recalcularea layout-ului listei
        self.file_list.doItemsLayout()
        
        # Actualizăm butonul Add Sources (Welcome Page)
        if hasattr(self, 'btn_add'):
            self.btn_add.apply_zoom(factor)

    def update_theme_colors(self, colors):
        self.current_icon_color = colors.get("ICON_COLOR", "#CCCCCC")
        self.current_fg_color = colors.get("FG", "#FFFFFF")
        self.current_primary_color = colors.get("PRIMARY", "#00AAFF")
        self.current_menu_bg = colors.get("MENU_BG", "#252525")
        self.current_border_color = colors.get("BORDER", "#333333")
        
        # 0. Update Header Background & Mask
        self.ui.update_theme_colors(colors)
        
        # 1. Update Icons
        self._set_action_icon_colored(self.act_sel_folder, "folder-solid-full.svg", self.current_icon_color)
        self._set_action_icon_colored(self.act_rescan, "arrow-rotate-right-solid-full.svg", self.current_icon_color)
        
        self._refresh_header_controls_theme()
        self._refresh_dashboard_button_styles()

        # Delegate colors
        self.playlist_delegate.set_colors(self.current_fg_color, self.current_primary_color, self.current_icon_color)
            
        # Dacă suntem pe pagina Queue, reîmprospătăm pentru a lua noile culori
        if self.view_mode == "queue":
            self.request_queue_data.emit()

        # 4. Repaint delegate items with new colors
        self.file_list.viewport().update()

    def _set_action_icon_colored(self, action, filename, color_hex):
        PlaylistHelpers.set_action_icon_colored(action, filename, color_hex)
            
    @property
    def playlist_files(self):
        current_files = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            type_ = item.data(ROLE_ITEM_TYPE)
            if type_ == "file" and path:
                current_files.append(path)
        
        # MODIFICAT: Dacă nu sunt fișiere vizibile (ex: suntem într-un folder Root cu subfoldere),
        # și suntem în modul Browser, returnăm recursiv tot ce e în folderul curent.
        if not current_files and self.view_mode == "browser" and self.logic.current_path:
            return PlaylistScanner.get_all_songs_recursive(self.logic.current_path)
            
        # MODIFICAT: Pentru Artists/Albums Root, redăm toată biblioteca
        if not current_files and self.view_mode in ["artists_root", "albums_root"]:
            if not self.logic.all_songs_cache:
                self.logic.rescan_library()
            return self.logic.all_songs_cache
            
        return current_files

    def load_queue_view(self, queue_list, current_song_path):
        """ Apelată de MainApp cu datele efective """
        self.view_manager.load_queue_view(queue_list, current_song_path)
        self.view_mode = "queue"
        self._enable_drag_drop()
