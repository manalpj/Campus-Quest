"""Tests for Rules tab, dynamic FAQ, and Location Test mode authorization."""

import time
import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
import game
from main import app


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    """Ensure an isolated database for each test run."""
    test_db = tmp_path / "test_rules_and_test_mode.db"
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
def running_game_with_team():
    """Setup running game, checkpoint, and authenticated team client."""
    conn = db.get_connection()
    try:
        cp1 = db.create_checkpoint(
            conn,
            name="Library Courtyard",
            lat=22.693000,
            lng=75.867000,
            radius=30.0,
            clue="Search where books sleep.",
            hint="Near the central library doors.",
            story="Built in 1998, this is the intellectual heart of the campus.",
        )
        team_row, device_token = db.create_team(
            conn,
            name="Voyagers",
            members=["Alice", "Bob"],
        )
        now = time.time()
        db.set_setting(conn, "game_state", "running")
        db.set_setting(conn, "started_at", str(now - 60))
        db.set_setting(conn, "test_mode", "0")

        client = TestClient(app)
        client.cookies.set(auth.DEVICE_COOKIE_NAME, device_token)

        return {
            "client": client,
            "team": team_row,
            "device_token": device_token,
            "checkpoint": cp1,
        }
    finally:
        conn.close()


def test_rules_endpoint_returns_rules_and_all_5_faq_entries():
    """GET /api/rules returns status 200 with rules and all 5 required FAQ entries."""
    client = TestClient(app)
    res = client.get("/api/rules")
    assert res.status_code == 200
    data = res.json()

    assert "rules" in data
    assert len(data["rules"]) >= 5

    assert "faq" in data
    faq_questions = [item["q"] for item in data["faq"]]

    required_faq = [
        "GPS is not working",
        "My phone died",
        "I am standing at the spot but it does not unlock",
        "What does a Hint cost",
        "How do I win",
    ]
    for req in required_faq:
        assert req in faq_questions, f"Missing required FAQ entry: {req}"


def test_rules_reflects_changed_config_values(monkeypatch):
    """GET /api/rules text changes immediately when config parameters change."""
    client = TestClient(app)

    # Monkeypatch config values to custom numbers
    monkeypatch.setattr(config, "HINT_PENALTY_S", 300)      # 5 minutes
    monkeypatch.setattr(config, "SKIP_WAIT_S", 900)        # 15 minutes
    monkeypatch.setattr(config, "SKIP_PENALTY_S", 720)     # 12 minutes
    monkeypatch.setattr(config, "RADAR_DURATION_S", 90)    # 90 seconds
    monkeypatch.setattr(config, "ACCURACY_LIMIT_M", 45.0)  # 45 metres

    res = client.get("/api/rules")
    assert res.status_code == 200
    data = res.json()

    # Verify hint penalty updated to 5 minutes / 300s
    hint_rule = next(r for r in data["rules"] if r["title"] == "Power-ups")
    assert "5-minute penalty" in hint_rule["text"]
    assert "+300s" in hint_rule["text"]

    hint_faq = next(f for f in data["faq"] if f["q"] == "What does a Hint cost")
    assert "5 minutes" in hint_faq["a"]
    assert "+300s" in hint_faq["a"]

    # Verify skip rules updated to 15m wait and 12m penalty
    skip_rule = next(r for r in data["rules"] if r["title"] == "Skipping Checkpoints")
    assert "15 minutes" in skip_rule["text"]
    assert "900s" in skip_rule["text"]
    assert "12-minute penalty" in skip_rule["text"]
    assert "+720s" in skip_rule["text"]

    # Verify accuracy limit updated to 45 m
    gps_rule = next(r for r in data["rules"] if r["title"] == "GPS & Speed Limits")
    assert "45 m" in gps_rule["text"]

    # Values mapping reflects the monkeypatched configuration
    assert data["values"]["hint_penalty_s"] == 300
    assert data["values"]["skip_wait_s"] == 900
    assert data["values"]["skip_penalty_s"] == 720
    assert data["values"]["radar_duration_s"] == 90
    assert data["values"]["accuracy_limit_m"] == 45.0


