"""SQLite persistence (Python standard library, no server to install).

The database file lives in data/balanceai.db and is created automatically.
Schema changes are applied as numbered migrations so existing data is kept.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import config

_lock = threading.RLock()
_db_path: Path = config.DB_PATH

MIGRATIONS = [
    # 1 - initial schema for profiles, timetable, exams, revisions, notifications, push
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        settings TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS schedule_entries (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        day INTEGER NOT NULL,
        start TEXT NOT NULL,
        "end" TEXT NOT NULL,
        location TEXT NOT NULL DEFAULT '',
        recurring INTEGER NOT NULL DEFAULT 1,
        date TEXT,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_entries_user ON schedule_entries(user_id);
    CREATE TABLE IF NOT EXISTS schedule_exceptions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date TEXT NOT NULL,
        entry_id TEXT REFERENCES schedule_entries(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        start TEXT,
        "end" TEXT,
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_exc_user ON schedule_exceptions(user_id, date);
    CREATE TABLE IF NOT EXISTS exams (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        subject TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        chapters TEXT NOT NULL DEFAULT '',
        difficult TEXT NOT NULL DEFAULT '',
        date TEXT,
        time TEXT,
        priority TEXT NOT NULL DEFAULT 'medium',
        preparation INTEGER NOT NULL DEFAULT 0,
        minutes_per_day INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'upcoming',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_exams_user ON exams(user_id);
    CREATE TABLE IF NOT EXISTS revision_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        exam_id TEXT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
        date TEXT NOT NULL,
        start TEXT NOT NULL,
        "end" TEXT NOT NULL,
        minutes INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'planned',
        locked INTEGER NOT NULL DEFAULT 0,
        focus TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON revision_sessions(user_id, date);
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        link TEXT NOT NULL DEFAULT '#home',
        scheduled_for TEXT,
        created_at TEXT NOT NULL,
        read INTEGER NOT NULL DEFAULT 0,
        pushed INTEGER NOT NULL DEFAULT 0,
        dedupe_key TEXT NOT NULL,
        UNIQUE(user_id, dedupe_key)
    );
    CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, created_at);
    CREATE TABLE IF NOT EXISTS push_subscriptions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        endpoint TEXT NOT NULL UNIQUE,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_success TEXT,
        failures INTEGER NOT NULL DEFAULT 0
    );
    """,
    # 2 - accounts, sessions, AI chat
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        csrf TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    CREATE TABLE IF NOT EXISTS chat_conversations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_conv_user ON chat_conversations(user_id, updated_at);
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        conv_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_msg_conv ON chat_messages(conv_id, created_at);
    """,
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def set_path(path) -> None:
    """Use another database file (used by the automated tests)."""
    global _db_path
    _db_path = Path(path)


def _connect() -> sqlite3.Connection:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def tx():
    """Open a connection, commit on success, roll back on error."""
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init() -> int:
    """Create / migrate the schema. Returns the current schema version."""
    with tx() as c:
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        row = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        version = int(row["value"]) if row else 0
        if version and version < len(MIGRATIONS) and _db_path.exists():
            import shutil
            shutil.copy2(_db_path, _db_path.with_name(f"{_db_path.name}.backup-v{version}"))
        for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
            c.executescript(script)
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)", (str(i),))
            version = i
    return version


def rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def load_json(text: str, default):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default
