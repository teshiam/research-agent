import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id               TEXT PRIMARY KEY,
    topic            TEXT NOT NULL,
    depth            TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'queued',
    mode             TEXT NOT NULL DEFAULT '',
    model            TEXT NOT NULL DEFAULT '',
    report           TEXT,
    error            TEXT,
    searches         INTEGER NOT NULL DEFAULT 0,
    pages_read       INTEGER NOT NULL DEFAULT 0,
    input_tokens     INTEGER NOT NULL DEFAULT 0,
    output_tokens    INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    started_at       TEXT,
    finished_at      TEXT
);

CREATE TABLE IF NOT EXISTS steps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,
    kind          TEXT NOT NULL,
    title         TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '{}',
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (run_id, idx)
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """One short-lived connection per operation: safe across worker threads."""
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
