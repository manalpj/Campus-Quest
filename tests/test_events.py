"""Tests for audit event logging, security rules, and GET /api/gods/events."""

import json
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
    test_db = tmp_path / "test_events.db"
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


def test_log_event_stores_server_time_and_allows_null_team():
    """db.log_event records current timestamp, allows NULL team_id, and handles JSON details."""
    conn = db.get_connection()
    try:
        t_before = time.time()
        db.log_event(conn, None, game.EVENT_GAME_STARTED, {"countdown_s": 10})
        t_after = time.time()

        events = db.get_latest_events(conn, limit=10)
        assert len(events) == 1
        ev = events[0]
        assert ev["team_id"] is None
        assert ev["type"] == game.EVENT_GAME_STARTED
        assert t_before <= ev["ts"] <= t_after
        parsed_detail = json.loads(ev["detail"])
        assert parsed_detail["countdown_s"] == 10
    finally:
        conn.close()


def test_failed_admin_login_logs_event_without_password_or_username(anon_client):
    """Failed admin login logs an event with client IP and result, never password or username."""
    secret_pass = "super_secret_sensitive_pass_123"
    attempted_user = "intruder_user"

    res = anon_client.post(
        "/api/gods/login",
        json={"username": attempted_user, "password": secret_pass},
    )
    assert res.status_code == 401

    conn = db.get_connection()
    try:
        events = db.get_latest_events(conn, limit=10)
        assert len(events) == 1
        ev = events[0]
        assert ev["team_id"] is None
        assert ev["type"] == game.EVENT_ADMIN_LOGIN_FAILURE
        detail = ev["detail"]
        assert "result=failed" in detail
        assert "ip=" in detail
        # Strictly verify sensitive information is never logged
        assert secret_pass not in detail
        assert attempted_user not in detail
    finally:
        conn.close()


def test_successful_admin_login_logs_event(anon_client):
    """Successful admin login logs admin_login_success without passwords or cookies."""
    res = anon_client.post(
        "/api/gods/login",
        json={"username": config.ADMIN_USER, "password": config.ADMIN_PASS},
    )
    assert res.status_code == 200

    conn = db.get_connection()
    try:
        events = db.get_latest_events(conn, limit=10)
        assert len(events) == 1
        ev = events[0]
        assert ev["team_id"] is None
        assert ev["type"] == game.EVENT_ADMIN_LOGIN_SUCCESS
        assert "ip=" in ev["detail"]
        assert config.ADMIN_PASS not in ev["detail"]
    finally:
        conn.close()


def test_checkpoint_unlock_writes_event(admin_client, anon_client):
    """Unlocking a checkpoint records a checkpoint_unlocked event inside the same transaction."""
    conn = db.get_connection()
    try:
        # Create 5 checkpoints inside campus
        base_lat = (config.CAMPUS_BOUNDS_SW_LAT + config.CAMPUS_BOUNDS_NE_LAT) / 2.0
        base_lng = (config.CAMPUS_BOUNDS_SW_LNG + config.CAMPUS_BOUNDS_NE_LNG) / 2.0
        cp_ids = []
        for i in range(1, 6):
            cp = db.create_checkpoint(
                conn,
                name=f"Spot {i}",
                lat=round(base_lat + (i * 0.0001), 6),
                lng=round(base_lng + (i * 0.0001), 6),
                radius=30.0,
                clue=f"Clue {i}",
                hint=f"Hint {i}",
            )
            cp_ids.append(cp["id"])
    finally:
        conn.close()

    # Register team
    reg_res = anon_client.post("/api/register", json={"name": "Explorers", "members": ["Alice", "Bob"]})
    assert reg_res.status_code == 201
    team_data = reg_res.json()
    team_id = team_data["id"]

    # Start game
    start_res = admin_client.post("/api/gods/game/start")
    assert start_res.status_code == 200

    # Ensure started_at is now past
    conn = db.get_connection()
    try:
        db.set_setting(conn, "started_at", str(time.time() - 10))
    finally:
        conn.close()

    # Ping twice inside checkpoint 1 radius to trigger unlock
    first_cp = db.get_checkpoint_by_id(db.get_connection(), cp_ids[0])
    ping_payload = {
        "lat": first_cp["lat"],
        "lng": first_cp["lng"],
        "accuracy": 5.0,
    }
    p1 = anon_client.post("/api/ping", json=ping_payload)
    assert p1.status_code == 200
    p2 = anon_client.post("/api/ping", json=ping_payload)
    assert p2.status_code == 200
    assert p2.json()["status"] == "unlocked"

    # Verify event was logged
    conn = db.get_connection()
    try:
        events = db.get_latest_events(conn, limit=20)
        types = [e["type"] for e in events]
        assert game.EVENT_CHECKPOINT_UNLOCKED in types
        unlock_event = next(e for e in events if e["type"] == game.EVENT_CHECKPOINT_UNLOCKED)
        assert unlock_event["team_id"] == team_id
        assert f"checkpoint_id={cp_ids[0]}" in unlock_event["detail"]
    finally:
        conn.close()


