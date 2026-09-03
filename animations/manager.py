import os
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QApplication, QLabel, QWidget
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QPoint, QParallelAnimationGroup, QTimer, QCoreApplication
from PyQt6.QtGui import QPixmap, QIcon

from .overlay import TransitionOverlay

class AnimationManager:
    # Durata de referinta a fade-urilor. Toate celelalte se deriva din ea,
    # pastrand proportiile cu care a fost reglata aplicatia: la valoarea
    # implicita ies exact duratele dinainte de a exista reglajul.
    DEFAULT_FADE_SPEED_MS = 200

    def __init__(self, main_window):
        self.main = main_window
        self.speed_move = 350
        self.set_fade_speed(self.DEFAULT_FADE_SPEED_MS)
        self._overlays = [] # Păstrăm referințe pentru cleanup
        self._effects_targets = [] # Widget-uri care au primit efecte grafice

    def set_fade_speed(self, ms):
        """ Un singur reglaj pentru toate fade-urile din aplicatie. Restul
        duratelor se deriva din el, ca raporturile dintre ele sa ramana cele
        alese vizual (fade out-ul e mai scurt decat fade in-ul etc.). """
        try:
            ms = int(ms)
        except (TypeError, ValueError):
            ms = self.DEFAULT_FADE_SPEED_MS
        ms = max(60, min(700, ms))

        self.fade_speed_ms = ms
        self.speed_fade_in = ms
        self.speed_fade_out = ms
        # Continutul Player-ului la trecerea Full <-> Mini.
        self.NON_ART_FADE_IN_MS = ms
        self.NON_ART_FADE_OUT_MS = max(40, int(ms * 0.65))
        # Schimbarea paginii din dreapta (EQ / Playlist / Setari).
        self.STACK_FADE_IN_MS = ms
        self.STACK_FADE_OUT_MS = max(40, int(ms * 0.75))
        # Fade-ul intre paginile din Playlist (dashboard <-> sectiuni).
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
        Full si Mini (se micsoreaza sau se mareste, dupa caz), iar restul
        continutului (titlu, artist, waveform, butoane) face fade out inainte
        de schimbare si fade in in timp ce artwork-ul aluneca.

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
        # animatiei intrerupte e inca pe ecran. Daca l-am abandona, la comutari
        # rapide s-ar aduna mai multe artwork-uri suprapuse. Il preluam si
        # continuam animatia din locul in care a ramas.
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

        # Token de generatie: fade in-ul continutului e programat pe timer, deci
        # un click urmator trebuie sa-l poata invalida pe cel in asteptare.
        token = getattr(self, '_artwork_resize_token', 0) + 1
        self._artwork_resize_token = token

        # rebuild_fn reintra in on_tab_changed, care se uita la acest flag ca sa
        # nu porneasca inca o animatie.
        def guarded_rebuild():
            self._in_artwork_resize = True
            try:
                rebuild_fn()
            finally:
                self._in_artwork_resize = False

        # Cand preluam un overlay intrerupt, pornim de unde a ramas el, nu de la
        # pozitia din layout - altfel artwork-ul ar sari vizibil.
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
            guarded_rebuild()
            return

        entering_full = (ui_player.current_mode == "MINI")
        target_mode = "FULL" if entering_full else "MINI"

        # animate_transition_to_player isi face singura fade-ul continutului si
        # se bazeaza pe faptul ca on_tab_changed(0) termina rebuild-ul inainte de
        # a-i masura destinatiile - acolo rulam sincron, fara fade.
        do_fade = not getattr(self, '_suppress_artwork_resize_fade', False)

        # Destinatiile artwork-ului sunt stabile cat timp fereastra nu isi schimba
        # marimea, deci le tinem minte de la o tranzitie la alta. Cu destinatia
        # stiuta dinainte, animatia poate porni odata cu fade out-ul, fara sa
        # asteptam rebuild-ul. Cheia include marimea ferestrei, deci un resize
        # invalideaza automat valorile vechi.
        cache = getattr(self, '_art_dest_cache', None)
        if cache is None:
            cache = self._art_dest_cache = {}
        dest_key = (target_mode, self.main.width(), self.main.height())
        predicted_end = cache.get(dest_key)

        # Rebuild-ul are voie sa ruleze o singura data, indiferent daca il cheama
        # semnalul de final al fade out-ului sau plasa de siguranta de pe timer.
        state = {'ran': False}

        def ensure_overlay(at_rect):
            """ Overlay-ul care tine locul artwork-ului real pe durata animatiei.
            Il refolosim pe cel preluat de la o animatie intrerupta, ca sa ramana
            unul singur pe ecran oricat de repede s-ar comuta. """
            ov = getattr(self, '_artwork_resize_overlay', None)
            if ov is None:
                ov = TransitionOverlay(self.main)
                ov.setScaledContents(True)
                ov.radius = 20.0
                ov.render_mode = "cover"
                ov.setGeometry(at_rect)
            ov.setPixmap(pixmap)
            ov.raise_() # aceeasi ordine ca la animate_transition_to_player (functionala)
            ov.show()
            self._artwork_resize_overlay = ov
            return ov

        def start_move(overlay, from_rect, to_rect, duration):
            group = QParallelAnimationGroup()
            self._add_anim(group, overlay, b"geometry", from_rect, to_rect, duration)

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


            return group

        def apply_rebuild():
            """ Schimba layout-ul si masoara destinatia reala a artwork-ului. """
            # Ascundem artwork-ul real INAINTE de rebuild, ca sa nu apuce sa se
            # vada la marimea finala inainte de vreme. Folosim setVisible(False)
            # (nu un QGraphicsOpacityEffect) - efectul de opacitate nu supravietuia
            # reparent-arii facute de rebuild_fn() (Qt il reseteaza).
            lbl_art.setVisible(False)

            guarded_rebuild()

            # Rebuild-ul trece prin animate_stack_switch -> _stop_previous_animation()
            # -> _cleanup(), care face lbl_art.setHidden(False). Fara re-ascundere
            # s-ar vedea doua artwork-uri in timpul animatiei.
            lbl_art.setVisible(False)

            # Rebuild-ul reconstruieste layout-ul si sterge efectele grafice
            # (_clear_player_transition_effects), deci punem opacitatea 0 la loc
            # abia acum, pe widget-urile noi, ca sa avem de unde face fade in.
            if do_fade and hasattr(ui_player, 'set_non_art_controls_opacity'):
                try:
                    ui_player.set_non_art_controls_opacity(0.0)
                except Exception:
                    pass

            art_c = getattr(ui_player, 'artwork_container', None)

            # La intrarea in Full, set_mode_full() nu primeste nicio latime tinta
            # explicita (spre deosebire de Mini, unde _apply_tab_change() calculeaza
            # si fixeaza deja inaltimea corecta) - fortam layout-ul sa se aseze
            # inainte de masuratoare. La iesirea din Full NU atingem inaltimea -
            # e deja corecta, orice recalculare aici ar suprascrie-o gresit.
            if entering_full:
                if ui_player.layout():
                    ui_player.layout().activate()
                if art_c:
                    cw = art_c.width()
                    if cw > 0 and art_c.height() != cw:
                        art_c.setFixedHeight(cw)
                    if art_c.layout():
                        art_c.layout().activate()

            # Overlay-ul trebuie sa existe inaintea oricarei redesenari: artwork-ul
            # real e ascuns, deci un cadru desenat fara overlay ar arata un gol.
            ensure_overlay(start_rect)

            # Golim coada de evenimente in AMBELE sensuri, altfel fereastra poate
            # ramane nedesenata pana la urmatorul eveniment de mouse.
            QCoreApplication.sendPostedEvents(None, 0)

            # on_tab_changed suspenda desenarea waveform-ului si o reactiveaza abia
            # 120ms mai tarziu. Un widget vizibil cu setUpdatesEnabled(False) inghite
            # cererea de repaint a ferestrei, iar animatia ar rula fara sa se vada
            # nimic. Ramane invizibil oricum, opacity_factor e inca 0.
            waveform = getattr(ui_player, 'waveform', None)
            if waveform is not None:
                try:
                    if hasattr(waveform, 'suspend_visual_updates'):
                        waveform.suspend_visual_updates(False)
                    else:
                        waveform.setUpdatesEnabled(True)
                except Exception:
                    pass

            # Aici era un self.main.repaint() sincron, pus cand credeam ca fereastra
            # ramane blocata dupa fade out. Cauza reala era waveform-ul lasat cu
            # setUpdatesEnabled(False), reparat la sursa. Repaint-ul sincron forta
            # o desenare exact cand se creau/distrugeau efecte grafice, ceea ce
            # ducea la pictori Qt imbricati ("A paint device can only be painted by
            # one painter at a time") si, dupa destule tranzitii, la access violation.
            self.main.update()

            if art_c and art_c.width() > 0:
                measured = self.get_global_rect(art_c)
            else:
                measured = self.get_global_rect(lbl_art)
                measured.setHeight(measured.width())

            # Retinem destinatia reala pentru tranzitiile urmatoare.
            cache[(ui_player.current_mode, self.main.width(), self.main.height())] = QRect(measured)
            return measured

        def rects_differ(a, b):
            return (abs(a.x() - b.x()) > 2 or abs(a.y() - b.y()) > 2
                    or abs(a.width() - b.width()) > 2 or abs(a.height() - b.height()) > 2)

        def fade_in_controls():
            # Daca intre timp a pornit alta tranzitie, ea decide cand reapare.
            if getattr(self, '_artwork_resize_token', 0) != token:
                return
            # Nu are rost sa reapara continutul vechi: asteptam rebuild-ul.
            if not state['ran']:
                QTimer.singleShot(40, fade_in_controls)
                return
            if hasattr(ui_player, 'fade_non_art_controls_in'):
                ui_player.fade_non_art_controls_in(
                    delay_ms=0,
                    duration_ms=self.NON_ART_FADE_IN_MS,
                )

        def rebuild_after_fade():
            """ Cale simultana: animatia deja ruleaza, aici doar schimbam layout-ul
            si corectam destinatia daca cea memorata nu mai e valabila. """
            if getattr(self, '_artwork_resize_token', 0) != token:
                return
            if state['ran']:
                return
            state['ran'] = True

            running = getattr(self, '_artwork_resize_anim', None)
            elapsed = running.currentTime() if running else 0

            real_end = apply_rebuild()

            overlay = getattr(self, '_artwork_resize_overlay', None)
            if overlay is None:
                return
            if predicted_end is None or rects_differ(real_end, predicted_end):
                # Destinatia memorata nu mai e valabila - continuam din pozitia
                # curenta spre cea reala, cu timpul ramas.
                if running and running.state() == QPropertyAnimation.State.Running:
                    running.stop()
                remaining = max(90, self.speed_move - elapsed)
                start_move(overlay, QRect(overlay.geometry()), real_end, remaining)
            self.main.update()

        def rebuild_then_move():
            """ Cale secventiala (prima tranzitie, dupa un resize, sau fara fade):
            intai rebuild, apoi animatia, pentru ca destinatia nu e cunoscuta. """
            if getattr(self, '_artwork_resize_token', 0) != token:
                return
            if state['ran']:
                return
            state['ran'] = True

            end_rect = apply_rebuild()
            overlay = getattr(self, '_artwork_resize_overlay', None)
            if overlay is None:
                return
            start_move(overlay, start_rect, end_rect, self.speed_move)
            self.main.update()
            if do_fade:
                QTimer.singleShot(int(self.speed_move * 0.45), fade_in_controls)

        has_fade_api = hasattr(ui_player, 'fade_non_art_controls_out')

        if do_fade and has_fade_api and predicted_end is not None:
            # Artwork-ul pleaca ACUM spre destinatia memorata, in paralel cu fade
            # out-ul continutului real. Layout-ul vechi e inca pe ecran pana la
            # rebuild, deci continutul vechi nu se suprapune peste tabul nou.
            lbl_art.setVisible(False)
            moving_overlay = ensure_overlay(start_rect)
            start_move(moving_overlay, start_rect, QRect(predicted_end), self.speed_move)
            ui_player.fade_non_art_controls_out(
                on_finished=rebuild_after_fade,
                duration_ms=self.NON_ART_FADE_OUT_MS,
            )
            # Plasa de siguranta: stop() nu emite 'finished' in Qt, deci daca cineva
            # opreste grupul de fade out, rebuild-ul nu ar mai porni niciodata.
            QTimer.singleShot(self.NON_ART_FADE_OUT_MS + 80, rebuild_after_fade)
            QTimer.singleShot(int(self.speed_move * 0.45), fade_in_controls)
        elif do_fade and has_fade_api:
            ui_player.fade_non_art_controls_out(
                on_finished=rebuild_then_move,
                duration_ms=self.NON_ART_FADE_OUT_MS,
            )
            QTimer.singleShot(self.NON_ART_FADE_OUT_MS + 80, rebuild_then_move)
        else:
            rebuild_then_move()

    def _switch_to_player_tab_sync(self):
        """ on_tab_changed(0) fara fade-ul de continut, ca rebuild-ul de layout
        sa se termine inainte de a returna (animatia de aici masoara imediat
        dupa destinatiile din player). """
        self._suppress_artwork_resize_fade = True
        try:
            self.main.on_tab_changed(0)
        finally:
            self._suppress_artwork_resize_fade = False

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
            self._switch_to_player_tab_sync()
            return

        # 2. Switch Tab & Layout Update
        self.main.navbar.buttons[0].setChecked(True)
        self._switch_to_player_tab_sync()
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

    def fade_in_stack_widget(self, widget, duration_ms=None):
        """ Fade in pentru continutul tabului care reapare la iesirea din Player
        Full. animate_stack_switch nu acopera cazul asta: el ruleaza doar cand se
        schimba pagina, iar la intoarcerea pe acelasi tab pagina ramane aceeasi,
        deci continutul aparea instant. """
        if not widget:
            return
        if duration_ms is None:
            duration_ms = self.STACK_FADE_IN_MS

        # O animatie anterioara intrerupta ar lasa widget-ul semi-transparent:
        # stop() nu emite 'finished', deci curatam efectul explicit.
        prev = getattr(self, '_stack_fade_anim', None)
        prev_target = getattr(self, '_stack_fade_target', None)
        if prev is not None and prev.state() == QPropertyAnimation.State.Running:
            prev.stop()
        if prev_target is not None:
            try:
                prev_target.setGraphicsEffect(None)
            except Exception:
                pass

        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(duration_ms)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        def done():
            try:
                widget.setGraphicsEffect(None)
            except Exception:
                pass
            if getattr(self, '_stack_fade_anim', None) is anim:
                self._stack_fade_anim = None
                self._stack_fade_target = None

        anim.finished.connect(done)
        self._stack_fade_anim = anim
        self._stack_fade_target = widget
        anim.start()

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
