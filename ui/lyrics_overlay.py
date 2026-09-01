from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

class LyricsOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Fundal solid, dar va fi în spatele artwork-ului care se mișcă
        self.setStyleSheet("background-color: #1C1C1C;")
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_lyrics = QLabel("No lyrics found.")
        self.lbl_lyrics.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_lyrics.setWordWrap(True)
        self.lbl_lyrics.setStyleSheet("""
            QLabel {
                font-size: 16px;
                color: #AAAAAA;
                padding: 20px;
            }
        """)
        
        layout.addWidget(self.lbl_lyrics)