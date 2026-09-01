from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, pyqtProperty, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QColor, QFont, QPalette, QFontMetrics

class AnimatedLyricLine(QLabel):
    clicked_with_time = pyqtSignal(float)

    def __init__(self, text, timestamp, parent=None):
        super().__init__(text, parent)
        self.timestamp = timestamp
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContentsMargins(10, 5, 10, 5) # 🔥 Padding gestionat corect de layout

        self._raw_text = text
        self._wrapped_for_width = 0
        
        # Stare internă
        self.zoom_factor = 1.0
        self.base_inactive_size = 16.0
        self.base_active_size = 26.0
        self._font_size = self.base_inactive_size
        self._inactive_color = QColor("#FFFFFF")
        self._active_color = QColor("#00AAFF")
        self._text_color = self._inactive_color
        self._is_active = False
        
        # Inițializare font
        f = self.font()
        f.setPointSizeF(self._font_size)
        f.setBold(False)
        self.setFont(f)
        
        # Inițializare culoare
        self.textColor = self._text_color

    def _wrap_text_for_width(self, font, width, max_lines=2):
        words = self._raw_text.split()
        if not words:
            return self._raw_text, 0

        metrics = QFontMetrics(font)
        lines = []
        line = words[0]
        for word in words[1:]:
            test = f"{line} {word}"
            if metrics.horizontalAdvance(test) <= width:
                line = test
            else:
                lines.append(line)
                if max_lines and len(lines) >= max_lines:
                    line = word
                    break
                line = word
        lines.append(line)

        max_width = 0
        for ln in lines:
            max_width = max(max_width, metrics.horizontalAdvance(ln))
        return "\n".join(lines), max_width

    def _max_line_width(self, font, text):
        metrics = QFontMetrics(font)
        lines = text.split("\n") if text else [""]
        max_width = 0
        for ln in lines:
            max_width = max(max_width, metrics.horizontalAdvance(ln))
        return max_width

    def _fit_font_size(self, size):
        available = self.contentsRect().width()
        if available <= 0:
            return size

        text = self.text()
        if not text:
            return size

        f = self.font()
        f.setPointSizeF(size)

        text = self.text()
        max_line_width = self._max_line_width(f, text)

        width_limit = max(10.0, available * 0.95)
        if max_line_width <= 0 or max_line_width <= width_limit:
            return size

        scale = width_limit / max_line_width
        return max(10.0, size * scale)

    def set_zoom_factor(self, factor):
        self.zoom_factor = max(0.6, float(factor))
        target_size = (self.base_active_size if self._is_active else self.base_inactive_size) * self.zoom_factor
        self.fontSize = target_size

    def set_theme_colors(self, active_hex, inactive_hex):
        """ Actualizează culorile în funcție de temă """
        self._active_color = QColor(active_hex)
        self._inactive_color = QColor(inactive_hex)
        self.textColor = self._active_color if self._is_active else self._inactive_color

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_with_time.emit(self.timestamp)
        super().mousePressEvent(event) # Propagăm evenimentul pentru a permite drag-scrolling

    # --- PROPRIETĂȚI PENTRU ANIMAȚIE ---
    @pyqtProperty(float)
    def fontSize(self):
        return self._font_size

    @fontSize.setter
    def fontSize(self, size):
        size = self._fit_font_size(size)
        self._font_size = size
        f = self.font()
        f.setPointSizeF(size)
        self.setFont(f) 

    @pyqtProperty(QColor)
    def textColor(self):
        return self._text_color

    @textColor.setter
    def textColor(self, color):
        self._text_color = color
        # 🔥 Folosim QPalette pentru performanță maximă (fără CSS)
        pal = self.palette()
        pal.setColor(self.foregroundRole(), color)
        self.setPalette(pal)

    def set_active(self, active):
        if self._is_active == active: return
        self._is_active = active
        
        f = self.font()
        f.setBold(active)
        self.setFont(f)
        
        # Configurare valori țintă
        target_size = (self.base_active_size if active else self.base_inactive_size) * self.zoom_factor
        target_size = self._fit_font_size(target_size)
        target_color = self._active_color if active else self._inactive_color
        
        # Grupăm animațiile pentru a rula simultan
        self.anim_group = QParallelAnimationGroup(self)
        
        anim_size = QPropertyAnimation(self, b"fontSize")
        anim_size.setDuration(300)
        anim_size.setStartValue(self._font_size)
        anim_size.setEndValue(target_size)
        anim_size.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        anim_color = QPropertyAnimation(self, b"textColor")
        anim_color.setDuration(300)
        anim_color.setStartValue(self._text_color)
        anim_color.setEndValue(target_color)
        anim_color.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.anim_group.addAnimation(anim_size)
        self.anim_group.addAnimation(anim_color)
        self.anim_group.start()

    def update_style_static(self):
        """ Resetare rapidă fără animație (la inițializare) """
        self.fontSize = self.base_inactive_size * self.zoom_factor # Folosim setter-ul pentru a aplica fontul
        self.textColor = self._inactive_color
        self._is_active = False
        f = self.font()
        f.setBold(False)
        self.setFont(f)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        available = self.contentsRect().width()
        if available > 0 and available != self._wrapped_for_width:
            base_size = self.base_inactive_size * self.zoom_factor
            f = self.font()
            f.setPointSizeF(base_size)
            wrap_limit = max(10.0, available * 0.7)
            wrapped, _ = self._wrap_text_for_width(f, wrap_limit, max_lines=2)
            if wrapped != self.text():
                self.setText(wrapped)
            self._wrapped_for_width = available

        if self._font_size:
            self.fontSize = self._font_size