def test_hint_and_radar_powerup_logging(admin_client, anon_client):
    """Using hint and radar logs hint_used and radar_used events."""
    conn = db.get_connection()
    try:
        base_lat = (config.CAMPUS_BOUNDS_SW_LAT + config.CAMPUS_BOUNDS_NE_LAT) / 2.0
        base_lng = (config.CAMPUS_BOUNDS_SW_LNG + config.CAMPUS_BOUNDS_NE_LNG) / 2.0
        for i in range(1, 6):
            db.create_checkpoint(
                conn,
                name=f"Spot {i}",
                lat=round(base_lat + (i * 0.0001), 6),
                lng=round(base_lng + (i * 0.0001), 6),
                radius=30.0,
                clue=f"Clue {i}",
                hint=f"Hint {i}",
            )
    finally:
        conn.close()

    reg_res = anon_client.post("/api/register", json={"name": "Navigators", "members": ["Carol", "Dave"]})
    team_id = reg_res.json()["id"]

    admin_client.post("/api/gods/game/start")
    conn = db.get_connection()
    try:
        db.set_setting(conn, "started_at", str(time.time() - 10))
        # Give radar powerup
        conn.execute("UPDATE teams SET radar_left = 1 WHERE id = ?", (team_id,))
    finally:
        conn.close()

    # Use hint
    hint_res = anon_client.post("/api/powerup/hint")
    assert hint_res.status_code == 200

    # Use radar
    radar_res = anon_client.post("/api/powerup/radar")
    assert radar_res.status_code == 200

    conn = db.get_connection()
    try:
        events = db.get_latest_events(conn, limit=20)
        types = [e["type"] for e in events]
        assert game.EVENT_HINT_USED in types
        assert game.EVENT_RADAR_USED in types

        hint_event = next(e for e in events if e["type"] == game.EVENT_HINT_USED)
        assert hint_event["team_id"] == team_id
        assert "penalty_s=" in hint_event["detail"]

        radar_event = next(e for e in events if e["type"] == game.EVENT_RADAR_USED)
        assert radar_event["team_id"] == team_id
        assert "duration_s=" in radar_event["detail"]
    finally:
        conn.close()


def test_gods_events_endpoint_permissions_and_pagination(admin_client, anon_client):
    """GET /api/gods/events requires admin, orders newest first, and respects limit."""
    # 1. Unauthenticated request rejected
    assert anon_client.get("/api/gods/events").status_code == 401

    # 2. Insert test events
    conn = db.get_connection()
    try:
        for i in range(15):
            db.log_event(conn, None, game.EVENT_GAME_STARTED, f"run={i}")
    finally:
        conn.close()

    # 3. Default limit returns events
    res = admin_client.get("/api/gods/events")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 15
    # Chronological check: latest insert should be first
    assert data[0]["detail"] == "run=14"
    assert data[-1]["detail"] == "run=0"

    # 4. Limit parameter works
    res_lim = admin_client.get("/api/gods/events?limit=5")
    assert res_lim.status_code == 200
    assert len(res_lim.json()) == 5
    assert res_lim.json()[0]["detail"] == "run=14"
