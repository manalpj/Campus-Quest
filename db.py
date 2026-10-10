"""Database connection management and SQLite schema definitions for Campus Quest.

All raw SQL statements are isolated here. No game rules live in this module.
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time
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


# --- Settings & Team Management Operations ---


def get_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    """Retrieve setting value by key, or None if not set."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Insert or update a setting value in the settings table.

    Runs inside a write_tx (BEGIN IMMEDIATE) transaction.
    """
    with write_tx(conn):
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def get_checkpoint_count(conn: sqlite3.Connection) -> int:
    """Return the total number of configured checkpoints."""
    row = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()
    return row[0] if row else 0


def log_event(
    conn: sqlite3.Connection,
    event_type: str,
    detail: Optional[str] = None,
    team_id: Optional[int] = None,
) -> None:
    """Record an operational or game audit event into the events table.

    Runs inside a write_tx (BEGIN IMMEDIATE) transaction.
    """
    with write_tx(conn):
        conn.execute(
            "INSERT INTO events (ts, team_id, type, detail) VALUES (?, ?, ?, ?)",
            (time.time(), team_id, event_type, detail),
        )


def get_team_by_code(conn: sqlite3.Connection, code: str) -> Optional[sqlite3.Row]:
    """Fetch team row by unique team code (case-insensitive lookup)."""
    return conn.execute(
        "SELECT * FROM teams WHERE UPPER(code) = UPPER(?)",
        (code.strip(),),
    ).fetchone()


def get_team_by_id(conn: sqlite3.Connection, team_id: int) -> Optional[sqlite3.Row]:
    """Fetch team row by primary key id."""
    return conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()


def get_team_by_device_hash(conn: sqlite3.Connection, device_hash: str) -> Optional[sqlite3.Row]:
    """Fetch team row matching device token hash."""
    return conn.execute(
        "SELECT * FROM teams WHERE device_hash = ?",
        (device_hash,),
    ).fetchone()


def create_team(
    conn: sqlite3.Connection,
    name: str,
    members: list[str],
    max_retries: int = 5,
) -> tuple[sqlite3.Row, str]:
    """Register a new team, generating a unique team code and device token.

    Stores the SHA-256 hash of the device token.
    Runs within write_tx (BEGIN IMMEDIATE).
    Returns (team_row, device_token).
    """
    import json
    import time
    import auth
    import game

    with write_tx(conn):
        reg_open = get_setting(conn, "registration_open")
        if reg_open != "1":
            raise ValueError("Registration is currently closed by the organizer.")

        members_json = json.dumps(members)
        now = time.time()

        for _ in range(max_retries):
            code = game.generate_team_code(name)
            token = auth.generate_device_token()
            token_hash = auth.hash_device_token(token)

            try:
                cursor = conn.execute(
                    """
                    INSERT INTO teams (name, code, members, device_hash, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, code, members_json, token_hash, now),
                )
                team_id = cursor.lastrowid
                conn.execute(
                    "INSERT INTO events (ts, team_id, type, detail) VALUES (?, ?, 'team_registered', ?)",
                    (now, team_id, f"Team {name} registered with code {code}"),
                )
                row = get_team_by_id(conn, team_id)
                assert row is not None
                return row, token
            except sqlite3.IntegrityError:
                # Collision on code UNIQUE constraint; retry with a new code
                continue

        raise RuntimeError("Failed to generate a unique team code after maximum retries.")


def bind_team_device(conn: sqlite3.Connection, team_id: int, device_hash: str) -> None:
    """Bind a new device hash to a team whose device was cleared.

    Runs within write_tx (BEGIN IMMEDIATE).
    """
    import time

    with write_tx(conn):
        now = time.time()
        conn.execute(
            "UPDATE teams SET device_hash = ?, last_seen = ? WHERE id = ?",
            (device_hash, now, team_id),
        )
        conn.execute(
            "INSERT INTO events (ts, team_id, type, detail) VALUES (?, ?, 'device_bound', 'Device bound to team')",
            (now, team_id),
        )


# --- Checkpoint Progress & Ping Operations ---


def get_team_next_checkpoint(conn: sqlite3.Connection, team_id: int) -> Optional[sqlite3.Row]:
    """Retrieve the next uncompleted checkpoint for a team.

    Finds the checkpoint with the lowest route sequence position that has
    no matching record in the progress table for this team.
    """
    return conn.execute(
        """
        SELECT c.*
        FROM checkpoints c
        WHERE c.id NOT IN (
            SELECT p.checkpoint_id
            FROM progress p
            WHERE p.team_id = ?
        )
        ORDER BY c.position ASC, c.id ASC
        LIMIT 1
        """,
        (team_id,),
    ).fetchone()


