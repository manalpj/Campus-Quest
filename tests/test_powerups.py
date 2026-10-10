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
    """Hint power-up adds 180s penalty, reveals hint, and does not charge twice for the same checkpoint."""
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
    assert data["penalty_added_s"] == 180
    assert data["penalty_s"] == 180
    assert data["already_revealed"] is False

    # State now includes active_hint and penalty_s
    st2 = client.get("/api/state").json()
    assert st2["active_hint"] == "Hint for Spot 1"
    assert st2["penalty_s"] == 180

    # Second call for the same checkpoint: returns hint with 0 added penalty
    res2 = client.post("/api/powerup/hint")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["hint"] == "Hint for Spot 1"
    assert data2["penalty_added_s"] == 0
    assert data2["penalty_s"] == 180
    assert data2["already_revealed"] is True

    # Check leaderboard adjusted time includes the penalty
    lb = client.get("/api/leaderboard").json()
    team_entry = [t for t in lb if t["name"] == "Power Testers"][0]
    assert team_entry["adjusted_time_s"] == 180


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


def test_boost_powerup_expands_radius(test_setup):
    """Radius boost (+20m) allows unlocking at distances beyond the base 30m radius."""
    client = test_setup["client"]
    conn = db.get_connection(test_setup["db_path"])

    # Give team 1 boost
    with db.write_tx(conn):
        conn.execute("UPDATE teams SET boost_left = 1")

    # Spot 1 is at 22.6928, 75.8676.
    # Lat delta 0.00036 is about 40m away: outside 30m base radius, inside 50m boosted radius.
    test_lat = 22.6928 + 0.00036
    test_lng = 75.8676

    # Ping without boost -> streak is 0, status searching
    p1 = client.post("/api/ping", json={"lat": test_lat, "lng": test_lng, "accuracy": 10.0}).json()
    assert p1["status"] == "searching"

    # Activate radius boost
    b_res = client.post("/api/powerup/boost")
    assert b_res.status_code == 200
    assert b_res.json()["boost_left"] == 0

    # Fix 1 inside boosted radius (streak = 1)
    p2 = client.post("/api/ping", json={"lat": test_lat, "lng": test_lng, "accuracy": 10.0}).json()
    assert p2["status"] == "searching"

    # Fix 2 inside boosted radius -> unlocks!
    p3 = client.post("/api/ping", json={"lat": test_lat, "lng": test_lng, "accuracy": 10.0}).json()
    assert p3["status"] == "unlocked"
    assert p3["checkpoint_name"] == "Spot 1"


def test_alternating_powerup_awards_on_gps_unlocks(test_setup):
    """GPS unlocks award alternating power-ups: 1st clear gives Radar, 2nd gives Boost."""
    client = test_setup["client"]

    # Spot 1 coordinates
    lat1, lng1 = 22.6928, 75.8676

    # Unlock Spot 1 (2 inside fixes)
    client.post("/api/ping", json={"lat": lat1, "lng": lng1, "accuracy": 10.0})
    u1 = client.post("/api/ping", json={"lat": lat1, "lng": lng1, "accuracy": 10.0}).json()
    assert u1["status"] == "unlocked"
    assert u1["awarded_powerup"] == "radar"

    # Check inventory in state
    st1 = client.get("/api/state").json()
    assert st1["radar_left"] == 1
    assert st1["boost_left"] == 0

    # Spot 2 coordinates
    lat2, lng2 = 22.69316, 75.8676

    # Unlock Spot 2 (2 inside fixes)
    client.post("/api/ping", json={"lat": lat2, "lng": lng2, "accuracy": 10.0})
    u2 = client.post("/api/ping", json={"lat": lat2, "lng": lng2, "accuracy": 10.0}).json()
    assert u2["status"] == "unlocked"
    assert u2["awarded_powerup"] == "boost"

    # Check inventory in state: now has 1 Radar and 1 Boost!
    st2 = client.get("/api/state").json()
    assert st2["radar_left"] == 1
    assert st2["boost_left"] == 1
