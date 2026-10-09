"""Tests for admin authentication, signed session cookies, rate limiting, and route protection."""

import time
import pytest
from fastapi.testclient import TestClient

import auth
import config
from main import app
import ratelimit


@pytest.fixture(autouse=True)
def clean_ratelimit_and_db(tmp_path, monkeypatch):
    """Ensure clean in-memory rate limiters and temporary database for every test."""
    ratelimit.clear_rate_limits()
    test_db = tmp_path / "test_auth_quest.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))


def test_verify_admin_credentials():
    """Constant-time credential check succeeds only with configured admin user and pass."""
    assert auth.verify_admin_credentials(config.ADMIN_USER, config.ADMIN_PASS) is True
    assert auth.verify_admin_credentials("wrong_user", config.ADMIN_PASS) is False
    assert auth.verify_admin_credentials(config.ADMIN_USER, "wrong_pass") is False
    assert auth.verify_admin_credentials("", "") is False


def test_signed_cookie_verification_and_tampering():
    """HMAC cookie correctly verifies valid signatures and rejects tampering or expiry."""
    # 1. Valid cookie
    cookie = auth.create_admin_cookie_value(config.ADMIN_USER)
    assert auth.verify_admin_cookie(cookie) == config.ADMIN_USER

    # 2. Tampered signature
    payload, sig = cookie.rsplit(":", 1)
    tampered_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert auth.verify_admin_cookie(f"{payload}:{tampered_sig}") is None

    # 3. Tampered payload
    user, exp = payload.split(":", 1)
    tampered_user_cookie = f"attacker:{exp}:{sig}"
    assert auth.verify_admin_cookie(tampered_user_cookie) is None

    # 4. Expired cookie
    past_timestamp = int(time.time()) - 100
    expired_cookie = auth.create_admin_cookie_value(config.ADMIN_USER, expires_at=past_timestamp)
    assert auth.verify_admin_cookie(expired_cookie) is None

    # 5. Malformed string
    assert auth.verify_admin_cookie("malformed_cookie_value") is None
    assert auth.verify_admin_cookie(None) is None


def test_sliding_window_rate_limiter():
    """In-memory rate limiter throttles keys after max_attempts within sliding window."""
    key = "192.168.1.10"
    for _ in range(config.LOGIN_ATTEMPTS_PER_MIN):
        assert ratelimit.is_rate_limited(key, max_attempts=config.LOGIN_ATTEMPTS_PER_MIN, window_s=60) is False

    # Next attempt must be throttled
    assert ratelimit.is_rate_limited(key, max_attempts=config.LOGIN_ATTEMPTS_PER_MIN, window_s=60) is True

    # Other keys must not be affected
    other_key = "192.168.1.20"
    assert ratelimit.is_rate_limited(other_key, max_attempts=config.LOGIN_ATTEMPTS_PER_MIN, window_s=60) is False


def test_gods_page_served_and_not_linked_in_player_app():
    """Admin panel is served at /gods and never referenced in index.html."""
    with TestClient(app) as client:
        res = client.get("/gods")
        assert res.status_code == 200
        assert "Organizer Login" in res.text

        # Ensure player app does not link to /gods
        index_res = client.get("/")
        assert index_res.status_code == 200
        assert "/gods" not in index_res.text


def test_admin_login_success_and_logout_flow():
    """Admin logs in, receives HttpOnly cookie, accesses /api/gods/me, and logs out."""
    with TestClient(app) as client:
        login_res = client.post(
            "/api/gods/login",
            json={"username": config.ADMIN_USER, "password": config.ADMIN_PASS},
        )
        assert login_res.status_code == 200
        assert login_res.json() == {"status": "ok", "username": config.ADMIN_USER}

        # Verify cookie attributes
        cookie = login_res.cookies.get(auth.ADMIN_COOKIE_NAME)
        assert cookie is not None

        # Access protected endpoint with session
        me_res = client.get("/api/gods/me")
        assert me_res.status_code == 200
        assert me_res.json() == {"username": config.ADMIN_USER}

        # Logout
        logout_res = client.post("/api/gods/logout")
        assert logout_res.status_code == 200

        # After logout, accessing /me returns 401
        after_logout_res = client.get("/api/gods/me")
        assert after_logout_res.status_code == 401


def test_admin_login_invalid_credentials():
    """Invalid credentials return 401 Unauthorized without setting cookie."""
    with TestClient(app) as client:
        res = client.post(
            "/api/gods/login",
            json={"username": config.ADMIN_USER, "password": "wrong-password"},
        )
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid username or password"
        assert auth.ADMIN_COOKIE_NAME not in res.cookies


def test_admin_login_rate_limiting():
    """Repeated login attempts trigger 429 Too Many Requests."""
    with TestClient(app) as client:
        for _ in range(config.LOGIN_ATTEMPTS_PER_MIN):
            client.post(
                "/api/gods/login",
                json={"username": config.ADMIN_USER, "password": "wrong-password"},
            )

        # The subsequent attempt is rate limited
        blocked_res = client.post(
            "/api/gods/login",
            json={"username": config.ADMIN_USER, "password": "wrong-password"},
        )
        assert blocked_res.status_code == 429
        assert "Too many login attempts" in blocked_res.json()["detail"]


def test_all_admin_routes_require_authentication():
    """All registered /api/gods/ routes (except login) must reject unauthenticated requests with 401."""
    with TestClient(app) as client:
        admin_routes_found = 0
        for route in app.routes:
            path = getattr(route, "path", "")
            if path.startswith("/api/gods") and path != "/api/gods/login":
                methods = getattr(route, "methods", {"GET"})
                for method in methods:
                    if method in {"HEAD", "OPTIONS"}:
                        continue
                    admin_routes_found += 1
                    req_func = getattr(client, method.lower())
                    response = req_func(path)
                    assert response.status_code == 401, (
                        f"Expected route {method} {path} to require admin auth and return 401, but got {response.status_code}"
                    )

        # Assert that we actually discovered and tested the protected admin routes
        assert admin_routes_found >= 2, f"Expected at least 2 protected admin routes, found {admin_routes_found}"
