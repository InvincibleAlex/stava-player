import os
from collections import OrderedDict
from PyQt6.QtWidgets import (QListView, QAbstractItemView, QScrollBar,
                             QStyledItemDelegate, QStyle)
from PyQt6.QtCore import (Qt, QRectF, QPropertyAnimation, QEasingCurve, QPoint, QSize,
                          QObject, pyqtSignal, QRunnable, QThreadPool, QEvent, QRect,
                          QAbstractListModel, QModelIndex, QMimeData, pyqtProperty, QTimer)
from PyQt6.QtGui import (QPixmap, QPainter, QColor, QWheelEvent, QFont, QPen,
                         QImage, QIcon, QPainterPath)
from core.utils import IconHelper


# Custom data roles stored on playlist row items
ROLE_ITEM_TYPE = Qt.ItemDataRole.UserRole + 1   # "dir", "file", "album_group", "artist_group"
ROLE_SUBTITLE = Qt.ItemDataRole.UserRole + 10   # line2 text (artist / stats)
ROLE_INFO = Qt.ItemDataRole.UserRole + 11       # line3 text (duration | ext)
ROLE_ART_PATH = Qt.ItemDataRole.UserRole + 12   # cached artwork file path on disk
ROLE_IS_CURRENT = Qt.ItemDataRole.UserRole + 13 # True for currently-playing song in queue
ROLE_ART_SOURCE_PATH = Qt.ItemDataRole.UserRole + 14  # source audio/folder path used to resolve artwork lazily


class PlaylistModelItem:
    """Small row object with QListWidgetItem-style data/flags compatibility."""
    def __init__(self):
        self._data = {}
        self._flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        self._selected = False

    def data(self, role):
        return self._data.get(role)

    def setData(self, first, second=Qt.ItemDataRole.UserRole + 1):
        known_roles = {
            int(Qt.ItemDataRole.DisplayRole),
            int(Qt.ItemDataRole.UserRole),
            int(Qt.ItemDataRole.DecorationRole),
            int(Qt.ItemDataRole.SizeHintRole),
            int(ROLE_ITEM_TYPE),
            int(ROLE_SUBTITLE),
            int(ROLE_INFO),
            int(ROLE_ART_PATH),
            int(ROLE_IS_CURRENT),
            int(ROLE_ART_SOURCE_PATH),
        }
        if isinstance(first, (int, Qt.ItemDataRole)) and int(first) in known_roles:
            role = first
            value = second
        else:
            role = second
            value = first
        if value is None:
            self._data.pop(role, None)
        else:
            self._data[role] = value

    def flags(self):
        return self._flags

    def setFlags(self, flags):
        self._flags = flags

    def setSelected(self, selected):
        self._selected = bool(selected)

    def isSelected(self):
        return self._selected


class PlaylistListModel(QAbstractListModel):
    MIME_TYPE = "application/x-stava-playlist-row"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        item = self.itemFromIndex(index)
        return item.data(role) if item else None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        item = self.itemFromIndex(index)
        if not item:
            return False
        item.setData(value, role)
        self.dataChanged.emit(index, index, [role])
        return True

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsDropEnabled
        item = self.itemFromIndex(index)
        if item:
            return item.flags() | base
        return base

    def appendItem(self, item):
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()

    def clear(self):
        if not self._items:
            return
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def item(self, row):
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def itemFromIndex(self, index):
        return self.item(index.row()) if index.isValid() else None

    def indexFromItem(self, item):
        try:
            row = self._items.index(item)
        except ValueError:
            return QModelIndex()
        return self.index(row, 0)

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def mimeTypes(self):
        return [self.MIME_TYPE]

    def mimeData(self, indexes):
        mime = QMimeData()
        rows = sorted({index.row() for index in indexes if index.isValid()})
        mime.setData(self.MIME_TYPE, ",".join(map(str, rows)).encode("ascii"))
        return mime

    def dropMimeData(self, mime, action, row, column, parent):
        if action != Qt.DropAction.MoveAction or not mime.hasFormat(self.MIME_TYPE):
            return False
        raw = bytes(mime.data(self.MIME_TYPE)).decode("ascii", errors="ignore")
        rows = [int(part) for part in raw.split(",") if part.strip().isdigit()]
        if not rows:
            return False
        source = rows[0]
        destination = row if row >= 0 else parent.row()
        if destination < 0:
            destination = len(self._items)
        if source < destination:
            destination -= 1
        return self.moveRows(QModelIndex(), source, 1, QModelIndex(), destination)

    def moveRows(self, source_parent, source_row, count, destination_parent, destination_child):
        if count != 1:
            return False
        if source_parent.isValid() or destination_parent.isValid():
            return False
        if source_row < 0 or source_row >= len(self._items):
            return False
        if destination_child < 0 or destination_child > len(self._items):
            return False
        if destination_child == source_row or destination_child == source_row + 1:
            return False
        if not self.beginMoveRows(QModelIndex(), source_row, source_row, QModelIndex(), destination_child):
            return False
        item = self._items.pop(source_row)
        insert_at = destination_child
        if source_row < destination_child:
            insert_at -= 1
        self._items.insert(insert_at, item)
        self.endMoveRows()
        return True


