from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QSlider, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt

from tabs.tab_player import PlayerTab
from tabs.tab_eq import EqTab
from tabs.tab_settings import SettingsTab
from playlist.tab_playlist import PlaylistTab
from ui.ui_navbar import NavBar

class MainWindowBuilder:
    def __init__(self, main_app):
        self.main = main_app

    def build_layout(self):
        central_widget = QWidget()
        self.main.setCentralWidget(central_widget)
        
        self.main.global_layout = QVBoxLayout()
        self.main.global_layout.setContentsMargins(0, 0, 0, 10)
        self.main.global_layout.setSpacing(0)
        central_widget.setLayout(self.main.global_layout)
        
        self.main.content_area = QWidget()
        self.main.split_layout = QHBoxLayout()
        self.main.split_layout.setContentsMargins(0, 0, 0, 0)
        self.main.split_layout.setSpacing(0)
        self.main.content_area.setLayout(self.main.split_layout)
        
        self.main.ui_player = PlayerTab(self.main.audio)
        self.main.split_layout.addWidget(self.main.ui_player)
        
        self.main.right_stack = QStackedWidget()
        self.main.ui_eq = None
        self.main.ui_settings = None
        self.main.ui_playlist = PlaylistTab()
        self.main.ui_playlist.set_animation_manager(self.main.anim_manager) 
        self.main.ui_playlist.set_audio_engine(self.main.audio) 
        
        self.main.placeholder_eq = QWidget()
        self.main.placeholder_settings = QWidget()
        
        self.main.right_stack.addWidget(self.main.placeholder_eq)       
        self.main.right_stack.addWidget(self.main.ui_playlist) 
        self.main.right_stack.addWidget(self.main.placeholder_settings) 
        
        self.main.split_layout.addWidget(self.main.right_stack)
        self.main.global_layout.addWidget(self.main.content_area)

    def setup_bottom_bar(self):
        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(20, 0, 20, 0) 
        bottom_layout.addStretch(1)

        self.main.navbar = NavBar()
        self.main.navbar.currentChanged.connect(self.main.nav_controller.on_tab_changed)
        bottom_layout.addWidget(self.main.navbar)

        volume_container = QWidget()
        vol_layout = QHBoxLayout(volume_container)
        vol_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.main.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.main.volume_slider.setFixedWidth(120)
        self.main.volume_slider.setRange(0, 100)
        self.main.volume_slider.setToolTip("Master Volume")
        
        self.main.vol_effect = QGraphicsOpacityEffect(self.main.volume_slider)
        self.main.vol_effect.setOpacity(0.5)
        self.main.volume_slider.setGraphicsEffect(self.main.vol_effect)

        def vol_enter(event):
            self.main.vol_effect.setOpacity(1.0)
            QSlider.enterEvent(self.main.volume_slider, event) 
        def vol_leave(event):
            self.main.vol_effect.setOpacity(0.5)
            QSlider.leaveEvent(self.main.volume_slider, event)
            
        self.main.volume_slider.enterEvent = vol_enter
        self.main.volume_slider.leaveEvent = vol_leave
        
        vol_layout.addWidget(self.main.volume_slider)
        bottom_layout.addWidget(volume_container, 1) 
        self.main.global_layout.addWidget(bottom_container)

    def init_deferred_ui(self):
        """ Crează tab-urile ascunse (Lazy Loading) """
        self.main.ui_eq = EqTab()
        self.main.ui_settings = SettingsTab()

        self.main.right_stack.insertWidget(0, self.main.ui_eq)
        self.main.right_stack.removeWidget(self.main.placeholder_eq)
        self.main.placeholder_eq.deleteLater()
        
        self.main.right_stack.insertWidget(2, self.main.ui_settings)
        self.main.right_stack.removeWidget(self.main.placeholder_settings)
        self.main.placeholder_settings.deleteLater()