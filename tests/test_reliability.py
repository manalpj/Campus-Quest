"""Tests for Task 19: Reliability, Wake Lock and error states.

Verifies that the index page serves all required reliability UI components
(wake lock fallback, in-app browser advisory, GPS permission guide, and reconnecting notice),
that app.js contains zero localStorage/sessionStorage usage, and that the server
authoritatively restores game and team state upon client reload.
"""

from pathlib import Path
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
    test_db = tmp_path / "test_reliability.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


def test_index_contains_reliability_elements():
    """Verify that the frontend contains all required reliability and error state components."""
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Screen Wake Lock notice
    assert 'id="wakelock-notice"' in html
    assert 'Keep this screen on' in html
    assert 'id="btn-dismiss-wakelock"' in html

    # In-App browser advisory hint
    assert 'id="inapp-browser-banner"' in html
    assert 'Chrome' in html and 'Safari' in html
    assert 'id="btn-dismiss-inapp"' in html

    # Location permission denied guide
    assert 'id="gps-permission-guide"' in html
    assert 'Location permission denied' in html
    assert 'id="btn-retry-gps"' in html

    # Offline / Reconnecting banner
    assert 'id="status-reconnecting"' in html
    assert 'Connection lost' in html or 'Reconnecting' in html


def test_app_js_contains_no_local_storage():
    """Verify strictly that app.js does not store any game state in localStorage or sessionStorage."""
    app_js_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
    assert app_js_path.is_file()
    content = app_js_path.read_text(encoding="utf-8")

    assert "localStorage" not in content, "Client must not use localStorage for game state"
    assert "sessionStorage" not in content, "Client must not use sessionStorage for game state"


def test_server_session_continuity_on_reload():
    """Verify that client reloading resumes exactly where the team was without local storage."""
    conn = db.get_connection()
    try:
        cp1 = db.create_checkpoint(
            conn,
            name="Parijat Tree",
            lat=22.693000,
            lng=75.867000,
            radius=30.0,
            clue="Look near the fragrant tree.",
            hint="Beside the eastern gate.",
            story="Planted in 1985.",
        )
        team_row, device_token = db.create_team(
            conn,
            name="Reliable Rovers",
            members=["Sita", "Geeta"],
        )
        db.set_setting(conn, "game_state", "running")
        db.set_setting(conn, "started_at", str(time.time() - 100))
    finally:
        conn.close()

    client = TestClient(app)
    client.cookies.set(auth.DEVICE_COOKIE_NAME, device_token)

    # Initial session check
    res1 = client.get("/api/state")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["name"] == "Reliable Rovers"
    assert data1["cleared"] == 0
    assert data1["current_clue"] == "Look near the fragrant tree."

    # Simulate page reload by making a fresh GET /api/state call
    res2 = client.get("/api/state")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["code"] == data1["code"]
    assert data2["game_state"] == "running"
    assert data2["current_clue"] == data1["current_clue"]


def test_api_state_error_codes():
    """Verify proper HTTP status codes for unauthorized or unauthenticated requests."""
    client = TestClient(app)

    # Missing cookie -> 401
    res = client.get("/api/state")
    assert res.status_code == 401

    # Fake cookie -> 401
    client.cookies.set(auth.DEVICE_COOKIE_NAME, "completely_fake_token_12345")
    res_fake = client.get("/api/state")
    assert res_fake.status_code == 401
