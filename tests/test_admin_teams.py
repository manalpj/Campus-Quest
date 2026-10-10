"""Tests for administrative team management (/api/gods/teams) under Section 3.2.

Covers:
- require_admin protection on all admin team endpoints
- Listing teams with live metrics, progress, and device status
- Release device action and subsequent re-pairing
- Admin force-clear checkpoint progression, zero power-up rule, and finished state
- Time adjustment (penalties and bonuses) with reason logging
- Team deletion with cascading cleanup
- Verification of operational audit log entries in the events table
"""

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
    test_db = tmp_path / "test_admin_teams.db"
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
def anon_client():
    """Return an unauthenticated TestClient without admin credentials."""
    return TestClient(app)


def seed_checkpoints(count: int = 5):
    """Seed the database with N valid checkpoints inside DAVV bounds."""
    conn = db.get_connection()
    try:
        base_lat = (config.CAMPUS_BOUNDS_SW_LAT + config.CAMPUS_BOUNDS_NE_LAT) / 2.0
        base_lng = (config.CAMPUS_BOUNDS_SW_LNG + config.CAMPUS_BOUNDS_NE_LNG) / 2.0
        for i in range(1, count + 1):
            db.create_checkpoint(
                conn,
                name=f"Checkpoint {i}",
                lat=round(base_lat + (i * 0.0001), 6),
                lng=round(base_lng + (i * 0.0001), 6),
                radius=30.0,
                clue=f"Clue for checkpoint {i}",
                hint=f"Hint for checkpoint {i}",
                story=f"Story for checkpoint {i}",
                position=i,
            )
    finally:
        conn.close()


def register_sample_team(client: TestClient, name: str = "Trailblazers"):
    """Register a team and return registration response payload."""
    resp = client.post(
        "/api/register",
        json={"name": name, "members": ["Alice", "Bob"]},
    )
    assert resp.status_code == 201
    return resp.json()


def test_admin_teams_require_admin(anon_client):
    """Verify all /api/gods/teams endpoints strictly reject unauthenticated requests."""
    assert anon_client.get("/api/gods/teams").status_code == 401
    assert anon_client.post("/api/gods/teams/1/release-device").status_code == 401
    assert anon_client.post("/api/gods/teams/1/force-clear", json={"reason": "Test"}).status_code == 401
    assert anon_client.post("/api/gods/teams/1/adjust-time", json={"minutes": 5, "reason": "Test"}).status_code == 401
    assert anon_client.delete("/api/gods/teams/1").status_code == 401


def test_list_teams_empty_and_populated(admin_client, anon_client):
    """Verify listing teams returns accurate details, members, and progress metrics."""
    seed_checkpoints(5)

    # Initially empty
    res = admin_client.get("/api/gods/teams")
    assert res.status_code == 200
    assert res.json() == []

    # Register sample team
    reg_data = register_sample_team(anon_client, name="Cyber Phoenix")

    res = admin_client.get("/api/gods/teams")
    assert res.status_code == 200
    teams = res.json()
    assert len(teams) == 1
    t = teams[0]
    assert t["name"] == "Cyber Phoenix"
    assert t["code"] == reg_data["code"]
    assert t["members"] == ["Alice", "Bob"]
    assert t["device_bound"] is True
    assert t["cleared"] == 0
    assert t["total"] == 5
    assert t["finished"] is False
    assert t["next_checkpoint"]["position"] == 1
    assert t["next_checkpoint"]["name"] == "Checkpoint 1"


def test_release_device_and_rejoin(admin_client, anon_client):
    """Verify releasing device frees the device token lock and allows a new device to pair."""
    reg_data = register_sample_team(anon_client, name="Robo Racers")
    team_code = reg_data["code"]

    # Another phone attempting to join while bound is rejected with 409
    other_phone = TestClient(app)
    join_res = other_phone.post("/api/join", json={"code": team_code})
    assert join_res.status_code == 409

    # Admin releases device
    teams = admin_client.get("/api/gods/teams").json()
    team_id = teams[0]["id"]

    rel_res = admin_client.post(f"/api/gods/teams/{team_id}/release-device")
    assert rel_res.status_code == 200
    assert rel_res.json()["status"] == "ok"

    # Verify team device_bound is now False
    teams_after = admin_client.get("/api/gods/teams").json()
    assert teams_after[0]["device_bound"] is False

    # Now the other phone can successfully join and bind
    join_res2 = other_phone.post("/api/join", json={"code": team_code})
    assert join_res2.status_code == 200
    join_data = join_res2.json()
    assert join_data["code"] == team_code
    assert auth.DEVICE_COOKIE_NAME in join_res2.cookies

    # Releasing non-existent team returns 404
    assert admin_client.post("/api/gods/teams/999/release-device").status_code == 404


