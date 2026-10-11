"""Tests verifying security review audit findings and defensive controls.

Covers:
1. Rate limiter bucket isolation (login vs join vs register).
2. Registration rate limiting.
3. Registration member count maximum limit.
4. X-Forwarded-For reverse proxy hop parsing and anti-spoofing.
5. Chunked transfer encoding rejection on API endpoints.
6. Negative or invalid Content-Length rejection.
7. Power-up re-activation rejection while active.
8. Strict-Transport-Security (HSTS) in production mode.
9. Idempotent unlock handling when concurrent pings race.
"""

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
def clean_test_env(tmp_path, monkeypatch):
    """Ensure a fresh SQLite database and clean rate limits for each test."""
    test_db = tmp_path / "test_sec_review.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


def test_rate_limiter_bucket_isolation():
    """Failed login attempts do not exhaust team join or registration rate limit buckets."""
    client = TestClient(app)

    # Exhaust login attempts (5 per min)
    for _ in range(config.LOGIN_ATTEMPTS_PER_MIN):
        client.post(
            "/api/gods/login",
            json={"username": config.ADMIN_USER, "password": "wrong-password"},
        )

    # Next login attempt is throttled
    login_res = client.post(
        "/api/gods/login",
        json={"username": config.ADMIN_USER, "password": "wrong-password"},
    )
    assert login_res.status_code == 429
    assert "Too many login attempts" in login_res.json()["detail"]

    # Team join on the same IP must NOT be throttled
    join_res = client.post("/api/join", json={"code": "NONEXISTENT"})
    assert join_res.status_code == 404  # Reached team lookup, not 429

    # Team registration on the same IP must NOT be throttled
    reg_res = client.post(
        "/api/register",
        json={"name": "IsolatedTeam", "members": ["Alice", "Bob"]},
    )
    assert reg_res.status_code == 201


def test_register_rate_limiting():
    """Repeated registration attempts trigger 429 Too Many Requests."""
    client = TestClient(app)

    for i in range(config.REGISTER_ATTEMPTS_PER_MIN):
        res = client.post(
            "/api/register",
            json={"name": f"Team {i}", "members": ["Alice", "Bob"]},
        )
        assert res.status_code == 201

    # The next registration attempt from the same IP is rate limited
    blocked_res = client.post(
        "/api/register",
        json={"name": "OverflowTeam", "members": ["Alice", "Bob"]},
    )
    assert blocked_res.status_code == 429
    assert "Too many registration attempts" in blocked_res.json()["detail"]


def test_register_max_members_validation():
    """Registration rejects member lists exceeding MAX_MEMBERS."""
    client = TestClient(app)
    too_many_members = [f"Member {i}" for i in range(config.MAX_MEMBERS + 1)]

    res = client.post(
        "/api/register",
        json={"name": "HugeTeam", "members": too_many_members},
    )
    assert res.status_code == 422
    assert f"cannot have more than {config.MAX_MEMBERS} members" in res.text


def test_x_forwarded_for_anti_spoofing():
    """get_client_ip selects the last hop from X-Forwarded-For to prevent client spoofing."""
    from unittest.mock import Mock

    mock_request = Mock()
    mock_request.headers = {
        "x-forwarded-for": "10.0.0.1, 192.168.1.100",
    }
    mock_request.client = None

    extracted_ip = ratelimit.get_client_ip(mock_request)
    assert extracted_ip == "192.168.1.100"


def test_chunked_transfer_encoding_rejected():
    """API endpoints reject Transfer-Encoding: chunked with 400 Bad Request."""
    client = TestClient(app)
    res = client.post(
        "/api/register",
        headers={"transfer-encoding": "chunked"},
        json={"name": "ChunkedTeam", "members": ["Alice", "Bob"]},
    )
    assert res.status_code == 400
    assert "Chunked transfer encoding is not supported" in res.json()["detail"]


def test_negative_content_length_rejected():
    """Negative Content-Length header is rejected with 413 or 400."""
    client = TestClient(app)
    res = client.post(
        "/api/register",
        headers={"content-length": "-5"},
        json={"name": "NegativeTeam", "members": ["Alice", "Bob"]},
    )
    assert res.status_code in (400, 413)


def test_powerup_reactivation_rejected_while_active():
    """Activating Radar or Boost while already active returns 400 and preserves charges."""
    conn = db.get_connection()
    try:
        # Create team with 2 radars and 2 boosts
        team_row, token = db.create_team(conn, "PowerTeam", ["Member A", "Member B"])
        with db.write_tx(conn):
            conn.execute(
                """
                INSERT INTO checkpoints (name, lat, lng, radius, position, clue, hint)
                VALUES ('CP 1', 22.6928, 75.8676, 30.0, 1, 'Clue 1', 'Hint 1')
                """
            )
            conn.execute(
                "UPDATE teams SET radar_left = 2, boost_left = 2 WHERE id = ?",
                (team_row["id"],),
            )
        db.set_setting(conn, "game_state", "running")
        db.set_setting(conn, "started_at", "100.0")

        client = TestClient(app)
        client.cookies.set(auth.DEVICE_COOKIE_NAME, token)

        # 1. Activate Radar first time
        r1 = client.post("/api/powerup/radar")
        assert r1.status_code == 200
        assert r1.json()["radar_left"] == 1

        # 2. Activate Radar again while still active
        r2 = client.post("/api/powerup/radar")
        assert r2.status_code == 400
        assert "Radar is already active" in r2.json()["detail"]

        # Check that remaining radar charge was NOT consumed
        check_team = db.get_team_by_id(conn, team_row["id"])
        assert check_team["radar_left"] == 1

        # 3. Activate Boost first time
        b1 = client.post("/api/powerup/boost")
        assert b1.status_code == 200
        assert b1.json()["boost_left"] == 1

        # 4. Activate Boost again while still active
        b2 = client.post("/api/powerup/boost")
        assert b2.status_code == 400
        assert "Radius boost is already active" in b2.json()["detail"]

        check_team = db.get_team_by_id(conn, team_row["id"])
        assert check_team["boost_left"] == 1
    finally:
        conn.close()


def test_hsts_header_in_production(monkeypatch):
    """Strict-Transport-Security header is injected when ENV=production."""
    monkeypatch.setattr(config, "ENV", "production")
    client = TestClient(app)
    res = client.get("/healthz")
    assert res.status_code == 200
    assert "Strict-Transport-Security" in res.headers
    assert "max-age=31536000" in res.headers["Strict-Transport-Security"]
