from PyQt6.QtWidgets import QPushButton, QLabel, QGraphicsOpacityEffect, QApplication
from PyQt6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QRect, QPoint, Qt
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPainterPath, QPixmap

from animations.overlay import TransitionOverlay


class GlitterButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(200, 50)

        self.setStyleSheet("""
            QPushButton {
                background-color: #00AAFF;
                color: white;
                border-radius: 25px;
                font-size: 16px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover { background-color: #0088CC; }
        """)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_anim)
        self.anim_pos = 0.0

    def enterEvent(self, event):
        self.anim_pos = 0.0
        self.timer.start(20)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.timer.stop()
        self.anim_pos = 0.0
        self.update()
        super().leaveEvent(event)

    def update_anim(self):
        self.anim_pos += 0.05
        if self.anim_pos > 1.2:
            self.timer.stop()
            self.update()
            return
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if not self.timer.isActive():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        shine_width = width * 0.4
        start_x = -shine_width
        end_x = width
        current_x = start_x + (self.anim_pos * (end_x - start_x + shine_width))

        gradient = QLinearGradient(current_x, 0, current_x + shine_width, 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.01, QColor(255, 255, 255, 180))
        gradient.setColorAt(0.99, QColor(255, 255, 255, 180))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))

        path = QPainterPath()
        path.addRoundedRect(0, 0, width, height, height / 2, height / 2)
        painter.setClipPath(path)

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)

        painter.save()
        painter.translate(current_x + shine_width / 2, height / 2)
        painter.rotate(25)
        painter.translate(-(current_x + shine_width / 2), -height / 2)
        painter.drawRect(int(current_x), -50, int(shine_width), height + 100)
        painter.restore()

    def apply_zoom(self, factor):
        width = max(1, int(200 * factor))
        height = max(1, int(50 * factor))
        font_size = max(1, int(16 * factor))
        radius = height // 2
        self.setFixedSize(width, height)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #00AAFF;
                color: white;
                border-radius: {radius}px;
                font-size: {font_size}px;
                font-weight: bold;
                border: none;
            }}
            QPushButton:hover {{ background-color: #0088CC; }}
        """)


class PlaylistTabAnimations:
    def __init__(self, tab):
        self.tab = tab
        self._page_fade_out_anim = None
        self._page_fade_in_anim = None
        self._enter_snapshot_anim = None
        self._page_fade_widgets = []
        self.back_anim_group = None
        self.enter_anim_group = None
        self._hierarchy_anim_group = None
        self._hierarchy_overlays = []
        self._hierarchy_effect_targets = []

    def _header_motion_duration(self):
        if getattr(self.tab, 'anim_manager', None):
            return max(180, int(getattr(self.tab.anim_manager, 'speed_move', 350)))
        return 350

    def _header_fade_duration(self, scale=0.72, minimum=180):
        return max(minimum, int(self._header_motion_duration() * scale))

    def _playlist_anim_root(self):
        if getattr(self.tab, 'anim_manager', None) and getattr(self.tab.anim_manager, 'main', None):
            return self.tab.anim_manager.main
        return self.tab.window() or self.tab

    def _playlist_global_rect(self, widget):
        root = self._playlist_anim_root()
        return QRect(widget.mapTo(root, QPoint(0, 0)), widget.size())

    def _stop_playlist_hierarchy_animation(self):
        if self._hierarchy_anim_group and self._hierarchy_anim_group.state() == QPropertyAnimation.State.Running:
            self._hierarchy_anim_group.stop()
        self._hierarchy_anim_group = None
        self._cleanup_playlist_hierarchy_animation()

    def _cleanup_playlist_hierarchy_animation(self):
        for target in self._hierarchy_effect_targets:
            try:
                if target:
                    target.setGraphicsEffect(None)
            except Exception:
                pass
        self._hierarchy_effect_targets.clear()

        for overlay in self._hierarchy_overlays:
            try:
                overlay.hide()
                overlay.deleteLater()
            except Exception:
                pass
        self._hierarchy_overlays.clear()

    def _create_playlist_overlay_anim(self, group, pixmap, start_rect, end_rect, start_radius, end_radius, render_mode, shape_mode="rounded_rect"):
        if not pixmap or pixmap.isNull() or not start_rect or not end_rect:
            return None

        overlay = TransitionOverlay(self._playlist_anim_root())
        overlay.setPixmap(pixmap)
        overlay.setScaledContents(True)
        overlay.setGeometry(start_rect)
        overlay.radius = start_radius
        overlay.render_mode = render_mode
        overlay.shape_mode = shape_mode
        overlay.raise_()
        overlay.show()
        self._hierarchy_overlays.append(overlay)

        anim_geom = QPropertyAnimation(overlay, b"geometry")
        anim_geom.setDuration(self._header_motion_duration())
        anim_geom.setStartValue(start_rect)
        anim_geom.setEndValue(end_rect)
        anim_geom.setEasingCurve(QEasingCurve.Type.OutQuad)
        group.addAnimation(anim_geom)

        if start_radius != end_radius:
            anim_radius = QPropertyAnimation(overlay, b"radius")
            anim_radius.setDuration(self._header_motion_duration())
            anim_radius.setStartValue(start_radius)
            anim_radius.setEndValue(end_radius)
            anim_radius.setEasingCurve(QEasingCurve.Type.OutQuad)
            group.addAnimation(anim_radius)

        return overlay

    def _add_playlist_fade_anim(self, group, target, start, end, duration):
        if not target:
            return
        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)
        self._hierarchy_effect_targets.append(target)
        animation = QPropertyAnimation(effect, b"opacity")
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        group.addAnimation(animation)

    def cleanup_page_fade_effects(self):
        for widget in self._page_fade_widgets:
            try:
                if widget:
                    widget.setGraphicsEffect(None)
            except Exception:
                pass
        self._page_fade_widgets.clear()

    def stop_page_fade_transition(self):
        for anim in (self._page_fade_out_anim, self._page_fade_in_anim):
            if anim and anim.state() == QPropertyAnimation.State.Running:
                anim.stop()
        self._page_fade_out_anim = None
        self._page_fade_in_anim = None
        self.cleanup_page_fade_effects()

    def create_browser_snapshot_overlay(self):
        snapshot = QLabel(self.tab)
        snapshot.setPixmap(self.tab.page_browser.grab())
        snapshot_rect = QRect(self.tab.page_browser.mapTo(self.tab, QPoint(0, 0)), self.tab.page_browser.size())
        snapshot.setGeometry(snapshot_rect)
        snapshot.show()
        snapshot.raise_()
        return snapshot

    def create_static_item_overlay(self, overlay_data):
        if not overlay_data:
            return None

        pixmap = overlay_data.get("pixmap")
        rect = overlay_data.get("rect")
        if not pixmap or pixmap.isNull() or not rect or not rect.isValid():
            return None

        overlay = QLabel(self.tab)
        overlay.setPixmap(pixmap)
        overlay.setGeometry(rect)
        overlay.show()
        overlay.raise_()
        return overlay

    def cleanup_overlay_widget(self, overlay):
        if not overlay:
            return
        try:
            overlay.hide()
            overlay.deleteLater()
        except Exception:
            pass

    def _build_drifted_rect(self, rect, drift_scale=0.10, grow_scale=0.18, direction_x=-1, direction_y=-1):
        drift = max(28, int(min(rect.width(), rect.height()) * max(drift_scale, 0.10)))
        grow_w = max(88, int(rect.width() * max(grow_scale, 0.18)))
        grow_h = max(64, int(rect.height() * max(grow_scale, 0.18)))
        end_rect = QRect(rect)
        end_rect.adjust(-grow_w, -grow_h, grow_w, grow_h)
        end_rect.translate(int(direction_x * drift), int(direction_y * drift))
        return end_rect

    def _build_rect_with_reference_motion(self, rect, reference_rect, drift_scale=0.10, grow_scale=0.18, direction_x=-1, direction_y=-1):
        end_rect = self._build_drifted_rect(rect, drift_scale=drift_scale, grow_scale=grow_scale, direction_x=direction_x, direction_y=direction_y)
        if not reference_rect or not reference_rect.isValid():
            return end_rect

        reference_end_rect = self._build_drifted_rect(reference_rect, drift_scale=drift_scale, grow_scale=grow_scale, direction_x=direction_x, direction_y=direction_y)
        motion_delta = reference_end_rect.topLeft() - reference_rect.topLeft()
        current_delta = end_rect.topLeft() - rect.topLeft()
        end_rect.translate(motion_delta - current_delta)
        return end_rect

    def _add_static_overlay_exit_motion(self, animation_group, overlay, duration=None, direction_x=1, direction_y=1):
        if not overlay:
            return None

        move_duration = duration if duration is not None else self._header_motion_duration()
        fade_duration = self._header_fade_duration(scale=0.72, minimum=140)

        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)

        anim_opacity = QPropertyAnimation(effect, b"opacity")
        anim_opacity.setDuration(fade_duration)
        anim_opacity.setStartValue(1.0)
        anim_opacity.setEndValue(0.0)
        anim_opacity.setEasingCurve(QEasingCurve.Type.OutQuad)
        animation_group.addAnimation(anim_opacity)

        start_rect = QRect(overlay.geometry())
        end_rect = self._build_drifted_rect(start_rect, direction_x=direction_x, direction_y=direction_y)
        anim_geom = QPropertyAnimation(overlay, b"geometry")
        anim_geom.setDuration(move_duration)
        anim_geom.setStartValue(start_rect)
        anim_geom.setEndValue(end_rect)
        anim_geom.setEasingCurve(QEasingCurve.Type.OutQuad)
        animation_group.addAnimation(anim_geom)

        return effect

    def _add_static_overlay_entry_motion(self, animation_group, overlay, duration=None, direction_x=1, direction_y=1):
        if not overlay:
            return None

        move_duration = duration if duration is not None else self._header_motion_duration()
        fade_duration = self._header_fade_duration(scale=0.72, minimum=140)

        effect = QGraphicsOpacityEffect(overlay)
        effect.setOpacity(0.0)
        overlay.setGraphicsEffect(effect)

        end_rect = QRect(overlay.geometry())
        start_rect = self._build_drifted_rect(end_rect, direction_x=direction_x, direction_y=direction_y)
        overlay.setGeometry(start_rect)

        anim_opacity = QPropertyAnimation(effect, b"opacity")
        anim_opacity.setDuration(fade_duration)
        anim_opacity.setStartValue(0.0)
        anim_opacity.setEndValue(1.0)
        anim_opacity.setEasingCurve(QEasingCurve.Type.OutQuad)
        animation_group.addAnimation(anim_opacity)

        anim_geom = QPropertyAnimation(overlay, b"geometry")
        anim_geom.setDuration(move_duration)
        anim_geom.setStartValue(start_rect)
        anim_geom.setEndValue(end_rect)
        anim_geom.setEasingCurve(QEasingCurve.Type.OutQuad)
        animation_group.addAnimation(anim_geom)

        return effect

    def _add_snapshot_exit_motion(self, animation_group, snapshot, duration=None, direction_x=-1, direction_y=-1):
        if not snapshot:
            return None

        move_duration = duration if duration is not None else self._header_motion_duration()

        eff_snap = QGraphicsOpacityEffect(snapshot)
        snapshot.setGraphicsEffect(eff_snap)

        anim_snap = QPropertyAnimation(eff_snap, b"opacity")
        anim_snap.setDuration(self._header_fade_duration(scale=0.72, minimum=140))
        anim_snap.setStartValue(1.0)
        anim_snap.setEndValue(0.0)
        anim_snap.setEasingCurve(QEasingCurve.Type.OutQuad)
        animation_group.addAnimation(anim_snap)

        start_rect = QRect(snapshot.geometry())
        end_rect = self._build_drifted_rect(start_rect, direction_x=direction_x, direction_y=direction_y)
        anim_geom = QPropertyAnimation(snapshot, b"geometry")
        anim_geom.setDuration(move_duration)
        anim_geom.setStartValue(start_rect)
        anim_geom.setEndValue(end_rect)
        anim_geom.setEasingCurve(QEasingCurve.Type.OutQuad)
        animation_group.addAnimation(anim_geom)

        return eff_snap

    def _build_static_overlay_data_for_target(self, target_id):
        if not target_id:
            return None

        zoom = getattr(self.tab, 'global_zoom', 1.0)
        for index in range(self.tab.file_list.count()):
            item = self.tab.file_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) != target_id:
                continue

            rect = self.tab.file_list.visualItemRect(item)
            if not rect.isValid() or not self.tab.file_list.viewport().rect().intersects(rect):
                continue

            item_pixmap = self.tab.file_list.viewport().grab(rect)
            if item_pixmap.isNull():
                return None

            icon_size = int(64 * zoom)
            icon_rect = QRect(10, (rect.height() - icon_size) // 2, icon_size, icon_size)
            painter = QPainter(item_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(icon_rect, Qt.GlobalColor.transparent)
            painter.end()

            overlay_top_left = self.tab.file_list.viewport().mapTo(self.tab, rect.topLeft())
            return {'pixmap': item_pixmap, 'rect': QRect(overlay_top_left, rect.size())}

        return None

    def _set_opacity_effect(self, widget, opacity):
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(opacity)
        widget.setGraphicsEffect(effect)
        return effect

    def _add_parallel_opacity_animation(self, animation_group, effects, duration, start_value, end_value):
        animations = []
        for effect in effects:
            if not effect:
                continue
            animation = QPropertyAnimation(effect, b"opacity")
            animation.setDuration(duration)
            animation.setStartValue(start_value)
            animation.setEndValue(end_value)
            animation_group.addAnimation(animation)
            animations.append(animation)
        return animations

    def hide_browser_live_content(self, include_nav=True):
        effects = [self._set_opacity_effect(self.tab.page_browser, 0.0)]
        if include_nav and hasattr(self.tab, "nav_container") and self.tab.nav_container:
            effects.append(self._set_opacity_effect(self.tab.nav_container, 0.0))
        return effects

    def clear_browser_live_content_effects(self):
        self.tab.page_browser.setGraphicsEffect(None)
        if hasattr(self.tab, "nav_container") and self.tab.nav_container:
            self.tab.nav_container.setGraphicsEffect(None)
        self.tab.file_list.setGraphicsEffect(None)
        self.tab.ui.header.setGraphicsEffect(None)

    def animate_playlist_page_switch(self, update_func, target_widget=None, total_duration=None):
        if total_duration is None:
            # Aceeasi reglare ca restul fade-urilor din aplicatie.
            manager = getattr(self.tab.window(), 'anim_manager', None)
            total_duration = int(getattr(manager, 'PAGE_SWITCH_MS', 240) or 240)

        current_widget = self.tab.stack.currentWidget()
        target_widget = target_widget or self.tab.page_browser

        # Animam ori de cate ori chiar se schimba pagina. Inainte conditia era
        # "doar daca plecam de pe dashboard", deci intoarcerea inapoi la
        # dashboard (din Folders, All Songs, Albums, Artists etc.) se facea
        # instant, fara fade.
        if current_widget is target_widget:
            update_func()
            return

        self.stop_page_fade_transition()

        out_effect = QGraphicsOpacityEffect(current_widget)
        out_effect.setOpacity(1.0)
        current_widget.setGraphicsEffect(out_effect)
        self._page_fade_widgets.append(current_widget)

        fade_out = QPropertyAnimation(out_effect, b"opacity", self.tab)
        fade_out.setDuration(total_duration // 2)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.OutQuad)

        def after_fade_out():
            try:
                current_widget.setGraphicsEffect(None)
            except Exception:
                pass
            if current_widget in self._page_fade_widgets:
                self._page_fade_widgets.remove(current_widget)

            update_func()

            actual_target = target_widget or self.tab.stack.currentWidget()
            if not actual_target:
                self.stop_page_fade_transition()
                return

            in_effect = QGraphicsOpacityEffect(actual_target)
            in_effect.setOpacity(0.0)
            actual_target.setGraphicsEffect(in_effect)
            self._page_fade_widgets.append(actual_target)

            fade_in = QPropertyAnimation(in_effect, b"opacity", self.tab)
            fade_in.setDuration(total_duration // 2)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.InQuad)

            def after_fade_in():
                self.stop_page_fade_transition()

            self._page_fade_in_anim = fade_in
            fade_in.finished.connect(after_fade_in)
            fade_in.start()

        self._page_fade_out_anim = fade_out
        fade_out.finished.connect(after_fade_out)
        fade_out.start()

    def animate_from_header(self, header_pix, target_id, header_rect=None):
        if not header_pix or not target_id:
            return

        self._stop_playlist_hierarchy_animation()

        start_rect = header_rect if header_rect else self._playlist_global_rect(self.tab.ui.header)
        end_rect = None

        QApplication.processEvents()

        zoom = getattr(self.tab, 'global_zoom', 1.0)
        for index in range(self.tab.file_list.count()):
            item = self.tab.file_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == target_id:
                self.tab.file_list.scrollToItem(item, self.tab.file_list.ScrollHint.PositionAtCenter)
                QApplication.processEvents()

                item_rect = self.tab.file_list.visualItemRect(item)
                if item_rect.isValid():
                    icon_size = int(64 * zoom)
                    icon_rect = QRect(
                        item_rect.left() + 10,
                        item_rect.top() + (item_rect.height() - icon_size) // 2,
                        icon_size,
                        icon_size,
                    )
                    global_pos = self.tab.file_list.viewport().mapTo(self._playlist_anim_root(), icon_rect.topLeft())
                    end_rect = QRect(global_pos, icon_rect.size())
                break

        if not end_rect:
            return

        self._hierarchy_anim_group = QParallelAnimationGroup()
        self._create_playlist_overlay_anim(self._hierarchy_anim_group, header_pix, start_rect, end_rect, 30.0, 10.0, "cover")
        self._hierarchy_anim_group.finished.connect(self._cleanup_playlist_hierarchy_animation)
        self._hierarchy_anim_group.start()

    def animate_to_header(self, start_rect, pixmap, on_finished=None, previous_header_pixmap=None, previous_header_reference_rect=None):
        if not start_rect or not pixmap:
            self.tab.ui.header.set_content_opacity(1.0)
            if on_finished:
                on_finished()
            return

        self._stop_playlist_hierarchy_animation()

        header_widget = self.tab.ui.header
        if hasattr(header_widget, 'update_geometry_state'):
            header_widget.update_geometry_state()

        header_widget.updateGeometry()
        if header_widget.parentWidget() and header_widget.parentWidget().layout():
            header_widget.parentWidget().layout().activate()
            header_widget.parentWidget().adjustSize()

        QApplication.processEvents()

        header_rect = self._playlist_global_rect(header_widget)
        if self.tab.isVisible():
            playlist_rect = self._playlist_global_rect(self.tab)
            minimum_expected_width = max(120, int(playlist_rect.width() * 0.35))
            if header_rect.width() < minimum_expected_width and header_widget.parentWidget():
                parent_rect = self._playlist_global_rect(header_widget.parentWidget())
                if parent_rect.width() >= minimum_expected_width:
                    header_rect = parent_rect

        end_rect = header_rect

        if hasattr(header_widget, 'set_content_opacity'):
            header_widget.set_content_opacity(0.0)

        self._hierarchy_anim_group = QParallelAnimationGroup()

        if previous_header_pixmap and not previous_header_pixmap.isNull():
            previous_end_rect = self._build_rect_with_reference_motion(
                end_rect,
                previous_header_reference_rect,
                drift_scale=0.10,
                grow_scale=0.18,
            )

            old_overlay = self._create_playlist_overlay_anim(
                self._hierarchy_anim_group,
                previous_header_pixmap,
                end_rect,
                previous_end_rect,
                30.0,
                30.0,
                "cover",
                shape_mode="header_mask",
            )
            self._add_playlist_fade_anim(self._hierarchy_anim_group, old_overlay, 1.0, 0.0, self._header_fade_duration())

        self._create_playlist_overlay_anim(self._hierarchy_anim_group, pixmap, start_rect, end_rect, 10.0, 30.0, "cover")

        def finish():
            self._cleanup_playlist_hierarchy_animation()
            if hasattr(header_widget, 'reload_high_quality'):
                header_widget.reload_high_quality()
            if hasattr(header_widget, 'set_content_opacity'):
                header_widget.set_content_opacity(1.0)
                header_widget.update()
            if on_finished:
                on_finished()

        self._hierarchy_anim_group.finished.connect(finish)
        self._hierarchy_anim_group.start()

    def _flush_deferred_background_update(self):
        view_manager = getattr(self.tab, 'view_manager', None)
        flush = getattr(view_manager, 'flush_deferred_background_update', None)
        if callable(flush):
            flush()

    def _flush_deferred_background_update_later(self, delay_ms=0):
        QTimer.singleShot(max(0, int(delay_ms)), self._flush_deferred_background_update)

    def _settle_playlist_layout_later(self, delay_ms=0):
        view_manager = getattr(self.tab, 'view_manager', None)
        settle = getattr(view_manager, 'settle_playlist_layout', None)
        if callable(settle):
            QTimer.singleShot(max(0, int(delay_ms)), settle)

    def _add_header_arrival_motion(self, animation_group, incoming_pixmap=None):
        """ Perechea inversa a blocului previous_header_pixmap din animate_to_header
        (acolo, headerul vechi creste si dispare cand intri intr-un folder/album -
        "animatia Y"). Aici, la intoarcere, headerul la care revii (deja setat de
        load_callback, dar altfel ar aparea instant, fara nicio animatie) creste
        dintr-o pozitie usor marita/deplasata si face fade-in - "animatia -Y".

        incoming_pixmap: imaginea retinuta cand s-a intrat in acest folder (vezi
        _push_header_pixmap in playlist_navigation.py). Header-ul isi incarca
        imaginea asincron, deci daca am citi-o abia acum direct din widget, am
        prinde-o adesea neincarcata inca (arata gresit o clipa, apoi sare brusc
        la cea corecta). Cand avem valoarea retinuta, o folosim pe aceea. """
        header_widget = getattr(self.tab.ui, 'header', None)
        if not header_widget or not hasattr(header_widget, 'set_content_opacity'):
            return

        pixmap = incoming_pixmap if (incoming_pixmap and not incoming_pixmap.isNull()) else None
        if not pixmap:
            if getattr(header_widget, 'source_image', None) and not header_widget.source_image.isNull():
                pixmap = QPixmap.fromImage(header_widget.source_image)
            elif getattr(header_widget, 'pixmap', None) and not header_widget.pixmap.isNull():
                pixmap = header_widget.pixmap.copy()
        if not pixmap or pixmap.isNull():
            return

        end_rect = self._playlist_global_rect(header_widget)
        if not end_rect.isValid() or end_rect.width() <= 0:
            return
        start_rect = self._build_drifted_rect(end_rect, drift_scale=0.10, grow_scale=0.18, direction_x=-1, direction_y=-1)

        header_widget.set_content_opacity(0.0)

        overlay = self._create_playlist_overlay_anim(
            animation_group, pixmap, start_rect, end_rect, 30.0, 30.0, "cover", shape_mode="header_mask"
        )
        if overlay:
            self._add_playlist_fade_anim(animation_group, overlay, 0.0, 1.0, self._header_fade_duration())

    def animate_browser_back_to_root(self, load_callback, header_pix, folder_leaving, header_rect=None, incoming_header_pix=None):
        snapshot = self.create_browser_snapshot_overlay()
        live_effects = self.hide_browser_live_content()
        load_callback()
        static_item_overlay_data = self._build_static_overlay_data_for_target(folder_leaving)
        static_item_overlay = self.create_static_item_overlay(static_item_overlay_data)
        header_move_duration = self._header_motion_duration()

        def start_back_animations():
            self.animate_from_header(header_pix, folder_leaving, header_rect=header_rect)
            self._flush_deferred_background_update_later()

            self.back_anim_group = QParallelAnimationGroup()
            fade_duration = self._header_fade_duration(scale=0.72, minimum=160)

            self._add_snapshot_exit_motion(self.back_anim_group, snapshot, header_move_duration, direction_x=1, direction_y=1)
            self._add_static_overlay_entry_motion(self.back_anim_group, static_item_overlay, header_move_duration, direction_x=1, direction_y=1)
            self._add_parallel_opacity_animation(self.back_anim_group, live_effects, fade_duration, 0.0, 1.0)
            self._add_header_arrival_motion(self.back_anim_group, incoming_pixmap=incoming_header_pix)

            def on_back_finished():
                snapshot.hide()
                snapshot.deleteLater()
                self.cleanup_overlay_widget(static_item_overlay)
                self.clear_browser_live_content_effects()
                header_widget = getattr(self.tab.ui, 'header', None)
                if header_widget and hasattr(header_widget, 'set_content_opacity'):
                    header_widget.set_content_opacity(1.0)
                self._settle_playlist_layout_later()
                self.tab.set_hover_enabled(True)

            self.back_anim_group.finished.connect(on_back_finished)
            self.back_anim_group.start()

        QTimer.singleShot(0, start_back_animations)

    def animate_browser_back_to_parent(self, load_callback, header_pix, folder_leaving, header_rect=None, incoming_header_pix=None):
        old_pix = self.tab.file_list.grab()
        snapshot = QLabel(self.tab.page_browser)
        snapshot.setPixmap(old_pix)
        snapshot.setGeometry(self.tab.file_list.geometry())
        snapshot.show()

        effect = QGraphicsOpacityEffect(self.tab.file_list)
        self.tab.file_list.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        load_callback()
        static_item_overlay_data = self._build_static_overlay_data_for_target(folder_leaving)
        static_item_overlay = self.create_static_item_overlay(static_item_overlay_data)
        header_move_duration = self._header_motion_duration()

        def start_back_animations():
            self.animate_from_header(header_pix, folder_leaving, header_rect=header_rect)
            self._flush_deferred_background_update_later()

            self.back_anim_group = QParallelAnimationGroup()
            fade_duration = self._header_fade_duration(scale=0.72, minimum=160)

            self._add_snapshot_exit_motion(self.back_anim_group, snapshot, header_move_duration, direction_x=1, direction_y=1)
            self._add_static_overlay_entry_motion(self.back_anim_group, static_item_overlay, header_move_duration, direction_x=1, direction_y=1)

            anim_list = QPropertyAnimation(effect, b"opacity")
            anim_list.setDuration(fade_duration)
            anim_list.setStartValue(0.0)
            anim_list.setEndValue(1.0)

            self.back_anim_group.addAnimation(anim_list)
            self._add_header_arrival_motion(self.back_anim_group, incoming_pixmap=incoming_header_pix)

            def on_back_finished():
                snapshot.hide()
                snapshot.deleteLater()
                self.cleanup_overlay_widget(static_item_overlay)
                self.tab.file_list.setGraphicsEffect(None)
                header_widget = getattr(self.tab.ui, 'header', None)
                if header_widget and hasattr(header_widget, 'set_content_opacity'):
                    header_widget.set_content_opacity(1.0)
                self.tab.set_hover_enabled(True)

            self.back_anim_group.finished.connect(on_back_finished)
            self.back_anim_group.start()

        QTimer.singleShot(0, start_back_animations)

    def animate_browser_enter_from_root(self, load_callback, anim_duration, start_rect=None, pixmap=None, static_item_overlay_data=None):
        snapshot = self.create_browser_snapshot_overlay()
        static_item_overlay = self.create_static_item_overlay(static_item_overlay_data)
        live_effects = self.hide_browser_live_content(include_nav=False)
        load_callback()
        header_move_duration = self._header_motion_duration()

        delayed_nav = None
        if hasattr(self.tab, "nav_container") and self.tab.nav_container and self.tab.nav_container.isVisible():
            delayed_nav = self.tab.nav_container
            delayed_nav.hide()

        def start_enter_animations():
            def reveal_header_buttons():
                if delayed_nav:
                    delayed_nav.show()

            self.animate_to_header(start_rect, pixmap, on_finished=reveal_header_buttons)

            self.enter_anim_group = QParallelAnimationGroup()
            self._add_snapshot_exit_motion(self.enter_anim_group, snapshot, header_move_duration)
            self._add_static_overlay_exit_motion(self.enter_anim_group, static_item_overlay, header_move_duration)
            self._enter_snapshot_anim = self.enter_anim_group

            self._add_parallel_opacity_animation(
                self.enter_anim_group,
                live_effects,
                self._header_fade_duration(scale=0.45, minimum=120),
                0.0,
                1.0,
            )

            def on_enter_finished():
                snapshot.hide()
                snapshot.deleteLater()
                self.cleanup_overlay_widget(static_item_overlay)
                self.clear_browser_live_content_effects()
                self._enter_snapshot_anim = None
                self.tab.set_hover_enabled(True)

            self.enter_anim_group.finished.connect(on_enter_finished)
            self.enter_anim_group.start()

        QTimer.singleShot(0, start_enter_animations)

    def animate_browser_forward_to_child(self, load_callback, anim_duration, start_rect=None, pixmap=None, previous_header_pixmap=None, static_item_overlay_data=None):
        snapshot = self.create_browser_snapshot_overlay()
        static_item_overlay = self.create_static_item_overlay(static_item_overlay_data)
        live_effects = self.hide_browser_live_content(include_nav=True)
        load_callback()
        header_move_duration = self._header_motion_duration()
        snapshot_rect = QRect(snapshot.geometry())

        delayed_nav = None
        if hasattr(self.tab, "nav_container") and self.tab.nav_container and self.tab.nav_container.isVisible():
            delayed_nav = self.tab.nav_container
            delayed_nav.hide()

        def start_forward_animations():
            def reveal_header_buttons():
                if delayed_nav:
                    delayed_nav.show()

            self.animate_to_header(
                start_rect,
                pixmap,
                on_finished=reveal_header_buttons,
                previous_header_pixmap=previous_header_pixmap,
                previous_header_reference_rect=snapshot_rect,
            )

            self.enter_anim_group = QParallelAnimationGroup()
            self._add_snapshot_exit_motion(self.enter_anim_group, snapshot, header_move_duration)
            self._add_static_overlay_exit_motion(self.enter_anim_group, static_item_overlay, header_move_duration)
            self._enter_snapshot_anim = self.enter_anim_group

            self._add_parallel_opacity_animation(
                self.enter_anim_group,
                live_effects,
                self._header_fade_duration(scale=0.45, minimum=120),
                0.0,
                1.0,
            )

            def on_forward_finished():
                snapshot.hide()
                snapshot.deleteLater()
                self.cleanup_overlay_widget(static_item_overlay)
                self.clear_browser_live_content_effects()
                self._enter_snapshot_anim = None
                self.tab.set_hover_enabled(True)

            self.enter_anim_group.finished.connect(on_forward_finished)
            self.enter_anim_group.start()

        QTimer.singleShot(0, start_forward_animations)