class SmoothListWidget(QListView):
    itemClicked = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = PlaylistListModel(self)
        self.setModel(self._model)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_anim = QPropertyAnimation(self.verticalScrollBar(), b"value")
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic) 
        self._scroll_anim.setDuration(250) 
        self._overscroll_offset = 0.0
        self._overscroll_anim = QPropertyAnimation(self, b"overscrollOffset")
        self._overscroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._overscroll_anim.setDuration(420)
        self._scroll_target = 0.0
        self._overscroll_target = 0.0
        self._smooth_scroll_timer = QTimer(self)
        self._smooth_scroll_timer.setInterval(16)
        self._smooth_scroll_timer.timeout.connect(self._tick_smooth_scroll)
        self._overscroll_return_timer = QTimer(self)
        self._overscroll_return_timer.setSingleShot(True)
        self._overscroll_return_timer.timeout.connect(self._release_overscroll)
        self.overscroll_enabled = True
        self.overscroll_max_offset = 52.0
        self.overscroll_return_ms = 620
        self.overscroll_global_strength = 0.32
        self.overscroll_spread_strength = 0.52
        self.overscroll_falloff_ratio = 0.50
        self.clicked.connect(self._emit_item_clicked)

    def get_overscroll_offset(self):
        return self._overscroll_offset

    def set_overscroll_offset(self, value):
        self._overscroll_offset = float(value)
        self.viewport().update()

    overscrollOffset = pyqtProperty(float, get_overscroll_offset, set_overscroll_offset)

    def configure_overscroll(self, enabled=None, max_offset=None, return_ms=None,
                             global_strength=None, spread_strength=None, falloff_ratio=None):
        if enabled is not None:
            self.overscroll_enabled = bool(enabled)
        if max_offset is not None:
            self.overscroll_max_offset = max(0.0, min(160.0, float(max_offset)))
        if return_ms is not None:
            self.overscroll_return_ms = max(80, min(1200, int(return_ms)))
            self._overscroll_anim.setDuration(self.overscroll_return_ms)
        if global_strength is not None:
            self.overscroll_global_strength = max(0.0, min(1.5, float(global_strength)))
        if spread_strength is not None:
            self.overscroll_spread_strength = max(0.0, min(1.5, float(spread_strength)))
        if falloff_ratio is not None:
            self.overscroll_falloff_ratio = max(0.12, min(1.0, float(falloff_ratio)))
        if not self.overscroll_enabled:
            self._overscroll_target = 0.0
            self.set_overscroll_offset(0.0)

    def _emit_item_clicked(self, index):
        item = self._model.itemFromIndex(index)
        if item:
            self.itemClicked.emit(item)

    def addItem(self, item):
        if isinstance(item, PlaylistModelItem):
            self._model.appendItem(item)
            return

        model_item = PlaylistModelItem()
        roles = [
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.UserRole,
            ROLE_ITEM_TYPE,
            ROLE_SUBTITLE,
            ROLE_INFO,
            ROLE_ART_PATH,
            ROLE_IS_CURRENT,
            ROLE_ART_SOURCE_PATH,
            Qt.ItemDataRole.DecorationRole,
            Qt.ItemDataRole.SizeHintRole,
        ]
        for role in roles:
            value = item.data(role)
            if value is not None:
                model_item.setData(value, role)
        model_item.setFlags(item.flags())
        self._model.appendItem(model_item)

    def clear(self):
        self._model.clear()

    def count(self):
        return self._model.rowCount()

    def item(self, row):
        return self._model.item(row)

    def itemAt(self, position):
        index = self.indexAt(position)
        return self._model.itemFromIndex(index) if index.isValid() else None

    def scrollToItem(self, item, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        index = self._model.indexFromItem(item)
        if index.isValid():
            self.scrollTo(index, hint)

    def visualItemRect(self, item):
        index = self._model.indexFromItem(item)
        return self.visualRect(index) if index.isValid() else QRect()

    def stop_scroll_animation(self, snap_to_end=True):
        if self._scroll_anim.state() == QPropertyAnimation.State.Running:
            if snap_to_end:
                end_val = self._scroll_anim.endValue()
                if end_val is not None:
                    self.verticalScrollBar().setValue(int(end_val))
            self._scroll_anim.stop()
        if self._overscroll_anim.state() == QPropertyAnimation.State.Running:
            self._overscroll_anim.stop()
        if self._smooth_scroll_timer.isActive():
            self._smooth_scroll_timer.stop()
        if self._overscroll_return_timer.isActive():
            self._overscroll_return_timer.stop()
        self._scroll_target = float(self.verticalScrollBar().value())
        self._overscroll_target = 0.0
        self.set_overscroll_offset(0.0)

    def hideEvent(self, event):
        # Când schimbăm tab-ul, oprim animația de scroll ca să nu continue în background.
        self.stop_scroll_animation(snap_to_end=True)
        super().hideEvent(event)

    def showEvent(self, event):
        # Asigurăm o stare stabilă imediat la revenire pe tab.
        self.stop_scroll_animation(snap_to_end=True)
        super().showEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if self._scroll_anim.state() == QPropertyAnimation.State.Running:
            self._scroll_anim.stop()
        if self._overscroll_anim.state() == QPropertyAnimation.State.Running:
            self._overscroll_anim.stop()

        pixel_dy = event.pixelDelta().y()
        dy = pixel_dy if pixel_dy else event.angleDelta().y()
        scroll_bar = self.verticalScrollBar()
        if pixel_dy:
            step = -float(pixel_dy)
        elif abs(dy) >= 120:
            step = -60.0 * (float(dy) / 120.0)
        else:
            step = -float(dy) / 2.0

        current_val = float(scroll_bar.value())
        if not self._smooth_scroll_timer.isActive():
            self._scroll_target = current_val

        raw_target = self._scroll_target + step
        maximum = scroll_bar.maximum()
        target_val = max(0.0, min(raw_target, float(maximum)))

        pulling_top = self._scroll_target <= 0 and raw_target < 0
        pulling_bottom = self._scroll_target >= maximum and raw_target > maximum and maximum > 0
        if self.overscroll_enabled and (pulling_top or pulling_bottom):
            direction = 1 if pulling_top else -1
            wheel_energy = min(120.0, abs(float(dy)))
            pull = min(self.overscroll_max_offset, abs(raw_target - target_val) * 0.16 + wheel_energy * 0.045)
            self._overscroll_target = max(
                -self.overscroll_max_offset,
                min(self.overscroll_max_offset, self._overscroll_target + direction * pull)
            )
            self._scroll_target = target_val
            self._overscroll_return_timer.start(140)
            self._ensure_smooth_scroll_timer()
            event.accept()
            return

        self._scroll_target = target_val
        if self._overscroll_offset or self._overscroll_target:
            self._overscroll_target = 0.0
        self._ensure_smooth_scroll_timer()
        event.accept()

    def _ensure_smooth_scroll_timer(self):
        if not self._smooth_scroll_timer.isActive():
            self._smooth_scroll_timer.start()

    def _release_overscroll(self):
        self._overscroll_target = 0.0
        self._ensure_smooth_scroll_timer()

    def _tick_smooth_scroll(self):
        scroll_bar = self.verticalScrollBar()
        self._scroll_target = max(0.0, min(float(self._scroll_target), float(scroll_bar.maximum())))
        current = float(scroll_bar.value())
        diff = self._scroll_target - current

        if abs(diff) > 0.5:
            next_value = current + diff * 0.26
            next_int = int(round(next_value))
            if next_int == int(current):
                next_int = int(current + (1 if diff > 0 else -1))
            scroll_bar.setValue(max(0, min(next_int, scroll_bar.maximum())))
        else:
            scroll_bar.setValue(int(round(self._scroll_target)))

        offset_diff = self._overscroll_target - self._overscroll_offset
        if abs(offset_diff) > 0.12:
            ease = 0.13 if abs(self._overscroll_target) < 0.2 else 0.18
            self.set_overscroll_offset(self._overscroll_offset + offset_diff * ease)
        elif self._overscroll_offset:
            self.set_overscroll_offset(0.0 if abs(self._overscroll_target) < 0.12 else self._overscroll_target)

        scroll_done = abs(float(scroll_bar.value()) - self._scroll_target) <= 0.5
        overscroll_done = abs(self._overscroll_offset - self._overscroll_target) <= 0.12
        if scroll_done and overscroll_done and not self._overscroll_return_timer.isActive():
            self._smooth_scroll_timer.stop()


# ═══════════════════════════════════════════════════════════════════
# VIRTUALIZER SYSTEM — Model-View delegate + async artwork + LRU cache
# ═══════════════════════════════════════════════════════════════════

class _ArtLoadSignals(QObject):
    """Signals emitted by background artwork loader jobs."""
    loaded = pyqtSignal(int, str, QImage, int)  # row, art_path, image, generation


class _ArtLoadJob(QRunnable):
    """Reads an image from disk on a background thread (as QImage, NOT QPixmap)."""
    def __init__(self, row, art_path, generation, phys_size):
        super().__init__()
        self.row = row
        self.art_path = art_path
        self.generation = generation
        self.phys_size = phys_size
        self.signals = _ArtLoadSignals()

    def run(self):
        if not self.art_path or not os.path.exists(self.art_path):
            self.signals.loaded.emit(self.row, self.art_path, QImage(), self.generation)
            return
        img = QImage(self.art_path)
        if img.isNull():
            self.signals.loaded.emit(self.row, self.art_path, QImage(), self.generation)
            return
        # Pre-scale to physical pixel size so main-thread work is minimal
        img = img.scaled(self.phys_size, self.phys_size,
                         Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                         Qt.TransformationMode.SmoothTransformation)
        self.signals.loaded.emit(self.row, self.art_path, img, self.generation)


class ArtworkCache:
    """LRU cache mapping art_path → QPixmap (already rounded/cropped)."""
    def __init__(self, max_size=300):
        self._store = OrderedDict()
        self._max = max_size

    def get(self, key):
        if key not in self._store:
            return None
        val = self._store.pop(key)
        self._store[key] = val   # move to end (most recent)
        return val

    def put(self, key, value):
        self._store[key] = value
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def clear(self):
        self._store.clear()


class PlaylistDelegate(QStyledItemDelegate):
    """
    Universal delegate – paints folder / file / album / artist rows
    using only data roles on QListWidgetItem.  No widget per row.
    """
    # Icon paths (class-level, computed once)
    _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _folder_icon_path = os.path.join(_base_dir, 'icons', 'folder-solid-full.svg')
    _music_icon_path = os.path.join(_base_dir, 'icons', 'playlist', 'music-solid-full.svg')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fg_color = QColor("#FFFFFF")
        self.primary_color = QColor("#00AAFF")
        self.icon_color = QColor("#CCCCCC")
        self.hover_bg = QColor(255, 255, 255, 13)   # rgba(255,255,255,0.05)
        self.selected_bg = QColor(255, 255, 255, 25)
        self.base_icon = 64
        self.base_row = 84
        self.zoom = 1.0
        self.hover_enabled = True

        # Pre-render SVG fallback icons (will be re-generated on zoom/color change)
        self._rebuild_fallback_icons()

    def _rebuild_fallback_icons(self):
        s = self._icon_size()
        self._folder_pix = self._colored_svg(self._folder_icon_path, self.icon_color.name(), s)
        self._music_pix = self._colored_svg(self._music_icon_path, self.icon_color.name(), s)
        self._music_stats_pix = self._colored_svg(self._music_icon_path, self.primary_color.name(), max(10, int(14 * self.zoom)))

    @staticmethod
    def _colored_svg(path, color_hex, size):
        icon = IconHelper.get_colored_icon(path, color_hex, size=size)
        if icon.isNull():
            return QPixmap()
        return icon.pixmap(size, size)

    def set_colors(self, fg, primary, icon_color="#CCCCCC"):
        self.fg_color = QColor(fg)
        self.primary_color = QColor(primary)
        self.icon_color = QColor(icon_color)
        self._rebuild_fallback_icons()

    def set_zoom(self, z):
        self.zoom = max(0.5, min(3.0, z))
        self._rebuild_fallback_icons()

    def _icon_size(self):
        return int(self.base_icon * self.zoom)

    def _row_height(self):
        return int(self.base_row * self.zoom)

    def sizeHint(self, option, index):
        item_type = index.data(ROLE_ITEM_TYPE) or "file"
        if item_type == "separator":
            # Lăsăm separatorul să folosească înălțimea mică setată de noi (ex: 18px)
            size = index.data(Qt.ItemDataRole.SizeHintRole)
            if size and size.isValid():
                return size
            return QSize(option.rect.width(), int(18 * self.zoom))
            
        return QSize(option.rect.width(), self._row_height())

    # ── paint ──────────────────────────────────────────────────────
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        overscroll = getattr(self.parent(), "_overscroll_offset", 0.0)
        if overscroll:
            viewport = self.parent().viewport() if self.parent() else None
            viewport_h = viewport.height() if viewport else 0
            falloff_ratio = getattr(self.parent(), "overscroll_falloff_ratio", 0.42)
            falloff = max(160.0, min(760.0, viewport_h * falloff_ratio)) if viewport_h else 360.0
            if overscroll > 0:
                distance_from_edge = max(0.0, float(option.rect.top()))
            else:
                distance_from_edge = max(0.0, float(viewport_h - option.rect.bottom()))
            influence = min(1.0, distance_from_edge / falloff)
            eased = influence * influence * (3.0 - 2.0 * influence)
            global_part = overscroll * getattr(self.parent(), "overscroll_global_strength", 0.45)
            spread_part = overscroll * getattr(self.parent(), "overscroll_spread_strength", 0.75) * eased
            painter.translate(0, global_part + spread_part)

        rect = option.rect.adjusted(2, 2, -2, -2)
        radius = 15

        item_type = index.data(ROLE_ITEM_TYPE) or "file"

        # ── Separator (section header in search results) ──
        if item_type == "separator":
            z = self.zoom
            sep_font = QFont()
            sep_font.setBold(True)
            sep_font.setPixelSize(max(8, int(13 * z)))
            painter.setPen(QPen(self.primary_color))
            painter.setFont(sep_font)
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            
            # 1. Aliniem textul SUS (lipit de marginea superioară a rândului)
            # Folosim option.rect direct pentru a anula orice padding interior de sus
            text_rect = option.rect.adjusted(12, int(2 * z), -10, 0)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text)
            
            # 2. Calculăm spațiul rămas pentru linia orizontală
            fm = painter.fontMetrics()
            text_width = fm.horizontalAdvance(text)
            line_start_x = option.rect.left() + 12 + text_width + int(10 * z)
            line_end_x = option.rect.right() - int(20 * z)
            
            # Centram linia fix pe mijlocul vizual al fontului, măsurat de sus
            line_y = option.rect.top() + int(2 * z) + (fm.ascent() // 2) + int(1 * z)
            
            if line_start_x < line_end_x:
                line_color = QColor(self.primary_color)
                line_color.setAlpha(80) # Transparență elegantă pentru linie
                painter.setPen(QPen(line_color, max(1, int(1 * z))))
                painter.drawLine(line_start_x, line_y, line_end_x, line_y)
                
            painter.restore()
            return

        # Background on hover / selection
        if self.hover_enabled and option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.hover_bg)
            painter.drawRoundedRect(rect, radius, radius)

        is_folder = (item_type == "dir")
        is_circle = (item_type == "artist_group")

        icon_s = self._icon_size()
        left_margin = 10
        top_margin = (rect.height() - icon_s) // 2
        icon_rect = QRect(rect.left() + left_margin, rect.top() + top_margin, icon_s, icon_s)

        # ── Artwork ──
        deco = index.data(Qt.ItemDataRole.DecorationRole)
        pix = None
        if isinstance(deco, QPixmap) and not deco.isNull():
            pix = deco
        elif isinstance(deco, QIcon) and not deco.isNull():
            pix = deco.pixmap(icon_s, icon_s)

        if pix and not pix.isNull():
            # Draw rounded-rect clipped artwork
            painter.save()
            clip_path = QPainterPath()
            if is_circle:
                clip_path.addEllipse(QRectF(icon_rect))
            elif is_folder or item_type == "album_group":
                # Albumele și Folderele vor avea colțuri ușor curbate (mai mici)
                clip_path.addRoundedRect(QRectF(icon_rect), 4 * self.zoom, 4 * self.zoom)
            else:
                # Fișierele (melodiile) păstrează colțurile mult curbate
                clip_path.addRoundedRect(QRectF(icon_rect), 14 * self.zoom, 14 * self.zoom)
            painter.setClipPath(clip_path)
            painter.drawPixmap(icon_rect, pix)
            painter.restore()
        else:
            # Fallback SVG icon
            fb = self._folder_pix if is_folder else self._music_pix
            if fb and not fb.isNull():
                painter.drawPixmap(icon_rect, fb)

        # ── Text zone ──
        text_left = icon_rect.right() + 15
        text_right = rect.right() - (46 if is_folder else 10)

        z = self.zoom
        title = index.data(Qt.ItemDataRole.DisplayRole) or ""
        subtitle = index.data(ROLE_SUBTITLE) or ""
        info = index.data(ROLE_INFO) or ""

        # Title (bold, primary color if current song, else fg)
        is_current = index.data(ROLE_IS_CURRENT)
        title_color = self.primary_color if is_current else self.fg_color
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPixelSize(max(9, int(14 * z)))
        painter.setPen(QPen(title_color))
        painter.setFont(title_font)
        title_rect = QRect(text_left, rect.top() + int(14 * z), text_right - text_left, int(24 * z))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)

        # Subtitle
        sub_font = QFont()
        sub_font.setPixelSize(max(8, int(12 * z)))
        if is_folder:
            # Folder stats line: small music icon + text in primary color
            stats_y = rect.top() + int(42 * z)
            stats_icon_s = max(10, int(14 * z))
            if self._music_stats_pix and not self._music_stats_pix.isNull():
                painter.drawPixmap(text_left, stats_y, stats_icon_s, stats_icon_s, self._music_stats_pix)
            painter.setPen(QPen(self.primary_color))
            painter.setFont(sub_font)
            sub_font.setWeight(QFont.Weight.Medium)
            sub_rect = QRect(text_left + stats_icon_s + 6, stats_y, text_right - text_left - stats_icon_s - 6, int(20 * z))
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, subtitle)
        else:
            # Artist line (fg color)
            painter.setPen(QPen(self.fg_color))
            painter.setFont(sub_font)
            sub_rect = QRect(text_left, rect.top() + int(38 * z), text_right - text_left, int(20 * z))
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, subtitle)

            # Info line (duration | ext — primary color)
            if info:
                info_font = QFont()
                info_font.setPixelSize(max(8, int(10 * z)))
                painter.setPen(QPen(self.primary_color))
                painter.setFont(info_font)
                info_rect = QRect(text_left, rect.top() + int(58 * z), text_right - text_left, int(16 * z))
                painter.drawText(info_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, info)

        # Folder right chevron icon
        if is_folder:
            chev_s = int(24 * z)
            chev_x = rect.right() - chev_s - int(14 * z)
            chev_y = rect.top() + (rect.height() - chev_s) // 2
            fb = self._folder_pix
            if fb and not fb.isNull():
                painter.drawPixmap(chev_x, chev_y, chev_s, chev_s, fb)

        painter.restore()


