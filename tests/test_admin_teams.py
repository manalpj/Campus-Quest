"""Tests for administrator Teams management tab and endpoints.

Verifies GET /api/gods/teams, POST /api/gods/teams/{id}/release,
POST /api/gods/teams/{id}/adjust, and DELETE /api/gods/teams/{id},
including authentication enforcement, event logging, and state integrity.
"""

import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
import game
from main import app


@pytest.fixture(autouse=True)
def clean_test_env(tmp_path, monkeypatch):
    """Ensure a fresh SQLite database and configuration for each test."""
    test_db = tmp_path / "test_admin_teams.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


def get_admin_client() -> TestClient:
    """Create TestClient authenticated with a valid admin cookie."""
    client = TestClient(app)
    cookie_val = auth.create_admin_cookie_value(config.ADMIN_USER)
    client.cookies.set(auth.ADMIN_COOKIE_NAME, cookie_val)
    return client


def test_admin_teams_require_authentication():
    """All /api/gods/teams routes reject requests without a valid admin cookie."""
    unauth_client = TestClient(app)

    # GET /api/gods/teams
    r_get = unauth_client.get("/api/gods/teams")
    assert r_get.status_code == 401

    # POST /api/gods/teams/1/release
    r_rel = unauth_client.post("/api/gods/teams/1/release")
    assert r_rel.status_code == 401

    # POST /api/gods/teams/1/adjust
    r_adj = unauth_client.post(
        "/api/gods/teams/1/adjust",
        json={"minutes": 5, "reason": "Penalty test"},
    )
    assert r_adj.status_code == 401

    # DELETE /api/gods/teams/1
    r_del = unauth_client.delete("/api/gods/teams/1")
    assert r_del.status_code == 401

    # POST /api/gods/teams/reset
    r_rst_all = unauth_client.post("/api/gods/teams/reset")
    assert r_rst_all.status_code == 401

    # POST /api/gods/teams/1/reset
    r_rst_one = unauth_client.post("/api/gods/teams/1/reset")
    assert r_rst_one.status_code == 401


def test_get_teams_list():
    """GET /api/gods/teams returns team name, members, code, device status, cleared count, and adjusted time."""
    client = get_admin_client()

    # Register two teams
    r1 = client.post("/api/register", json={"name": "Thunder", "members": ["Aarav", "Kabir"]})
    assert r1.status_code == 201
    t1_data = r1.json()

    r2 = client.post("/api/register", json={"name": "Lightning", "members": ["Riya", "Diya"]})
    assert r2.status_code == 201
    t2_data = r2.json()

    res = client.get("/api/gods/teams")
    assert res.status_code == 200
    teams = res.json()
    assert len(teams) >= 2

    th = next(t for t in teams if t["id"] == t1_data["id"])
    assert th["name"] == "Thunder"
    assert th["code"] == t1_data["code"]
    assert th["members"] == ["Aarav", "Kabir"]
    assert th["device_status"] == "bound"
    assert th["cleared"] == 0
    assert th["adjusted_time"] == "00:00"
    assert th["last_seen"] is not None


def test_release_device():
    """POST /api/gods/teams/{id}/release clears device_hash, locks out old phone, allows new join, and logs event."""
    client = get_admin_client()

    # Register a team
    player_client = TestClient(app)
    r_reg = player_client.post("/api/register", json={"name": "Panthers", "members": ["Nitin", "Pooja"]})
    assert r_reg.status_code == 201
    team_data = r_reg.json()
    team_id = team_data["id"]
    code = team_data["code"]

    # Verify old phone can call /api/state
    r_state_before = player_client.get("/api/state")
    assert r_state_before.status_code == 200

    # Release device via admin endpoint
    r_rel = client.post(f"/api/gods/teams/{team_id}/release")
    assert r_rel.status_code == 200
    assert r_rel.json()["device_status"] == "free"

    # Verify old phone is now locked out (401)
    r_state_after = player_client.get("/api/state")
    assert r_state_after.status_code == 401

    # Verify new phone can join with the team code
    new_phone_client = TestClient(app)
    r_join = new_phone_client.post("/api/join", json={"code": code})
    assert r_join.status_code == 200
    assert r_join.json()["id"] == team_id

    # Verify new phone is authenticated
    r_new_state = new_phone_client.get("/api/state")
    assert r_new_state.status_code == 200

    # Verify event logged in events table
    conn = db.get_connection()
    try:
        events = db.get_latest_events(conn, limit=10)
        types = [e["type"] for e in events]
        assert game.EVENT_DEVICE_RELEASED in types
    finally:
        conn.close()


def test_release_device_not_found():
    """POST /api/gods/teams/{id}/release returns 404 for non-existent team."""
    client = get_admin_client()
    res = client.post("/api/gods/teams/9999/release")
    assert res.status_code == 404


