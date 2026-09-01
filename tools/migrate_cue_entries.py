import ast
import os
import sqlite3
import sys

from PyQt6.QtCore import QSettings


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from playlist.playlist_logic import PlaylistLogic
from playlist.playlist_scanner import PlaylistScanner


def parse_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith("['") or value.startswith('["'):
            try:
                return ast.literal_eval(value)
            except Exception:
                return []
        if ',' in value:
            return [item.strip() for item in value.split(',') if item.strip()]
        return [value]
    return []


def main():
    settings_path = os.path.join(PROJECT_ROOT, 'settings.ini')
    settings = QSettings(settings_path, QSettings.Format.IniFormat)

    logic = PlaylistLogic()
    logic.migrate_cue_virtual_entries()
    logic.db.close()

    queue = parse_list(settings.value('queue'))
    shuffled_queue = parse_list(settings.value('shuffled_queue'))
    last_song = settings.value('last_song', '')

    normalized_queue = PlaylistScanner.canonicalize_track_list([str(item) for item in queue if item])
    normalized_shuffled = PlaylistScanner.canonicalize_track_list([str(item) for item in shuffled_queue if item])
    normalized_last_song = PlaylistScanner.canonicalize_track_path(last_song) if last_song else ''

    settings.setValue('queue', normalized_queue)
    settings.setValue('shuffled_queue', normalized_shuffled)
    settings.setValue('last_song', normalized_last_song)
    settings.sync()

    db_path = os.path.join(PROJECT_ROOT, 'cache', 'databases', 'stava_library.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM songs WHERE path LIKE ?', (f'%{PlaylistScanner.CUE_MARKER}%',))
    cue_count = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM songs WHERE path LIKE ?', ('%Cargo%',))
    cargo_count = cur.fetchone()[0]
    cur.execute('SELECT path FROM songs WHERE path LIKE ? ORDER BY path LIMIT 5', ('%Cargo%',))
    examples = [row[0] for row in cur.fetchall()]
    conn.close()

    print(f'normalized_queue_count={len(normalized_queue)}')
    print(f'normalized_shuffled_count={len(normalized_shuffled)}')
    print(f'normalized_last_song={normalized_last_song}')
    print(f'cue_rows_after={cue_count}')
    print(f'cargo_rows_after={cargo_count}')
    for example in examples:
        print(f'example={example}')


if __name__ == '__main__':
    raise SystemExit(main())