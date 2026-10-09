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


# --- Checkpoint Management Operations ---


def get_checkpoints(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch all checkpoints ordered by their sequential route position."""
    return conn.execute(
        "SELECT id, name, lat, lng, radius, position, clue, hint, story, kind "
        "FROM checkpoints ORDER BY position ASC, id ASC"
    ).fetchall()


def get_checkpoint_by_id(conn: sqlite3.Connection, checkpoint_id: int) -> Optional[sqlite3.Row]:
    """Fetch a single checkpoint by primary key ID."""
    return conn.execute(
        "SELECT id, name, lat, lng, radius, position, clue, hint, story, kind "
        "FROM checkpoints WHERE id = ?",
        (checkpoint_id,),
    ).fetchone()


def create_checkpoint(
    conn: sqlite3.Connection,
    name: str,
    lat: float,
    lng: float,
    radius: float,
    clue: str,
    hint: str,
    story: Optional[str] = None,
    position: Optional[int] = None,
) -> sqlite3.Row:
    """Insert a new checkpoint, shifting positions safely to prevent duplicates.

    Runs inside BEGIN IMMEDIATE transaction to prevent concurrent sequence collisions.
    """
    import game

    with write_tx(conn):
        count = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        pos = game.compute_target_position(position, count)

        # Shift existing checkpoints at >= pos up by 1 to make room
        conn.execute(
            "UPDATE checkpoints SET position = position + 1 WHERE position >= ?",
            (pos,),
        )

        cursor = conn.execute(
            """
            INSERT INTO checkpoints (name, lat, lng, radius, position, clue, hint, story, kind)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'route')
            """,
            (name, lat, lng, radius, pos, clue, hint, story or None),
        )
        new_id = cursor.lastrowid
        row = get_checkpoint_by_id(conn, new_id)
        assert row is not None
        return row


def update_checkpoint(
    conn: sqlite3.Connection,
    checkpoint_id: int,
    name: str,
    lat: float,
    lng: float,
    radius: float,
    clue: str,
    hint: str,
    story: Optional[str] = None,
    position: Optional[int] = None,
) -> Optional[sqlite3.Row]:
    """Update checkpoint details and adjust sequence positions without duplicate gaps.

    Runs inside BEGIN IMMEDIATE transaction.
    """
    with write_tx(conn):
        existing = get_checkpoint_by_id(conn, checkpoint_id)
        if not existing:
            return None

        old_pos = existing["position"]
        count = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]

        if position is not None and position != old_pos:
            # Clamp target position to [1, count]
            new_pos = max(1, min(position, count))
            if new_pos < old_pos:
                # Moving up towards start: shift items in [new_pos, old_pos - 1] down (+1)
                conn.execute(
                    "UPDATE checkpoints SET position = position + 1 "
                    "WHERE position >= ? AND position < ? AND id != ?",
                    (new_pos, old_pos, checkpoint_id),
                )
            elif new_pos > old_pos:
                # Moving down towards end: shift items in [old_pos + 1, new_pos] up (-1)
                conn.execute(
                    "UPDATE checkpoints SET position = position - 1 "
                    "WHERE position > ? AND position <= ? AND id != ?",
                    (old_pos, new_pos, checkpoint_id),
                )
            final_pos = new_pos
        else:
            final_pos = old_pos

        conn.execute(
            """
            UPDATE checkpoints
            SET name = ?, lat = ?, lng = ?, radius = ?, position = ?, clue = ?, hint = ?, story = ?
            WHERE id = ?
            """,
            (name, lat, lng, radius, final_pos, clue, hint, story or None, checkpoint_id),
        )
        return get_checkpoint_by_id(conn, checkpoint_id)


def delete_checkpoint(conn: sqlite3.Connection, checkpoint_id: int) -> bool:
    """Delete a checkpoint and shift trailing checkpoints down to close order gaps.

    Runs inside BEGIN IMMEDIATE transaction.
    """
    with write_tx(conn):
        existing = get_checkpoint_by_id(conn, checkpoint_id)
        if not existing:
            return False

        del_pos = existing["position"]
        conn.execute("DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,))
        # Compact remaining positions so order sequence remains contiguous
        conn.execute(
            "UPDATE checkpoints SET position = position - 1 WHERE position > ?",
            (del_pos,),
        )
        return True
