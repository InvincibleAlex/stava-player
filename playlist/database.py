import sqlite3
import os

class DatabaseManager:
    def __init__(self, cache_dir, db_name="stava_library.db"):
        self.db_path = os.path.join(cache_dir, db_name)
        self.conn = None
        self.connect()

    def connect(self):
        """ Stabilește conexiunea la SQLite """
        try:
            # check_same_thread=False permite accesul din mai multe thread-uri (UI + Scanner)
            # timeout=30.0 așteaptă până la 30 secunde dacă DB e blocată de scriere (evită erorile "Database is locked")
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            
            # Returnăm rezultatele ca dicționare (row['title']) în loc de tupluri (row[0])
            self.conn.row_factory = sqlite3.Row 
            
            # 🔥 OPTIMIZARE MAJORĂ: Write-Ahead Logging + Synchronous Normal
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA cache_size=-8000;")  # 8MB cache (negativ = KB)
            self.conn.execute("PRAGMA temp_store=MEMORY;")
            
            self.create_tables()
        except Exception as e:
            print(f"Database Connection Error: {e}")

    def create_tables(self):
        """ Crearea tabelelor pentru Foldere și Piese """
        
        # 1. Tabel FOLDERS
        # Folosim 'path' ca cheie primară pentru că este unic
        query_folders = """
        CREATE TABLE IF NOT EXISTS folders (
            path TEXT PRIMARY KEY,
            song_count INTEGER,
            total_duration REAL
        )
        """
        self.execute(query_folders)

        # 2. Tabel SONGS
        # Stocăm metadatele și calea către artwork-ul cache-uit (art_path)
        query_songs = """
        CREATE TABLE IF NOT EXISTS songs (
            path TEXT PRIMARY KEY,
            title TEXT,
            artist TEXT,
            album TEXT,
            duration REAL,
            play_count INTEGER DEFAULT 0,
            skip_count INTEGER DEFAULT 0,
            listened_seconds REAL DEFAULT 0,
            last_played REAL DEFAULT 0,
            art_path TEXT,
            art_small_path TEXT,
            lyrics TEXT,
            waveform BLOB
        )
        """
        self.execute(query_songs)
        
        # Migrare pentru tabele existente (dacă coloana lipsește)
        # Verificăm întâi dacă există coloana pentru a evita eroarea în consolă
        cursor = self.execute("PRAGMA table_info(songs)")
        if cursor:
            columns = [row['name'] for row in cursor.fetchall()]
            if 'art_small_path' not in columns:
                self.execute("ALTER TABLE songs ADD COLUMN art_small_path TEXT")
            if 'waveform' not in columns:
                self.execute("ALTER TABLE songs ADD COLUMN waveform BLOB")
            if 'lyrics' not in columns:
                self.execute("ALTER TABLE songs ADD COLUMN lyrics TEXT")
            if 'play_count' not in columns:
                self.execute("ALTER TABLE songs ADD COLUMN play_count INTEGER DEFAULT 0")
            if 'skip_count' not in columns:
                self.execute("ALTER TABLE songs ADD COLUMN skip_count INTEGER DEFAULT 0")
            if 'listened_seconds' not in columns:
                self.execute("ALTER TABLE songs ADD COLUMN listened_seconds REAL DEFAULT 0")
            if 'last_played' not in columns:
                self.execute("ALTER TABLE songs ADD COLUMN last_played REAL DEFAULT 0")
        
        # 🔥 OPTIMIZARE: Index-uri pentru căutare rapidă
        self.execute("CREATE INDEX IF NOT EXISTS idx_artist ON songs(artist);")
        self.execute("CREATE INDEX IF NOT EXISTS idx_album ON songs(album);")
        self.execute("CREATE INDEX IF NOT EXISTS idx_title ON songs(title);")
        self.execute("CREATE INDEX IF NOT EXISTS idx_play_count ON songs(play_count DESC);")
        self.execute("CREATE INDEX IF NOT EXISTS idx_skip_count ON songs(skip_count DESC);")
        self.execute("CREATE INDEX IF NOT EXISTS idx_last_played ON songs(last_played DESC);")

    def execute(self, query, params=()):
        """ Execută o comandă (INSERT, UPDATE, DELETE, CREATE) """
        try:
            with self.conn: # Auto-commit
                cursor = self.conn.execute(query, params)
                return cursor
        except Exception as e:
            print(f"DB Execute Error: {query} | {e}")
            return None

    def fetch_all(self, query, params=()):
        """ Returnează toate rezultatele unei interogări (SELECT) - fără overhead tranzacții """
        try:
            cursor = self.conn.execute(query, params)
            return cursor.fetchall() if cursor else []
        except Exception as e:
            print(f"DB Fetch Error: {query} | {e}")
            return []

    def fetch_one(self, query, params=()):
        """ Returnează un singur rezultat - fără overhead tranzacții """
        try:
            cursor = self.conn.execute(query, params)
            return cursor.fetchone() if cursor else None
        except Exception as e:
            print(f"DB Fetch Error: {query} | {e}")
            return None
        
    def begin_transaction(self):
        """ Începe o tranzacție manuală (pentru bulk inserts) """
        self.conn.execute("BEGIN TRANSACTION")

    def commit_transaction(self):
        """ Comite tranzacția manuală """
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()