class ListVirtualizer(QObject):
    """
    Viewport-aware artwork loader.  Watches scroll position and loads
    artwork only for visible rows + a small buffer.  Uses ArtworkCache
    so re-scrolling is instant.
    """
    def __init__(self, list_widget, delegate, art_path_resolver=None):
        super().__init__(list_widget)
        self.lw = list_widget
        self.delegate = delegate
        self.art_path_resolver = art_path_resolver
        self.cache = ArtworkCache(300)
        self.loading = set()
        self.generation = 0
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(4)
        self._enabled = False

        self.lw.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.lw.viewport().installEventFilter(self)

    def _alive(self):
        try:
            self.lw.viewport().rect()
            return True
        except RuntimeError:
            return False

    def eventFilter(self, obj, event):
        if not self._alive():
            return False
        if obj is self.lw.viewport() and self._enabled:
            if event.type() == QEvent.Type.Resize:
                self.load_visible()
        return super().eventFilter(obj, event)

    def set_enabled(self, on):
        self._enabled = on
        if on:
            self.load_visible()

    def bump_generation(self):
        self.generation += 1
        self.loading.clear()

    def _on_scroll(self):
        if self._enabled:
            self.load_visible()

    # ── core: figure out visible rows and request their artwork ──
    def load_visible(self):
        if not self._alive() or not self._enabled or self.lw.count() == 0:
            return
        vp = self.lw.viewport().rect()
        model = self.lw.model()

        # Gasim primul rand vizibil direct (indexAt), fara sa pornim de la 0.
        # Foloseam visualItemRect(item), care cauta indexul randului printr-o
        # parcurgere liniara a listei (indexFromItem) - facuta pentru fiecare
        # rand de la 0 pana la scroll-ul curent, la fiecare scroll tick. Pe o
        # biblioteca mare, scrollata jos, asta era patratic si ingheta UI-ul.
        start_index = self.lw.indexAt(vp.topLeft())
        start_row = start_index.row() if start_index.isValid() else 0

        rows = []
        for r in range(start_row, self.lw.count()):
            ir = self.lw.visualRect(model.index(r, 0))
            if ir.bottom() < vp.top():
                continue
            if ir.top() > vp.bottom():
                break
            rows.append(r)
        if not rows:
            return

        # Buffer: ±15 rows around visible
        lo = max(0, rows[0] - 15)
        hi = min(self.lw.count() - 1, rows[-1] + 15)
        # Priority: visible first, then buffer
        candidates = list(rows) + [r for r in range(lo, hi + 1) if r not in rows]
        for r in candidates:
            self._request(r)

    def _request(self, row):
        if row < 0 or row >= self.lw.count():
            return
        item = self.lw.item(row)
        if not item:
            return
        art_path = item.data(ROLE_ART_PATH)
        if not art_path and self.art_path_resolver:
            try:
                lookup_path = item.data(ROLE_ART_SOURCE_PATH) or item.data(Qt.ItemDataRole.UserRole)
                art_path = self.art_path_resolver(
                    lookup_path,
                    item.data(ROLE_ITEM_TYPE),
                )
            except Exception:
                art_path = None
            if art_path:
                item.setData(ROLE_ART_PATH, art_path)
        if not art_path:
            return
        # Already has artwork set?
        deco = item.data(Qt.ItemDataRole.DecorationRole)
        if deco and not (isinstance(deco, QPixmap) and deco.isNull()) and not (isinstance(deco, QIcon) and deco.isNull()):
            return
        # In cache?
        cached = self.cache.get(art_path)
        if cached is not None:
            item.setData(Qt.ItemDataRole.DecorationRole, cached)
            return
        # Already loading?
        if row in self.loading:
            return
        self.loading.add(row)
        phys = int(128 * max(1.0, self.delegate.zoom))
        gen = self.generation
        job = _ArtLoadJob(row, art_path, gen, phys)
        job.signals.loaded.connect(self._on_loaded)
        self.pool.start(job)

    def _on_loaded(self, row, art_path, image, gen):
        self.loading.discard(row)
        if gen != self.generation:
            return
        if not self._alive():
            return
        if row < 0 or row >= self.lw.count():
            return
        item = self.lw.item(row)
        if not item or item.data(ROLE_ART_PATH) != art_path:
            return
        if image.isNull():
            return
        pix = QPixmap.fromImage(image)
        if pix.isNull():
            return
        self.cache.put(art_path, pix)
        item.setData(Qt.ItemDataRole.DecorationRole, pix)
