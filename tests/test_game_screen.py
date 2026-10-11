"""Tests for player game screen state endpoint and geofence privacy guarantees.

Verifies that /api/state returns current clue text and cleared checkpoints,
and strictly enforces that uncleared checkpoint coordinates and radii are
NEVER exposed to the client.
"""

import time
import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
from main import app


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    """Ensure an isolated database for each test run."""
    test_db = tmp_path / "test_game_screen.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


@pytest.fixture
def two_checkpoints_game():
    """Setup a running game with two checkpoints and a registered team."""
    conn = db.get_connection()
    try:
        cp1 = db.create_checkpoint(
            conn,
            name="Library Courtyard",
            lat=22.693000,
            lng=75.867000,
            radius=30.0,
            clue="Search where books sleep.",
            hint="Near the library entrance.",
            story="Built in 1998, holding over 100,000 volumes.",
        )
        cp2 = db.create_checkpoint(
            conn,
            name="Auditorium Lawn",
            lat=22.695000,
            lng=75.869000,
            radius=35.0,
            clue="Where applauses echo on green grass.",
            hint="Near the stage gate.",
            story="The venue for the annual tech festival.",
        )

        team_row, device_token = db.create_team(
            conn,
            name="Alpha Explorers",
            members=["Alice", "Bob"],
        )

        now = time.time()
        db.set_setting(conn, "game_state", "running")
        db.set_setting(conn, "started_at", str(now - 60))

        return {
            "cp1": dict(cp1),
            "cp2": dict(cp2),
            "team": dict(team_row),
            "token": device_token,
            "started_at": now - 60,
        }
    finally:
        conn.close()


@pytest.fixture
def player_client(two_checkpoints_game):
    """Return a TestClient authenticated with the registered team's device cookie."""
    client = TestClient(app)
    client.cookies.set(auth.DEVICE_COOKIE_NAME, two_checkpoints_game["token"])
    return client


def test_api_state_requires_authentication():
    """GET /api/state without cookie must return 401."""
    client = TestClient(app)
    res = client.get("/api/state")
    assert res.status_code == 401


def test_api_state_returns_clue_and_cleared_progress(player_client, two_checkpoints_game):
    """GET /api/state returns current clue text and initially empty cleared checkpoints."""
    res = player_client.get("/api/state")
    assert res.status_code == 200
    data = res.json()

    assert data["game_state"] == "running"
    assert data["cleared"] == 0
    assert data["total"] == 2
    assert data["finished"] is False
    # Team's first clue is cp1 clue
    assert data["current_clue"] == two_checkpoints_game["cp1"]["clue"]
    assert data["cleared_checkpoints"] == []


def test_api_state_never_leaks_uncleared_coordinates_or_radius(player_client, two_checkpoints_game):
    """Critical privacy requirement: /api/state must NEVER return next checkpoint lat, lng, or radius.

    This test comprehensively checks that neither coordinates nor radius of uncleared checkpoints
    appear anywhere in the /api/state response body, whether top-level or nested.
    """
    res = player_client.get("/api/state")
    assert res.status_code == 200
    data = res.json()

    # Top-level checks
    assert "lat" not in data
    assert "lng" not in data
    assert "radius" not in data
    assert "next_lat" not in data
    assert "next_lng" not in data
    assert "next_radius" not in data

    # Ensure cp1 coordinates do not appear in serialized JSON string
    res_text = res.text
    cp1_lat_str = str(two_checkpoints_game["cp1"]["lat"])
    cp1_lng_str = str(two_checkpoints_game["cp1"]["lng"])
    cp2_lat_str = str(two_checkpoints_game["cp2"]["lat"])
    cp2_lng_str = str(two_checkpoints_game["cp2"]["lng"])

    assert cp1_lat_str not in res_text, "Uncleared cp1 latitude leaked in /api/state!"
    assert cp1_lng_str not in res_text, "Uncleared cp1 longitude leaked in /api/state!"
    assert cp2_lat_str not in res_text, "Uncleared cp2 latitude leaked in /api/state!"
    assert cp2_lng_str not in res_text, "Uncleared cp2 longitude leaked in /api/state!"


