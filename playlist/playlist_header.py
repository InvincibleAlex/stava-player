from PyQt6.QtWidgets import QWidget, QFrame
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap, QImage, QImageReader

# --- CLASĂ PENTRU CONTAINER (MASKING) ---
class HeaderContainer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")

# --- CLASĂ PENTRU HEADER CU BACKGROUND ---
class PlaylistHeader(QWidget):
    def __init__(self):
        super().__init__()
        self.pixmap = None
        self.image_source_path = None
        self.source_image = QImage()
        self.is_compact = False # Stare internă
        self._content_opacity = 1.0 # Opacitate pentru animații
        self.setStyleSheet("background: transparent;")

    def set_image(self, pixmap, source_path=None):
        self.pixmap = pixmap
        self.image_source_path = source_path if source_path else None
        if self.image_source_path:
            self._load_source_image()
        elif self.pixmap and not self.pixmap.isNull():
            self.source_image = self.pixmap.toImage()
        else:
            self.source_image = QImage()
        self.update_geometry_state()
        self.update()

    def _load_source_image(self):
        if not self.image_source_path:
            self.source_image = QImage()
            return False
        reader = QImageReader(self.image_source_path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            self.source_image = QImage()
            return False
        self.source_image = image
        return True

    def reload_high_quality(self):
        if self._load_source_image():
            self.pixmap = QPixmap(self.image_source_path)
            self.update()

    def set_compact(self, is_compact):
        self.is_compact = is_compact
        self.update_geometry_state()

    def set_content_opacity(self, opacity):
        self._content_opacity = opacity
        self.update()

    def update_geometry_state(self):
        """ Calculează înălțimea header-ului: 60px (Compact) sau 2/3 din Artwork """
        # 🔥 FIX: Dacă widget-ul nu e vizibil sau părintele e prea mic (layout neterminat), ignorăm
        if not self.isVisible() or self.width() < 50: return

        if self.is_compact:
            target_h = 80 # Bază pentru compact; îl ridicăm dacă layout-ul cere mai mult la zoom.
            if self.layout():
                target_h = max(target_h, self.layout().minimumSize().height())
            # 🔥 FIX: Dacă e compact, forțăm înălțimea și ieșim. Nu lăsăm layout-ul să o modifice.
            if self.height() != target_h:
                self.setFixedHeight(target_h)
            # 🔥 FIX: Sincronizăm și containerul părinte pentru a preveni salt vizual la tab switch
            if self.parentWidget() and self.parentWidget().height() != target_h:
                self.parentWidget().setFixedHeight(target_h)
            return
            
        elif (self.pixmap and not self.pixmap.isNull()) or not self.source_image.isNull():
            # MODIFICAT: Înălțime bazată pe înălțimea ferestrei (60%) pentru a fi masiv
            # Folosim înălțimea containerului părinte (Tab-ul) pentru a fi mai exacți
            # Header -> Container -> PlaylistTab
            if self.parentWidget() and self.parentWidget().parentWidget():
                base_h = self.parentWidget().parentWidget().height()
            else:
                base_h = self.window().height() if self.window() else 600
            
            # Safety: Dacă înălțimea de bază e aberantă (ex: la inițializare), ignorăm
            if base_h < 200: return

            target_h = int(base_h * 0.35) # 35% din înălțime (fără minim forțat de 350px)
            
            # SAFETY: Lăsăm loc pentru listă (minim 150px) ca să nu o împingem afară
            if base_h > 150:
                target_h = min(target_h, base_h - 150)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.updateGeometry()
            self.adjustSize()
            if self.parentWidget():
                self.parentWidget().setMinimumHeight(0)
                self.parentWidget().setMaximumHeight(16777215)
            return

        # SAFETY: Ne asigurăm că nu tăiem conținutul intern (butoane, search)
        # Indiferent de calculul de mai sus, dacă layout-ul cere mai mult spațiu, i-l dăm.
        if self.layout():
            min_req = self.layout().minimumSize().height()
            if target_h < min_req:
                target_h = min_req

        # Aplicăm înălțimea doar dacă s-a schimbat (pentru a evita bucle infinite în resizeEvent)
        # 🔥 FIX: Toleranță de 1px pentru a evita micro-ajustările care fac imaginea să tremure
        if abs(self.height() - target_h) > 1:
            self.setFixedHeight(target_h)
            # 🔥 FIX: Sincronizăm și containerul părinte
            if self.parentWidget():
                self.parentWidget().setFixedHeight(target_h)

    def resizeEvent(self, event):
        # Only recalculate header height on genuine width change (window resize),
        # not during tab switch relayout which only changes height slightly.
        if not self.is_compact and ((self.pixmap and not self.pixmap.isNull()) or not self.source_image.isNull()):
            old_w = event.oldSize().width() if event.oldSize().isValid() else -1
            new_w = event.size().width()
            if old_w != new_w:
                self.update_geometry_state()
        self.update()
        super().resizeEvent(event)
        self.update() # Forțăm redesenarea background-ului curbat

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        source_image = self.source_image
        if source_image.isNull() and self.pixmap and not self.pixmap.isNull():
            source_image = self.pixmap.toImage()

        if not source_image.isNull():
            painter.setOpacity(self._content_opacity) # Aplicăm opacitatea

            # --- CLIP PATH (Rotunjire doar jos cu Anti-Aliasing) ---
            path = QPainterPath()
            w = self.width()
            h = self.height()
            r = 30 
            
            path.moveTo(0, 0)
            path.lineTo(w, 0)
            path.lineTo(w, h - r)
            path.arcTo(w - 2*r, h - 2*r, 2*r, 2*r, 0, -90)
            path.lineTo(r, h)
            path.arcTo(0, h - 2*r, 2*r, 2*r, 270, -90)
            path.lineTo(0, 0)
            path.closeSubpath()
            
            painter.setClipPath(path)

            img_w = max(1, source_image.width())
            img_h = max(1, source_image.height())
            target_w = max(1, self.width())
            target_h = max(1, self.height())

            scale = max(target_w / img_w, target_h / img_h)
            source_w = target_w / scale
            source_h = target_h / scale
            source_x = max(0.0, (img_w - source_w) / 2.0)
            source_y = max(0.0, (img_h - source_h) / 2.0)

            painter.drawImage(
                QRectF(0, 0, target_w, target_h),
                source_image,
                QRectF(source_x, source_y, source_w, source_h),
            )
