import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QSizePolicy, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor


class SpatialPad(QWidget):
    position_changed = pyqtSignal(float, float)  # x, y in [-1..1], y pozitiv = față

    def __init__(self, parent=None):
        super().__init__(parent)
        self._x = 0.0
        self._y = 0.0
        self._dragging = False
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_position(self, x, y, emit_signal=True):
        x = max(-1.0, min(1.0, float(x)))
        y = max(-1.0, min(1.0, float(y)))

        radius = math.sqrt((x * x) + (y * y))
        if radius > 1.0:
            x /= radius
            y /= radius

        changed = (abs(self._x - x) > 1e-6) or (abs(self._y - y) > 1e-6)
        self._x = x
        self._y = y
        self.update()

        if emit_signal and changed:
            self.position_changed.emit(self._x, self._y)

    def _pad_geometry(self):
        side = min(self.width(), self.height()) - 20
        side = max(80, side)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        radius = side / 2.0
        return cx, cy, radius

    def _pixel_to_norm(self, px, py):
        cx, cy, radius = self._pad_geometry()
        nx = (px - cx) / radius
        ny = (cy - py) / radius
        return nx, ny

    def _norm_to_pixel(self, nx, ny):
        cx, cy, radius = self._pad_geometry()
        px = cx + (nx * radius)
        py = cy - (ny * radius)
        return px, py

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy, radius = self._pad_geometry()

        if self.isEnabled():
            outer_pen = QColor("#4a4a4a")
            outer_bg = QColor("#1f1f1f")
            axis_col = QColor("#343434")
            listener_pen = QColor("#909090")
            listener_bg = QColor("#2a2a2a")
            source_pen = QColor("#00AAFF")
            source_bg = QColor("#00AAFF")
        else:
            outer_pen = QColor("#3a3a3a")
            outer_bg = QColor("#151515")
            axis_col = QColor("#2b2b2b")
            listener_pen = QColor("#666666")
            listener_bg = QColor("#1e1e1e")
            source_pen = QColor("#555555")
            source_bg = QColor("#555555")

        painter.setPen(QPen(outer_pen, 2))
        painter.setBrush(outer_bg)
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

        painter.setPen(QPen(axis_col, 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(cx - radius), int(cy), int(cx + radius), int(cy))
        painter.drawLine(int(cx), int(cy - radius), int(cx), int(cy + radius))

        listener_r = max(10, int(radius * 0.12))
        painter.setPen(QPen(listener_pen, 2))
        painter.setBrush(listener_bg)
        painter.drawEllipse(int(cx - listener_r), int(cy - listener_r), listener_r * 2, listener_r * 2)

        sx, sy = self._norm_to_pixel(self._x, self._y)
        source_r = max(8, int(radius * 0.10))
        painter.setPen(QPen(source_pen, 2))
        painter.setBrush(source_bg)
        painter.drawEllipse(int(sx - source_r), int(sy - source_r), source_r * 2, source_r * 2)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            nx, ny = self._pixel_to_norm(event.position().x(), event.position().y())
            self.set_position(nx, ny, emit_signal=True)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            nx, ny = self._pixel_to_norm(event.position().x(), event.position().y())
            self.set_position(nx, ny, emit_signal=True)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_position(0.0, 0.0, emit_signal=True)
            event.accept()


class Spatial3DPage(QWidget):
    stereo_position_changed = pyqtSignal(float, float)
    stereo_enabled_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self.group_stereo = QGroupBox("Stereo Sphere")
        left_layout = QVBoxLayout(self.group_stereo)
        self.btn_stereo_enable = QPushButton("Stereo Sphere: ON")
        self.btn_stereo_enable.setCheckable(True)
        self.btn_stereo_enable.setChecked(True)
        self.btn_stereo_enable.toggled.connect(self._on_stereo_toggled)
        self.lbl_stereo = QLabel("Coordonate în [-1..1], centru = 0: X=pan, Y=față/spate + reverb + punch")
        self.lbl_stereo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pad_stereo = SpatialPad()
        self.pad_stereo.position_changed.connect(self.stereo_position_changed)
        left_layout.addWidget(self.btn_stereo_enable, 0, Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.lbl_stereo)
        left_layout.addWidget(self.pad_stereo, 1)

        row.addWidget(self.group_stereo, 1)

        root.addWidget(container, 1)
        self._sync_pad_enabled_state()

    def _on_stereo_toggled(self, checked):
        self.btn_stereo_enable.setText("Stereo Sphere: ON" if checked else "Stereo Sphere: OFF")
        self._sync_pad_enabled_state()
        self.stereo_enabled_changed.emit(bool(checked))

    def _sync_pad_enabled_state(self):
        self.pad_stereo.setEnabled(self.btn_stereo_enable.isChecked())

    def set_stereo_enabled(self, enabled, emit_signal=False):
        checked = bool(enabled)
        previous = self.btn_stereo_enable.isChecked()
        self.btn_stereo_enable.blockSignals(not emit_signal)
        self.btn_stereo_enable.setChecked(checked)
        self.btn_stereo_enable.blockSignals(False)
        self.btn_stereo_enable.setText("Stereo Sphere: ON" if checked else "Stereo Sphere: OFF")
        self._sync_pad_enabled_state()
        if emit_signal and previous != checked:
            self.stereo_enabled_changed.emit(checked)

    def set_stereo_position(self, x, y, emit_signal=False):
        self.pad_stereo.set_position(x, y, emit_signal=emit_signal)

    def update_theme_colors(self, colors):
        fg = colors.get("FG", "#FFFFFF")
        menu_bg = colors.get("MENU_BG", "#252525")
        primary = colors.get("PRIMARY", "#00AAFF")
        secondary = colors.get("SECONDARY", "#444444")

        c = QColor(menu_bg)
        c.setAlphaF(0.2)
        pill_bg = f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alphaF()})"

        for g in [self.group_stereo]:
            g.setStyleSheet(f"QGroupBox {{ border: 1px solid {secondary}; border-radius: 12px; margin-top: 10px; padding-top: 8px; }}")

        btn_style = f"""
            QPushButton {{
                background-color: {pill_bg};
                color: {fg};
                border-radius: 16px;
                border: 1px solid transparent;
                font-weight: bold;
                padding: 6px 14px;
                min-width: 150px;
            }}
            QPushButton:checked {{
                background-color: {primary};
                color: #000000;
                border: 1px solid {primary};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid {primary};
            }}
        """
        self.btn_stereo_enable.setStyleSheet(btn_style)

        self.lbl_stereo.setStyleSheet(f"font-size: 14px; color: {fg};")

    def set_zoom_factor(self, factor):
        z = max(0.6, float(factor))
        self.lbl_stereo.setStyleSheet(f"font-size: {max(12, int(14 * z))}px;")
