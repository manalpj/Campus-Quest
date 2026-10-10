"""Tests for POST /api/ping: accuracy gating, streak progression, and checkpoint unlocks."""

from concurrent.futures import ThreadPoolExecutor
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
    test_db = tmp_path / "test_ping.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


@pytest.fixture
def test_setup():
    """Setup a running game with registered team and checkpoints."""
    conn = db.get_connection()
    try:
        # Create 2 checkpoints
        # Checkpoint 1: at (22.693000, 75.867000), radius 30m
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
        # Checkpoint 2: at (22.695000, 75.869000), radius 30m
        cp2 = db.create_checkpoint(
            conn,
            name="Auditorium Lawn",
            lat=22.695000,
            lng=75.869000,
            radius=30.0,
            clue="Where applauses echo.",
            hint="Near the stage gate.",
            story="Hosted the golden jubilee ceremony.",
        )

        # Register team
        team_row, device_token = db.create_team(
            conn,
            name="Alpha Explorers",
            members=["Alice", "Bob"],
        )

        # Set game running and started in the past (countdown elapsed)
        now = time.time()
        db.set_setting(conn, "game_state", "running")
        db.set_setting(conn, "started_at", str(now - 60))  # started 60 seconds ago

        return {
            "cp1": dict(cp1),
            "cp2": dict(cp2),
            "team": dict(team_row),
            "token": device_token,
            "started_at": now - 60,
        }
    finally:
        conn.close()


@pytest.fixture
def player_client(test_setup):
    """Return a TestClient authenticated with the registered team's device cookie."""
    client = TestClient(app)
    client.cookies.set(auth.DEVICE_COOKIE_NAME, test_setup["token"])
    return client


# --- 1. Authentication & Game State Guards ---


def test_ping_without_cookie_returns_401():
    """Ping without quest_device cookie must return HTTP 401."""
    client = TestClient(app)
    res = client.post("/api/ping", json={"lat": 22.693000, "lng": 75.867000, "accuracy": 10.0})
    assert res.status_code == 401


def test_ping_with_invalid_device_token_returns_401():
    """Ping with wrong/forged device token must return HTTP 401."""
    client = TestClient(app)
    client.cookies.set(auth.DEVICE_COOKIE_NAME, "forged-device-token-12345")
    res = client.post("/api/ping", json={"lat": 22.693000, "lng": 75.867000, "accuracy": 10.0})
    assert res.status_code == 401


def test_ping_when_game_not_running_returns_409(player_client):
    """Ping when game is in setup or ended state must return HTTP 409."""
    conn = db.get_connection()
    try:
        db.set_setting(conn, "game_state", "setup")
    finally:
        conn.close()

    res = player_client.post("/api/ping", json={"lat": 22.693000, "lng": 75.867000, "accuracy": 10.0})
    assert res.status_code == 409
    assert "not running" in res.json()["detail"].lower()


def test_ping_when_countdown_not_finished_returns_409(player_client):
    """Ping while launch countdown is still ticking down must return HTTP 409."""
    conn = db.get_connection()
    try:
        # Started at 10 seconds in the future
        future_start = time.time() + 10.0
        db.set_setting(conn, "started_at", str(future_start))
    finally:
        conn.close()

    res = player_client.post("/api/ping", json={"lat": 22.693000, "lng": 75.867000, "accuracy": 10.0})
    assert res.status_code == 409
    assert "countdown" in res.json()["detail"].lower()


# --- 2. Accuracy Gating ---


def test_weak_accuracy_ignored_without_affecting_streak(player_client, test_setup):
    """Weak GPS fix (> ACCURACY_LIMIT_M) returns weak_gps and leaves streak untouched."""
    # First: establish a streak of 1 with an inside fix
    cp1 = test_setup["cp1"]
    res1 = player_client.post(
        "/api/ping",
        json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 15.0},
    )
    assert res1.status_code == 200
    assert res1.json() == {"status": "searching"}

    conn = db.get_connection()
    try:
        team_row = db.get_team_by_id(conn, test_setup["team"]["id"])
        assert team_row["inside_streak"] == 1
    finally:
        conn.close()

    # Second: send fix with weak accuracy (e.g. 50m when limit is 30m)
    res2 = player_client.post(
        "/api/ping",
        json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 50.0},
    )
    assert res2.status_code == 200
    assert res2.json() == {"status": "weak_gps"}

    # Streak remains 1, not reset and not incremented
    conn = db.get_connection()
    try:
        team_row = db.get_team_by_id(conn, test_setup["team"]["id"])
        assert team_row["inside_streak"] == 1
    finally:
        conn.close()


