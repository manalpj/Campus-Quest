"""Database connection management and SQLite schema definitions for Campus Quest.

All raw SQL statements are isolated here. No game rules live in this module.
"""

from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time
from typing import Generator, Optional, Union

import config
import game

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
        last_fix_accuracy REAL,
        last_fix_test INTEGER NOT NULL DEFAULT 0,
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

    - check_same_thread=False: Allows AnyIO threadpool workers to close connections safely across threads.
    - isolation_level=None: Disables Python's automatic transaction management so
      transactions can be controlled explicitly using BEGIN IMMEDIATE in write_tx.
    - journal_mode=WAL: Allows concurrent readers alongside a writer.
    - busy_timeout=5000: Retries for up to 5 seconds if another thread holds the lock.
    - foreign_keys=ON: Enforces relational constraints on all foreign keys.
    """
    path = db_path if db_path is not None else config.DB_PATH
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
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
            # Idempotent column migrations for existing databases
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(teams)").fetchall()}
            if "last_fix_accuracy" not in cols:
                conn.execute("ALTER TABLE teams ADD COLUMN last_fix_accuracy REAL;")
            if "last_fix_test" not in cols:
                conn.execute("ALTER TABLE teams ADD COLUMN last_fix_test INTEGER NOT NULL DEFAULT 0;")
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
    team_id: Optional[int],
    type: str,
    detail: Optional[Union[str, dict, list]] = None,
) -> None:
    """Record an operational or game audit event into the events table.

    Stores server time. If detail is a dict or list, serializes it to JSON string.
    Executes directly if called within an existing transaction, or wraps in write_tx
    if called independently.
    """
    ts = time.time()
    if isinstance(detail, (dict, list)):
        detail_val = json.dumps(detail)
    elif detail is not None:
        detail_val = str(detail)
    else:
        detail_val = None

    if conn.in_transaction:
        conn.execute(
            "INSERT INTO events (ts, team_id, type, detail) VALUES (?, ?, ?, ?)",
            (ts, team_id, type, detail_val),
        )
    else:
        with write_tx(conn):
            conn.execute(
                "INSERT INTO events (ts, team_id, type, detail) VALUES (?, ?, ?, ?)",
                (ts, team_id, type, detail_val),
            )


def get_latest_events(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    """Retrieve the latest audit events ordered newest first.

    Guaranteed parameterised query. Limit clamped to safe range (1-500).
    """
    safe_limit = max(1, min(limit, 500))
    return conn.execute(
        """
        SELECT id, ts, team_id, type, detail
        FROM events
        ORDER BY id DESC
        LIMIT ?
        """,
        (safe_limit,),
    ).fetchall()


def get_events(
    conn: sqlite3.Connection,
    team_id: Optional[int] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[sqlite3.Row]:
    """Retrieve audit events with optional team and type filters, ordered newest first.

    Left-joins teams to provide team_name without leaking join codes or hashes.
    Guaranteed parameterised query with limit clamped between 1 and 200, offset >= 0.
    """
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)

    conditions: list[str] = []
    params: list[Union[int, str]] = []

    if team_id is not None:
        conditions.append("e.team_id = ?")
        params.append(team_id)
    if event_type:
        conditions.append("e.type = ?")
        params.append(event_type)

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([safe_limit, safe_offset])

    query = f"""
        SELECT e.id, e.ts, e.team_id, e.type, e.detail, t.name AS team_name
        FROM events e
        LEFT JOIN teams t ON e.team_id = t.id
        {where_sql}
        ORDER BY e.id DESC
        LIMIT ? OFFSET ?
    """
    return conn.execute(query, tuple(params)).fetchall()


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
                log_event(
                    conn,
                    team_id,
                    game.EVENT_TEAM_REGISTERED,
                    f"team_id={team_id}",
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
    with write_tx(conn):
        now = time.time()
        conn.execute(
            "UPDATE teams SET device_hash = ?, last_seen = ? WHERE id = ?",
            (device_hash, now, team_id),
        )
        log_event(
            conn,
            team_id,
            game.EVENT_DEVICE_BOUND,
            f"team_id={team_id}",
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


def get_team_last_progress_time(conn: sqlite3.Connection, team_id: int) -> Optional[float]:
    """Return the unlocked_at timestamp of the most recently cleared/skipped checkpoint, or None."""
    row = conn.execute(
        "SELECT MAX(unlocked_at) FROM progress WHERE team_id = ?",
        (team_id,),
    ).fetchone()
    if row and row[0] is not None:
        return float(row[0])
    return None


def update_team_fix_and_streak(
    conn: sqlite3.Connection,
    team_id: int,
    lat: float,
    lng: float,
    ts: float,
    streak: int,
    accuracy: Optional[float] = None,
    is_test: bool = False,
) -> None:
    """Update last fix location, accuracy, test flag, timestamp, last_seen, and inside streak for a team.

    Runs within write_tx (BEGIN IMMEDIATE).
    """
    with write_tx(conn):
        conn.execute(
            """
            UPDATE teams
            SET last_fix_lat = ?, last_fix_lng = ?, last_fix_ts = ?,
                last_fix_accuracy = ?, last_fix_test = ?, last_seen = ?, inside_streak = ?
            WHERE id = ?
            """,
            (lat, lng, ts, accuracy, 1 if is_test else 0, ts, streak, team_id),
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


def reset_team_streak(conn: sqlite3.Connection, team_id: int, now: float) -> None:
    """Reset inside_streak to 0 and update last_seen, keeping last_fix coordinates intact.

    Runs within write_tx (BEGIN IMMEDIATE).
    """
    with write_tx(conn):
        conn.execute(
            "UPDATE teams SET inside_streak = 0, last_seen = ? WHERE id = ?",
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
    accuracy: Optional[float] = None,
    is_test: bool = False,
    awarded_powerup: Optional[str] = None,
) -> bool:
    """Record an unlocked checkpoint in progress, reset streak, award powerup, and update team state.

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

        radar_inc = 1 if awarded_powerup == "radar" else 0
        boost_inc = 1 if awarded_powerup == "boost" else 0
        test_val = 1 if is_test else 0

        if is_last:
            conn.execute(
                """
                UPDATE teams
                SET inside_streak = 0, last_seen = ?, last_fix_lat = ?, last_fix_lng = ?, last_fix_ts = ?,
                    last_fix_accuracy = ?, last_fix_test = ?,
                    radar_left = radar_left + ?, boost_left = boost_left + ?, finished_at = ?
                WHERE id = ?
                """,
                (unlocked_at, lat, lng, unlocked_at, accuracy, test_val, radar_inc, boost_inc, unlocked_at, team_id),
            )
        else:
            conn.execute(
                """
                UPDATE teams
                SET inside_streak = 0, last_seen = ?, last_fix_lat = ?, last_fix_lng = ?, last_fix_ts = ?,
                    last_fix_accuracy = ?, last_fix_test = ?,
                    radar_left = radar_left + ?, boost_left = boost_left + ?
                WHERE id = ?
                """,
                (unlocked_at, lat, lng, unlocked_at, accuracy, test_val, radar_inc, boost_inc, team_id),
            )

        log_event(
            conn,
            team_id,
            game.EVENT_CHECKPOINT_UNLOCKED,
            f"checkpoint_id={checkpoint_id} elapsed_s={elapsed_s}",
        )

        return True


