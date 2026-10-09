"""Database connection management and SQLite schema definitions for Campus Quest.

All raw SQL statements are isolated here. No game rules live in this module.
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Generator, Optional

import config

TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS checkpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        radius REAL NOT NULL,
        position INTEGER NOT NULL,
        clue TEXT NOT NULL,
        hint TEXT NOT NULL,
        story TEXT,
        kind TEXT NOT NULL DEFAULT 'route'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT UNIQUE NOT NULL,
        members TEXT NOT NULL,
        device_hash TEXT,
        last_seen REAL,
        penalty_s INTEGER NOT NULL DEFAULT 0,
        bonus_s INTEGER NOT NULL DEFAULT 0,
        radar_left INTEGER NOT NULL DEFAULT 0,
        boost_left INTEGER NOT NULL DEFAULT 0,
        radar_until REAL,
        boost_until REAL,
        inside_streak INTEGER NOT NULL DEFAULT 0,
        last_fix_lat REAL,
        last_fix_lng REAL,
        last_fix_ts REAL,
        finished_at REAL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS progress (
        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        checkpoint_id INTEGER NOT NULL REFERENCES checkpoints(id) ON DELETE CASCADE,
        unlocked_at REAL NOT NULL,
        elapsed_s INTEGER NOT NULL,
        how TEXT NOT NULL,
        PRIMARY KEY (team_id, checkpoint_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS hint_uses (
        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        checkpoint_id INTEGER NOT NULL REFERENCES checkpoints(id) ON DELETE CASCADE,
        used_at REAL NOT NULL,
        PRIMARY KEY (team_id, checkpoint_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
        type TEXT NOT NULL,
        detail TEXT
    );
    """,
]

DEFAULT_SETTINGS = [
    ("game_state", "setup"),
    ("registration_open", "1"),
    ("started_at", ""),
    ("test_mode", "0"),
]


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open an autocommit SQLite connection with standard production PRAGMAs.

    - isolation_level=None: Disables Python's automatic transaction management so
      transactions can be controlled explicitly using BEGIN IMMEDIATE in write_tx.
    - journal_mode=WAL: Allows concurrent readers alongside a writer.
    - busy_timeout=5000: Retries for up to 5 seconds if another thread holds the lock.
    - foreign_keys=ON: Enforces relational constraints on all foreign keys.
    """
    path = db_path if db_path is not None else config.DB_PATH
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def write_tx(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for write transactions using BEGIN IMMEDIATE.

    Acquires SQLite's reserved write lock immediately to prevent check-then-insert
    race conditions and deadlocks between concurrent requests.
    Commits on successful block execution, rolls back on any exception.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database tables and seed default settings if not already present.

    Safe to call multiple times (idempotent). Automatically creates the directory
    for the database file if it does not yet exist.
    """
    path_str = db_path if db_path is not None else config.DB_PATH
    db_file = Path(path_str)

    # Ensure parent directory exists (e.g. data/)
    if db_file.parent and not db_file.parent.exists():
        db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(path_str)
    try:
        with write_tx(conn):
            for stmt in TABLE_STATEMENTS:
                conn.execute(stmt)
            for key, val in DEFAULT_SETTINGS:
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, val),
                )
    finally:
        conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding one connection per request and ensuring it closes."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
