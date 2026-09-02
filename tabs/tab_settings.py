import os
import platform
import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QGroupBox, QFormLayout, QPushButton, QSizePolicy, QScrollArea, QFrame,
                             QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QMenu, QStackedWidget, QGraphicsOpacityEffect)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings, QSize, QPropertyAnimation, QEasingCurve, QTimer
from PyQt6.QtGui import QIcon, QColor
import core.themes as themes
from Eq.knobs import AudioKnob
from core.utils import IconHelper, get_cache_root, get_settings_path
from playlist.playlist_scanner import PlaylistScanner

class SettingsTab(QWidget):
    theme_changed = pyqtSignal(str) 
    debug_toggled = pyqtSignal(bool) # 🔥 SEMNAL NOU
    eq_bands_changed = pyqtSignal(int) # Semnal pentru schimbarea nr. de benzi
    zoom_changed = pyqtSignal(float) # Semnal pentru Zoom
    setting_changed = pyqtSignal(str, object) # key, value
    open_wider_ui_requested = pyqtSignal()
    reset_limiter_debug_requested = pyqtSignal()
    reset_effects_debug_requested = pyqtSignal()
    reset_all_settings_debug_requested = pyqtSignal()
    statistics_refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        settings_path = get_settings_path()
        self.settings = QSettings(settings_path, QSettings.Format.IniFormat)
        self._current_theme_name = str(self.settings.value("theme", "Dark", type=str) or "Dark")
        self._settings_controls = {}
        self._settings_defaults = {}
        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")
        self._settings_fade_out_anim = None
        self._settings_fade_in_anim = None
        self._settings_fade_widgets = []
        self._dashboard_cards = []
        self._zoom_factor = 1.0
        self._pending_zoom_factor = 1.0
        self._zoom_emit_timer = QTimer(self)
        self._zoom_emit_timer.setSingleShot(True)
        self._zoom_emit_timer.setInterval(60)
        self._zoom_emit_timer.timeout.connect(self._emit_pending_zoom)
        self.init_ui()

    def _collect_library_versions(self):
        """ Citeste versiunile bibliotecilor folosite, cu fallback daca una
        lipseste sau nu isi expune versiunea. """
        versions = {
            "qt": "?", "pyqt": "?", "mutagen": "?",
            "pillow": "?", "pypresence": "?", "sqlite": "?",
        }
        try:
            from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
            versions["qt"] = QT_VERSION_STR
            versions["pyqt"] = PYQT_VERSION_STR
        except Exception:
            pass
        try:
            import mutagen
            versions["mutagen"] = mutagen.version_string
        except Exception:
            pass
        try:
            import PIL
            versions["pillow"] = PIL.__version__
        except Exception:
            pass
        try:
            import pypresence
            versions["pypresence"] = getattr(pypresence, "__version__", "instalat")
        except Exception:
            versions["pypresence"] = "neinstalat"
        try:
            import sqlite3
            versions["sqlite"] = sqlite3.sqlite_version
        except Exception:
            pass
        return versions

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.settings_stack = QStackedWidget()
        root_layout.addWidget(self.settings_stack)

        dashboard_page = QWidget()
        dashboard_scroll = QScrollArea()
        dashboard_scroll.setWidgetResizable(True)
        dashboard_scroll.setFrameShape(QFrame.Shape.NoFrame)
        dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        dashboard_host = QWidget()
        dashboard_scroll.setWidget(dashboard_host)
        dashboard_layout = QVBoxLayout(dashboard_host)
        self.dashboard_layout = dashboard_layout
        dashboard_layout.setContentsMargins(20, 20, 20, 20)
        dashboard_layout.setSpacing(10)
        dashboard_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        dashboard_page_layout = QVBoxLayout(dashboard_page)
        dashboard_page_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_page_layout.addWidget(dashboard_scroll)

        self.lbl_dashboard_title = QLabel("Setări")
        self.lbl_dashboard_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dashboard_layout.addWidget(self.lbl_dashboard_title)

        # --- 1. GRUP ASPECT ---
        group_app = QGroupBox("Aspect și Personalizare")
        app_layout = QVBoxLayout()
        app_layout.setSpacing(10)
        
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(list(themes.THEME_PALETTES.keys())) 
        if self._current_theme_name in themes.THEME_PALETTES:
            self.combo_theme.setCurrentText(self._current_theme_name)
        self.combo_theme.currentTextChanged.connect(self.on_theme_change)
        self.combo_theme.setMinimumHeight(32)
        self.combo_theme.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_theme.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self.lbl_theme = QLabel("🎨 Temă Interfață:")
        self.lbl_theme.setStyleSheet("font-weight: bold;")
        
        # Knob Zoom (stil similar Bass/Treble)
        self.knob_zoom = AudioKnob("ZOOM", 0.5, 2.0, step=0.02, orientation='horizontal', format_str="{:.2f}x")
        self.knob_zoom.setValue(1.0)
        self.knob_zoom.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.knob_zoom.value_changed.connect(self.on_zoom_change)
        
        # Knob Densitate FFT
        self.knob_fft = AudioKnob("FFT BARS", 10, 128, step=1.0, orientation='horizontal', format_str="{:.0f}")
        self.knob_fft.setValue(int(self.settings.value("fft_bars", 42, type=int)))
        self.knob_fft.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.knob_fft.value_changed.connect(lambda v: self._save_setting_value("fft_bars", int(round(v))))

        self.knob_animation_speed = AudioKnob("ANIM SPEED", 120, 900, step=10.0, orientation='horizontal', format_str="{:.0f} ms")
        self.knob_animation_speed.setValue(float(self.settings.value("animation_speed_ms", 350, type=int)))
        self.knob_animation_speed.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.knob_animation_speed.value_changed.connect(self.on_animation_speed_change)

        self.group_playlist_overscroll = QGroupBox("Playlist Rubber Band")
        overscroll_layout = QVBoxLayout()
        overscroll_layout.setSpacing(8)

        self.chk_playlist_overscroll = QCheckBox("Activează elasticitatea la capetele playlistului")
        self.chk_playlist_overscroll.setChecked(self.settings.value("playlist_overscroll_enabled", True, type=bool))
        self.chk_playlist_overscroll.toggled.connect(lambda checked: self._save_setting_value("playlist_overscroll_enabled", bool(checked)))

        self.knob_playlist_overscroll_max = AudioKnob("PULL", 20, 140, step=2.0, orientation='horizontal', format_str="{:.0f} px")
        self.knob_playlist_overscroll_max.setValue(float(self.settings.value("playlist_overscroll_max_px", 52, type=int)))
        self.knob_playlist_overscroll_max.value_changed.connect(lambda v: self._save_setting_value("playlist_overscroll_max_px", int(round(v))))

        self.knob_playlist_overscroll_global = AudioKnob("CONTENT", 0.0, 1.0, step=0.02, orientation='horizontal', format_str="{:.2f}")
        self.knob_playlist_overscroll_global.setValue(float(self.settings.value("playlist_overscroll_global_strength", 0.32, type=float)))
        self.knob_playlist_overscroll_global.value_changed.connect(lambda v: self._save_setting_value("playlist_overscroll_global_strength", float(v)))

        self.knob_playlist_overscroll_spread = AudioKnob("SPREAD", 0.0, 1.2, step=0.02, orientation='horizontal', format_str="{:.2f}")
        self.knob_playlist_overscroll_spread.setValue(float(self.settings.value("playlist_overscroll_spread_strength", 0.52, type=float)))
        self.knob_playlist_overscroll_spread.value_changed.connect(lambda v: self._save_setting_value("playlist_overscroll_spread_strength", float(v)))

        self.knob_playlist_overscroll_falloff = AudioKnob("RANGE", 0.18, 0.85, step=0.01, orientation='horizontal', format_str="{:.2f}")
        self.knob_playlist_overscroll_falloff.setValue(float(self.settings.value("playlist_overscroll_falloff_ratio", 0.50, type=float)))
        self.knob_playlist_overscroll_falloff.value_changed.connect(lambda v: self._save_setting_value("playlist_overscroll_falloff_ratio", float(v)))

        self.knob_playlist_overscroll_return = AudioKnob("RETURN", 120, 900, step=10.0, orientation='horizontal', format_str="{:.0f} ms")
        self.knob_playlist_overscroll_return.setValue(float(self.settings.value("playlist_overscroll_return_ms", 620, type=int)))
        self.knob_playlist_overscroll_return.value_changed.connect(lambda v: self._save_setting_value("playlist_overscroll_return_ms", int(round(v))))

        self.lbl_playlist_overscroll_max = QLabel("Tragere maximă:")
        self.lbl_playlist_overscroll_global = QLabel("Mișcare conținut:")
        self.lbl_playlist_overscroll_spread = QLabel("Separare rânduri:")
        self.lbl_playlist_overscroll_falloff = QLabel("Distanță undă:")
        self.lbl_playlist_overscroll_return = QLabel("Revenire:")
        for label in (
            self.lbl_playlist_overscroll_max,
            self.lbl_playlist_overscroll_global,
            self.lbl_playlist_overscroll_spread,
            self.lbl_playlist_overscroll_falloff,
            self.lbl_playlist_overscroll_return,
        ):
            label.setStyleSheet("font-weight: bold;")

        overscroll_layout.addWidget(self.chk_playlist_overscroll)
        for label, knob in (
            (self.lbl_playlist_overscroll_max, self.knob_playlist_overscroll_max),
            (self.lbl_playlist_overscroll_global, self.knob_playlist_overscroll_global),
            (self.lbl_playlist_overscroll_spread, self.knob_playlist_overscroll_spread),
            (self.lbl_playlist_overscroll_falloff, self.knob_playlist_overscroll_falloff),
            (self.lbl_playlist_overscroll_return, self.knob_playlist_overscroll_return),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(knob, 1)
            overscroll_layout.addLayout(row)

        self.group_playlist_overscroll.setLayout(overscroll_layout)

        row_theme = QHBoxLayout()
        row_theme.setSpacing(10)
        row_theme.addWidget(self.lbl_theme, 0, Qt.AlignmentFlag.AlignVCenter)
        row_theme.addWidget(self.combo_theme, 0, Qt.AlignmentFlag.AlignVCenter)
        row_theme.addStretch(1)

        self.lbl_zoom = QLabel("🔍 Zoom Aplicație:")
        self.lbl_zoom.setStyleSheet("font-weight: bold;")
        row_zoom = QHBoxLayout()
        row_zoom.setSpacing(10)
        row_zoom.addWidget(self.lbl_zoom, 0, Qt.AlignmentFlag.AlignVCenter)
        row_zoom.addWidget(self.knob_zoom, 1)

        self.lbl_fft = QLabel("📊 Densitate FFT:")
        self.lbl_fft.setStyleSheet("font-weight: bold;")
        row_fft = QHBoxLayout()
        row_fft.setSpacing(10)
        row_fft.addWidget(self.lbl_fft, 0, Qt.AlignmentFlag.AlignVCenter)
        row_fft.addWidget(self.knob_fft, 1)

        self.lbl_animation_speed = QLabel("🎬 Viteză Animații:")
        self.lbl_animation_speed.setStyleSheet("font-weight: bold;")
        row_animation_speed = QHBoxLayout()
        row_animation_speed.setSpacing(10)
        row_animation_speed.addWidget(self.lbl_animation_speed, 0, Qt.AlignmentFlag.AlignVCenter)
        row_animation_speed.addWidget(self.knob_animation_speed, 1)

        # Aliniem etichetele la aceeasi latime (cea mai lunga dintre ele), ca
        # toate knob-urile sa porneasca din acelasi loc pe orizontala - altfel
        # fiecare rand are propriul QHBoxLayout, iar un text mai lung ("Viteza
        # Animatii:") impinge knob-ul lui mai la dreapta decat celelalte.
        aspect_labels = (self.lbl_theme, self.lbl_zoom, self.lbl_fft, self.lbl_animation_speed)
        label_width = max(lbl.sizeHint().width() for lbl in aspect_labels)
        for lbl in aspect_labels:
            lbl.setMinimumWidth(label_width)

        app_layout.addLayout(row_theme)
        app_layout.addLayout(row_zoom)
        app_layout.addLayout(row_fft)
        app_layout.addLayout(row_animation_speed)
        app_layout.addWidget(self.group_playlist_overscroll)
        group_app.setLayout(app_layout)
        group_app.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        group_app.setMinimumHeight(group_app.sizeHint().height())
        self.group_app = group_app

        # --- 1.5 GRUP AUDIO (NOU) ---
        group_audio = QGroupBox("Audio & EQ")
        audio_layout = QFormLayout()
        
        # Knob EQ Bands
        self.knob_bands = AudioKnob("BANDS", 5, 31, step=1.0, orientation='horizontal', format_str="{:.0f} Bands")
        self.knob_bands.setValue(10)
        self.knob_bands.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        self.knob_bands.value_changed.connect(self.on_bands_change)

        self.knob_bass_range = AudioKnob("BASS RANGE", 0, 500, step=1.0, orientation='horizontal', format_str="{:.0f} Hz")
        self.knob_bass_range.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.knob_bass_range.setValue(float(self.settings.value("bass_shelf_freq", 90, type=int)))
        self.knob_bass_range.value_changed.connect(self.on_bass_range_change)

        self.knob_treble_range = AudioKnob("TREBLE RANGE", 2000, 20000, step=100.0, orientation='horizontal', format_str="{:.0f} Hz")
        self.knob_treble_range.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.knob_treble_range.setValue(float(self.settings.value("treble_shelf_freq", 10000, type=int)))
        self.knob_treble_range.value_changed.connect(self.on_treble_range_change)
        
        audio_layout.addRow("Număr Benzi EQ:", self.knob_bands)
        audio_layout.addRow("Bass Interval (0..X):", self.knob_bass_range)
        audio_layout.addRow("Treble Interval (X..20000):", self.knob_treble_range)

        # Toate knob-urile din Settings au deja o eticheta externa (randul din
        # care fac parte), deci ascundem titlul propriu al knob-ului (ex.
        # "ZOOM", "ANIM SPEED") si pastram doar valoarea - evita repetarea
        # textului si taierea titlurilor lungi intr-un container ingust.
        for knob in (
            self.knob_zoom, self.knob_fft, self.knob_animation_speed,
            self.knob_playlist_overscroll_max, self.knob_playlist_overscroll_global,
            self.knob_playlist_overscroll_spread, self.knob_playlist_overscroll_falloff,
            self.knob_playlist_overscroll_return,
            self.knob_bands, self.knob_bass_range, self.knob_treble_range,
        ):
            knob.set_title_visible(False)


        group_audio.setLayout(audio_layout)
        self.group_audio = group_audio

        group_discord = QGroupBox("Discord Rich Presence")
        discord_layout = QFormLayout()

        self.chk_discord_presence = QCheckBox("Enable Discord Presence")
        self.chk_discord_presence.setChecked(self.settings.value("discord_presence_enabled", False, type=bool))
        self.chk_discord_presence.toggled.connect(lambda checked: self._save_setting_value("discord_presence_enabled", bool(checked)))

        self.input_discord_client_id = QLineEdit(str(self.settings.value("discord_client_id", "", type=str) or ""))
        self.input_discord_client_id.setPlaceholderText("Discord application client ID")
        self.input_discord_client_id.editingFinished.connect(lambda: self._save_setting_value("discord_client_id", self.input_discord_client_id.text().strip()))

        self.combo_discord_activity_type = QComboBox()
        self.combo_discord_activity_type.addItem("Playing", "playing")
        self.combo_discord_activity_type.addItem("Listening", "listening")
        saved_activity_type = str(self.settings.value("discord_activity_type", "listening", type=str) or "listening").strip().lower()
        activity_index = max(0, self.combo_discord_activity_type.findData(saved_activity_type))
        self.combo_discord_activity_type.setCurrentIndex(activity_index)
        self.combo_discord_activity_type.currentIndexChanged.connect(
            lambda _=0: self._save_setting_value(
                "discord_activity_type",
                str(self.combo_discord_activity_type.currentData() or "listening").strip().lower(),
            )
        )

        self.combo_discord_pause_behavior = QComboBox()
        self.combo_discord_pause_behavior.addItem("Show paused position", "show_paused_position")
        self.combo_discord_pause_behavior.addItem("Keep running timer", "keep_running_timer")
        self.combo_discord_pause_behavior.addItem("Hide presence on pause", "hide_presence")
        saved_pause_behavior = str(self.settings.value("discord_pause_behavior", "show_paused_position", type=str) or "show_paused_position").strip().lower()
        pause_behavior_index = max(0, self.combo_discord_pause_behavior.findData(saved_pause_behavior))
        self.combo_discord_pause_behavior.setCurrentIndex(pause_behavior_index)
        self.combo_discord_pause_behavior.currentIndexChanged.connect(
            lambda _=0: self._save_setting_value(
                "discord_pause_behavior",
                str(self.combo_discord_pause_behavior.currentData() or "show_paused_position").strip().lower(),
            )
        )

        self.input_discord_large_image = QLineEdit(str(self.settings.value("discord_large_image_key", "", type=str) or ""))
        self.input_discord_large_image.setPlaceholderText("Fallback asset key or direct image URL")
        self.input_discord_large_image.editingFinished.connect(lambda: self._save_setting_value("discord_large_image_key", self.input_discord_large_image.text().strip()))

        self.chk_discord_online_artwork = QCheckBox("Auto search online artwork from track metadata")
        self.chk_discord_online_artwork.setChecked(self.settings.value("discord_online_artwork_enabled", True, type=bool))
        self.chk_discord_online_artwork.toggled.connect(lambda checked: self._save_setting_value("discord_online_artwork_enabled", bool(checked)))

        self.chk_discord_small_status_icons = QCheckBox("Show play/pause status icon in small Discord slot")
        self.chk_discord_small_status_icons.setChecked(self.settings.value("discord_small_status_icons_enabled", True, type=bool))
        self.chk_discord_small_status_icons.toggled.connect(lambda checked: self._save_setting_value("discord_small_status_icons_enabled", bool(checked)))

        self.input_discord_play_small_image = QLineEdit(str(self.settings.value("discord_play_small_image_key", "play", type=str) or ""))
        self.input_discord_play_small_image.setPlaceholderText("Play small image key or URL")
        self.input_discord_play_small_image.editingFinished.connect(lambda: self._save_setting_value("discord_play_small_image_key", self.input_discord_play_small_image.text().strip()))

        self.input_discord_pause_small_image = QLineEdit(str(self.settings.value("discord_pause_small_image_key", "pause", type=str) or ""))
        self.input_discord_pause_small_image.setPlaceholderText("Pause small image key or URL")
        self.input_discord_pause_small_image.editingFinished.connect(lambda: self._save_setting_value("discord_pause_small_image_key", self.input_discord_pause_small_image.text().strip()))

        self.lbl_discord_note = QLabel("Poți folosi asset keys sau URL-uri directe pentru imaginea mare și iconița mică. Artwork-ul mare poate fi găsit automat online, Activity Type schimbă felul în care Discord afișează cardul, iar Pause Behavior controlează ce se întâmplă când oprești piesa.")
        self.lbl_discord_note.setWordWrap(True)
        self.lbl_discord_note.setStyleSheet("font-size: 11px;")

        discord_layout.addRow(self.chk_discord_presence)
        discord_layout.addRow("Client ID:", self.input_discord_client_id)
        discord_layout.addRow("Activity Type:", self.combo_discord_activity_type)
        discord_layout.addRow("Pause Behavior:", self.combo_discord_pause_behavior)
        discord_layout.addRow("Online Artwork:", self.chk_discord_online_artwork)
        discord_layout.addRow("Fallback Key / URL:", self.input_discord_large_image)
        discord_layout.addRow("Small Status Icon:", self.chk_discord_small_status_icons)
        discord_layout.addRow("Play Icon Key / URL:", self.input_discord_play_small_image)
        discord_layout.addRow("Pause Icon Key / URL:", self.input_discord_pause_small_image)
        discord_layout.addRow(self.lbl_discord_note)
        group_discord.setLayout(discord_layout)
        self.group_discord = group_discord

        self.group_statistics = QGroupBox("Statistici")
        statistics_layout = QVBoxLayout()
        statistics_layout.setSpacing(12)

        self.lbl_statistics_note = QLabel("Aici vezi ce asculți cel mai mult: timp total, skip-uri, favorite și alte statistici utile. Skip tracking și listened time încep să se adune automat de acum înainte.")
        self.lbl_statistics_note.setWordWrap(True)
        self.lbl_statistics_note.setStyleSheet("font-size: 11px;")
        statistics_layout.addWidget(self.lbl_statistics_note)

        self.statistics_cards = {}
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(12)
        stats_grid.setVerticalSpacing(12)

        stat_specs = [
            ("overall_time", "Ore Ascultate Overall", "#4DB6AC"),
            ("total_plays", "Total Play-uri", "#7986CB"),
            ("unique_tracks", "Piese Unice Ascultate", "#BA68C8"),
            ("total_skips", "Total Skip-uri", "#FF8A65"),
            ("most_played", "Cea Mai Ascultată", "#81C784"),
            ("most_skipped", "Cea Mai Skip-uită", "#E57373"),
            ("favorite_artist", "Artist Favorit", "#64B5F6"),
            ("favorite_album", "Album Favorit", "#FFD54F"),
            ("avg_completion", "Media de Completion", "#90A4AE"),
            ("last_played", "Ultima Piesă Pornită", "#A1887F"),
        ]

        for index, (key, title, accent) in enumerate(stat_specs):
            card = self._create_statistics_card(title, accent)
            self.statistics_cards[key] = card
            row = index // 2
            column = index % 2
            stats_grid.addWidget(card["frame"], row, column)

        statistics_layout.addLayout(stats_grid)
        self.group_statistics.setLayout(statistics_layout)

        self.group_info = QGroupBox("Info")
        info_layout = QVBoxLayout()
        info_layout.setSpacing(10)

        self.lbl_info_summary = QLabel(
            "STAVA Player — player audio pentru biblioteci muzicale locale. Redare prin "
            "motorul nativ BASS, equalizer parametric cu benzi configurabile, efecte "
            "spațiale și reverb, waveform, versuri sincronizate (LRC), Discord Rich "
            "Presence și integrare cu tastele media ale sistemului."
        )
        self.lbl_info_summary.setWordWrap(True)

        info_grid = QFormLayout()
        info_grid.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        info_grid.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        info_grid.setHorizontalSpacing(16)
        info_grid.setVerticalSpacing(8)

        # Versiunile bibliotecilor sunt citite dinamic, cu fallback daca lipsesc.
        versions = self._collect_library_versions()

        self._info_label_widgets = []
        self._info_value_widgets = []

        def add_info_row(label_text, value_text, wrap=False):
            lbl = QLabel(label_text)
            val = QLabel(str(value_text))
            val.setWordWrap(wrap)
            self._info_label_widgets.append(lbl)
            self._info_value_widgets.append(val)
            info_grid.addRow(lbl, val)
            return val

        audio_ext = ", ".join(ext.lstrip(".") for ext in PlaylistScanner.AUDIO_EXT)
        cue_ext = ", ".join(ext.lstrip(".") for ext in PlaylistScanner.CUE_EXT)

        add_info_row("Versiune:", "1.0")
        add_info_row("Runtime:", f"Python {platform.python_version()} • {platform.system()} {platform.release()}")
        add_info_row("Interfață:", f"PyQt {versions['pyqt']} (Qt {versions['qt']})")
        add_info_row("Bibliotecă audio:", "BASS (un4seen) — bass.dll / libbass")
        add_info_row("Extensii audio:", "BASS_FX (tempo, reverb) • BASSFLAC (FLAC) • BASS_VST (plugin-uri VST)")
        add_info_row("Plugin VST:", "Wider — extindere stereo")
        add_info_row("Formate redate:", f"{audio_ext} (+ playlist-uri {cue_ext})")
        add_info_row("Metadata / tag-uri:", f"Mutagen {versions['mutagen']}")
        add_info_row("Procesare imagini:", f"Pillow {versions['pillow']}")
        add_info_row("Discord:", f"pypresence {versions['pypresence']}")
        add_info_row("Bază de date:", f"SQLite {versions['sqlite']} (bibliotecă, statistici, cozi)")

        self.lbl_info_licenses_title = QLabel("Licențe și atribuiri")
        self.lbl_info_licenses = QLabel(
            "• BASS, BASS_FX, BASSFLAC, BASS_VST — © un4seen developments. Gratuite pentru "
            "uz necomercial; distribuția comercială necesită licență de la un4seen.\n"
            "• Qt / PyQt6 — Qt sub LGPL v3, PyQt6 sub GPL v3 sau licență comercială Riverbank.\n"
            "• Mutagen — GPL v2 sau ulterior.\n"
            "• Pillow — licență MIT-CMU (HPND).\n"
            "• pypresence — licență MIT.\n"
            "• Wider (VST) — proprietatea autorului său; inclus doar ca plugin extern.\n\n"
            "Coperțile, versurile și metadatele aparțin deținătorilor lor de drepturi. "
            "Pentru termenii exacți, consultă licența fiecărui proiect în parte."
        )
        self.lbl_info_licenses.setWordWrap(True)

        info_layout.addWidget(self.lbl_info_summary)
        info_layout.addLayout(info_grid)
        info_layout.addWidget(self.lbl_info_licenses_title)
        info_layout.addWidget(self.lbl_info_licenses)
        self.group_info.setLayout(info_layout)

        # --- Box separat pentru locatii/configurare (conturat cu alb) ---
        self.group_info_paths = QGroupBox("Locații și configurare")
        paths_layout = QVBoxLayout()
        paths_grid = QFormLayout()
        paths_grid.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        paths_grid.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        paths_grid.setHorizontalSpacing(16)
        paths_grid.setVerticalSpacing(8)

        def add_path_row(label_text, value_text):
            lbl = QLabel(label_text)
            val = QLabel(str(value_text))
            val.setWordWrap(True)
            self._info_label_widgets.append(lbl)
            self._info_value_widgets.append(val)
            paths_grid.addRow(lbl, val)

        add_path_row("Teme disponibile:", ", ".join(list(themes.THEME_PALETTES.keys())))
        add_path_row("Settings file:", get_settings_path())
        add_path_row("Cache folder:", get_cache_root())
        add_path_row("Project root:", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        add_path_row("Executabil:", sys.executable)

        paths_layout.addLayout(paths_grid)
        self.group_info_paths.setLayout(paths_layout)

        # --- 1.7 GRUP SETTINGS.INI (NOU) ---
        self.group_ini = QGroupBox("Settings.ini (Advanced)")
        ini_layout = QVBoxLayout()
        self.cache_root_path = get_cache_root()

        cache_row = QHBoxLayout()
        cache_row.setSpacing(10)
        self.lbl_cache_root = QLabel("Cache folder:")
        self.lbl_cache_root.setStyleSheet("font-weight: bold;")
        self.input_cache_root = QLineEdit(self.cache_root_path)
        self.input_cache_root.setReadOnly(True)
        self.input_cache_root.setCursorPosition(0)
        self.input_cache_root.setToolTip(self.cache_root_path)
        cache_row.addWidget(self.lbl_cache_root)
        cache_row.addWidget(self.input_cache_root, 1)
        ini_layout.addLayout(cache_row)

        cache_exists = os.path.isdir(self.cache_root_path)
        cache_status = "Exists already." if cache_exists else "Will be created automatically when cache data is first written."
        self.lbl_cache_status = QLabel(cache_status)
        self.lbl_cache_status.setStyleSheet("font-size: 11px;")
        self.lbl_cache_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.lbl_cache_status.setWordWrap(True)
        ini_layout.addWidget(self.lbl_cache_status)

        self.form_ini = QFormLayout()
        self.form_ini.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.form_ini.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.form_ini.setHorizontalSpacing(16)
        self.form_ini.setVerticalSpacing(8)
        ini_layout.addLayout(self.form_ini)
        self.lbl_ini_status = QLabel("Tip: click dreapta pe o setare pentru reset sau folosește butonul Restore.")
        self.lbl_ini_status.setStyleSheet("font-size: 11px;")
        self.lbl_ini_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        ini_layout.addWidget(self.lbl_ini_status)
        self.group_ini.setLayout(ini_layout)
        self._build_ini_settings_form()

        # --- 🔥 2. GRUP DEVELOPER (NOU) ---
        group_dev = QGroupBox("Developer Tools")
        dev_layout = QVBoxLayout()

        self.btn_debug = QPushButton("Debug Mode (Show Layers)")
        self.btn_debug.setCheckable(True) # Face butonul să rămână apăsat
        self.btn_debug.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_debug.setFixedWidth(self.btn_debug.sizeHint().width() + 8)
        self.btn_debug.setStyleSheet("""
            QPushButton:checked { background-color: #FF4444; color: white; border: 2px solid red; }
        """)
        self.btn_debug.toggled.connect(self.on_debug_toggle)

        self.btn_open_wider_ui = QPushButton("Open Wider UI (Debug)")
        self.btn_open_wider_ui.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_open_wider_ui.setFixedWidth(self.btn_open_wider_ui.sizeHint().width() + 8)
        self.btn_open_wider_ui.clicked.connect(self.on_open_wider_ui)

        self.btn_reset_limiter_debug = QPushButton("Reset Limiter State")
        self.btn_reset_limiter_debug.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_reset_limiter_debug.setFixedWidth(self.btn_reset_limiter_debug.sizeHint().width() + 8)
        self.btn_reset_limiter_debug.clicked.connect(self.on_reset_limiter_debug)

        self.btn_reset_effects_debug = QPushButton("Reset DSP Effects")
        self.btn_reset_effects_debug.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_reset_effects_debug.setFixedWidth(self.btn_reset_effects_debug.sizeHint().width() + 8)
        self.btn_reset_effects_debug.clicked.connect(self.on_reset_effects_debug)

        self.btn_reset_all_settings_debug = QPushButton("Reset ALL")
        self.btn_reset_all_settings_debug.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_reset_all_settings_debug.setFixedWidth(self.btn_reset_all_settings_debug.sizeHint().width() + 8)
        self.btn_reset_all_settings_debug.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #e74c3c;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        self.btn_reset_all_settings_debug.clicked.connect(self.on_reset_all_settings_debug)

        self.btn_open_ini_page = QPushButton("Settings.ini (editor)")
        self.btn_open_ini_page.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_open_ini_page.setFixedWidth(self.btn_open_ini_page.sizeHint().width() + 8)
        self.btn_open_ini_page.clicked.connect(lambda: self._open_settings_section("ini"))

        dev_layout.addWidget(self.btn_debug)
        dev_layout.addWidget(self.btn_open_ini_page)
        dev_layout.addWidget(self.btn_open_wider_ui)
        dev_layout.addWidget(self.btn_reset_limiter_debug)
        dev_layout.addWidget(self.btn_reset_effects_debug)
        dev_layout.addWidget(self.btn_reset_all_settings_debug)
        group_dev.setLayout(dev_layout)
        self.group_dev = group_dev

        button_specs = [
            ("Aspect și Personalizare", "Temă, zoom, FFT și viteza animațiilor.", "settings-app-dashboard.svg", "app"),
            ("Audio & EQ", "Benzi EQ, bass și treble range.", "settings-audio-dashboard.svg", "audio"),
            ("Statistici", "Timp ascultat, piese favorite, skip-uri și alte stats.", "settings-stats-dashboard.svg", "stats"),
            ("Advanced", "Settings.ini, Discord Rich Presence și Developer Tools.", "settings-advanced-dashboard.svg", "advanced"),
            ("Info", "Versiune, runtime, locații și detalii generale despre aplicație.", "settings-info-dashboard.svg", "info"),
        ]

        self.settings_dashboard_buttons = []
        for title, subtitle, icon_name, section_key in button_specs:
            button = self._create_settings_dashboard_button(title, subtitle, icon_name)
            button.clicked.connect(lambda _=False, key=section_key: self._open_settings_section(key))
            self.settings_dashboard_buttons.append(button)
            dashboard_layout.addWidget(button)

        dashboard_layout.addStretch()

        self.detail_page = QWidget()
        detail_layout = QVBoxLayout(self.detail_page)
        detail_layout.setContentsMargins(20, 20, 20, 20)
        detail_layout.setSpacing(12)

        top_row = QHBoxLayout()
        self.btn_back_to_dashboard = QPushButton("")
        self.btn_back_to_dashboard.setFixedHeight(34)
        self.btn_back_to_dashboard.setFixedWidth(40)
        self.btn_back_to_dashboard.setCursor(Qt.CursorShape.PointingHandCursor)
        back_icon_path = os.path.join(self._icons_dir, "playlist", "arrow-down-solid-full.svg")
        back_icon = IconHelper.get_colored_icon(back_icon_path, "white", size=16)
        if not back_icon.isNull():
            self.btn_back_to_dashboard.setIcon(back_icon)
            self.btn_back_to_dashboard.setIconSize(QSize(16, 16))
        self.btn_back_to_dashboard.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.5);
                color: white;
                border-radius: 17px;
                border: 1px solid rgba(255,255,255,0.12);
                padding: 0;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #000000; }
        """)
        self.btn_back_to_dashboard.clicked.connect(self._go_to_settings_dashboard)

        self.lbl_section_title = QLabel("Settings")

        top_row.addWidget(self.btn_back_to_dashboard, 0)
        top_row.addWidget(self.lbl_section_title, 1)
        top_row.addStretch()
        detail_layout.addLayout(top_row)

        self.section_stack = QStackedWidget()
        detail_layout.addWidget(self.section_stack, 1)

        self.section_pages = {
            "app": self._create_settings_section_page([self.group_app]),
            "audio": self._create_settings_section_page([self.group_audio]),
            "stats": self._create_settings_section_page([self.group_statistics]),
            "info": self._create_settings_section_page([self.group_info, self.group_info_paths]),
            "advanced": self._create_settings_section_page([self.group_discord, self.group_dev]),
            "ini": self._create_settings_section_page([self.group_ini]),
        }
        self.section_titles = {
            "app": "Aspect și Personalizare",
            "audio": "Audio & EQ",
            "stats": "Statistici",
            "info": "Info",
            "advanced": "Advanced",
            "ini": "Settings.ini",
        }

        for key in ("app", "audio", "stats", "info", "advanced", "ini"):
            self.section_stack.addWidget(self.section_pages[key])

        self.settings_stack.addWidget(dashboard_page)
        self.settings_stack.addWidget(self.detail_page)
        self.settings_stack.setCurrentWidget(dashboard_page)
        self._apply_settings_theme(self._current_theme_name)

    def _create_settings_dashboard_button(self, title, subtitle, icon_name):
        button = QPushButton()
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(76)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setProperty("subtitleText", subtitle)
        button.setText("")

        content_layout = QHBoxLayout(button)
        content_layout.setContentsMargins(12, 8, 14, 8)
        content_layout.setSpacing(12)

        icon_holder = QLabel()
        icon_holder.setFixedSize(42, 42)
        icon_path = os.path.join(self._icons_dir, icon_name)
        icon = QIcon(icon_path)
        pixmap = icon.pixmap(QSize(34, 34))
        if not pixmap.isNull():
            icon_holder.setPixmap(pixmap)
        icon_holder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        body_label = QLabel()
        body_label.setContentsMargins(0, 0, 0, 0)
        body_label.setWordWrap(True)
        body_label.setTextFormat(Qt.TextFormat.RichText)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        text_layout.addWidget(body_label)

        content_layout.addWidget(icon_holder, 0, Qt.AlignmentFlag.AlignVCenter)
        content_layout.addLayout(text_layout, 1)
        self._dashboard_cards.append({
            "button": button,
            "body": body_label,
            "title_text": title,
            "subtitle_text": subtitle,
            "icon_holder": icon_holder,
            "icon_name": icon_name,
        })
        return button

    def _create_settings_section_page(self, groups):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page_layout.addWidget(scroll)

        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for group in groups:
            layout.addWidget(group)
        layout.addStretch()

        scroll.setWidget(host)
        return page

    def _open_settings_section(self, section_key):
        if section_key not in self.section_pages:
            return
        self._current_section_key = section_key
        def switch():
            self.lbl_section_title.setText(self.section_titles.get(section_key, "Settings"))
            self.section_stack.setCurrentWidget(self.section_pages[section_key])
            self.settings_stack.setCurrentWidget(self.detail_page)
            if section_key == "stats":
                self.statistics_refresh_requested.emit()

        self._animate_settings_stack_switch(switch, target_widget=self.detail_page)

    def _create_statistics_card(self, title, accent_color):
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        title_label = QLabel(title)
        value_label = QLabel("-")
        value_label.setWordWrap(True)
        subtitle_label = QLabel("Se încarcă...")
        subtitle_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(subtitle_label)
        return {"frame": frame, "title": title_label, "value": value_label, "subtitle": subtitle_label, "accent": accent_color}

    def _theme_rgba(self, color_hex, alpha):
        color = QColor(color_hex)
        color.setAlphaF(max(0.0, min(1.0, alpha)))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alphaF()})"

    def _apply_settings_theme(self, theme_name):
        self._current_theme_name = theme_name if theme_name in themes.THEME_PALETTES else "Dark"
        z = max(0.6, float(getattr(self, "_zoom_factor", 1.0)))
        colors = themes.THEME_PALETTES.get(self._current_theme_name, themes.THEME_PALETTES["Dark"])
        fg = colors.get("FG", "#FFFFFF")
        secondary = colors.get("TEXT_SECONDARY", "#AAAAAA")
        border = colors.get("BORDER", "#333333")
        menu_bg = colors.get("MENU_BG", "#252525")
        danger = "#c0392b"
        danger_hover = "#e74c3c"
        danger_pressed = "#a93226"

        title_size = max(18, int(24 * z))
        note_size = max(10, int(11 * z))
        dashboard_card_h = max(64, int(76 * z))
        dashboard_radius = dashboard_card_h // 2
        dashboard_icon_box = max(36, int(42 * z))
        dashboard_icon_size = max(28, int(34 * z))
        dashboard_title_size = max(13, int(16 * z))
        dashboard_subtitle_size = max(10, int(11 * z))
        back_h = max(30, int(34 * z))
        back_w = max(36, int(40 * z))
        back_radius = back_h // 2
        back_icon_size = max(14, int(16 * z))
        stat_title_size = max(10, int(12 * z))
        stat_value_size = max(14, int(18 * z))

        if hasattr(self, 'dashboard_layout'):
            self.dashboard_layout.setContentsMargins(int(20 * z), int(20 * z), int(20 * z), int(20 * z))
            self.dashboard_layout.setSpacing(max(10, int(12 * z)))
        if hasattr(self, 'detail_page') and self.detail_page.layout():
            self.detail_page.layout().setContentsMargins(int(20 * z), int(20 * z), int(20 * z), int(20 * z))
            self.detail_page.layout().setSpacing(max(10, int(12 * z)))

        self.lbl_dashboard_title.setStyleSheet(f"font-size: {title_size}px; font-weight: bold; margin-bottom: 10px; color: {fg};")
        self.lbl_section_title.setStyleSheet(f"font-size: {title_size}px; font-weight: bold; color: {fg};")
        self.lbl_theme.setStyleSheet(f"font-weight: bold; color: {fg};")
        self.lbl_zoom.setStyleSheet(f"font-weight: bold; color: {fg};")
        self.lbl_fft.setStyleSheet(f"font-weight: bold; color: {fg};")
        self.lbl_animation_speed.setStyleSheet(f"font-weight: bold; color: {fg};")
        if hasattr(self, 'group_playlist_overscroll'):
            self.group_playlist_overscroll.setStyleSheet(f"QGroupBox {{ color: {fg}; font-weight: bold; }}")
            self.chk_playlist_overscroll.setStyleSheet(f"color: {fg}; font-weight: 600;")
            for label in (
                self.lbl_playlist_overscroll_max,
                self.lbl_playlist_overscroll_global,
                self.lbl_playlist_overscroll_spread,
                self.lbl_playlist_overscroll_falloff,
                self.lbl_playlist_overscroll_return,
            ):
                label.setStyleSheet(f"font-weight: bold; color: {fg};")
        self.lbl_cache_root.setStyleSheet(f"font-weight: bold; color: {fg};")
        self.lbl_discord_note.setStyleSheet(f"font-size: {note_size}px; color: {self._theme_rgba(secondary, 0.92)};")
        self.lbl_statistics_note.setStyleSheet(f"font-size: {note_size}px; color: {self._theme_rgba(secondary, 0.92)};")
        self.lbl_info_summary.setStyleSheet(f"font-size: {max(11, int(13 * z))}px; color: {fg};")
        self.lbl_cache_status.setStyleSheet(f"font-size: {note_size}px; color: {self._theme_rgba(secondary, 0.92)};")
        self.lbl_ini_status.setStyleSheet(f"font-size: {note_size}px; color: {self._theme_rgba(secondary, 0.92)};")

        # Listele sunt construite la crearea sectiunii Info (add_info_row), ca
        # sa nu trebuiasca actualizate manual aici la fiecare rand nou.
        for label in getattr(self, '_info_label_widgets', []):
            label.setStyleSheet(f"font-weight: bold; color: {fg};")
        for value in getattr(self, '_info_value_widgets', []):
            value.setStyleSheet(f"color: {self._theme_rgba(secondary, 0.96)};")

        if hasattr(self, 'lbl_info_licenses_title'):
            self.lbl_info_licenses_title.setStyleSheet(
                f"font-weight: bold; font-size: {max(12, int(14 * z))}px; color: {fg}; margin-top: 6px;"
            )
        if hasattr(self, 'lbl_info_licenses'):
            self.lbl_info_licenses.setStyleSheet(
                f"font-size: {note_size}px; color: {self._theme_rgba(secondary, 0.92)};"
            )

        if hasattr(self, 'group_info_paths'):
            # Box separat, conturat cu alb, ca sa se distinga de restul sectiunii.
            self.group_info_paths.setStyleSheet(
                "QGroupBox {"
                " color: #FFFFFF;"
                " font-weight: bold;"
                " border: 1px solid rgba(255, 255, 255, 0.85);"
                " border-radius: 8px;"
                " margin-top: 1.2em;"
                " padding: 10px;"
                "}"
                "QGroupBox::title {"
                " subcontrol-origin: margin;"
                " subcontrol-position: top left;"
                " left: 10px;"
                " padding: 0 4px;"
                "}"
            )

        back_icon_path = os.path.join(self._icons_dir, "playlist", "arrow-down-solid-full.svg")
        back_icon = IconHelper.get_colored_icon(back_icon_path, fg, size=back_icon_size)
        if not back_icon.isNull():
            self.btn_back_to_dashboard.setIcon(back_icon)
            self.btn_back_to_dashboard.setIconSize(QSize(back_icon_size, back_icon_size))

        self.btn_back_to_dashboard.setFixedHeight(back_h)
        self.btn_back_to_dashboard.setFixedWidth(back_w)

        self.btn_back_to_dashboard.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._theme_rgba(menu_bg, 0.72)};
                color: {fg};
                border-radius: {back_radius}px;
                border: 1px solid {self._theme_rgba(border, 0.42)};
                padding: 0;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {self._theme_rgba(menu_bg, 0.9)}; }}
        """)

        self.btn_debug.setStyleSheet(f"""
            QPushButton:checked {{ background-color: {danger}; color: {fg}; border: 2px solid {danger_hover}; }}
        """)
        self.btn_reset_all_settings_debug.setStyleSheet(f"""
            QPushButton {{
                background-color: {danger};
                color: {fg};
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background-color: {danger_hover};
            }}
            QPushButton:pressed {{
                background-color: {danger_pressed};
            }}
        """)

        hover_bg = self._theme_rgba(fg, 0.04)
        pressed_bg = self._theme_rgba(fg, 0.08)
        for card in self._dashboard_cards:
            card["button"].setFixedHeight(dashboard_card_h)
            if card["button"].layout():
                card["button"].layout().setContentsMargins(max(10, int(12 * z)), max(6, int(8 * z)), max(12, int(14 * z)), max(6, int(8 * z)))
                card["button"].layout().setSpacing(max(10, int(12 * z)))
            card["icon_holder"].setFixedSize(dashboard_icon_box, dashboard_icon_box)
            pixmap = QIcon(os.path.join(self._icons_dir, card["icon_name"])).pixmap(QSize(dashboard_icon_size, dashboard_icon_size))
            if not pixmap.isNull():
                card["icon_holder"].setPixmap(pixmap)
            card["button"].setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    text-align: left;
                    padding: 8px 12px;
                    border: none;
                    border-radius: {dashboard_radius}px;
                    color: {fg};
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {hover_bg};
                    border: 1px solid {self._theme_rgba(border, 0.14)};
                }}
                QPushButton:pressed {{
                    background-color: {pressed_bg};
                }}
            """)
            card["body"].setText(
                f"<div style='margin:0; padding:0; line-height:0.95;'>"
                f"<div style='margin:0; padding:0; font-size:{dashboard_title_size}px; font-weight:700; color:{fg};'>{card['title_text']}</div>"
                f"<div style='margin:0; padding:0; font-size:{dashboard_subtitle_size}px; font-weight:600; color:{self._theme_rgba(secondary, 0.92)};'>{card['subtitle_text']}</div>"
                f"</div>"
            )

        for card in self.statistics_cards.values():
            if card["frame"].layout():
                card["frame"].layout().setContentsMargins(max(12, int(16 * z)), max(10, int(14 * z)), max(12, int(16 * z)), max(10, int(14 * z)))
                card["frame"].layout().setSpacing(max(4, int(4 * z)))
            card["frame"].setStyleSheet(
                f"""
                QFrame {{
                    background-color: {self._theme_rgba(fg, 0.04)};
                    border: 1px solid {self._theme_rgba(border, 0.18)};
                    border-radius: 20px;
                }}
                """
            )
            card["title"].setStyleSheet(f"font-size: {stat_title_size}px; font-weight: bold; color: {card['accent']};")
            card["value"].setStyleSheet(f"font-size: {stat_value_size}px; font-weight: bold; color: {fg};")
            card["subtitle"].setStyleSheet(f"font-size: {note_size}px; color: {self._theme_rgba(secondary, 0.92)};")

    def set_statistics_data(self, summary):
        summary = summary or {}

        self._set_statistics_card("overall_time", self._format_listen_time(summary.get("total_listened_seconds", 0.0)), "Timp total real acumulat din ascultare.")
        self._set_statistics_card("total_plays", str(int(summary.get("total_plays", 0) or 0)), "De câte ori ai pornit piese din bibliotecă.")
        self._set_statistics_card("unique_tracks", str(int(summary.get("unique_played_tracks", 0) or 0)), f"Din {int(summary.get('total_tracks', 0) or 0)} piese indexate.")
        self._set_statistics_card("total_skips", str(int(summary.get("total_skips", 0) or 0)), "Skip-urile se contorizează când sari înainte de final.")

        top_played = summary.get("top_played") or {}
        self._set_statistics_card(
            "most_played",
            top_played.get("title") or "Nu există încă",
            self._format_track_meta(top_played, count_key="play_count", suffix="play-uri"),
        )

        top_skipped = summary.get("top_skipped") or {}
        self._set_statistics_card(
            "most_skipped",
            top_skipped.get("title") or "Nu există încă",
            self._format_track_meta(top_skipped, count_key="skip_count", suffix="skip-uri"),
        )

        top_artist = summary.get("top_artist") or {}
        artist_value = top_artist.get("artist") or "Nu există încă"
        artist_subtitle = self._format_artist_album_meta(top_artist)
        self._set_statistics_card("favorite_artist", artist_value, artist_subtitle)

        top_album = summary.get("top_album") or {}
        album_value = top_album.get("album") or "Nu există încă"
        album_subtitle = self._format_artist_album_meta(top_album, artist_key="artist")
        self._set_statistics_card("favorite_album", album_value, album_subtitle)

        completion_rate = float(summary.get("avg_completion_rate", 0.0) or 0.0)
        self._set_statistics_card("avg_completion", f"{completion_rate * 100:.0f}%", "Procent mediu ascultat din piesele pe care le-ai pornit.")

        last_played = summary.get("last_played") or {}
        self._set_statistics_card(
            "last_played",
            last_played.get("title") or "Nu există încă",
            self._format_track_meta(last_played, count_key=None, suffix=None),
        )

    def _set_statistics_card(self, key, value, subtitle):
        card = self.statistics_cards.get(key)
        if not card:
            return
        card["value"].setText(str(value or "-"))
        card["subtitle"].setText(str(subtitle or ""))

    def _format_listen_time(self, seconds):
        try:
            seconds = int(float(seconds or 0.0))
        except Exception:
            seconds = 0
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours <= 0:
            return f"{minutes} min"
        return f"{hours}h {minutes:02d}m"

    def _format_track_meta(self, row, count_key=None, suffix=None):
        if not row:
            return ""
        parts = []
        artist = row.get("artist")
        album = row.get("album")
        if artist:
            parts.append(str(artist))
        if album:
            parts.append(str(album))
        if count_key and row.get(count_key) is not None:
            parts.append(f"{int(row.get(count_key) or 0)} {suffix}")
        return " • ".join(parts)

    def _format_artist_album_meta(self, row, artist_key="artist"):
        if not row:
            return ""
        parts = []
        artist = row.get(artist_key)
        if artist:
            parts.append(str(artist))
        total_plays = row.get("total_plays")
        if total_plays is not None:
            parts.append(f"{int(total_plays or 0)} play-uri")
        listened_seconds = row.get("total_listened_seconds")
        if listened_seconds:
            parts.append(self._format_listen_time(listened_seconds))
        return " • ".join(parts)

    def _go_to_settings_dashboard(self):
        # Pagina Settings.ini se deschide din Advanced (Developer Tools), deci
        # butonul inapoi duce acolo, nu direct in dashboard.
        if getattr(self, '_current_section_key', None) == "ini":
            self._open_settings_section("advanced")
            return
        self._current_section_key = None
        self._animate_settings_stack_switch(lambda: self.settings_stack.setCurrentIndex(0), target_widget=self.settings_stack.widget(0))

    def _cleanup_settings_fade_effects(self):
        for widget in self._settings_fade_widgets:
            try:
                if widget:
                    widget.setGraphicsEffect(None)
            except Exception:
                pass
        self._settings_fade_widgets.clear()

    def _stop_settings_fade_transition(self):
        for animation in (self._settings_fade_out_anim, self._settings_fade_in_anim):
            if animation and animation.state() == QPropertyAnimation.State.Running:
                animation.stop()
        self._settings_fade_out_anim = None
        self._settings_fade_in_anim = None
        self._cleanup_settings_fade_effects()

    def _animate_settings_stack_switch(self, update_func, target_widget=None, total_duration=240):
        current_widget = self.settings_stack.currentWidget()
        if not current_widget:
            update_func()
            return

        self._stop_settings_fade_transition()

        out_effect = QGraphicsOpacityEffect(current_widget)
        out_effect.setOpacity(1.0)
        current_widget.setGraphicsEffect(out_effect)
        self._settings_fade_widgets.append(current_widget)

        fade_out = QPropertyAnimation(out_effect, b"opacity", self)
        fade_out.setDuration(total_duration // 2)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.OutQuad)

        def after_fade_out():
            try:
                current_widget.setGraphicsEffect(None)
            except Exception:
                pass
            if current_widget in self._settings_fade_widgets:
                self._settings_fade_widgets.remove(current_widget)

            update_func()

            actual_target = target_widget or self.settings_stack.currentWidget()
            if not actual_target:
                self._stop_settings_fade_transition()
                return

            in_effect = QGraphicsOpacityEffect(actual_target)
            in_effect.setOpacity(0.0)
            actual_target.setGraphicsEffect(in_effect)
            self._settings_fade_widgets.append(actual_target)

            fade_in = QPropertyAnimation(in_effect, b"opacity", self)
            fade_in.setDuration(total_duration // 2)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.InQuad)

            def after_fade_in():
                self._stop_settings_fade_transition()

            self._settings_fade_in_anim = fade_in
            fade_in.finished.connect(after_fade_in)
            fade_in.start()

        self._settings_fade_out_anim = fade_out
        fade_out.finished.connect(after_fade_out)
        fade_out.start()

    def on_theme_change(self, theme_name):
        self._apply_settings_theme(theme_name)
        self.theme_changed.emit(theme_name)

    def on_bands_change(self, value):
        bands = int(round(value))
        self.eq_bands_changed.emit(bands)

    def on_bass_range_change(self, value):
        freq = int(round(value))
        self._save_setting_value("bass_shelf_freq", freq)

    def on_treble_range_change(self, value):
        freq = int(round(value))
        self._save_setting_value("treble_shelf_freq", freq)

    def on_debug_toggle(self, checked):
        if checked:
            self.btn_debug.setText("⚠️ DEBUG: ON")
        else:
            self.btn_debug.setText("DEBUG: OFF")
        self.btn_debug.setFixedWidth(self.btn_debug.sizeHint().width() + 8)
        self.debug_toggled.emit(checked)

    def on_zoom_change(self, value):
        try:
            self._pending_zoom_factor = max(0.5, min(2.0, float(value)))
        except (TypeError, ValueError):
            return
        self._zoom_emit_timer.start()

    def _emit_pending_zoom(self):
        self.zoom_changed.emit(float(self._pending_zoom_factor))

    def on_animation_speed_change(self, value):
        self._save_setting_value("animation_speed_ms", int(round(value)))

    def on_open_wider_ui(self):
        self.open_wider_ui_requested.emit()

    def on_reset_limiter_debug(self):
        self.reset_limiter_debug_requested.emit()

    def on_reset_effects_debug(self):
        self.reset_effects_debug_requested.emit()

    def on_reset_all_settings_debug(self):
        self.reset_all_settings_debug_requested.emit()

    def _known_settings_schema(self):
        return {
            "artwork_scan_depth": {"type": "int", "min": 0, "max": 5, "default": 2},
            "ui_refresh_ms": {"type": "int", "min": 0, "max": 50, "default": 0},
            "volume": {"type": "int", "min": 0, "max": 100, "default": 40},
            "shuffle": {"type": "int", "min": 0, "max": 1, "default": 0},
            "repeat": {"type": "int", "min": 0, "max": 2, "default": 0},
            "eq_master": {"type": "bool", "default": False},
            "eq_tone": {"type": "bool", "default": True},
            "bass_shelf_freq": {"type": "int", "min": 0, "max": 500, "default": 90},
            "treble_shelf_freq": {"type": "int", "min": 2000, "max": 20000, "default": 10000},
            "eq_limit": {"type": "bool", "default": False},
            "debug_vst_ui_on_start": {"type": "bool", "default": False},
            "library_root": {"type": "str", "default": ""},
            "theme": {"type": "enum", "values": list(themes.THEME_PALETTES.keys()), "default": "Dark"},
            "fft_bars": {"type": "int", "min": 10, "max": 128, "default": 42},
            "animation_speed_ms": {"type": "int", "min": 120, "max": 900, "default": 350},
            "playlist_overscroll_enabled": {"type": "bool", "default": True},
            "playlist_overscroll_max_px": {"type": "int", "min": 20, "max": 140, "default": 52},
            "playlist_overscroll_return_ms": {"type": "int", "min": 120, "max": 900, "default": 620},
            "playlist_overscroll_global_strength": {"type": "float", "min": 0.0, "max": 1.0, "default": 0.32},
            "playlist_overscroll_spread_strength": {"type": "float", "min": 0.0, "max": 1.2, "default": 0.52},
            "playlist_overscroll_falloff_ratio": {"type": "float", "min": 0.18, "max": 0.85, "default": 0.50},
            "discord_presence_enabled": {"type": "bool", "default": False},
            "discord_client_id": {"type": "str", "default": ""},
            "discord_activity_type": {"type": "enum", "values": ["playing", "listening"], "default": "listening"},
            "discord_pause_behavior": {"type": "enum", "values": ["show_paused_position", "keep_running_timer", "hide_presence"], "default": "show_paused_position"},
            "discord_online_artwork_enabled": {"type": "bool", "default": True},
            "discord_large_image_key": {"type": "str", "default": ""},
            "discord_small_status_icons_enabled": {"type": "bool", "default": True},
            "discord_play_small_image_key": {"type": "str", "default": "play"},
            "discord_pause_small_image_key": {"type": "str", "default": "pause"},
        }

    def _build_ini_settings_form(self):
        schema = self._known_settings_schema()
        all_keys = set(self.settings.allKeys())
        all_keys.update(schema.keys())
        
        # Ascundem proprietățile interne să nu fie corupte de text box-uri
        hidden_keys = {
            "queue", "shuffled_queue", "geometry", "last_song", "last_position",
            "eq_bands_values", "eq_preamp", "eq_bass_knob", "eq_treble_knob", "fft_bars", "animation_speed_ms",
            "playlist_overscroll_enabled", "playlist_overscroll_max_px", "playlist_overscroll_return_ms",
            "playlist_overscroll_global_strength", "playlist_overscroll_spread_strength", "playlist_overscroll_falloff_ratio",
            "discord_presence_enabled", "discord_client_id", "discord_activity_type", "discord_pause_behavior", "discord_online_artwork_enabled", "discord_large_image_key",
            "discord_small_status_icons_enabled", "discord_play_small_image_key", "discord_pause_small_image_key"
        }

        for key in sorted(all_keys):
            if key in hidden_keys:
                continue
            field = QLabel(key)
            field.setStyleSheet("font-weight: 600;")
            control = self._create_setting_control(key, schema.get(key))

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(control, 1)

            default_value = schema.get(key, {}).get("default") if schema.get(key) else None
            self._settings_defaults[key] = default_value

            btn_restore = QPushButton("Restore")
            btn_restore.setFixedHeight(28)
            btn_restore.setEnabled(default_value is not None)
            btn_restore.setToolTip("Resetează la valoarea default")
            btn_restore.clicked.connect(lambda _=False, k=key: self._restore_setting(k))
            row_layout.addWidget(btn_restore)

            self._attach_right_click_reset(control, key)

            self.form_ini.addRow(field, row_widget)

    def _create_setting_control(self, key, meta):
        if meta and meta.get("type") == "bool":
            value = self.settings.value(key, False, type=bool)
            w = QCheckBox()
            w.setChecked(bool(value))
            w.toggled.connect(lambda checked, k=key: self._save_setting_value(k, bool(checked)))
            self._settings_controls[key] = {"type": "bool", "control": w}
            return w

        if meta and meta.get("type") == "int":
            minimum = meta.get("min", -999999)
            maximum = meta.get("max", 999999)
            value = self.settings.value(key, 0, type=int)
            w = QSpinBox()
            w.setRange(int(minimum), int(maximum))
            w.setValue(int(value))
            w.valueChanged.connect(lambda v, k=key: self._save_setting_value(k, int(v)))
            self._settings_controls[key] = {"type": "int", "control": w}
            return w

        if meta and meta.get("type") == "float":
            minimum = float(meta.get("min", -999999.0))
            maximum = float(meta.get("max", 999999.0))
            value = self.settings.value(key, 0.0, type=float)
            w = QDoubleSpinBox()
            w.setDecimals(3)
            w.setSingleStep(0.1)
            w.setRange(minimum, maximum)
            w.setValue(float(value))
            w.valueChanged.connect(lambda v, k=key: self._save_setting_value(k, float(v)))
            self._settings_controls[key] = {"type": "float", "control": w}
            return w

        if meta and meta.get("type") == "enum":
            values = meta.get("values", [])
            current = str(self.settings.value(key, values[0] if values else "", type=str))
            w = QComboBox()
            w.addItems(values)
            if current in values:
                w.setCurrentText(current)
            w.currentTextChanged.connect(lambda txt, k=key: self._save_setting_value(k, txt))
            self._settings_controls[key] = {"type": "enum", "control": w}
            return w

        raw = self.settings.value(key, "")
        if isinstance(raw, (list, tuple)):
            raw = ", ".join([str(x) for x in raw])
        elif isinstance(raw, (bytes, bytearray)):
            raw = str(raw)
        elif raw is None:
            raw = ""

        w = QLineEdit(str(raw))
        w.setPlaceholderText("string value")
        w.editingFinished.connect(lambda k=key, le=w: self._save_setting_value(k, le.text()))
        self._settings_controls[key] = {"type": "str", "control": w}
        return w

    def _attach_right_click_reset(self, control, key):
        control.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Execută reset-ul direct la click dreapta, fără a mai afișa meniul
        control.customContextMenuRequested.connect(lambda pos, k=key: self._restore_setting(k))

    def _restore_setting(self, key):
        default_value = self._settings_defaults.get(key)
        if default_value is None:
            self.lbl_ini_status.setText(f"'{key}' nu are default cunoscut.")
            return

        info = self._settings_controls.get(key)
        if not info:
            return

        control = info.get("control")
        control.blockSignals(True)
        try:
            ctype = info.get("type")
            if ctype == "bool":
                control.setChecked(bool(default_value))
            elif ctype in ("int", "float"):
                control.setValue(default_value)
            elif ctype == "enum":
                control.setCurrentText(str(default_value))
            else:
                control.setText(str(default_value))
        finally:
            control.blockSignals(False)

        self._save_setting_value(key, default_value)
        self.lbl_ini_status.setText(f"'{key}' a fost resetat la default.")

    def _save_setting_value(self, key, value):
        self.settings.setValue(key, value)
        self._sync_threshold_knobs_and_controls(key, value)
        self.setting_changed.emit(key, value)

    def _sync_threshold_knobs_and_controls(self, key, value):
        if key == "bass_shelf_freq":
            try:
                v = int(value)
            except:
                return
            if hasattr(self, 'knob_bass_range'):
                self.knob_bass_range.blockSignals(True)
                self.knob_bass_range.setValue(float(v))
                self.knob_bass_range.blockSignals(False)

            info = self._settings_controls.get("bass_shelf_freq")
            if info and info.get("type") == "int":
                control = info.get("control")
                control.blockSignals(True)
                control.setValue(v)
                control.blockSignals(False)
            return

        if key == "treble_shelf_freq":
            try:
                v = int(value)
            except:
                return
            if hasattr(self, 'knob_treble_range'):
                self.knob_treble_range.blockSignals(True)
                self.knob_treble_range.setValue(float(v))
                self.knob_treble_range.blockSignals(False)

            info = self._settings_controls.get("treble_shelf_freq")
            if info and info.get("type") == "int":
                control = info.get("control")
                control.blockSignals(True)
                control.setValue(v)
                control.blockSignals(False)
            return

        if key == "animation_speed_ms":
            try:
                v = int(value)
            except:
                return
            if hasattr(self, 'knob_animation_speed'):
                self.knob_animation_speed.blockSignals(True)
                self.knob_animation_speed.setValue(float(v))
                self.knob_animation_speed.blockSignals(False)
            return

        overscroll_knobs = {
            "playlist_overscroll_max_px": ("knob_playlist_overscroll_max", int),
            "playlist_overscroll_return_ms": ("knob_playlist_overscroll_return", int),
            "playlist_overscroll_global_strength": ("knob_playlist_overscroll_global", float),
            "playlist_overscroll_spread_strength": ("knob_playlist_overscroll_spread", float),
            "playlist_overscroll_falloff_ratio": ("knob_playlist_overscroll_falloff", float),
        }
        if key == "playlist_overscroll_enabled":
            if hasattr(self, 'chk_playlist_overscroll'):
                self.chk_playlist_overscroll.blockSignals(True)
                self.chk_playlist_overscroll.setChecked(bool(value))
                self.chk_playlist_overscroll.blockSignals(False)
            return
        if key in overscroll_knobs:
            attr, caster = overscroll_knobs[key]
            try:
                v = caster(value)
            except:
                return
            knob = getattr(self, attr, None)
            if knob:
                knob.blockSignals(True)
                knob.setValue(float(v))
                knob.blockSignals(False)
            return

        if key == "discord_presence_enabled":
            checked = bool(value)
            if hasattr(self, 'chk_discord_presence'):
                self.chk_discord_presence.blockSignals(True)
                self.chk_discord_presence.setChecked(checked)
                self.chk_discord_presence.blockSignals(False)
            return

        if key == "discord_client_id":
            text = str(value or "")
            if hasattr(self, 'input_discord_client_id'):
                self.input_discord_client_id.blockSignals(True)
                self.input_discord_client_id.setText(text)
                self.input_discord_client_id.blockSignals(False)
            return

        if key == "discord_activity_type":
            text = str(value or "listening").strip().lower()
            if hasattr(self, 'combo_discord_activity_type'):
                index = self.combo_discord_activity_type.findData(text)
                if index < 0:
                    index = self.combo_discord_activity_type.findData("listening")
                self.combo_discord_activity_type.blockSignals(True)
                self.combo_discord_activity_type.setCurrentIndex(max(0, index))
                self.combo_discord_activity_type.blockSignals(False)
            return

        if key == "discord_pause_behavior":
            text = str(value or "show_paused_position").strip().lower()
            if hasattr(self, 'combo_discord_pause_behavior'):
                index = self.combo_discord_pause_behavior.findData(text)
                if index < 0:
                    index = self.combo_discord_pause_behavior.findData("show_paused_position")
                self.combo_discord_pause_behavior.blockSignals(True)
                self.combo_discord_pause_behavior.setCurrentIndex(max(0, index))
                self.combo_discord_pause_behavior.blockSignals(False)
            return

        if key == "discord_online_artwork_enabled":
            checked = bool(value)
            if hasattr(self, 'chk_discord_online_artwork'):
                self.chk_discord_online_artwork.blockSignals(True)
                self.chk_discord_online_artwork.setChecked(checked)
                self.chk_discord_online_artwork.blockSignals(False)
            return

        if key == "discord_small_status_icons_enabled":
            checked = bool(value)
            if hasattr(self, 'chk_discord_small_status_icons'):
                self.chk_discord_small_status_icons.blockSignals(True)
                self.chk_discord_small_status_icons.setChecked(checked)
                self.chk_discord_small_status_icons.blockSignals(False)
            return

        if key == "discord_large_image_key":
            text = str(value or "")
            if hasattr(self, 'input_discord_large_image'):
                self.input_discord_large_image.blockSignals(True)
                self.input_discord_large_image.setText(text)
                self.input_discord_large_image.blockSignals(False)
            return

        if key == "discord_play_small_image_key":
            text = str(value or "")
            if hasattr(self, 'input_discord_play_small_image'):
                self.input_discord_play_small_image.blockSignals(True)
                self.input_discord_play_small_image.setText(text)
                self.input_discord_play_small_image.blockSignals(False)
            return

        if key == "discord_pause_small_image_key":
            text = str(value or "")
            if hasattr(self, 'input_discord_pause_small_image'):
                self.input_discord_pause_small_image.blockSignals(True)
                self.input_discord_pause_small_image.setText(text)
                self.input_discord_pause_small_image.blockSignals(False)
            return

    def set_zoom_factor(self, factor):
        z = max(0.6, float(factor))
        self._zoom_factor = z
        if hasattr(self, 'knob_bands'):
            self.knob_bands.set_zoom_factor(z)
        if hasattr(self, 'knob_bass_range'):
            self.knob_bass_range.set_zoom_factor(z)
        if hasattr(self, 'knob_treble_range'):
            self.knob_treble_range.set_zoom_factor(z)
        if hasattr(self, 'knob_fft'):
            self.knob_fft.set_zoom_factor(z)
        if hasattr(self, 'knob_animation_speed'):
            self.knob_animation_speed.set_zoom_factor(z)
        for attr in (
            'knob_playlist_overscroll_max',
            'knob_playlist_overscroll_global',
            'knob_playlist_overscroll_spread',
            'knob_playlist_overscroll_falloff',
            'knob_playlist_overscroll_return',
        ):
            knob = getattr(self, attr, None)
            if knob:
                knob.set_zoom_factor(z)
        self._apply_settings_theme(self._current_theme_name)
