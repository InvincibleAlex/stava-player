import os
import platform
from PyQt6.QtGui import QColor

# --- DEFINIREA PALETELOR DE CULORI ---
THEME_PALETTES = {
    "Default": {
        "MENU_BG": "#252525", "FG": "#FFFFFF",
        "TEXT_SECONDARY": "#AAAAAA", "PRIMARY": "#00AAFF", 
        "SECONDARY": "#444444", "ACCENT": "#0077CC", 
        "BORDER": "#333333", "ICON_COLOR": "#D3D3D3",
        "BACKGROUND": "#181818" 
    },
    "Dark": {
        "MENU_BG": "#252525", "FG": "#FFFFFF",
        "TEXT_SECONDARY": "#AAAAAA", "PRIMARY": "#00AAFF", 
        "SECONDARY": "#444444", "ACCENT": "#0077CC", 
        "BORDER": "#333333", "ICON_COLOR": "#D3D3D3",
        "BACKGROUND": "#121212"
    },
    "Light": {
        "MENU_BG": "#E0E0E0", "FG": "#000000",
        "TEXT_SECONDARY": "#555555", "PRIMARY": "#007AFF", 
        "SECONDARY": "#929292", "ACCENT": "#0056B3", 
        "BORDER": "#727272", "ICON_COLOR": "#333333",
        "BACKGROUND": "#F5F5F5"
    },
    "Aqua": {
        "MENU_BG": "#00BCD4", "FG": "#E0F7FA",
        "TEXT_SECONDARY": "#80DEEA", "PRIMARY": "#00E5FF", 
        "SECONDARY": "#006064", "ACCENT": "#0097A7", 
        "BORDER": "#006064", "ICON_COLOR": "#80DEEA",
        "BACKGROUND": "#002147"   
    }
}

def get_stylesheet(theme_name):
    colors = THEME_PALETTES.get(theme_name, THEME_PALETTES["Dark"])
    
    if platform.system() == "Darwin":
        font_family = '".AppleSystemUIFont", "Helvetica Neue", "Arial", sans-serif'
    elif platform.system() == "Windows":
        font_family = '"Segoe UI", "Meiryo", "Noto Sans", "Noto Sans CJK JP", "Arial Unicode MS", sans-serif'
    else:
        font_family = '"Noto Sans", "Ubuntu", "Segoe UI", sans-serif'

    return f"""
    QMainWindow {{
        background: transparent; /* Transparent pentru a vedea bg_label */
        color: {colors["FG"]};
    }}
    
    QWidget {{
        background-color: transparent; /* Lăsăm gradientul din Main să se vadă */
        color: {colors["FG"]};
        font-family: {font_family};
    }}

    /* --- MENIUL DE JOS (NAVBAR) --- */
    /* Acum stilizăm un QFrame simplu, nu TabWidget */
    NavBar {{
        background-color: {colors["MENU_BG"]};
        border-radius: 30px; 
            
        
    }}

    /* --- BUTOANELE DIN NAVBAR --- */
    /* Selectăm strict butoanele din meniu */
    NavBar > QPushButton {{
        background-color: transparent;
        border: none;
        border-radius: 25px; /* Rotunjire butoane la hover */
        margin: 0px;
        padding: 0px;
    }}

    /* Efect Hover (Când treci cu mouse-ul) */
    NavBar > QPushButton:hover {{
        background-color: rgba(255, 255, 255, 0.1);
    }}

    /* Efect Checked (Tab-ul activ) */
    NavBar > QPushButton:checked {{
        background-color: rgba(255, 255, 255, 0.2);
    }}

    /* --- RESTUL ELEMENTELOR UI (Neschimbate) --- */
    
    QPushButton {{ 
        /* Butoane generice din restul aplicației */
        background-color: transparent; /* DEBUG: Removed BG */
        border: 1px solid {colors["BORDER"]};
        color: {colors["FG"]};
        padding: 5px;
        border-radius: 20px;
        outline: none; /* Elimină conturul de focus global */
    }}
    
    QSlider::groove:horizontal {{
        border: 1px solid {colors["BORDER"]};
        height: 6px;
        background: transparent; /* DEBUG: Removed BG */
        margin: 2px 0;
        border-radius: 3px;
    }}

    QSlider::sub-page:horizontal {{
        background: {colors["PRIMARY"]};
        border-top-left-radius: 3px;
        border-bottom-left-radius: 6px;
    }}

    QSlider::handle:horizontal,
    QSlider::handle:horizontal:hover,
    QSlider::handle:horizontal:pressed {{
        background: {colors["PRIMARY"]};
        border: 1px solid transparent;
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}

    QListWidget {{
        background-color: transparent;
        border: none;
    }}
    QListWidget::item {{
        color: {colors["FG"]};
        border-bottom: 1px solid {colors["BORDER"]};
        padding: 5px;
    }}
    QListWidget::item:selected {{
        background-color: {colors["MENU_BG"]};
        border-left: 3px solid {colors["PRIMARY"]};
    }}
    
    QLineEdit {{
        background-color: rgba(0, 0, 0, 0.2);
        border: 1px solid {colors["BORDER"]};
        color: {colors["FG"]};
        border-radius: 5px;
        padding: 5px;
    }}

    QComboBox {{
        background-color: {colors["MENU_BG"]};
        color: {colors["FG"]};
        border: 1px solid {colors["BORDER"]};
        border-radius: 8px;
        padding: 4px 10px;
    }}
    QComboBox:hover {{
        border: 1px solid {colors["PRIMARY"]};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {colors["MENU_BG"]};
        color: {colors["FG"]};
        border: 1px solid {colors["BORDER"]};
        selection-background-color: {colors["PRIMARY"]};
        selection-color: {colors["FG"]};
        outline: none;
    }}

    /* --- SCROLLBAR (Vertical) --- */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {colors["FG"]};
        min-height: 20px;
        border-radius: 3px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    /* --- SLIDERS (Vertical EQ) --- */
    /* Doar definim geometria, desenarea e custom în EqBandSlider */
    QSlider::groove:vertical {{
        width: 3px;
        background: transparent;
    }}
    QSlider::handle:vertical,
    QSlider::handle:vertical:hover,
    QSlider::handle:vertical:pressed {{
        height: 25px;
        width: 40px;
        margin: 0 -18.5px; /* (40-3)/2 */
        background: transparent;
    }}
    
    /* --- SCROLLBAR (Horizontal) --- */
    QScrollBar:horizontal {{
        border: none;
        background: transparent;
        height: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {colors["FG"]};
        min-width: 20px;
        border-radius: 3px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}

    /* --- CUSTOM WIDGETS --- */
    SquareFrame {{
        background: transparent;
        border: none;
    }}
    """

def get_pill_style(bg_color, radius):
    """ Returnează stilul pentru containerele tip 'pastilă' """
    return f"background-color: {bg_color}; border-radius: {radius}px;"

def get_label_style(size, color, bold=False):
    size = max(1, int(size))
    weight = "bold" if bold else "normal"
    return f"font-size: {size}px; font-weight: {weight}; color: {color}; background: transparent; border: none;"

def get_pill_bg_color(theme_name):
    """ Calculează culoarea semi-transparentă pentru pastile """
    colors = THEME_PALETTES.get(theme_name, THEME_PALETTES["Dark"])
    menu_bg = colors.get("MENU_BG", "#252525")
    c = QColor(menu_bg)
    c.setAlphaF(0.2)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alphaF()})"
