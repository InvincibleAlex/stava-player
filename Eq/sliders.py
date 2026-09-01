from PyQt6.QtWidgets import QSlider, QStyle, QStyleOptionSlider
from PyQt6.QtCore import Qt, QRect, QPointF, QVariantAnimation, QEasingCurve, QEvent
from PyQt6.QtGui import QPainter, QColor, QPen, QLinearGradient

class EqBandSlider(QSlider):
    def __init__(self, orientation):
        super().__init__(orientation)
        self._anim_value = 0.0
        self.val_anim = QVariantAnimation(self)
        self.val_anim.setDuration(250)
        self.val_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.val_anim.valueChanged.connect(self._on_anim_value_changed)
        
    def _on_anim_value_changed(self, val):
        if val is None: return
        try:
            self._anim_value = float(val)
            self.update()
        except (ValueError, TypeError): pass

    def setValue(self, val):
        if val is None: return
        try:
            val_f = float(val)
            super().setValue(int(round(val_f)))
        except (ValueError, TypeError): return
        
        if self.isEnabled() and self.val_anim.state() != QVariantAnimation.State.Running:
            self._anim_value = val_f
            self.update()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.EnabledChange:
            enabled = self.isEnabled()
            self.val_anim.stop()
            self.val_anim.setStartValue(self._anim_value)
            self.val_anim.setEndValue(float(self.value()) if enabled else 0.0)
            self.val_anim.start()
        super().changeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        display_value = self._anim_value if (self.val_anim.state() == QVariantAnimation.State.Running or not self.isEnabled()) else float(self.value())

        # Obținem geometria de la sistemul de stiluri (definită în themes.py)
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        # Când sliderul este dezactivat, păstrăm poziția vizuală pe valoarea animată (de obicei 0),
        # nu pe valoarea logică internă care trebuie restaurată la reactivare.
        if self.val_anim.state() == QVariantAnimation.State.Running or not self.isEnabled():
            opt.sliderPosition = int(round(display_value))
            opt.sliderValue = int(round(display_value))

        groove_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)

        if self.orientation() == Qt.Orientation.Vertical:
            # --- VERTICAL ---
            # 1. Desenare Groove
            groove_pen = QPen(QColor("#444"), 3)
            painter.setPen(groove_pen)
            center_x = groove_rect.center().x()
            painter.drawLine(center_x, 0, center_x, self.height())

            # 2. Desenare Fill
            zero_pos_y = self.get_y_for_value(0)
            handle_center_y = handle_rect.center().y()

            fill_rect = QRect()
            if display_value > 0:
                fill_rect.setRect(center_x - 4, handle_center_y, 8, int(zero_pos_y - handle_center_y))
            elif display_value < 0:
                fill_rect.setRect(center_x - 4, int(zero_pos_y), 8, int(handle_center_y - zero_pos_y))

            if not fill_rect.isEmpty():
                gradient = QLinearGradient(QPointF(fill_rect.topLeft()), QPointF(fill_rect.bottomLeft()))
                gradient.setColorAt(0, QColor("#9EFD2F"))
                gradient.setColorAt(1, QColor("#35C02A"))
                painter.setBrush(gradient)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(fill_rect, 4, 4)

        else:
            # --- HORIZONTAL ---
            # 1. Desenare Groove
            groove_pen = QPen(QColor("#444"), 3)
            painter.setPen(groove_pen)
            center_y = groove_rect.center().y()
            painter.drawLine(0, center_y, self.width(), center_y)

            # 2. Desenare Fill
            zero_pos_x = self.get_pos_for_value(0)
            handle_center_x = handle_rect.center().x()

            fill_rect = QRect()
            if display_value > 0:
                fill_rect.setRect(int(zero_pos_x), center_y - 4, int(handle_center_x - zero_pos_x), 8)
            elif display_value < 0:
                fill_rect.setRect(int(handle_center_x), center_y - 4, int(zero_pos_x - handle_center_x), 8)

            if not fill_rect.isEmpty():
                gradient = QLinearGradient(QPointF(fill_rect.topLeft()), QPointF(fill_rect.topRight()))
                gradient.setColorAt(0, QColor("#9EFD2F"))
                gradient.setColorAt(1, QColor("#35C02A"))
                painter.setBrush(gradient)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(fill_rect, 4, 4)

        # 3. Desenare Mâner (handle)
        center = handle_rect.center()
        if self.orientation() == Qt.Orientation.Vertical:
            diameter = handle_rect.height()
        else:
            diameter = handle_rect.width()
            
        radius = diameter / 2.0

        painter.setBrush(QColor("#303030"))
        painter.setPen(QPen(QColor("#222"), 1))
        painter.drawEllipse(QPointF(center), radius, radius)
        
        # 4. Desenare punct în interiorul mânerului
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#888"))
        inner_radius = radius * 0.35
        painter.drawEllipse(QPointF(center), inner_radius, inner_radius)

    def get_y_for_value(self, value):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        
        # Simulăm poziția pentru valoarea dorită (ex: 0) pentru a vedea unde pune stilul mânerul
        opt.sliderPosition = int(value)
        opt.sliderValue = int(value)
        
        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        return handle_rect.center().y()

    def get_pos_for_value(self, value):
        """ Returnează poziția X (pentru orizontal) """
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        opt.sliderPosition = int(value)
        opt.sliderValue = int(value)
        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        return handle_rect.center().x()

    def wheelEvent(self, event):
        # Scroll cu pas de 1 unitate (0.5 dB)
        if event.angleDelta().y() > 0:
            self.setValue(self.value() + 1)
        else:
            self.setValue(self.value() - 1)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.setValue(0)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)