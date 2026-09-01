from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, pyqtProperty, QRectF, QSize
from PyQt6.QtGui import QPainter, QPainterPath

class TransitionOverlay(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._radius = 0.0
        self.render_mode = "cover" # 'cover' (Artwork) sau 'stretch'/'aspect_left' (Text)
        self.target_size = QSize(0, 0) # Dimensiunea finală a imaginii (pentru mask reveal)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

    @pyqtProperty(float)
    def radius(self): return self._radius

    @radius.setter
    def radius(self, r):
        self._radius = r
        self.update()
        
    def set_target_size(self, size):
        self.target_size = size

    def paintEvent(self, event):
        if not self.pixmap() or self.pixmap().isNull(): return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        if self._radius > 0:
            path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
            painter.setClipPath(path)
        
        if self.render_mode == "mask_reveal" and self.target_size.isValid():
            # --- MOD MASCĂ (User Request) ---
            # Scalăm imaginea la dimensiunea FINALĂ (Header Width)
            # O desenăm centrată pe overlay-ul curent.
            # Pe măsură ce overlay-ul crește, se vede mai mult din imaginea statică.
            scale_factor = self.target_size.width() / self.pixmap().width()
            new_w = self.target_size.width()
            new_h = int(self.pixmap().height() * scale_factor)
            
            scaled = self.pixmap().scaled(new_w, new_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
            # Centrare pe widget-ul curent
            x = (self.width() - new_w) // 2
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