# --- 3. Streak Progression and Checkpoint Unlocking ---


def test_one_inside_fix_does_not_unlock(player_client, test_setup):
    """A single inside fix increments streak to 1 but returns searching and creates no progress."""
    cp1 = test_setup["cp1"]
    res = player_client.post(
        "/api/ping",
        json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "searching"}

    conn = db.get_connection()
    try:
        progress = conn.execute("SELECT COUNT(*) FROM progress").fetchone()[0]
        assert progress == 0
        team = db.get_team_by_id(conn, test_setup["team"]["id"])
        assert team["inside_streak"] == 1
    finally:
        conn.close()


def test_two_consecutive_inside_fixes_unlock_checkpoint(player_client, test_setup):
    """Two consecutive inside fixes unlock checkpoint 1, returning next clue and story."""
    cp1 = test_setup["cp1"]
    cp2 = test_setup["cp2"]

    # First fix inside
    res1 = player_client.post(
        "/api/ping",
        json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0},
    )
    assert res1.status_code == 200
    assert res1.json() == {"status": "searching"}

    # Second fix inside -> Unlocks!
    res2 = player_client.post(
        "/api/ping",
        json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 12.0},
    )
    assert res2.status_code == 200
    data = res2.json()
    assert data["status"] == "unlocked"
    assert data["story"] == cp1["story"]
    assert data["next_clue"] == cp2["clue"]
    assert data["cleared"] == 1
    assert data["total"] == 2

    # Verify progress recorded in database and streak reset to 0
    conn = db.get_connection()
    try:
        prog_row = conn.execute(
            "SELECT * FROM progress WHERE team_id = ? AND checkpoint_id = ?",
            (test_setup["team"]["id"], cp1["id"]),
        ).fetchone()
        assert prog_row is not None
        assert prog_row["how"] == "gps"
        assert prog_row["elapsed_s"] >= 60

        team = db.get_team_by_id(conn, test_setup["team"]["id"])
        assert team["inside_streak"] == 0
        assert team["finished_at"] is None
    finally:
        conn.close()


def test_outside_fix_resets_streak(player_client, test_setup):
    """An outside fix resets an existing inside streak back to 0."""
    cp1 = test_setup["cp1"]

    # First fix inside -> streak = 1
    player_client.post(
        "/api/ping",
        json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0},
    )

    conn = db.get_connection()
    try:
        team = db.get_team_by_id(conn, test_setup["team"]["id"])
        assert team["inside_streak"] == 1
    finally:
        conn.close()

    # Second fix outside (39m away, 10s walking time -> plausible speed ~3.9 m/s)
    now = time.time()
    conn = db.get_connection()
    try:
        with db.write_tx(conn):
            conn.execute("UPDATE teams SET last_fix_ts = ? WHERE id = ?", (now - 10.0, test_setup["team"]["id"]))
    finally:
        conn.close()

    res_out = player_client.post(
        "/api/ping",
        json={"lat": 22.693350, "lng": 75.867000, "accuracy": 10.0},
    )
    assert res_out.status_code == 200
    assert res_out.json() == {"status": "searching"}

    # Streak reset to 0
    conn = db.get_connection()
    try:
        team = db.get_team_by_id(conn, test_setup["team"]["id"])
        assert team["inside_streak"] == 0
    finally:
        conn.close()


