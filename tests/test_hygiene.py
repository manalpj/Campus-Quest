"""Tests for Task 22: Trust and hygiene pages.

Validates:
- /privacy and /terms plain-language disclosure pages with organizer details.
- Custom 404 handling (HTML for browser requests, JSON for /api routes).
- Unique <title> for all pages and favicon availability.
- Security response headers (Referrer-Policy, X-Content-Type-Options, X-Frame-Options).
- Admin Wipe Event Data endpoint (require_admin, WIPE confirmation, deletes teams/progress/hints/events, preserves checkpoints/settings, logs event_wiped).
"""

import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
import game
from main import app, invalidate_leaderboard_cache


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    """Ensure an isolated database for each test run."""
    test_db = tmp_path / "test_hygiene.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))
    invalidate_leaderboard_cache()


def test_privacy_page_content_and_headers():
    """GET /privacy returns plain language disclosures, organizer contact, and security headers."""
    client = TestClient(app)
    res = client.get("/privacy")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")

    # Required headers
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert res.headers.get("X-Frame-Options") == "DENY"

    # Title & Favicon
    assert "<title>Privacy Notice - Campus Quest</title>" in res.text
    assert 'href="/favicon.svg"' in res.text

    # Plain language disclosures
    assert "Team Name" in res.text
    assert "quest_device" in res.text  # Disclose the cookie
    assert "Device Location" in res.text
    assert "OpenStreetMap" in res.text  # Disclose OSM sees IP
    assert "tile.openstreetmap.org" in res.text
    assert "deleted after the event" in res.text or "wipe all event and player data" in res.text

    # Organizer details
    assert config.ORGANIZER_NAME in res.text
    assert config.ORGANIZER_CONTACT in res.text


def test_terms_page_content_and_headers():
    """GET /terms returns event rules, safety requirements, and organizer details."""
    client = TestClient(app)
    res = client.get("/terms")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")

    # Security headers
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    # Title & Favicon
    assert "<title>Event Rules &amp; Terms - Campus Quest</title>" in res.text
    assert 'href="/favicon.svg"' in res.text

    # Rule requirements
    assert "Public Outdoor Areas Only" in res.text
    assert "Daytime Participation &amp; Safety" in res.text
    assert "Fair Play &amp; Anti-Cheat" in res.text
    assert "Organizers&#39; Decisions are Final" in res.text or "Organizers' Decisions are Final" in res.text
    assert config.ORGANIZER_NAME in res.text
    assert config.ORGANIZER_CONTACT in res.text


def test_favicon_endpoint():
    """GET /favicon.ico and static /favicon.svg return SVG content."""
    client = TestClient(app)
    res = client.get("/favicon.ico")
    assert res.status_code == 200
    assert "image/svg+xml" in res.headers.get("content-type", "")
    assert "<svg" in res.text

    res_svg = client.get("/favicon.svg")
    assert res_svg.status_code == 200
    assert "<svg" in res_svg.text


def test_custom_404_html_for_browser_routes():
    """404 on browser navigation routes returns HTML page with Page Not Found title."""
    client = TestClient(app)
    res = client.get("/non-existent-page-url")
    assert res.status_code == 404
    assert "text/html" in res.headers.get("content-type", "")
    assert "<title>Page Not Found - Campus Quest</title>" in res.text
    assert "404" in res.text
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_custom_404_json_for_api_routes():
    """404 on /api/ routes returns JSON {detail: '...'}."""
    client = TestClient(app)
    res = client.get("/api/unknown-endpoint")
    assert res.status_code == 404
    assert "application/json" in res.headers.get("content-type", "")
    data = res.json()
    assert "detail" in data
    assert res.headers.get("X-Content-Type-Options") == "nosniff"


def test_all_pages_have_unique_titles_and_favicons():
    """Every page (/, /gods, /board, /privacy, /terms, 404) has a unique title and favicon link."""
    client = TestClient(app)

    pages = {
        "/": "Campus Quest - DAVV Clue Hunt",
        "/gods": "Admin Panel - Campus Quest",
        "/board": "Campus Quest - Live Leaderboard",
        "/privacy": "Privacy Notice - Campus Quest",
        "/terms": "Event Rules &amp; Terms - Campus Quest",
        "/nonexistent-page": "Page Not Found - Campus Quest",
    }

    seen_titles = set()
    for route, expected_title in pages.items():
        res = client.get(route)
        assert res.status_code in (200, 404)
        assert expected_title in res.text
        assert expected_title not in seen_titles, f"Duplicate title detected: {expected_title}"
        seen_titles.add(expected_title)
        assert 'href="/favicon.svg"' in res.text, f"Missing favicon link in {route}"


