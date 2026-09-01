import os
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup, QFrame, QLayout
from PyQt6.QtCore import QSize, pyqtSignal, Qt
from core.utils import IconHelper
import core.themes as themes

class NavBar(QFrame):
    # Semnalul care anunță MainApp să schimbe pagina (trimite indexul 0, 1, 2, 3)
    currentChanged = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        
        # --- CONFIGURARE LAYOUT ---
        self.layout = QHBoxLayout()
        # Padding: Stânga, Sus, Dreapta, Jos
        self.layout.setContentsMargins(5, 5, 5, 5) 
        self.layout.setSpacing(10) 
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Setăm mărimea containerului să fie fixă pe conținut (elastică automat)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        
        self.setLayout(self.layout)

        # --- LOGICA DE GRUP (Pentru excludere vizuală) ---
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True) 

        self.buttons = []
        self.icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'icons')
        
        self.icon_colors = {
            "Dark": "#D3D3D3", 
            "Light": "#333333", 
            "Aqua": "#001f2b"
        }
        
        self.current_zoom = 1.0
        self.current_theme = "Dark"

        # --- ADĂUGARE BUTOANE ---
        # 0: Player
        self.add_nav_button(0, "headphones-solid-full.svg")
        # 1: EQ
        self.add_nav_button(1, "audio-lines.svg")
        # 2: Playlist
        self.add_nav_button(2, "folder-solid-full.svg")
        # 3: Settings
        self.add_nav_button(3, "gear-solid-full.svg")
        
        # Activăm primul buton la pornire
        self.buttons[0].setChecked(True)

    def add_nav_button(self, id, icon_name):
        btn = QPushButton()
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus) # Elimină conturul punctat la click
        btn.setCheckable(True)
        btn.setFixedSize(80, 50) 
        btn.setIconSize(QSize(24, 24))
        btn.setProperty("icon_name", icon_name)
        
        # 🔥 FIX: Conectăm direct CLICK-ul butonului la funcția noastră
        # Folosim lambda pentru a trimite ID-ul corect
        btn.clicked.connect(lambda checked, idx=id: self.on_button_clicked(idx))
        
        self.layout.addWidget(btn)
        self.btn_group.addButton(btn, id)
        self.buttons.append(btn)

    def on_button_clicked(self, id):
        # Debugging: Vezi în consolă dacă apare acest mesaj când apeși
        print(f"DEBUG: NavBar Clicked -> Index {id}")
        self.currentChanged.emit(id)

    def currentIndex(self):
        return self.btn_group.checkedId()

    def update_theme(self, theme_name):
        """ Reculorează iconițele """
        self.current_theme = theme_name
        color_hex = self.icon_colors.get(theme_name, "#D3D3D3")
        
        for btn in self.buttons:
            icon_name = btn.property("icon_name")
            if icon_name:
                path = os.path.join(self.icons_dir, icon_name)
                colored_icon = IconHelper.get_colored_icon(path, color_hex)
                btn.setIcon(colored_icon)
        
        self.update_style()
        return color_hex

    def apply_zoom(self, factor):
        self.current_zoom = factor
        """ Redimensionează butoanele din navbar în funcție de zoom """
        # Dimensiuni de bază: 80x50, Icon 24x24
        w = int(80 * factor)
        h = int(50 * factor)
        icon_s = int(24 * factor)
        
        for btn in self.buttons:
            btn.setFixedSize(w, h)
            btn.setIconSize(QSize(icon_s, icon_s))
            
        self.update_style()

    def update_style(self):
        # Calculăm înălțimea totală (Buton + Margini)
        btn_h = int(50 * self.current_zoom)
        total_h = btn_h + 10 # 5px padding sus/jos
        radius = total_h // 2
        btn_radius = btn_h // 2
        
        colors = themes.THEME_PALETTES.get(self.current_theme, themes.THEME_PALETTES["Dark"])
        bg = colors.get("MENU_BG", "#252525")
        
        self.setStyleSheet(f"""
            NavBar {{ 
                background-color: {bg}; 
                border-radius: {radius}px; 
            }}
            NavBar > QPushButton {{
                border-radius: {btn_radius}px;
            }}
        """)