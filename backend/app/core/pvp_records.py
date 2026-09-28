"""Private completed PvP archives: PostgreSQL in cloud, SQLite locally, 500-hand FIFO."""
import json
import os
import sqlite3
import zlib
from contextlib import closing
from pathlib import Path

MAX_RECORDS = 500


def archive_pvp_game(record, *, db_path=None):
    if record.get('phase') != 'finished' or not record.get('result'):
        raise ValueError('Only completed PvP hands can be archived')
    payload = zlib.compress(json.dumps(record, ensure_ascii=False).encode('utf-8'))
    url = os.getenv('DATABASE_URL', '')
    if db_path is None and not os.getenv('PVP_RECORD_DB_PATH') and url.startswith(('postgres://', 'postgresql://')):
        import psycopg
        with psycopg.connect(url, connect_timeout=15) as db:
            db.execute('SELECT pg_advisory_xact_lock(7422500)')
            db.execute('CREATE TABLE IF NOT EXISTS pvp_game_records (id BIGSERIAL PRIMARY KEY, game_id TEXT NOT NULL UNIQUE, payload BYTEA NOT NULL)')
            db.execute('INSERT INTO pvp_game_records(game_id,payload) VALUES (%s,%s) ON CONFLICT (game_id) DO NOTHING', (record['game_id'], payload))
            db.execute('DELETE FROM pvp_game_records WHERE id NOT IN (SELECT id FROM pvp_game_records ORDER BY id DESC LIMIT %s)', (MAX_RECORDS,))
    else:
        path = Path(db_path or os.getenv('PVP_RECORD_DB_PATH') or Path(__file__).resolve().parents[2] / 'data' / 'pvp_records.sqlite3')
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=15)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS pvp_game_records (id INTEGER PRIMARY KEY AUTOINCREMENT, game_id TEXT NOT NULL UNIQUE, payload BLOB NOT NULL)')
            db.commit()
            with db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT OR IGNORE INTO pvp_game_records(game_id,payload) VALUES (?,?)', (record['game_id'], payload))
                db.execute('DELETE FROM pvp_game_records WHERE id NOT IN (SELECT id FROM pvp_game_records ORDER BY id DESC LIMIT ?)', (MAX_RECORDS,))


def scoring_groups(detail, hand, god):
    """Reveal physical tiles only for groups the existing settlement engine actually scored."""
    remaining = list(hand)
    groups = []
    for item in detail.get('breakdown', []):
        if item.get('hu', 0) <= 0:
            continue
        group = dict(item)
        if item['source'] == 'open':
            group['tiles'] = list(item['physical_tiles'])
        else:
            count = 2 if item['kind'] == 'pair' else 3
            tiles = []
            for tile in list(remaining):
                identity = god if tile == 'P' else tile
                if identity == item['tile'] and len(tiles) < count:
                    tiles.append(tile)
                    remaining.remove(tile)
            group['tiles'] = tiles
        groups.append(group)
    return groups
