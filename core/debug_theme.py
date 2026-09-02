# debug_theme.py
import platform

def get_debug_stylesheet():
    """
    Returnează un CSS care evidențiază toate containerele.
    Fiecare tip de widget are o culoare distinctă pentru a identifica layout-ul.
    """
    if platform.system() == "Darwin":
        font_family = '".AppleSystemUIFont", "Helvetica Neue", "Arial", sans-serif'
    else:
        font_family = '"Segoe UI", "Meiryo", "Noto Sans", "Noto Sans CJK JP", "Arial Unicode MS", sans-serif'

    css = """
    /* --- DEBUG MODE: EXTREME VISIBILITY --- */
    
    * {
        font-family: %FONT_FAMILY%;
        color: #000000; /* Text negru pentru contrast maxim pe culori neon */
        font-weight: bold;
    }

    QMainWindow {
        background-color: #202020;
    }

    /* 🟥 QWidget Generic - Roșu deschis */
    QWidget {
        background-color: rgba(255, 0, 0, 0.05); 
        border: 1px dashed rgba(255, 0, 0, 0.5);
    }

    /*  QFrame - Albastru (Containere logice) */
    QFrame {
        background-color: rgba(0, 0, 255, 0.1);
        border: 2px solid blue;
    }
    
    /* 🟩 QStackedWidget - Verde (Pagini) */
    QStackedWidget {
        border: 3px solid #00FF00;
        margin: 5px;
        background-color: rgba(0, 255, 0, 0.05);
    }

    /*  QLabel - Galben (Text/Spacer) */
    QLabel {
        background-color: rgba(255, 255, 0, 0.3);
        border: 1px dotted #AAAA00;
    }

    /*  QPushButton - Portocaliu */
    QPushButton {
        background-color: rgba(255, 165, 0, 0.4);
        border: 2px solid orange;
    }

    /* 🟪 QLineEdit - Mov */
    QLineEdit {
        background-color: rgba(128, 0, 128, 0.3);
        border: 2px solid purple;
    }

    /* 🟦 NavBar - Cyan */
    NavBar {
        background-color: rgba(0, 255, 255, 0.2);
        border: 3px solid cyan;
    }

    /* 🌸 PlaylistHeader - Magenta (Foarte important pentru problema ta) */
    PlaylistHeader {
        background-color: rgba(255, 0, 255, 0.2);
        border: 4px solid magenta;
        min-height: 10px; /* Să se vadă chiar dacă e gol */
    }

    /* 🟫 QListWidget - Maro */
    QListWidget {
        background-color: rgba(139, 69, 19, 0.2);
        border: 2px solid brown;
    }

    /* 🟧 QScrollArea - Portocaliu deschis (folosit la EQ) */
    QScrollArea {
        border: 2px dashed orange;
        background-color: rgba(255, 165, 0, 0.1);
    }

    /* 📦 QGroupBox - Cyan închis (folosit la Settings) */
    QGroupBox {
        border: 2px solid darkcyan;
        margin-top: 1.5em;
    }

    /* 🔽 QComboBox - Roz */
    QComboBox {
        border: 2px solid hotpink;
        background-color: rgba(255, 105, 180, 0.2);
    }
    
    /* Slider */
    QSlider::groove:horizontal {
        background: red;
        height: 10px;
    }
    QSlider::handle:horizontal {
        background: yellow;
        border: 2px solid black;
        width: 20px;
    }
    QSlider::groove:vertical {
        background: red;
        width: 10px;
    }
    QSlider::handle:vertical {
        background: yellow;
        border: 2px solid black;
        height: 20px;
    }

    /* --- PLAYER TAB SPECIFIC --- */
    
    /* PlayerTab Container - Magenta Puternic */
    PlayerTab {
        border: 5px solid #FF00FF; 
        background-color: rgba(255, 0, 255, 0.05);
    }

    /* SquareFrame (Artwork container) - Cyan Dashed */
    SquareFrame {
        border: 3px dashed #00FFFF; 
        background-color: rgba(0, 255, 255, 0.1);
    }

    /* RoundedArtLabel - Gold */
    RoundedArtLabel {
        border: 2px solid #FFD700; 
        background-color: rgba(255, 215, 0, 0.2);
    }

    /* WaveformWidget - Chartreuse (Verde Neon) */
    WaveformWidget {
        border: 2px solid #7FFF00; 
        background-color: rgba(127, 255, 0, 0.1);
    }

    /* MultiStateButton (Butoanele extra, shuffle, repeat) - OrangeRed */
    MultiStateButton {
        border: 2px solid #FF4500; 
        background-color: rgba(255, 69, 0, 0.3);
    }

    /* ClickThroughContainer (Overlay in mini mode) - Alb Dotted */
    ClickThroughContainer {
        border: 2px dotted #FFFFFF;
        background-color: rgba(255, 255, 255, 0.1);
    }

    /* --- EQ & CUSTOM WIDGETS --- */

    /* 🎛️ AudioKnob (containerul mare) - lime, contine cele doua de mai jos */
    AudioKnob {
        border: 2px dashed lime;
        background-color: rgba(0, 255, 0, 0.05);
    }

    /* 🎯 Container-ul de text/valoare al knob-ului - portocaliu */
    QWidget#AudioKnobTextContainer {
        border: 2px dotted #FF8C00;
        background-color: rgba(255, 140, 0, 0.18);
    }

    /* 🔵 KnobGraphic (cercul propriu-zis) - cyan.
       Nota: KnobGraphic isi deseneaza singur continutul (paintEvent custom),
       deci border-ul din stylesheet poate sa nu apara; conturul lui se vede
       oricum prin diferenta fata de containerul portocaliu de alaturi. */
    KnobGraphic {
        border: 2px dotted #00E5FF;
        background-color: rgba(0, 229, 255, 0.10);
    }

    /* 🎚️ EqBandSlider */
    EqBandSlider {
        border: 1px solid yellow;
        background-color: rgba(255, 255, 0, 0.1);
    }

    /* ✨ GlitterButton (Playlist Welcome) */
    GlitterButton {
        border: 3px double gold;
        background-color: rgba(255, 215, 0, 0.3);
    }

    /* 👻 TransitionOverlay - Vizibil pentru debug animații */
    TransitionOverlay {
        border: 2px dashed red;
        background-color: rgba(255, 0, 0, 0.2);
    }
    """
    return css.replace("%FONT_FAMILY%", font_family)