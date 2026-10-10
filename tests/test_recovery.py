"""Tests for stuck-team recovery: player Skip and admin force-clear.

Verifies:
- Skip refused too early (before SKIP_WAIT_S)
- Skip adds exactly SKIP_PENALTY_S
- Double Skip clears one checkpoint
- Force-clear needs admin
- Force-clear requires reason, writes how='admin', adds 0 penalty, awards no power-up
- Skipped and force-cleared checkpoints count as cleared for ranking
"""

import time
import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
import game
from main import app


@pytest.fixture(autouse=True)
def clean_test_env(tmp_path, monkeypatch):
    """Ensure a fresh SQLite database and default settings for each test."""
    test_db = tmp_path / "test_recovery.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


def get_admin_client() -> TestClient:
    """Create TestClient authenticated with a valid admin cookie."""
    client = TestClient(app)
    cookie_val = auth.create_admin_cookie_value(config.ADMIN_USER)
    client.cookies.set(auth.ADMIN_COOKIE_NAME, cookie_val)
    return client


def seed_test_checkpoints(conn, count=3):
    """Create test checkpoints with valid coordinates."""
    with db.write_tx(conn):
        for i in range(1, count + 1):
            conn.execute(
                """
                INSERT INTO checkpoints (name, lat, lng, radius, position, clue, hint, story)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"Checkpoint {i}",
                    22.6928 + (i * 0.0005),
                    75.8676 + (i * 0.0005),
                    30.0,
                    i,
                    f"Clue for {i}",
                    f"Hint for {i}",
                    f"Historical story for {i}",
                ),
            )


def start_running_game(conn, started_at_ts=None):
    """Transition game state to running with a start timestamp."""
    start_ts = started_at_ts if started_at_ts is not None else time.time() - 100
    db.set_setting(conn, "game_state", "running")
    db.set_setting(conn, "started_at", str(start_ts))


def test_is_skip_allowed_pure_logic():
    """is_skip_allowed returns True only when elapsed time meets or exceeds limit."""
    assert not game.is_skip_allowed(599.9, wait_limit_s=600)
    assert game.is_skip_allowed(600.0, wait_limit_s=600)
    assert game.is_skip_allowed(650.0, wait_limit_s=600)


def test_skip_refused_too_early():
    """POST /api/skip returns 403 Forbidden if team has not waited SKIP_WAIT_S on checkpoint."""
    conn = db.get_connection()
    try:
        seed_test_checkpoints(conn, count=3)
        # Game started just 10 seconds ago
        now = time.time()
        start_running_game(conn, started_at_ts=now - 10)

        # Register team
        player_client = TestClient(app)
        reg_res = player_client.post(
            "/api/register",
            json={"name": "EarlyBirds", "members": ["Alice", "Bob"]},
        )
        assert reg_res.status_code == 201

        # Attempt to skip immediately
        skip_res = player_client.post("/api/skip")
        assert skip_res.status_code == 403
        assert "Skip is not available yet" in skip_res.json()["detail"]
    finally:
        conn.close()


def test_skip_adds_exactly_penalty_and_returns_no_story():
    """POST /api/skip adds SKIP_PENALTY_S, writes how='skipped', awards no power-up, and returns next clue without story."""
    conn = db.get_connection()
    try:
        seed_test_checkpoints(conn, count=3)
        # Game started 700 seconds ago (> SKIP_WAIT_S=600)
        now = time.time()
        start_running_game(conn, started_at_ts=now - 700)

        player_client = TestClient(app)
        reg_res = player_client.post(
            "/api/register",
            json={"name": "Pioneers", "members": ["Charlie", "Dana"]},
        )
        assert reg_res.status_code == 201
        team_id = reg_res.json()["id"]

        # Initial powerups
        team_before = db.get_team_by_id(conn, team_id)
        assert team_before["penalty_s"] == 0
        assert team_before["radar_left"] == 0
        assert team_before["boost_left"] == 0

        # Perform skip
        skip_res = player_client.post("/api/skip")
        assert skip_res.status_code == 200
        data = skip_res.json()

        assert data["status"] == "skipped"
        assert data["checkpoint_name"] == "Checkpoint 1"
        assert data["story"] is None
        assert data["next_clue"] == "Clue for 2"
        assert data["cleared"] == 1
        assert data["total"] == 3
        assert data["penalty_s"] == config.SKIP_PENALTY_S
        assert data["penalty_added_s"] == config.SKIP_PENALTY_S

        # Verify DB records
        team_after = db.get_team_by_id(conn, team_id)
        assert team_after["penalty_s"] == config.SKIP_PENALTY_S
        # No power-ups awarded
        assert team_after["radar_left"] == 0
        assert team_after["boost_left"] == 0

        # Check progress table
        progress_row = conn.execute(
            "SELECT * FROM progress WHERE team_id = ? AND checkpoint_id = 1",
            (team_id,),
        ).fetchone()
        assert progress_row is not None
        assert progress_row["how"] == "skipped"

        # Check audit event log
        event_row = conn.execute(
            "SELECT * FROM events WHERE team_id = ? AND type = ?",
            (team_id, game.EVENT_CHECKPOINT_SKIPPED),
        ).fetchone()
        assert event_row is not None
        assert "penalty_s=600" in event_row["detail"]
    finally:
        conn.close()


def test_double_skip_clears_one_checkpoint():
    """Double-clicking / concurrent skip calls clear only one checkpoint and do not double-penalize."""
    conn = db.get_connection()
    try:
        seed_test_checkpoints(conn, count=3)
        now = time.time()
        start_running_game(conn, started_at_ts=now - 700)

        player_client = TestClient(app)
        reg_res = player_client.post(
            "/api/register",
            json={"name": "FastClickers", "members": ["Eve", "Frank"]},
        )
        assert reg_res.status_code == 201
        team_id = reg_res.json()["id"]

        # First skip succeeds
        res1 = player_client.post("/api/skip")
        assert res1.status_code == 200
        assert res1.json()["cleared"] == 1

        # Second immediate skip should either fail as too early for checkpoint 2 or 409
        res2 = player_client.post("/api/skip")
        # Checkpoint 2 was just started seconds ago, so wait time is not satisfied!
        assert res2.status_code == 403 or res2.status_code == 409

        # Verify only 1 progress row exists
        cleared_count, _ = db.get_team_progress_counts(conn, team_id)
        assert cleared_count == 1

        # Penalty must be exactly 1 skip penalty, not doubled
        team_row = db.get_team_by_id(conn, team_id)
        assert team_row["penalty_s"] == config.SKIP_PENALTY_S
    finally:
        conn.close()


def test_force_clear_needs_admin():
    """POST /api/gods/teams/{id}/clear requires admin authentication."""
    unauth_client = TestClient(app)
    res = unauth_client.post(
        "/api/gods/teams/1/clear",
        json={"reason": "Organizer bypass"},
    )
    assert res.status_code == 401


def test_force_clear_validates_reason():
    """POST /api/gods/teams/{id}/clear requires a non-empty reason between 3 and 120 chars."""
    admin_client = get_admin_client()
    conn = db.get_connection()
    try:
        seed_test_checkpoints(conn, count=2)
        start_running_game(conn)

        # Register team
        reg_res = admin_client.post(
            "/api/register",
            json={"name": "ValidationTeam", "members": ["Grace", "Heidi"]},
        )
        assert reg_res.status_code == 201
        team_id = reg_res.json()["id"]

        # Too short reason
        res_short = admin_client.post(
            f"/api/gods/teams/{team_id}/clear",
            json={"reason": "no"},
        )
        assert res_short.status_code == 422

        # Missing reason
        res_empty = admin_client.post(
            f"/api/gods/teams/{team_id}/clear",
            json={},
        )
        assert res_empty.status_code == 422
    finally:
        conn.close()


def test_force_clear_succeeds_with_no_penalty_and_no_powerup():
    """Admin force-clear marks checkpoint as how='admin', adds 0 penalty, awards no power-up, and logs reason."""
    admin_client = get_admin_client()
    conn = db.get_connection()
    try:
        seed_test_checkpoints(conn, count=2)
        start_running_game(conn)

        # Register team
        reg_res = admin_client.post(
            "/api/register",
            json={"name": "StuckTeam", "members": ["Ivan", "Judy"]},
        )
        assert reg_res.status_code == 201
        team_id = reg_res.json()["id"]

        # Force clear checkpoint 1
        clear_res = admin_client.post(
            f"/api/gods/teams/{team_id}/clear",
            json={"reason": "Construction work blocked checkpoint 1 entrance"},
        )
        assert clear_res.status_code == 200
        data = clear_res.json()
        assert data["status"] == "ok"
        assert data["checkpoint_name"] == "Checkpoint 1"
        assert data["cleared"] == 1
        assert data["total"] == 2
        assert data["next_clue"] == "Clue for 2"

        # Check DB state
        team_row = db.get_team_by_id(conn, team_id)
        assert team_row["penalty_s"] == 0
        assert team_row["radar_left"] == 0
        assert team_row["boost_left"] == 0

        # Check progress table
        p_row = conn.execute(
            "SELECT * FROM progress WHERE team_id = ? AND checkpoint_id = 1",
            (team_id,),
        ).fetchone()
        assert p_row is not None
        assert p_row["how"] == "admin"

        # Check audit event log
        event_row = conn.execute(
            "SELECT * FROM events WHERE team_id = ? AND type = ?",
            (team_id, game.EVENT_CHECKPOINT_FORCE_CLEARED),
        ).fetchone()
        assert event_row is not None
        assert "Construction work blocked checkpoint 1 entrance" in event_row["detail"]
    finally:
        conn.close()


def test_skip_and_force_clear_count_for_ranking():
    """Skipped and force-cleared checkpoints count as cleared on the leaderboard."""
    admin_client = get_admin_client()
    conn = db.get_connection()
    try:
        seed_test_checkpoints(conn, count=2)
        now = time.time()
        start_running_game(conn, started_at_ts=now - 700)

        # Team A skips checkpoint 1
        client_a = TestClient(app)
        reg_a = client_a.post("/api/register", json={"name": "TeamA", "members": ["A1", "A2"]})
        assert reg_a.status_code == 201
        team_a_id = reg_a.json()["id"]
        skip_a = client_a.post("/api/skip")
        assert skip_a.status_code == 200

        # Team B is force-cleared by admin
        client_b = TestClient(app)
        reg_b = client_b.post("/api/register", json={"name": "TeamB", "members": ["B1", "B2"]})
        assert reg_b.status_code == 201
        team_b_id = reg_b.json()["id"]
        clear_b = admin_client.post(
            f"/api/gods/teams/{team_b_id}/clear",
            json={"reason": "Admin test clear"},
        )
        assert clear_b.status_code == 200

        # Fetch leaderboard
        leaderboard_res = client_a.get("/api/leaderboard")
        assert leaderboard_res.status_code == 200
        standings = leaderboard_res.json()
        assert len(standings) == 2

        # Both have 1 cleared checkpoint
        team_a_lb = next(t for t in standings if t["name"] == "TeamA")
        team_b_lb = next(t for t in standings if t["name"] == "TeamB")
        assert team_a_lb["cleared"] == 1
        assert team_b_lb["cleared"] == 1

        # Team A has +600s penalty, Team B has 0 penalty -> Team B ranks higher
        assert team_b_lb["rank"] == 1
        assert team_a_lb["rank"] == 2
        assert team_a_lb["adjusted_time_s"] >= team_b_lb["adjusted_time_s"] + 600
    finally:
        conn.close()
