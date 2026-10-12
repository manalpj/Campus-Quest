"""Tests for F7 Power-ups (Hint, Radar, Radius boost) and time rules."""

import time
import pytest
from fastapi.testclient import TestClient

import config
import db
from main import app


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    """Ensure an isolated database for each test run."""
    test_db = tmp_path / "test_powerups.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    monkeypatch.setattr(config, "HINT_PENALTY_S", 300)
    db.init_db(str(test_db))


@pytest.fixture
def test_setup():
    """Seed game in running state with 3 checkpoints and 1 registered team."""
    conn = db.get_connection()
    db.set_setting(conn, "game_state", "running")
    db.set_setting(conn, "registration_open", "1")
    db.set_setting(conn, "started_at", str(time.time() - 100))

    with db.write_tx(conn):
        # Checkpoint 1 (at center)
        conn.execute(
            """
            INSERT INTO checkpoints (name, lat, lng, radius, position, clue, hint, story, kind)
            VALUES ('Spot 1', 22.6928, 75.8676, 30.0, 1, 'Clue 1', 'Hint for Spot 1', 'Story 1', 'route')
            """
        )
        # Checkpoint 2 (slightly north, ~40m away)
        # 22.69316 is ~40m north of 22.6928
        conn.execute(
            """
            INSERT INTO checkpoints (name, lat, lng, radius, position, clue, hint, story, kind)
            VALUES ('Spot 2', 22.69316, 75.8676, 30.0, 2, 'Clue 2', 'Hint for Spot 2', 'Story 2', 'route')
            """
        )
        # Checkpoint 3 (further north)
        conn.execute(
            """
            INSERT INTO checkpoints (name, lat, lng, radius, position, clue, hint, story, kind)
            VALUES ('Spot 3', 22.6936, 75.8676, 30.0, 3, 'Clue 3', 'Hint for Spot 3', 'Story 3', 'route')
            """
        )

    client = TestClient(app)
    # Register team
    reg_resp = client.post(
        "/api/register",
        json={"name": "Power Testers", "members": ["Alice", "Bob"]},
    )
    assert reg_resp.status_code == 201
    token = reg_resp.cookies.get("team_token")
    client.cookies.set("team_token", token)

    return {
        "client": client,
        "db_path": config.DB_PATH,
    }


def test_hint_powerup_adds_penalty_and_prevents_duplicate_charge(test_setup):
    """Hint power-up adds 300s (5m) penalty, reveals hint, and does not charge twice for the same checkpoint."""
    client = test_setup["client"]

    # Before hint: state has no active_hint
    st = client.get("/api/state").json()
    assert st["active_hint"] is None
    assert st["penalty_s"] == 0

    # Call hint power-up
    res = client.post("/api/powerup/hint")
    assert res.status_code == 200
    data = res.json()
    assert data["powerup"] == "hint"
    assert data["hint"] == "Hint for Spot 1"
    assert data["penalty_added_s"] == 300
    assert data["penalty_s"] == 300
    assert data["already_revealed"] is False

    # State now includes active_hint and penalty_s
    st2 = client.get("/api/state").json()
    assert st2["active_hint"] == "Hint for Spot 1"
    assert st2["penalty_s"] == 300

    # Second call for the same checkpoint: returns hint with 0 added penalty
    res2 = client.post("/api/powerup/hint")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["hint"] == "Hint for Spot 1"
    assert data2["penalty_added_s"] == 0
    assert data2["penalty_s"] == 300
    assert data2["already_revealed"] is True

    # Check leaderboard adjusted time includes the penalty
    lb = client.get("/api/leaderboard").json()
    team_entry = [t for t in lb if t["name"] == "Power Testers"][0]
    assert team_entry["adjusted_time_s"] == 300


def test_radar_powerup_activation_and_ping_exposure(test_setup):
    """Radar exposes distance during its active window, and conceals it otherwise."""
    client = test_setup["client"]
    conn = db.get_connection(test_setup["db_path"])

    # Attempt radar with 0 balance -> 400
    fail_res = client.post("/api/powerup/radar")
    assert fail_res.status_code == 400
    assert "No Radar power-ups remaining" in fail_res.json()["detail"]

    # Give team 1 radar directly
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET radar_left = 1")

    # Regular ping before radar does NOT expose distance or label
    ping_before = client.post(
        "/api/ping",
        json={"lat": 22.6920, "lng": 75.8676, "accuracy": 10.0},
    ).json()
    assert "radar_distance_m" not in ping_before
    assert "radar_label" not in ping_before

    # Activate radar
    radar_res = client.post("/api/powerup/radar")
    assert radar_res.status_code == 200
    r_data = radar_res.json()
    assert r_data["radar_left"] == 0
    assert r_data["duration_s"] == 60

    # Ping now exposes radar distance and label!
    ping_during = client.post(
        "/api/ping",
        json={"lat": 22.6920, "lng": 75.8676, "accuracy": 10.0},
    ).json()
    assert "radar_distance_m" in ping_during
    assert ping_during["radar_distance_m"] > 0
    assert "radar_label" in ping_during

    # When radar expires, ping stops exposing distance
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET radar_until = ?", (time.time() - 5.0,))

    ping_after = client.post(
        "/api/ping",
        json={"lat": 22.6920, "lng": 75.8676, "accuracy": 10.0},
    ).json()
    assert "radar_distance_m" not in ping_after
    assert "radar_label" not in ping_after


