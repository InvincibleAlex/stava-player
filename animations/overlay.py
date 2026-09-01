from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, pyqtProperty, QRectF
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen

class TransitionOverlay(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._radius = 0.0
        self.render_mode = "cover" # 'cover' (Artwork) sau 'stretch'/'aspect_left' (Text)
        self.shape_mode = "rounded_rect"
        self.border_width = 0.0
        self.border_color = QColor(255, 255, 255, 0)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

    @pyqtProperty(float)
    def radius(self): return self._radius

    @radius.setter
    def radius(self, r):
        self._radius = r
        self.update()

    def paintEvent(self, event):
        if not self.pixmap() or self.pixmap().isNull(): return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        rect = QRectF(self.rect())
        if self.shape_mode == "header_mask":
            radius = max(0.0, self._radius)
            path.moveTo(rect.left(), rect.top())
            path.lineTo(rect.right(), rect.top())
            path.lineTo(rect.right(), rect.bottom() - radius)
            path.arcTo(rect.right() - 2 * radius, rect.bottom() - 2 * radius, 2 * radius, 2 * radius, 0, -90)
            path.lineTo(rect.left() + radius, rect.bottom())
            path.arcTo(rect.left(), rect.bottom() - 2 * radius, 2 * radius, 2 * radius, 270, -90)
            path.lineTo(rect.left(), rect.top())
            path.closeSubpath()
            painter.setClipPath(path)
        elif self._radius > 0:
            path.addRoundedRect(rect, self._radius, self._radius)
            painter.setClipPath(path)
        else:
            path.addRect(rect)
        
        if self.render_mode == "width_fill":
            # --- MOD WIDTH FILL (User Request) ---
            # Prioritate: Marginile stânga-dreapta lipite de container (Full Width).
            if self.pixmap().width() > 0:
                scale = self.width() / self.pixmap().width()
                new_w = self.width()
                new_h = int(self.pixmap().height() * scale)
                
                # Folosim IgnoreAspectRatio pentru a forța dimensiunile calculate manual
                scaled = self.pixmap().scaled(new_w, new_h, 
                                            Qt.AspectRatioMode.IgnoreAspectRatio, 
                                            Qt.TransformationMode.SmoothTransformation)
                
                # Centrare verticală (Crop Center Vertical)
                x = 0
                y = (self.height() - new_h) // 2
                painter.drawPixmap(x, y, scaled)
            
        elif self.render_mode == "cover":
            # Artwork: Păstrăm proporțiile, tăiem marginile, centrat
            scaled = self.pixmap().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        elif self.render_mode == "aspect_left":
            # Text: Păstrăm proporțiile, aliniat la STÂNGA și CENTRAT VERTICAL
            scaled = self.pixmap().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(0, y, scaled)
        else: # stretch
            # Text: Întindem imaginea pe tot rect-ul (Stretch)
            painter.drawPixmap(self.rect(), self.pixmap())

        if self.border_width > 0 and self.border_color.alpha() > 0:
            painter.setClipping(False)
            pen = QPen(self.border_color)
            pen.setWidthF(self.border_width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            inset = self.border_width / 2.0
            border_rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
            if self._radius > 0:
                painter.drawRoundedRect(border_rect, self._radius, self._radius)
            else:
                painter.drawRect(border_rect)