def get_team_current_checkpoint_start(
    conn: sqlite3.Connection,
    team_id: int,
    started_at_ts: float,
) -> float:
    """Return timestamp when the team started their current checkpoint.

    If the team has cleared checkpoints, this is the unlocked_at timestamp
    of their most recent unlock. Otherwise, it is the game's started_at timestamp.
    """
    row = conn.execute(
        "SELECT MAX(unlocked_at) AS last_unlock FROM progress WHERE team_id = ?",
        (team_id,),
    ).fetchone()
    if row and row["last_unlock"] is not None:
        return float(row["last_unlock"])
    return started_at_ts


def skip_checkpoint(
    conn: sqlite3.Connection,
    team_id: int,
    checkpoint_id: int,
    unlocked_at: float,
    elapsed_s: int,
    penalty_s: int,
    is_last: bool,
) -> tuple[bool, int]:
    """Record skipped checkpoint in progress, apply skip penalty, and reset streak.

    Runs within write_tx (BEGIN IMMEDIATE).
    Guaranteed atomic: checks for existing progress row to prevent double-skipping or double-clearing.
    Awards NO power-up.
    Returns (success, new_penalty_s).
    """
    with write_tx(conn):
        existing = conn.execute(
            "SELECT 1 FROM progress WHERE team_id = ? AND checkpoint_id = ?",
            (team_id, checkpoint_id),
        ).fetchone()
        if existing:
            team_row = conn.execute("SELECT penalty_s FROM teams WHERE id = ?", (team_id,)).fetchone()
            return False, team_row["penalty_s"] if team_row else 0

        conn.execute(
            """
            INSERT INTO progress (team_id, checkpoint_id, unlocked_at, elapsed_s, how)
            VALUES (?, ?, ?, ?, 'skipped')
            """,
            (team_id, checkpoint_id, unlocked_at, elapsed_s),
        )

        if is_last:
            conn.execute(
                """
                UPDATE teams
                SET inside_streak = 0, last_seen = ?, penalty_s = penalty_s + ?, finished_at = ?
                WHERE id = ?
                """,
                (unlocked_at, penalty_s, unlocked_at, team_id),
            )
        else:
            conn.execute(
                """
                UPDATE teams
                SET inside_streak = 0, last_seen = ?, penalty_s = penalty_s + ?
                WHERE id = ?
                """,
                (unlocked_at, penalty_s, team_id),
            )

        team_row = conn.execute("SELECT penalty_s FROM teams WHERE id = ?", (team_id,)).fetchone()
        new_penalty = team_row["penalty_s"] if team_row else penalty_s

        log_event(
            conn,
            team_id,
            game.EVENT_CHECKPOINT_SKIPPED,
            f"checkpoint_id={checkpoint_id} penalty_s={penalty_s}",
        )
        return True, new_penalty