def test_adjust_team_time_positive_and_negative():
    """POST /api/gods/teams/{id}/adjust adds penalty (+min) or awards bonus (-min) and logs reason."""
    client = get_admin_client()

    r_reg = client.post("/api/register", json={"name": "Cheetahs", "members": ["Dev", "Sam"]})
    assert r_reg.status_code == 201
    team_id = r_reg.json()["id"]

    # Add +5 minutes penalty
    r_adj1 = client.post(
        f"/api/gods/teams/{team_id}/adjust",
        json={"minutes": 5, "reason": "Left campus bounds warning"},
    )
    assert r_adj1.status_code == 200
    data1 = r_adj1.json()
    assert data1["penalty_s"] == 300
    assert data1["bonus_s"] == 0

    # Award -2 minutes bonus (credit)
    r_adj2 = client.post(
        f"/api/gods/teams/{team_id}/adjust",
        json={"minutes": -2, "reason": "Staff delay at checkpoint"},
    )
    assert r_adj2.status_code == 200
    data2 = r_adj2.json()
    assert data2["penalty_s"] == 300
    assert data2["bonus_s"] == 120

    # Verify team row reflects updated times in GET /api/gods/teams
    r_list = client.get("/api/gods/teams")
    team = next(t for t in r_list.json() if t["id"] == team_id)
    assert team["penalty_s"] == 300
    assert team["bonus_s"] == 120
    # adjusted_time = elapsed (0) + 300 - 120 = 180s = 03:00
    assert team["adjusted_time"] == "03:00"

    # Verify event logs exist with reasons
    conn = db.get_connection()
    try:
        events = db.get_latest_events(conn, limit=10)
        adj_events = [e for e in events if e["type"] == game.EVENT_TIME_ADJUSTED]
        assert len(adj_events) >= 2
        details = [e["detail"] for e in adj_events]
        assert any("Left campus bounds warning" in d for d in details)
        assert any("Staff delay at checkpoint" in d for d in details)
    finally:
        conn.close()


def test_adjust_team_validation_errors():
    """POST /api/gods/teams/{id}/adjust rejects invalid inputs."""
    client = get_admin_client()

    r_reg = client.post("/api/register", json={"name": "Tigers", "members": ["Raj", "Ravi"]})
    team_id = r_reg.json()["id"]

    # Zero minutes
    r_zero = client.post(
        f"/api/gods/teams/{team_id}/adjust",
        json={"minutes": 0, "reason": "Valid reason text"},
    )
    assert r_zero.status_code == 422

    # Reason too short (< 3 chars)
    r_short = client.post(
        f"/api/gods/teams/{team_id}/adjust",
        json={"minutes": 2, "reason": "hi"},
    )
    assert r_short.status_code == 422

    # Reason too long (> 120 chars)
    r_long = client.post(
        f"/api/gods/teams/{team_id}/adjust",
        json={"minutes": 2, "reason": "x" * 121},
    )
    assert r_long.status_code == 422

    # Team not found
    r_nf = client.post(
        "/api/gods/teams/9999/adjust",
        json={"minutes": 2, "reason": "Valid reason"},
    )
    assert r_nf.status_code == 404


def test_delete_team():
    """DELETE /api/gods/teams/{id} deletes team, cascades cleanly, and logs event."""
    client = get_admin_client()

    r_reg = client.post("/api/register", json={"name": "Falcons", "members": ["Karan", "Simran"]})
    assert r_reg.status_code == 201
    team_id = r_reg.json()["id"]

    # Delete team
    r_del = client.delete(f"/api/gods/teams/{team_id}")
    assert r_del.status_code == 200
    assert r_del.json()["deleted_id"] == team_id

    # Verify team no longer in list
    r_list = client.get("/api/gods/teams")
    assert all(t["id"] != team_id for t in r_list.json())

    # Deleting again returns 404
    r_del2 = client.delete(f"/api/gods/teams/{team_id}")
    assert r_del2.status_code == 404

    # Verify EVENT_TEAM_DELETED was logged
    conn = db.get_connection()
    try:
        events = db.get_latest_events(conn, limit=10)
        types = [e["type"] for e in events]
        assert game.EVENT_TEAM_DELETED in types
    finally:
        conn.close()


