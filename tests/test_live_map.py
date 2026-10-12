"""Tests for Admin Live Team Map (Bonus 4): GET /api/gods/live and position handling."""

import time
import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
import game
from main import app
import ratelimit


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Provide an isolated database and clean rate limits for each test."""
    ratelimit.clear_rate_limits()
    test_db = tmp_path / "test_live_map.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


@pytest.fixture
def admin_client():
    """Client authenticated as administrator."""
    client = TestClient(app)
    cookie = auth.create_admin_cookie_value(config.ADMIN_USER)
    client.cookies.set(auth.ADMIN_COOKIE_NAME, cookie)
    return client


@pytest.fixture
def anon_client():
    """Unauthenticated client."""
    return TestClient(app)


def seed_checkpoints(count: int = 5):
    """Seed the database with valid checkpoints."""
    conn = db.get_connection()
    try:
        base_lat = (config.CAMPUS_BOUNDS_SW_LAT + config.CAMPUS_BOUNDS_NE_LAT) / 2.0
        base_lng = (config.CAMPUS_BOUNDS_SW_LNG + config.CAMPUS_BOUNDS_NE_LNG) / 2.0
        for i in range(1, count + 1):
            db.create_checkpoint(
                conn,
                name=f"Checkpoint {i}",
                lat=round(base_lat + (i * 0.0001), 6),
                lng=round(base_lng + (i * 0.0001), 6),
                radius=30.0,
                clue=f"Clue for checkpoint {i}",
                hint=f"Hint for checkpoint {i}",
            )
    finally:
        conn.close()


def start_game_running():
    """Start game and set started_at in the past so countdown is elapsed."""
    conn = db.get_connection()
    try:
        now = time.time()
        db.set_setting(conn, "game_state", "running")
        db.set_setting(conn, "started_at", str(now - 15.0))
    finally:
        conn.close()


def test_gods_live_endpoint_requires_admin(anon_client):
    """Unauthenticated access to GET /api/gods/live must return HTTP 401."""
    res = anon_client.get("/api/gods/live")
    assert res.status_code == 401


def test_gods_live_excludes_code_and_device_hash(admin_client, anon_client):
    """GET /api/gods/live must never return team secret codes or device hashes."""
    reg = anon_client.post(
        "/api/register",
        json={"name": "Hawks", "members": ["Aarav", "Priya"]},
    )
    assert reg.status_code == 201

    res = admin_client.get("/api/gods/live")
    assert res.status_code == 200
    teams = res.json()
    assert len(teams) >= 1
    hawks = next(t for t in teams if t["name"] == "Hawks")

    # Strictly verify secret credentials are absent
    assert "code" not in hawks
    assert "device_hash" not in hawks
    assert "members" not in hawks


def test_team_with_no_fix_returns_null_coordinates(admin_client, anon_client):
    """A registered team with no GPS ping has null coordinates and does not break the payload."""
    seed_checkpoints(5)
    reg = anon_client.post(
        "/api/register",
        json={"name": "Falcons", "members": ["Kabir", "Meera"]},
    )
    assert reg.status_code == 201

    res = admin_client.get("/api/gods/live")
    assert res.status_code == 200
    teams = res.json()
    falcon = next(t for t in teams if t["name"] == "Falcons")

    assert falcon["name"] == "Falcons"
    assert falcon["lat"] is None
    assert falcon["lng"] is None
    assert falcon["accuracy"] is None
    assert falcon["cleared"] == 0
    assert falcon["total"] == 5
    assert falcon["is_test"] is False
    assert falcon["seconds_since_last_seen"] is not None
    assert falcon["seconds_since_last_seen"] >= 0.0


def test_live_team_position_updated_on_valid_ping(admin_client, anon_client):
    """An accepted GPS ping stores latest coordinates, accuracy, and test flag."""
    seed_checkpoints(5)
    start_game_running()

    reg = anon_client.post(
        "/api/register",
        json={"name": "Eagles", "members": ["Rohan", "Ananya"]},
    )
    assert reg.status_code == 201

    now = time.time()
    ping_res = anon_client.post(
        "/api/ping",
        json={
            "lat": 22.693123,
            "lng": 75.867456,
            "accuracy": 12.5,
            "ts": now,
        },
    )
    assert ping_res.status_code == 200

    live_res = admin_client.get("/api/gods/live")
    assert live_res.status_code == 200
    eagles = next(t for t in live_res.json() if t["name"] == "Eagles")

    assert eagles["lat"] == 22.693123
    assert eagles["lng"] == 75.867456
    assert eagles["accuracy"] == 12.5
    assert eagles["is_test"] is False
    assert eagles["seconds_since_last_seen"] is not None
    assert eagles["seconds_since_last_seen"] <= 5.0


def test_live_team_position_marks_test_flag_when_test_ping(admin_client, anon_client, monkeypatch):
    """A ping with test: true records is_test: true when test mode is enabled."""
    seed_checkpoints(5)
    start_game_running()
    monkeypatch.setattr(config, "ALLOW_TEST_MODE", True)

    conn = db.get_connection()
    try:
        db.set_setting(conn, "test_mode", "1")
    finally:
        conn.close()

    reg = anon_client.post(
        "/api/register",
        json={"name": "TestOspreys", "members": ["Tester 1", "Tester 2"]},
    )
    assert reg.status_code == 201

    now = time.time()
    ping_res = anon_client.post(
        "/api/ping",
        json={
            "lat": 22.693500,
            "lng": 75.867800,
            "accuracy": 8.0,
            "ts": now,
            "test": True,
        },
    )
    assert ping_res.status_code == 200

    live_res = admin_client.get("/api/gods/live")
    assert live_res.status_code == 200
    osprey = next(t for t in live_res.json() if t["name"] == "TestOspreys")

    assert osprey["lat"] == 22.693500
    assert osprey["lng"] == 75.867800
    assert osprey["accuracy"] == 8.0
    assert osprey["is_test"] is True


def test_game_reset_clears_stored_positions(admin_client, anon_client):
    """POST /api/gods/game/reset clears all teams' stored coordinates, accuracy, and test flags."""
    seed_checkpoints(5)
    start_game_running()

    anon_client.post(
        "/api/register",
        json={"name": "Phoenix", "members": ["Member A", "Member B"]},
    )
    anon_client.post(
        "/api/ping",
        json={"lat": 22.693200, "lng": 75.867500, "accuracy": 10.0, "ts": time.time()},
    )

    # Confirm position is recorded
    before = admin_client.get("/api/gods/live").json()
    p_before = next(t for t in before if t["name"] == "Phoenix")
    assert p_before["lat"] == 22.693200

    # Reset game
    reset_res = admin_client.post("/api/gods/game/reset")
    assert reset_res.status_code == 200

    # Verify live endpoint shows empty positions
    after = admin_client.get("/api/gods/live").json()
    p_after = next(t for t in after if t["name"] == "Phoenix")
    assert p_after["lat"] is None
    assert p_after["lng"] is None
    assert p_after["accuracy"] is None
    assert p_after["is_test"] is False