def test_api_state_after_unlocking_checkpoint(player_client, two_checkpoints_game):
    """After unlocking cp1, /api/state reveals cp1 in cleared list and advances to cp2 clue."""
    # 2 inside pings to unlock cp1
    cp1 = two_checkpoints_game["cp1"]
    cp2 = two_checkpoints_game["cp2"]

    p1 = player_client.post("/api/ping", json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0})
    assert p1.json()["status"] == "searching"
    p2 = player_client.post("/api/ping", json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0})
    assert p2.json()["status"] == "unlocked"
    assert p2.json()["checkpoint_name"] == cp1["name"]
    assert p2.json()["story"] == cp1["story"]
    assert p2.json()["next_clue"] == cp2["clue"]

    # Poll /api/state
    res = player_client.get("/api/state")
    assert res.status_code == 200
    data = res.json()

    assert data["cleared"] == 1
    assert data["total"] == 2
    assert data["finished"] is False
    # Next clue is cp2 clue
    assert data["current_clue"] == cp2["clue"]

    # Cleared checkpoints contains cp1 only
    cleared = data["cleared_checkpoints"]
    assert len(cleared) == 1
    assert cleared[0]["name"] == cp1["name"]
    assert cleared[0]["lat"] == cp1["lat"]
    assert cleared[0]["lng"] == cp1["lng"]
    assert cleared[0]["story"] == cp1["story"]

    # Uncleared cp2 coordinates must STILL be secret!
    res_text = res.text
    cp2_lat_str = str(cp2["lat"])
    cp2_lng_str = str(cp2["lng"])
    assert cp2_lat_str not in res_text, "Uncleared cp2 latitude leaked in /api/state!"
    assert cp2_lng_str not in res_text, "Uncleared cp2 longitude leaked in /api/state!"


def test_api_state_when_all_checkpoints_completed(player_client, two_checkpoints_game):
    """When all checkpoints are cleared, /api/state marks finished=True and current_clue=None."""
    cp1 = two_checkpoints_game["cp1"]
    cp2 = two_checkpoints_game["cp2"]

    # Clear cp1
    player_client.post("/api/ping", json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0})
    player_client.post("/api/ping", json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0})

    # Simulate walking to cp2 (60s elapsed)
    conn = db.get_connection()
    try:
        now = time.time()
        with db.write_tx(conn):
            conn.execute("UPDATE teams SET last_fix_ts = ? WHERE id = ?", (now - 60.0, two_checkpoints_game["team"]["id"]))
    finally:
        conn.close()

    # Clear cp2
    player_client.post("/api/ping", json={"lat": cp2["lat"], "lng": cp2["lng"], "accuracy": 10.0})
    p_last = player_client.post("/api/ping", json={"lat": cp2["lat"], "lng": cp2["lng"], "accuracy": 10.0})
    assert p_last.json()["status"] == "unlocked"

    # Poll state
    res = player_client.get("/api/state")
    assert res.status_code == 200
    data = res.json()

    assert data["cleared"] == 2
    assert data["total"] == 2
    assert data["finished"] is True
    assert data["current_clue"] is None
    assert len(data["cleared_checkpoints"]) == 2


def test_player_ui_layout_and_navigation_drawer():
    """Verify clean UI layout: no bottom tab bar, stacked top-left controls, top-right status, and drawer menu."""
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Top-left controls: menu and leaderboard buttons stacked
    assert 'class="top-left-controls"' in html
    assert 'id="btn-nav"' in html
    assert 'id="btn-leaderboard"' in html

    # Top status HUD chips
    assert 'id="game-status-bar"' in html
    assert 'id="status-cleared"' in html
    assert 'id="status-timer"' in html
    assert 'id="gps-status"' in html

    # Bottom HUD with power-ups on bottom-left and clue card
    assert 'id="game-bottom-hud"' in html
    assert 'id="powerup-tray"' in html
    assert 'id="game-clue-card"' in html

    # Bottom 4-button tab bar is removed
    assert 'id="game-tab-bar"' not in html
    assert 'id="tab-game-map"' not in html

    # Navigation menu drawer has required options
    assert 'id="nav-overlay"' in html
    assert 'id="btn-menu-team"' in html
    assert 'id="btn-menu-history"' in html
    assert 'id="btn-menu-rules"' in html
    assert 'href="/privacy"' in html
    assert 'href="/terms"' in html

    # Checkpoint history modal exists
    assert 'id="view-history"' in html
    assert 'id="history-items-container"' in html

