from PyQt6.QtCore import QCoreApplication, QTimer


class NavigationController:
    def __init__(self, main_window):
        self.main = main_window
        self.anim_manager = main_window.anim_manager

    def on_tab_changed(self, index):
        # Reset Playlist Dashboard daca apasam din nou pe tab.
        if (
            index == 2
            and self.main.right_stack.isVisible()
            and self.main.right_stack.currentWidget() == self.main.ui_playlist
        ):
            self.main.ui_playlist.go_to_dashboard(reset_history=True)
            return

        updates_suspended = False

        try:
            switching_player_size = (
                (index == 0 and self.main.ui_player.current_mode == "MINI")
                or (index != 0 and self.main.ui_player.current_mode == "FULL")
            )
            if switching_player_size:
                self._prepare_waveform_for_layout_transition()

            self.main.setUpdatesEnabled(False)
            updates_suspended = True

            self._clear_player_transition_effects()

            if index == 0:
                self.main.right_stack.hide()
                self.main.ui_player.setMinimumWidth(0)
                self.main.ui_player.setMaximumWidth(16777215)
                self.main.ui_player.set_mode_full()

                self.main.split_layout.setStretch(0, 1)
                self.main.split_layout.setStretch(1, 0)
            else:
                self.main.right_stack.show()
                needs_layout_switch = self.main.ui_player.current_mode != "MINI"

                self.main.ui_player.set_mode_mini(deferred_refresh=True)

                self.main.split_layout.setStretch(0, 1)
                self.main.split_layout.setStretch(1, 3)

                if needs_layout_switch:
                    total_w = self.main.content_area.width()
                    target_player_w = total_w // 4
                    self.main.ui_player.setFixedWidth(target_player_w)

                    art = self.main.ui_player.artwork_container
                    if art:
                        art_available_w = target_player_w - 30
                        art.setFixedHeight(art_available_w)

                    self.main.split_layout.activate()
                    if self.main.ui_player.content_widget and self.main.ui_player.content_widget.layout():
                        self.main.ui_player.content_widget.layout().activate()
                    QCoreApplication.sendPostedEvents(None, 0)

                    self.main.ui_player.setMinimumWidth(0)
                    self.main.ui_player.setMaximumWidth(16777215)
                    if art:
                        art.setMinimumHeight(0)
                        art.setMaximumHeight(16777215)

                target = None
                if index == 1:
                    target = getattr(self.main, "ui_eq", None) or getattr(self.main, "placeholder_eq", None)
                elif index == 2:
                    target = self.main.ui_playlist
                elif index == 3:
                    target = getattr(self.main, "ui_settings", None) or getattr(self.main, "placeholder_settings", None)

                if self.main.right_stack.isVisible() and self.main.right_stack.currentWidget() != target:
                    self.anim_manager.animate_stack_switch(
                        self.main.right_stack,
                        self.main.right_stack.currentWidget(),
                        target,
                    )
                elif target:
                    self.main.right_stack.setCurrentWidget(target)

            self.main.ui_player._force_layout_refresh()
            if self.main.ui_player.layout():
                self.main.ui_player.layout().activate()

            self._clear_player_transition_effects()

            self.main.setUpdatesEnabled(True)
            updates_suspended = False
            self.main.update()
            self.main.bg_manager.update_background()
            if switching_player_size:
                QTimer.singleShot(120, self._fade_waveform_in_after_layout_transition)

        except Exception as e:
            print(f"Nav Error: {e}")
            self._fade_waveform_in_after_layout_transition()
        finally:
            if updates_suspended:
                self.main.setUpdatesEnabled(True)
            try:
                if self.main.isVisible() and self.main.windowHandle() is not None:
                    self.main.update()
            except Exception:
                pass

    def _clear_player_transition_effects(self):
        ui_player = getattr(self.main, "ui_player", None)
        if not ui_player:
            return

        widgets = [ui_player, getattr(ui_player, "lbl_art", None)]
        if hasattr(ui_player, "_non_art_transition_widgets"):
            widgets.extend(ui_player._non_art_transition_widgets())

        seen = set()
        for widget in widgets:
            if not widget or id(widget) in seen:
                continue
            seen.add(id(widget))
            try:
                widget.setGraphicsEffect(None)
            except Exception:
                pass

        waveform = getattr(ui_player, "waveform", None)
        is_loading = bool(getattr(getattr(self.main, "playback", None), "is_loading", False))
        waveform_transitioning = bool(getattr(waveform, "layout_transition_fade_active", False))
        if waveform and not is_loading and not waveform_transitioning:
            try:
                waveform.opacity_factor = 1.0
                waveform.update()
            except Exception:
                pass

    def _prepare_waveform_for_layout_transition(self):
        waveform = getattr(getattr(self.main, "ui_player", None), "waveform", None)
        if not waveform:
            return
        try:
            if hasattr(waveform, "prepare_for_layout_transition"):
                waveform.prepare_for_layout_transition()
            else:
                waveform.setUpdatesEnabled(False)
        except Exception:
            pass

    def _fade_waveform_in_after_layout_transition(self):
        waveform = getattr(getattr(self.main, "ui_player", None), "waveform", None)
        if not waveform:
            return
        try:
            if hasattr(waveform, "fade_in_after_layout_transition"):
                waveform.fade_in_after_layout_transition()
            else:
                waveform.setUpdatesEnabled(True)
                waveform.update()
        except Exception:
            pass