def admin_force_clear_checkpoint(
    conn: sqlite3.Connection,
    team_id: int,
    checkpoint_id: int,
    unlocked_at: float,
    elapsed_s: int,
    reason: str,
    is_last: bool,
) -> bool:
    """Force-clear the team's current checkpoint by admin with no penalty or power-up.

    Runs within write_tx (BEGIN IMMEDIATE).
    Guaranteed atomic: checks for existing progress row.
    Logs EVENT_CHECKPOINT_FORCE_CLEARED with mandatory reason.
    Returns True if successfully cleared, False if already cleared.
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
            VALUES (?, ?, ?, ?, 'admin')
            """,
            (team_id, checkpoint_id, unlocked_at, elapsed_s),
        )

        if is_last:
            conn.execute(
                """
                UPDATE teams
                SET inside_streak = 0, finished_at = ?
                WHERE id = ?
                """,
                (unlocked_at, team_id),
            )
        else:
            conn.execute(
                """
                UPDATE teams
                SET inside_streak = 0
                WHERE id = ?
                """,
                (team_id,),
            )

        log_event(
            conn,
            team_id,
            game.EVENT_CHECKPOINT_FORCE_CLEARED,
            f"checkpoint_id={checkpoint_id} reason={reason}",
        )
        return True


def use_hint(
    conn: sqlite3.Connection,
    team_id: int,
    checkpoint_id: int,
    penalty_s: int,
    now: float,
) -> tuple[bool, str, int]:
    """Record hint usage for a checkpoint and apply time penalty.

    Runs within write_tx (BEGIN IMMEDIATE).
    If hint was already used for this checkpoint, returns (False, hint_text, current_penalty_s)
    without applying a second penalty.
    If first use, records in hint_uses, increments teams.penalty_s by penalty_s,
    logs to events, and returns (True, hint_text, new_penalty_s).
    """
    with write_tx(conn):
        cp = conn.execute(
            "SELECT hint FROM checkpoints WHERE id = ?",
            (checkpoint_id,),
        ).fetchone()
        if not cp:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")
        hint_text = cp["hint"]

        existing = conn.execute(
            "SELECT 1 FROM hint_uses WHERE team_id = ? AND checkpoint_id = ?",
            (team_id, checkpoint_id),
        ).fetchone()

        team_row = conn.execute("SELECT penalty_s FROM teams WHERE id = ?", (team_id,)).fetchone()
        current_penalty = team_row["penalty_s"] if team_row else 0

        if existing:
            return False, hint_text, current_penalty

        conn.execute(
            "INSERT INTO hint_uses (team_id, checkpoint_id, used_at) VALUES (?, ?, ?)",
            (team_id, checkpoint_id, now),
        )
        conn.execute(
            "UPDATE teams SET penalty_s = penalty_s + ? WHERE id = ?",
            (penalty_s, team_id),
        )
        new_penalty = current_penalty + penalty_s

        log_event(
            conn,
            team_id,
            game.EVENT_HINT_USED,
            f"checkpoint_id={checkpoint_id} penalty_s={penalty_s}",
        )
        return True, hint_text, new_penalty