def test_force_clear_checkpoint_lifecycle(admin_client, anon_client):
    """Verify organizer force-clear advances checkpoint, awards no power-up, and respects game state."""
    seed_checkpoints(5)
    reg_data = register_sample_team(anon_client, name="Solar Seekers")
    teams = admin_client.get("/api/gods/teams").json()
    team_id = teams[0]["id"]

    # Cannot force clear before game start
    res_before = admin_client.post(
        f"/api/gods/teams/{team_id}/force-clear",
        json={"reason": "Stuck in setup"},
    )
    assert res_before.status_code == 400
    assert "not currently running" in res_before.json()["detail"]

    # Start game
    start_res = admin_client.post("/api/gods/game/start")
    assert start_res.status_code == 200

    # Force clear checkpoint 1
    fc1 = admin_client.post(
        f"/api/gods/teams/{team_id}/force-clear",
        json={"reason": "GPS multipath obstruction near building A"},
    )
    assert fc1.status_code == 200
    data1 = fc1.json()["cleared"]
    assert data1["checkpoint_name"] == "Checkpoint 1"
    assert data1["cleared"] == 1
    assert data1["is_last"] is False

    # Verify team state: cleared=1, next is Checkpoint 2, NO powerup awarded (radar=0, boost=0)
    team_state = admin_client.get("/api/gods/teams").json()[0]
    assert team_state["cleared"] == 1
    assert team_state["radar_left"] == 0
    assert team_state["boost_left"] == 0
    assert team_state["next_checkpoint"]["position"] == 2

    # Force clear checkpoints 2, 3, 4
    for i in range(2, 5):
        admin_client.post(
            f"/api/gods/teams/{team_id}/force-clear",
            json={"reason": f"Clear checkpoint {i}"},
        )

    # Force clear checkpoint 5 (last checkpoint)
    fc_last = admin_client.post(
        f"/api/gods/teams/{team_id}/force-clear",
        json={"reason": "Final checkpoint verification by judge"},
    )
    assert fc_last.status_code == 200
    data_last = fc_last.json()["cleared"]
    assert data_last["is_last"] is True

    # Team is now finished
    team_state_fin = admin_client.get("/api/gods/teams").json()[0]
    assert team_state_fin["cleared"] == 5
    assert team_state_fin["finished"] is True
    assert team_state_fin["next_checkpoint"] is None

    # Force-clearing an already finished team returns 400
    fc3 = admin_client.post(
        f"/api/gods/teams/{team_id}/force-clear",
        json={"reason": "Extra clear attempt"},
    )
    assert fc3.status_code == 400
    assert "completed all checkpoints" in fc3.json()["detail"]


def test_adjust_team_time_and_ranking(admin_client, anon_client):
    """Verify admin time adjustments add/subtract penalty minutes and update leaderboard."""
    seed_checkpoints(5)
    register_sample_team(anon_client, name="Speed Demons")
    team_id = admin_client.get("/api/gods/teams").json()[0]["id"]

    # Add +5 min penalty
    adj1 = admin_client.post(
        f"/api/gods/teams/{team_id}/adjust-time",
        json={"minutes": 5, "reason": "Boundary violation penalty"},
    )
    assert adj1.status_code == 200
    assert adj1.json()["new_penalty_s"] == 300

    # Subtract 2 min credit
    adj2 = admin_client.post(
        f"/api/gods/teams/{team_id}/adjust-time",
        json={"minutes": -2, "reason": "Organizer timing offset credit"},
    )
    assert adj2.status_code == 200
    assert adj2.json()["new_penalty_s"] == 180

    # Verify team overview reflects penalty
    t = admin_client.get("/api/gods/teams").json()[0]
    assert t["penalty_s"] == 180
    assert t["adjusted_time"] == "03:00"

    # Adjusting non-existent team returns 404
    assert admin_client.post(
        "/api/gods/teams/999/adjust-time",
        json={"minutes": 1, "reason": "Missing team"},
    ).status_code == 404


def test_delete_team_cascading(admin_client, anon_client):
    """Verify deleting a team removes team and cascades progress records."""
    seed_checkpoints(5)
    admin_client.post("/api/gods/game/start")
    register_sample_team(anon_client, name="Temp Team")
    team_id = admin_client.get("/api/gods/teams").json()[0]["id"]

    # Force clear a checkpoint so progress row exists
    admin_client.post(f"/api/gods/teams/{team_id}/force-clear", json={"reason": "Step 1"})

    # Delete team
    del_res = admin_client.delete(f"/api/gods/teams/{team_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted_id"] == team_id

    # Verify team is gone from admin list
    assert admin_client.get("/api/gods/teams").json() == []

    # Deleting again returns 404
    assert admin_client.delete(f"/api/gods/teams/{team_id}").status_code == 404


def test_operational_audit_logging(admin_client, anon_client):
    """Verify all admin team modifications write descriptive audit events into the events table."""
    seed_checkpoints(5)
    admin_client.post("/api/gods/game/start")
    register_sample_team(anon_client, name="Audited Crew")
    team_id = admin_client.get("/api/gods/teams").json()[0]["id"]

    admin_client.post(f"/api/gods/teams/{team_id}/release-device")
    admin_client.post(f"/api/gods/teams/{team_id}/force-clear", json={"reason": "Signal dead zone"})
    admin_client.post(f"/api/gods/teams/{team_id}/adjust-time", json={"minutes": 3, "reason": "Late check-in"})
    admin_client.delete(f"/api/gods/teams/{team_id}")

    # Inspect events in database
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT type, detail FROM events ORDER BY id ASC").fetchall()
        event_types = [r["type"] for r in rows]
        assert "device_released" in event_types
        assert "admin_force_clear" in event_types
        assert "admin_time_adjusted" in event_types
        assert "team_deleted" in event_types
    finally:
        conn.close()