def get_team_progress_counts(conn: sqlite3.Connection, team_id: int) -> tuple[int, int]:
    """Return (cleared_count, total_count) for the team."""
    cleared_row = conn.execute(
        "SELECT COUNT(*) FROM progress WHERE team_id = ?",
        (team_id,),
    ).fetchone()
    cleared = cleared_row[0] if cleared_row else 0

    total_row = conn.execute(
        "SELECT COUNT(*) FROM checkpoints",
    ).fetchone()
    total = total_row[0] if total_row else 0
    return cleared, total


def update_team_fix_and_streak(
    conn: sqlite3.Connection,
    team_id: int,
    lat: float,
    lng: float,
    ts: float,
    streak: int,
) -> None:
    """Update last fix location, timestamp, last_seen, and inside streak for a team.

    Runs within write_tx (BEGIN IMMEDIATE).
    """
    with write_tx(conn):
        conn.execute(
            """
            UPDATE teams
            SET last_fix_lat = ?, last_fix_lng = ?, last_fix_ts = ?, last_seen = ?, inside_streak = ?
            WHERE id = ?
            """,
            (lat, lng, ts, ts, streak, team_id),
        )


def touch_team_last_seen(conn: sqlite3.Connection, team_id: int, now: float) -> None:
    """Update last_seen timestamp for a team without altering fix coordinates or streak.

    Runs within write_tx (BEGIN IMMEDIATE).
    """
    with write_tx(conn):
        conn.execute(
            "UPDATE teams SET last_seen = ? WHERE id = ?",
            (now, team_id),
        )


def unlock_checkpoint(
    conn: sqlite3.Connection,
    team_id: int,
    checkpoint_id: int,
    unlocked_at: float,
    elapsed_s: int,
    is_last: bool,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> bool:
    """Record an unlocked checkpoint in progress, reset streak, and update team state.

    Runs within write_tx (BEGIN IMMEDIATE).
    Guaranteed atomic and idempotent: checks for existing progress row to prevent
    duplicate progress records from concurrent requests.
    Returns True if successfully unlocked, or False if already unlocked.
    """
    with write_tx(conn):
        existing = conn.execute(
            "SELECT 1 FROM progress WHERE team_id = ? AND checkpoint_id = ?",
            (team_id, checkpoint_id),
        ).fetchone()
        if existing:
            return False

        conn.execute(
            """
            INSERT INTO progress (team_id, checkpoint_id, unlocked_at, elapsed_s, how)
            VALUES (?, ?, ?, ?, 'gps')
            """,
            (team_id, checkpoint_id, unlocked_at, elapsed_s),
        )

        if is_last:
            conn.execute(
                """
                UPDATE teams
                SET inside_streak = 0, last_seen = ?, last_fix_lat = ?, last_fix_lng = ?, last_fix_ts = ?, finished_at = ?
                WHERE id = ?
                """,
                (unlocked_at, lat, lng, unlocked_at, unlocked_at, team_id),
            )
            conn.execute(
                """
                INSERT INTO events (ts, team_id, type, detail)
                VALUES (?, ?, 'team_finished', 'Team completed all checkpoints')
                """,
                (unlocked_at, team_id),
            )
        else:
            conn.execute(
                """
                UPDATE teams
                SET inside_streak = 0, last_seen = ?, last_fix_lat = ?, last_fix_lng = ?, last_fix_ts = ?
                WHERE id = ?
                """,
                (unlocked_at, lat, lng, unlocked_at, team_id),
            )

        conn.execute(
            """
            INSERT INTO events (ts, team_id, type, detail)
            VALUES (?, ?, 'checkpoint_unlocked', ?)
            """,
            (unlocked_at, team_id, f"Unlocked checkpoint {checkpoint_id} (elapsed {elapsed_s}s)"),
        )
        return True


def get_team_cleared_checkpoints(conn: sqlite3.Connection, team_id: int) -> list[sqlite3.Row]:
    """Retrieve all cleared checkpoints for a team in route order.

    Returns rows with id, name, lat, lng, story, position, unlocked_at, elapsed_s.
    """
    return conn.execute(
        """
        SELECT c.id, c.name, c.lat, c.lng, c.story, c.position, p.unlocked_at, p.elapsed_s
        FROM progress p
        JOIN checkpoints c ON p.checkpoint_id = c.id
        WHERE p.team_id = ?
        ORDER BY c.position ASC, c.id ASC
        """,
        (team_id,),
    ).fetchall()


