import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QToolButton, QMenu, QGridLayout, QProgressBar,
                             QStackedWidget, QFrame, QLayout)
from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor

from core.utils import IconHelper
try:
    from .playlist_widgets import SmoothListWidget
except ImportError:
    from playlist_widgets import SmoothListWidget

# Importăm clasele de header din noul fișier
from .playlist_header import HeaderContainer, PlaylistHeader

class PlaylistUI(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.header = None # Referință către header
        self.mini_icon_size = 16
        self.current_zoom = 1.0
        self.search_collapsed_width = 40
        self.search_expanded_width = 300
        self.search_icon_size = 18
        self.menu_icon_size = 30
        # Calea de bază către icons
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.icons_dir = os.path.join(base_dir, 'icons')
        self.dashboard_buttons = [] # Inițializare sigură

    def _rgba(self, color_hex, alpha):
        color = QColor(color_hex)
        color.setAlphaF(max(0.0, min(1.0, alpha)))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alphaF()})"

    def setup_header_area(self, parent_layout):
        """ Construiește zona de sus unificată (Search + Navigare + Background) """
        icon_color = getattr(self.parent, 'current_icon_color', '#AAAAAA') if self.parent else '#AAAAAA'
        fg = getattr(self.parent, 'current_fg_color', '#FFFFFF') if self.parent else '#FFFFFF'
        menu_bg = getattr(self.parent, 'current_menu_bg', '#252525') if self.parent else '#252525'
        border = getattr(self.parent, 'current_border_color', '#333333') if self.parent else '#333333'
        soft_bg = self._rgba(menu_bg, 0.72)
        hover_bg = self._rgba(menu_bg, 0.9)
        soft_border = self._rgba(border, 0.22)

        # --- CONTAINER EXTERN (WRAPPER) ---
        # Acesta învelește header-ul pentru a permite manipulări ulterioare de layout
        self.header_container = HeaderContainer()
        container_layout = QVBoxLayout(self.header_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.header = PlaylistHeader()
        main_vbox = QVBoxLayout(self.header)
        self.header_main_layout = main_vbox
        # Reducem marginea de jos la 5px pentru a fi mai compact
        main_vbox.setContentsMargins(15, 15, 15, 15) 
        main_vbox.setSpacing(10)

        # --- RÂNDUL 1: SEARCH + MENU ---
        top_row = QHBoxLayout()
        self.header_top_row = top_row
        
        # --- 1. CUSTOM SEARCH BAR (Frame -> Layout -> Icon + Edit) ---
        search_frame = QFrame()
        self.search_frame = search_frame
        search_frame.setFixedHeight(40)
        # Pornim ca un cerc perfect (40x40)
        search_frame.setMaximumWidth(self.search_collapsed_width)
        search_frame.setStyleSheet(
            f"QFrame {{ background-color: {soft_bg}; border-radius: 20px; border: 1px solid {soft_border}; }} "
            f"QFrame:hover {{ background-color: {hover_bg}; }}"
        )
        
        sf_layout = QHBoxLayout(search_frame)
        sf_layout.setContentsMargins(0, 0, 10, 0) # 0 la stânga pentru buton, 10 la dreapta pentru text
        sf_layout.setSpacing(0) 

        # A. Butonul de Search (Trigger pentru animație)
        btn_search = QPushButton()
        self.btn_search = btn_search
        btn_search.setFixedSize(40, 40)
        btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_search.setStyleSheet("background: transparent; border: none; border-radius: 20px;")
        
        search_icon_path = os.path.join(self.icons_dir, "playlist", "magnifying-glass-solid-full.svg")
        icon = IconHelper.get_colored_icon(search_icon_path, icon_color, size=self.search_icon_size)
        if not icon.isNull():
            btn_search.setIcon(icon)
            btn_search.setIconSize(QSize(self.search_icon_size, self.search_icon_size))
        else:
            btn_search.setText("🔍")

        # B. Text Input
        search_bar = QLineEdit()
        self.search_bar_input = search_bar
        search_bar.setPlaceholderText("Search...")
        search_bar.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: {fg};
                font-size: 15px; 
                margin-left: 5px;
            }
        """)
        search_bar.hide() # Ascundem inițial pentru a nu bloca click-ul pe lupă

        sf_layout.addWidget(btn_search)
        sf_layout.addWidget(search_bar)

        # --- ANIMAȚIE EXTINDERE ---
        # Animăm maximumWidth pentru a permite layout-ului să se extindă
        anim = QPropertyAnimation(search_frame, b"maximumWidth")
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Salvăm referința ca să nu fie ștearsă de Garbage Collector
        search_frame.anim = anim 
        
        def on_anim_finished():
            # Dacă s-a terminat animația de închidere (40px), ascundem textul
            if search_frame.maximumWidth() == self.search_collapsed_width:
                search_bar.hide()
        
        anim.finished.connect(on_anim_finished)

        def toggle_search():
            current_w = search_frame.width()
            if current_w <= self.search_collapsed_width + 5: # Dacă e cerc (collapsed)
                search_bar.show() # Afișăm bara de scris înainte de extindere
                anim.setStartValue(self.search_collapsed_width)
                anim.setEndValue(self.search_expanded_width)
                anim.start()
                search_bar.setFocus()
            else:
                # Colapsăm înapoi la cerc
                anim.setStartValue(current_w)
                anim.setEndValue(self.search_collapsed_width)
                anim.start()
                search_bar.clear()
                search_bar.clearFocus()

        btn_search.clicked.connect(toggle_search)
        
        # --- 2. MENU BUTTON ---
        menu_btn = QToolButton()
        self.menu_btn = menu_btn
        self._set_button_icon(menu_btn, "playlist/menu-circle-dots.svg", icon_color, size=self.menu_icon_size)
        
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_btn.setFixedSize(40, 40)
        
        menu_btn.setStyleSheet("""
            QToolButton { 
                background-color: %s; 
                color: %s; 
                border: 1px solid %s; 
                border-radius: 20px; 
                padding: 0px; 
            }
            QToolButton::menu-indicator { image: none; }
            QToolButton:hover { background-color: %s; }
        """ % (soft_bg, fg, soft_border, hover_bg))

        main_menu = QMenu(menu_btn)
        self.main_menu = main_menu
        main_menu.setStyleSheet(f"QMenu {{ background: {menu_bg}; color: {fg}; border: 1px solid {self._rgba(border, 0.5)}; }}")
        
        act_sel_folder = QAction(" Select Folders", self)
        act_rescan = QAction(" Rescan", self)
        
        main_menu.addAction(act_sel_folder)
        main_menu.addAction(act_rescan)
        menu_btn.setMenu(main_menu)
        
        top_row.addWidget(search_frame)
        top_row.addStretch()
        top_row.addWidget(menu_btn)
        
        main_vbox.addLayout(top_row)
        
        # Spacer elastic vertical (împinge totul jos)
        main_vbox.addStretch()
        
        # --- RÂNDUL 2: BACK + PATH ---
        # Grupăm rândul de navigare într-un container pentru a-l ascunde complet
        
        # --- 1.5 PROGRESS BAR (NOU) ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { border: none; background: rgba(255,255,255,0.1); border-radius: 2px; } QProgressBar::chunk { background: #00AAFF; border-radius: 2px; }")
        self.progress_bar.hide()
        main_vbox.addWidget(self.progress_bar)
        
        self.nav_container = QWidget()
        self.nav_container.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(self.nav_container)
        self.nav_layout = nav_layout
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(15) # 15px spațiu vertical între Cale și Butoane

        # 1. Path Label (Sus)
        lbl_path = QLabel("Select a folder from menu")
        self.lbl_path = lbl_path
        lbl_path.setFixedHeight(30)
        lbl_path.setStyleSheet("""
            QLabel {
                background-color: %s;
                color: %s;
                border-radius: 15px;
                padding: 0 15px;
                font-weight: 500;
                border: 1px solid %s;
            }
            QLabel:hover {
                background-color: %s;
            }
        """ % (soft_bg, fg, soft_border, hover_bg))
        nav_layout.addWidget(lbl_path, 0, Qt.AlignmentFlag.AlignLeft)

        # 2. Controls Row (Jos: Back + Play + Shuffle)
        controls_container = QWidget()
        controls_row = QHBoxLayout(controls_container)
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(10)

        btn_back = QPushButton()
        # Iconiță Back (Arrow Down din playlist)
        back_icon_path = os.path.join(self.icons_dir, "playlist", "arrow-down-solid-full.svg")
        icon = IconHelper.get_colored_icon(back_icon_path, icon_color, size=self.mini_icon_size)
        if not icon.isNull():
            btn_back.setIcon(icon)
            btn_back.setIconSize(QSize(self.mini_icon_size, self.mini_icon_size))

        # Stil "Pastilă" (fără text, doar icon)
        btn_back.setFixedSize(60, 30)
        btn_back.setFixedSize(40, 30)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton {
                background-color: %s; 
                color: %s; 
                border-radius: 15px; 
                font-size: 12px;
                font-weight: bold;
                border: 1px solid %s;
            }
            QPushButton:hover { background-color: %s; }
        """ % (soft_bg, fg, soft_border, hover_bg))
        btn_back.hide() 

        # --- Butoane Noi: Play & Shuffle ---
        self.btn_play_folder = QPushButton("")
        self.btn_shuffle_folder = QPushButton("")
        
        # Iconițe pentru butoane noi
        for btn, icon_name in [(self.btn_play_folder, "play-solid-full.svg"), (self.btn_shuffle_folder, "shuffle-solid-full.svg")]:
            icon_path = os.path.join(self.icons_dir, "player", icon_name)
            icon = IconHelper.get_colored_icon(icon_path, icon_color, size=self.mini_icon_size)
            if not icon.isNull():
                btn.setIcon(icon)
                btn.setIconSize(QSize(self.mini_icon_size, self.mini_icon_size))

        # Stil comun
        common_style = """ 
            QPushButton {
                background-color: %s; 
                color: %s; 
                border-radius: 15px; 
                font-size: 12px;
                font-weight: bold;
                border: 1px solid %s;
            }
            QPushButton:hover { background-color: %s; }
        """ % (soft_bg, fg, soft_border, hover_bg)
        
        self.btn_play_folder.setStyleSheet(common_style)
        self.btn_play_folder.setFixedSize(60, 30)
        self.btn_play_folder.setFixedSize(40, 30)
        self.btn_play_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play_folder.hide()

        self.btn_shuffle_folder.setStyleSheet(common_style)
        self.btn_shuffle_folder.setFixedSize(60, 30)
        self.btn_shuffle_folder.setFixedSize(40, 30)
        self.btn_shuffle_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_shuffle_folder.hide()

        controls_row.addWidget(btn_back)
        controls_row.addWidget(self.btn_play_folder)
        controls_row.addWidget(self.btn_shuffle_folder)
        controls_row.addStretch()

        nav_layout.addWidget(controls_container)
        
        main_vbox.addWidget(self.nav_container)
        
        container_layout.addWidget(self.header, 0, Qt.AlignmentFlag.AlignTop)
        parent_layout.addWidget(self.header_container)
        
        return search_bar, act_sel_folder, act_rescan, btn_back, lbl_path, self.nav_container, menu_btn, self.btn_play_folder, self.btn_shuffle_folder

    def apply_zoom(self, factor):
        self.current_zoom = max(0.6, float(factor))
        self.mini_icon_size = max(12, int(16 * self.current_zoom))
        self.search_icon_size = max(14, int(18 * self.current_zoom))
        self.menu_icon_size = max(18, int(30 * self.current_zoom))
        self.search_collapsed_width = max(36, int(40 * self.current_zoom))
        self.search_expanded_width = max(self.search_collapsed_width, int(300 * self.current_zoom))

        margin = max(10, int(15 * self.current_zoom))
        spacing = max(8, int(10 * self.current_zoom))
        if hasattr(self, 'header_main_layout'):
            self.header_main_layout.setContentsMargins(margin, margin, margin, margin)
            self.header_main_layout.setSpacing(spacing)

        search_size = self.search_collapsed_width
        if hasattr(self, 'search_frame'):
            expanded = self.search_frame.maximumWidth() > self.search_collapsed_width + 5
            self.search_frame.setFixedHeight(search_size)
            self.search_frame.setMinimumWidth(self.search_collapsed_width)
            self.search_frame.setMaximumWidth(self.search_expanded_width if expanded else self.search_collapsed_width)
        if hasattr(self, 'btn_search'):
            self.btn_search.setFixedSize(search_size, search_size)
        if hasattr(self, 'menu_btn'):
            self.menu_btn.setFixedSize(search_size, search_size)
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setFixedHeight(max(4, int(4 * self.current_zoom)))
        if hasattr(self, 'lbl_path'):
            self.lbl_path.setFixedHeight(max(30, int(30 * self.current_zoom)))
        if hasattr(self, 'nav_layout'):
            self.nav_layout.setSpacing(max(10, int(15 * self.current_zoom)))

        control_w = max(40, int(40 * self.current_zoom))
        control_h = max(30, int(30 * self.current_zoom))
        for attr in ('btn_back', 'btn_play_folder', 'btn_shuffle_folder', 'page2_play_btn', 'page2_shuffle_btn'):
            btn = getattr(self, attr, None)
            if btn:
                btn.setFixedSize(control_w, control_h)

        if hasattr(self, 'page2_back_btn'):
            circle = max(40, int(40 * self.current_zoom))
            self.page2_back_btn.setFixedSize(circle, circle)
        if hasattr(self, 'page2_icon_lbl'):
            icon_box = max(48, int(64 * self.current_zoom))
            self.page2_icon_lbl.setFixedSize(icon_box, icon_box)
            self._refresh_page2_icon_pixmap(icon_box)

    def _set_control_icon(self, btn, relative_path, color_hex, size, fallback_text=""):
        icon_path = os.path.join(self.icons_dir, *relative_path.split('/'))
        icon = IconHelper.get_colored_icon(icon_path, color_hex, size=size)
        if not icon.isNull():
            btn.setIcon(icon)
            btn.setIconSize(QSize(size, size))
            if fallback_text:
                btn.setText("")
        elif fallback_text:
            btn.setText(fallback_text)

    def update_theme_colors(self, colors):
        """ Actualizează culorile componentelor din UI """
        icon_color = colors.get("ICON_COLOR", "#AAAAAA")
        fg = colors.get("FG", "#FFFFFF")
        menu_bg = colors.get("MENU_BG", "#252525")
        border = colors.get("BORDER", "#333333")
        primary = colors.get("PRIMARY", "#00AAFF")
        soft_bg = self._rgba(menu_bg, 0.72)
        hover_bg = self._rgba(menu_bg, 0.9)
        soft_border = self._rgba(border, 0.22)
        search_radius = self.btn_search.height() // 2 if hasattr(self, 'btn_search') else 20
        menu_radius = self.menu_btn.height() // 2 if hasattr(self, 'menu_btn') else 20
        # Nu mai avem nevoie să setăm culoarea măștii manual, containerul folosește setMask
        if hasattr(self, 'search_frame'):
            self.search_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {soft_bg};
                    border-radius: {search_radius}px;
                    border: 1px solid {soft_border};
                }}
                QFrame:hover {{
                    background-color: {hover_bg};
                }}
            """)
        if hasattr(self, 'btn_search'):
            self.btn_search.setStyleSheet(f"background: transparent; border: none; border-radius: {search_radius}px;")
            self._set_button_icon(self.btn_search, "playlist/magnifying-glass-solid-full.svg", icon_color, size=self.search_icon_size)
        if hasattr(self, 'search_bar_input'):
            self.search_bar_input.setStyleSheet(f"""
                QLineEdit {{
                    background: transparent;
                    border: none;
                    color: {fg};
                    font-size: 15px;
                    margin-left: 5px;
                }}
            """)
        if hasattr(self, 'parent') and hasattr(self.parent, 'menu_btn'):
            self._set_button_icon(self.parent.menu_btn, "playlist/menu-circle-dots.svg", icon_color, size=self.menu_icon_size)
        if hasattr(self, 'menu_btn'):
            self.menu_btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: {soft_bg};
                    color: {fg};
                    border: 1px solid {soft_border};
                    border-radius: {menu_radius}px;
                    padding: 0px;
                }}
                QToolButton::menu-indicator {{ image: none; }}
                QToolButton:hover {{ background-color: {hover_bg}; }}
            """)
            self._set_button_icon(self.menu_btn, "playlist/menu-circle-dots.svg", icon_color, size=self.menu_icon_size)
        if hasattr(self, 'main_menu'):
            self.main_menu.setStyleSheet(
                f"QMenu {{ background: {menu_bg}; color: {fg}; border: 1px solid {self._rgba(border, 0.5)}; }}"
            )
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setStyleSheet(
                f"QProgressBar {{ border: none; background: {self._rgba(border, 0.24)}; border-radius: 2px; }} "
                f"QProgressBar::chunk {{ background: {primary}; border-radius: 2px; }}"
            )

    def setup_dashboard(self, target_widget, callback_folders, callback_all_songs, callback_albums, callback_artists, callback_queue, callback_most_replayed=None):
        """ Dashboard cu butoane stil 'Pill' la hover """
        layout = QVBoxLayout()
        hover_bg = self._rgba(getattr(self.parent, 'current_menu_bg', '#252525') if self.parent else '#252525', 0.82)
        # Reducem marginea de sus la 5px (header-ul are deja 5px jos = 10px total)
        layout.setContentsMargins(20, 5, 20, 20) 
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.dashboard_buttons = [] # Resetăm lista la setup

        # Configurare: (Text, SVG_Name, Culoare, Emoji_Fallback)
        buttons_data = [
            ("Folders Hierarchy", "more_folders-solid-full.svg", "#7986CB", "📂"), # Indigo Soft
            ("All Songs", "music-solid-full.svg", "#64B5F6", "🎵"), # Blue Soft
            ("Albums", "disc-solid-full.svg", "#4DB6AC", "💿"), # Teal Soft
            ("Artists", "microphone-solid-full.svg", "#FFB74D", "🎤"), # Orange Soft
            ("Playlists", "layer-group-solid-full.svg", "#81C784", "📜"), # Green Soft
            ("Queue", "list-solid-full.svg", "#FFD54F", "⏳"), # Amber Soft
            ("Most Replayed", "fire-solid-full.svg", "#E57373", "🔥") # Red Soft
        ]

        for text, icon_name, color, emoji in buttons_data:
            btn = QPushButton(f"  {text}") 
            
            # Folosim noua funcție generalizată
            icon = self._create_dashboard_icon_wrapper(icon_name, color, emoji, size=64)
            
            # Stocăm datele pentru regenerare la Zoom
            btn.setProperty("dashboard_data", {
                "icon_name": icon_name,
                "color": color,
                "emoji": emoji
            })
            
            btn.setIcon(icon)
            btn.setIconSize(QSize(32, 32)) 
            btn.setFixedHeight(64) # Forțăm înălțimea pentru a păstra forma de pastilă
            
            # Margini curbate stânga-dreapta (32px)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    text-align: left;
                    padding-left: 15px;
                    padding-top: 15px;
                    padding-bottom: 15px;
                    border: none;
                    border-radius: 32px; 
                    font-size: 16px;
                    font-weight: bold;
                    outline: none; /* Elimină conturul de selecție la click */
                }
                QPushButton:hover {
                    background-color: %s;
                    border: none; /* Fără contur la hover, ca în Settings */
                }
                QPushButton:pressed {
                    background-color: #00AAFF;
                    color: black;
                    border: none;
                }
            """ % hover_bg)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus) # Previne rămânerea butonului "agățat" în focus
            
            if text == "Folders Hierarchy":
                btn.clicked.connect(callback_folders)
            elif text == "All Songs":
                btn.clicked.connect(callback_all_songs)
            elif text == "Albums":
                btn.clicked.connect(callback_albums)
            elif text == "Artists":
                btn.clicked.connect(callback_artists)
            elif text == "Queue":
                btn.clicked.connect(callback_queue)
            elif text == "Most Replayed" and callback_most_replayed:
                btn.clicked.connect(callback_most_replayed)
            else:
                pass # Alte butoane (ex: Playlists) rămân inactive momentan
                
            self.dashboard_buttons.append(btn)
            layout.addWidget(btn)
        
        target_widget.setLayout(layout)

    def setup_browser_list(self, target_widget, item_clicked_callback):
        """ Lista de fișiere cu elemente rotunjite """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        file_list = SmoothListWidget()
        file_list.setMinimumHeight(100) # 🔥 Asigurăm că lista nu dispare complet
        file_list.setSpacing(0)  # Eliminăm complet "zona moartă" dintre piese
        file_list.setFrameShape(QFrame.Shape.NoFrame)
        file_list.setLineWidth(0)
        file_list.setMidLineWidth(0)
        file_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        file_list.viewport().setStyleSheet("background: transparent; border: none;")
        
        # 🔥 Elements rotunjite (15px) + Padding
        file_list.setStyleSheet("""
            SmoothListWidget,
            QListView { 
                background: transparent; 
                border: none; 
                outline: 0;
                padding: 0;
            }
            SmoothListWidget:focus,
            QListView:focus {
                border: none;
                outline: 0;
            }
            SmoothListWidget::item,
            QListView::item { 
                border: none; 
                padding: 2px;
                border-radius: 15px; 
            }
            SmoothListWidget::item:hover,
            QListView::item:hover { 
                background-color: #2a2a2a; 
                border-radius: 15px; 
                border: none;
            }
            SmoothListWidget::item:selected,
            QListView::item:selected { 
                background-color: #333; 
                border-radius: 15px; 
                border: none;
            }
        """)
        
        file_list.itemClicked.connect(item_clicked_callback)
        
        layout.addWidget(file_list)
        target_widget.setLayout(layout)
        return file_list

    def setup_page2_header_widget(self, target_layout, back_callback):
        """ Creează titlul special pentru Pagina 2 (Folders Hierarchy Root) """
        icon_color = getattr(self.parent, 'current_icon_color', '#AAAAAA') if self.parent else '#AAAAAA'
        fg = getattr(self.parent, 'current_fg_color', '#FFFFFF') if self.parent else '#FFFFFF'
        menu_bg = getattr(self.parent, 'current_menu_bg', '#252525') if self.parent else '#252525'
        border = getattr(self.parent, 'current_border_color', '#333333') if self.parent else '#333333'
        soft_bg = self._rgba(menu_bg, 0.72)
        hover_bg = self._rgba(menu_bg, 0.9)
        soft_border = self._rgba(border, 0.22)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 20, 10, 20)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # 1. Buton Back (Mic, discret)
        self.page2_back_btn = QPushButton()
        back_icon_path = os.path.join(self.icons_dir, "playlist", "arrow-down-solid-full.svg")
        icon = IconHelper.get_colored_icon(back_icon_path, getattr(self.parent, 'current_icon_color', '#AAAAAA') if self.parent else '#AAAAAA', size=self.mini_icon_size)
        if not icon.isNull():
            self.page2_back_btn.setIcon(icon)
            self.page2_back_btn.setIconSize(QSize(self.mini_icon_size, self.mini_icon_size))
        
        self.page2_back_btn.setFixedSize(40, 40)
        self.page2_back_btn.setStyleSheet(
            "QPushButton { background-color: %s; border-radius: 20px; border: 1px solid %s; } QPushButton:hover { background-color: %s; }"
            % (soft_bg, soft_border, hover_bg)
        )
        self.page2_back_btn.clicked.connect(back_callback)
        
        # 2. Iconița (Cerc Mov - exact ca în Dashboard)
        # Inițializăm cu Folders Hierarchy, dar va fi actualizat dinamic
        self.page2_icon_lbl = QLabel()
        self.page2_icon_lbl.setProperty("page2_icon_data", {
            "icon_name": "more_folders-solid-full.svg",
            "color": "#7986CB",
            "emoji": "📂",
        })
        self._refresh_page2_icon_pixmap(64)
        
        # 3. Text Titlu
        self.page2_title_lbl = QLabel("Folders Hierarchy")
        self.page2_title_lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {fg};")
        
        # --- Butoane Play & Shuffle (Pagina 2) ---
        self.page2_play_btn = QPushButton()
        self.page2_shuffle_btn = QPushButton()
        
        common_style = """
            QPushButton {
                background-color: %s; 
                color: %s; 
                border-radius: 15px; 
                font-size: 12px;
                font-weight: bold;
                border: 1px solid %s;
            }
            QPushButton:hover { background-color: %s; }
        """ % (soft_bg, fg, soft_border, hover_bg)
        
        for btn, icon_name in [(self.page2_play_btn, "play-solid-full.svg"), (self.page2_shuffle_btn, "shuffle-solid-full.svg")]:
            btn.setStyleSheet(common_style)
            btn.setFixedSize(40, 30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            icon_path = os.path.join(self.icons_dir, "player", icon_name)
            icon = IconHelper.get_colored_icon(icon_path, icon_color, size=self.mini_icon_size)
            if not icon.isNull():
                btn.setIcon(icon)
                btn.setIconSize(QSize(self.mini_icon_size, self.mini_icon_size))

        layout.addWidget(self.page2_back_btn)
        layout.addWidget(self.page2_icon_lbl)
        layout.addWidget(self.page2_title_lbl)
        
        layout.addSpacing(15)
        layout.addWidget(self.page2_play_btn)
        layout.addWidget(self.page2_shuffle_btn)
        
        target_layout.insertWidget(0, container) # Îl punem primul în layout
        return container

    def update_page2_header(self, title, icon_name, color_hex, emoji_fallback):
        """ Actualizează titlul și iconița header-ului special (Pagina 2) """
        self.page2_title_lbl.setText(title)
        self.page2_icon_lbl.setProperty("page2_icon_data", {
            "icon_name": icon_name,
            "color": color_hex,
            "emoji": emoji_fallback,
        })
        self._refresh_page2_icon_pixmap(self.page2_icon_lbl.width() or 64)

    def _refresh_page2_icon_pixmap(self, size=64):
        if not hasattr(self, 'page2_icon_lbl'):
            return
        data = self.page2_icon_lbl.property("page2_icon_data") or {}
        icon = self._create_dashboard_icon_wrapper(
            data.get("icon_name"),
            data.get("color", "#7986CB"),
            data.get("emoji", "📂"),
            size=max(1, int(size)),
        )
        self.page2_icon_lbl.setPixmap(icon.pixmap(size, size))

    def _create_dashboard_icon_wrapper(self, icon_name, color_hex, emoji_fallback, size=64):
        """ Wrapper care rezolvă calea iconiței și apelează IconHelper """
        icon_path = None
        if icon_name:
            paths = [
                os.path.join(self.icons_dir, icon_name),
                os.path.join(self.icons_dir, "playlist", icon_name)
            ]
            for p in paths:
                if os.path.exists(p):
                    icon_path = p
                    break
        
        return IconHelper.create_dashboard_icon(icon_path, color_hex, size, emoji_fallback)


    def _set_button_icon(self, btn, filename, color_hex, size=30):
        self._set_control_icon(btn, filename, color_hex, size, fallback_text="☰")