def test_radar_powerup_works_with_test_mode_pings(test_setup):
    """Test mode pings (test: True) receive radar_distance_m and radar_label while radar is active."""
    client = test_setup["client"]
    conn = db.get_connection(test_setup["db_path"])

    # Enable test mode on server
    db.set_setting(conn, "test_mode", "1")

    # Give team 1 radar
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET radar_left = 1")

    # Activate radar
    radar_res = client.post("/api/powerup/radar")
    assert radar_res.status_code == 200

    # Simulated test ping returns distance and label
    test_ping = client.post(
        "/api/ping",
        json={"lat": 22.6920, "lng": 75.8676, "accuracy": 5.0, "test": True},
    ).json()
    assert "radar_distance_m" in test_ping
    assert test_ping["radar_distance_m"] > 0
    assert "radar_label" in test_ping
    assert test_ping["radar_label"].endswith("m")


def test_radar_powerup_exposes_distance_in_api_state(test_setup):
    """GET /api/state exposes radar_distance_m and radar_label when radar is active and last fix is known."""
    client = test_setup["client"]
    conn = db.get_connection(test_setup["db_path"])

    # Give team a prior location fix and 1 radar
    with db.write_tx(conn):
        conn.execute(
            "UPDATE teams SET last_fix_lat = 22.6920, last_fix_lng = 75.8676, radar_left = 1"
        )

    # Before activation: /api/state does not expose distance
    s_before = client.get("/api/state").json()
    assert "radar_distance_m" not in s_before
    assert "radar_label" not in s_before

    # Activate radar
    radar_res = client.post("/api/powerup/radar")
    assert radar_res.status_code == 200

    # /api/state now exposes radar distance and label without waiting for a new ping!
    s_during = client.get("/api/state").json()
    assert s_during["radar_active"] is True
    assert "radar_distance_m" in s_during
    assert s_during["radar_distance_m"] > 0
    assert "radar_label" in s_during
    assert s_during["radar_label"].endswith("m")

    # When radar expires, /api/state stops exposing distance
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET radar_until = ?", (time.time() - 5.0,))

    s_after = client.get("/api/state").json()
    assert s_after["radar_active"] is False
    assert "radar_distance_m" not in s_after
    assert "radar_label" not in s_after




def test_boost_powerup_expands_radius(test_setup):
    """Radius boost (+30%) allows unlocking at distances beyond the base 30m radius (up to 39m)."""
    client = test_setup["client"]
    conn = db.get_connection(test_setup["db_path"])

    # Give team 1 boost
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET boost_left = 1")

    # Spot 1 is at 22.6928, 75.8676 with base radius 30m.
    # Lat delta 0.00031 is about 34.5m away: outside 30m base radius, inside 39m boosted radius (+30%).
    test_lat = 22.6928 + 0.00031
    test_lng = 75.8676

    # Ping without boost -> streak is 0, status searching
    p1 = client.post("/api/ping", json={"lat": test_lat, "lng": test_lng, "accuracy": 10.0}).json()
    assert p1["status"] == "searching"

    # Activate radius boost
    b_res = client.post("/api/powerup/boost")
    assert b_res.status_code == 200
    assert b_res.json()["boost_left"] == 0
    assert b_res.json()["boost_percent"] == 30

    # Fix 1 inside boosted radius (streak = 1)
    p2 = client.post("/api/ping", json={"lat": test_lat, "lng": test_lng, "accuracy": 10.0}).json()
    assert p2["status"] == "searching"

    # Fix 2 inside boosted radius -> unlocks!
    p3 = client.post("/api/ping", json={"lat": test_lat, "lng": test_lng, "accuracy": 10.0}).json()
    assert p3["status"] == "unlocked"
    assert p3["checkpoint_name"] == "Spot 1"