def test_final_checkpoint_unlock_sets_finished_at(player_client, test_setup):
    """Unlocking the last checkpoint sets finished_at and returns next_clue as None."""
    cp1 = test_setup["cp1"]
    cp2 = test_setup["cp2"]

    # Unlock checkpoint 1 (2 inside fixes)
    player_client.post("/api/ping", json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0})
    player_client.post("/api/ping", json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0})

    # Simulate team walking to checkpoint 2 (60s elapsed)
    conn = db.get_connection()
    try:
        now = time.time()
        with db.write_tx(conn):
            conn.execute("UPDATE teams SET last_fix_ts = ? WHERE id = ?", (now - 60.0, test_setup["team"]["id"]))
    finally:
        conn.close()

    # Unlock checkpoint 2 (2 inside fixes)
    player_client.post("/api/ping", json={"lat": cp2["lat"], "lng": cp2["lng"], "accuracy": 10.0})
    res_final = player_client.post(
        "/api/ping",
        json={"lat": cp2["lat"], "lng": cp2["lng"], "accuracy": 10.0},
    )

    assert res_final.status_code == 200
    data = res_final.json()
    assert data["status"] == "unlocked"
    assert data["next_clue"] is None
    assert data["cleared"] == 2
    assert data["total"] == 2

    conn = db.get_connection()
    try:
        team = db.get_team_by_id(conn, test_setup["team"]["id"])
        assert team["finished_at"] is not None
    finally:
        conn.close()


# --- 4. Concurrency Guard ---


def test_two_simultaneous_pings_produce_exactly_one_progress_row(test_setup):
    """Concurrent pings hitting the unlock threshold produce exactly 1 progress row."""
    cp1 = test_setup["cp1"]

    # Set team streak directly to 1 so the next inside ping triggers unlock
    conn = db.get_connection()
    try:
        conn.execute(
            "UPDATE teams SET inside_streak = 1 WHERE id = ?",
            (test_setup["team"]["id"],),
        )
    finally:
        conn.close()

    def send_ping():
        client = TestClient(app)
        client.cookies.set(auth.DEVICE_COOKIE_NAME, test_setup["token"])
        return client.post(
            "/api/ping",
            json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0},
        )

    # Fire two pings concurrently
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(send_ping) for _ in range(2)]
        responses = [f.result() for f in futures]

    # Both requests succeed (HTTP 200); at least one unlocks CP1
    for res in responses:
        assert res.status_code == 200
    assert any(res.json()["status"] == "unlocked" for res in responses)

    # Verify exactly 1 row was written in progress for checkpoint 1
    conn = db.get_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM progress WHERE team_id = ? AND checkpoint_id = ?",
            (test_setup["team"]["id"], cp1["id"]),
        ).fetchone()[0]
        assert count == 1
    finally:
        conn.close()


# --- 5. Information Leak Prevention ---


def test_ping_never_leaks_coordinates_or_distance(player_client, test_setup):
    """Response payloads must never disclose checkpoint coordinates, radius, or distance."""
    cp1 = test_setup["cp1"]

    # Searching response
    res1 = player_client.post(
        "/api/ping",
        json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0},
    )
    data1 = res1.json()
    for forbidden in ["lat", "lng", "radius", "distance", "distance_m", "checkpoint"]:
        assert forbidden not in data1

    # Unlocked response
    res2 = player_client.post(
        "/api/ping",
        json={"lat": cp1["lat"], "lng": cp1["lng"], "accuracy": 10.0},
    )
    data2 = res2.json()
    for forbidden in ["lat", "lng", "radius", "distance", "distance_m", "checkpoint"]:
        assert forbidden not in data2


# --- 6. Speed Plausibility Checks ---


