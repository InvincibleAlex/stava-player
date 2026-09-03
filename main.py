import sys
import os
import shutil
import signal
import time
import re

# Pe Windows, cand stdout/stderr e redirectat (fisier, pipe, consola veche),
# Python foloseste encoding-ul local (ex. cp1252) in loc de UTF-8. Orice print()
# cu diacritice (titluri de piese, nume de fisiere) crapa cu UnicodeEncodeError.
# Fortam UTF-8 aici, cat mai devreme, ca sa evitam asta peste tot in aplicatie.
for _stream in (sys.stdout, sys.stderr):
    if _stream is None:
        continue
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QObject, QEvent, QTimer, Qt, QProcess, qInstallMessageHandler
from PyQt6.QtGui import QIcon  

_original_set_stylesheet = QWidget.setStyleSheet


def _safe_set_stylesheet(self, stylesheet):
    if isinstance(stylesheet, str) and "font-size" in stylesheet:
        def clamp_font_size(match):
            size = int(match.group(1))
            return f"font-size: {max(1, size)}px"

        stylesheet = re.sub(r"font-size\s*:\s*(-?\d+)px", clamp_font_size, stylesheet)
    return _original_set_stylesheet(self, stylesheet)


def _qt_message_handler(mode, context, message):
    if message == "QFont::setPixelSize: Pixel size <= 0 (0)":
        return
    print(message, file=sys.stderr)


QWidget.setStyleSheet = _safe_set_stylesheet
qInstallMessageHandler(_qt_message_handler)

# --- ADAUGĂ ACEASTĂ FUNCȚIE AICI PENTRU PYINSTALLER ---
def resource_path(relative_path):
    """ Obține calea absolută, funcționează și pentru VS Code și pentru PyInstaller """
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            # --onedir: Resursele sunt lângă executabil
            base_path = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        
    return os.path.join(base_path, relative_path)

# --- IMPORTURI ---
from audio.audio_engine import AudioEngine
from playlist.queue_manager import QueueManager
from core.session_manager import SessionManager # 🔥 Noul manager de setări
from core.playback_controller import PlaybackController # 🔥 Noul manager de redare
from core.events_coordinator import EventsCoordinator # 🔥 Noul manager de evenimente
from ui.main_window_builder import MainWindowBuilder # 🔥 Noul manager de UI

import core.themes as themes
from animations import AnimationManager
from core.utils import IconHelper

# Core Modules
from background.background_manager import BackgroundManager
from core.navigation_controller import NavigationController
from core.os_integration import OSIntegration
from core.discord_presence import DiscordPresenceManager

# Debug
try:
    import core.debug_theme as debug_theme
except ImportError:
    debug_theme = None

