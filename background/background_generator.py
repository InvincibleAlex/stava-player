from PyQt6.QtCore import Qt, QRect, QRectF, QSize
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect

class BackgroundGenerator:
    @staticmethod
    def get_background_pixmap(target_pixmap, target_size):
        """ 
        Primește un QPixmap și returnează un QPixmap scalat și cropuit (Cover Mode)
        pentru a acoperi perfect target_size.
        """
        if not target_pixmap or target_pixmap.isNull():
            return None

        try:
            # --- TEHNICA "ABSTRACT CLOUD" ---
            # Nu lucrăm la rezoluția ecranului (prea lent și se văd detalii nedorite).
            # Lucrăm la o rezoluție fixă, mică, dar suficientă pentru culori (ex: 256px).
            
            process_h = 256
            # Calculăm lățimea necesară pentru a păstra aspect ratio-ul ferestrei țintă
            aspect = target_size.width() / target_size.height() if target_size.height() > 0 else 1
            process_w = int(process_h * aspect)
            process_size = QSize(process_w, process_h)
            
            # 1. Scalare Intermediară (Upscale de la 52px sau Downscale de la HD)
            # Folosim SmoothTransformation pentru a elimina pixelarea inițială
            scaled = target_pixmap.scaled(process_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            
            # 2. Crop Center (Tăiem excesul pentru a centra imaginea)
            x = (scaled.width() - process_w) // 2
            y = (scaled.height() - process_h) // 2
            cropped = scaled.copy(x, y, process_w, process_h)
            
            # 3. Aplicăm BLUR MASIV
            # Pe o imagine de 256px, un radius de 80 înseamnă că totul devine un gradient fin.
            return BackgroundGenerator.apply_blur(cropped, radius=80)
            
            
        except Exception as e:
            print(f"BG Generator Error: {e}")
            return None

    @staticmethod
    def apply_blur(pixmap, radius=80):
        """ Aplică un blur puternic folosind QGraphicsBlurEffect """
        if not pixmap or pixmap.isNull(): return pixmap

        scene = QGraphicsScene()
        item = QGraphicsPixmapItem(pixmap)
        
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(radius)
        # PerformanceHint e crucial pentru viteză
        blur.setBlurHints(QGraphicsBlurEffect.BlurHint.PerformanceHint)
        
        item.setGraphicsEffect(blur)
        scene.addItem(item)
        
        result = QPixmap(pixmap.size())
        result.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(result)
        # Randăm scena în pixmap
        scene.render(painter, QRectF(), QRectF(0, 0, pixmap.width(), pixmap.height()))
        painter.end()
        
        return result