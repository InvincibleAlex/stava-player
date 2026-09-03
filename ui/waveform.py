import sys
import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QVariantAnimation, QAbstractAnimation, QEasingCurve, QThread
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen, QPixmap, QLinearGradient

class WaveformWorker(QThread):
    finished = pyqtSignal(list, float)

    def __init__(self, audio_engine, filepath):
        super().__init__()
        self.audio = audio_engine
        self.filepath = filepath

    def run(self):
        # Rulează pe un thread separat, nu blochează UI-ul
        if hasattr(self.audio, 'get_waveform_data'):
            peaks, duration = self.audio.get_waveform_data(self.filepath)
            self.finished.emit(peaks, duration)

class WaveformWidget(QWidget):
    # Emite secunda DOAR când utilizatorul a terminat de mutat (Release) sau la Scroll
    seek_request = pyqtSignal(float) 

    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.bass = audio_engine 
        self.setMinimumHeight(100)
        
        # Tracking pentru a detecta drag-ul
        self.setMouseTracking(True) 
        
        # Culori Default
        self.colors = {
            "PRIMARY": "#00AAFF",
            "SECONDARY": "#333333",
            "TEXT_PRIMARY": "#ffffff",
            "BACKGROUND": "transparent"
        }

        # Date Audio
        self.peaks = []       
        self.duration = 0.0   
        self.current_pos = 0.0 
        # Timpul reprezentat de un „peak” vizual.
        # Păstrăm datele audio detaliate dar afișăm o versiune „comprimată”.
        self.time_per_peak = 0.0
        
        # --- CACHE GRAFIC (NOU) ---
        self.chunks_played = [] # Lista de QPixmap (Albastru/Primary)
        self.chunks_future = [] # Lista de QPixmap (Gri/Secondary)
        self.chunk_width = 2000 # Lățimea unei bucăți pre-randate

        # Buffer-ul de cadru și masca de fade se refolosesc intre cadre - se
        # realoca doar cand se schimba dimensiunea, nu la fiecare paintEvent.
        # Inainte se realocau la fiecare cadru, cost proportional cu numarul
        # de pixeli ai ferestrei (fluent pe fereastra mica, lag pe fullscreen).
        self._frame_buffer = None
        self._frame_buffer_key = None
        self._fade_mask = None
        self._fade_mask_key = None

        # Interacțiune
        self.is_dragging = False 
        self.drag_start_x = 0    
        self.drag_start_pos = 0.0 
        
        # Vizual (stil „clean”, bare verticale cu spațiu între ele)
        self.base_bar_width = 6
        self.base_bar_gap = 4
        self.zoom_factor = 1.0
        self.bar_width = self.base_bar_width
        self.bar_gap = self.base_bar_gap
        self.stride = 5 # 🔥 COMPRESSION: 5 puncte audio = 1 bară vizuală

        # --- VISUALIZER MODE ---
        self.mode = "waveform"
        self.target_mode = None
        self.visual_updates_suspended = False
        self.layout_transition_fade_active = False
        self.fft_bars = 42
        self.current_fft = [0.0] * self.fft_bars

        # --- ANIMAȚII ---
        self.cursor_factor = 0.0 
        self.cursor_anim = QVariantAnimation()
        self.cursor_anim.setDuration(200) 
        self.cursor_anim.setEasingCurve(QEasingCurve.Type.OutCubic) 
        self.cursor_anim.valueChanged.connect(self.update_cursor_anim)

        # Animație Scroll (Rotiță)
        self.scroll_anim = QVariantAnimation()
        self.scroll_anim.setDuration(150) 
        self.scroll_anim.setEasingCurve(QEasingCurve.Type.OutQuad) 
        self.scroll_anim.valueChanged.connect(self.on_smooth_scroll)
        
        # Animație Fade In (La încărcare)
        self.opacity_factor = 1.0
        self.fade_anim = QVariantAnimation()
        self.fade_anim.setDuration(400) # 400ms fade
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.fade_anim.valueChanged.connect(self.update_fade)
        
        self.worker = None

    def set_mode(self, mode):
        if self.mode == mode: return
        self.target_mode = mode
        
        # Oprim o animație anterioară dacă e în curs
        if self.fade_anim.state() == QAbstractAnimation.State.Running:
            self.fade_anim.stop()
        try: self.fade_anim.finished.disconnect()
        except: pass
        
        # Dacă panoul este deja invizibil sau nu avem melodie (idle), schimbăm instant
        if self.opacity_factor < 0.05 or not self.peaks:
            self.mode = mode
            self.target_mode = None
            self.update()
            return
            
        # Altfel, pornim un Fade Out rapid
        self.fade_anim.setDuration(150)
        self.fade_anim.setStartValue(self.opacity_factor)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(self._on_mode_fade_out_done)
        self.fade_anim.start()
        
    def _on_mode_fade_out_done(self):
        try: self.fade_anim.finished.disconnect()
        except: pass
        
        if getattr(self, 'target_mode', None):
            self.mode = self.target_mode
            self.target_mode = None
            
        # Imediat după ce ajunge la 0 și se schimbă modul, facem Fade In
        self.fade_anim.setDuration(250)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

    def set_fft_bars(self, count):
        self.fft_bars = max(10, min(128, int(count)))
        if len(self.current_fft) != self.fft_bars:
            self.current_fft = [0.0] * self.fft_bars
        self.update()

    def set_fft_data(self, fft_raw):
        if self.mode != "visualizer": return
        if self.visual_updates_suspended: return
        needs_update = False
        if len(self.current_fft) != self.fft_bars: return
        
        if not fft_raw:
            for i in range(self.fft_bars):
                if self.current_fft[i] > 0.001:
                    self.current_fft[i] = max(0.0, self.current_fft[i] - 0.04)
                    needs_update = True
        else:
            for i in range(self.fft_bars):
                idx = int(math.pow(i / self.fft_bars, 1.5) * 60)
                idx = max(0, min(127, idx))
                boost = 8.0 + (i / self.fft_bars) * 15.0
                val = min(1.0, fft_raw[idx] * boost)
                
                if val < self.current_fft[i]: self.current_fft[i] = max(val, self.current_fft[i] - 0.05)
                else: self.current_fft[i] = min(val, self.current_fft[i] + 0.25)
                if self.current_fft[i] > 0.001: needs_update = True

        if needs_update: self.update()

    def set_zoom_factor(self, factor):
        # Acelasi motiv ca la set_theme_colors: render_chunks() e costisitor
        # (~60ms) si depinde doar de peaks, stride, bar_width, bar_gap si
        # chunk_width - nu de marimea widget-ului. Metoda asta e chemata la
        # fiecare comutare Full<->Mini prin _update_dynamic_sizes, cu acelasi
        # zoom, deci refacea cache-ul degeaba si bloca firul in mijlocul
        # animatiei de tranzitie.
        new_zoom = max(0.6, float(factor))
        new_bar_width = max(3, int(self.base_bar_width * new_zoom))
        new_bar_gap = max(2, int(self.base_bar_gap * new_zoom))
        if (new_zoom == self.zoom_factor
                and new_bar_width == self.bar_width
                and new_bar_gap == self.bar_gap):
            return

        self.zoom_factor = new_zoom
        self.bar_width = new_bar_width
        self.bar_gap = new_bar_gap
        self.render_chunks()
        self.update()

    def set_theme_colors(self, theme_colors):
        # Randarea chunk-urilor (render_chunks) e costisitoare - o facem doar
        # daca s-au schimbat culorile care chiar apar in desen. Altfel se
        # refacea tot cache-ul de imagini de fiecare data cand Player-ul
        # trecea Full<->Mini, chiar daca tema era aceeasi (~50ms irosite).
        old_primary = self.colors.get("PRIMARY")
        old_secondary = self.colors.get("SECONDARY")
        self.colors.update(theme_colors)
        colors_changed = (
            old_primary != self.colors.get("PRIMARY")
            or old_secondary != self.colors.get("SECONDARY")
        )
        if colors_changed:
            self.render_chunks()
        self.update()

    def update_fade(self, val):
        self.opacity_factor = float(val)
        if not self.visual_updates_suspended:
            self.update()

    def update_cursor_anim(self, value):
        self.cursor_factor = float(value)
        self.update() 

    def on_smooth_scroll(self, value):
        # Rotița face seek imediat
        new_pos = float(value)
        self.current_pos = new_pos
        self.seek_request.emit(new_pos)
        self.update()

    def load_song_async(self, filepath):
        """ Încarcă waveform-ul pe un thread separat pentru a nu bloca UI-ul """
        # 1. Reset la starea "Loading" — rămâne invizibil până la fade-in
        self.peaks = []
        self.duration = 0
        self.current_pos = 0
        self.chunks_played = []
        self.chunks_future = []
        self.opacity_factor = 0.0
        self.update()

        # 2. Oprim worker-ul vechi graceful dacă există
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(2000)  # Așteptăm max 2s
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait()

        # 3. Pornim noul worker
        self.worker = WaveformWorker(self.bass, filepath)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_finished(self, peaks, duration):
        self.load_data(peaks, duration)

    def load_song(self, filepath):
        self.peaks = []
        self.duration = 0
        self.current_pos = 0
        self.chunks_played = []
        self.chunks_future = []
        self.update()
        try:
            if hasattr(self.bass, 'get_waveform_data'):
                data, dur = self.bass.get_waveform_data(filepath)
                if data:
                    self.duration = float(dur)
                    self.peaks = list(data)
                    if self.duration > 0 and len(self.peaks) > 1:
                        self.time_per_peak = self.duration / float(len(self.peaks) - 1)
                    else:
                        self.time_per_peak = 0.0
        except Exception as e:
            print(f"Waveform Error: {e}")
            
        # Generăm imaginile o singură dată la încărcare
        if self.peaks:
            self.render_chunks()
            self.update()
            
    def load_data(self, peaks, duration):
        """ Încarcă date pre-calculate (din DB) - INSTANT """
        # Oprim worker-ul dacă rulează (caz rar de race condition)
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        self.peaks = peaks
        self.duration = duration
        self.current_pos = 0
        self.chunks_played = []
        self.chunks_future = []
        
        # 🔥 FIX: Defer rendering to main thread to avoid QPainter conflicts
        if self.peaks:
            # Use QTimer to ensure rendering happens on main thread
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self.render_chunks)
            QTimer.singleShot(5, self.update)
        if self.duration > 0 and len(self.peaks) > 1:
            self.time_per_peak = self.duration / float(len(self.peaks) - 1)
            
        self.render_chunks()
        self.update()
        
        # Start Fade In (Efect vizual plăcut)
        if self.fade_anim.state() == QAbstractAnimation.State.Running:
            self.fade_anim.stop()
        try: self.fade_anim.finished.disconnect()
        except: pass
        
        # Dacă a fost întreruptă o comutare de mod de o melodie nouă, aplicăm modul
        if getattr(self, 'target_mode', None):
            self.mode = self.target_mode
            self.target_mode = None
            
        self.fade_anim.setDuration(400) # Resetăm durata la cea de încărcare normală
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

    def render_chunks(self):
        """ Pre-randează waveform-ul în imagini statice (Chunks) """
        self.chunks_played = []
        self.chunks_future = []
        
        if not self.peaks: return

        # --- COMPRESSION LOGIC ---
        # Grupăm 'self.stride' puncte într-o singură bară vizuală (Max value)
        display_peaks = []
        for i in range(0, len(self.peaks), self.stride):
            chunk = self.peaks[i:i+self.stride]
            if chunk:
                display_peaks.append(max(chunk))

        step_px = self.bar_width + self.bar_gap
        total_width = len(display_peaks) * step_px
        num_chunks = math.ceil(total_width / self.chunk_width)
        
        # Culori
        c_prim = QColor(self.colors.get("PRIMARY", "#00AAFF"))
        c_prim.setAlpha(230)
        c_sec = QColor(self.colors.get("SECONDARY", "#333333"))
        c_sec.setAlpha(150)
        
        # Înălțimea fixă a cache-ului, scalată pentru DPI
        dpr = self.devicePixelRatioF()
        cache_h = int(160 * dpr)
        phys_chunk_width = int(self.chunk_width * dpr)

        for i in range(num_chunks):
            # 1. Creăm Pixmap-uri transparente la rezoluție fizică
            pm_played = QPixmap(phys_chunk_width, cache_h)
            pm_played.fill(Qt.GlobalColor.transparent)
            pm_played.setDevicePixelRatio(dpr)
            
            pm_future = QPixmap(phys_chunk_width, cache_h)
            pm_future.fill(Qt.GlobalColor.transparent)
            pm_future.setDevicePixelRatio(dpr)
            
            # 2. Desenăm barele (coordonatele sunt logice, QPainter scalează automat)
            self._draw_chunk(pm_played, i, step_px, c_prim, 160, display_peaks)
            self._draw_chunk(pm_future, i, step_px, c_sec, 160, display_peaks)
            
            self.chunks_played.append(pm_played)
            self.chunks_future.append(pm_future)

    def _draw_chunk(self, pixmap, chunk_index, step_px, color, h, peaks_data):
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)

        start_idx = int((chunk_index * self.chunk_width) / step_px)
        # Desenăm un pic peste margine pentru a nu tăia barele la îmbinare
        end_idx = int(((chunk_index + 1) * self.chunk_width) / step_px) + 1
        end_idx = min(end_idx, len(peaks_data))

        for j in range(start_idx, end_idx):
            peak = peaks_data[j]
            norm = max(0.0, min(1.0, float(peak) if peak > 0 else -peak))
            bar_h = max(4.0, norm * h)
            
            x = (j * step_px) - (chunk_index * self.chunk_width)
            y = (h - bar_h) / 2.0
            
            painter.drawRoundedRect(QRectF(x, y, self.bar_width, bar_h), self.bar_width/2, self.bar_width/2)
        
        painter.end()

    def set_position(self, pos_seconds):
        # Cât timp facem DRAG sau SCROLL, ignorăm update-urile de la timer-ul melodiei.
        if not self.is_dragging and self.scroll_anim.state() == QAbstractAnimation.State.Stopped:
            if abs(pos_seconds - self.current_pos) < 0.03:
                return
            self.current_pos = pos_seconds
            if not self.visual_updates_suspended:
                self.update()

    def suspend_visual_updates(self, suspended):
        self.visual_updates_suspended = bool(suspended)
        self.setUpdatesEnabled(not self.visual_updates_suspended)
        if not self.visual_updates_suspended:
            self.update()

    def prepare_for_layout_transition(self):
        self.layout_transition_fade_active = True
        if self.fade_anim.state() == QAbstractAnimation.State.Running:
            self.fade_anim.stop()
        try: self.fade_anim.finished.disconnect()
        except: pass
        self.opacity_factor = 0.0
        self.suspend_visual_updates(True)

    def fade_in_after_layout_transition(self, duration_ms=260):
        self.suspend_visual_updates(False)
        if self.fade_anim.state() == QAbstractAnimation.State.Running:
            self.fade_anim.stop()
        try: self.fade_anim.finished.disconnect()
        except: pass

        def finish():
            self.layout_transition_fade_active = False
            self.opacity_factor = 1.0
            self.update()

        self.fade_anim.setDuration(max(1, int(duration_ms)))
        self.fade_anim.setStartValue(self.opacity_factor)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.finished.connect(finish)
        self.fade_anim.start()

    def wheelEvent(self, event):
        """ 
        Rotița face seek +/- 1 secundă.
        INVERSAT: Scroll UP (+) = Înainte, Scroll DOWN (-) = Înapoi
        """
        delta = event.angleDelta().y()
        step = 1.0 
        
        # 🔥 LOGICA INVERSATĂ AICI
        if delta > 0: 
            target_pos = self.current_pos + step # Scroll UP -> MERGI ÎNAINTE
        else: 
            target_pos = self.current_pos - step # Scroll DOWN -> MERGI ÎNAPOI
            
        target_pos = max(0.0, min(target_pos, self.duration))
        
        self.scroll_anim.stop() 
        self.scroll_anim.setStartValue(self.current_pos)
        self.scroll_anim.setEndValue(target_pos)
        self.scroll_anim.start()

    # --- MOUSE EVENTS ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.scroll_anim.stop() 
            self.is_dragging = True
            self.drag_start_x = event.position().x()
            self.drag_start_pos = self.current_pos
            
            # Animație Start (Apare bara)
            self.cursor_anim.stop()
            self.cursor_anim.setStartValue(self.cursor_factor)
            self.cursor_anim.setEndValue(1.0)
            self.cursor_anim.setDirection(QAbstractAnimation.Direction.Forward)
            self.cursor_anim.start()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            # Calculăm noua poziție VIZUALĂ
            # De data asta, dacă tragem spre stânga, vedem viitorul (melodia "vine" spre noi)
            # sau invers? La "center lock", dacă tragi waveform-ul spre stânga, te duci în viitor.
            
            current_x = event.position().x()
            diff_pixels = self.drag_start_x - current_x # Diferența
            
            # Calculăm dinamic câți pixeli reprezintă o secundă
            if self.time_per_peak > 0:
                sec_per_bar = self.stride * self.time_per_peak
                pps = (self.bar_width + self.bar_gap) / sec_per_bar
                diff_seconds = diff_pixels / pps
            else:
                diff_seconds = 0
            
            new_pos = self.drag_start_pos + diff_seconds
            new_pos = max(0.0, min(new_pos, self.duration))
            
            self.current_pos = new_pos
            self.update()

    def mouseReleaseEvent(self, event):
        if self.is_dragging and event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            
            # Seek final (fără gap)
            self.seek_request.emit(self.current_pos)
            
            # Animație Stop (Dispare bara)
            self.cursor_anim.stop()
            self.cursor_anim.setStartValue(self.cursor_factor)
            self.cursor_anim.setEndValue(0.0)
            self.cursor_anim.setDirection(QAbstractAnimation.Direction.Forward)
            self.cursor_anim.start()

    def leaveEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.seek_request.emit(self.current_pos)
            
            self.cursor_anim.stop()
            self.cursor_anim.setStartValue(self.cursor_factor)
            self.cursor_anim.setEndValue(0.0)
            self.cursor_anim.start()
        self.update()

    # --- DESENARE ---
    def paintEvent(self, event):
        if self.visual_updates_suspended:
            return
        painter = QPainter(self) # Painter-ul final (pe widget)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Aplicăm opacitatea globală (pentru Fade In)
        # Dacă suntem în loading (peaks=[]), opacity e 1.0 (Idle). Când încărcăm, animăm 0->1.
        if self.peaks: painter.setOpacity(self.opacity_factor)
        
        # 1. Background
        bg_col = self.colors.get("BACKGROUND", "transparent")
        if bg_col != "transparent":
            painter.fillRect(self.rect(), QColor(bg_col))

        w = self.width()
        h = self.height()
        center_x = w / 2 
        
        # --- BUFFER PENTRU WAVEFORM (PENTRU FADE) ---
        # Desenăm waveform-ul într-un pixmap temporar pentru a putea aplica masca de fade.
        # Buffer-ul e persistent intre cadre, doar continutul se sterge/redeseneaza.
        dpr = self.devicePixelRatioF()
        phys_w = max(1, int(w * dpr))
        phys_h = max(1, int(h * dpr))
        buffer_key = (phys_w, phys_h)
        if self._frame_buffer is None or self._frame_buffer_key != buffer_key:
            self._frame_buffer = QPixmap(phys_w, phys_h)
            self._frame_buffer.setDevicePixelRatio(dpr)
            self._frame_buffer_key = buffer_key
        wave_pix = self._frame_buffer
        wave_pix.fill(Qt.GlobalColor.transparent)

        p = QPainter(wave_pix) # Painter-ul temporar
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        c_prim = QColor(self.colors.get("PRIMARY", "#00AAFF"))
        c_sec = QColor(self.colors.get("SECONDARY", "#333333"))
        
        color_played = QColor(c_prim)
        color_played.setAlpha(230)
        
        color_future = QColor(c_sec)
        color_future.setAlpha(150) 

        # 2. Idle State
        if not self.peaks:
            self._draw_idle_pattern(p, w, h/2)
            # Continuăm execuția pentru a aplica fade-ul și a desena pe ecran

        # 3. Desenare Visualizer
        elif self.mode == "visualizer":
            self._draw_visualizer(p, w, h)
        # 4. Desenare Waveform (Center-Lock, imagine liniară care se translatează)
        # Dacă nu avem durată/mapare validă, nu desenăm nimic
        elif self.duration > 0 and self.time_per_peak > 0 and self.chunks_played:
            # Pasul între bare în pixeli este fix (bar_width + gap) – ca la o imagine discretă.
            step_px = self.bar_width + self.bar_gap

            # Offset-ul „imaginii” în pixeli, proporțional cu timpul curent.
            # Împărțim la stride pentru a ține cont de compresie
            current_index = (self.current_pos / self.time_per_peak) / self.stride
            scroll_offset = current_index * step_px

            # Desenăm Chunks
            draw_start_x = center_x - scroll_offset
            
            visible_start = scroll_offset - (w / 2)
            visible_end = scroll_offset + (w / 2)
            
            first_chunk = max(0, int(visible_start / self.chunk_width))
            last_chunk = min(len(self.chunks_played), int(visible_end / self.chunk_width) + 1)
            
            scale_y = min(1.0, (h * 0.8) / 160.0)
            target_h = 160.0 * scale_y
            y_offset = (h - target_h) / 2.0

            for i in range(first_chunk, last_chunk):
                chunk_x = draw_start_x + (i * self.chunk_width)
                
                # Desenăm pe buffer 'p' (chunks sunt deja la rezoluție fizică, drawPixmap le scalează corect)
                p.setClipRect(0, 0, int(center_x), int(h))
                p.drawPixmap(QRectF(chunk_x, y_offset, self.chunk_width, target_h),
                             self.chunks_played[i],
                             QRectF(self.chunks_played[i].rect()))
                
                p.setClipRect(int(center_x), 0, int(w - center_x), int(h))
                p.drawPixmap(QRectF(chunk_x, y_offset, self.chunk_width, target_h),
                             self.chunks_future[i],
                             QRectF(self.chunks_future[i].rect()))

            p.setClipping(False)

            # 4. CURSOR ANIMAT (Pe buffer)
            if self.cursor_factor > 0.01:
                cursor_col = QColor(self.colors.get("TEXT_PRIMARY", "#FFFFFF"))
                cursor_col.setAlpha(220)
                
                pen = QPen(cursor_col, 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap) 
                p.setPen(pen)
                
                max_h = target_h
                current_h = max_h * self.cursor_factor
                
                y_start = (h / 2) - (current_h / 2)
                y_end = (h / 2) + (current_h / 2)
                
                p.drawLine(int(center_x), int(y_start), int(center_x), int(y_end))

        # --- APLICARE FADE MASK PE BUFFER ---
        # Folosim DestinationIn pentru a face marginile transparente.
        # Masca e cache-uita: gradientul se recalculeaza doar cand se schimba
        # dimensiunea sau zoom-ul, nu la fiecare cadru.
        fade_w = max(20, int(40 * self.zoom_factor)) # Distanță scurtă de fade
        if w > 0:
            mask_key = (phys_w, phys_h, fade_w)
            if self._fade_mask is None or self._fade_mask_key != mask_key:
                self._fade_mask = self._build_fade_mask(w, h, dpr, fade_w)
                self._fade_mask_key = mask_key

            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            p.drawPixmap(0, 0, self._fade_mask)

        p.end() # Terminăm desenarea pe buffer

        # 5. Desenăm Buffer-ul pe Widget
        painter.drawPixmap(0, 0, wave_pix)

        # 6. Timpi (Mereu vizibili, desenați PESTE fade)
        self._draw_timers(painter, w, h)

    def _draw_visualizer(self, painter, w, h):
        step_x = w / self.fft_bars
        bar_w = step_x * 0.65
        fft_c = QColor(self.colors.get("PRIMARY", "#00AAFF"))
        painter.setBrush(QBrush(fft_c))
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(self.fft_bars):
            val = self.current_fft[i]
            if val > 0.005:
                bar_h = val * h * 0.9 
                bx = i * step_x + (step_x - bar_w) / 2 
                radius = min(bar_w / 2.0, bar_h / 2.0)
                painter.drawRoundedRect(QRectF(bx, h - bar_h, bar_w, bar_h), radius, radius)

    def _draw_timers(self, painter, w, h):
        # Timere desenate în „bule" rotunjite (stil similar cu exemplul din poză)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        time_font = painter.font()
        time_font.setPointSize(max(8, int(9 * self.zoom_factor)))
        time_font.setBold(True)
        painter.setFont(time_font)

        elapsed_str = self.format_time(self.current_pos)
        total_str = self.format_time(self.duration)

        fm = painter.fontMetrics()
        pad_x = max(6, int(10 * self.zoom_factor))
        pad_y = max(3, int(4 * self.zoom_factor))
        edge_m = max(3, int(5 * self.zoom_factor))

        # Culori pentru buline (fundal închis + text alb)
        bg_col = QColor(0, 0, 0, 200)
        text_col = QColor(255, 255, 255)

        # Stânga – timp scurs
        elapsed_w = fm.horizontalAdvance(elapsed_str) + pad_x * 2
        elapsed_h = fm.height() + pad_y * 2
        left_rect = QRectF(edge_m, h - elapsed_h - edge_m, elapsed_w, elapsed_h)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_col)
        painter.drawRoundedRect(left_rect, elapsed_h / 2, elapsed_h / 2)

        painter.setPen(text_col)
        painter.drawText(left_rect, int(Qt.AlignmentFlag.AlignCenter), elapsed_str)

        # Dreapta – durata totală
        total_w = fm.horizontalAdvance(total_str) + pad_x * 2
        total_h = fm.height() + pad_y * 2
        right_rect = QRectF(w - total_w - edge_m, h - total_h - edge_m, total_w, total_h)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_col)
        painter.drawRoundedRect(right_rect, total_h / 2, total_h / 2)

        painter.setPen(text_col)
        painter.drawText(right_rect, int(Qt.AlignmentFlag.AlignCenter), total_str)

    def _build_fade_mask(self, w, h, dpr, fade_w):
        """ Construieste masca de fade (transparent la margini) o singura
        data pentru o dimensiune/zoom date, in loc sa recalculeze gradientul
        la fiecare cadru. """
        mask = QPixmap(max(1, int(w * dpr)), max(1, int(h * dpr)))
        mask.setDevicePixelRatio(dpr)
        mask.fill(Qt.GlobalColor.transparent)

        mp = QPainter(mask)
        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))       # Transparent stânga
        gradient.setColorAt(fade_w / w, QColor(0, 0, 0, 255)) # Opac după fade_w
        gradient.setColorAt(1.0 - (fade_w / w), QColor(0, 0, 0, 255)) # Opac până la dreapta
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))       # Transparent dreapta
        mp.fillRect(QRectF(0, 0, w, h), gradient)
        mp.end()

        return mask

    def _draw_idle_pattern(self, painter, w, mid_y):
        col = QColor(self.colors.get('PRIMARY', '#00AAFF'))
        col.setAlpha(80)
        painter.setBrush(col)
        painter.setPen(Qt.PenStyle.NoPen)
        spacing = 10
        for x in range(0, w, spacing):
            painter.drawEllipse(QRectF(x, mid_y - 2, 4, 4))

    @staticmethod
    def format_time(seconds):
        s = int(seconds)
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        if h > 0: return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"

def convert_policy(val):
    from PyQt6.QtWidgets import QSizePolicy
    if val == 1: return QSizePolicy.Policy.Expanding
    return QSizePolicy.Policy.Fixed
