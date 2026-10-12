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


def test_gods_events_filtering_and_parameter_validation(admin_client, anon_client):
    """GET /api/gods/events validates parameters, caps limit at 200, and filters by team and type."""
    conn = db.get_connection()
    try:
        t1, _ = db.create_team(conn, name="Team Alfa", members=["A1", "A2"])
        t2, _ = db.create_team(conn, name="Team Beta", members=["B1", "B2"])

        db.log_event(conn, t1["id"], game.EVENT_CHECKPOINT_UNLOCKED, "cp=1")
        db.log_event(conn, t2["id"], game.EVENT_CHECKPOINT_SKIPPED, "cp=1")
        db.log_event(conn, t1["id"], game.EVENT_HINT_USED, "cp=2")
        db.log_event(conn, None, game.EVENT_GAME_STARTED, "start")
    finally:
        conn.close()

    # 1. Filter by team_id
    res_team = admin_client.get(f"/api/gods/events?team_id={t1['id']}")
    assert res_team.status_code == 200
    data_team = res_team.json()
    assert len(data_team) == 3
    assert all(e["team_id"] == t1["id"] for e in data_team)
    assert all(e["team_name"] == "Team Alfa" for e in data_team)

    # 2. Filter by type
    res_type = admin_client.get(f"/api/gods/events?type={game.EVENT_CHECKPOINT_SKIPPED}")
    assert res_type.status_code == 200
    data_type = res_type.json()
    assert len(data_type) == 1
    assert data_type[0]["type"] == game.EVENT_CHECKPOINT_SKIPPED
    assert data_type[0]["team_name"] == "Team Beta"

    # 3. Limit capping: maximum 200, le=200 enforced
    res_over_limit = admin_client.get("/api/gods/events?limit=201")
    assert res_over_limit.status_code == 422

    # 4. Offset pagination
    res_offset = admin_client.get("/api/gods/events?offset=2&limit=2")
    assert res_offset.status_code == 200
    assert len(res_offset.json()) == 2

    # 5. Invalid type pattern rejected
    res_bad_type = admin_client.get("/api/gods/events?type=bad';DROP--")
    assert res_bad_type.status_code == 422


def test_csv_exports_require_admin_cookie(anon_client):
    """Both CSV exports return 401 without valid admin credentials."""
    assert anon_client.get("/api/gods/export/teams.csv").status_code == 401
    assert anon_client.get("/api/gods/export/events.csv").status_code == 401


def test_teams_csv_export_format_injection_protection_and_secret_exclusion(admin_client):
    """Teams CSV sanitizes formula injection, encodes UTF-8-sig BOM, and never includes device_hash or join code."""
    import csv
    import io

    conn = db.get_connection()
    try:
        # Create checkpoints
        for i in range(1, 4):
            db.create_checkpoint(
                conn,
                name=f"Spot {i}",
                lat=22.7100 + (i * 0.001),
                lng=75.8700 + (i * 0.001),
                radius=30.0,
                clue=f"Clue {i}",
                hint=f"Hint {i}",
            )

        # Team with malicious formula name and join code
        malicious_name = '=HYPERLINK("http://evil.com", "Hack")'
        t1, _ = db.create_team(conn, name=malicious_name, members=["Alice", "Bob"])
        t1_id = t1["id"]

        # Record progress: 1 unlocked, 1 skipped, 1 admin
        cps = db.get_checkpoints(conn)
        db.unlock_checkpoint(conn, t1_id, cps[0]["id"], unlocked_at=time.time(), elapsed_s=120, is_last=False, lat=22.711, lng=75.871)
        db.skip_checkpoint(conn, t1_id, cps[1]["id"], unlocked_at=time.time() + 10, elapsed_s=240, penalty_s=600, is_last=False)
        db.admin_force_clear_checkpoint(conn, t1_id, cps[2]["id"], unlocked_at=time.time() + 20, elapsed_s=300, reason="Organizers verified", is_last=True)
    finally:
        conn.close()

    res = admin_client.get("/api/gods/export/teams.csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'attachment; filename="teams.csv"' in res.headers["content-disposition"]

    # Verify BOM present
    raw_bytes = res.content
    assert raw_bytes.startswith(b"\xef\xbb\xbf")

    # Parse CSV content
    text = raw_bytes.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    assert len(reader) >= 2
    header = reader[0]
    row = reader[1]

    # Verify header does NOT contain device_hash, token, cookie, ip, or join code
    forbidden_terms = {"device_hash", "hash", "code", "join_code", "token", "cookie", "ip"}
    for col in header:
        assert col.lower().strip() not in forbidden_terms

    # Check injection neutralization on team name
    team_name_idx = header.index("Team Name")
    assert row[team_name_idx].startswith("'=")
    assert row[team_name_idx] == f"'{malicious_name}"

    # Verify member joining
    members_idx = header.index("Members")
    assert row[members_idx] == "Alice; Bob"

    # Verify clearance breakdown
    unlocked_idx = header.index("Unlocked Count")
    skipped_idx = header.index("Skipped Count")
    admin_idx = header.index("Admin Cleared Count")
    assert row[unlocked_idx] == "1"
    assert row[skipped_idx] == "1"
    assert row[admin_idx] == "1"


def test_events_csv_export_and_download_event_logging(admin_client):
    """Events CSV exports time, team, type, detail, logs export_downloaded, and strips raw IPs."""
    import csv
    import io

    # Insert test events including an admin login failure with an IP
    conn = db.get_connection()
    try:
        t, _ = db.create_team(conn, name="Delta Team", members=["Dan"])
        db.log_event(conn, t["id"], game.EVENT_CHECKPOINT_UNLOCKED, "checkpoint_id=1 elapsed_s=60")
        db.log_event(conn, None, game.EVENT_ADMIN_LOGIN_FAILURE, "result=failed ip=192.168.1.100")
    finally:
        conn.close()

    res = admin_client.get("/api/gods/export/events.csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'attachment; filename="events.csv"' in res.headers["content-disposition"]

    raw_bytes = res.content
    assert raw_bytes.startswith(b"\xef\xbb\xbf")
    text = raw_bytes.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    assert len(reader) >= 3

    header = reader[0]
    assert header == ["Time", "Team Name", "Type", "Detail"]

    # Check that raw IP was sanitized/redacted in detail
    details = [r[3] for r in reader[1:]]
    assert any("result=failed" in d for d in details)
    assert not any("192.168.1.100" in d for d in details)

    # Verify export_downloaded audit event was logged
    conn = db.get_connection()
    try:
        events = db.get_events(conn, event_type=game.EVENT_EXPORT_DOWNLOADED)
        assert len(events) >= 1
        assert any(e["detail"] == "export=events" for e in events)
    finally:
        conn.close()
