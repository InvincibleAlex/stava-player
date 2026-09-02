import os
from PyQt6.QtWidgets import (QWidget, QLabel, QFrame, QSizePolicy, QPushButton)
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QSize, QEvent, QVariantAnimation, QEasingCurve, QSequentialAnimationGroup, QPointF
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap, QRegion, QColor, QPen, QIcon
from core.utils import IconHelper

# --- 1. FALLBACK WAVEFORM (Dacă lipsește modulul real) ---
class DummyWaveformWidget(QWidget):
    seek_request = pyqtSignal(float)
    def __init__(self, bass): super().__init__()
    def load_song(self, path): pass
    def set_position(self, pos): pass
    def set_theme_colors(self, colors): pass
    def wheelEvent(self, event): pass
    def mousePressEvent(self, event): pass
    def mouseMoveEvent(self, event): pass
    def mouseReleaseEvent(self, event): pass

# --- 1.5 CLICKABLE LABEL (NOU) ---
class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# --- 2. CONTAINER TRANSPARENT (Click-Through) ---
class ClickThroughContainer(QWidget):
    """
    Un container care lasă click-urile să treacă la Waveform
    dacă nu nimerești niciun buton.
    """
    def __init__(self, waveform_ref, parent=None):
        super().__init__(parent)
        self.waveform = waveform_ref
        self.setMouseTracking(True) 

    def mousePressEvent(self, event):
        if not self.childAt(event.position().toPoint()):
            self.waveform.mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.childAt(event.position().toPoint()):
            self.waveform.mouseMoveEvent(event)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.childAt(event.position().toPoint()):
            self.waveform.mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)
            
    def wheelEvent(self, event):
        self.waveform.wheelEvent(event)

# --- 3. PĂTRAT PERFECT (Pentru Artwork) ---
class SquareFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
    def resizeEvent(self, event):
        w = self.width()
        if self.height() != w and w > 0: self.setFixedHeight(w)
        super().resizeEvent(event)

