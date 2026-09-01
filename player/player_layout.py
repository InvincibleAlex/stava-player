from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSizePolicy
from PyQt6.QtCore import Qt, QSize, QTimer
from core.utils import IconHelper
import core.themes as themes

class PlayerLayoutManager:
    """
    Clasă utilitară pentru a gestiona construcția layout-urilor complexe
    din PlayerTab, reducând numărul de linii din fișierul principal.
    """
    @staticmethod
    def setup_full_layout(tab):
        tab.rescue_widgets()
        
        if tab.content_widget:
            tab.main_layout.removeWidget(tab.content_widget)
            tab.content_widget.deleteLater()

        tab.content_widget = QWidget()
        tab.main_layout.addWidget(tab.content_widget)
        
        cw_layout = QVBoxLayout(tab.content_widget)
        cw_layout.setContentsMargins(0, 0, 0, 0)
        cw_layout.addStretch()
        
        tab.player_container = QWidget()
        tab.player_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cw_layout.addWidget(tab.player_container)
        
        layout = QHBoxLayout(tab.player_container)
        layout.setContentsMargins(30, 0, 30, 0)
        layout.setSpacing(30)
        
        tab.artwork_container.setMinimumWidth(100)
        layout.addWidget(tab.artwork_container, stretch=1)
        
        cw_layout.addStretch()
        
        right_col = QWidget()
        right_col.setMinimumWidth(300)
        r_layout = QVBoxLayout()
        r_layout.setContentsMargins(0,0,0,0)
        r_layout.setSpacing(20)
        
        # 1. INFO CONTAINER
        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(5)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        info_layout.addWidget(tab.title_pill)
        info_layout.addWidget(tab.artist_pill)
        r_layout.addWidget(info_container, stretch=0)
        
        # 2. OVERLAY CONTAINER (Waveform + Buttons)
        overlay_container = QWidget()
        overlay_grid = QGridLayout(overlay_container)
        overlay_grid.setContentsMargins(0, 0, 0, 0)
        overlay_grid.setSpacing(0)
        
        tab.waveform.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        overlay_grid.addWidget(tab.waveform, 0, 0)
        
        from .player_widgets import ClickThroughContainer
        transport_widget = ClickThroughContainer(tab.waveform)
        transport_widget.setStyleSheet("background: transparent;")
        
        t_layout = QHBoxLayout(transport_widget)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.setSpacing(20)
        t_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        t_layout.addWidget(tab.btn_prev)
        t_layout.addWidget(tab.btn_play)
        t_layout.addWidget(tab.btn_next)
        
        overlay_grid.addWidget(transport_widget, 0, 0, Qt.AlignmentFlag.AlignCenter)
        r_layout.addWidget(overlay_container, stretch=1)
        
        # 3. Path Pill
        r_layout.addWidget(tab.path_pill, 0, Qt.AlignmentFlag.AlignCenter)
        
        # 4. Extra Buttons Toolbar
        toolbar_widget = QWidget()
        toolbar_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 10, 0, 0)
        toolbar_layout.setSpacing(10)
        toolbar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        toolbar_layout.addWidget(tab._create_pill_widget(tab.btn_extra_1))
        toolbar_layout.addWidget(tab._create_pill_widget(tab.btn_extra_2))
        toolbar_layout.addSpacing(20) 
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(tab._create_pill_widget(tab.btn_repeat))
        toolbar_layout.addWidget(tab._create_pill_widget(tab.btn_shuffle))

        r_layout.addWidget(toolbar_widget)
        right_col.setLayout(r_layout)
        layout.addWidget(right_col, stretch=1)

    @staticmethod
    def setup_mini_layout(tab):
        tab.rescue_widgets()
        
        if tab.content_widget:
            tab.main_layout.removeWidget(tab.content_widget)
            tab.content_widget.deleteLater()

        tab.content_widget = QWidget()
        tab.main_layout.addWidget(tab.content_widget)
        
        layout = QVBoxLayout(tab.content_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10) 

        tab.artwork_container.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
        tab.artwork_container.setMinimumWidth(0) 
        layout.addWidget(tab.artwork_container, stretch=1) 
        
        # --- INFO PILLS ---
        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 5, 0, 5)
        info_layout.setSpacing(5)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        info_layout.addWidget(tab.title_pill)
        info_layout.addWidget(tab.artist_pill)
        layout.addWidget(info_container)
        
        # --- TOOLBAR ---
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 5, 0, 0)
        toolbar.setSpacing(10)
        
        toolbar.addWidget(tab._create_pill_widget(tab.btn_extra_1))
        toolbar.addWidget(tab._create_pill_widget(tab.btn_extra_2))
        toolbar.addStretch() 
        toolbar.addWidget(tab._create_pill_widget(tab.btn_repeat))
        toolbar.addWidget(tab._create_pill_widget(tab.btn_shuffle))
        layout.addLayout(toolbar)

        # Overlay
        overlay_container = QWidget()
        overlay_grid = QGridLayout(overlay_container)
        overlay_grid.setContentsMargins(0, 0, 0, 0)
        overlay_grid.setSpacing(0)

        tab.waveform.setMinimumHeight(0) 
        tab.waveform.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        overlay_grid.addWidget(tab.waveform, 0, 0)

        from .player_widgets import ClickThroughContainer
        controls_widget = ClickThroughContainer(tab.waveform)
        controls_widget.setStyleSheet("background: transparent;")
        c_layout = QHBoxLayout(controls_widget)
        c_layout.setSpacing(10)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        c_layout.addWidget(tab.btn_prev)
        c_layout.addWidget(tab.btn_play)
        c_layout.addWidget(tab.btn_next)
        
        overlay_grid.addWidget(controls_widget, 0, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(overlay_container, stretch=1)