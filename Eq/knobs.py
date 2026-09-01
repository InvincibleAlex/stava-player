import math
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QVariantAnimation, QEasingCurve, QEvent
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QConicalGradient, QPalette

class KnobGraphic(QWidget):
    value_changed = pyqtSignal(float)

    def __init__(self, title, min_val, max_val, step=1.0, parent=None):
        super().__init__(parent)
        self.min_val = float(min_val)
        self.max_val = float(max_val)
        self.step = float(step)
        self.title = title
        self._value = 0.0
        self._anim_value = 0.0 # Valoarea vizuală
        self.inner_color = QColor("#1C1C1C")
        self.border_color = QColor("#333333")
        
        # Unghiurile pentru arcul de cerc (270 de grade)
        # MODIFICAT: Start 225 (Stânga Jos), Span -270 (Sens Orar -> Dreapta Jos)
        self.start_angle = 225
        self.span_angle = -270

        self.setMinimumSize(100, 100) # Un minim mult mai mare pentru grafică

        # Variabile pentru interacțiunea cu mouse-ul
        self.is_dragging = False
        self.drag_start_y = 0
        self.drag_start_value = 0.0
        
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_colors(self, inner_col, border_col):
        self.inner_color = QColor(inner_col)
        self.border_color = QColor(border_col)
        self.update()

    def setValue(self, value, update_visual=True):
        clamped_value = max(self.min_val, min(self.max_val, value))
        if self._value != clamped_value:
            self._value = clamped_value
            self.value_changed.emit(self._value)
        if update_visual:
            self.set_anim_value(clamped_value)

    def set_anim_value(self, val):
        self._anim_value = val
        self.update()

    def value(self):
        return self._value

    def value_to_angle(self, value):
        value_ratio = (value - self.min_val) / (self.max_val - self.min_val)
        return self.start_angle + value_ratio * self.span_angle

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height()) - 10
        if side < 10: side = 10
        
        # Center the knob
        x = (self.width() - side) / 2
        y = (self.height() - side) / 2
        rect = QRectF(x, y, side, side)
        
        pen_width = 4 # Linie foarte subțire
        draw_rect = rect.adjusted(pen_width / 2, pen_width / 2, -pen_width / 2, -pen_width / 2)

        # 1. Desenare fundal arc (groove)
        pen = QPen(QColor("#333333"))
        pen.setWidth(pen_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(draw_rect, int(self.start_angle * 16), int(self.span_angle * 16))

        # 2. Desenare arc activ (fill)
        current_angle = self.value_to_angle(self._anim_value)
        
        # Dacă avem interval bipolar (ex: -15 la +15), desenăm din zero (centru)
        if self.min_val < 0 < self.max_val:
            zero_angle = self.value_to_angle(0)
            start_draw_angle = zero_angle
            fill_span = current_angle - zero_angle
        else:
            # Comportament clasic (de la minim)
            start_draw_angle = self.start_angle
            fill_span = current_angle - self.start_angle
        
        if abs(fill_span) > 0:
            gradient = QConicalGradient(rect.center(), 90)
            if "BASS" in self.title.upper():
                gradient.setColorAt(0.35, QColor("#FFD700"))
                gradient.setColorAt(0.65, QColor("#FFA500"))
            else: # Treble
                gradient.setColorAt(0.35, QColor("#00BFFF"))
                gradient.setColorAt(0.65, QColor("#1E90FF"))

            pen.setBrush(gradient)
            painter.setPen(pen)
            painter.drawArc(draw_rect, int(start_draw_angle * 16), int(fill_span * 16))

        # 3. Desenare corp knob (cercul interior)
        gap = 10 # Spațiu între arcul subțire și corpul knob-ului
        inner_rect = draw_rect.adjusted(gap, gap, -gap, -gap)
        painter.setPen(QPen(self.border_color, 2))
        painter.setBrush(self.inner_color)
        painter.drawEllipse(inner_rect)

        # 4. Desenare indicator pe knob
        indicator_radius = inner_rect.width() / 2 - 10
        indicator_angle_rad = math.radians(-current_angle)
        ix = inner_rect.center().x() + indicator_radius * math.cos(indicator_angle_rad)
        iy = inner_rect.center().y() + indicator_radius * math.sin(indicator_angle_rad)
        
        painter.save()
        painter.translate(ix, iy)
        painter.rotate(-current_angle) # Rotim indicatorul radial (spre exterior)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#888888"))
        painter.drawRoundedRect(QRectF(-8, -2, 16, 4), 2, 2)
        painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_start_y = event.position().y()
            self.drag_start_value = self._value
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            dy = self.drag_start_y - event.position().y()
            sensitivity = 200
            dv = (dy / sensitivity) * (self.max_val - self.min_val)
            self.setValue(self.drag_start_value + dv)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            event.accept()

    def wheelEvent(self, event):
        # Scroll cu pas definit (default 1.0, custom pentru Tempo 0.1)
        if event.angleDelta().y() > 0:
            self.setValue(self._value + self.step)
        else:
            self.setValue(self._value - self.step)
        event.accept()

class AudioKnob(QWidget):
    value_changed = pyqtSignal(float)

    def __init__(self, title, min_val, max_val, step=1.0, parent=None, orientation='horizontal', format_str="{:.0f}%"):
        super().__init__(parent)
        self.format_str = format_str
        self.orientation = orientation
        self.base_title_size = 12
        self.base_value_size = 13
        self.title_color = None
        self.value_color = None
        
        self.zero_val = 0.0
        if "TEMPO" in title.upper(): self.zero_val = 1.0
        elif "BALANCE" in title.upper(): self.zero_val = 50.0
        elif min_val <= 0 <= max_val: self.zero_val = 0.0
        else: self.zero_val = min_val

        self.val_anim = QVariantAnimation(self)
        self.val_anim.setDuration(250)
        self.val_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.val_anim.valueChanged.connect(self._on_anim_value_changed)

        if orientation == 'vertical':
            self.setMinimumSize(80, 100)
        else:
            self.setMinimumSize(220, 110) # Mult mai mari pe orizontală (Bass/Treble)
            
        self.setMaximumSize(280, 280) # Limităm mărimea pentru consistență între tab-uri
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Main Layout
        if orientation == 'vertical':
            layout = QVBoxLayout(self)
        else:
            layout = QHBoxLayout(self)
            
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # 1. Text Container
        text_container = QWidget()
        if orientation == 'horizontal':
            text_width = 120 if len(str(title)) > 8 else 76
            text_container.setFixedWidth(text_width)
            
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(4, 0, 4, 0)
        text_layout.setSpacing(0)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self.lbl_title = QLabel(title)
        
        self.lbl_value = QLabel(self.format_str.format(min_val))
        
        if orientation == 'vertical':
            self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
            self.lbl_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self._apply_label_styles(self.base_title_size, self.base_value_size)
        
        text_layout.addWidget(self.lbl_title)
        text_layout.addWidget(self.lbl_value)
        
        # 2. Knob Graphic (Right)
        self.knob = KnobGraphic(title, min_val, max_val, step=step)
        self.knob.value_changed.connect(self.on_knob_change)
        
        if orientation == 'vertical':
            layout.addWidget(self.knob)
            layout.addWidget(text_container)
        else:
            layout.addWidget(text_container)
            layout.addWidget(self.knob)

    def _on_anim_value_changed(self, val):
        if val is None: return
        try:
            v = float(val)
            self.knob.set_anim_value(v)
            self.lbl_value.setText(self.format_str.format(v))
        except (ValueError, TypeError): pass

    def changeEvent(self, event):
        if event.type() == QEvent.Type.EnabledChange:
            enabled = self.isEnabled()
            self.val_anim.stop()
            self.val_anim.setStartValue(self.knob._anim_value)
            self.val_anim.setEndValue(self.knob._value if enabled else self.zero_val)
            self.val_anim.start()
        elif event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.StyleChange,
        ):
            self._apply_label_styles(self.lbl_title.font().pointSize(), self.lbl_value.font().pointSize())
        super().changeEvent(event)

    def on_knob_change(self, val):
        if self.isEnabled() and self.val_anim.state() != QVariantAnimation.State.Running:
            self.lbl_value.setText(self.format_str.format(val))
        self.value_changed.emit(val)

    def setValue(self, val):
        if val is None: return
        try:
            val = float(val)
        except (ValueError, TypeError): return
        
        update_visual = self.isEnabled() and self.val_anim.state() != QVariantAnimation.State.Running
        self.knob.setValue(val, update_visual=update_visual)
        if update_visual:
            self.lbl_value.setText(self.format_str.format(val))

    def value(self):
        return self.knob.value()

    def _get_default_title_color(self):
        return self.palette().color(QPalette.ColorRole.WindowText).name()

    def _get_default_value_color(self):
        title = self.lbl_title.text().upper()
        if "BASS" in title:
            return "#FFA500"
        if "TREBLE" in title:
            return "#1E90FF"
        return self._get_default_title_color()

    def _apply_label_styles(self, title_size, value_size):
        title_size = max(1, int(title_size))
        value_size = max(1, int(value_size))
        title_color = self.title_color or self._get_default_title_color()
        value_color = self.value_color or self._get_default_value_color()
        self.lbl_title.setStyleSheet(
            f"font-weight: bold; font-size: {title_size}px; color: {title_color}; margin-bottom: 2px;"
        )
        self.lbl_value.setStyleSheet(
            f"font-weight: bold; font-size: {value_size}px; color: {value_color}; margin-top: 2px;"
        )

    def set_colors(self, inner, border, title_color=None, value_color=None):
        self.knob.set_colors(inner, border)
        self.title_color = title_color
        self.value_color = value_color
        self._apply_label_styles(self.lbl_title.font().pointSize(), self.lbl_value.font().pointSize())

    def set_zoom_factor(self, factor):
        z = max(0.6, float(factor))

        title_size = max(8, int(self.base_title_size * z))
        value_size = max(9, int(self.base_value_size * z))

        self._apply_label_styles(title_size, value_size)

        if self.orientation == 'vertical':
            self.setMinimumSize(int(80 * z), int(100 * z))
        else:
            self.setMinimumSize(int(220 * z), int(110 * z))

        max_dim = int(280 * z)
        self.setMaximumSize(max_dim, max_dim)

    def contextMenuEvent(self, event):
        try:
            title = self.lbl_title.text().strip().upper()
            self.setValue(self.zero_val)
            event.accept()
            return
        except Exception:
            pass
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.setValue(self.zero_val)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
