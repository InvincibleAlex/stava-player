from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect, QWidget
from PyQt6.QtCore import Qt, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QRect, QTimer
from PyQt6.QtGui import QPixmap
from background.background_generator import BackgroundGenerator
import core.themes as themes

class BackgroundManager:
    def __init__(self, main_window):
        self.main = main_window
        self.current_track_pixmap = None
        self.playlist_context_pixmap = None
        self._no_pending_playlist_pixmap = object()
        self._pending_playlist_context_pixmap = self._no_pending_playlist_pixmap
        self._playlist_update_delay_ms = 120
        self._playlist_update_timer = QTimer()
        self._playlist_update_timer.setSingleShot(True)
        self._playlist_update_timer.timeout.connect(self._apply_pending_playlist_pixmap)
        
        # 🔥 OPTIMIZARE: Debounce timer evită re-render multiplu la schimbări rapide
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(50)  # 50ms debounce
        self._debounce_timer.timeout.connect(self._do_update_background)
        
        # --- BACKGROUND CONTAINER & LABEL ---
        # Folosim un container pentru a tăia marginile (clip) când facem zoom
        self.container = QWidget(self.main)
        self.container.setGeometry(self.main.rect())
        self.container.lower()
        self.container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        self.bg_label = QLabel(self.container)
        self.bg_label.setGeometry(self.container.rect())
        self.bg_label.setStyleSheet("background-color: #121212;") 
        self.bg_label.setScaledContents(True) # Asigură că imaginea umple tot spațiul
        self.bg_label.show()  # Ne asigurăm că e vizibil
        
        self.anim_group = None
        self.transition_overlay = None

    def update_background(self):
        """ Debounced: Programează o actualizare de fundal după 50ms de liniște """
        self._debounce_timer.start()

    def _do_update_background(self):
        """ Calculează și aplică gradientul de fundal pe Main Window cu tranziție """
        
        # 1. Verificăm tema curentă
        # Doar tema 'Default' folosește poza de fundal. Restul folosesc culoare statică.
        current_theme = getattr(self.main, 'last_used_theme', 'Dark')
        
        if current_theme != "Default":
            colors = themes.THEME_PALETTES.get(current_theme, themes.THEME_PALETTES["Default"])
            bg_color = colors.get("BACKGROUND", "#121212")
            # Aplicăm tranziția către culoarea solidă (fără pixmap)
            self._animate_transition(None, fallback_color=bg_color)
            return

        # Logică selecție sursă (Playlist vs Track)
        # Prioritate: 1. Folder/Playlist (dacă suntem în tab-ul 2) -> 2. Piesa Curentă
        target_pixmap = self.current_track_pixmap # Default fallback
        
        if self.main.navbar.currentIndex() == 2 and self.playlist_context_pixmap:
            target_pixmap = self.playlist_context_pixmap

        # Folosim Generatorul pentru a obține QPixmap-ul procesat
        new_pixmap = BackgroundGenerator.get_background_pixmap(target_pixmap, self.main.size())

        # 4. Executăm tranziția
        self._animate_transition(new_pixmap)

    def _animate_transition(self, new_pixmap, fallback_color="#121212"):
        # 🔥 STOP: Oprim animația anterioară dacă rulează
        if self.anim_group and self.anim_group.state() == QPropertyAnimation.State.Running:
            self.anim_group.stop()
            try: self.anim_group.finished.disconnect()
            except: pass
            # Nu ștergem anim_group aici, îl suprascriem mai jos, dar ne asigurăm că nu mai apelează _cleanup_overlay

        # A. Creăm overlay cu vechiul stil (dacă există)
        self._cleanup_overlay()
        
        self.transition_overlay = QLabel(self.container)
        # Copiem geometria vizuală curentă a bg_label (care poate fi zoom-uită)
        self.transition_overlay.setGeometry(self.bg_label.geometry())
        self.transition_overlay.setScaledContents(True)
        
        # Copiem starea curentă a bg_label în overlay
        if self.bg_label.pixmap() and not self.bg_label.pixmap().isNull():
            self.transition_overlay.setPixmap(self.bg_label.pixmap())
        else:
            self.transition_overlay.setStyleSheet(self.bg_label.styleSheet())

        self.transition_overlay.show()
        self.transition_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # Ordinea Z: Overlay sub UI, BG sub Overlay
        self.transition_overlay.raise_()
        # self.bg_label este deja în container, care e lowered

        # B. Aplicăm noua imagine pe bg_label (care e dedesubt)
        self.bg_label.setGeometry(self.container.rect()) # Reset la mărimea ferestrei
        
        if new_pixmap:
            self.bg_label.setStyleSheet("background: transparent;") # Resetăm culoarea solidă
            self.bg_label.setPixmap(new_pixmap)
        else:
            self.bg_label.setPixmap(QPixmap()) # Golim imaginea
            self.bg_label.setStyleSheet(f"background-color: {fallback_color};") # Culoare statică

        # C. Animăm Opacitatea Overlay-ului (Fade Out)
        self.bg_label.lower()
        self.transition_overlay.raise_()

        self.anim_group = QParallelAnimationGroup()
        effect = QGraphicsOpacityEffect(self.transition_overlay)
        self.transition_overlay.setGraphicsEffect(effect)
        
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(850)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        
        self.anim_group.addAnimation(anim)
        self.anim_group.finished.connect(self._cleanup_overlay)
        self.anim_group.start()

    def _cleanup_overlay(self):
        if self.transition_overlay:
            self.transition_overlay.hide()
            self.transition_overlay.deleteLater()
            self.transition_overlay = None

    def set_track_pixmap(self, pixmap):
        self.current_track_pixmap = pixmap
        self.update_background()

    def set_playlist_pixmap(self, pixmap):
        self._pending_playlist_context_pixmap = pixmap
        # Actualizăm doar dacă suntem pe tab-ul Playlist
        if self.main.navbar.currentIndex() == 2:
            self._playlist_update_timer.start(self._playlist_update_delay_ms)
        else:
            self._apply_pending_playlist_pixmap()
            
    def _apply_pending_playlist_pixmap(self):
        if self._pending_playlist_context_pixmap is self._no_pending_playlist_pixmap:
            return
        self.playlist_context_pixmap = self._pending_playlist_context_pixmap
        self._pending_playlist_context_pixmap = self._no_pending_playlist_pixmap
        if self.main.navbar.currentIndex() == 2:
            self.update_background()

    def handle_resize(self):
        """ Apelat din main.resizeEvent pentru a redimensiona overlay-ul """
        rect = self.main.rect()
        self.container.setGeometry(rect)
        
        if self.transition_overlay:
            self.transition_overlay.setGeometry(rect)
            
        # Asigurăm că label-ul de fundal are mereu dimensiunea corectă
        self.bg_label.setGeometry(rect)