def test_single_team_reset_clears_stored_positions(admin_client, anon_client):
    """POST /api/gods/teams/{id}/reset clears the target team's stored fix."""
    seed_checkpoints(5)
    start_game_running()

    anon_client.post(
        "/api/register",
        json={"name": "Griffins", "members": ["G1", "G2"]},
    )
    anon_client.post(
        "/api/ping",
        json={"lat": 22.693300, "lng": 75.867600, "accuracy": 9.0, "ts": time.time()},
    )

    before = admin_client.get("/api/gods/live").json()
    griffin = next(t for t in before if t["name"] == "Griffins")
    team_id = griffin["id"]
    assert griffin["lat"] == 22.693300

    # Reset single team
    res = admin_client.post(f"/api/gods/teams/{team_id}/reset")
    assert res.status_code == 200

    after = admin_client.get("/api/gods/live").json()
    g_after = next(t for t in after if t["id"] == team_id)
    assert g_after["lat"] is None
    assert g_after["lng"] is None
    assert g_after["accuracy"] is None
    assert g_after["is_test"] is False


def test_wipe_event_data_clears_all_teams(admin_client, anon_client):
    """POST /api/gods/wipe empties all teams and live data completely."""
    seed_checkpoints(5)
    anon_client.post(
        "/api/register",
        json={"name": "Dragons", "members": ["D1", "D2"]},
    )
    wipe_res = admin_client.post("/api/gods/wipe", json={"confirm": "WIPE"})
    assert wipe_res.status_code == 200

    live_res = admin_client.get("/api/gods/live")
    assert live_res.status_code == 200
    assert live_res.json() == []


def test_idempotent_db_migration(tmp_path):
    """Calling init_db multiple times on an existing DB is idempotent."""
    db_file = tmp_path / "idempotent_test.db"
    db.init_db(str(db_file))
    db.init_db(str(db_file))  # Must not crash

    conn = db.get_connection(str(db_file))
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(teams)").fetchall()}
        assert "last_fix_accuracy" in cols
        assert "last_fix_test" in cols
    finally:
        conn.close()