def test_reset_all_teams_progress():
    """POST /api/gods/teams/reset resets progress, powerups, streaks, finished_at for all teams."""
    client = get_admin_client()

    r1 = client.post("/api/register", json={"name": "Team Alpha", "members": ["A1", "A2"]})
    team1_id = r1.json()["id"]
    r2 = client.post("/api/register", json={"name": "Team Beta", "members": ["B1", "B2"]})
    team2_id = r2.json()["id"]

    conn = db.get_connection()
    try:
        cp = db.create_checkpoint(conn, "CP1", 22.7, 75.8, 30.0, 1, "Clue 1", "Hint 1")
        cp_id = cp["id"]
        with db.write_tx(conn):
            conn.execute(
                "INSERT INTO progress (team_id, checkpoint_id, unlocked_at, elapsed_s, how) VALUES (?, ?, ?, ?, 'gps')",
                (team1_id, cp_id, 50.0, 50),
            )
            conn.execute(
                "INSERT INTO progress (team_id, checkpoint_id, unlocked_at, elapsed_s, how) VALUES (?, ?, ?, ?, 'gps')",
                (team2_id, cp_id, 75.0, 75),
            )
            conn.execute(
                "INSERT INTO hint_uses (team_id, checkpoint_id, used_at) VALUES (?, ?, ?)",
                (team1_id, cp_id, 30.0),
            )
            conn.execute(
                "UPDATE teams SET finished_at = 999.0, penalty_s = 180, inside_streak = 2 WHERE id = ?",
                (team1_id,),
            )
            conn.execute(
                "UPDATE teams SET finished_at = 888.0, penalty_s = 600, radar_left = 1 WHERE id = ?",
                (team2_id,),
            )
    finally:
        conn.close()

    # Reset all teams
    res = client.post("/api/gods/teams/reset")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["teams_reset"] >= 2

    # Verify both teams reset in database
    conn = db.get_connection()
    try:
        t1 = db.get_team_by_id(conn, team1_id)
        t2 = db.get_team_by_id(conn, team2_id)
        assert t1["finished_at"] is None
        assert t1["penalty_s"] == 0
        assert t1["inside_streak"] == 0
        assert t2["finished_at"] is None
        assert t2["penalty_s"] == 0
        assert t2["radar_left"] == 0

        c1, _ = db.get_team_progress_counts(conn, team1_id)
        c2, _ = db.get_team_progress_counts(conn, team2_id)
        assert c1 == 0
        assert c2 == 0

        events = db.get_latest_events(conn, limit=5)
        assert any(e["type"] == game.EVENT_TEAMS_PROGRESS_RESET for e in events)
    finally:
        conn.close()


def test_reset_single_team_progress():
    """POST /api/gods/teams/{id}/reset resets only the specified team's progress."""
    client = get_admin_client()

    r1 = client.post("/api/register", json={"name": "Team Solo", "members": ["S1", "S2"]})
    team1_id = r1.json()["id"]
    r2 = client.post("/api/register", json={"name": "Team Untouched", "members": ["U1", "U2"]})
    team2_id = r2.json()["id"]

    conn = db.get_connection()
    try:
        cp = db.create_checkpoint(conn, "CP Solo", 22.7, 75.8, 30.0, 1, "Clue", "Hint")
        cp_id = cp["id"]
        with db.write_tx(conn):
            conn.execute(
                "INSERT INTO progress (team_id, checkpoint_id, unlocked_at, elapsed_s, how) VALUES (?, ?, ?, ?, 'gps')",
                (team1_id, cp_id, 40.0, 40),
            )
            conn.execute(
                "INSERT INTO progress (team_id, checkpoint_id, unlocked_at, elapsed_s, how) VALUES (?, ?, ?, ?, 'gps')",
                (team2_id, cp_id, 45.0, 45),
            )
            conn.execute("UPDATE teams SET finished_at = 500.0, penalty_s = 300 WHERE id = ?", (team1_id,))
            conn.execute("UPDATE teams SET finished_at = 600.0, penalty_s = 400 WHERE id = ?", (team2_id,))
    finally:
        conn.close()

    # Reset only team 1
    res = client.post(f"/api/gods/teams/{team1_id}/reset")
    assert res.status_code == 200
    assert res.json()["team_id"] == team1_id

    # 404 for non-existent team
    res_404 = client.post("/api/gods/teams/99999/reset")
    assert res_404.status_code == 404

    # Verify team 1 reset, team 2 untouched
    conn = db.get_connection()
    try:
        t1 = db.get_team_by_id(conn, team1_id)
        t2 = db.get_team_by_id(conn, team2_id)
        assert t1["finished_at"] is None
        assert t1["penalty_s"] == 0
        assert t2["finished_at"] == 600.0
        assert t2["penalty_s"] == 400

        c1, _ = db.get_team_progress_counts(conn, team1_id)
        c2, _ = db.get_team_progress_counts(conn, team2_id)
        assert c1 == 0
        assert c2 == 1

        events = db.get_latest_events(conn, limit=5)
        assert any(e["type"] == game.EVENT_TEAM_RESET for e in events)
    finally:
        conn.close()

