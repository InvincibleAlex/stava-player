import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QSizePolicy, QApplication, QGridLayout, QFrame, QStackedWidget, QGraphicsOpacityEffect, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QImage, QLinearGradient, QTransform, QAction

# Importuri Widget-uri Custom
from player.player_widgets import (SquareFrame, RoundedArtLabel, ClickThroughContainer, 
                                   DummyWaveformWidget, MultiStateButton, ClickableLabel)
from core.utils import IconHelper
import core.themes as themes

# Noile importuri din fișiere separate
from player.scrolling_label import ScrollingLabel
from player.lyrics_widget import LyricsSlidingWidget
from player.player_layout import PlayerLayoutManager

try:
    from ui.waveform import WaveformWidget
except ImportError:
    WaveformWidget = DummyWaveformWidget

class PlayerTab(QWidget):
    play_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    shuffle_state_changed = pyqtSignal(int)
    repeat_state_changed = pyqtSignal(int)
    seek_requested = pyqtSignal(float) 
    path_clicked = pyqtSignal() # 🔥 SEMNAL NOU
    switch_to_player_requested = pyqtSignal() # 🔥 Semnal pentru trecerea la Full Player

    def __init__(self, audio_engine):
        super().__init__()
        self.audio = audio_engine
        
        # --- CONFIGURARE CALE ICONIȚE ---
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.icons_player_dir = os.path.join(base_dir, 'icons', 'player')
        
        if not os.path.exists(self.icons_player_dir):
             self.icons_player_dir = os.path.join(base_dir, 'icons')

        self.is_playing = False # Stare internă pentru iconița Play/Pause
        self.setStyleSheet("background-color: transparent; border: none;")
        
        self.current_colors = {
            "PRIMARY": "#00FF00", "SECONDARY": "#333333",
            "FG": "#FFFFFF", "TEXT_PRIMARY": "#FFFFFF", "TEXT_SECONDARY": "#AAAAAA",
            "BACKGROUND": "transparent"
        }
        self.current_icon_color = "#888888"
        self.current_transport_icon_color = "#FFFFFF"
        self.global_zoom = 1.0 # Factor de zoom implicit

        self.current_mode = None
        self.current_pill_bg = "rgba(0, 0, 0, 0.2)"
        self.button_pills = []
        self.lyrics_visible = False
        self.current_artwork_pixmap = None

        self.create_widgets()
        
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.main_layout)
        
        self.content_widget = QWidget()
        self.main_layout.addWidget(self.content_widget)
        
        # Inițializăm layout-ul
        self.set_mode_full()

        # --- HOVER LOGIC FOR LYRICS BUTTON ---
        self.btn_lyrics.setCheckable(True) # 🔥 Reactivat toggle vizual
        self.btn_lyrics.clicked.connect(self.on_lyrics_clicked) # 🔥 Reactivat funcție
        self.btn_lyrics.hide() # Ascundem butonul implicit
        
        # --- ANIMATION SETUP ---
        self.lyrics_opacity = QGraphicsOpacityEffect(self.btn_lyrics)
        self.lyrics_opacity.setOpacity(0.0)
        self.btn_lyrics.setGraphicsEffect(self.lyrics_opacity)
        
        self.lyrics_anim = QPropertyAnimation(self.lyrics_opacity, b"opacity")
        self.lyrics_anim.setDuration(200) # 200ms Fade
        self.lyrics_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        # Asigurăm că art_frame primește evenimente de mouse pentru a detecta enter/leave
        self.artwork_container.setMouseTracking(True) 
        self.artwork_container.enterEvent = self.on_art_enter
        self.artwork_container.leaveEvent = self.on_art_leave

    def _get_icon(self, name):
        # Folosim IconHelper, deci returnăm calea completă
        p = os.path.join(self.icons_player_dir, name)
        if not os.path.exists(p):
             base_dir = os.path.dirname(self.icons_player_dir)
             p = os.path.join(base_dir, name)
        return p

    def create_widgets(self):
        # 1. Container principal pentru Artwork + Lyrics
        self.artwork_container = SquareFrame()
        art_l = QGridLayout(self.artwork_container)
        art_l.setContentsMargins(0,0,0,0)
        
        # 🔥 FOLOSIM NOUL WIDGET SIMPLIFICAT PENTRU ARTWORK + LYRICS
        self.lyrics_view = LyricsSlidingWidget()
        self.lyrics_view.seek_requested.connect(self.seek_requested.emit) # 🔥 CONECTARE SEEK
        self.lyrics_view.toggle_requested.connect(self.on_lyrics_gesture) # 🔥 CONECTARE GESTURI SCROLL
        art_l.addWidget(self.lyrics_view, 0, 0)
        
        # Alias pentru compatibilitate cu restul codului (lbl_art e acum în lyrics_view)
        self.lbl_art = self.lyrics_view.lbl_art

        # --- A. BUTOANE EXTRA (STÂNGA) ---
        vis_states = [
            {"icon": self._get_icon("audio-lines.svg"), "color_type": "FG"},
            {"icon": self._get_icon("audio-lines.svg"), "color_type": "PRIME"}
        ]
        self.btn_extra_1 = MultiStateButton(vis_states, size=24)
        self.btn_extra_1.state_changed.connect(self.toggle_waveform_mode)
        self._install_state_menu(
            self.btn_extra_1,
            [
                {"label": "Waveform", "icon": self._get_icon("audio-lines.svg"), "color_type": "FG"},
                {"label": "Visualizer", "icon": self._get_icon("audio-lines.svg"), "color_type": "PRIME"},
            ],
        )
        
        dummy_state2 = [{"icon": self._get_icon("2-solid-full.svg"), "color_type": "FG"}]
        self.btn_extra_2 = MultiStateButton(dummy_state2, size=24)

        # --- BUTON LYRICS (NOU) ---
        self.btn_lyrics = QPushButton()
        self.btn_lyrics.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 🔥 Elimină punctele de focus
        
        # Container pentru poziționare (Acum copil direct al artwork_container pentru a rămâne vizibil)
        self.lyrics_container = QWidget(self.artwork_container)
        self.lyrics_layout = QVBoxLayout(self.lyrics_container)
        self.lyrics_layout.setContentsMargins(0, 0, 0, 0) # Se va seta dinamic la zoom
        self.lyrics_layout.addWidget(self.btn_lyrics)
        # 🔥 FIX: Aliniem containerul în grid, astfel încât să nu ocupe tot spațiul și să blocheze mouse-ul
        art_l.addWidget(self.lyrics_container, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        # --- B. BUTOANE CONTROL (DREAPTA) ---
        repeat_states = [
            {"icon": self._get_icon("repeat-solid-full.svg"), "color_type": "FG"},
            {"icon": self._get_icon("repeat-solid-full.svg"), "color_type": "ICON_COLOR"},
            {"icon": self._get_icon("repeat-solid-full.svg"), "color_type": "PRIME"}
        ]
        self.btn_repeat = MultiStateButton(repeat_states, size=24)
        self.btn_repeat.state_changed.connect(self.repeat_state_changed.emit)
        self._install_state_menu(
            self.btn_repeat,
            [
                {"label": "Repeat Off", "icon": self._get_icon("repeat-solid-full.svg"), "color_type": "FG"},
                {"label": "Repeat One", "icon": self._get_icon("repeat-solid-full.svg"), "color_type": "ICON_COLOR"},
                {"label": "Repeat All", "icon": self._get_icon("repeat-solid-full.svg"), "color_type": "PRIME"},
            ],
        )

        shuffle_states = [
            {"icon": self._get_icon("shuffle-solid-full.svg"), "color_type": "ICON_COLOR"},
            {"icon": self._get_icon("shuffle-solid-full.svg"), "color_type": "FG"},
            {"icon": self._get_icon("shuffle-solid-full.svg"), "color_type": "PRIME"}
        ]
        self.btn_shuffle = MultiStateButton(shuffle_states, size=24)
        self.btn_shuffle.state_changed.connect(self.shuffle_state_changed.emit)
        self._install_state_menu(
            self.btn_shuffle,
            [
                {"label": "Shuffle Off", "icon": self._get_icon("shuffle-solid-full.svg"), "color_type": "ICON_COLOR"},
                {"label": "Shuffle On", "icon": self._get_icon("shuffle-solid-full.svg"), "color_type": "FG"},
                {"label": "Shuffle Accent", "icon": self._get_icon("shuffle-solid-full.svg"), "color_type": "PRIME"},
            ],
        )

        # --- C. TRANSPORT ---
        self.btn_prev = QPushButton()
        self.btn_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 🔥 Elimină punctele de focus
        self.btn_prev.clicked.connect(self.prev_clicked.emit)
        
        self.btn_play = QPushButton()
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 🔥 Elimină punctele de focus
        self.btn_play.clicked.connect(self.play_clicked.emit)
        
        self.btn_next = QPushButton()
        self.btn_next.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 🔥 Elimină punctele de focus
        self.btn_next.clicked.connect(self.next_clicked.emit)

        # --- E. INFO PILLS (Titlu & Artist Separate) ---
        # 1. Title Pill
        self.title_pill = QFrame()
        sp_title = QSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        sp_title.setRetainSizeWhenHidden(True) # 🔥 FIX: Rezervă spațiul când e ascuns
        self.title_pill.setSizePolicy(sp_title)
        
        tp_layout = QVBoxLayout(self.title_pill)
        tp_layout.setContentsMargins(10, 0, 10, 0)
        tp_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        self.lbl_title = ScrollingLabel("STAVA Player") # 🔥 FOLOSIM SCROLLING LABEL
        # 🔥 FIX: Folosim Minimum pentru a forța layout-ul să respecte lățimea textului (până la max)
        sp_lbl = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        sp_lbl.setRetainSizeWhenHidden(True) # 🔥 FIX: Și textul își păstrează locul
        self.lbl_title.setSizePolicy(sp_lbl)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        tp_layout.addWidget(self.lbl_title)

        # 2. Artist Pill
        self.artist_pill = QFrame()
        sp_artist = QSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        sp_artist.setRetainSizeWhenHidden(True) # 🔥 FIX
        self.artist_pill.setSizePolicy(sp_artist)
        
        ap_layout = QVBoxLayout(self.artist_pill)
        ap_layout.setContentsMargins(10, 0, 10, 0)
        ap_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.lbl_artist = QLabel("Welcome")
        self.lbl_artist.setSizePolicy(sp_lbl) # Refolosim politica
        self.lbl_artist.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ap_layout.addWidget(self.lbl_artist)

        # 3. Path Pill (Sub Waveform)
        self.path_pill = QFrame()
        self.path_pill.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.path_pill.setFixedHeight(24)
        # Stilul va fi setat în update_theme_colors
        
        pp_layout = QHBoxLayout(self.path_pill)
        pp_layout.setContentsMargins(10, 0, 10, 0)
        pp_layout.setSpacing(5)
        pp_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_path_icon = QLabel()
        self.lbl_path_icon.setFixedSize(12, 12)
        self.lbl_path_icon.setStyleSheet("background: transparent; border: none;")
        
        self.lbl_path_text = ClickableLabel("No File") # 🔥 Folosim ClickableLabel
        self.lbl_path_text.setStyleSheet("font-size: 10px; font-weight: bold; color: #AAAAAA; background: transparent; border: none;")
        self.lbl_path_text.clicked.connect(self.path_clicked.emit) # 🔥 Conectăm click-ul
        
        pp_layout.addWidget(self.lbl_path_icon)
        pp_layout.addWidget(self.lbl_path_text)

        # --- D. WAVEFORM ---
        self.waveform = WaveformWidget(self.audio)
        self.waveform.setMinimumHeight(100) 
        self.waveform.seek_request.connect(self.seek_requested.emit)

        self.lbl_current_time = QLabel("00:00")
        self.lbl_total_time = QLabel("00:00")
        
        self.update_theme_colors(self.current_colors, self.current_icon_color)

    def update_theme_colors(self, colors, icon_color_hex="#CCCCCC"):
        self.current_colors = colors
        self.current_icon_color = icon_color_hex
        self.current_transport_icon_color = colors.get("FG", icon_color_hex or "#FFFFFF")

        # 🔥 FIX: Forțăm fundal transparent pentru Waveform, altfel ia culoarea temei (ex: #121212)
        wave_colors = colors.copy()
        wave_colors["BACKGROUND"] = "transparent"
        self.waveform.set_theme_colors(wave_colors)
        
        self.btn_extra_1.set_theme_data(colors, icon_color_hex)
        self.btn_extra_2.set_theme_data(colors, icon_color_hex)
        self.btn_repeat.set_theme_data(colors, icon_color_hex)
        self.btn_shuffle.set_theme_data(colors, icon_color_hex)
        
        # Update Lyrics Colors
        self.lyrics_view.update_theme_colors(colors)
        
        # --- UPDATE LYRICS ICON (Rotit 90 grade) ---
        # Construim calea către iconița din playlist
        base_icons_dir = os.path.dirname(self.icons_player_dir) # .../icons
        lyrics_icon_path = os.path.join(base_icons_dir, 'audio-lines.svg')
        
        # 1. Obținem iconița colorată standard
        icon_raw = IconHelper.get_colored_icon(lyrics_icon_path, icon_color_hex)
        if not icon_raw.isNull():
            # 2. Extragem Pixmap, Rotim și Setăm
            pix = icon_raw.pixmap(QSize(64, 64)) # Rezoluție bună pentru scalare
            transform = QTransform().rotate(90)
            rotated_pix = pix.transformed(transform, Qt.TransformationMode.SmoothTransformation)
            self.btn_lyrics.setIcon(QIcon(rotated_pix))

        # Update Info Pill Colors
        fg_color = colors.get("FG", "#FFFFFF")
        sec_color = colors.get("TEXT_SECONDARY", "#AAAAAA")
        
        self.lbl_title.setStyleSheet(themes.get_label_style(14, fg_color, True))
        self.lbl_artist.setStyleSheet(themes.get_label_style(11, sec_color))
        
        # --- PILL COLORS (MENU_BG with Alpha) ---
        menu_bg = colors.get("MENU_BG", "#252525")
        c = QColor(menu_bg)
        c.setAlphaF(0.2)
        self.current_pill_bg = f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alphaF()})"
        
        self.path_pill.setStyleSheet(themes.get_pill_style(self.current_pill_bg, 12))
        for pill in self.button_pills:
            pill.setStyleSheet(themes.get_pill_style(self.current_pill_bg, 17))

        # Path Pill Colors
        self.lbl_path_text.setStyleSheet(themes.get_label_style(10, sec_color, True))
        self._set_label_icon(self.lbl_path_icon, "folder-solid-full.svg", sec_color)
        
        # Actualizăm iconițele de transport după tema activă
        self._set_icon_colored(self.btn_prev, "backward-solid-full.svg", self.current_transport_icon_color)
        self._set_icon_colored(self.btn_next, "forward-solid-full.svg", self.current_transport_icon_color)
        self._update_play_icon(self.current_transport_icon_color)
        
        self._update_dynamic_sizes()

    def set_zoom_factor(self, factor):
        self.global_zoom = factor
        self._update_dynamic_sizes()

    def _set_icon_colored(self, btn, filename, color_hex):
        # Folosim IconHelper
        icon = IconHelper.get_colored_icon(self._get_icon(filename), color_hex)
        btn.setIcon(icon)

    def _set_label_icon(self, label, filename, color_hex):
        # Folosim IconHelper și extragem pixmap-ul
        icon = IconHelper.get_colored_icon(self._get_icon(filename), color_hex, size=label.height())
        if not icon.isNull():
            label.setPixmap(icon.pixmap(label.size()))

    def _rgba(self, color_hex, alpha):
        color = QColor(color_hex)
        color.setAlphaF(max(0.0, min(1.0, alpha)))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alphaF()})"

    def _install_state_menu(self, button, items):
        button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos, b=button, i=items: self._show_state_menu(b, i))

    def _show_state_menu(self, button, items):
        if not button or not items:
            return

        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        menu.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        menu.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        menu.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)

        for index, item in enumerate(items[:len(button.states)]):
            action = QAction(item.get("label", f"Mode {index + 1}"), menu)
            icon = self._state_menu_icon(item)
            if not icon.isNull():
                action.setIcon(icon)
            action.setCheckable(True)
            action.setChecked(index == button.current_index)
            action.triggered.connect(lambda checked=False, i=index, b=button: self._set_button_state_from_menu(b, i))
            menu.addAction(action)

        menu.setStyleSheet(self._state_menu_stylesheet())
        menu.ensurePolished()
        size = menu.sizeHint()
        anchor = button.mapToGlobal(QPoint(button.width() // 2, button.height() + 6))
        menu.popup(QPoint(anchor.x() - size.width() // 2, anchor.y()))

    def _set_button_state_from_menu(self, button, index):
        if button:
            button.set_state(index)

    def _state_menu_icon(self, item):
        icon_path = item.get("icon", "")
        if not icon_path:
            return QIcon()

        color_type = item.get("color_type", "FG")
        if color_type == "ICON_COLOR":
            color = self.current_icon_color
        elif color_type == "PRIME":
            color = self.current_colors.get("PRIMARY", "#00AAFF")
        else:
            color = self.current_colors.get("FG", "#FFFFFF")

        return IconHelper.get_colored_icon(icon_path, color, size=max(18, int(20 * self.global_zoom)))

    def _state_menu_stylesheet(self):
        menu_bg = self.current_colors.get("MENU_BG", "#252525")
        border = self.current_colors.get("BORDER", "#333333")
        fg = self.current_colors.get("FG", "#FFFFFF")
        primary = self.current_colors.get("PRIMARY", "#00AAFF")
        bg = self._rgba(menu_bg, 0.82)
        hover_bg = self._rgba(menu_bg, 0.94)
        border_rgba = self._rgba(border, 0.55)
        checked_bg = self._rgba(primary, 0.22)

        return f"""
            QMenu {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border_rgba};
                border-radius: 12px;
                padding: 6px;
                margin: 0px;
            }}
            QMenu::item {{
                padding: 7px 10px 7px 8px;
                border-radius: 8px;
                background: transparent;
            }}
            QMenu::icon {{
                padding-left: 2px;
                padding-right: 6px;
            }}
            QMenu::item:selected {{
                background-color: {hover_bg};
            }}
            QMenu::item:checked {{
                background-color: {checked_bg};
                color: {fg};
            }}
            QMenu::indicator {{
                width: 0px;
                height: 0px;
            }}
        """

    def _update_play_icon(self, color_hex):
        # Alegem iconița în funcție de stare
        icon_name = "pause-solid-full.svg" if self.is_playing else "play-solid-full.svg"
        self._set_icon_colored(self.btn_play, icon_name, color_hex)

    def _non_art_transition_widgets(self):
        widgets = [
            self.title_pill,
            self.artist_pill,
            self.path_pill,
            self.waveform,
            self.btn_prev,
            self.btn_play,
            self.btn_next,
        ]
        widgets.extend(getattr(self, "button_pills", []))

        result = []
        seen = set()
        for widget in widgets:
            if widget and id(widget) not in seen:
                seen.add(id(widget))
                result.append(widget)
        return result

    def set_non_art_controls_opacity(self, opacity):
        if hasattr(self, "_non_art_fade_group") and self._non_art_fade_group:
            if self._non_art_fade_group.state() == QParallelAnimationGroup.State.Running:
                self._non_art_fade_group.stop()
        self._non_art_effect_targets = []

        for widget in self._non_art_transition_widgets():
            effect = widget.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(effect)
            effect.setOpacity(opacity)
            self._non_art_effect_targets.append(widget)

    def fade_non_art_controls_in(self, delay_ms=70, duration_ms=180):
        widgets = self._non_art_transition_widgets()
        if not widgets:
            return

        def start():
            self._non_art_fade_group = QParallelAnimationGroup(self)
            targets = []
            for widget in widgets:
                if not widget:
                    continue
                effect = widget.graphicsEffect()
                if not isinstance(effect, QGraphicsOpacityEffect):
                    effect = QGraphicsOpacityEffect(widget)
                    effect.setOpacity(0.0)
                    widget.setGraphicsEffect(effect)
                anim = QPropertyAnimation(effect, b"opacity")
                anim.setDuration(duration_ms)
                anim.setStartValue(effect.opacity())
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.Type.OutQuad)
                self._non_art_fade_group.addAnimation(anim)
                targets.append(widget)

            def cleanup():
                for widget in targets:
                    try:
                        widget.setGraphicsEffect(None)
                    except Exception:
                        pass

            self._non_art_fade_group.finished.connect(cleanup)
            self._non_art_fade_group.start()

        QTimer.singleShot(max(0, int(delay_ms)), start)

    def fade_non_art_controls_out(self, on_finished=None, duration_ms=130):
        widgets = self._non_art_transition_widgets()
        if not widgets:
            if on_finished:
                on_finished()
            return

        if hasattr(self, "_non_art_fade_group") and self._non_art_fade_group:
            if self._non_art_fade_group.state() == QParallelAnimationGroup.State.Running:
                self._non_art_fade_group.stop()

        self._non_art_fade_group = QParallelAnimationGroup(self)
        for widget in widgets:
            effect = widget.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(widget)
                effect.setOpacity(1.0)
                widget.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity")
            anim.setDuration(duration_ms)
            anim.setStartValue(effect.opacity())
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self._non_art_fade_group.addAnimation(anim)

        if on_finished:
            self._non_art_fade_group.finished.connect(on_finished)
        self._non_art_fade_group.start()

    def rescue_widgets(self):
        widgets_to_save = [
            self.artwork_container, 
            self.btn_extra_1, self.btn_extra_2, self.btn_repeat, self.btn_shuffle,
            # self.btn_lyrics, # NU îl mai salvăm separat, este acum copil permanent al art_frame
            self.btn_prev, self.btn_play, self.btn_next,
            self.waveform, self.lbl_current_time, self.lbl_total_time,
            self.title_pill, self.artist_pill, self.path_pill
        ]
        for w in widgets_to_save: w.setParent(None)

    def _force_layout_refresh(self):
        """ 🔥 FIX: Forțează recalcularea geometriei pentru containerul de Artwork """
        if self.artwork_container:
            # Forțăm widget-ul să-și recalculeze aspect ratio
            self.artwork_container.updateGeometry()
            # Forțăm redesenarea
            self.artwork_container.repaint()
            
            # Opțional: Dacă tot face figuri, un resize +/- 1 pixel de obicei rezolvă orice glitch QT
            w = self.artwork_container.width()
            h = self.artwork_container.height()
            self.artwork_container.resize(w + 1, h)
            self.artwork_container.resize(w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Verificăm să nu intrăm peste NavBar (prin limitarea la înălțimea ferestrei)
        if self.current_mode == "FULL" and self.artwork_container:
            # Limităm lățimea maximă la înălțimea disponibilă (minus margini de aprox 80px)
            # Deoarece este SquareFrame, limitarea lățimii va limita automat și înălțimea,
            # prevenind overflow-ul vertical și suprapunerea cu elementele de jos.
            max_h = int((self.height() - 80) * max(0.9, min(1.15, self.global_zoom)))
            if max_h < 100: max_h = 100
            self.artwork_container.setMaximumWidth(max_h)
        
        # 🔥 FIX: Limităm lățimea titlului pentru a forța scroll-ul
        # Dacă nu limităm, "pastila" se va lăți la infinit.
        self.lbl_title.setMaximumWidth(int(self.width() * 0.8))

        # Poziționăm manual copiii containerului de artwork
        if hasattr(self, 'artwork_container'):
            w = self.artwork_container.width()
            h = self.artwork_container.height()

        self._update_dynamic_sizes()

    def _update_dynamic_sizes(self):
        # --- ZOOM PENTRU BUTOANE ---
        z = self.global_zoom

        if hasattr(self, 'waveform') and hasattr(self.waveform, 'set_zoom_factor'):
            self.waveform.set_zoom_factor(z)
            self.waveform.setMinimumHeight(max(80, int(100 * z)))
        if hasattr(self, 'lyrics_view') and hasattr(self.lyrics_view, 'set_zoom_factor'):
            self.lyrics_view.set_zoom_factor(z)

        if hasattr(self, 'artwork_container') and self.artwork_container:
            if self.current_mode == "FULL":
                self.artwork_container.setMinimumWidth(max(140, int(220 * z)))
                self.artwork_container.setMaximumWidth(max(220, int((self.height() - 80) * max(0.9, min(1.15, z)))))

                if hasattr(self, 'player_container') and self.player_container and self.player_container.layout():
                    full_layout = self.player_container.layout()
                    art_stretch = max(1, int(round(1 + (z - 1.0) * 2.0)))
                    full_layout.setStretch(0, art_stretch)
                    full_layout.setStretch(1, 1)

            elif self.current_mode == "MINI":
                self.artwork_container.setMinimumWidth(max(120, int(170 * z)))
                self.artwork_container.setMinimumHeight(max(120, int(170 * z)))

                if self.content_widget and self.content_widget.layout():
                    mini_layout = self.content_widget.layout()
                    art_stretch = max(1, int(round(2 + z)))
                    wave_stretch = max(1, int(round(3 - min(1.5, z))))
                    mini_layout.setStretch(0, art_stretch)
                    mini_layout.setStretch(3, wave_stretch)
        
        # 1. Transport Buttons (Play, Prev, Next)
        if self.current_mode == "FULL":
            play_s = int(90 * z)
            play_icon = int(36 * z)
            nav_s = int(60 * z)
            nav_icon = int(24 * z)
        else: # MINI
            play_s = int(70 * z)
            play_icon = int(28 * z)
            nav_s = int(50 * z)
            nav_icon = int(20 * z)

        menu_bg = self.current_colors.get("MENU_BG", "#252525")
        border = self.current_colors.get("BORDER", self.current_icon_color or "#555555")
        icon_tint = self.current_colors.get("ICON_COLOR", self.current_transport_icon_color)
        button_bg = self._rgba(menu_bg, 0.58)
        button_border = self._rgba(border, 0.72)
        button_hover_bg = self._rgba(menu_bg, 0.72)
        button_hover_border = self._rgba(icon_tint, 0.55)
        button_pressed_bg = self._rgba(menu_bg, 0.84)
            
        IconHelper.apply_round_button_style(
            self.btn_play,
            play_s,
            bg_color=button_bg,
            border_color=button_border,
            hover_bg_color=button_hover_bg,
            hover_border_color=button_hover_border,
            pressed_bg_color=button_pressed_bg,
        )
        self.btn_play.setIconSize(QSize(play_icon, play_icon))
        
        IconHelper.apply_round_button_style(
            self.btn_prev,
            nav_s,
            bg_color=button_bg,
            border_color=button_border,
            hover_bg_color=button_hover_bg,
            hover_border_color=button_hover_border,
            pressed_bg_color=button_pressed_bg,
        )
        self.btn_prev.setIconSize(QSize(nav_icon, nav_icon))
        
        IconHelper.apply_round_button_style(
            self.btn_next,
            nav_s,
            bg_color=button_bg,
            border_color=button_border,
            hover_bg_color=button_hover_bg,
            hover_border_color=button_hover_border,
            pressed_bg_color=button_pressed_bg,
        )
        self.btn_next.setIconSize(QSize(nav_icon, nav_icon))

        # 1.5 Lyrics Button (Cerc, stil similar cu transport dar mai mic)
        # Dimensiune similară cu înălțimea pastilelor (34px)
        lyrics_s = int(34 * z)
        radius = lyrics_s // 2
        primary = self.current_colors.get("PRIMARY", "#00AAFF")
        
        self.btn_lyrics.setFixedSize(lyrics_s, lyrics_s)
        self.btn_lyrics.setIconSize(QSize(int(18 * z), int(18 * z)))
        
        # Stil custom FĂRĂ BORDURĂ pentru a elimina punctele
        self.btn_lyrics.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 0, 0, 0.4);
                border-radius: {radius}px;
                border: none;
                outline: none;
            }}
            QPushButton:hover {{ background-color: rgba(0, 0, 0, 0.6); }}
            QPushButton:checked {{ background-color: {primary}; color: black; }}
        """)
        
        # Setăm marginea containerului (distanța față de colțul artwork-ului)
        margin = int(20 * z)
        self.lyrics_layout.setContentsMargins(0, 0, margin, margin)

        # 2. Control Pills (Shuffle, Repeat, Extras)
        # Base Pill Height: 34. Base Button Icon: 24.
        pill_h = int(34 * z)
        btn_size = int(24 * z)

        # 3. Path Pill (Zoom)
        path_h = int(24 * z)
        path_icon_s = int(12 * z)
        path_font = int(10 * z)
        
        self.path_pill.setFixedHeight(path_h)
        self.path_pill.setStyleSheet(themes.get_pill_style(self.current_pill_bg, path_h // 2))
        self.path_pill.layout().setContentsMargins(int(10 * z), 0, int(10 * z), 0)
        self.path_pill.layout().setSpacing(int(5 * z))
        
        self.lbl_path_icon.setFixedSize(path_icon_s, path_icon_s)
        sec_color = self.current_colors.get("TEXT_SECONDARY", "#AAAAAA")
        self.lbl_path_text.setStyleSheet(themes.get_label_style(path_font, sec_color, True))
        self._set_label_icon(self.lbl_path_icon, "folder-solid-full.svg", sec_color)

        if self.current_mode == "MINI":
            fg_color = self.current_colors.get("FG", "#FFFFFF")
            sec_color = self.current_colors.get("TEXT_SECONDARY", "#AAAAAA")
            
            # Aplicăm zoom și la textul din Mini Player
            t_size = int(14 * self.global_zoom)
            a_size = int(12 * self.global_zoom)
            
            self.lbl_title.setStyleSheet(themes.get_label_style(t_size, fg_color, True))
            self.lbl_artist.setStyleSheet(themes.get_label_style(a_size, sec_color))
            
            # Scalăm și pastilele (Pills)
            self.title_pill.setFixedHeight(int(30 * self.global_zoom))
            self.title_pill.setStyleSheet(themes.get_pill_style(self.current_pill_bg, int(15 * self.global_zoom)))
            
            self.artist_pill.setFixedHeight(int(26 * self.global_zoom))
            self.artist_pill.setStyleSheet(themes.get_pill_style(self.current_pill_bg, int(13 * self.global_zoom)))
            
            # Update Pills în Mini Mode
            for pill in self.button_pills:
                pill.setFixedHeight(pill_h)
                pill.setStyleSheet(themes.get_pill_style(self.current_pill_bg, pill_h // 2))
                if pill.layout().count() > 0:
                    w = pill.layout().itemAt(0).widget()
                    if isinstance(w, MultiStateButton):
                        w.resize_button(btn_size)
                        
            return

        if self.current_mode != "FULL": return
        
        w = self.width()
        # Definim intervalul de lățime pentru scalare (ex: 600px -> 1400px)
        factor = (w - 600) / 800
        factor = max(0.0, min(1.0, factor))
        
        # Title: Min 14 -> Max 42 (Triplu)
        t_size = (14 + (28 * factor)) * self.global_zoom
        # Artist: Min 11 -> Max 33 (Triplu)
        a_size = (11 + (22 * factor)) * self.global_zoom
        
        fg_color = self.current_colors.get("FG", "#FFFFFF")
        sec_color = self.current_colors.get("TEXT_SECONDARY", "#AAAAAA")
        
        self.lbl_title.setStyleSheet(themes.get_label_style(int(t_size), fg_color, True))
        self.lbl_artist.setStyleSheet(themes.get_label_style(int(a_size), sec_color))
        
        # Update Pills Height & Radius
        tp_h = int(t_size + 20 * self.global_zoom)
        self.title_pill.setFixedHeight(tp_h)
        self.title_pill.setStyleSheet(themes.get_pill_style(self.current_pill_bg, tp_h//2))
        
        ap_h = int(a_size + 16 * self.global_zoom)
        self.artist_pill.setFixedHeight(ap_h)
        self.artist_pill.setStyleSheet(themes.get_pill_style(self.current_pill_bg, ap_h//2))
        
        # Update Pills în Full Mode
        for pill in self.button_pills:
            pill.setFixedHeight(pill_h)
            pill.setStyleSheet(themes.get_pill_style(self.current_pill_bg, pill_h // 2))
            if pill.layout().count() > 0:
                w = pill.layout().itemAt(0).widget()
                if isinstance(w, MultiStateButton):
                    w.resize_button(btn_size)

    def _create_pill_widget(self, btn):
        """ Helper pentru a crea containerul tip 'pastilă' standardizat """
        pill = QFrame()
        pill.setFixedHeight(34)
        # Stilul inițial, va fi suprascris de update_theme_colors
        pill.setStyleSheet(themes.get_pill_style("rgba(0, 0, 0, 0.2)", 17))
        
        layout = QHBoxLayout(pill)
        layout.setContentsMargins(5, 0, 5, 0) # Padding-ul cerut (Pastilă)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn.setFixedSize(34, 24)
        layout.addWidget(btn)
        self.button_pills.append(pill)
        return pill

    def set_mode_full(self):
        if self.current_mode == "FULL": return
        self.setUpdatesEnabled(False)
        self.button_pills = [] # Reset pills list
        try:
            # Delegăm construcția layout-ului către managerul extern
            PlayerLayoutManager.setup_full_layout(self)
            self.current_mode = "FULL"
            self.update_theme_colors(self.current_colors, self.current_icon_color)
            self._force_layout_refresh()
            self._force_layout_refresh()
        finally:
            self.setUpdatesEnabled(True)

    def set_mode_mini(self, deferred_refresh=True):
        if self.current_mode == "MINI": return
        self.setUpdatesEnabled(False)
        self.button_pills = [] # Reset pills list
        self.player_container = None
        try:
            # 🔥 FIX: Resetăm starea versurilor la intrarea în Mini Mode
            # Vrem ca Mini Player să arate mereu Artwork-ul
            if hasattr(self, 'lyrics_view'):
                self.lyrics_view.set_lyrics_visible(False, animate=False)
            self.lyrics_visible = False
            self.btn_lyrics.setChecked(False)

            # Delegăm construcția layout-ului către managerul extern
            PlayerLayoutManager.setup_mini_layout(self)
            self.current_mode = "MINI"
            self.update_theme_colors(self.current_colors, self.current_icon_color)
            if deferred_refresh is None:
                pass
            elif deferred_refresh:
                QTimer.singleShot(10, self._force_layout_refresh)
            else:
                self._force_layout_refresh()
        finally:
            self.setUpdatesEnabled(True)

    def toggle_waveform_mode(self, state):
        mode = "visualizer" if state == 1 else "waveform"
        self.waveform.set_mode(mode)

    def on_lyrics_clicked(self, checked):
        """ Gestionează click-ul pe Lyrics în funcție de modul curent """
        if self.current_mode == "MINI":
            # Dacă suntem în Mini, anulăm starea vizuală momentan
            self.btn_lyrics.setChecked(False)
            
            # Cerem trecerea la Full Player
            self.switch_to_player_requested.emit()
            # Așteptăm tranziția (500ms) apoi activăm versurile
            QTimer.singleShot(500, self._trigger_lyrics_delayed)
        else:
            self.toggle_lyrics_view(checked)

    def on_lyrics_gesture(self, show):
        """ Apelat când se face scroll pe artwork/lyrics """
        # Actualizăm starea butonului doar dacă e diferită
        if self.btn_lyrics.isChecked() != show:
            self.btn_lyrics.setChecked(show)
            self.on_lyrics_clicked(show)

    def _trigger_lyrics_delayed(self):
        """ Activează versurile după ce tranziția s-a terminat """
        self.btn_lyrics.setChecked(True)
        self.toggle_lyrics_view(True)

    def toggle_lyrics_view(self, checked):
        """ Apelează animația din widget-ul dedicat """
        self.lyrics_visible = checked
        self.lyrics_view.set_lyrics_visible(checked)

    def set_lyrics(self, text):
        self.lyrics_view.set_lyrics(text)

    # --- HOVER EVENTS FOR ARTWORK ---
    def on_art_enter(self, event):
        """ Afișează butonul Lyrics la hover pe artwork. """
        self.lyrics_anim.stop()
        try: self.lyrics_anim.finished.disconnect()
        except: pass
        
        self.btn_lyrics.show()
        self.lyrics_anim.setStartValue(self.lyrics_opacity.opacity())
        self.lyrics_anim.setEndValue(1.0)
        self.lyrics_anim.start()
        
        QFrame.enterEvent(self.artwork_container, event) # Apelăm implementarea originală

    def on_art_leave(self, event):
        """ Reduce opacitatea butonului Lyrics la părăsirea artwork-ului. """
        self.lyrics_anim.stop()
        try: self.lyrics_anim.finished.disconnect()
        except: pass
        
        # Nu mai conectăm .hide(), butonul rămâne vizibil
        self.lyrics_anim.setStartValue(self.lyrics_opacity.opacity())
        self.lyrics_anim.setEndValue(0.25) # 🔥 Setăm opacitatea la 25%
        self.lyrics_anim.start()
        
        QFrame.leaveEvent(self.artwork_container, event) # Apelăm implementarea originală

    def set_playing_state(self, is_playing):
        self.is_playing = is_playing
        self._update_play_icon(self.current_transport_icon_color)
        
    def set_album_art(self, data):
        """ data poate fi: str (cale fișier), QImage, bytes sau None """
        img = None
        try:
            if isinstance(data, str) and os.path.exists(data):
                img = QImage(data)
            elif isinstance(data, QImage):
                img = data
            elif isinstance(data, (bytes, bytearray)):
                img = QImage.fromData(data)
            
            if img and not img.isNull():
                self.current_artwork_pixmap = QPixmap.fromImage(img)
                self.lbl_art.set_art(img)
                self.lbl_art.setText("")
                return
            
            # Fallback
            self.current_artwork_pixmap = None
            self.lbl_art.set_art(None)
            self.lbl_art.setText("🎵\nNo Art")
        except Exception: 
            self.current_artwork_pixmap = None
            self.lbl_art.set_art(None)
            self.lbl_art.setText("🎵\nNo Art")

    def set_track_info(self, title, artist, filepath=None):
        self.lbl_title.setText(title if title else "Unknown Title")
        self.lbl_artist.setText(artist if artist else "Unknown Artist")
        if filepath:
            self.lbl_path_text.setText(filepath)

    def update_timers(self, current, total=None):
        """ Actualizează etichetele de timp (format MM:SS) """
        def fmt(s):
            m = int(s // 60)
            sec = int(s % 60)
            return f"{m:02d}:{sec:02d}"

        current_sec = int(current)
        if getattr(self, '_last_current_sec', None) != current_sec:
            self.lbl_current_time.setText(fmt(current))
            self._last_current_sec = current_sec

        if total is not None and total > 0:
            total_sec = int(total)
            if getattr(self, '_last_total_sec', None) != total_sec:
                self.lbl_total_time.setText(fmt(total))
                self._last_total_sec = total_sec
            
        # 🔥 ACTUALIZARE VERSURI SINCRONIZATE
        if self.lyrics_visible:
            self.lyrics_view.update_position(current)
