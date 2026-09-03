import os
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QApplication, QLabel, QWidget
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QPoint, QParallelAnimationGroup, QTimer, QCoreApplication
from PyQt6.QtGui import QPixmap, QIcon

from .overlay import TransitionOverlay

class AnimationManager:
    # Durata de referinta a fade-urilor. Restul se deriva din ea, pastrand
    # proportiile alese vizual: la valoarea implicita ies exact duratele
    # dinainte de a exista reglajul.
    DEFAULT_FADE_SPEED_MS = 200

    def __init__(self, main_window):
        self.main = main_window
        self.speed_move = 350
        self.set_fade_speed(self.DEFAULT_FADE_SPEED_MS)
        self._overlays = [] # Păstrăm referințe pentru cleanup
        self._effects_targets = [] # Widget-uri care au primit efecte grafice

    def set_fade_speed(self, ms):
        """ Un singur reglaj pentru fade-urile din aplicatie: schimbarea paginii
        din dreapta (EQ / Playlist / Setari), paginile interne din Playlist si
        aparitia Player-ului la intrarea dintr-o piesa. """
        try:
            ms = int(ms)
        except (TypeError, ValueError):
            ms = self.DEFAULT_FADE_SPEED_MS
        ms = max(60, min(700, ms))

        self.fade_speed_ms = ms
        self.speed_fade_in = ms
        self.speed_fade_out = ms
        self.STACK_FADE_IN_MS = ms
        self.STACK_FADE_OUT_MS = max(40, int(ms * 0.75))
        self.PAGE_SWITCH_MS = max(80, int(ms * 1.2))

    def get_global_rect(self, widget):
        if not widget: return QRect()
        return QRect(widget.mapTo(self.main, QPoint(0, 0)), widget.size())

    def capture_player_state(self, ui_player):
        """ Capturează geometria și imaginile elementelor din player pentru animație """
        state = {}
        if not ui_player: return state

        # 1. Artwork
        state['art_rect'] = self.get_global_rect(ui_player.lbl_art)
        if getattr(ui_player, 'current_artwork_pixmap', None):
            state['pixmap'] = ui_player.current_artwork_pixmap
        elif hasattr(ui_player.lbl_art, 'image_data') and ui_player.lbl_art.image_data:
            state['pixmap'] = QPixmap.fromImage(ui_player.lbl_art.image_data)
        else:
            state['pixmap'] = ui_player.lbl_art.pixmap()

        # 2. Text geometry only. Text pixmaps are captured only when a transition needs them.
        if hasattr(ui_player, 'lbl_title'):
            state['title_rect'] = self.get_global_rect(ui_player.lbl_title)

        if hasattr(ui_player, 'lbl_artist'):
            state['artist_rect'] = self.get_global_rect(ui_player.lbl_artist)
            
        return state

    def _add_anim(self, group, target, prop, start, end, duration, curve=QEasingCurve.Type.Linear):
        anim = QPropertyAnimation(target, prop)
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(curve)
        group.addAnimation(anim)

    def _create_overlay_anim(self, group, pixmap, start_rect, end_rect, start_radius, end_radius, render_mode,
                             border_width=0.0, border_color=None, shape_mode="rounded_rect"):
        if not pixmap or not start_rect or not end_rect: return
        
        overlay = TransitionOverlay(self.main)
        overlay.setPixmap(pixmap)
        overlay.setScaledContents(True)
        overlay.setGeometry(start_rect)
        overlay.radius = start_radius
        overlay.render_mode = render_mode
        overlay.shape_mode = shape_mode
        if border_color is not None:
            overlay.border_color = border_color
        overlay.border_width = border_width
        overlay.raise_() # 🔥 Asigurăm că overlay-ul e peste tot
        overlay.show()
        self._overlays.append(overlay)

        self._add_anim(group, overlay, b"geometry", start_rect, end_rect, self.speed_move)
        if start_radius != end_radius:
            self._add_anim(group, overlay, b"radius", start_radius, end_radius, self.speed_move)
        return overlay

    def _add_fade_anim(self, group, target, start, end, duration):
        if not target: return
        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)
        self._effects_targets.append(target)
        self._add_anim(group, effect, b"opacity", start, end, duration)

    def _cleanup(self):
        # Restaurăm vizibilitatea elementelor reale
        # Eliminăm efectele de opacitate (setate în NavController sau aici)
        fade_non_art = getattr(self, '_fade_non_art_after_cleanup', False)
        self._fade_non_art_after_cleanup = False
        try:
            self.main.ui_player.setGraphicsEffect(None)
        except Exception:
            pass
        try:
            self.main.ui_player.lbl_art.setGraphicsEffect(None)
        except Exception:
            pass
        if hasattr(self.main.ui_player, 'lbl_title'):
            try:
                self.main.ui_player.lbl_title.setGraphicsEffect(None)
            except Exception:
                pass
        if hasattr(self.main.ui_player, 'lbl_artist'):
            try:
                self.main.ui_player.lbl_artist.setGraphicsEffect(None)
            except Exception:
                pass
        
        try:
            self.main.ui_player.lbl_art.setHidden(False) # Just in case
        except Exception:
            pass

        # Ștergem efectele înainte să distrugem eventualele overlay-uri care le dețin.
        for target in self._effects_targets:
            try:
                if target:
                    target.setGraphicsEffect(None)
            except Exception:
                pass
        self._effects_targets.clear()
        
        # Ștergem overlay-urile
        for ov in self._overlays:
            try:
                ov.hide()
                ov.deleteLater()
            except Exception:
                pass
        self._overlays.clear()

        # Pre-setăm artwork-ul nou pe lbl_art înainte de a-l face vizibil (evită flash-ul cu arta veche)
        pending_pix = getattr(self, '_pending_art_pixmap', None)
        if pending_pix and not pending_pix.isNull() and hasattr(self.main.ui_player, 'lbl_art'):
            try:
                self.main.ui_player.lbl_art.set_art(pending_pix.toImage())
            except Exception:
                pass
        self._pending_art_pixmap = None
        
        # Ștergem snapshot-ul de fade out dacă există
        if hasattr(self.main, 'snapshot_overlay'):
            try:
                self.main.snapshot_overlay.hide()
                self.main.snapshot_overlay.deleteLater()
                del self.main.snapshot_overlay
            except Exception:
                pass
            
        # 🔥 FIX FINAL: Forțăm un refresh de layout pe Player pentru a repara orice "squeeze"
        skip_layout_refresh = getattr(self, '_skip_cleanup_layout_refresh', False)
        self._skip_cleanup_layout_refresh = False
        if not skip_layout_refresh and hasattr(self.main.ui_player, '_force_layout_refresh'):
            # Aplicăm MEREU (și pe FULL) pentru a garanta starea corectă (Fix Double Click)
            self.main.ui_player._force_layout_refresh()
        if fade_non_art and hasattr(self.main.ui_player, 'fade_non_art_controls_in'):
            self.main.ui_player.fade_non_art_controls_in()

    def _cleanup_hierarchy(self):
        # Cleanup specific pentru animațiile de ierarhie (Folder -> Header)
        for target in self._effects_targets:
            try:
                if target:
                    target.setGraphicsEffect(None)
            except Exception:
                pass
        self._effects_targets.clear()

        for ov in self._overlays:
            try:
                ov.hide()
                ov.deleteLater()
            except Exception:
                pass
        self._overlays.clear()
        
    def _stop_previous_animation(self):
        """ Oprește forțat animația curentă și curăță resursele înainte de a începe una nouă """
        if hasattr(self.main, 'anim_group') and self.main.anim_group:
            if self.main.anim_group.state() == QPropertyAnimation.State.Running:
                self.main.anim_group.stop()
            
            # Deconectăm semnalele pentru a evita apeluri duble sau eronate la _cleanup
            try: self.main.anim_group.finished.disconnect()
            except: pass
            
            self.main.anim_group = None
            
        # Curățăm overlay-urile rămase de la animația întreruptă
        self._cleanup()

    def animate_player_artwork_resize(self, rebuild_fn):
        """ Artwork-ul isi schimba animat marimea cand Player-ul trece intre
        Full si Mini (se micsoreaza sau se mareste, dupa caz).

        Deliberat izolata: nu foloseste self.main.anim_group, _cleanup(),
        _create_overlay_anim() sau listele comune (_overlays/_effects_targets),
        ca sa nu poata interfera cu animate_transition_to_player sau
        animate_stack_switch, care ruleaza in acelasi timp.
        """
        ui_player = self.main.ui_player
        lbl_art = getattr(ui_player, 'lbl_art', None)

        # Daca se apasa rapid de mai multe ori, o animatie anterioara neterminata
        # nu trebuie sa lase artwork-ul blocat invizibil (setVisible(False) fara
        # sa mai apuce sa ruleze done()).
        prev_anim = getattr(self, '_artwork_resize_anim', None)
        if prev_anim:
            if prev_anim.state() == QPropertyAnimation.State.Running:
                prev_anim.stop()
            self._artwork_resize_anim = None

        # stop() NU emite 'finished' in Qt, deci done() nu a rulat si overlay-ul
        # animatiei intrerupte a ramas pe ecran. Fara asta, la comutari rapide se
        # adunau mai multe artwork-uri suprapuse, blocate. Il preluam si continuam
        # animatia din locul in care a ramas.
        carried_overlay = getattr(self, '_artwork_resize_overlay', None)
        try:
            if carried_overlay is not None and not carried_overlay.isVisible():
                carried_overlay = None
        except RuntimeError: # obiectul C++ a fost deja distrus
            carried_overlay = None
        if carried_overlay is None:
            self._artwork_resize_overlay = None

        # Artwork-ul real ramane ascuns cat timp overlay-ul preluat il acopera.
        if lbl_art and carried_overlay is None:
            lbl_art.setVisible(True)

        # Cand preluam un overlay intrerupt, pornim din locul in care a ramas,
        # nu de la pozitia din layout - altfel artwork-ul ar sari vizibil.
        if carried_overlay is not None:
            start_rect = QRect(carried_overlay.geometry())
        else:
            start_rect = self.get_global_rect(lbl_art) if lbl_art else None
        pixmap = None
        if lbl_art:
            if getattr(lbl_art, 'image_data', None):
                pixmap = QPixmap.fromImage(lbl_art.image_data)
            else:
                pixmap = lbl_art.pixmap()

        # Fara imagine/geometrie valida nu avem ce anima - schimbam tabul normal.
        if not start_rect or not pixmap or pixmap.isNull():
            if carried_overlay is not None:
                self._artwork_resize_overlay = None
                try:
                    carried_overlay.hide()
                    carried_overlay.deleteLater()
                except Exception:
                    pass
                if lbl_art:
                    lbl_art.setVisible(True)
            rebuild_fn()
            return

        entering_full = (ui_player.current_mode == "MINI")

        # Ascundem artwork-ul real INAINTE de rebuild, ca sa nu apuce sa se
        # vada la marimea finala inainte de vreme. Folosim setVisible(False)
        # (nu un QGraphicsOpacityEffect) - efectul de opacitate nu supravietuia
        # reparent-arii facute de rebuild_fn() (Qt il reseteaza), asa ca
        # artwork-ul real redevenea vizibil la locul lui in timpul animatiei.
        # setVisible(False) e o ascundere reala, nu doar vizuala, si nu poate
        # fi anulata de reparent-are.
        lbl_art.setVisible(False)

        rebuild_fn()

        art_c = getattr(ui_player, 'artwork_container', None)

        # La intrarea in Full, set_mode_full() nu primeste nicio latime tinta
        # explicita (spre deosebire de Mini, unde _apply_tab_change() calculeaza
        # si fixeaza deja inaltimea corecta) - fortam layout-ul sa se aseze
        # inainte de masuratoare, altfel citim inca latimea veche (mica) si
        # animatia nu are unde sa se duca (start_rect == end_rect). La iesirea
        # din Full NU atingem inaltimea - e deja corecta, orice recalculare aici
        # ar suprascrie-o cu o valoare intermediara, gresita.
        if entering_full:
            if ui_player.layout():
                ui_player.layout().activate()
            if art_c:
                cw = art_c.width()
                if cw > 0 and art_c.height() != cw:
                    art_c.setFixedHeight(cw)
                if art_c.layout():
                    art_c.layout().activate()
            QCoreApplication.sendPostedEvents(None, 0)

        if art_c and art_c.width() > 0:
            end_rect = self.get_global_rect(art_c)
        else:
            end_rect = self.get_global_rect(lbl_art)
            end_rect.setHeight(end_rect.width())

        # Refolosim overlay-ul preluat de la o animatie intrerupta, ca sa ramana
        # unul singur pe ecran oricat de repede s-ar comuta.
        overlay = carried_overlay
        if overlay is None:
            overlay = TransitionOverlay(self.main)
            overlay.setScaledContents(True)
            overlay.radius = 20.0
            overlay.render_mode = "cover"
        overlay.setPixmap(pixmap)
        overlay.setGeometry(start_rect)
        overlay.raise_() # aceeasi ordine ca la animate_transition_to_player (functionala)
        overlay.show()
        self._artwork_resize_overlay = overlay

        group = QParallelAnimationGroup()
        self._add_anim(group, overlay, b"geometry", start_rect, end_rect, self.speed_move)

        def done():
            if getattr(self, '_artwork_resize_overlay', None) is overlay:
                self._artwork_resize_overlay = None
            try:
                overlay.hide()
                overlay.deleteLater()
            except Exception:
                pass
            try:
                lbl_art.setVisible(True)
            except Exception:
                pass
            self._artwork_resize_anim = None

        group.finished.connect(done)
        self._artwork_resize_anim = group # pastram referinta ca sa nu fie colectata
        group.start()

    def animate_transition_to_player(self, filepath=None):
        self._stop_previous_animation() # 🔥 STOP & CLEANUP
        start_rect, start_radius, pixmap = None, 10.0, None
        start_rect_t, start_rect_a = None, None

        # 1. Găsim sursa — folosim datele pre-capturate din click handler (O(1))
        pending = getattr(self.main.ui_playlist, '_pending_anim_source', None)
        if pending:
            start_rect = pending['rect']
            pixmap = pending['pixmap']
            start_radius = pending.get('radius', 12.0)
            self.main.ui_playlist._pending_anim_source = None
        
        if not start_rect and self.main.ui_player.isVisible():
            start_rect = self.get_global_rect(self.main.ui_player.lbl_art)
            if hasattr(self.main.ui_player, 'lbl_title'): start_rect_t = self.get_global_rect(self.main.ui_player.lbl_title)
            if hasattr(self.main.ui_player, 'lbl_artist'): start_rect_a = self.get_global_rect(self.main.ui_player.lbl_artist)
            
            if hasattr(self.main.ui_player.lbl_art, 'image_data') and self.main.ui_player.lbl_art.image_data:
                pixmap = QPixmap.fromImage(self.main.ui_player.lbl_art.image_data)
            else:
                pixmap = self.main.ui_player.lbl_art.pixmap()
            start_radius = 20.0

        if not start_rect or not pixmap:
            self.main.navbar.buttons[0].setChecked(True)
            self.main.on_tab_changed(0)
            return

        # 2. Switch Tab & Layout Update
        self.main.navbar.buttons[0].setChecked(True)
        self.main.on_tab_changed(0)
        self.main.ui_player.layout().activate()
        self.main.ui_player.adjustSize()
        QCoreApplication.sendPostedEvents(None, 0)
        # Forțăm SquareFrame să-și stabilizeze înălțimea (h = w) înainte de măsurători
        art_c = getattr(self.main.ui_player, 'artwork_container', None)
        if art_c:
            cw = art_c.width()
            if cw > 0 and art_c.height() != cw:
                art_c.setFixedHeight(cw)
            art_c.layout().activate() if art_c.layout() else None
        QCoreApplication.sendPostedEvents(None, 0)

        # 3. Setup Destinații — folosim artwork_container (SquareFrame stabilizat) pentru precizie
        if art_c and art_c.width() > 0:
            end_rect = self.get_global_rect(art_c)
        else:
            end_rect = self.get_global_rect(self.main.ui_player.lbl_art)
            end_rect.setHeight(end_rect.width()) # Force square
        
        end_rect_t = self.get_global_rect(self.main.ui_player.lbl_title) if hasattr(self.main.ui_player, 'lbl_title') else None
        end_rect_a = self.get_global_rect(self.main.ui_player.lbl_artist) if hasattr(self.main.ui_player, 'lbl_artist') else None


        # 5. Construim Animațiile
        self.main.anim_group = QParallelAnimationGroup()
        self._pending_art_pixmap = pixmap  # Păstrăm pentru _cleanup
        
        self._create_overlay_anim(self.main.anim_group, pixmap, start_rect, end_rect, start_radius, 20.0, "cover")
        
        if end_rect_t:
            pix_t = self.main.ui_player.lbl_title.grab()
            self._create_overlay_anim(self.main.anim_group, pix_t, start_rect_t or end_rect_t, end_rect_t, 0, 0, "stretch")
            
        if end_rect_a:
            pix_a = self.main.ui_player.lbl_artist.grab()
            self._create_overlay_anim(self.main.anim_group, pix_a, start_rect_a or end_rect_a, end_rect_a, 0, 0, "stretch")

        if hasattr(self.main.ui_player, 'player_container'):
            self._add_fade_anim(self.main.anim_group, self.main.ui_player, 0.0, 1.0, self.speed_fade_in)

        self.main.anim_group.finished.connect(self._cleanup)
        self.main.anim_group.start()

    def execute_exit_player_animation(self, start_rect, pixmap, existing_art_overlay=None):
        self._stop_previous_animation() # 🔥 STOP & CLEANUP
        art_effect = QGraphicsOpacityEffect(self.main.ui_player.lbl_art)
        art_effect.setOpacity(0.0)
        self.main.ui_player.lbl_art.setGraphicsEffect(art_effect)
        # 🔥 FIX: Forțăm layout-ul să fie gata înainte de a calcula destinația
        # Nu folosim adjustSize() pentru că strică constrângerile din Splitter
        if self.main.ui_player.layout():
            self.main.ui_player.layout().activate()
        
        # Forțăm și containerul părinte
        if self.main.content_area.layout():
            self.main.content_area.layout().activate()

        end_rect = self.get_global_rect(self.main.ui_player.lbl_art)
        # 🔥 FIX SQUEEZE: Forțăm destinația să fie pătrată (bazat pe lățime)
        # În modul Mini, lățimea este fixă/calculată corect, dar înălțimea poate varia eronat.
        end_rect.setHeight(end_rect.width())
        

        self.main.anim_group = QParallelAnimationGroup()


        # Overlays
        if existing_art_overlay:
            existing_art_overlay.raise_()
            self._overlays.append(existing_art_overlay)
            self._add_anim(self.main.anim_group, existing_art_overlay, b"geometry", existing_art_overlay.geometry(), end_rect, self.speed_move)
            if getattr(existing_art_overlay, "radius", 20.0) != 20.0:
                self._add_anim(self.main.anim_group, existing_art_overlay, b"radius", existing_art_overlay.radius, 20.0, self.speed_move)
        else:
            self._create_overlay_anim(self.main.anim_group, pixmap, start_rect, end_rect, 20.0, 20.0, "cover")
        # 🔥 ADD FADE IN (Matches Enter Animation)
        self._skip_cleanup_layout_refresh = True
        self._fade_non_art_after_cleanup = True
        self.main.anim_group.finished.connect(self._cleanup)
        self.main.anim_group.start()

    def execute_enter_player_animation(self, start_rect, pixmap, existing_art_overlay=None):
        self._stop_previous_animation() # 🔥 STOP & CLEANUP
        art_effect = QGraphicsOpacityEffect(self.main.ui_player.lbl_art)
        art_effect.setOpacity(0.0)
        self.main.ui_player.lbl_art.setGraphicsEffect(art_effect)
        # 🔥 FIX: Forțăm layout-ul să fie gata înainte de a calcula destinația
        # Astfel ne asigurăm că end_rect corespunde cu starea "Good" de după refresh.
        if self.main.content_area.layout():
            self.main.content_area.layout().activate()
            self.main.content_area.layout().update()
            
        # No event pump here: NavigationController starts this while window updates are paused.

        end_rect = self.get_global_rect(self.main.ui_player.lbl_art)
        end_rect.setHeight(end_rect.width()) # Force square for Full Player
        
        self.main.anim_group = QParallelAnimationGroup()

        if existing_art_overlay:
            existing_art_overlay.raise_()
            self._overlays.append(existing_art_overlay)
            self._add_anim(self.main.anim_group, existing_art_overlay, b"geometry", existing_art_overlay.geometry(), end_rect, self.speed_move)
            if getattr(existing_art_overlay, "radius", 20.0) != 20.0:
                self._add_anim(self.main.anim_group, existing_art_overlay, b"radius", existing_art_overlay.radius, 20.0, self.speed_move)
        else:
            self._create_overlay_anim(self.main.anim_group, pixmap, start_rect, end_rect, 20.0, 20.0, "cover")

        self._fade_non_art_after_cleanup = True
        self.main.anim_group.finished.connect(self._cleanup)
        self.main.anim_group.start()

    def animate_stack_switch(self, stack, old_widget, new_widget):
        """ Animație Fade Out -> Switch -> Fade In pentru tab-uri """
        self._stop_previous_animation() # 🔥 STOP & CLEANUP
        if not old_widget or not new_widget: return
        
        # 1. Fade Out Old
        self.main.anim_group = QParallelAnimationGroup()
        self._add_fade_anim(self.main.anim_group, old_widget, 1.0, 0.0, self.STACK_FADE_OUT_MS)
        
        def after_fade_out():
            # 🔥 FIX: Pre-ascundem noul widget ÎNAINTE de switch pentru a preveni
            # flash-ul vizual cauzat de recalcularea layout-ului în showEvent.
            enter_eff = QGraphicsOpacityEffect(new_widget)
            enter_eff.setOpacity(0.0)
            new_widget.setGraphicsEffect(enter_eff)
            self._effects_targets.append(new_widget)

            # 2. Switch Page (showEvent se declanșează aici, dar widget-ul e invizibil)
            stack.setCurrentWidget(new_widget)
            old_widget.setGraphicsEffect(None) # Cleanup old

            if hasattr(new_widget, 'prepare_for_show'):
                new_widget.prepare_for_show()
            
            # 3. Fade In New (reutilizăm efectul pre-aplicat)
            self.main.anim_group = QParallelAnimationGroup()
            self._add_anim(self.main.anim_group, enter_eff, b"opacity", 0.0, 1.0, self.STACK_FADE_IN_MS)
            
            def after_fade_in():
                new_widget.setGraphicsEffect(None) # Cleanup new
                # Deferred scroll restore after graphics effect cleanup settles
                if hasattr(new_widget, '_deferred_scroll_restore'):
                    saved = getattr(new_widget, '_scroll_on_hide', 0)
                    QTimer.singleShot(0, lambda: new_widget._deferred_scroll_restore(saved))
                
            self.main.anim_group.finished.connect(after_fade_in)
            self.main.anim_group.start()
            
        self.main.anim_group.finished.connect(after_fade_out)
        self.main.anim_group.start()