def test_alternating_powerup_awards_on_gps_unlocks(test_setup):
    """GPS unlocks award power-ups on alternate checkpoints (1st Radar, 2nd None, 3rd Boost) if under 150s."""
    client = test_setup["client"]

    # Spot 1 coordinates
    lat1, lng1 = 22.6928, 75.8676

    # Unlock Spot 1 (within 150s from start) -> Checkpoint 1 awards Radar
    client.post("/api/ping", json={"lat": lat1, "lng": lng1, "accuracy": 10.0})
    u1 = client.post("/api/ping", json={"lat": lat1, "lng": lng1, "accuracy": 10.0}).json()
    assert u1["status"] == "unlocked"
    assert u1["awarded_powerup"] == "radar"

    # Check inventory in state: 1 Radar, 0 Boost
    st1 = client.get("/api/state").json()
    assert st1["radar_left"] == 1
    assert st1["boost_left"] == 0

    # Spot 2 coordinates (~40m away)
    lat2, lng2 = 22.69316, 75.8676

    # Simulate walking to Spot 2 (30s elapsed -> plausible speed ~1.3 m/s)
    conn = db.get_connection(test_setup["db_path"])
    now = time.time()
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET last_fix_ts = ?", (now - 30.0,))

    # Unlock Spot 2 -> Even clear (2nd checkpoint), awards NO powerup
    client.post("/api/ping", json={"lat": lat2, "lng": lng2, "accuracy": 10.0})
    u2 = client.post("/api/ping", json={"lat": lat2, "lng": lng2, "accuracy": 10.0}).json()
    assert u2["status"] == "unlocked"
    assert u2["awarded_powerup"] is None

    # Check inventory: still 1 Radar, 0 Boost
    st2 = client.get("/api/state").json()
    assert st2["radar_left"] == 1
    assert st2["boost_left"] == 0

    # Spot 3 coordinates (~45m north)
    lat3, lng3 = 22.6936, 75.8676

    # Simulate walking to Spot 3 (35s elapsed)
    now = time.time()
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET last_fix_ts = ?", (now - 35.0,))

    # Unlock Spot 3 -> Alternate clear (3rd checkpoint), awards Boost!
    client.post("/api/ping", json={"lat": lat3, "lng": lng3, "accuracy": 10.0})
    u3 = client.post("/api/ping", json={"lat": lat3, "lng": lng3, "accuracy": 10.0}).json()
    assert u3["status"] == "unlocked"
    assert u3["awarded_powerup"] == "boost"

    # Check inventory in state: now has 1 Radar and 1 Boost!
    st3 = client.get("/api/state").json()
    assert st3["radar_left"] == 1
    assert st3["boost_left"] == 1


def test_checkpoint_taking_longer_than_2m30s_awards_no_powerup(test_setup):
    """If finding the checkpoint exceeds 2m 30s (150s), no power-up is awarded."""
    client = test_setup["client"]
    conn = db.get_connection(test_setup["db_path"])

    # Simulate game started 200 seconds ago (exceeding 150s limit)
    now = time.time()
    db.set_setting(conn, "started_at", str(now - 200.0))

    lat1, lng1 = 22.6928, 75.8676
    client.post("/api/ping", json={"lat": lat1, "lng": lng1, "accuracy": 10.0})
    u1 = client.post("/api/ping", json={"lat": lat1, "lng": lng1, "accuracy": 10.0}).json()
    assert u1["status"] == "unlocked"
    # Even though it's checkpoint 1, taking > 150s forfeits the power-up
    assert u1["awarded_powerup"] is None

    st = client.get("/api/state").json()
    assert st["radar_left"] == 0
    assert st["boost_left"] == 0


def test_boost_cannot_use_with_none_left(test_setup):
    """Attempting to activate Radius boost with 0 remaining returns HTTP 400."""
    client = test_setup["client"]

    # Team starts with 0 boost
    st = client.get("/api/state").json()
    assert st["boost_left"] == 0

    res = client.post("/api/powerup/boost")
    assert res.status_code == 400
    assert "no radius boost power-ups remaining" in res.json()["detail"].lower()


def test_boost_not_inside_after_timer_ends(test_setup):
    """Fix at distance between base radius (30m) and boosted radius (39m) is NOT inside once boost timer expires."""
    client = test_setup["client"]
    conn = db.get_connection(test_setup["db_path"])

    # Give team 1 boost
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET boost_left = 1")

    # Spot 1 is at 22.6928, 75.8676 (radius 30m, boosted to 39m).
    # Delta 0.00031 is ~34.5m away (between 30m and 39m).
    test_lat = 22.6928 + 0.00031
    test_lng = 75.8676

    # Activate boost
    b_res = client.post("/api/powerup/boost")
    assert b_res.status_code == 200

    # 1 fix inside while boosted (streak = 1)
    p1 = client.post("/api/ping", json={"lat": test_lat, "lng": test_lng, "accuracy": 10.0}).json()
    assert p1["status"] == "searching"
    team = db.get_team_by_id(conn, 1)
    assert team["inside_streak"] == 1

    # Simulate timer expiring: set boost_until in the past
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET boost_until = ?", (time.time() - 5.0,))

    # Ping at the same ~34.5m distance after timer expired -> evaluated against base 30m radius
    # Since 34.5m > 30m, fix is outside: streak resets to 0, status remains searching
    p2 = client.post("/api/ping", json={"lat": test_lat, "lng": test_lng, "accuracy": 10.0}).json()
    assert p2["status"] == "searching"
    team_after = db.get_team_by_id(conn, 1)
    assert team_after["inside_streak"] == 0

    # Second ping after timer expired: still outside, does NOT unlock
    p3 = client.post("/api/ping", json={"lat": test_lat, "lng": test_lng, "accuracy": 10.0}).json()
    assert p3["status"] == "searching"
    assert "checkpoint_name" not in p3
