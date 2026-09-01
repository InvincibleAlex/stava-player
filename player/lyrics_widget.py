import re
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QScroller, QGraphicsOpacityEffect, QScrollerProperties
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QBrush
from player.player_widgets import RoundedArtLabel
from player.lyrics_animations import AnimatedLyricLine

class LyricsSlidingWidget(QWidget):
    seek_requested = pyqtSignal(float) # Semnal pentru seek la click
    toggle_requested = pyqtSignal(bool) # 🔥 Semnal pentru gesturi (True=Show, False=Hide)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lyrics_visible = False
        self.slide_anim_group = None
        self.zoom_factor = 1.0
        
        self.active_color = "#00AAFF"
        self.inactive_color = "#FFFFFF"
        
        # 1. Artwork Label
        self.lbl_art = RoundedArtLabel(self)
        
        # 2. Lyrics Panel
        self.lyrics_panel = QWidget(self)
        # Fundal semi-transparent închis pentru lizibilitate
        self.lyrics_panel.setStyleSheet("background-color: transparent; border-radius: 10px;")
        
        # Revenim la QVBoxLayout simplu, nu mai avem nevoie de stack
        lyric_layout = QVBoxLayout(self.lyrics_panel)
        lyric_layout.setContentsMargins(0, 0, 0, 0)
        
        # Scroll Area pentru versuri lungi
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff) # 🔥 Scrollbar ascuns
        
        # 🔥 MASCĂ DE OPACITATE (Fade Out real prin transparență)
        self.opacity_effect = QGraphicsOpacityEffect(self.scroll_area)
        self.scroll_area.setGraphicsEffect(self.opacity_effect)
        
        # 🔥 FIX SCROLL: Activăm Kinetic Scrolling (Drag cu mouse-ul)
        try:
            QScroller.grabGesture(self.scroll_area.viewport(), QScroller.ScrollerGesture.LeftMouseButtonGesture)
            
            # 🌊 TUNE SCROLLER FOR SMOOTHNESS
            scroller = QScroller.scroller(self.scroll_area.viewport())
            props = scroller.scrollerProperties()
            
            # Decelerare mai lentă (0.85) = Alunecare mai lungă și fluidă
            props.setScrollMetric(QScrollerProperties.ScrollMetric.DecelerationFactor, 0.85)
            # Smoothing la input (reduce tremuratul mouse-ului)
            props.setScrollMetric(QScrollerProperties.ScrollMetric.DragVelocitySmoothingFactor, 0.6)
            # Overshoot (efect elastic la capete)
            props.setScrollMetric(QScrollerProperties.ScrollMetric.OvershootDragResistanceFactor, 0.3)
            
            scroller.setScrollerProperties(props)
            
            # 🔥 DETECTARE SCROLL MANUAL (Drag)
            scroller.stateChanged.connect(self._on_scroller_state_changed)
        except (AttributeError, ImportError):
            pass 
        
        # 🔥 EVENT FILTER: Pentru a detecta scroll-ul în sus când suntem la începutul listei
        self.scroll_area.viewport().installEventFilter(self)
        
        # 🔥 TIMER PENTRU REVENIRE LA AUTO-SCROLL
        self.user_is_scrolling = False
        self.auto_scroll_timer = QTimer(self)
        self.auto_scroll_timer.setSingleShot(True)
        self.auto_scroll_timer.setInterval(3000) # După 3 secunde de inactivitate, revenim la piesa curentă
        self.auto_scroll_timer.timeout.connect(self._resume_auto_scroll)

        # Container text
        self.text_container = QWidget()
        self.text_container.setStyleSheet("background: transparent;")
        self.text_layout = QVBoxLayout(self.text_container)
        # Padding mare sus/jos pentru a putea centra prima și ultima linie
        self.text_layout.setContentsMargins(20, 150, 20, 150)
        self.text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.text_container)
        lyric_layout.addWidget(self.scroll_area)
        
        # Poziționare inițială
        self.lbl_art.move(0, 0)
        
        self.lines = [] # Listă de tupluri (timestamp, widget)
        self.current_line_index = -1

    def _on_scroller_state_changed(self, state):
        if state in (QScroller.State.Pressed, QScroller.State.Dragging, QScroller.State.Scrolling):
            self.user_is_scrolling = True
            self.auto_scroll_timer.stop()
            if hasattr(self, 'scroll_anim') and self.scroll_anim.state() == QPropertyAnimation.State.Running:
                self.scroll_anim.stop()
        elif state == QScroller.State.Inactive:
            self.auto_scroll_timer.start()

    def _resume_auto_scroll(self):
        self.user_is_scrolling = False
        if self.current_line_index >= 0 and self.current_line_index < len(self.lines):
            self._smooth_scroll_to(self.lines[self.current_line_index][1])

    def set_zoom_factor(self, factor):
        self.zoom_factor = max(0.6, float(factor))

        top_bottom = int(150 * self.zoom_factor)
        side = int(20 * self.zoom_factor)
        self.text_layout.setContentsMargins(side, top_bottom, side, top_bottom)

        for _, widget in self.lines:
            if hasattr(widget, 'set_zoom_factor'):
                widget.set_zoom_factor(self.zoom_factor)

        self._update_mask()

    def eventFilter(self, source, event):
        # Detectăm Scroll UP când suntem la începutul versurilor -> Ascunde Lyrics
        if source == self.scroll_area.viewport() and event.type() == QEvent.Type.Wheel:
            # 🔥 DETECTARE SCROLL MANUAL (Rotiță mouse)
            self.user_is_scrolling = True
            self.auto_scroll_timer.start()
            if hasattr(self, 'scroll_anim') and self.scroll_anim.state() == QPropertyAnimation.State.Running:
                self.scroll_anim.stop()
                
            if self.lyrics_visible:
                if event.angleDelta().y() > 0: # Scroll UP
                    if self.scroll_area.verticalScrollBar().value() <= 0:
                        self.toggle_requested.emit(False)
                        return True # Consumăm evenimentul
        return super().eventFilter(source, event)

    def wheelEvent(self, event):
        # Detectăm Scroll DOWN pe Artwork -> Arată Lyrics
        if not self.lyrics_visible:
            if event.angleDelta().y() < 0: # Scroll DOWN
                self.toggle_requested.emit(True)
                event.accept()
        super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_geometries()
        self._update_mask()

    def _update_mask(self):
        """ Actualizează gradientul de transparență pe baza înălțimii curente """
        h = self.scroll_area.height()
        if h <= 0: return
        
        fade_h = int(60 * self.zoom_factor) # Înălțimea zonei de fade
        if fade_h * 2 > h: fade_h = h / 2
        
        # Gradient Alpha: Transparent -> Opac -> Opac -> Transparent
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, Qt.GlobalColor.transparent)
        gradient.setColorAt(fade_h / h, Qt.GlobalColor.black) # Black = Opac în mască
        gradient.setColorAt(1.0 - (fade_h / h), Qt.GlobalColor.black)
        gradient.setColorAt(1.0, Qt.GlobalColor.transparent)
        
        self.opacity_effect.setOpacityMask(gradient)

    def _update_geometries(self):
        w, h = self.width(), self.height()
        self.lbl_art.resize(w, h)
        self.lyrics_panel.resize(w, h)
        
        if self.slide_anim_group and self.slide_anim_group.state() == QPropertyAnimation.State.Running:
            return

        if not self.lyrics_visible:
            self.lbl_art.move(0, 0)
            self.lyrics_panel.move(0, h)
        else:
            self.lbl_art.move(0, -h)
            self.lyrics_panel.move(0, 0)

    def update_theme_colors(self, colors):
        """ Preia culorile din temă și le aplică versurilor """
        self.active_color = colors.get("PRIMARY", "#00AAFF")
        self.inactive_color = colors.get("FG", "#FFFFFF")
        
        for _, widget in self.lines:
            widget.set_theme_colors(self.active_color, self.inactive_color)

    def set_lyrics_visible(self, visible, animate=True):
        if self.lyrics_visible == visible: return
        self.lyrics_visible = visible
        
        h = self.height()
        if not animate:
            self._update_geometries()
            return

        self.slide_anim_group = QParallelAnimationGroup(self)
        
        anim_art = QPropertyAnimation(self.lbl_art, b"pos")
        anim_art.setDuration(400)
        anim_art.setEasingCurve(QEasingCurve.Type.InOutQuart)
        
        anim_lyrics = QPropertyAnimation(self.lyrics_panel, b"pos")
        anim_lyrics.setDuration(400)
        anim_lyrics.setEasingCurve(QEasingCurve.Type.InOutQuart)
        
        if self.lyrics_visible:
            anim_art.setEndValue(QPoint(0, -h))
            anim_lyrics.setStartValue(QPoint(0, h))
            anim_lyrics.setEndValue(QPoint(0, 0))
        else:
            anim_art.setEndValue(QPoint(0, 0))
            anim_lyrics.setStartValue(QPoint(0, 0))
            anim_lyrics.setEndValue(QPoint(0, h))
            
        self.slide_anim_group.addAnimation(anim_art)
        self.slide_anim_group.addAnimation(anim_lyrics)
        self.slide_anim_group.start()

    def set_lyrics(self, text):
        """ Actualizează textul versurilor """
        # 1. Curățăm layout-ul vechi
        while self.text_layout.count():
            item = self.text_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.lines = []
        self.current_line_index = -1
        
        if not text:
            self._add_placeholder("No lyrics found.")
            return

        # 2. Parsare LRC [mm:ss.xx]
        pattern = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)')
        parsed_lines = []
        has_timestamps = False
        
        for line in text.split('\n'):
            line = line.strip()
            match = pattern.match(line)
            if match:
                has_timestamps = True
                minutes = int(match.group(1))
                seconds = float(match.group(2))
                timestamp = minutes * 60 + seconds
                content = match.group(3).strip()
                parsed_lines.append((timestamp, content))
            elif not has_timestamps and line:
                # Dacă nu am găsit timestamp-uri, păstrăm textul brut momentan
                pass

        # 3. Construire UI
        if has_timestamps:
            parsed_lines.sort(key=lambda x: x[0])
            for ts, content in parsed_lines:
                if not content: content = "..." # Placeholder pentru instrumental
                lw = AnimatedLyricLine(content, ts) # 🔥 Folosim clasa cu animații
                lw.set_zoom_factor(self.zoom_factor)
                lw.set_theme_colors(self.active_color, self.inactive_color) # 🔥 Aplicăm culorile curente
                lw.clicked_with_time.connect(self.seek_requested.emit)
                self.text_layout.addWidget(lw)
                self.lines.append((ts, lw))
        else:
            # Fallback: Text simplu (nesincronizat)
            self._add_placeholder(text)

        # Resetăm scroll-ul sus
        self.scroll_area.verticalScrollBar().setValue(0)

    def _add_placeholder(self, text):
        lbl = QLabel(text)
        place_size = max(11, int(18 * self.zoom_factor))
        lbl.setStyleSheet(f"color: #E0E0E0; font-size: {place_size}px; font-weight: 500; line-height: 1.6;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        self.text_layout.addWidget(lbl)

    def update_position(self, current_time):
        """ Sincronizează versurile cu timpul curent """
        if not self.lines or not self.lyrics_visible: return
        
        # Găsim linia activă (ultima care a trecut de timpul curent)
        active_idx = -1
        for i, (ts, _) in enumerate(self.lines):
            if ts <= current_time + 0.2: # Toleranță mică pentru sync vizual
                active_idx = i
            else:
                break
        
        if active_idx != self.current_line_index:
            # Dezactivăm vechea linie
            if self.current_line_index >= 0 and self.current_line_index < len(self.lines):
                self.lines[self.current_line_index][1].set_active(False)
            
            # Activăm noua linie și facem scroll
            if active_idx >= 0:
                widget = self.lines[active_idx][1]
                widget.set_active(True)
                
                # 🔥 Centrare automată cu animație lină
                self._smooth_scroll_to(widget)
            
            self.current_line_index = active_idx

    def _smooth_scroll_to(self, widget):
        # 🔥 Nu forțăm scroll-ul dacă utilizatorul explorează manual versurile
        if self.user_is_scrolling:
            return
            
        if hasattr(self, 'scroll_anim') and self.scroll_anim.state() == QPropertyAnimation.State.Running:
            self.scroll_anim.stop()
            
        scroll_bar = self.scroll_area.verticalScrollBar()
        widget_center = widget.y() + widget.height() // 2
        viewport_h = self.scroll_area.viewport().height()
        target_val = widget_center - viewport_h // 2
        
        self.scroll_anim = QPropertyAnimation(scroll_bar, b"value")
        self.scroll_anim.setDuration(400)
        self.scroll_anim.setStartValue(scroll_bar.value())
        self.scroll_anim.setEndValue(target_val)
        self.scroll_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.scroll_anim.start()