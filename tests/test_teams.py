"""Tests for player team registration, device binding, join flow, and lobby state."""

import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
import game
from main import app
import ratelimit


@pytest.fixture(autouse=True)
def clean_test_env(tmp_path, monkeypatch):
    """Ensure a fresh SQLite database and clean rate limits for each test."""
    ratelimit.clear_rate_limits()
    test_db = tmp_path / "test_teams_quest.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


def test_team_code_generation():
    """Verify code generation prefix, padding, hyphen, and 4-digit formatting."""
    # Standard name with >= 3 letters
    code1 = game.generate_team_code("Phoenix")
    assert len(code1) == 8
    assert code1.startswith("PHO-")
    assert code1[4:].isdigit()

    # Name with fewer than 3 letters gets uppercase padded
    code2 = game.generate_team_code("AI")
    assert len(code2) == 8
    assert code2.startswith("AI")
    assert code2[2].isalpha() and code2[2].isupper()
    assert code2[3] == "-"
    assert code2[4:].isdigit()

    # Name with spaces and special characters
    code3 = game.generate_team_code("  The 7th Team! ")
    assert len(code3) == 8
    assert code3.startswith("THE-")
    assert code3[4:].isdigit()


def test_team_code_normalization():
    """Normalize team code strips whitespace and uppercase."""
    assert game.normalize_team_code("  pho-1234  ") == "PHO-1234"


def test_register_team_success():
    """Registering a team creates database records, generates unique code, and sets device cookie."""
    client = TestClient(app)
    response = client.post(
        "/api/register",
        json={"name": "Hawks", "members": ["Aarav", "Priya"]},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Hawks"
    assert data["members"] == ["Aarav", "Priya"]
    assert "code" in data
    assert data["code"].startswith("HAW-")

    # Verify HttpOnly cookie was set
    cookie = response.cookies.get(auth.DEVICE_COOKIE_NAME)
    assert cookie is not None

    # Verify device hash stored in SQLite matches cookie token
    conn = db.get_connection()
    try:
        team = db.get_team_by_code(conn, data["code"])
        assert team is not None
        assert team["device_hash"] == auth.hash_device_token(cookie)
    finally:
        conn.close()


def test_register_team_closed():
    """Registration fails with 403 when registration_open is 0 in settings."""
    conn = db.get_connection()
    try:
        with db.write_tx(conn):
            conn.execute("UPDATE settings SET value = '0' WHERE key = 'registration_open'")
    finally:
        conn.close()

    client = TestClient(app)
    response = client.post(
        "/api/register",
        json={"name": "Hawks", "members": ["Aarav", "Priya"]},
    )
    assert response.status_code == 403
    assert "Registration is currently closed" in response.json()["detail"]


def test_register_validation_errors():
    """Invalid team names and insufficient members are rejected with 422."""
    client = TestClient(app)

    # Team name too short
    r1 = client.post("/api/register", json={"name": "A", "members": ["Alice", "Bob"]})
    assert r1.status_code == 422

    # Team name too long (>30 chars)
    r2 = client.post("/api/register", json={"name": "A" * 31, "members": ["Alice", "Bob"]})
    assert r2.status_code == 422

    # Insufficient members (< MIN_MEMBERS)
    r3 = client.post("/api/register", json={"name": "Hawks", "members": ["Alice"]})
    assert r3.status_code == 422

    # Blank member name
    r4 = client.post("/api/register", json={"name": "Hawks", "members": ["Alice", "   "]})
    assert r4.status_code == 422


def test_state_missing_or_invalid_cookie():
    """Accessing /api/state without cookie or with tampered token returns 401."""
    client = TestClient(app)

    # 1. No cookie
    r1 = client.get("/api/state")
    assert r1.status_code == 401

    # 2. Bogus cookie
    client.cookies.set(auth.DEVICE_COOKIE_NAME, "bogus_random_token")
    r2 = client.get("/api/state")
    assert r2.status_code == 401


def test_state_with_valid_cookie():
    """Valid device cookie restores team state, code, and members without localStorage."""
    client = TestClient(app)
    reg_res = client.post(
        "/api/register",
        json={"name": "RoboCamp", "members": ["Dev", "Tanvi"]},
    )
    assert reg_res.status_code == 201

    # Client preserves the cookie returned by registration
    state_res = client.get("/api/state")
    assert state_res.status_code == 200
    state = state_res.json()
    assert state["name"] == "RoboCamp"
    assert state["members"] == ["Dev", "Tanvi"]
    assert state["game_state"] == "setup"
    assert state["device_status"] == "this phone is your team's device"
    assert state["code"].startswith("ROB-")


def test_join_team_conflict_when_already_bound():
    """Entering a code for an already bound team returns 409 conflict message."""
    client1 = TestClient(app)
    reg = client1.post(
        "/api/register",
        json={"name": "Titans", "members": ["Rohan", "Sneha"]},
    )
    code = reg.json()["code"]

    # Second phone enters the code
    client2 = TestClient(app)
    join_res = client2.post("/api/join", json={"code": code})
    assert join_res.status_code == 409
    assert join_res.json()["detail"] == "This team is already playing on another device."


def test_join_team_invalid_code():
    """Attempting to join with non-existent code returns 404."""
    client = TestClient(app)
    res = client.post("/api/join", json={"code": "XYZ-9999"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Team code not found"


def test_join_team_after_device_release():
    """When a device is cleared (e.g. phone lost and released), a new phone can bind."""
    client1 = TestClient(app)
    reg = client1.post(
        "/api/register",
        json={"name": "Titans", "members": ["Rohan", "Sneha"]},
    )
    code = reg.json()["code"]

    # Organizer simulates "Release device" by clearing device_hash in db
    conn = db.get_connection()
    try:
        with db.write_tx(conn):
            conn.execute("UPDATE teams SET device_hash = NULL WHERE code = ?", (code,))
    finally:
        conn.close()

    # Now Phone 2 calls /api/join
    client2 = TestClient(app)
    join_res = client2.post("/api/join", json={"code": code})
    assert join_res.status_code == 200
    assert join_res.json()["name"] == "Titans"

    # Phone 2 now has the bound device cookie and can fetch state
    state_res = client2.get("/api/state")
    assert state_res.status_code == 200
    assert state_res.json()["name"] == "Titans"

    # Phone 1's old cookie is now invalid
    old_state = client1.get("/api/state")
    assert old_state.status_code == 401


def test_join_rate_limiting():
    """Excessive join attempts from the same IP trigger HTTP 429."""
    client = TestClient(app)
    for _ in range(config.JOIN_ATTEMPTS_PER_MIN):
        r = client.post("/api/join", json={"code": "BAD-0000"})
        assert r.status_code == 404

    # The (N + 1)-th attempt must be throttled
    throttled = client.post("/api/join", json={"code": "BAD-0000"})
    assert throttled.status_code == 429
    assert "Too many join attempts" in throttled.json()["detail"]


def test_index_contains_auth_and_lobby_overlays():
    """Verify that index.html includes the registration form, join form, and lobby structures."""
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert 'id="auth-overlay"' in html
    assert 'id="form-register"' in html
    assert 'id="form-join"' in html
    assert 'id="lobby-overlay"' in html
    assert 'id="lobby-team-code"' in html
    assert 'id="lobby-members-list"' in html
    assert 'id="lobby-device-status"' in html
    assert "Waiting for the organizer to start" in html