def use_radar(
    conn: sqlite3.Connection,
    team_id: int,
    duration_s: int,
    now: float,
) -> tuple[bool, float, int]:
    """Activate Radar power-up for a team.

    Runs within write_tx (BEGIN IMMEDIATE).
    Checks if radar_left > 0. If 0, returns (False, current_radar_until, 0).
    Otherwise decrements radar_left, sets radar_until = now + duration_s,
    logs to events, and returns (True, radar_until, remaining_radar).
    """
    with write_tx(conn):
        team = conn.execute(
            "SELECT radar_left, radar_until FROM teams WHERE id = ?",
            (team_id,),
        ).fetchone()
        if not team or team["radar_left"] <= 0:
            radar_until = team["radar_until"] if team and team["radar_until"] else 0.0
            return False, radar_until, 0

        new_until = now + duration_s
        remaining = team["radar_left"] - 1
        conn.execute(
            "UPDATE teams SET radar_left = ?, radar_until = ? WHERE id = ?",
            (remaining, new_until, team_id),
        )
        log_event(
            conn,
            team_id,
            game.EVENT_RADAR_USED,
            f"duration_s={duration_s}",
        )
        return True, new_until, remaining


def use_boost(
    conn: sqlite3.Connection,
    team_id: int,
    duration_s: int,
    now: float,
) -> tuple[bool, float, int]:
    """Activate Radius boost power-up for a team.

    Runs within write_tx (BEGIN IMMEDIATE).
    Checks if boost_left > 0. If 0, returns (False, current_boost_until, 0).
    Otherwise decrements boost_left, sets boost_until = now + duration_s,
    and returns (True, boost_until, remaining_boost).
    """
    with write_tx(conn):
        team = conn.execute(
            "SELECT boost_left, boost_until FROM teams WHERE id = ?",
            (team_id,),
        ).fetchone()
        if not team or team["boost_left"] <= 0:
            boost_until = team["boost_until"] if team and team["boost_until"] else 0.0
            return False, boost_until, 0

        new_until = now + duration_s
        remaining = team["boost_left"] - 1
        conn.execute(
            "UPDATE teams SET boost_left = ?, boost_until = ? WHERE id = ?",
            (remaining, new_until, team_id),
        )
        return True, new_until, remaining


def get_active_hint_for_team(
    conn: sqlite3.Connection,
    team_id: int,
    checkpoint_id: int,
) -> Optional[str]:
    """Return revealed hint string if team already used a hint for this checkpoint."""
    row = conn.execute(
        """
        SELECT c.hint
        FROM hint_uses h
        JOIN checkpoints c ON h.checkpoint_id = c.id
        WHERE h.team_id = ? AND h.checkpoint_id = ?
        """,
        (team_id, checkpoint_id),
    ).fetchone()
    return row["hint"] if row else None


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


