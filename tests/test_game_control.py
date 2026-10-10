"""Tests for game lifecycle control (registration, start, end) and checkpoint locking rules."""

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
    test_db = tmp_path / "test_game_control.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


@pytest.fixture
def admin_client():
    """Return an authenticated TestClient with an admin session cookie."""
    client = TestClient(app)
    admin_cookie = auth.create_admin_cookie_value(config.ADMIN_USER)
    client.cookies.set(auth.ADMIN_COOKIE_NAME, admin_cookie)
    return client


@pytest.fixture
def anon_client():
    """Return an unauthenticated TestClient without admin credentials."""
    return TestClient(app)


def seed_checkpoints(count: int = 5):
    """Seed the database with N valid checkpoints inside DAVV bounds."""
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
                story=f"Story for checkpoint {i}",
            )
    finally:
        conn.close()


# --- 1. Authorization & Security on Game Control Endpoints ---


def test_game_control_endpoints_require_admin(anon_client):
    """Unauthenticated requests to admin control endpoints must return HTTP 401."""
    assert anon_client.post("/api/gods/registration/open").status_code == 401
    assert anon_client.post("/api/gods/registration/close").status_code == 401
    assert anon_client.post("/api/gods/game/start").status_code == 401
    assert anon_client.post("/api/gods/game/end").status_code == 401
    assert anon_client.get("/api/gods/game/status").status_code == 401


# --- 2. Registration Open / Close Control ---


def test_registration_toggle_flow(admin_client, anon_client):
    """Admin can open and close registration, controlling player /api/register access."""
    # Close registration
    close_res = admin_client.post("/api/gods/registration/close")
    assert close_res.status_code == 200
    assert close_res.json()["registration_open"] is False

    # Player registration should now be blocked (403)
    reg_fail = anon_client.post(
        "/api/register",
        json={"name": "Hawks", "members": ["Aarav", "Priya"]},
    )
    assert reg_fail.status_code == 403

    # Open registration
    open_res = admin_client.post("/api/gods/registration/open")
    assert open_res.status_code == 200
    assert open_res.json()["registration_open"] is True

    # Player registration should now succeed (201)
    reg_ok = anon_client.post(
        "/api/register",
        json={"name": "Hawks", "members": ["Aarav", "Priya"]},
    )
    assert reg_ok.status_code == 201


# --- 3. Game Start & End Rules ---


def test_start_game_refused_with_insufficient_checkpoints(admin_client):
    """Start must be rejected with 400 when fewer than MIN_CHECKPOINTS exist."""
    # Database starts empty (0 checkpoints)
    res = admin_client.post("/api/gods/game/start")
    assert res.status_code == 400
    assert f"at least {config.MIN_CHECKPOINTS} checkpoints required" in res.json()["detail"]


def test_start_game_success_sets_running_and_countdown(admin_client):
    """When checkpoints >= MIN_CHECKPOINTS, start sets running state and future started_at."""
    seed_checkpoints(count=config.MIN_CHECKPOINTS)

    before = time.time()
    res = admin_client.post("/api/gods/game/start")
    assert res.status_code == 200
    data = res.json()
    assert data["game_state"] == "running"
    assert data["countdown_s"] == config.COUNTDOWN_S
    # started_at should be approximately server_time + COUNTDOWN_S
    expected_start = before + config.COUNTDOWN_S
    assert abs(data["started_at"] - expected_start) < 2.0
    assert data["started_at_ms"] == int(data["started_at"] * 1000)

    # Double start is rejected
    res2 = admin_client.post("/api/gods/game/start")
    assert res2.status_code == 400
    assert "already running" in res2.json()["detail"]


def test_end_game_sets_ended_state(admin_client):
    """Ending game sets game_state = 'ended' and rejects repeated end attempts."""
    seed_checkpoints(count=config.MIN_CHECKPOINTS)
    admin_client.post("/api/gods/game/start")

    res = admin_client.post("/api/gods/game/end")
    assert res.status_code == 200
    assert res.json()["game_state"] == "ended"

    # Repeated end call is rejected
    res_repeat = admin_client.post("/api/gods/game/end")
    assert res_repeat.status_code == 400
    assert "already ended" in res_repeat.json()["detail"]


# --- 4. Locking Rule on Checkpoints ---


def test_checkpoint_modifications_allowed_before_start(admin_client):
    """In 'setup' state, full creation, updating coordinates/order, and deletion are allowed."""
    seed_checkpoints(count=1)
    base_lat = round((config.CAMPUS_BOUNDS_SW_LAT + config.CAMPUS_BOUNDS_NE_LAT) / 2.0, 6)
    base_lng = round((config.CAMPUS_BOUNDS_SW_LNG + config.CAMPUS_BOUNDS_NE_LNG) / 2.0, 6)

    # Checkpoint can be edited completely
    put_res = admin_client.put(
        "/api/gods/checkpoints/1",
        json={
            "name": "Updated Spot",
            "lat": base_lat,
            "lng": base_lng,
            "radius": 45.0,
            "position": 1,
            "clue": "New clue",
            "hint": "New hint",
            "story": "New story",
        },
    )
    assert put_res.status_code == 200
    assert put_res.json()["radius"] == 45.0

    # Checkpoint can be deleted
    del_res = admin_client.delete("/api/gods/checkpoints/1")
    assert del_res.status_code == 200