class DebugHoverInspector(QObject):
    def __init__(self, main_app):
        super().__init__(main_app)
        self.main = main_app
        self.enabled = False
        self._installed = False
        self._name_cache = {}
        self._last_cache_ms = 0

    def set_enabled(self, enabled):
        enabled = bool(enabled)
        app = QApplication.instance()
        if not app:
            return

        if enabled and not self._installed:
            app.installEventFilter(self)
            self._installed = True
        elif not enabled and self._installed:
            app.removeEventFilter(self)
            self._installed = False

        self.enabled = enabled
        if not enabled:
            self._name_cache = {}

    def eventFilter(self, obj, event):
        if not self.enabled or not isinstance(obj, QWidget):
            return False

        if event.type() == QEvent.Type.ToolTip:
            try:
                pos = event.globalPos()
            except Exception:
                pos = obj.mapToGlobal(obj.rect().center())
            from PyQt6.QtWidgets import QToolTip
            QToolTip.showText(pos, self._describe_widget(obj), obj)
            return True

        return False

    def _describe_widget(self, widget):
        names = self._names_for(widget)
        object_name = self._safe_call(widget, "objectName")
        class_name = widget.__class__.__name__

        lines = [
            "Debug hover",
            f"Name: {names or '(no Python attribute found)'}",
            f"ObjectName: {object_name or '(empty)'}",
            f"Class: {class_name}",
        ]

        label = self._display_text(widget)
        if label:
            lines.append(f"Text: {label}")

        parent_name = self._nearest_named_parent(widget)
        if parent_name and parent_name != names:
            lines.append(f"Parent: {parent_name}")

        return "\n".join(lines)

    def _names_for(self, widget):
        self._refresh_name_cache_if_needed()
        names = self._name_cache.get(id(widget), [])
        if names:
            return ", ".join(names[:4])
        return ""

    def _nearest_named_parent(self, widget):
        parent = widget.parentWidget()
        while parent:
            name = self._names_for(parent)
            if name:
                return name
            parent = parent.parentWidget()
        return ""

    def _display_text(self, widget):
        for method_name in ("text", "title", "placeholderText"):
            text = self._safe_call(widget, method_name)
            if text:
                return str(text).replace("\n", " ")[:120]
        return ""

    def _safe_call(self, obj, method_name):
        method = getattr(obj, method_name, None)
        if not callable(method):
            return ""
        try:
            return method() or ""
        except Exception:
            return ""

    def _refresh_name_cache_if_needed(self):
        now_ms = int(time.monotonic() * 1000)
        if self._name_cache and now_ms - self._last_cache_ms < 500:
            return
        self._last_cache_ms = now_ms
        self._name_cache = {}
        self._collect_names(self.main, "main")

    def _collect_names(self, root, root_name):
        queue = [(root, root_name, 0)]
        visited = set()

        while queue and len(visited) < 4000:
            obj, path, depth = queue.pop(0)
            obj_id = id(obj)
            if obj_id in visited:
                continue
            visited.add(obj_id)

            if isinstance(obj, QWidget):
                self._name_cache.setdefault(obj_id, []).append(path)

            if depth >= 4:
                continue

            try:
                attrs = vars(obj)
            except Exception:
                attrs = {}

            for name, value in attrs.items():
                if name.startswith("_") and name not in {"_wider_editor_popup", "_wider_editor_host"}:
                    continue
                child_path = f"{path}.{name}"
                self._enqueue_named_value(queue, value, child_path, depth + 1)

    def _enqueue_named_value(self, queue, value, path, depth):
        if isinstance(value, QObject):
            queue.append((value, path, depth))
            return

        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value[:80]):
                if isinstance(item, QObject):
                    queue.append((item, f"{path}[{index}]", depth))
            return

        if isinstance(value, dict):
            for key, item in list(value.items())[:80]:
                if isinstance(item, QObject):
                    queue.append((item, f"{path}[{key!r}]", depth))

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STAVA Player")
        self._debug_hover_inspector = DebugHoverInspector(self)
        
        # --- ICONIȚĂ APLICAȚIE (Folosind resource_path) ---
        icon_path = resource_path(os.path.join('icons', 'Logo.icns'))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setMinimumSize(1000, 620)
        
        # --- RESTAURARE GEOMETRIE (Dimensiuni & Poziție) ---
        self.session = SessionManager(self)
        self.session.restore_geometry()

        # --- SEPARARE LOGICĂ ÎN MODULE DE INIȚIALIZARE ---
        self._init_core_managers()
        self.builder = MainWindowBuilder(self)
        self.builder.build_layout()
        self.builder.setup_bottom_bar()
        self.session.restore_early_session() # 🔥 Preia controlul de la funcția ștearsă
        
        self.events = EventsCoordinator(self)
        self.events.setup_all_connections()
        self._init_timers()
        self._start_lazy_loading()

    def _init_core_managers(self):
        self.audio = AudioEngine()
        self._wider_editor_popup = None
        self._wider_editor_host = None
        try:
            self.audio.set_vst_editor_parent_hwnd(int(self.winId()))
        except:
            pass
        self._apply_vst_debug_settings()

        self.current_path = None
        self.eq_bands_on = True
        self.knobs_on = True
        self.spatial_on = True
        self.reverb_on = True
        self.last_used_theme = "Dark"
        self._skip_settings_save_once = False
        
        self.qm = QueueManager() 
        self.playback = PlaybackController(self)
        
        self.anim_manager = AnimationManager(self)
        self._apply_animation_speed_settings()
        self.discord_presence = DiscordPresenceManager(self.settings)
        self.bg_manager = BackgroundManager(self)
        self.nav_controller = NavigationController(self)
        
        self.os_integration = OSIntegration(self)
        self.os_integration.play_triggered.connect(self.playback.toggle_play_ui)
        self.os_integration.pause_triggered.connect(self.playback.toggle_play_ui)
        self.os_integration.toggle_triggered.connect(self.playback.toggle_play_ui)
        self.os_integration.next_triggered.connect(self.playback.play_next)
        self.os_integration.prev_triggered.connect(self.playback.play_prev)
        self.os_integration.shuffle_triggered.connect(self.playback.set_shuffle_from_os)
        self.os_integration.loop_triggered.connect(self.playback.set_loop_from_os)

    def _apply_animation_speed_settings(self, value=None):
        try:
            speed_ms = int(value if value is not None else self.settings.value("animation_speed_ms", 350, type=int))
        except:
            speed_ms = 350

        speed_ms = max(120, min(900, speed_ms))
        self.anim_manager.speed_move = speed_ms
        self.anim_manager.speed_fade_in = speed_ms
        self.anim_manager.speed_fade_out = speed_ms

    def _refresh_discord_presence_settings(self):
        if hasattr(self, 'discord_presence'):
            self.discord_presence.refresh_from_settings()

    def _refresh_statistics_panel(self):
        if not getattr(self, 'ui_settings', None):
            return
        if not getattr(self, 'ui_playlist', None) or not hasattr(self.ui_playlist, 'logic'):
            return
        try:
            summary = self.ui_playlist.logic.get_statistics_summary()
            self.ui_settings.set_statistics_data(summary)
        except Exception:
            pass

    def _init_timers(self):
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        ui_refresh_ms = self.settings.value("ui_refresh_ms", 0, type=int)
        if ui_refresh_ms <= 0:
            ui_refresh_ms = self._detect_ui_refresh_interval_ms()
        ui_refresh_ms = max(6, min(50, ui_refresh_ms))
        self.timer.setInterval(ui_refresh_ms)
        self.timer.timeout.connect(self.playback.update_ui_loop)
        self.timer.start()

    def _start_lazy_loading(self):
        saved_theme = self.settings.value("theme", "Dark", type=str)
        self.apply_theme(saved_theme)
        self.on_tab_changed(0)
        self._refresh_wider_knob_tooltips()
        
        QTimer.singleShot(100, self.bg_manager.update_background)
        QTimer.singleShot(50, self._deferred_startup_init)

    def _deferred_startup_init(self):
        self.builder.init_deferred_ui()

        # 3. Restaurare setări și stări pentru EQ
        self.session.restore_deferred_ui_state()

        # 4. Conectăm semnalele EQ și Settings (acum că UI-ul există)
        self.events.setup_deferred_connections()

        # 5. Restaurăm valorile slidere/knob-urilor
        self._restore_effect_settings()
        self._refresh_wider_knob_tooltips()

        # 7. Aplicăm culorile temei pe noile tab-uri
        colors = themes.THEME_PALETTES.get(self.last_used_theme, themes.THEME_PALETTES["Dark"])
        if hasattr(self.ui_eq, 'update_theme_colors'):
            self.ui_eq.update_theme_colors(colors)
        if hasattr(self.ui_settings, 'update_theme_colors'):
            self.ui_settings.update_theme_colors(colors)
        self._refresh_statistics_panel()
            
        print("DEBUG: Deferred UI (EQ & Settings) initialized successfully.")

    def _detect_ui_refresh_interval_ms(self):
        """Detectează intervalul optim pentru timer din refresh rate-ul monitorului."""
        try:
            screen = self.screen() or QApplication.primaryScreen()
            if not screen:
                return 16

            hz = float(screen.refreshRate())
            if hz <= 1:
                return 16

            # Interval aproximativ pentru frame update (ex: 144Hz -> 7ms, 60Hz -> 16ms)
            interval = int(round(1000.0 / hz))
            return max(6, interval)
        except:
            return 16

    # Notă: Am păstrat _restore_effect_settings (apelat mai sus) direct în Main 
    # deoarece implică mult cod audio și blocaje de semnale care sunt strict legate de interfață.
    def _restore_effect_settings(self):
        if not getattr(self, 'ui_eq', None):
            return
            
        controls = []
        spatial = self.ui_eq.page_spatial
        reverb = self.ui_eq.page_reverb

        controls = [
            spatial.knob_tempo,
            spatial.knob_balance,
            spatial.knob_stereo,
            spatial.knob_low_bypass,
            reverb.knob_damp,
            reverb.knob_filter,
            reverb.knob_fade,
            reverb.knob_predelay,
            reverb.knob_predelay_mix,
            reverb.knob_size,
            self.ui_eq.slider_preamp,
            self.ui_eq.knob_bass,
            self.ui_eq.knob_treble,
        ]
        controls.extend(self.ui_eq.sliders)

        for control in controls:
            # 🔥 FIX: Oprim orice animație vizuală care ar suprascrie valoarea restaurată
            if hasattr(control, '_val_anim'):
                control._val_anim.stop()
            # Eliminat control.blockSignals(True) pentru a permite widget-urilor să se redeseneze!

        # RESTAURARE PREAMP, BASS ȘI TREBLE
        self.ui_eq.slider_preamp.setValue(self.settings.value("eq_preamp", 0, type=int))
        self.ui_eq.knob_bass.setValue(self.settings.value("eq_bass_knob", 0.0, type=float))
        self.ui_eq.knob_treble.setValue(self.settings.value("eq_treble_knob", 0.0, type=float))

        # RESTAURARE BENZI GRAPHIC EQ
        saved_bands = self.settings.value("eq_bands_values")
        if saved_bands is not None:
            try:
                if isinstance(saved_bands, str):
                    if saved_bands.startswith('[') or saved_bands.startswith('('):
                        import ast
                        saved_bands = ast.literal_eval(saved_bands)
                    elif ',' in saved_bands:
                        saved_bands = [x.strip() for x in saved_bands.split(',') if x.strip()]
                if isinstance(saved_bands, (list, tuple)):
                    for i, val in enumerate(saved_bands):
                        if i < len(self.ui_eq.sliders):
                            self.ui_eq.sliders[i].setValue(int(float(val)))
            except Exception as e:
                print(f"DEBUG: Failed to restore bands: {e}")

        spatial.knob_tempo.setValue(self.settings.value("fx_tempo", 1.0, type=float))
        spatial.knob_balance.setValue(self.settings.value("fx_balance", 50.0, type=float))
        spatial.knob_stereo.setValue(self.settings.value("fx_stereo_expand", 0.0, type=float))
        spatial.knob_low_bypass.setValue(self.settings.value("fx_low_bypass", 0.0, type=float))

        reverb.knob_damp.setValue(self.settings.value("fx_reverb_damp", 0.0, type=float))
        reverb.knob_filter.setValue(self.settings.value("fx_reverb_filter", 0.0, type=float))
        reverb.knob_fade.setValue(self.settings.value("fx_reverb_fade", 0.0, type=float))
        reverb.knob_predelay.setValue(self.settings.value("fx_reverb_predelay", 0.0, type=float))
        reverb.knob_predelay_mix.setValue(self.settings.value("fx_reverb_predelay_mix", 0.0, type=float))
        reverb.knob_size.setValue(self.settings.value("fx_reverb_size", 0.0, type=float))
        
        # 🔥 FIX: Aplicăm corect starea "zeroed" pentru a asigura compatibilitatea cu animațiile
        master_on = self.ui_eq.btn_master.isChecked()
        tone_on = master_on and self.ui_eq.btn_tone.isChecked()
        spatial_on = master_on and hasattr(self.ui_eq, 'btn_spatial') and self.ui_eq.btn_spatial.isChecked()
        reverb_on = master_on and hasattr(self.ui_eq, 'btn_reverb') and self.ui_eq.btn_reverb.isChecked()
        
        def sync_zero_state(knob, is_on, zero_val=0.0):
            knob._saved_value = knob.value()
            if not is_on:
                knob.setValue(zero_val)
                knob._is_zeroed = True
            else:
                knob._is_zeroed = False
                
        sync_zero_state(self.ui_eq.knob_bass, tone_on, 0.0)
        sync_zero_state(self.ui_eq.knob_treble, tone_on, 0.0)
        sync_zero_state(spatial.knob_tempo, spatial_on, 1.0)
        sync_zero_state(spatial.knob_balance, spatial_on, 50.0)
        sync_zero_state(spatial.knob_stereo, spatial_on, 0.0)
        sync_zero_state(spatial.knob_low_bypass, spatial_on, 0.0)
        sync_zero_state(reverb.knob_damp, reverb_on, 0.0)
        sync_zero_state(reverb.knob_filter, reverb_on, 0.0)
        sync_zero_state(reverb.knob_fade, reverb_on, 0.0)
        sync_zero_state(reverb.knob_predelay, reverb_on, 0.0)
        sync_zero_state(reverb.knob_predelay_mix, reverb_on, 0.0)
        sync_zero_state(reverb.knob_size, reverb_on, 0.0)

        # 🔥 FIX: Sincronizăm stările interne cu butoanele UI (deoarece semnalele au fost blocate la pornire)
        self.eq_bands_on = self.ui_eq.btn_bands.isChecked()
        self.knobs_on = self.ui_eq.btn_tone.isChecked()
        if hasattr(self.ui_eq, 'btn_spatial'): self.spatial_on = self.ui_eq.btn_spatial.isChecked()
        if hasattr(self.ui_eq, 'btn_reverb'): self.reverb_on = self.ui_eq.btn_reverb.isChecked()

        # 🔥 FIX: Forțăm actualizarea dreptunghiului vizual (Graficele EQ și Tone)
        self.ui_eq.update_visualizer_tone()
        self.ui_eq.update_visualizer_eq()

        # Aplicăm setările restaurate pentru EQ în engine
        self.audio.set_preamp(self.ui_eq.slider_preamp.value())
        self.force_refresh_knobs()
        self.force_refresh_eq()

        self.audio.set_tempo(spatial.knob_tempo.value())
        self.audio.set_balance(spatial.knob_balance.value())
        self.audio.set_stereo_expand(spatial.knob_stereo.value())
        self.audio.set_stereo_low_bypass(spatial.knob_low_bypass.value())
        self.audio.set_reverb(
            reverb.knob_damp.value(),
            reverb.knob_filter.value(),
            reverb.knob_fade.value(),
            reverb.knob_size.value(),
            reverb.knob_predelay.value(),
            reverb.knob_predelay_mix.value(),
        )

        # 🔥 FIX: Resetăm stările pentru prima afișare vizuală a tab-urilor
        self.ui_eq._eq_first_show = False
        self.ui_eq._spatial_first_show = False
        self.ui_eq._reverb_first_show = False
        self.ui_eq._tone_first_show = False
        if self.ui_eq.isVisible():
            self.ui_eq._tone_first_show = True
            self.ui_eq.animate_widget_sweep_visual(self.ui_eq.knob_bass, self.ui_eq.knob_bass.value(), delay=0)
            self.ui_eq.animate_widget_sweep_visual(self.ui_eq.knob_treble, self.ui_eq.knob_treble.value(), delay=60)
            self.ui_eq.trigger_first_show_animations(self.ui_eq.stack.currentIndex())

    def _refresh_wider_knob_tooltips(self):
        if not getattr(self, 'ui_eq', None):
            return
        try:
            spatial = getattr(self.ui_eq, 'page_spatial', None)
            if not spatial:
                return

            available, reason = self.audio.get_wider_availability()
            if available:
                tip_stereo = "Stereo Expand (Wider VST)"
                tip_low = "Low Bypass (Wider VST)"
            else:
                tip_stereo = f"Stereo Expand inactive: {reason}"
                tip_low = f"Low Bypass inactive: {reason}"

            stereo_knob = spatial.knob_stereo
            low_knob = spatial.knob_low_bypass

            for widget, tip in (
                (stereo_knob, tip_stereo),
                (stereo_knob.knob, tip_stereo),
                (stereo_knob.lbl_title, tip_stereo),
                (stereo_knob.lbl_value, tip_stereo),
                (low_knob, tip_low),
                (low_knob.knob, tip_low),
                (low_knob.lbl_title, tip_low),
                (low_knob.lbl_value, tip_low),
            ):
                try:
                    widget.setToolTip(tip)
                except:
                    pass
        except:
            pass

    def open_wider_editor_window(self):
        if os.name != 'nt':
            return self.audio.open_wider_ui_debug()

        popup = getattr(self, '_wider_editor_popup', None)
        host = getattr(self, '_wider_editor_host', None)

        if popup is None:
            popup = QDialog(self)
            popup.setWindowFlag(Qt.WindowType.Window, True)
            popup.setWindowTitle("Wider")
            popup.resize(760, 520)
            popup.setMinimumSize(480, 320)

            layout = QVBoxLayout(popup)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            host = QWidget(popup)
            host.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
            host.setObjectName("widerEditorHost")
            host.setStyleSheet("background-color: #101010;")
            layout.addWidget(host, 1)

            hint = QLabel("Loading Wider...")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet("padding: 8px; color: #BBBBBB; background-color: #101010;")
            layout.addWidget(hint)

            def clear_popup_refs():
                self._wider_editor_popup = None
                self._wider_editor_host = None

            popup.finished.connect(lambda _result: clear_popup_refs())

            self._wider_editor_popup = popup
            self._wider_editor_host = host

        popup.show()
        popup.raise_()
        popup.activateWindow()

        def embed_editor():
            current_popup = getattr(self, '_wider_editor_popup', None)
            current_host = getattr(self, '_wider_editor_host', None)
            if not current_popup or not current_host:
                return

            ok = self.audio.open_wider_ui_debug(host_hwnd=int(current_host.winId()), prefer_popup=False)
            print(f"DEBUG: Wider popup host open -> {ok}")
            if not ok:
                current_popup.close()

        QTimer.singleShot(0, embed_editor)
        return True

    # --- NAVIGARE ---
    def on_tab_changed(self, index):
        self.nav_controller.on_tab_changed(index)

    # --- LOGICA TEME & DEBUG ---
    def apply_theme(self, theme_name):
        self.last_used_theme = theme_name
        stylesheet = themes.get_stylesheet(theme_name)
        self.setStyleSheet(stylesheet)
        
        colors = themes.THEME_PALETTES.get(theme_name, themes.THEME_PALETTES["Dark"])
        self.navbar.update_theme(theme_name)
        
        content_icon_color = colors.get("ICON_COLOR", "#CCCCCC")

        self.ui_player.update_theme_colors(colors, content_icon_color)
        if hasattr(self.ui_playlist, 'update_theme_colors'):
            self.ui_playlist.update_theme_colors(colors)
        if getattr(self, 'ui_eq', None) and hasattr(self.ui_eq, 'update_theme_colors'):
            self.ui_eq.update_theme_colors(colors)
            
        self.bg_manager.update_background()

    def change_theme_user(self, theme_name):
        self.last_used_theme = theme_name
        if getattr(self, 'ui_settings', None) and self.ui_settings.btn_debug.isChecked():
            self.ui_settings.btn_debug.setChecked(False) 
        else:
            self.apply_theme(theme_name)

    def toggle_debug_mode(self, active):
        self._debug_hover_inspector.set_enabled(active)
        if active:
            if debug_theme:
                print("🪲 DEBUG MODE: ON")
                self.setStyleSheet(debug_theme.get_debug_stylesheet())
            else:
                print("⚠️ EROARE: Fișierul 'debug_theme.py' lipsește!")
        else:
            print("🪲 DEBUG MODE: OFF")
            self.apply_theme(self.last_used_theme)

    def set_app_zoom(self, factor):
        if getattr(self, '_applying_zoom', False):
            self._pending_app_zoom = factor
            return

        try:
            factor = max(0.5, min(2.0, float(factor)))
        except (TypeError, ValueError):
            return

        self._applying_zoom = True
        base_size = 10.0
        try:
            new_font = QApplication.font()
            new_font.setPointSizeF(base_size * factor)
            QApplication.setFont(new_font)

            if hasattr(self, 'navbar') and hasattr(self.navbar, 'apply_zoom'):
                self.navbar.apply_zoom(factor)
            
            if getattr(self, 'ui_player', None):
                self.ui_player.set_zoom_factor(factor)

            if getattr(self, 'ui_playlist', None):
                self.ui_playlist.set_zoom_factor(factor)

            if getattr(self, 'ui_eq', None):
                self.ui_eq.set_zoom_factor(factor)

            if getattr(self, 'ui_settings', None):
                self.ui_settings.set_zoom_factor(factor)
        finally:
            self._applying_zoom = False

        pending = getattr(self, '_pending_app_zoom', None)
        self._pending_app_zoom = None
        if pending is not None:
            try:
                pending_float = float(pending)
            except (TypeError, ValueError):
                pending_float = None
            if pending_float is not None and abs(pending_float - factor) > 0.001:
                QTimer.singleShot(0, lambda value=pending_float: self.set_app_zoom(value))

    # --- HANDLERS PENTRU EFECTE / EQ (Apelate din EventsCoordinator) ---
    def on_master_dsp_toggled(self, checked):
        self.audio.set_master_dsp(checked)

    def on_limiter_toggled(self, checked):
        self.audio.set_limiter(checked)

    def on_spatial_toggled(self, checked):
        self.spatial_on = checked
        if not getattr(self, 'ui_eq', None): return
        if checked:
            spatial = self.ui_eq.page_spatial
            self.audio.set_tempo(spatial.knob_tempo.value())
            self.audio.set_balance(spatial.knob_balance.value())
            self.audio.set_stereo_expand(spatial.knob_stereo.value())
            self.audio.set_stereo_low_bypass(spatial.knob_low_bypass.value())
        else:
            self.audio.set_tempo(1.0)
            self.audio.set_balance(50.0)
            self.audio.set_stereo_expand(0.0)
            self.audio.set_stereo_low_bypass(0.0)

    def on_reverb_toggled(self, checked):
        self.reverb_on = checked
        if not getattr(self, 'ui_eq', None): return
        if checked:
            reverb = self.ui_eq.page_reverb
            self.audio.set_reverb(
                reverb.knob_damp.value(),
                reverb.knob_filter.value(),
                reverb.knob_fade.value(),
                reverb.knob_size.value(),
                reverb.knob_predelay.value(),
                reverb.knob_predelay_mix.value(),
            )
        else:
            self.audio.set_reverb(0, 0, 0, 0, 0, 0)

    def on_tone_toggled(self, checked):
        self.knobs_on = checked
        self.force_refresh_knobs()

    def on_eq_bands_toggled(self, checked):
        self.eq_bands_on = checked
        self.force_refresh_eq()

    def apply_master_ui_state(self):
        """ Reaplică valorile efectelor atunci când se încarcă o nouă melodie """
        self.force_refresh_eq()
        self.force_refresh_knobs()
        self.on_spatial_toggled(self.spatial_on)
        self.on_reverb_toggled(self.reverb_on)

    def update_parametric(self, band, freq, gain, bandwidth=2.5):
        actual_gain = float(gain) if self.knobs_on else 0.0
        self.audio.set_parametric_eq(band, freq, actual_gain, bandwidth)

    def update_graphic_eq(self, index, value):
        if hasattr(self.ui_eq, 'freqs_float') and index < len(self.ui_eq.freqs_float):
            freq = self.ui_eq.freqs_float[index]
            actual_gain = float(value) if self.eq_bands_on else 0.0
            self.audio.set_parametric_eq(index + 2, freq, actual_gain)

    def force_refresh_knobs(self):
        if not getattr(self, 'ui_eq', None):
            return
        # Use audio engine's knob handlers so behaviour is consistent
        try:
            if not self.knobs_on:
                # Tone OFF: anulăm complet boost-urile Bass/Treble
                self.audio.set_bass_knob(0)
                self.audio.set_treble_knob(0)
            else:
                self.audio.set_bass_knob(self.ui_eq.knob_bass.value())
                self.audio.set_treble_knob(self.ui_eq.knob_treble.value())
        except:
            pass

    def force_refresh_eq(self):
        if not getattr(self, 'ui_eq', None):
            return
        for i, slider in enumerate(self.ui_eq.sliders):
            self.update_graphic_eq(i, slider.value() / 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'bg_manager'):
            self.bg_manager.handle_resize()

    def closeEvent(self, event):
        if getattr(self, 'ui_eq', None):
            self.ui_eq.force_restore_true_values_for_save()
        if hasattr(self, 'playback'):
            self.playback.flush_statistics()
        if not self._skip_settings_save_once:
            # 🔥 Salvăm totul folosind noul Manager (inclusiv EQ)
            self.session.save_session()

        if hasattr(self, 'discord_presence'):
            self.discord_presence.shutdown()

        if hasattr(self, 'os_integration'):
            self.os_integration.shutdown()

        self.audio.free()
        event.accept()

    def _apply_vst_debug_settings(self):
        try:
            open_on_start = self.settings.value("debug_vst_ui_on_start", False, type=bool)
            self.audio.configure_vst_debug(open_on_start=open_on_start, open_wider=True)
        except:
            pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.playback.toggle_play_ui() 
        else:
            super().keyPressEvent(event) 

if __name__ == "__main__":
    app = QApplication(sys.argv)

    def _handle_sigint(*_args):
        app.quit()

    signal.signal(signal.SIGINT, _handle_sigint)
    sigint_timer = QTimer()
    sigint_timer.setInterval(250)
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start()
    
    # 🔥 ICONIȚA ÎN DOCK (Mac) - Trebuie setată aici pe QApplication
    icon_path = resource_path(os.path.join('icons', 'Logo.icns'))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        
    window = MainApp()
    window.show()
    sys.exit(app.exec())