def get_leaderboard_data(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Retrieve raw progress and penalty metrics for all registered teams for ranking.

    Returns rows containing:
    team_id, name, code, penalty_s, bonus_s, finished_at, cleared, total,
    elapsed_at_last_unlock_s, last_unlock_ts.
    """
    return conn.execute(
        """
        SELECT 
            t.id AS team_id,
            t.name,
            t.code,
            t.penalty_s,
            t.bonus_s,
            t.finished_at,
            COUNT(p.checkpoint_id) AS cleared,
            (SELECT COUNT(*) FROM checkpoints) AS total,
            COALESCE(MAX(p.elapsed_s), 0) AS elapsed_at_last_unlock_s,
            MAX(p.unlocked_at) AS last_unlock_ts
        FROM teams t
        LEFT JOIN progress p ON t.id = p.team_id
        GROUP BY t.id
        """
    ).fetchall()


def get_admin_teams_data(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Retrieve all teams with device status, members, last_seen, cleared count, and timing.

    Returns rows with:
    id, name, code, members, device_hash, last_seen, penalty_s, bonus_s,
    finished_at, cleared, total, elapsed_at_last_unlock_s.
    Ordered by team id ASC.
    """
    return conn.execute(
        """
        SELECT
            t.id,
            t.name,
            t.code,
            t.members,
            t.device_hash,
            t.last_seen,
            t.penalty_s,
            t.bonus_s,
            t.finished_at,
            COUNT(p.checkpoint_id) AS cleared,
            (SELECT COUNT(*) FROM checkpoints) AS total,
            COALESCE(MAX(p.elapsed_s), 0) AS elapsed_at_last_unlock_s
        FROM teams t
        LEFT JOIN progress p ON t.id = p.team_id
        GROUP BY t.id
        ORDER BY t.id ASC
        """
    ).fetchall()


def get_teams_export_data(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Retrieve team metrics and breakdown of clearance methods for CSV export.

    Guarantees no sensitive tokens, device hashes, or join codes are returned.
    Returns:
    team_id, name, members, penalty_s, bonus_s, finished_at, cleared, total,
    elapsed_at_last_unlock_s, last_unlock_ts, count_unlocked, count_skipped, count_admin.
    """
    return conn.execute(
        """
        SELECT
            t.id AS team_id,
            t.name,
            t.members,
            t.penalty_s,
            t.bonus_s,
            t.finished_at,
            COUNT(p.checkpoint_id) AS cleared,
            (SELECT COUNT(*) FROM checkpoints) AS total,
            COALESCE(MAX(p.elapsed_s), 0) AS elapsed_at_last_unlock_s,
            MAX(p.unlocked_at) AS last_unlock_ts,
            COUNT(CASE WHEN p.how IN ('unlocked', 'gps') THEN 1 END) AS count_unlocked,
            COUNT(CASE WHEN p.how = 'skipped' THEN 1 END) AS count_skipped,
            COUNT(CASE WHEN p.how = 'admin' THEN 1 END) AS count_admin
        FROM teams t
        LEFT JOIN progress p ON t.id = p.team_id
        GROUP BY t.id
        ORDER BY t.id ASC
        """
    ).fetchall()


def release_team_device(conn: sqlite3.Connection, team_id: int) -> bool:
    """Clear device_hash for a team, releasing device binding so another phone can join.

    Runs within write_tx (BEGIN IMMEDIATE).
    Returns True if team existed and was updated, False if team not found.
    Logs EVENT_DEVICE_RELEASED.
    """
    with write_tx(conn):
        team = get_team_by_id(conn, team_id)
        if not team:
            return False
        conn.execute("UPDATE teams SET device_hash = NULL WHERE id = ?", (team_id,))
        log_event(
            conn,
            team_id,
            game.EVENT_DEVICE_RELEASED,
            f"team_id={team_id} code={team['code']}",
        )
        return True


def adjust_team_time(
    conn: sqlite3.Connection,
    team_id: int,
    minutes: int,
    reason: str,
) -> tuple[bool, int, int]:
    """Adjust team time penalty or bonus by given minutes with an audited reason.

    If minutes > 0, increments penalty_s by minutes * 60.
    If minutes < 0, increments bonus_s by abs(minutes) * 60.
    Runs within write_tx (BEGIN IMMEDIATE).
    Returns (success, new_penalty_s, new_bonus_s).
    """
    with write_tx(conn):
        team = get_team_by_id(conn, team_id)
        if not team:
            return False, 0, 0

        diff_s = abs(minutes) * 60
        if minutes > 0:
            conn.execute(
                "UPDATE teams SET penalty_s = penalty_s + ? WHERE id = ?",
                (diff_s, team_id),
            )
        else:
            conn.execute(
                "UPDATE teams SET bonus_s = bonus_s + ? WHERE id = ?",
                (diff_s, team_id),
            )

        updated = get_team_by_id(conn, team_id)
        assert updated is not None

        log_event(
            conn,
            team_id,
            game.EVENT_TIME_ADJUSTED,
            f"minutes={minutes:+d} reason={reason}",
        )
        return True, updated["penalty_s"], updated["bonus_s"]


def delete_team(conn: sqlite3.Connection, team_id: int) -> bool:
    """Delete a team and cascade deletes to progress and hint_uses.

    Runs within write_tx (BEGIN IMMEDIATE).
    Returns True if deleted, False if team was not found.
    Logs EVENT_TEAM_DELETED before deletion.
    """
    with write_tx(conn):
        team = get_team_by_id(conn, team_id)
        if not team:
            return False
        log_event(
            conn,
            team_id,
            game.EVENT_TEAM_DELETED,
            f"team_id={team_id} name={team['name']} code={team['code']}",
        )
        conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        return True


def reset_all_teams_progress(conn: sqlite3.Connection) -> int:
    """Reset gameplay progress, powerups, streaks, and completion state for all teams.

    Preserves team registrations, secret codes, members, and bound devices.
    Clears all rows from progress and hint_uses.
    Returns the count of teams whose runtime state was reset.
    """
    with write_tx(conn):
        conn.execute("DELETE FROM progress")
        conn.execute("DELETE FROM hint_uses")
        cur = conn.execute(
            """
            UPDATE teams
            SET penalty_s = 0,
                bonus_s = 0,
                radar_left = 0,
                boost_left = 0,
                radar_until = NULL,
                boost_until = NULL,
                inside_streak = 0,
                last_fix_lat = NULL,
                last_fix_lng = NULL,
                last_fix_ts = NULL,
                last_fix_accuracy = NULL,
                last_fix_test = 0,
                finished_at = NULL
            """
        )
        count = cur.rowcount
        log_event(
            conn,
            None,
            game.EVENT_TEAMS_PROGRESS_RESET,
            f"teams_count={count}",
        )
        return count


def reset_team_progress(conn: sqlite3.Connection, team_id: int) -> bool:
    """Reset gameplay progress, powerups, streak, and completion state for a single team.

    Preserves team registration, secret code, members, and bound device.
    Clears progress and hint_uses for this team.
    Returns True if team was found and reset, False if not found.
    """
    with write_tx(conn):
        team = get_team_by_id(conn, team_id)
        if not team:
            return False
        conn.execute("DELETE FROM progress WHERE team_id = ?", (team_id,))
        conn.execute("DELETE FROM hint_uses WHERE team_id = ?", (team_id,))
        conn.execute(
            """
            UPDATE teams
            SET penalty_s = 0,
                bonus_s = 0,
                radar_left = 0,
                boost_left = 0,
                radar_until = NULL,
                boost_until = NULL,
                inside_streak = 0,
                last_fix_lat = NULL,
                last_fix_lng = NULL,
                last_fix_ts = NULL,
                last_fix_accuracy = NULL,
                last_fix_test = 0,
                finished_at = NULL
            WHERE id = ?
            """,
            (team_id,),
        )
        log_event(
            conn,
            team_id,
            game.EVENT_TEAM_RESET,
            f"team_id={team_id} name={team['name']} code={team['code']}",
        )
        return True


def wipe_event_data(conn: sqlite3.Connection) -> None:
    """Wipe all teams, gameplay progress, hint uses, and event logs.

    Preserves checkpoints and settings completely intact.
    Logs nothing afterwards except that a wipe happened.
    """
    with write_tx(conn):
        conn.execute("DELETE FROM hint_uses;")
        conn.execute("DELETE FROM progress;")
        conn.execute("DELETE FROM teams;")
        conn.execute("DELETE FROM events;")
        log_event(conn, None, game.EVENT_EVENT_WIPED, "event data wiped")


def get_teams_live_positions(conn: sqlite3.Connection, now: float) -> list[dict]:
    """Retrieve live location and progress metrics for all teams.

    Never returns device hashes, team secret codes, or member rosters.
    """
    total_cps = get_checkpoint_count(conn)
    rows = conn.execute(
        """
        SELECT
            t.id,
            t.name,
            t.last_seen,
            t.last_fix_lat,
            t.last_fix_lng,
            t.last_fix_accuracy,
            t.last_fix_test,
            COUNT(p.checkpoint_id) AS cleared
        FROM teams t
        LEFT JOIN progress p ON t.id = p.team_id
        GROUP BY t.id
        ORDER BY t.name COLLATE NOCASE ASC
        """
    ).fetchall()

    results = []
    for r in rows:
        seconds_since = None
        if r["last_seen"] is not None:
            seconds_since = max(0.0, round(now - r["last_seen"], 1))

        results.append({
            "id": r["id"],
            "name": r["name"],
            "lat": r["last_fix_lat"],
            "lng": r["last_fix_lng"],
            "accuracy": r["last_fix_accuracy"],
            "seconds_since_last_seen": seconds_since,
            "cleared": r["cleared"],
            "total": total_cps,
            "is_test": bool(r["last_fix_test"]),
        })
    return results