def test_ping_speed_implausible_rejected(player_client, test_setup):
    """Pings exceeding MAX_SPEED_MPS are rejected, reset streak, log event, and leave last_fix intact."""
    conn = db.get_connection()
    try:
        # First valid fix: establishes initial fix position
        res1 = player_client.post(
            "/api/ping",
            json={"lat": 22.693000, "lng": 75.867000, "accuracy": 10.0},
        )
        assert res1.status_code == 200
        assert res1.json()["status"] == "searching"

        # Check DB: team has inside_streak=1 and last_fix recorded
        team_id = test_setup["team"]["id"]
        row1 = conn.execute("SELECT inside_streak, last_fix_lat, last_fix_lng, last_fix_ts FROM teams WHERE id = ?", (team_id,)).fetchone()
        assert row1["inside_streak"] == 1
        assert row1["last_fix_lat"] == 22.693000
        initial_ts = row1["last_fix_ts"]

        # Simulate 2 seconds passing, but jumping 200 metres (~100 m/s > 12 m/s)
        now = time.time()
        with db.write_tx(conn):
            conn.execute("UPDATE teams SET last_fix_ts = ? WHERE id = ?", (now - 2.0, team_id))

        res2 = player_client.post(
            "/api/ping",
            json={"lat": 22.694806, "lng": 75.867000, "accuracy": 10.0},
        )
        assert res2.status_code == 200
        assert res2.json() == {"status": "implausible"}

        # Check DB: inside_streak reset to 0, last_fix coordinates are NOT updated
        row2 = conn.execute("SELECT inside_streak, last_fix_lat, last_fix_lng, last_fix_ts FROM teams WHERE id = ?", (team_id,)).fetchone()
        assert row2["inside_streak"] == 0
        assert row2["last_fix_lat"] == 22.693000  # remains original fix!
        assert row2["last_fix_lng"] == 75.867000

        # Check event logging
        event = conn.execute(
            "SELECT type, detail FROM events WHERE team_id = ? AND type = 'speed_rejected'",
            (team_id,),
        ).fetchone()
        assert event is not None
        assert "speed_mps=" in event["detail"]
    finally:
        conn.close()


def test_ping_rejected_fix_does_not_poison_last_fix(player_client, test_setup):
    """A rejected teleport fix does not poison the last_fix for subsequent legitimate pings."""
    conn = db.get_connection()
    try:
        team_id = test_setup["team"]["id"]

        # 1. First legitimate fix at position A
        res1 = player_client.post(
            "/api/ping",
            json={"lat": 22.693000, "lng": 75.867000, "accuracy": 10.0},
        )
        assert res1.status_code == 200

        # 2. Teleporting fix at position B 2 seconds later (rejected)
        now = time.time()
        with db.write_tx(conn):
            conn.execute("UPDATE teams SET last_fix_ts = ? WHERE id = ?", (now - 4.0, team_id))

        res2 = player_client.post(
            "/api/ping",
            json={"lat": 22.698000, "lng": 75.867000, "accuracy": 10.0},  # ~550m away
        )
        assert res2.json() == {"status": "implausible"}

        # 3. Legitimate second fix near position A (e.g. 5m away, 10s after position A fix)
        with db.write_tx(conn):
            conn.execute("UPDATE teams SET last_fix_ts = ? WHERE id = ?", (now - 10.0, team_id))

        res3 = player_client.post(
            "/api/ping",
            json={"lat": 22.693045, "lng": 75.867000, "accuracy": 10.0},  # ~5m from position A
        )
        # Should be accepted (speed = ~5m / 10s = ~0.5 m/s)
        # If position B had been saved, speed would be ~550m / 10s = ~55 m/s and would have failed!
        assert res3.status_code == 200
        assert res3.json()["status"] == "searching"

        # Verify last_fix updated to position C
        row3 = conn.execute("SELECT last_fix_lat FROM teams WHERE id = ?", (team_id,)).fetchone()
        assert row3["last_fix_lat"] == 22.693045
    finally:
        conn.close()


def test_ping_speed_long_gap_signal_loss_accepted(player_client, test_setup):
    """A long gap followed by a 600m jump (e.g. 5 minutes signal loss) gives low speed and is accepted."""
    conn = db.get_connection()
    try:
        team_id = test_setup["team"]["id"]

        # First fix
        player_client.post(
            "/api/ping",
            json={"lat": 22.693000, "lng": 75.867000, "accuracy": 10.0},
        )

        # Simulate 5 minutes (300 s) gap
        now = time.time()
        with db.write_tx(conn):
            conn.execute("UPDATE teams SET last_fix_ts = ? WHERE id = ?", (now - 300.0, team_id))

        # 600m away fix (~22.698417)
        res = player_client.post(
            "/api/ping",
            json={"lat": 22.698417, "lng": 75.867000, "accuracy": 10.0},
        )
        # 600m / 300s = 2 m/s <= 12 m/s -> accepted!
        assert res.status_code == 200
        assert res.json()["status"] != "implausible"
    finally:
        conn.close()