# --- 4. COPERTĂ ROTUNJITĂ ---
class RoundedArtLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_data = None
        self.radius = 20
        # Pixmap-ul scalat se cacheaza si se refoloseste intre cadre - inainte
        # se recalcula (scalare SmoothTransformation) la fiecare paintEvent,
        # chiar daca imaginea si dimensiunea nu se schimbasera.
        self._scaled_pixmap_cache = None
        self._scaled_pixmap_key = None
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        # Stil implicit
        self.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a; 
                border-radius: 20px; 
                border: none;
                font-size: 20px; 
                font-weight: bold; 
                color: #555;
            }
        """)
        self.setText("🎵\nNo Art")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    def set_art(self, qimage):
        self.image_data = qimage
        self._scaled_pixmap_cache = None
        self._scaled_pixmap_key = None
        self.update()

    def resizeEvent(self, event):
        self._scaled_pixmap_cache = None
        self._scaled_pixmap_key = None
        super().resizeEvent(event)

    def _get_scaled_pixmap(self, dpr):
        phys_w = int(self.width() * dpr)
        phys_h = int(self.height() * dpr)
        key = (id(self.image_data), phys_w, phys_h)
        if self._scaled_pixmap_cache is not None and self._scaled_pixmap_key == key:
            return self._scaled_pixmap_cache

        pixmap = QPixmap.fromImage(self.image_data)
        scaled_pixmap = pixmap.scaled(phys_w, phys_h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        scaled_pixmap.setDevicePixelRatio(dpr)
        self._scaled_pixmap_cache = scaled_pixmap
        self._scaled_pixmap_key = key
        return scaled_pixmap

    def paintEvent(self, event):
        if not self.image_data or self.image_data.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        painter.setClipPath(path)
        dpr = self.devicePixelRatioF()
        scaled_pixmap = self._get_scaled_pixmap(dpr)
        logical_w = scaled_pixmap.width() / dpr
        logical_h = scaled_pixmap.height() / dpr
        x = (self.width() - logical_w) / 2
        y = (self.height() - logical_h) / 2
        painter.drawPixmap(int(x), int(y), scaled_pixmap)

# --- 5. BUTON MULTI-STATE (NOU) ---
class MultiStateButton(QPushButton):
    state_changed = pyqtSignal(int) # Emite indexul noii stări

    def __init__(self, states_config, size=30, parent=None):
        """
        states_config = [
            {"icon": "path/to/icon.svg", "color_type": "ICON_COLOR"}, 
            {"icon": "path/to/icon.svg", "color_type": "FG"},
            {"icon": "path/to/icon.svg", "color_type": "PRIME"}
        ]
        color_type poate fi: 'ICON_COLOR' (gri), 'FG' (alb/text), 'PRIME' (tema)
        """
        super().__init__(parent)
        self.states = states_config
        self.current_index = 0
        self.icon_size = size
        self.theme_colors = {}
        self.fixed_icon_color = "#888888" # Default Gray
        
        # Formă de pastilă: Width mai mare decât Height
        self.setFixedSize(size + 16, size) 
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("border: none; background: transparent; border-radius: 15px;")
        
        self.clicked.connect(self.next_state)

    def resize_button(self, new_size):
        """ Redimensionează butonul și iconița (pentru Zoom) """
        self.icon_size = new_size
        # Păstrăm proporția originală (Width = Size + 16 padding la size 24)
        # Scalăm padding-ul proporțional
        scale = new_size / 24.0
        padding = int(16 * scale)
        self.setFixedSize(new_size + padding, new_size)
        self.refresh_look()

    def set_theme_data(self, colors, icon_color_hex):
        """ Primește paleta de culori și actualizează iconița curentă """
        self.theme_colors = colors
        self.fixed_icon_color = icon_color_hex
        self.refresh_look()

    def next_state(self):
        """ Trece la următoarea stare ciclic """
        if not self.states: return
        self.set_state((self.current_index + 1) % len(self.states))

    def set_state(self, index, emit_signal=True):
        if not self.states:
            return
        self.current_index = max(0, min(len(self.states) - 1, int(index)))
        self.refresh_look()
        if emit_signal:
            self.state_changed.emit(self.current_index)

    def _resolve_current_color(self):
        if not self.states:
            return "#FFFFFF"

        color_type = self.states[self.current_index]["color_type"]
        if color_type == "ICON_COLOR":
            return self.fixed_icon_color
        if color_type == "FG":
            return self.theme_colors.get("FG", self.theme_colors.get("TEXT_PRIMARY", "#FFFFFF"))
        if color_type == "PRIME":
            return self.theme_colors.get("PRIMARY", "#00FF00")
        return "#FFFFFF"

    def refresh_look(self):
        """ Desenează iconița bazat pe starea curentă și culori """
        if not self.states: return

        state = self.states[self.current_index]
        icon_path = state["icon"]
        color_type = state["color_type"]

        # Determinăm culoarea Hex
        hex_color = self._resolve_current_color()

        # Colorăm SVG-ul
        icon = IconHelper.get_colored_icon(icon_path, hex_color)
        if not icon.isNull():
            self.setIcon(icon)
            # Iconița un pic mai mică decât butonul
            self.setIconSize(QSize(self.icon_size - 6, self.icon_size - 6))
        
        # Calculăm raza dinamic (jumătate din înălțime)
        radius = self.height() // 2
        
        # Efect vizual pastilă: Dacă e PRIME (activ), punem un fundal subtil
        if color_type == "PRIME":
             self.setStyleSheet(f"border: none; background: {hex_color}1a; border-radius: {radius}px;")
        else:
             self.setStyleSheet(f"border: none; background: transparent; border-radius: {radius}px;")


class AnimatedHeadphonesButton(MultiStateButton):
    def __init__(self, size=30, parent=None):
        super().__init__([{"icon": "", "color_type": "FG"}], size=size, parent=parent)
        self._capsule_progress = 0.0
        self._icon_color = QColor("#FFFFFF")
        self.setIcon(QIcon())

        self._approach_anim = QVariantAnimation(self)
        self._approach_anim.setStartValue(0.0)
        self._approach_anim.setEndValue(1.0)
        self._approach_anim.setDuration(95)
        self._approach_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._approach_anim.valueChanged.connect(self._set_capsule_progress)

        self._release_anim = QVariantAnimation(self)
        self._release_anim.setStartValue(1.0)
        self._release_anim.setEndValue(0.0)
        self._release_anim.setDuration(135)
        self._release_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._release_anim.valueChanged.connect(self._set_capsule_progress)

        self._click_anim_group = QSequentialAnimationGroup(self)
        self._click_anim_group.addAnimation(self._approach_anim)
        self._click_anim_group.addAnimation(self._release_anim)

        self.clicked.connect(self._play_click_animation)

    def _set_capsule_progress(self, value):
        self._capsule_progress = float(value)
        self.update()

    def _play_click_animation(self):
        if self._click_anim_group.state() == QSequentialAnimationGroup.State.Running:
            self._click_anim_group.stop()
        self._click_anim_group.start()

    def refresh_look(self):
        if not self.states:
            return

        color_type = self.states[self.current_index]["color_type"]
        hex_color = self._resolve_current_color()
        self._icon_color = QColor(hex_color)
        self.setIcon(QIcon())

        radius = self.height() // 2
        if color_type == "PRIME":
            self.setStyleSheet(f"border: none; background: {hex_color}1a; border-radius: {radius}px;")
        else:
            self.setStyleSheet(f"border: none; background: transparent; border-radius: {radius}px;")

        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        color = QColor(self._icon_color)
        if not self.isEnabled():
            color.setAlpha(120)

        icon_w = max(12.0, min(float(self.width() - 8), float(self.icon_size - 2)))
        icon_h = max(12.0, min(float(self.height() - 8), float(self.icon_size - 2)))
        center_x = self.width() / 2.0
        center_y = self.height() / 2.0

        pen = QPen(color)
        pen.setWidthF(max(1.7, icon_w * 0.09))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        progress = self._capsule_progress
        spread = icon_w * (0.28 - (0.14 * progress))
        cup_w = icon_w * (0.17 + (0.05 * progress))
        cup_h = icon_h * (0.38 + (0.10 * progress))
        cup_y = center_y + icon_h * (0.08 + (0.01 * progress))
        stem_top_y = center_y - icon_h * (0.11 + (0.04 * progress))
        stem_bottom_y = cup_y - (cup_h / 2.0) + (icon_h * 0.01)
        band_top_y = center_y - icon_h * (0.38 - 0.08 * progress)
        band_side_y = center_y - icon_h * (0.15 + 0.02 * progress)

        band_left_x = center_x - spread - (cup_w * 0.28)
        band_right_x = center_x + spread + (cup_w * 0.28)

        band_path = QPainterPath()
        band_path.moveTo(band_left_x, band_side_y)
        band_path.cubicTo(
            center_x - icon_w * (0.28 - 0.04 * progress),
            band_top_y,
            center_x + icon_w * (0.28 - 0.04 * progress),
            band_top_y,
            band_right_x,
            band_side_y,
        )
        painter.drawPath(band_path)

        left_x = center_x - spread
        right_x = center_x + spread
        painter.drawLine(QPointF(left_x, stem_top_y), QPointF(left_x, stem_bottom_y))
        painter.drawLine(QPointF(right_x, stem_top_y), QPointF(right_x, stem_bottom_y))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        rounding = min(cup_w, cup_h) * 0.48
        left_rect = QRectF(left_x - cup_w / 2.0, cup_y - cup_h / 2.0, cup_w, cup_h)
        right_rect = QRectF(right_x - cup_w / 2.0, cup_y - cup_h / 2.0, cup_w, cup_h)
        painter.drawRoundedRect(left_rect, rounding, rounding)
        painter.drawRoundedRect(right_rect, rounding, rounding)