def test_checkpoint_locking_rule_after_game_starts(admin_client):
    """Once started, PUT cannot change location, radius, or order; DELETE and POST are rejected."""
    seed_checkpoints(count=config.MIN_CHECKPOINTS)
    base_lat = round((config.CAMPUS_BOUNDS_SW_LAT + config.CAMPUS_BOUNDS_NE_LAT) / 2.0, 6)
    base_lng = round((config.CAMPUS_BOUNDS_SW_LNG + config.CAMPUS_BOUNDS_NE_LNG) / 2.0, 6)
    cp1_lat = round(base_lat + 0.0001, 6)
    cp1_lng = round(base_lng + 0.0001, 6)

    # Start the game
    start_res = admin_client.post("/api/gods/game/start")
    assert start_res.status_code == 200

    # 1. Attempt to change latitude -> 400
    bad_lat = admin_client.put(
        "/api/gods/checkpoints/1",
        json={
            "name": "Checkpoint 1",
            "lat": round(cp1_lat + 0.0005, 6),  # Changed
            "lng": cp1_lng,
            "radius": 30.0,
            "position": 1,
            "clue": "Clue 1",
            "hint": "Hint 1",
        },
    )
    assert bad_lat.status_code == 400
    assert "locked" in bad_lat.json()["detail"].lower()

    # 2. Attempt to change radius -> 400
    bad_radius = admin_client.put(
        "/api/gods/checkpoints/1",
        json={
            "name": "Checkpoint 1",
            "lat": cp1_lat,
            "lng": cp1_lng,
            "radius": 50.0,  # Changed from 30
            "position": 1,
            "clue": "Clue 1",
            "hint": "Hint 1",
        },
    )
    assert bad_radius.status_code == 400
    assert "locked" in bad_radius.json()["detail"].lower()

    # 3. Attempt to change order (position) -> 400
    bad_pos = admin_client.put(
        "/api/gods/checkpoints/1",
        json={
            "name": "Checkpoint 1",
            "lat": cp1_lat,
            "lng": cp1_lng,
            "radius": 30.0,
            "position": 2,  # Changed from 1
            "clue": "Clue 1",
            "hint": "Hint 1",
        },
    )
    assert bad_pos.status_code == 400
    assert "locked" in bad_pos.json()["detail"].lower()

    # 4. Attempt to delete checkpoint -> 400
    del_res = admin_client.delete("/api/gods/checkpoints/1")
    assert del_res.status_code == 400
    assert "cannot be deleted once the game has started" in del_res.json()["detail"]

    # 5. Attempt to add a new checkpoint -> 400
    post_res = admin_client.post(
        "/api/gods/checkpoints",
        json={
            "name": "Late Checkpoint",
            "lat": cp1_lat,
            "lng": cp1_lng,
            "radius": 30.0,
            "clue": "Late clue",
            "hint": "Late hint",
        },
    )
    assert post_res.status_code == 400
    assert "Cannot add checkpoints once the game has started" in post_res.json()["detail"]

    # 6. BUT updating only clue, hint, and story succeeds!
    text_edit = admin_client.put(
        "/api/gods/checkpoints/1",
        json={
            "name": "Checkpoint 1",
            "lat": cp1_lat,
            "lng": cp1_lng,
            "radius": 30.0,
            "position": 1,
            "clue": "Updated clue text during active game",
            "hint": "Updated hint text during active game",
            "story": "Updated historical fact",
        },
    )
    assert text_edit.status_code == 200
    updated = text_edit.json()
    assert updated["clue"] == "Updated clue text during active game"
    assert updated["hint"] == "Updated hint text during active game"
    assert updated["story"] == "Updated historical fact"


# --- 5. Player GET /api/state returns server time and countdown ---


def test_api_state_returns_server_timestamps_and_game_state(anon_client, admin_client):
    """GET /api/state returns server_now_ms, started_at_ms, and game_state."""
    # Register team
    reg_res = anon_client.post(
        "/api/register",
        json={"name": "Wolves", "members": ["Dia", "Kabir"]},
    )
    assert reg_res.status_code == 201

    # Before start
    state_setup = anon_client.get("/api/state")
    assert state_setup.status_code == 200
    data_setup = state_setup.json()
    assert data_setup["game_state"] == "setup"
    assert "server_now_ms" in data_setup
    assert data_setup["started_at_ms"] is None

    # Start game
    seed_checkpoints(count=config.MIN_CHECKPOINTS)
    admin_client.post("/api/gods/game/start")

    # After start
    state_running = anon_client.get("/api/state")
    assert state_running.status_code == 200
    data_running = state_running.json()
    assert data_running["game_state"] == "running"
    assert isinstance(data_running["server_now_ms"], int)
    assert isinstance(data_running["started_at_ms"], int)
    assert data_running["started_at_ms"] > data_running["server_now_ms"]
