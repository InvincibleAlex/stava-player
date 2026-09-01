from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel, QFrame, QPushButton, QStackedWidget, QButtonGroup, QGridLayout, QDial, QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QGroupBox)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRectF, QVariantAnimation, QEasingCurve, QPropertyAnimation, QTimer
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter, QPainterPath, QBrush, QPen
import math
import os
from Eq.knobs import AudioKnob
from Eq.equalizers import SpatialPage, ReverbPage
from Eq.sliders import EqBandSlider
from core.utils import IconHelper

class EqVisualizerCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bass_val = 0.0 # 0 la 100
        self.treble_val = 0.0 # 0 la 100
        self.bass_freq = 90.0
        self.treble_freq = 10000.0
        self.primary_color = "#00AAFF"
        self.bass_color = "#FFA500"
        self.fg_color = "#FFFFFF"
        self.eq_bands = [] # Lista de (freq, gain)
        self.fft_bars = 42 # Câte bare de muzică să apară
        self.current_fft = [0.0] * self.fft_bars
        
        self.tone_factor = 0.0
        self.target_tone_factor = 0.0
        self.tone_anim = QVariantAnimation(self)
        self.tone_anim.setDuration(250)
        self.tone_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.tone_anim.valueChanged.connect(self._update_tone_factor)

        self.eq_factor = 0.0
        self.target_eq_factor = 0.0
        self.eq_anim = QVariantAnimation(self)
        self.eq_anim.setDuration(250)
        self.eq_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.eq_anim.valueChanged.connect(self._update_eq_factor)

    def _update_eq_factor(self, value):
        self.eq_factor = float(value)
        self.update()

    def set_eq_enabled(self, enabled):
        target = 1.0 if enabled else 0.0
        if self.target_eq_factor != target:
            self.target_eq_factor = target
            self.eq_anim.stop()
            self.eq_anim.setStartValue(self.eq_factor)
            self.eq_anim.setEndValue(target)
            self.eq_anim.start()

    def _update_tone_factor(self, value):
        self.tone_factor = float(value)
        self.update()

    def set_tone_enabled(self, enabled):
        target = 1.0 if enabled else 0.0
        if self.target_tone_factor != target:
            self.target_tone_factor = target
            self.tone_anim.stop()
            self.tone_anim.setStartValue(self.tone_factor)
            self.tone_anim.setEndValue(target)
            self.tone_anim.start()

    def set_tone(self, bass, treble):
        self.bass_val = bass
        self.treble_val = treble
        self.update()

    def set_freqs(self, bass_f, treble_f):
        self.bass_freq = float(bass_f)
        self.treble_freq = float(treble_f)
        self.update()

    def set_eq_bands(self, bands):
        self.eq_bands = bands
        self.update()

    def set_fft_bars(self, count):
        self.fft_bars = max(10, min(128, int(count)))
        self.current_fft = [0.0] * self.fft_bars
        self.update()

    def set_fft_data(self, fft_raw):
        needs_update = False
        # Prevenim index out of bounds în timpul redimensionării listei
        if len(self.current_fft) != self.fft_bars: return
        
        if not fft_raw:
            # PAUZĂ: Netezim căderea barelor la 0
            for i in range(self.fft_bars):
                if self.current_fft[i] > 0.001:
                    self.current_fft[i] = max(0.0, self.current_fft[i] - 0.04)
                    needs_update = True
        else:
            # PLAY: Mapăm cele 128 de valori primite pe cele 42 de bare vizuale
            for i in range(self.fft_bars):
                # Folosim scalare logaritmică fină pentru a ne concentra pe muzică (joase/medii)
                idx = int(math.pow(i / self.fft_bars, 1.5) * 60)
                idx = max(0, min(127, idx))
                
                # Înaltele au energie mai mică în mod natural, le aplicăm un mic boost vizual
                boost = 8.0 + (i / self.fft_bars) * 15.0
                val = min(1.0, fft_raw[idx] * boost)
                
                # Easing: urcă rapid, coboară mai lent
                if val < self.current_fft[i]: self.current_fft[i] = max(val, self.current_fft[i] - 0.05)
                else: self.current_fft[i] = min(val, self.current_fft[i] + 0.25)
                if self.current_fft[i] > 0.001: needs_update = True

        if needs_update: self.update()

    def set_colors(self, primary, fg):
        self.primary_color = primary
        self.fg_color = fg
        self.update()

    def _freq_to_x(self, freq, width):
        min_f, max_f = 20.0, 20000.0
        f = max(min_f, min(max_f, float(freq)))
        return (math.log10(f / min_f) / math.log10(max_f / min_f)) * width

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        
        # Mască de tăiere pentru a păstra desenul strict în marginile rotunjite (8px) ale containerului părinte
        clip_path = QPainterPath()
        clip_path.addRoundedRect(0, 0, w, h, 8, 8)
        painter.setClipPath(clip_path)
        
        mid_y = h / 2.0

        # 0. Desenăm FFT-ul Muzicii (Pe Ultimul Layer, în spate de tot)
        step_x = w / self.fft_bars
        bar_w = step_x * 0.65 # Lăsăm 35% spațiu gol între ele pentru a se distinge ca pastile
        fft_c = QColor(self.primary_color)
        fft_c.setAlpha(40) # Foarte transparent
        painter.setBrush(QBrush(fft_c))
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(self.fft_bars):
            val = self.current_fft[i]
            if val > 0.005:
                bar_h = val * h * 0.9 # Urcă până la maxim 90% din înălțime
                bx = i * step_x + (step_x - bar_w) / 2 # Centrat pe segmentul său
                # Raza adaptivă (max jumătate din lățime) ca să arate a pastilă perfectă și când e mică
                radius = min(bar_w / 2.0, bar_h / 2.0)
                painter.drawRoundedRect(QRectF(bx, h - bar_h, bar_w, bar_h), radius, radius)

        # 1. Desenăm linia 0 dB (Acum Continuă)
        pen0 = QPen(QColor(self.fg_color))
        c0 = pen0.color()
        c0.setAlpha(60)
        pen0.setColor(c0)
        pen0.setWidth(1)
        pen0.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen0)
        painter.drawLine(0, int(mid_y), w, int(mid_y))

        # 2. Desenăm Curba de Bass (La baza dreptunghiului)
        if self.bass_val > 0.01 and self.tone_factor > 0.01:
            end_x = self._freq_to_x(self.bass_freq, w)
            max_h = (self.bass_val / 100.0) * (mid_y - 2) * self.tone_factor # Aplatizare proporțională
            base_y = h # Marginea de jos
            
            # Path pentru umplere (Culoarea interioară)
            fill_path = QPainterPath()
            fill_path.moveTo(0, base_y)
            fill_path.lineTo(0, base_y - max_h)
            
            # Path pentru contur (Doar curba)
            line_path = QPainterPath()
            line_path.moveTo(0, base_y - max_h)
            
            steps = max(1, int(end_x))
            for i in range(1, steps + 1):
                t = i / end_x
                y_val = max_h * math.cos(t * math.pi / 2.0)
                fill_path.lineTo(i, base_y - y_val)
                line_path.lineTo(i, base_y - y_val) # Conturul urmărește doar punctele curbei
                
            fill_path.lineTo(end_x, base_y)
            fill_path.closeSubpath()
            
            bc = QColor(self.bass_color)
            bc.setAlpha(int(90 * self.tone_factor)) # Fade out
            
            # 1. Desenăm Culoarea (fără linii de contur)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(bc))
            painter.drawPath(fill_path)
            
            # 2. Desenăm Linia Curbei (fără umplere interioară)
            lc = QColor(self.bass_color)
            lc.setAlpha(int(255 * self.tone_factor))
            painter.setPen(QPen(lc, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(line_path)

        # 3. Desenăm Curba de Treble (La baza dreptunghiului)
        if self.treble_val > 0.01 and self.tone_factor > 0.01:
            start_x = self._freq_to_x(self.treble_freq, w)
            max_h = (self.treble_val / 100.0) * (mid_y - 2) * self.tone_factor
            base_y = h # Marginea de jos
            
            fill_path = QPainterPath()
            fill_path.moveTo(start_x, base_y)
            
            line_path = QPainterPath()
            line_path.moveTo(start_x, base_y)
            
            steps = max(1, int(w - start_x))
            for i in range(1, steps + 1):
                x = start_x + i
                t = (x - start_x) / (w - start_x)
                y_val = max_h * math.sin(t * math.pi / 2.0)
                fill_path.lineTo(x, base_y - y_val)
                line_path.lineTo(x, base_y - y_val)
            
            fill_path.lineTo(w, base_y - max_h)
            fill_path.lineTo(w, base_y)
            fill_path.closeSubpath()
            
            tc = QColor(self.primary_color)
            tc.setAlpha(int(90 * self.tone_factor))
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(tc))
            painter.drawPath(fill_path)
            
            lc2 = QColor(self.primary_color)
            lc2.setAlpha(int(255 * self.tone_factor))
            painter.setPen(QPen(lc2, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(line_path)
            
        # 4. Desenăm Curba Egalizatorului (Graphic EQ)
        if hasattr(self, 'eq_bands') and self.eq_bands and self.eq_factor > 0.01:
            path = QPainterPath()
            points = []
            
            for freq, gain in self.eq_bands:
                x = self._freq_to_x(freq, w)
                # Gain: -12 to +12 se mapează de la marginea de jos la marginea de sus a jumătății
                flattened_gain = gain * self.eq_factor # Aplatizare proporțională
                y = mid_y - (flattened_gain / 12.0) * (mid_y - 8)
                points.append((x, y))
                
            if points:
                # Extindem linia plat spre marginile din stânga și dreapta (pentru continuitate)
                first_x, first_y = points[0]
                last_x, last_y = points[-1]
                
                path.moveTo(0, first_y)
                path.lineTo(first_x, first_y)
                
                # Creăm o curbă lină (Bezier Cubic) prin toate punctele intermediare
                for i in range(len(points) - 1):
                    x1, y1 = points[i]
                    x2, y2 = points[i+1]
                    # Puncte de control la jumătatea distanței pe axa X pentru a asigura o curbă orizontală fluidă
                    ctrl_x = (x1 + x2) / 2.0
                    path.cubicTo(ctrl_x, y1, ctrl_x, y2, x2, y2)
                    
                path.lineTo(w, last_y)
                
                # Fade și subțiere linie
                line_alpha = int(255 * self.eq_factor)
                line_color = QColor(self.fg_color)
                line_color.setAlpha(line_alpha)
                line_thickness = max(0.1, 2.0 * self.eq_factor)
                
                # Desenăm linia EQ-ului
                line_pen = QPen(line_color, line_thickness)
                line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(line_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
                
                # Desenăm punctele (cercuri mici de control) colorate
                dot_color = QColor(self.primary_color)
                dot_color.setAlpha(line_alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(dot_color))
                dot_radius = line_thickness / 2.0
                if dot_radius > 0.5:
                    for x, y in points:
                        painter.drawEllipse(QRectF(x - dot_radius, y - dot_radius, dot_radius * 2, dot_radius * 2))

class EqTab(QWidget):
    bass_changed = pyqtSignal(float)
    treble_changed = pyqtSignal(float)
    band_changed = pyqtSignal(int, float)
    preamp_changed = pyqtSignal(float)
    
    toggle_eq_bands = pyqtSignal(bool)
    toggle_knobs = pyqtSignal(bool)
    toggle_limiter = pyqtSignal(bool)
    toggle_master_dsp = pyqtSignal(bool)
    toggle_spatial = pyqtSignal(bool)
    toggle_reverb = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        # Setup icons dir
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.icons_dir = os.path.join(base_dir, 'icons')
        self.freqs_float = [] # Stocăm frecvențele calculate (Hz)
        self.freqs_str = []   # Stocăm etichetele (ex: "1k")
        self.is_horizontal_layout = False # False = Slidere Verticale (Standard), True = Slidere Orizontale (Listă)
        self.current_band_count = 10
        self.global_zoom = 1.0
        self.current_colors = {}
        self.init_ui()

    def _get_icon(self, name):
        # Căutăm iconița în diverse locații
        p = os.path.join(self.icons_dir, name)
        if not os.path.exists(p):
             p = os.path.join(self.icons_dir, 'player', name)
        if not os.path.exists(p):
             p = os.path.join(self.icons_dir, 'playlist', name)
        return p

    def _create_nav_btn(self, icon_name, id, group, layout):
        btn = QPushButton()
        btn.setCheckable(True)
        btn.setFixedSize(40, 40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("icon_name", icon_name)
        group.addButton(btn, id)
        layout.addWidget(btn)
        return btn

    def init_ui(self):
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- 1. NAVBAR SUPERIOR ---
        nav_container = QWidget()
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(20, 10, 20, 10)
        self.nav_layout = nav_layout
        
        # 1. Butonul EQU (Fostul Effects) - Stânga
        self.btn_master = QPushButton("Equ")
        self.btn_master.setCheckable(True)
        self.btn_master.setChecked(False)
        self.btn_master.setFixedSize(60, 34)
        self.btn_master.toggled.connect(self.on_master_toggle)
        
        nav_layout.addWidget(self.btn_master)
        nav_layout.addStretch()

        # Containerul "Pastilă"
        self.pill_nav = QFrame()
        self.pill_nav.setFixedHeight(50)
        
        pill_layout = QHBoxLayout(self.pill_nav)
        pill_layout.setContentsMargins(5, 5, 5, 5)
        pill_layout.setSpacing(10)
        self.pill_layout = pill_layout

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_group.idClicked.connect(self.switch_page)

        # Folosim iconițe (numele fișierelor SVG)
        self.btn_nav_eq = self._create_nav_btn("eq-sliders-3knobs.svg", 0, self.nav_group, pill_layout)
        self.btn_nav_spatial = self._create_nav_btn("stereo-expand-3nodes.svg", 1, self.nav_group, pill_layout)
        self.btn_nav_reverb = self._create_nav_btn("reverb-knob-ripples.svg", 2, self.nav_group, pill_layout)
        
        self.btn_nav_eq.setChecked(True)
        
        nav_layout.addWidget(self.pill_nav)
        nav_layout.addStretch()
        
        # Dummy widget dreapta pentru a balansa layout-ul (centrare perfectă)
        dummy = QWidget()
        dummy.setFixedSize(60, 34)
        self.nav_dummy = dummy
        nav_layout.addWidget(dummy)
        
        self.main_layout.addWidget(nav_container)

        # --- 2. STACKED WIDGET (PAGINI) ---
        self.stack = QStackedWidget()
        
        self.page_eq = QWidget()
        self.setup_eq_page(self.page_eq)
        self.stack.addWidget(self.page_eq)

        # --- SPATIAL PAGE ---
        self.page_spatial = SpatialPage()
        self.spatial_wrapper = QWidget()
        sw_layout = QVBoxLayout(self.spatial_wrapper)
        sw_layout.setContentsMargins(20, 0, 20, 0) # 20px stânga -> Aliniat perfect sub 'Equ'
        sw_layout.setSpacing(10)
        
        self.btn_spatial = QPushButton("Spatial")
        self.btn_spatial.setCheckable(True)
        self.btn_spatial.setChecked(True)
        self.btn_spatial.setFixedSize(70, 34)
        self.btn_spatial.setEnabled(False) # Master OFF default
        self.btn_spatial.toggled.connect(self.on_spatial_toggle)
        
        sw_layout.addWidget(self.btn_spatial, 0, Qt.AlignmentFlag.AlignLeft)
        sw_layout.addWidget(self.page_spatial, 1)
        self.stack.addWidget(self.spatial_wrapper)

        # --- REVERB PAGE ---
        self.page_reverb = ReverbPage()
        self.reverb_wrapper = QWidget()
        rw_layout = QVBoxLayout(self.reverb_wrapper)
        rw_layout.setContentsMargins(20, 0, 20, 0)
        rw_layout.setSpacing(10)
        
        self.btn_reverb = QPushButton("Reverb")
        self.btn_reverb.setCheckable(True)
        self.btn_reverb.setChecked(True)
        self.btn_reverb.setFixedSize(70, 34)
        self.btn_reverb.setEnabled(False) # Master OFF default
        self.btn_reverb.toggled.connect(self.on_reverb_toggle)
        
        rw_layout.addWidget(self.btn_reverb, 0, Qt.AlignmentFlag.AlignLeft)
        rw_layout.addWidget(self.page_reverb, 1)
        self.stack.addWidget(self.reverb_wrapper)

        self.main_layout.addWidget(self.stack)
        self.setLayout(self.main_layout)

    def switch_page(self, id):
        self.stack.setCurrentIndex(id)
        if self.isVisible():
            self.trigger_first_show_animations(id)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_tone_first_show', False):
            self._tone_first_show = True
            if hasattr(self, 'knob_bass') and hasattr(self, 'knob_treble'):
                self.animate_widget_sweep_visual(self.knob_bass, self.knob_bass.value(), delay=0)
                self.animate_widget_sweep_visual(self.knob_treble, self.knob_treble.value(), delay=60)
                
        if hasattr(self, 'stack'):
            self.trigger_first_show_animations(self.stack.currentIndex())

    def trigger_first_show_animations(self, page_id):
        if page_id == 0 and not getattr(self, '_eq_first_show', False):
            self._eq_first_show = True
            if hasattr(self, 'slider_preamp'):
                self.animate_widget_sweep_visual(self.slider_preamp, self.slider_preamp.value(), delay=0)
            if hasattr(self, 'sliders'):
                for i, slider in enumerate(self.sliders):
                    self.animate_widget_sweep_visual(slider, slider.value(), delay=i * 30)
                    
        elif page_id == 1 and not getattr(self, '_spatial_first_show', False):
            self._spatial_first_show = True
            if hasattr(self, 'page_spatial'):
                sp = self.page_spatial
                self.animate_widget_sweep_visual(sp.knob_tempo, sp.knob_tempo.value(), delay=0, start_val=1.0)
                self.animate_widget_sweep_visual(sp.knob_balance, sp.knob_balance.value(), delay=30, start_val=50.0)
                self.animate_widget_sweep_visual(sp.knob_stereo, sp.knob_stereo.value(), delay=60)
                self.animate_widget_sweep_visual(sp.knob_low_bypass, sp.knob_low_bypass.value(), delay=90)
                
        elif page_id == 2 and not getattr(self, '_reverb_first_show', False):
            self._reverb_first_show = True
            if hasattr(self, 'page_reverb'):
                rv = self.page_reverb
                knobs = [rv.knob_damp, rv.knob_filter, rv.knob_fade, rv.knob_size, rv.knob_predelay, rv.knob_predelay_mix]
                for i, knob in enumerate(knobs):
                    self.animate_widget_sweep_visual(knob, knob.value(), delay=i * 30)

    def setup_eq_page(self, parent):
        layout = QVBoxLayout(parent)
        
        # --- 1. EQ BANDS (SUS) ---
        self.eq_frame = QFrame()
        eq_layout = QHBoxLayout()
        eq_layout.setContentsMargins(10, 10, 10, 20)
        
        # Preamp
        preamp_layout = QVBoxLayout()
        preamp_layout.setSpacing(0) # Fără padding între elemente
        preamp_layout.setContentsMargins(0, 0, 0, 0) # Fără margini
        self.slider_preamp = EqBandSlider(Qt.Orientation.Vertical)
        self.slider_preamp.setRange(-24, 24)
        self.slider_preamp.setValue(0)
        self.slider_preamp.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self.slider_preamp.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding) # Maxim de lung
        self.slider_preamp.setMinimumHeight(30) # Permite micșorarea
        
        lbl_pre = QLabel("PRE")
        self.lbl_pre = lbl_pre
        lbl_pre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_pre.setStyleSheet("font-size: 10px; font-weight: bold;") # Text mai mic
        lbl_pre.setFixedHeight(15) # Înălțime fixă mică
        self.lbl_pre_val = QLabel("0")
        self.lbl_pre_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pre_val.setStyleSheet("font-size: 11px; font-weight: bold;")
        self.lbl_pre_val.setFixedHeight(15) # Înălțime fixă mică
        self.slider_preamp.valueChanged.connect(self.on_preamp_change)

        preamp_layout.addWidget(self.slider_preamp)
        preamp_layout.addWidget(lbl_pre)
        preamp_layout.addWidget(self.lbl_pre_val)
        eq_layout.addLayout(preamp_layout)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        eq_layout.addWidget(line)

        # Scroll Area pentru Benzi (Scroll Orizontal)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setMinimumWidth(0) # 🔥 FIX: Permite micșorarea fără a forța lărgirea Playlist-ului

        # Widget-ul intern va fi creat în regenerate_bands
        self.bands_widget = None
        eq_layout.addWidget(self.scroll_area, 1)

        self.eq_frame.setLayout(eq_layout)
        layout.addWidget(self.eq_frame, stretch=3)

        # --- 1.5 TONE VISUALIZER (MIJLOC) ---
        # Canvas-ul pe care vom desena curba de Bass/Treble
        self.visualizer_frame = QGroupBox()
        self.visualizer_frame.setTitle("") # Îl lăsăm fără titlu, doar ca formă de panou
        self.visualizer_frame.setMinimumHeight(60)
        self.visualizer_frame.setMaximumHeight(80)
        
        viz_layout = QVBoxLayout(self.visualizer_frame)
        viz_layout.setContentsMargins(0, 0, 0, 0)
        self.visualizer_canvas = EqVisualizerCanvas()
        viz_layout.addWidget(self.visualizer_canvas)
        
        layout.addWidget(self.visualizer_frame, stretch=1)

        # Generăm benzile abia DUPĂ ce a fost creat visualizer_canvas
        self.regenerate_bands(10) # Default 10 benzi
        self.eq_frame.setEnabled(False) # Default Disabled (Master OFF)

        # --- 2. CONTROLS (JOS) ---
        bottom_container = QHBoxLayout()
        bottom_container.setContentsMargins(10, 10, 10, 10)

        # Container Butoane (Effects + Limiter)
        self.buttons_container = QWidget()
        buttons_layout = QVBoxLayout(self.buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(10) # 🔥 Reducem drastic spațiul dintre butoane
        
        # Buton Bands (Nou)
        self.btn_bands = QPushButton("Bands")
        self.btn_bands.setCheckable(True)
        self.btn_bands.setChecked(True)
        self.btn_bands.setFixedSize(70, 34)
        self.btn_bands.setEnabled(False) # Default Disabled
        self.btn_bands.toggled.connect(self.on_bands_toggle)

        # Buton Tone (Nou)
        self.btn_tone = QPushButton("Tone")
        self.btn_tone.setCheckable(True)
        self.btn_tone.setChecked(True)
        self.btn_tone.setFixedSize(70, 34) # Dimensiune fixă, egală și compactă
        self.btn_tone.setEnabled(False) # Default Disabled
        self.btn_tone.toggled.connect(self.on_tone_toggle)

        # Buton Limit (Redenumit)
        self.btn_limit = QPushButton("Limit")
        self.btn_limit.setCheckable(True)
        self.btn_limit.setChecked(False)
        self.btn_limit.setEnabled(False) # Default Disabled
        self.btn_limit.setFixedSize(70, 34) # Dimensiune fixă, egală și compactă
        self.btn_limit.toggled.connect(lambda c: self.toggle_limiter.emit(c))

        buttons_layout.addStretch()
        buttons_layout.addWidget(self.btn_bands)
        buttons_layout.addWidget(self.btn_tone)
        buttons_layout.addWidget(self.btn_limit)
        buttons_layout.addStretch()

        # Container Knobs (Bass + Treble)
        self.knobs_container = QWidget()
        knobs_layout = QHBoxLayout(self.knobs_container)
        knobs_layout.setContentsMargins(0, 0, 0, 0)
        
        knobs_layout.addStretch()
        # Range 0% la 100% (Boost Only), Default 0%
        self.knob_bass = AudioKnob("BASS", 0, 100, format_str="{:.0f}%") 
        self.knob_bass.setValue(0) 
        self.knob_bass.setEnabled(False) # Default Disabled
        self.knob_bass.value_changed.connect(self.update_visualizer_tone)
        self.knob_bass.value_changed.connect(self.bass_changed.emit)
        
        self.knob_treble = AudioKnob("TREBLE", 0, 100, format_str="{:.0f}%")
        self.knob_treble.setValue(0)
        self.knob_treble.setEnabled(False) # Default Disabled
        self.knob_treble.value_changed.connect(self.update_visualizer_tone)
        self.knob_treble.value_changed.connect(self.treble_changed.emit)
        knobs_layout.addWidget(self.knob_bass)
        knobs_layout.addSpacing(30)
        knobs_layout.addWidget(self.knob_treble)
        knobs_layout.addStretch()

        bottom_container.addWidget(self.buttons_container, 1)
        bottom_container.addWidget(self.knobs_container, 3)

        layout.addLayout(bottom_container)

    def set_tone_freqs(self, bass_f, treble_f):
        """ Chemată de MainApp pentru a sincroniza setările """
        self.visualizer_canvas.set_freqs(bass_f, treble_f)

    def update_visualizer_tone(self, *_):
        """ Calculează ce valori sunt vizibile pe grafic pe baza comutatoarelor """
        if not hasattr(self, 'visualizer_canvas') or getattr(self, 'btn_tone', None) is None:
            return
            
        enabled = self.btn_tone.isChecked() and self.btn_master.isChecked()
        self.visualizer_canvas.set_tone_enabled(enabled)
        self.visualizer_canvas.set_tone(self.knob_bass.value(), self.knob_treble.value())

    def update_visualizer_eq(self, *_):
        """ Extrage valorile tuturor sliderelor și le trimite către canvas """
        if not hasattr(self, 'visualizer_canvas'):
            return
        bands = []
        if hasattr(self, 'sliders') and self.sliders:
            for i, slider in enumerate(self.sliders):
                if i < len(self.freqs_float):
                    # slider.value() este între -24 și 24, deci împărțim la 2 pentru dB reali
                    bands.append((self.freqs_float[i], slider.value() / 2.0))
        self.visualizer_canvas.set_eq_bands(bands)
        
        is_enabled = self.btn_master.isChecked()
        if hasattr(self, 'btn_bands'):
            is_enabled = is_enabled and self.btn_bands.isChecked()
            
        self.visualizer_canvas.set_eq_enabled(is_enabled)

    def set_zoom_factor(self, factor):
        self.global_zoom = max(0.6, float(factor))
        z = self.global_zoom

        self.btn_master.setFixedSize(int(60 * z), int(34 * z))
        self.btn_bands.setFixedSize(int(70 * z), int(34 * z))
        self.btn_tone.setFixedSize(int(70 * z), int(34 * z))
        self.btn_limit.setFixedSize(int(70 * z), int(34 * z))
        if hasattr(self, 'btn_spatial'): self.btn_spatial.setFixedSize(int(70 * z), int(34 * z))
        if hasattr(self, 'btn_reverb'): self.btn_reverb.setFixedSize(int(70 * z), int(34 * z))

        nav_size = max(24, int(40 * z))
        for btn in [self.btn_nav_eq, self.btn_nav_spatial, self.btn_nav_reverb]:
            btn.setFixedSize(nav_size, nav_size)

        pad = max(2, int(3 * z))
        spacing = max(3, int(6 * z))
        pill_h = nav_size + (2 * pad)
        self.pill_layout.setContentsMargins(pad, pad, pad, pad)
        self.pill_layout.setSpacing(spacing)
        self.pill_nav.setFixedHeight(pill_h)

        nav_h = max(4, int(10 * z))
        nav_w = max(8, int(20 * z))
        self.nav_layout.setContentsMargins(nav_w, nav_h, nav_w, nav_h)
        self.nav_dummy.setFixedSize(int(60 * z), int(34 * z))

        if hasattr(self, 'lbl_pre'):
            self.lbl_pre.setFixedHeight(max(12, int(15 * z)))
            self.lbl_pre.setStyleSheet(f"font-size: {max(8, int(10 * z))}px; font-weight: bold;")
        self.lbl_pre_val.setFixedHeight(max(12, int(15 * z)))
        self.lbl_pre_val.setStyleSheet(f"font-size: {max(9, int(11 * z))}px; font-weight: bold;")

        self.slider_preamp.setMinimumHeight(max(20, int(30 * z)))

        for slider in getattr(self, 'sliders', []):
            if slider.orientation() == Qt.Orientation.Horizontal:
                slider.setFixedHeight(max(20, int(30 * z)))
            else:
                slider.setMinimumHeight(max(24, int(40 * z)))

        if self.bands_widget:
            for lbl in self.bands_widget.findChildren(QLabel):
                cur = lbl.styleSheet() or ""
                if "font-size" in cur:
                    if "font-weight: bold" in cur:
                        lbl.setStyleSheet(f"font-size: {max(9, int(12 * z))}px; font-weight: bold;")
                    else:
                        lbl.setStyleSheet(f"font-size: {max(8, int(10 * z))}px;")

        for knob in self.findChildren(AudioKnob):
            knob.set_zoom_factor(z)

        if hasattr(self.page_spatial, 'set_zoom_factor'):
            self.page_spatial.set_zoom_factor(z)
        if hasattr(self.page_reverb, 'set_zoom_factor'):
            self.page_reverb.set_zoom_factor(z)
        if self.current_colors:
            self.update_theme_colors(self.current_colors)
            
        if hasattr(self, 'visualizer_frame'):
            self.visualizer_frame.setMinimumHeight(max(30, int(60 * z)))
            self.visualizer_frame.setMaximumHeight(max(40, int(80 * z)))

    def _set_btn_icon(self, btn, color_hex):
        icon_name = btn.property("icon_name")
        if not icon_name: return
        
        path = self._get_icon(icon_name)
        icon_size = max(18, min(btn.width() - 6, int(btn.width() * 0.72)))
        icon = IconHelper.get_colored_icon(path, color_hex, size=icon_size)
        btn.setIcon(icon)
        btn.setIconSize(QSize(icon_size, icon_size))

    def update_theme_colors(self, colors):
        self.current_colors = dict(colors)
        menu_bg = colors.get("MENU_BG", "#252525")
        fg_color = colors.get("FG", "#FFFFFF")
        primary = colors.get("PRIMARY", "#00AAFF")
        icon_color = colors.get("ICON_COLOR", fg_color)
        
        c = QColor(menu_bg)
        c.setAlphaF(0.2)
        pill_bg = f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alphaF()})"
        
        btn_radius = max(10, self.btn_tone.height() // 2)
        master_radius = max(10, self.btn_master.height() // 2)
        pill_radius = max(12, self.pill_nav.height() // 2)
        nav_btn_radius = max(8, self.btn_nav_eq.height() // 2)

        # Stil pentru butoanele mici (EQ, Knobs, Limiter)
        btn_style = f"""
            QPushButton {{
                background-color: {pill_bg};
                color: {fg_color};
                border-radius: {btn_radius}px;
                border: 1px solid transparent;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background-color: {primary};
                color: #000000;
                border: 1px solid {primary};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid {primary};
            }}
        """
        
        # Stil pentru Containerul Pastilă
        self.pill_nav.setStyleSheet(f"background-color: {pill_bg}; border-radius: {pill_radius}px;")
        
        # Stil pentru Butoanele de Navigare (Transparente, doar icon)
        nav_btn_style = f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: {nav_btn_radius}px;
            }}
            QPushButton:checked {{ background-color: rgba(255, 255, 255, 0.1); }}
            QPushButton:hover {{ background-color: rgba(255, 255, 255, 0.05); }}
        """
        self.btn_nav_eq.setStyleSheet(nav_btn_style)
        self.btn_nav_spatial.setStyleSheet(nav_btn_style)
        self.btn_nav_reverb.setStyleSheet(nav_btn_style)
        
        # Setăm iconițele colorate
        self._set_btn_icon(self.btn_nav_eq, icon_color)
        self._set_btn_icon(self.btn_nav_spatial, icon_color)
        self._set_btn_icon(self.btn_nav_reverb, icon_color)
        
        # Update Knobs Colors
        knob_border = colors.get("SECONDARY", "#444444")
        self.knob_bass.set_colors("#1C1C1C", knob_border, title_color=fg_color)
        self.knob_treble.set_colors("#1C1C1C", knob_border, title_color=fg_color)
        
        # Update Visualizer Colors
        self.visualizer_canvas.set_colors(primary, fg_color)
        
        if hasattr(self.page_spatial, 'update_theme_colors'):
            self.page_spatial.update_theme_colors(colors)
        if hasattr(self.page_reverb, 'update_theme_colors'):
            self.page_reverb.update_theme_colors(colors)
        self.btn_master.setStyleSheet(btn_style.replace(f"border-radius: {btn_radius}px;", f"border-radius: {master_radius}px;"))
        self.btn_bands.setStyleSheet(btn_style)
        self.btn_tone.setStyleSheet(btn_style)
        self.btn_limit.setStyleSheet(btn_style)
        if hasattr(self, 'btn_spatial'): self.btn_spatial.setStyleSheet(btn_style)
        if hasattr(self, 'btn_reverb'): self.btn_reverb.setStyleSheet(btn_style)
        
        # Actualizăm culoarea textului pentru label-uri (păstrând dimensiunea)
        pre_size = max(9, int(11 * self.global_zoom))
        self.lbl_pre_val.setStyleSheet(f"font-size: {pre_size}px; font-weight: bold; color: {fg_color};")
        
        # Notă: Label-urile din loop (benzile) moștenesc culoarea din QWidget global, 
        # dar le putem forța dacă e nevoie. Momentan le lăsăm să moștenească FG.

    def regenerate_bands(self, count):
        """ Regenerează sliderele EQ pentru un număr dat de benzi """
        self.current_band_count = count
        
        # 1. Creăm un nou container pentru benzi
        new_widget = QWidget()
        new_widget.setStyleSheet("background: transparent;")
        
        if self.is_horizontal_layout:
            # Mod COMPACT: Listă verticală cu slidere orizontale
            self.bands_layout = QVBoxLayout(new_widget)
            self.bands_layout.setSpacing(10)
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            # Mod STANDARD: Rând orizontal cu slidere verticale
            self.bands_layout = QHBoxLayout(new_widget)
            self.bands_layout.setSpacing(2)
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.bands_layout.setContentsMargins(5, 5, 5, 5)

        self.sliders = []
        self.freqs_float = []
        self.freqs_str = []

        # 2. Calculăm frecvențele (Logaritmic între 31Hz și 16kHz)
        start_f = 31.0
        end_f = 16000.0
        if count < 1: count = 1
        
        if count == 1:
            self.freqs_float = [1000.0]
            self.freqs_str = ["1k"]
        else:
            factor = (end_f / start_f) ** (1 / (count - 1))
            curr = start_f
            for _ in range(count):
                self.freqs_float.append(curr)
                # Formatare etichetă
                if curr >= 999.5:
                    val = curr / 1000
                    lbl = f"{int(round(val))}k" if abs(round(val)-val) < 0.1 else f"{val:.1f}k"
                else:
                    lbl = f"{int(round(curr))}"
                self.freqs_str.append(lbl)
                curr *= factor

        # 3. Creăm UI-ul
        for i, (freq_val, freq_lbl) in enumerate(zip(self.freqs_float, self.freqs_str)):
            band_wrapper = QWidget()
            
            if self.is_horizontal_layout:
                # --- LAYOUT ORIZONTAL (Compact) ---
                # [Freq Label] [Slider Orizontal] [Value Label]
                container = QHBoxLayout(band_wrapper)
                container.setContentsMargins(0, 0, 0, 0)
                container.setSpacing(10)
                
                lbl_freq = QLabel(freq_lbl)
                lbl_freq.setFixedWidth(40)
                lbl_freq.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                lbl_freq.setStyleSheet("font-size: 12px; font-weight: bold;")
                
                slider = EqBandSlider(Qt.Orientation.Horizontal)
                slider.setRange(-24, 24)
                slider.setValue(0)
                slider.setFixedHeight(30)
                
                lbl_val = QLabel("0")
                lbl_val.setFixedWidth(30)
                lbl_val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                lbl_val.setStyleSheet("font-size: 12px;")
                
                slider._lbl_val_ref = lbl_val
                container.addWidget(lbl_freq)
                container.addWidget(slider)
                container.addWidget(lbl_val)
                
            else:
                # --- LAYOUT VERTICAL (Standard) ---
                # [Slider Vertical]
                # [Freq Label]
                # [Value Label]
                band_wrapper.setMinimumWidth(45)
                band_wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                
                container = QVBoxLayout(band_wrapper)
                container.setContentsMargins(0, 0, 0, 0)
                container.setSpacing(0)

                slider = EqBandSlider(Qt.Orientation.Vertical)
                slider.setRange(-24, 24)
                slider.setValue(0)
                slider.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
                slider.setMinimumHeight(40)
                
                lbl_freq = QLabel(freq_lbl)
                lbl_freq.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_freq.setStyleSheet("font-size: 9px;")
                lbl_freq.setFixedHeight(15)
                
                lbl_val = QLabel("0")
                lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_val.setStyleSheet("font-size: 10px;")
                lbl_val.setFixedHeight(15)
                
                slider._lbl_val_ref = lbl_val
                container.addWidget(slider)
                container.addWidget(lbl_freq)
                container.addWidget(lbl_val)

            # Conectare semnale
            slider.valueChanged.connect(lambda val, l=lbl_val: l.setText(f"{val/2:g}"))
            
            # 🔥 FIX: Eliminăm `.repaint()` și folosim un timer (throttle) 
            # pentru a lăsa UI-ul să deseneze mânerul slider-ului fluent în timpul tragerii
            def on_slider_drag(val, idx=i, s=slider):
                if hasattr(s, '_throttle_timer'):
                    s._throttle_timer.stop()
                    s._throttle_timer.deleteLater()
                
                t = QTimer()
                t.setSingleShot(True)
                t.setInterval(12) # ~80 FPS - Oferă interfeței timp să animeze slider-ul
                t.timeout.connect(lambda: self.band_changed.emit(idx, s.value()/2))
                t.timeout.connect(self.update_visualizer_eq)
                t.start()
                s._throttle_timer = t
                
            slider.valueChanged.connect(on_slider_drag)

            self.bands_layout.addWidget(band_wrapper)
            self.sliders.append(slider)

        # Setăm noul widget în ScrollArea
        self.scroll_area.setWidget(new_widget)
        self.bands_widget = new_widget
        self.update_visualizer_eq() # Forțăm update-ul la inițializare

    def _apply_master_visual(self, checked):
        """Aplică grey-out vizual bazat pe starea Master (fără a emite semnale)"""
        self.btn_limit.setEnabled(checked)
        self.btn_bands.setEnabled(checked)
        self.btn_tone.setEnabled(checked)
        if hasattr(self, 'btn_spatial'): self.btn_spatial.setEnabled(checked)
        if hasattr(self, 'btn_reverb'): self.btn_reverb.setEnabled(checked)

        self._set_widget_dim(self.btn_limit, checked)
        self._set_widget_dim(self.btn_bands, checked)
        self._set_widget_dim(self.btn_tone, checked)
        if hasattr(self, 'btn_spatial'): self._set_widget_dim(self.btn_spatial, checked)
        if hasattr(self, 'btn_reverb'): self._set_widget_dim(self.btn_reverb, checked)
        self._set_widget_dim(self.visualizer_frame, checked)

        if checked:
            self.on_bands_toggle(self.btn_bands.isChecked())
            self.on_tone_toggle(self.btn_tone.isChecked())
            if hasattr(self, 'btn_spatial'): self.on_spatial_toggle(self.btn_spatial.isChecked())
            if hasattr(self, 'btn_reverb'): self.on_reverb_toggle(self.btn_reverb.isChecked())
        else:
            self.knob_bass.setEnabled(False)
            self.knob_treble.setEnabled(False)
            self._set_widget_dim(self.knob_bass, False)
            self._set_widget_dim(self.knob_treble, False)
            
            self.eq_frame.setEnabled(False)
            self._set_widget_dim(self.eq_frame, False)
            
            self.page_spatial.setEnabled(False)
            self._set_widget_dim(self.page_spatial, False)
            
            self.page_reverb.setEnabled(False)
            self._set_widget_dim(self.page_reverb, False)

    def on_spatial_toggle(self, checked):
        enabled = bool(checked) and self.btn_master.isChecked()
        self.page_spatial.setEnabled(enabled)
        self._set_widget_dim(self.page_spatial, enabled)
        
        knobs = [
            (self.page_spatial.knob_tempo, 1.0),
            (self.page_spatial.knob_balance, 50.0),
            (self.page_spatial.knob_stereo, 0.0),
            (self.page_spatial.knob_low_bypass, 0.0)
        ]
        self._apply_knob_animations(knobs, enabled)
        
        def emit_signal():
            if hasattr(self, 'btn_spatial') and self.btn_spatial.isChecked() == checked:
                try: self.toggle_spatial.emit(bool(checked))
                except: pass
        if checked:
            anim = getattr(self.page_spatial.knob_tempo, '_val_anim', None)
            if anim and anim.state() == QVariantAnimation.State.Running:
                anim.finished.connect(emit_signal)
            else:
                emit_signal()
        else:
            emit_signal()

    def on_reverb_toggle(self, checked):
        enabled = bool(checked) and self.btn_master.isChecked()
        self.page_reverb.setEnabled(enabled)
        self._set_widget_dim(self.page_reverb, enabled)
        
        knobs = [
            (self.page_reverb.knob_damp, 0.0),
            (self.page_reverb.knob_filter, 0.0),
            (self.page_reverb.knob_fade, 0.0),
            (self.page_reverb.knob_size, 0.0),
            (self.page_reverb.knob_predelay, 0.0),
            (self.page_reverb.knob_predelay_mix, 0.0)
        ]
        self._apply_knob_animations(knobs, enabled)
        
        def emit_signal():
            if hasattr(self, 'btn_reverb') and self.btn_reverb.isChecked() == checked:
                try: self.toggle_reverb.emit(bool(checked))
                except: pass
        if checked:
            anim = getattr(self.page_reverb.knob_damp, '_val_anim', None)
            if anim and anim.state() == QVariantAnimation.State.Running:
                anim.finished.connect(emit_signal)
            else:
                emit_signal()
        else:
            emit_signal()

    def on_bands_toggle(self, checked):
        enabled = bool(checked) and self.btn_master.isChecked()
        self.eq_frame.setEnabled(enabled)
        self._set_widget_dim(self.eq_frame, enabled)
        self.update_visualizer_eq()
        
        def emit_signal():
            if hasattr(self, 'btn_bands') and self.btn_bands.isChecked() == checked:
                try: self.toggle_eq_bands.emit(bool(checked))
                except: pass
        if checked:
            anim = getattr(self.eq_frame, '_dim_anim', None)
            if anim and anim.state() == QPropertyAnimation.State.Running:
                anim.finished.connect(emit_signal)
            else:
                emit_signal()
        else:
            emit_signal()

    def on_master_toggle(self, checked):
        self._apply_master_visual(checked)
        self.update_visualizer_tone()
        self.update_visualizer_eq()
        
        def emit_signal():
            if hasattr(self, 'btn_master') and self.btn_master.isChecked() == checked:
                try: self.toggle_master_dsp.emit(bool(checked))
                except: pass
        if checked:
            anim = getattr(self.visualizer_frame, '_dim_anim', None)
            if anim and anim.state() == QPropertyAnimation.State.Running:
                anim.finished.connect(emit_signal)
            else:
                emit_signal()
        else:
            emit_signal()

    def on_tone_toggle(self, checked):
        enabled = bool(checked) and self.btn_master.isChecked()
        self.knob_bass.setEnabled(enabled)
        self.knob_treble.setEnabled(enabled)
        self._set_widget_dim(self.knob_bass, enabled)
        self._set_widget_dim(self.knob_treble, enabled)
        
        knobs = [
            (self.knob_bass, 0.0),
            (self.knob_treble, 0.0)
        ]
        self._apply_knob_animations(knobs, enabled)
        
        self.update_visualizer_tone()
        
        def emit_signal():
            if hasattr(self, 'btn_tone') and self.btn_tone.isChecked() == checked:
                try: self.toggle_knobs.emit(bool(checked))
                except: pass
        if checked:
            anim = getattr(self.knob_bass, '_val_anim', None)
            if anim and anim.state() == QVariantAnimation.State.Running:
                anim.finished.connect(emit_signal)
            else:
                emit_signal()
        else:
            emit_signal()

    def _set_widget_dim(self, widget, enabled, disabled_opacity=0.45):
        if widget is None:
            return

        effect = widget.graphicsEffect()
        
        # Dacă elementul este deja activ și nu are efect de opacitate, nu facem nimic
        if enabled and effect is None:
            return
            
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            # Dacă abia a fost creat, plecăm de la opacitate maximă (dacă dezactivăm) sau viceversa
            effect.setOpacity(1.0 if not enabled else disabled_opacity)
            widget.setGraphicsEffect(effect)
            
        current_opacity = effect.opacity()
        target_opacity = 1.0 if enabled else disabled_opacity
        
        if current_opacity == target_opacity:
            if enabled: widget.setGraphicsEffect(None)
            return
            
        # Oprim o eventuală animație aflată în derulare
        if hasattr(widget, '_dim_anim') and widget._dim_anim.state() == QPropertyAnimation.State.Running:
            widget._dim_anim.stop()
            
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(250) # Sincronizat cu graficul (250ms)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.setStartValue(current_opacity)
        anim.setEndValue(target_opacity)
        
        if enabled:
            # Când elementul se aprinde la 100%, eliminăm masca pentru performanță
            anim.finished.connect(lambda w=widget, e=effect: w.setGraphicsEffect(None) if e.opacity() >= 0.99 else None)
            
        widget._dim_anim = anim
        anim.start()

    def _apply_knob_animations(self, knobs_with_zeros, enabled):
        for knob, zero_val in knobs_with_zeros:
            if not enabled:
                # Salvăm valoarea înainte de a o duce la 0, doar dacă nu e deja "zeroed"
                if not getattr(knob, '_is_zeroed', False):
                    knob._saved_value = knob.value()
                knob._is_zeroed = True
                self._animate_value(knob, zero_val, is_activating=False)
            else:
                # Restaurăm valoarea salvată și animăm spre ea
                knob._is_zeroed = False
                target = getattr(knob, '_saved_value', knob.value())
                self._animate_value(knob, target, is_activating=True)

    def _animate_value(self, widget, target_value, is_activating=False):
        if hasattr(widget, '_val_anim') and widget._val_anim.state() == QVariantAnimation.State.Running:
            widget._val_anim.stop()
            
        anim = QVariantAnimation(widget)
        anim.setDuration(400) # 400ms pentru o mișcare lină și naturală
        
        if is_activating:
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic) # Pleacă lin, prinde viteză, se oprește lin
        else:
            anim.setEasingCurve(QEasingCurve.Type.OutCubic) # Pleacă rapid, se oprește lin
            
        anim.setStartValue(float(widget.value()))
        anim.setEndValue(float(target_value))
        
        anim.valueChanged.connect(lambda v, w=widget: w.setValue(v))
        
        widget._val_anim = anim
        # 🔥 Pornim animația INSTANT, fără niciun delay
        anim.start()
        
    def animate_widget_sweep_visual(self, widget, target_value, delay=0, start_val=0):
        if hasattr(widget, '_val_anim') and widget._val_anim.state() == QVariantAnimation.State.Running:
            widget._val_anim.stop()
            
        widget._target_sweep_value = target_value
        
        # Setează vizual de la punctul start, blocând semnalele pentru a nu corupe audio-ul real activ.
        widget.blockSignals(True)
        if isinstance(widget, QSlider) or isinstance(target_value, int):
            widget.setValue(int(start_val))
        else:
            widget.setValue(float(start_val))
        widget.blockSignals(False)
        
        anim = QVariantAnimation(widget)
        anim.setDuration(600)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(float(start_val))
        anim.setEndValue(float(target_value))
        
        def on_val_change(v):
            widget.blockSignals(True)
            if isinstance(widget, QSlider) or isinstance(target_value, int):
                widget.setValue(int(v))
            else:
                widget.setValue(float(v))
            widget.blockSignals(False)
            
            if hasattr(self, 'update_visualizer_tone') and widget in [getattr(self, 'knob_bass', None), getattr(self, 'knob_treble', None)]:
                self.update_visualizer_tone()
            if hasattr(self, 'update_visualizer_eq') and hasattr(self, 'sliders') and widget in self.sliders:
                self.update_visualizer_eq()
                
            if widget == getattr(self, 'slider_preamp', None) and hasattr(self, 'lbl_pre_val'):
                self.lbl_pre_val.setText(f"{int(v)/2:g}")
            if hasattr(widget, '_lbl_val_ref'):
                widget._lbl_val_ref.setText(f"{int(v)/2:g}")

        anim.valueChanged.connect(on_val_change)
        widget._val_anim = anim
        
        if delay > 0:
            QTimer.singleShot(delay, anim.start)
        else:
            anim.start()

    def force_restore_true_values_for_save(self):
        """ Restaurăm valorile reale instant înainte de salvarea setărilor la ieșire. """
        knobs = [
            self.knob_bass, self.knob_treble,
            self.page_spatial.knob_tempo, self.page_spatial.knob_balance,
            self.page_spatial.knob_stereo, self.page_spatial.knob_low_bypass,
            self.page_reverb.knob_damp, self.page_reverb.knob_filter,
            self.page_reverb.knob_fade, self.page_reverb.knob_size,
            self.page_reverb.knob_predelay, self.page_reverb.knob_predelay_mix
        ]
        if hasattr(self, 'slider_preamp'):
            knobs.append(self.slider_preamp)
            
        for knob in knobs:
            if hasattr(knob, '_val_anim') and knob._val_anim.state() == QVariantAnimation.State.Running:
                knob._val_anim.stop()
                if hasattr(knob, '_target_sweep_value'):
                    knob.blockSignals(True)
                    knob.setValue(knob._target_sweep_value)
                    knob.blockSignals(False)
            elif getattr(knob, '_is_zeroed', False) and hasattr(knob, '_saved_value'):
                if hasattr(knob, '_val_anim'): knob._val_anim.stop()
                knob.blockSignals(True)
                knob.setValue(knob._saved_value)
                knob.blockSignals(False)
                
        if hasattr(self, 'sliders'):
            for slider in self.sliders:
                if hasattr(slider, '_val_anim') and slider._val_anim.state() == QVariantAnimation.State.Running:
                    slider._val_anim.stop()
                    if hasattr(slider, '_target_sweep_value'):
                        slider.blockSignals(True)
                        slider.setValue(slider._target_sweep_value)
                        slider.blockSignals(False)

    def on_preamp_change(self, value):
        real_val = value / 2.0
        self.lbl_pre_val.setText(f"{real_val:g}")
        self.preamp_changed.emit(real_val)

    def resizeEvent(self, event):
        # 🔥 FIX: Nu regenerăm benzile dacă tab-ul nu e vizibil (ex: în timpul tranziției)
        if not self.isVisible(): return

        # Dacă lățimea scade sub 700px, trecem pe layout orizontal (listă)
        should_be_horizontal = self.width() < 700
        if should_be_horizontal != self.is_horizontal_layout:
            self.is_horizontal_layout = should_be_horizontal
            self.regenerate_bands(self.current_band_count)
        super().resizeEvent(event)