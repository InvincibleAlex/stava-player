import os
import platform
import sys
from collections import OrderedDict
from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon, QImage, QPainterPath, QFont
from PyQt6.QtCore import Qt, QRectF, QSize, QStandardPaths
from PyQt6.QtSvg import QSvgRenderer

APP_NAME = "Stava Player"


def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_runtime_data_dir():
    if getattr(sys, 'frozen', False):
        data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if not data_dir:
            if sys.platform == 'darwin':
                data_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
            else:
                safe_name = APP_NAME.lower().replace(" ", "_")
                data_dir = os.path.join(os.path.expanduser("~"), f".{safe_name}")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    return get_project_root()


def get_settings_path():
    return os.path.join(get_runtime_data_dir(), "settings.ini")


def get_cache_root():
    return os.path.join(get_runtime_data_dir(), "cache")

class IconHelper:
    _cache = OrderedDict() # Cache limitat pentru (path, color_hex, size) -> QIcon
    MAX_CACHE_SIZE = 150

    @staticmethod
    def get_colored_icon(path, color_hex, size=None):
        """
        Încarcă un SVG/PNG, îl colorează și returnează QIcon.
        Folosește caching pentru performanță.
        """
        # Cheie unică pentru cache
        key = (path, color_hex, size)
        if key in IconHelper._cache:
            # Mutăm la final (ca fiind cel mai recent folosit)
            IconHelper._cache.move_to_end(key)
            return IconHelper._cache[key]

        if not os.path.exists(path):
            return QIcon()

        if size:
            # 🔥 FIX: Randăm SVG-ul la rezoluție triplă pentru High DPI (Retina/4K)
            scale = 3.0
            pix = QIcon(path).pixmap(int(size * scale), int(size * scale))
        else:
            pix = QPixmap(path)
            
        if pix.isNull(): 
            return QIcon()

        # Colorare
        painter = QPainter(pix)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pix.rect(), QColor(color_hex))
        painter.end()

        # Setăm DPR după colorare pentru claritate pe High DPI
        if size:
            pix.setDevicePixelRatio(scale)

        icon = QIcon(pix)
        IconHelper._cache[key] = icon
        
        # Curățăm cele mai vechi elemente dacă depășim limita
        if len(IconHelper._cache) > IconHelper.MAX_CACHE_SIZE:
            IconHelper._cache.popitem(last=False)
            
        return icon

    @staticmethod
    def apply_round_button_style(btn, size, bg_color=None, border_color=None, hover_bg_color=None, hover_border_color=None, pressed_bg_color=None):
        """ Aplică stilul rotund standard pentru butoane """
        btn.setFixedSize(size, size)
        radius = size // 2
        bg_color = bg_color or "rgba(255, 255, 255, 0.1)"
        border_color = border_color or "rgba(255, 255, 255, 0.2)"
        hover_bg_color = hover_bg_color or "rgba(255, 255, 255, 0.3)"
        hover_border_color = hover_border_color or "rgba(255, 255, 255, 0.5)"
        pressed_bg_color = pressed_bg_color or "rgba(255, 255, 255, 0.5)"
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                border-radius: {radius}px;
                border: 1px solid {border_color};
                outline: none;
            }}
            QPushButton:hover {{
                background-color: {hover_bg_color};
                border: 1px solid {hover_border_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_bg_color};
            }}
        """)

    @staticmethod
    def crop_to_rounded_square(pixmap, target_size, radius, scale=2.0):
        """ Decupează o imagine pătrată cu colțuri rotunjite (High DPI Ready) """
        if not pixmap or pixmap.isNull(): return QPixmap()
        
        # Calculăm dimensiunea fizică (dublă pentru claritate)
        phys_size = int(target_size * scale)
        phys_radius = int(radius * scale)
        
        img = pixmap.toImage()
        size = min(img.width(), img.height())
        rect = QRectF((img.width() - size) / 2, (img.height() - size) / 2, size, size).toRect()
        cropped = img.copy(rect)
        
        scaled = cropped.scaled(phys_size, phys_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        out_img = QImage(phys_size, phys_size, QImage.Format.Format_ARGB32)
        out_img.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(out_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, phys_size, phys_size, phys_radius, phys_radius)
        painter.setClipPath(path)
        painter.drawImage(0, 0, scaled)
        painter.end()
        
        # Setăm Device Pixel Ratio pentru ca Qt să știe că e o imagine High DPI
        res_pix = QPixmap.fromImage(out_img)
        res_pix.setDevicePixelRatio(scale)
        return res_pix

    @staticmethod
    def crop_to_circle(pixmap, target_size, scale=2.0):
        """ Decupează o imagine în formă de cerc (High DPI Ready) """
        if not pixmap or pixmap.isNull(): return QPixmap()
        
        phys_size = int(target_size * scale)
        
        img = pixmap.toImage()
        size = min(img.width(), img.height())
        rect = QRectF((img.width() - size) / 2, (img.height() - size) / 2, size, size).toRect()
        cropped = img.copy(rect)
        
        scaled = cropped.scaled(phys_size, phys_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        out_img = QImage(phys_size, phys_size, QImage.Format.Format_ARGB32)
        out_img.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(out_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, phys_size, phys_size)
        painter.setClipPath(path)
        painter.drawImage(0, 0, scaled)
        painter.end()
        
        res_pix = QPixmap.fromImage(out_img)
        res_pix.setDevicePixelRatio(scale)
        return res_pix

    @staticmethod
    def create_dashboard_icon(icon_path, bg_color_hex, size, emoji_fallback=None):
        """ Creează iconița complexă pentru dashboard (Cerc colorat + Icon decupat/Emoji) """
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # 1. Cerc Colorat
        painter.setBrush(QColor(bg_color_hex)) 
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, size, size)
        
        # 2. Încercăm să încărcăm SVG-ul pentru Mască
        found_svg = False
        if icon_path and os.path.exists(icon_path):
            renderer = QSvgRenderer(icon_path)
            if renderer.isValid():
                target_size = int(size * 0.55) # 55% din cerc
                x = (size - target_size) // 2
                y = (size - target_size) // 2
                
                # Decupăm forma iconiței din cerc (DestinationOut)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
                renderer.render(painter, QRectF(x, y, target_size, target_size))
                found_svg = True
        
        # 3. Dacă nu am găsit SVG, desenăm Emoji peste cerc (alb)
        if not found_svg and emoji_fallback:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QColor("white"))
            
            font_name = "Segoe UI Emoji"
            if platform.system() == "Darwin":
                font_name = "Apple Color Emoji"
                
            font = QFont(font_name, int(size * 0.4))
            font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, emoji_fallback)
        
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def extract_gradient_colors(pixmap):
        """ Extrage 6 culori dominante pentru un gradient complex """
        if not pixmap or pixmap.isNull():
            # Fallback Dark: 6 puncte de negru/gri
            return ["#121212", "#181818", "#1a1a1a", "#151515", "#0a0a0a", "#000000"]
        
        # Scalăm la 3x2 pixeli pentru a obține 6 puncte de culoare
        img = pixmap.toImage().scaled(3, 2, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        
        colors = []
        # Ordine pentru a crea un flux vizual interesant pe diagonală
        # (0,0) -> (1,0) -> (0,1) -> (2,0) -> (1,1) -> (2,1)
        coords = [(0,0), (1,0), (0,1), (2,0), (1,1), (2,1)]
        
        for x, y in coords:
            c = QColor(img.pixelColor(x, y))
            colors.append(c.darker(140).name()) # Întunecăm pentru lizibilitate
            
        return colors
