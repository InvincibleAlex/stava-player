from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QSizePolicy
from Eq.knobs import AudioKnob

class SpatialPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # --- TOP CONTAINER (grupuri separate pentru controale) ---
        top_container = QWidget()
        top_layout = QHBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(14)

        # Container 1: Tempo + Stereo Expand
        stereo_container = QWidget()
        stereo_layout = QHBoxLayout(stereo_container)
        stereo_layout.setContentsMargins(0, 0, 0, 0)
        stereo_layout.setSpacing(22)
        
        # Tempo
        # Interval 0.0 - 2.0 pentru ca 1.0 să fie la mijloc (sus). Pas 0.10 la scroll.
        self.knob_tempo = AudioKnob("TEMPO", 0.00, 2.00, step=0.05, orientation='vertical', format_str="{:.2f}x")
        self.knob_tempo.setValue(1.00) # Default 1.00x (Normal)
        self.knob_tempo.setMinimumSize(110, 150)
        stereo_layout.addWidget(self.knob_tempo)

        # Stereo Expand
        self.knob_stereo = AudioKnob("STEREO EXPAND", 0, 100, orientation='vertical')
        self.knob_stereo.setValue(0)
        self.knob_stereo.setMinimumSize(110, 150)
        stereo_layout.addWidget(self.knob_stereo)
        top_layout.addWidget(stereo_container, 2)

        # Container 2: Low Bypass
        low_bypass_container = QWidget()
        low_bypass_layout = QHBoxLayout(low_bypass_container)
        low_bypass_layout.setContentsMargins(0, 0, 0, 0)
        low_bypass_layout.setSpacing(0)

        # Low Bypass (Wider): 0 Hz .. 20 kHz, knob mai mic
        self.knob_low_bypass = AudioKnob("LOW BYPASS", 0, 20000, step=100.0, orientation='vertical', format_str="{:.0f} Hz")
        self.knob_low_bypass.setValue(0)
        self.knob_low_bypass.set_zoom_factor(0.48)
        self.knob_low_bypass.setMinimumSize(76, 98)
        self.knob_low_bypass.knob.setMinimumSize(52, 52)
        low_bypass_layout.addStretch(1)
        low_bypass_layout.addWidget(self.knob_low_bypass)
        low_bypass_layout.addStretch(1)
        top_layout.addWidget(low_bypass_container, 1)
        
        layout.addWidget(top_container, 1)

        # --- BOTTOM CONTAINER (Balance + FX Knobs) ---
        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(14)
        bottom_layout.addStretch()

        # Balance
        self.knob_balance = AudioKnob("BALANCE", 0, 100)
        self.knob_balance.setValue(50) # Default 50% (Centru)
        bottom_layout.addWidget(self.knob_balance)
        
        bottom_layout.addStretch()
        layout.addWidget(bottom_container, 1)

    def update_theme_colors(self, colors):
        border = colors.get("SECONDARY", "#444444")
        fg = colors.get("FG", "#FFFFFF")
        for child in self.findChildren(AudioKnob):
            child.set_colors("#1C1C1C", border, title_color=fg)

    def set_zoom_factor(self, factor):
        z = max(0.6, float(factor))
        for child in self.findChildren(AudioKnob):
            if child is getattr(self, 'knob_low_bypass', None):
                child.set_zoom_factor(max(0.45, z * 0.58))
            elif child in (getattr(self, 'knob_tempo', None), getattr(self, 'knob_stereo', None)):
                child.set_zoom_factor(max(0.9, z * 1.18))
            else:
                child.set_zoom_factor(z)

class ReverbPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # Layout principal pentru centrare
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container Grid pentru cele 6 knob-uri
        grid_container = QWidget()
        grid_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        grid = QGridLayout(grid_container)
        grid.setSpacing(5)
        grid.setContentsMargins(0, 0, 0, 0)
        
        # Setăm stretch factors pentru ca celulele să se extindă uniform
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        
        # --- RÂNDUL 1 ---
        self.knob_damp = AudioKnob("DAMP", 0, 100)
        self.knob_damp.setValue(0)
        grid.addWidget(self.knob_damp, 0, 0)
        
        self.knob_filter = AudioKnob("FILTER", 0, 100)
        self.knob_filter.setValue(0)
        grid.addWidget(self.knob_filter, 0, 1)
        
        self.knob_fade = AudioKnob("FADE", 0, 100)
        self.knob_fade.setValue(0)
        grid.addWidget(self.knob_fade, 0, 2)
        
        # --- RÂNDUL 2 ---
        self.knob_predelay = AudioKnob("PRE-DELAY", 0, 100)
        self.knob_predelay.setValue(0)
        grid.addWidget(self.knob_predelay, 1, 0)
        
        self.knob_predelay_mix = AudioKnob("PRE-DELAY MIX", 0, 100)
        self.knob_predelay_mix.setValue(0)
        grid.addWidget(self.knob_predelay_mix, 1, 1)
        
        self.knob_size = AudioKnob("SIZE", 0, 100)
        self.knob_size.setValue(0)
        grid.addWidget(self.knob_size, 1, 2)

        main_layout.addStretch()
        main_layout.addWidget(grid_container, 1) # Stretch 1 pentru a permite extinderea
        main_layout.addStretch()

    def update_theme_colors(self, colors):
        border = colors.get("SECONDARY", "#444444")
        fg = colors.get("FG", "#FFFFFF")
        for child in self.findChildren(AudioKnob):
            child.set_colors("#1C1C1C", border, title_color=fg)

    def set_zoom_factor(self, factor):
        z = max(0.6, float(factor))
        for child in self.findChildren(AudioKnob):
            child.set_zoom_factor(z)