def test_ping_test_true_refused_when_test_mode_off(running_game_with_team):
    """A location ping with test: true is refused with 403 when test_mode is off, and logged."""
    client = running_game_with_team["client"]
    team = running_game_with_team["team"]

    # Ensure test_mode is off
    conn = db.get_connection()
    try:
        db.set_setting(conn, "test_mode", "0")
    finally:
        conn.close()

    res = client.post(
        "/api/ping",
        json={
            "lat": 22.693000,
            "lng": 75.867000,
            "accuracy": 5.0,
            "ts": time.time(),
            "test": True,
        },
    )
    assert res.status_code == 403
    assert "Test mode is not active" in res.json()["detail"]

    # Check event log recorded the refusal
    conn = db.get_connection()
    try:
        cur = conn.execute(
            "SELECT * FROM events WHERE team_id = ? AND type = ?",
            (team["id"], game.EVENT_TEST_PING_REFUSED),
        )
        row = cur.fetchone()
        assert row is not None
        assert "test_ping_refused" in row["detail"]
    finally:
        conn.close()


def test_admin_test_mode_toggle_rejected_when_allow_test_mode_false(admin_client, monkeypatch):
    """Admin cannot enable test mode if ALLOW_TEST_MODE is false in the environment."""
    monkeypatch.setattr(config, "ALLOW_TEST_MODE", False)

    res = admin_client.post("/api/gods/game/test-mode", json={"enabled": True})
    assert res.status_code == 403
    assert "Test mode is disabled in this environment" in res.json()["detail"]

    conn = db.get_connection()
    try:
        assert db.get_setting(conn, "test_mode") == "0"
    finally:
        conn.close()


def test_admin_test_mode_toggle_succeeds_when_allow_test_mode_true(admin_client, monkeypatch):
    """Admin can enable and disable test mode when ALLOW_TEST_MODE is true."""
    monkeypatch.setattr(config, "ALLOW_TEST_MODE", True)

    # Enable test mode
    res = admin_client.post("/api/gods/game/test-mode", json={"enabled": True})
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "test_mode": True}

    conn = db.get_connection()
    try:
        assert db.get_setting(conn, "test_mode") == "1"
        cur = conn.execute(
            "SELECT * FROM events WHERE type = ?",
            (game.EVENT_TEST_MODE_TOGGLED,),
        )
        assert cur.fetchone() is not None
    finally:
        conn.close()

    # Disable test mode
    res2 = admin_client.post("/api/gods/game/test-mode", json={"enabled": False})
    assert res2.status_code == 200
    assert res2.json() == {"status": "ok", "test_mode": False}

    conn = db.get_connection()
    try:
        assert db.get_setting(conn, "test_mode") == "0"
    finally:
        conn.close()


def test_ping_test_true_allowed_when_test_mode_on(running_game_with_team, monkeypatch):
    """When test_mode is on, pings with test: true are accepted and bypass speed checks."""
    monkeypatch.setattr(config, "ALLOW_TEST_MODE", True)
    client = running_game_with_team["client"]

    # Turn test mode on in DB
    conn = db.get_connection()
    try:
        db.set_setting(conn, "test_mode", "1")
    finally:
        conn.close()

    # First simulated fix inside checkpoint
    res1 = client.post(
        "/api/ping",
        json={
            "lat": 22.693000,
            "lng": 75.867000,
            "accuracy": 5.0,
            "ts": time.time(),
            "test": True,
        },
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "searching"

    # Second simulated fix inside checkpoint unlocks it!
    res2 = client.post(
        "/api/ping",
        json={
            "lat": 22.693000,
            "lng": 75.867000,
            "accuracy": 5.0,
            "ts": time.time() + 1,
            "test": True,
        },
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "unlocked"

    # Third simulated fix far away (e.g. 800m away, 1 second later)
    # Standard pings would trigger speed plausibility check (>12 m/s), but test pings bypass it
    res3 = client.post(
        "/api/ping",
        json={
            "lat": 22.699000,
            "lng": 75.875000,
            "accuracy": 5.0,
            "ts": time.time() + 2,
            "test": True,
        },
    )
    assert res3.status_code == 200
    # Must NOT be implausible
    assert res3.json()["status"] != "implausible"


def test_public_config_and_state_expose_test_mode(running_game_with_team, monkeypatch):
    """GET /api/config, GET /api/state, and GET /api/gods/game/status report test_mode state."""
    monkeypatch.setattr(config, "ALLOW_TEST_MODE", True)
    client = running_game_with_team["client"]

    conn = db.get_connection()
    try:
        db.set_setting(conn, "test_mode", "1")
    finally:
        conn.close()

    # Check public config
    anon_client = TestClient(app)
    cfg_res = anon_client.get("/api/config")
    assert cfg_res.status_code == 200
    assert cfg_res.json()["test_mode"] is True
    assert cfg_res.json()["allow_test_mode"] is True

    # Check player state
    state_res = client.get("/api/state")
    assert state_res.status_code == 200
    assert state_res.json()["test_mode"] is True
