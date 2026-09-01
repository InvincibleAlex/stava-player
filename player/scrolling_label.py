from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPainter, QPixmap, QColor, QLinearGradient

class ScrollingLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_pos)
        self._timer.setInterval(30) # 30ms = ~33 FPS
        self._wait_counter = 0
        self._text_width = 0
        self._is_scrolling = False

    def setText(self, text):
        super().setText(text)
        self._offset = 0
        self._wait_counter = 50 # Așteaptă 1.5s înainte de a începe
        self._is_scrolling = False
        self._timer.stop()
        self.update()

    def sizeHint(self):
        fm = self.fontMetrics()
        w = fm.horizontalAdvance(self.text())
        return QSize(max(50, w), super().sizeHint().height())

    def paintEvent(self, event):
        fm = self.fontMetrics()
        self._text_width = fm.horizontalAdvance(self.text())
        
        if self._text_width <= self.width() + 5:
            self._is_scrolling = False
            self._timer.stop()
            self._offset = 0
            painter = QPainter(self)
            painter.setFont(self.font())
            
            color = self.palette().color(self.foregroundRole())
            painter.setPen(color)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            
            y = (self.height() + fm.ascent() - fm.descent()) // 2
            painter.drawText(0, y, self.text())
            return

        if not self._is_scrolling:
            self._is_scrolling = True
            self._wait_counter = 50
            self._timer.start()

        dpr = self.devicePixelRatioF()
        phys_w = int(self.width() * dpr)
        phys_h = int(self.height() * dpr)
        pixmap = QPixmap(phys_w, phys_h)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        p = QPainter(pixmap)
        p.setFont(self.font())
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        color = self.palette().color(self.foregroundRole())
        p.setPen(color)
        
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        
        x1 = -self._offset
        p.drawText(x1, y, self.text())
        
        spacing = 40
        x2 = x1 + self._text_width + spacing
        if x2 < self.width():
            p.drawText(x2, y, self.text())
            
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        
        fade_w = 30
        if fade_w > self.width() / 3: fade_w = self.width() / 3
        
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(fade_w / self.width(), QColor(0, 0, 0, 255))
        gradient.setColorAt(1.0 - (fade_w / self.width()), QColor(0, 0, 0, 255))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        
        p.fillRect(self.rect(), gradient)
        p.end()
        
        painter = QPainter(self)
        painter.drawPixmap(0, 0, pixmap)
            
    def _update_pos(self):
        if self._wait_counter > 0:
            self._wait_counter -= 1
            return
            
        self._offset += 1
        spacing = 40
        if self._offset >= self._text_width + spacing:
            self._offset = 0
            
        self.update()