def test_registration_consent_checkbox_in_index():
    """Registration form in index.html includes required consent checkbox linking to /privacy and /terms."""
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert 'id="reg-consent"' in res.text
    assert 'required' in res.text
    assert 'href="/privacy"' in res.text
    assert 'href="/terms"' in res.text


def test_admin_wipe_requires_admin_auth():
    """POST /api/gods/wipe is rejected with 401 without admin credentials."""
    client = TestClient(app)
    res = client.post("/api/gods/wipe", json={"confirm": "WIPE"})
    assert res.status_code == 401


def test_admin_wipe_requires_exact_word_wipe():
    """POST /api/gods/wipe rejects inputs that do not match 'WIPE'."""
    client = TestClient(app)
    admin_cookie = auth.create_admin_cookie_value(config.ADMIN_USER)
    client.cookies.set(auth.ADMIN_COOKIE_NAME, admin_cookie)

    # Lowercase 'wipe'
    res_lower = client.post("/api/gods/wipe", json={"confirm": "wipe"})
    assert res_lower.status_code == 422

    # Different word
    res_wrong = client.post("/api/gods/wipe", json={"confirm": "RESET"})
    assert res_wrong.status_code == 422

    # Missing confirm
    res_empty = client.post("/api/gods/wipe", json={})
    assert res_empty.status_code == 422


def test_admin_wipe_executes_cleanly_and_preserves_checkpoints():
    """POST /api/gods/wipe deletes teams, progress, hints, events, but keeps checkpoints and settings."""
    conn = db.get_connection()
    try:
        # Create checkpoint
        cp = db.create_checkpoint(
            conn, name="Central Tree", lat=22.680, lng=75.879, radius=30.0, clue="Under the tree", hint="Old oak"
        )
        # Create teams
        t1, _ = db.create_team(conn, name="Team 1", members=["P1", "P2"])
        t2, _ = db.create_team(conn, name="Team 2", members=["P3", "P4"])

        # Create progress and hint uses
        db.unlock_checkpoint(conn, t1["id"], cp["id"], unlocked_at=10.0, elapsed_s=10, is_last=False)
        conn.execute("INSERT INTO hint_uses (team_id, checkpoint_id, used_at) VALUES (?, ?, ?);", (t1["id"], cp["id"], 5.0))

        # Create an event
        db.log_event(conn, t1["id"], game.EVENT_CHECKPOINT_UNLOCKED, "test detail")

        # Set a setting
        db.set_setting(conn, "game_state", "running")
    finally:
        conn.close()

    # Verify data exists before wipe
    conn = db.get_connection()
    try:
        assert len(db.get_admin_teams_data(conn)) == 2
        assert db.get_checkpoint_count(conn) == 1
        assert len(db.get_latest_events(conn)) >= 1
    finally:
        conn.close()

    # Perform Wipe
    client = TestClient(app)
    admin_cookie = auth.create_admin_cookie_value(config.ADMIN_USER)
    client.cookies.set(auth.ADMIN_COOKIE_NAME, admin_cookie)

    res = client.post("/api/gods/wipe", json={"confirm": "WIPE"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # Verify data state after wipe
    conn = db.get_connection()
    try:
        # Teams, progress, hint_uses are completely empty
        assert len(db.get_admin_teams_data(conn)) == 0

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM progress;")
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM hint_uses;")
        assert cur.fetchone()[0] == 0

        # Checkpoints and settings are PRESERVED
        assert db.get_checkpoint_count(conn) == 1
        assert db.get_setting(conn, "game_state") == "running"

        # Events contains ONLY the single 'event_wiped' audit record
        events = db.get_latest_events(conn)
        assert len(events) == 1
        assert events[0]["type"] == game.EVENT_EVENT_WIPED
    finally:
        conn.close()
