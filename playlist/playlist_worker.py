from PyQt6.QtCore import QThread, pyqtSignal
from .playlist_scanner import PlaylistScanner

class LibraryScannerThread(QThread):
    progress_update = pyqtSignal(str) # Mesaj status (ex: "Scanning 50/1000...")
    progress_percent = pyqtSignal(int) # Procentaj (0-100)
    scan_finished = pyqtSignal()      # Semnal când e gata

    def __init__(self, logic, audio_engine=None, scan_root=None):
        super().__init__()
        self.logic = logic
        self.audio_engine = audio_engine # Primim engine-ul pentru waveform
        self.scan_root = scan_root
        self.is_running = True

    def run(self):
        # 1. Găsire fișiere (Rapid)
        self.progress_update.emit("Finding files...")
        self.progress_percent.emit(0)
        files = self.logic.rescan_library(self.scan_root)
        
        if not files:
            self.scan_finished.emit()
            return

        total = len(files)
        self.logic.clear_cache()
        
        # --- ETAPA 1: METADATE (Rapid) ---
        self.progress_update.emit("Step 1/3: Scanning Metadata...")
        try:
            self.logic.db.begin_transaction()
            for i, f in enumerate(files):
                if not self.is_running: break
                self.logic.scan_metadata(f)
                if i % 50 == 0: 
                    self.progress_update.emit(f"Step 1/3: Metadata ({i}/{total})")
                    percent = int((i / total) * 100)
                    self.progress_percent.emit(percent)
            self.logic.db.commit_transaction()
        except Exception as e: print(f"Meta Scan Error: {e}")

        # --- ETAPA 2: ARTWORK (Mediu) ---
        self.progress_update.emit("Step 2/3: Processing Artwork & Miniatures...")
        try:
            self.logic.db.begin_transaction()
            for i, f in enumerate(files):
                if not self.is_running: break
                self.logic.scan_artwork(f)
                if i % 20 == 0: 
                    self.progress_update.emit(f"Step 2/3: Artwork ({i}/{total})")
                    percent = int((i / total) * 100)
                    self.progress_percent.emit(percent)
            self.logic.db.commit_transaction()
        except Exception as e: print(f"Art Scan Error: {e}")

        # --- ETAPA 3: WAVEFORM (Lent) ---
        self.progress_update.emit("Step 3/3: Generating Waveforms...")
        try:
            processed_wave_sources = set()
            self.logic.db.begin_transaction()
            for i, f in enumerate(files):
                if not self.is_running: break
                source = PlaylistScanner.resolve_audio_path(f)
                if source in processed_wave_sources:
                    continue
                processed_wave_sources.add(source)
                self.logic.scan_waveform(f, self.audio_engine)
                if i % 10 == 0: 
                    self.progress_update.emit(f"Step 3/3: Waveforms ({i}/{total})")
                    percent = int((i / total) * 100)
                    self.progress_percent.emit(percent)
            
            self.logic.db.commit_transaction()
        except Exception as e:
            print(f"Scan Error: {e}")
        
        self.progress_update.emit(f"Library Ready ({total} songs)")
        self.progress_percent.emit(100)
        self.scan_finished.emit()

    def stop(self):
        self.is_running = False
