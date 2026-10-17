"""Shared transactional SQLite/PostgreSQL persistence for accounts and matches."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Connection:
    def __init__(self, raw, postgres=False):
        self.raw, self.postgres = raw, postgres

    def execute(self, sql, parameters=()):
        return self.raw.execute(sql.replace('?', '%s') if self.postgres else sql, parameters)

    def __getattr__(self, name):
        return getattr(self.raw, name)


@contextmanager
def connect():
    url = os.getenv('DATABASE_URL', '')
    postgres = bool(url)
    if postgres:
        import psycopg
        from psycopg.rows import dict_row
        raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=15)
    else:
        path = Path(os.getenv('AUTH_DB_PATH') or Path(__file__).resolve().parents[2] / 'data' / 'auth.sqlite3')
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(path, timeout=30)
        raw.row_factory = sqlite3.Row
        raw.execute('PRAGMA foreign_keys=ON')
    try:
        if postgres:
            raw.execute('SELECT pg_advisory_xact_lock(7422501)')
        else:
            raw.execute('BEGIN IMMEDIATE')
        yield Connection(raw, postgres)
        raw.commit()
    except BaseException:
        raw.rollback()
        raise
    finally:
        raw.close()


transaction = connect


def ensure_schema():
    statements = [
        '''CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, account TEXT NOT NULL, account_normalized TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS registration_codes (code_digest TEXT PRIMARY KEY, batch TEXT NOT NULL, expires_at TEXT, used_by TEXT REFERENCES users(id), used_at TEXT, revoked_at TEXT, created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS auth_tokens (token_digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), client_type TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS friendships (id TEXT PRIMARY KEY, user_low TEXT NOT NULL REFERENCES users(id), user_high TEXT NOT NULL REFERENCES users(id), requested_by TEXT NOT NULL REFERENCES users(id), status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(user_low,user_high))''',
        '''CREATE TABLE IF NOT EXISTS matches (id TEXT PRIMARY KEY, host_id TEXT NOT NULL REFERENCES users(id), status TEXT NOT NULL, start_at DOUBLE PRECISION, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS match_members (match_id TEXT NOT NULL REFERENCES matches(id), user_id TEXT NOT NULL REFERENCES users(id), seat INTEGER NOT NULL CHECK(seat BETWEEN 1 AND 4), ready INTEGER NOT NULL DEFAULT 0, joined_at TEXT NOT NULL, PRIMARY KEY(match_id,user_id), UNIQUE(match_id,seat))''',
        '''CREATE TABLE IF NOT EXISTS invitations (id TEXT PRIMARY KEY, match_id TEXT NOT NULL REFERENCES matches(id), inviter_id TEXT NOT NULL REFERENCES users(id), invitee_id TEXT NOT NULL REFERENCES users(id), status TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL, responded_at TEXT)''',
        '''CREATE UNIQUE INDEX IF NOT EXISTS invitations_one_pending ON invitations(match_id,invitee_id) WHERE status='pending' ''',
        '''CREATE TABLE IF NOT EXISTS match_hands (match_id TEXT NOT NULL REFERENCES matches(id), game_id TEXT PRIMARY KEY, hand_number INTEGER NOT NULL, scores TEXT NOT NULL, finished_at TEXT NOT NULL)''',
        '''CREATE INDEX IF NOT EXISTS auth_tokens_user ON auth_tokens(user_id)''',
        '''CREATE INDEX IF NOT EXISTS match_members_user ON match_members(user_id)''',
    ]
    with connect() as db:
        for statement in statements:
            db.execute(statement)
        if db.postgres:
            # Millisecond epoch values exceed PostgreSQL REAL's precision.
            db.execute('ALTER TABLE matches ALTER COLUMN start_at TYPE DOUBLE PRECISION')
