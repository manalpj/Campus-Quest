"""Tests for SQLite database schema, transactions, connection handling, and seed script."""

import sqlite3
import pytest

import config
import db
import seed


@pytest.fixture
def test_db_path(tmp_path):
    """Provide a path to a temporary database file."""
    return str(tmp_path / "test_quest.db")


def test_init_db_creates_tables_and_seeds_settings(test_db_path):
    """init_db creates required tables and seeds default settings."""
    db.init_db(test_db_path)

    conn = db.get_connection(test_db_path)
    try:
        # Check settings
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        settings_dict = {row["key"]: row["value"] for row in rows}
        assert settings_dict["game_state"] == "setup"
        assert settings_dict["registration_open"] == "1"
        assert settings_dict["started_at"] == ""
        assert settings_dict["test_mode"] == "0"

        # Check required tables exist
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        expected_tables = {"settings", "checkpoints", "teams", "progress", "hint_uses", "events"}
        assert expected_tables.issubset(table_names)
    finally:
        conn.close()


def test_init_db_twice_without_error(test_db_path):
    """Calling init_db multiple times is idempotent and preserves modified settings."""
    db.init_db(test_db_path)

    conn = db.get_connection(test_db_path)
    try:
        # Mutate a setting
        with db.write_tx(conn):
            conn.execute("UPDATE settings SET value = 'running' WHERE key = 'game_state'")
    finally:
        conn.close()

    # Re-run init_db
    db.init_db(test_db_path)

    conn = db.get_connection(test_db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'game_state'").fetchone()
        assert row["value"] == "running", "init_db overwrote an existing setting value"
    finally:
        conn.close()


def test_connection_pragmas(test_db_path):
    """Connections have WAL mode, busy_timeout=5000, and foreign_keys=ON."""
    db.init_db(test_db_path)
    conn = db.get_connection(test_db_path)
    try:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal"

        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert busy_timeout == 5000

        foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert foreign_keys == 1
    finally:
        conn.close()


def test_write_tx_commits_on_success(test_db_path):
    """write_tx commits changes to the database on normal exit."""
    db.init_db(test_db_path)
    conn = db.get_connection(test_db_path)
    try:
        with db.write_tx(conn):
            conn.execute(
                "INSERT INTO teams (name, code, members) VALUES (?, ?, ?)",
                ("Alpha", "A1B2", '["Alice", "Bob"]'),
            )

        # Verify team is saved
        row = conn.execute("SELECT name, code FROM teams WHERE code = 'A1B2'").fetchone()
        assert row is not None
        assert row["name"] == "Alpha"
    finally:
        conn.close()


def test_write_tx_rolls_back_on_error(test_db_path):
    """write_tx rolls back all operations if an exception occurs."""
    db.init_db(test_db_path)
    conn = db.get_connection(test_db_path)
    try:
        with pytest.raises(RuntimeError, match="Simulated failure"):
            with db.write_tx(conn):
                conn.execute(
                    "INSERT INTO teams (name, code, members) VALUES (?, ?, ?)",
                    ("Beta", "B2C3", '["Charlie", "Dave"]'),
                )
                raise RuntimeError("Simulated failure")

        # Verify transaction rolled back completely
        row = conn.execute("SELECT * FROM teams WHERE code = 'B2C3'").fetchone()
        assert row is None, "Failed write_tx transaction was not rolled back"
    finally:
        conn.close()


def test_progress_unique_constraint(test_db_path):
    """progress table enforces UNIQUE(team_id, checkpoint_id)."""
    db.init_db(test_db_path)
    conn = db.get_connection(test_db_path)
    try:
        with db.write_tx(conn):
            conn.execute(
                "INSERT INTO teams (id, name, code, members) VALUES (1, 'Gamma', 'G3H4', '[\"Eve\"]')"
            )
            conn.execute(
                """
                INSERT INTO checkpoints (id, name, lat, lng, radius, position, clue, hint, kind)
                VALUES (1, 'Spot 1', 22.693, 75.867, 30.0, 1, 'Clue 1', 'Hint 1', 'route')
                """
            )
            conn.execute(
                """
                INSERT INTO progress (team_id, checkpoint_id, unlocked_at, elapsed_s, how)
                VALUES (1, 1, 100.0, 50, 'unlocked')
                """
            )

        # Attempting duplicate progress insert must fail
        with pytest.raises(sqlite3.IntegrityError):
            with db.write_tx(conn):
                conn.execute(
                    """
                    INSERT INTO progress (team_id, checkpoint_id, unlocked_at, elapsed_s, how)
                    VALUES (1, 1, 120.0, 70, 'unlocked')
                    """
                )
    finally:
        conn.close()


def test_foreign_keys_rejected_for_orphan_progress(test_db_path):
    """Foreign key enforcement prevents inserting progress for non-existent team/checkpoint."""
    db.init_db(test_db_path)
    conn = db.get_connection(test_db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            with db.write_tx(conn):
                conn.execute(
                    """
                    INSERT INTO progress (team_id, checkpoint_id, unlocked_at, elapsed_s, how)
                    VALUES (999, 999, 100.0, 50, 'unlocked')
                    """
                )
    finally:
        conn.close()


def test_seed_database_success(test_db_path, monkeypatch):
    """seed_database successfully creates 6 checkpoints around campus."""
    monkeypatch.setattr(config, "ENV", "development")

    count = seed.seed_database(db_path=test_db_path)
    assert count == 6

    conn = db.get_connection(test_db_path)
    try:
        rows = conn.execute(
            "SELECT name, lat, lng, radius, position, kind FROM checkpoints ORDER BY position"
        ).fetchall()
        assert len(rows) == 6
        positions = [r["position"] for r in rows]
        assert positions == [1, 2, 3, 4, 5, 6]

        for r in rows:
            assert r["radius"] == 30.0
            assert r["kind"] == "route"
            # Verify coordinates are valid campus coordinates
            assert 22.6700 <= r["lat"] <= 22.7100
            assert 75.8500 <= r["lng"] <= 75.8900
    finally:
        conn.close()


def test_seed_database_refuses_in_production(test_db_path, monkeypatch):
    """seed_database refuses to run when ENV is 'production'."""
    monkeypatch.setattr(config, "ENV", "production")

    with pytest.raises(RuntimeError, match="Refusing to seed database in production"):
        seed.seed_database(db_path=test_db_path)


def test_get_db_dependency(tmp_path, monkeypatch):
    """get_db yields a connection and closes it upon exit."""
    db_file = str(tmp_path / "dep_test.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    db.init_db()

    gen = db.get_db()
    conn = next(gen)
    assert isinstance(conn, sqlite3.Connection)
    row = conn.execute("SELECT value FROM settings WHERE key = 'game_state'").fetchone()
    assert row["value"] == "setup"

    with pytest.raises(StopIteration):
        next(gen)

    # Verify connection was closed
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_fastapi_lifespan_initializes_db(tmp_path, monkeypatch):
    """FastAPI lifespan startup hook runs init_db automatically."""
    from fastapi.testclient import TestClient
    from main import app

    db_file = str(tmp_path / "lifespan_test.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)

    with TestClient(app) as client:
        res = client.get("/healthz")
        assert res.status_code == 200

    conn = db.get_connection(db_file)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'game_state'").fetchone()
        assert row["value"] == "setup"
    finally:
        conn.close()


def test_get_db_cross_thread_close(tmp_path, monkeypatch):
    """get_db allows closing connection from another thread as done in AnyIO threadpool."""
    import threading

    db_file = str(tmp_path / "thread_test.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    db.init_db()

    gen = db.get_db()
    conn = next(gen)

    err = None

    def close_conn():
        nonlocal err
        try:
            with pytest.raises(StopIteration):
                next(gen)
        except Exception as e:
            err = e

    t = threading.Thread(target=close_conn)
    t.start()
    t.join()

    assert err is None, f"Cross-thread close failed with: {err}"


