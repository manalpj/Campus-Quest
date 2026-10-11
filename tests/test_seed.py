"""Tests for seed.py database population and CLI safety flags."""

import sys
import pytest

import config
import db
import seed


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    """Ensure a temporary isolated database for every seed test."""
    test_db = tmp_path / "test_seed.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))
    return str(test_db)


def test_seed_sample_checkpoints_default(clean_test_db, monkeypatch):
    """Default seed_database populates sample checkpoints."""
    monkeypatch.setattr(config, "ENV", "development")
    count = seed.seed_database(db_path=clean_test_db, demo=False, force=False)
    assert count == len(seed.SAMPLE_CHECKPOINTS)

    conn = db.get_connection(clean_test_db)
    rows = conn.execute("SELECT name, position, kind FROM checkpoints ORDER BY position ASC").fetchall()
    conn.close()

    assert len(rows) == len(seed.SAMPLE_CHECKPOINTS)
    assert rows[0]["name"] == "A-Block"
    assert rows[0]["position"] == 1


def test_seed_demo_checkpoints(clean_test_db, monkeypatch):
    """Passing demo=True populates the real draft checkpoints from CHECKPOINTS_DRAFT.md."""
    monkeypatch.setattr(config, "ENV", "development")
    count = seed.seed_database(db_path=clean_test_db, demo=True, force=False)
    assert count == len(seed.DEMO_CHECKPOINTS)

    conn = db.get_connection(clean_test_db)
    rows = conn.execute("SELECT name, position, kind FROM checkpoints ORDER BY position ASC").fetchall()
    conn.close()

    assert len(rows) == 6
    names = [r["name"] for r in rows]
    assert names == ["A-Block", "B-Block", "D-Block", "E-Block", "F-Block", "Backstage"]


def test_seed_refuses_production_without_force(clean_test_db, monkeypatch):
    """seed_database must strictly refuse execution when ENV=production unless force=True."""
    monkeypatch.setattr(config, "ENV", "production")

    with pytest.raises(RuntimeError, match="Refusing to seed database in production without --force"):
        seed.seed_database(db_path=clean_test_db, demo=True, force=False)


def test_seed_allows_production_with_force(clean_test_db, monkeypatch):
    """seed_database succeeds in production when force=True is passed."""
    monkeypatch.setattr(config, "ENV", "production")

    count = seed.seed_database(db_path=clean_test_db, demo=True, force=True)
    assert count == len(seed.DEMO_CHECKPOINTS)


def test_seed_main_cli_arguments(clean_test_db, monkeypatch):
    """Verify CLI main entry point parses --demo and custom --db-path cleanly."""
    monkeypatch.setattr(config, "ENV", "development")
    monkeypatch.setattr(sys, "argv", ["seed.py", "--demo", "--db-path", clean_test_db])

    seed.main()

    conn = db.get_connection(clean_test_db)
    rows = conn.execute("SELECT COUNT(*) AS total FROM checkpoints WHERE kind = 'route'").fetchone()
    conn.close()

    assert rows["total"] == len(seed.DEMO_CHECKPOINTS)
