"""Tests for GET /api/leaderboard: ranking, time adjustment, and in-memory caching."""

import time
import pytest
from fastapi.testclient import TestClient

import config
import db
from main import app, invalidate_leaderboard_cache


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    """Ensure an isolated database for each test run and clear cache."""
    test_db = tmp_path / "test_leaderboard.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))
    invalidate_leaderboard_cache()


def test_leaderboard_empty():
    """Empty database returns empty list."""
    client = TestClient(app)
    res = client.get("/api/leaderboard")
    assert res.status_code == 200
    assert res.json() == []


def test_leaderboard_ranking_rules():
    """Verify sorting order: count (desc), adjusted time (asc), earlier unlock (asc), 0-clears at bottom."""
    conn = db.get_connection()
    try:
        # Create 3 checkpoints
        cp1 = db.create_checkpoint(conn, name="CP1", lat=22.693, lng=75.867, radius=30.0, clue="C1", hint="H1")
        cp2 = db.create_checkpoint(conn, name="CP2", lat=22.694, lng=75.868, radius=30.0, clue="C2", hint="H2")
        cp3 = db.create_checkpoint(conn, name="CP3", lat=22.695, lng=75.869, radius=30.0, clue="C3", hint="H3")

        # Team A: 2 clears, elapsed=200s, penalty=0s -> adj=200s
        t_a, _ = db.create_team(conn, name="Team A", members=["A1", "A2"])
        db.unlock_checkpoint(conn, t_a["id"], cp1["id"], unlocked_at=100.0, elapsed_s=100, is_last=False)
        db.unlock_checkpoint(conn, t_a["id"], cp2["id"], unlocked_at=200.0, elapsed_s=200, is_last=False)

        # Team B: 1 clear, elapsed=50s, penalty=0s -> adj=50s (Faster than A, but fewer checkpoints)
        t_b, _ = db.create_team(conn, name="Team B", members=["B1", "B2"])
        db.unlock_checkpoint(conn, t_b["id"], cp1["id"], unlocked_at=50.0, elapsed_s=50, is_last=False)

        # Team C: 1 clear, elapsed=40s, penalty=60s (+1 hint) -> adj=100s (Slower adjusted time than B)
        t_c, _ = db.create_team(conn, name="Team C", members=["C1", "C2"])
        db.unlock_checkpoint(conn, t_c["id"], cp1["id"], unlocked_at=40.0, elapsed_s=40, is_last=False)
        with db.write_tx(conn):
            conn.execute("UPDATE teams SET penalty_s = 60 WHERE id = ?", (t_c["id"],))

        # Team D: 1 clear, elapsed=50s, penalty=0s, unlocked at 60.0 (Ties B on count & adj, but unlocked later than B)
        t_d, _ = db.create_team(conn, name="Team D", members=["D1", "D2"])
        db.unlock_checkpoint(conn, t_d["id"], cp1["id"], unlocked_at=60.0, elapsed_s=50, is_last=False)

        # Team E: 0 clears
        t_e, _ = db.create_team(conn, name="Team E", members=["E1", "E2"])
    finally:
        conn.close()

    invalidate_leaderboard_cache()
    client = TestClient(app)
    res = client.get("/api/leaderboard")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 5

    # 1st: Team A (2 clears beats 1 clear)
    assert data[0]["name"] == "Team A"
    assert data[0]["rank"] == 1
    assert data[0]["cleared"] == 2
    assert data[0]["total"] == 3
    assert data[0]["adjusted_time_s"] == 200
    assert data[0]["adjusted_time"] == "03:20"

    # 2nd: Team B (1 clear, adj=50s, unlocked at 50.0)
    assert data[1]["name"] == "Team B"
    assert data[1]["rank"] == 2
    assert data[1]["cleared"] == 1
    assert data[1]["adjusted_time_s"] == 50

    # 3rd: Team D (1 clear, adj=50s, unlocked at 60.0 -> broken by later unlock)
    assert data[2]["name"] == "Team D"
    assert data[2]["rank"] == 3
    assert data[2]["cleared"] == 1
    assert data[2]["adjusted_time_s"] == 50

    # 4th: Team C (1 clear, adj=100s)
    assert data[3]["name"] == "Team C"
    assert data[3]["rank"] == 4
    assert data[3]["cleared"] == 1
    assert data[3]["adjusted_time_s"] == 100

    # 5th: Team E (0 clears at the bottom)
    assert data[4]["name"] == "Team E"
    assert data[4]["rank"] == 5
    assert data[4]["cleared"] == 0


def test_leaderboard_caching_and_invalidation():
    """Leaderboard serves cached data within 1 second and is invalidated on unlock."""
    conn = db.get_connection()
    try:
        cp1 = db.create_checkpoint(conn, name="CP1", lat=22.693, lng=75.867, radius=30.0, clue="C1", hint="H1")
        t_a, _ = db.create_team(conn, name="Team Alpha", members=["A1", "A2"])
    finally:
        conn.close()

    invalidate_leaderboard_cache()
    client = TestClient(app)

    # 1. First fetch
    res1 = client.get("/api/leaderboard")
    assert len(res1.json()) == 1
    assert res1.json()[0]["name"] == "Team Alpha"

    # 2. Add another team directly in DB without clearing cache
    conn = db.get_connection()
    try:
        db.create_team(conn, name="Team Beta", members=["B1", "B2"])
    finally:
        conn.close()

    # Immediate second fetch hits cache: Team Beta is not yet present
    res2 = client.get("/api/leaderboard")
    assert len(res2.json()) == 1

    # 3. Invalidate cache: Team Beta now appears
    invalidate_leaderboard_cache()
    res3 = client.get("/api/leaderboard")
    assert len(res3.json()) == 2
