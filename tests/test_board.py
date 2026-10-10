"""Tests for /board page and GET /api/board public big-screen leaderboard."""

import pytest
from fastapi.testclient import TestClient

import config
import db
from main import app, invalidate_leaderboard_cache


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    """Ensure an isolated database for each test run and clear cache."""
    test_db = tmp_path / "test_board.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))
    invalidate_leaderboard_cache()


def test_board_html_page_served():
    """GET /board serves projector HTML page with correct elements."""
    client = TestClient(app)
    res = client.get("/board")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "Campus Quest" in res.text
    assert 'id="board-status-badge"' in res.text
    assert 'id="board-tbody"' in res.text
    assert 'id="board-error-banner"' in res.text


def test_api_board_empty_and_public():
    """GET /api/board requires no cookies/auth and handles empty database."""
    client = TestClient(app)
    res = client.get("/api/board")
    assert res.status_code == 200
    data = res.json()
    assert "game_state" in data
    assert data["game_state"] == "waiting"
    assert data["status_label"] == "Waiting"
    assert data["teams"] == []


def test_api_board_sanitization_no_sensitive_fields():
    """GET /api/board never contains members, team codes, device hashes, or coordinates."""
    conn = db.get_connection()
    try:
        cp1 = db.create_checkpoint(
            conn, name="Secret Spot", lat=22.693, lng=75.867, radius=30.0, clue="Find spot", hint="Near tree"
        )
        t_a, _ = db.create_team(conn, name="Cyber Hawks", members=["Alice", "Bob"])
        db.unlock_checkpoint(conn, t_a["id"], cp1["id"], unlocked_at=100.0, elapsed_s=100, is_last=False)
    finally:
        conn.close()

    invalidate_leaderboard_cache()
    client = TestClient(app)
    res = client.get("/api/board")
    assert res.status_code == 200
    data = res.json()

    assert len(data["teams"]) == 1
    team = data["teams"][0]

    # Verify expected allowed fields
    allowed_keys = {"rank", "name", "cleared", "total", "adjusted_time"}
    assert set(team.keys()) == allowed_keys
    assert team["rank"] == 1
    assert team["name"] == "Cyber Hawks"
    assert team["cleared"] == 1
    assert team["total"] == 1
    assert team["adjusted_time"] == "01:40"

    # Verify forbidden sensitive fields are strictly absent
    forbidden_keys = [
        "members",
        "code",
        "device_hash",
        "device_token",
        "lat",
        "lng",
        "radius",
        "id",
        "team_id",
        "last_seen",
        "penalty_s",
        "bonus_s",
        "inside_streak",
    ]
    for k in forbidden_keys:
        assert k not in team, f"Forbidden key '{k}' found in /api/board team response"

    # Verify JSON text does not leak member names or team codes
    json_str = res.text
    assert "Alice" not in json_str
    assert "Bob" not in json_str
    assert t_a["code"] not in json_str
    assert "22.693" not in json_str
    assert "75.867" not in json_str


def test_api_board_reflects_game_state():
    """GET /api/board reflects setup (Waiting), running (Running), and ended (Ended)."""
    conn = db.get_connection()
    try:
        # Default: setup -> Waiting
        client = TestClient(app)
        res1 = client.get("/api/board")
        assert res1.json()["game_state"] == "waiting"
        assert res1.json()["status_label"] == "Waiting"

        # Running
        db.set_setting(conn, "game_state", "running")
        res2 = client.get("/api/board")
        assert res2.json()["game_state"] == "running"
        assert res2.json()["status_label"] == "Running"

        # Ended
        db.set_setting(conn, "game_state", "ended")
        res3 = client.get("/api/board")
        assert res3.json()["game_state"] == "ended"
        assert res3.json()["status_label"] == "Ended"
    finally:
        conn.close()


def test_api_board_ranking_order():
    """GET /api/board accurately sorts by cleared count then adjusted time."""
    conn = db.get_connection()
    try:
        cp1 = db.create_checkpoint(conn, name="CP1", lat=22.693, lng=75.867, radius=30.0, clue="C1", hint="H1")
        cp2 = db.create_checkpoint(conn, name="CP2", lat=22.694, lng=75.868, radius=30.0, clue="C2", hint="H2")

        # Team 1: 2 clears, 200s
        t1, _ = db.create_team(conn, name="Team 1", members=["M1", "M2"])
        db.unlock_checkpoint(conn, t1["id"], cp1["id"], unlocked_at=100.0, elapsed_s=100, is_last=False)
        db.unlock_checkpoint(conn, t1["id"], cp2["id"], unlocked_at=200.0, elapsed_s=200, is_last=True)

        # Team 2: 1 clear, 50s
        t2, _ = db.create_team(conn, name="Team 2", members=["M3", "M4"])
        db.unlock_checkpoint(conn, t2["id"], cp1["id"], unlocked_at=50.0, elapsed_s=50, is_last=False)
    finally:
        conn.close()

    invalidate_leaderboard_cache()
    client = TestClient(app)
    res = client.get("/api/board")
    teams = res.json()["teams"]

    assert len(teams) == 2
    assert teams[0]["rank"] == 1
    assert teams[0]["name"] == "Team 1"
    assert teams[0]["cleared"] == 2

    assert teams[1]["rank"] == 2
    assert teams[1]["name"] == "Team 2"
    assert teams[1]["cleared"] == 1
