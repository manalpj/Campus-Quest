"""Tests for checkpoint domain logic, database operations, validation, and admin endpoints."""

import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
import game
from main import app


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    """Ensure a temporary isolated database for every checkpoint test."""
    test_db = tmp_path / "test_checkpoints.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db(str(test_db))


@pytest.fixture
def admin_client():
    """Return a TestClient authenticated with a valid signed admin session cookie."""
    client = TestClient(app)
    admin_cookie = auth.create_admin_cookie_value(config.ADMIN_USER)
    client.cookies.set(auth.ADMIN_COOKIE_NAME, admin_cookie)
    return client


@pytest.fixture
def anon_client():
    """Return an unauthenticated TestClient without admin cookies."""
    return TestClient(app)


# --- 1. Pure Game Domain Logic Tests ---


def test_is_within_campus_bounds():
    """Validate that coordinate verification strictly enforces campus boundaries."""
    sw_lat, sw_lng = 22.6850, 75.8580
    ne_lat, ne_lng = 22.7010, 75.8780

    # Inside
    assert game.is_within_campus_bounds(22.6928, 75.8676, sw_lat, sw_lng, ne_lat, ne_lng) is True
    # Exactly on boundary corners
    assert game.is_within_campus_bounds(sw_lat, sw_lng, sw_lat, sw_lng, ne_lat, ne_lng) is True
    assert game.is_within_campus_bounds(ne_lat, ne_lng, sw_lat, sw_lng, ne_lat, ne_lng) is True

    # Outside: north
    assert game.is_within_campus_bounds(22.7050, 75.8676, sw_lat, sw_lng, ne_lat, ne_lng) is False
    # Outside: south
    assert game.is_within_campus_bounds(22.6800, 75.8676, sw_lat, sw_lng, ne_lat, ne_lng) is False
    # Outside: west
    assert game.is_within_campus_bounds(22.6928, 75.8500, sw_lat, sw_lng, ne_lat, ne_lng) is False
    # Outside: east
    assert game.is_within_campus_bounds(22.6928, 75.8850, sw_lat, sw_lng, ne_lat, ne_lng) is False


def test_compute_target_position():
    """Verify target position assignment, auto-appending, and boundary clamping."""
    assert game.compute_target_position(None, total_existing=3) == 4
    assert game.compute_target_position(10, total_existing=3) == 4
    assert game.compute_target_position(0, total_existing=3) == 1
    assert game.compute_target_position(-5, total_existing=3) == 1
    assert game.compute_target_position(2, total_existing=3) == 2


# --- 2. Database Operations & Safe Reordering Tests ---


def test_db_create_and_reorder_safely():
    """Verify inserting, shifting, and deleting maintain 1..N order without duplicate collisions."""
    conn = db.get_connection()
    try:
        # Create 3 checkpoints sequentially
        cp1 = db.create_checkpoint(conn, "Point 1", 22.690, 75.860, 30.0, "Clue 1", "Hint 1")
        cp2 = db.create_checkpoint(conn, "Point 2", 22.691, 75.861, 30.0, "Clue 2", "Hint 2")
        cp3 = db.create_checkpoint(conn, "Point 3", 22.692, 75.862, 30.0, "Clue 3", "Hint 3")

        cps = db.get_checkpoints(conn)
        assert [c["position"] for c in cps] == [1, 2, 3]

        # Insert new checkpoint at position 2 (inserting between Point 1 and Point 2)
        cp_mid = db.create_checkpoint(
            conn, "Point 1.5", 22.6905, 75.8605, 30.0, "Clue 1.5", "Hint 1.5", position=2
        )
        assert cp_mid["position"] == 2

        cps = db.get_checkpoints(conn)
        assert len(cps) == 4
        # Verify subsequent checkpoints shifted up safely
        assert [c["name"] for c in cps] == ["Point 1", "Point 1.5", "Point 2", "Point 3"]
        assert [c["position"] for c in cps] == [1, 2, 3, 4]

        # Move Point 3 (position 4) up to position 1
        updated_cp3 = db.update_checkpoint(
            conn,
            checkpoint_id=cp3["id"],
            name="Point 3",
            lat=22.692,
            lng=75.862,
            radius=30.0,
            clue="Clue 3",
            hint="Hint 3",
            position=1,
        )
        assert updated_cp3["position"] == 1

        cps = db.get_checkpoints(conn)
        assert [c["name"] for c in cps] == ["Point 3", "Point 1", "Point 1.5", "Point 2"]
        assert [c["position"] for c in cps] == [1, 2, 3, 4]

        # Delete Point 1.5 (currently position 3) and ensure remaining positions close the gap
        mid_id = cp_mid["id"]
        assert db.delete_checkpoint(conn, mid_id) is True

        cps = db.get_checkpoints(conn)
        assert len(cps) == 3
        assert [c["name"] for c in cps] == ["Point 3", "Point 1", "Point 2"]
        assert [c["position"] for c in cps] == [1, 2, 3]
    finally:
        conn.close()


# --- 3. Route Security & require_admin Tests ---


def test_checkpoint_endpoints_require_admin(anon_client):
    """Unauthenticated requests without admin cookies are rejected with 401."""
    # List
    res = anon_client.get("/api/gods/checkpoints")
    assert res.status_code == 401

    # Create
    res = anon_client.post(
        "/api/gods/checkpoints",
        json={
            "name": "Unauthorized Point",
            "lat": 22.6928,
            "lng": 75.8676,
            "radius": 30.0,
            "clue": "Sample clue",
            "hint": "Sample hint",
        },
    )
    assert res.status_code == 401

    # Update
    res = anon_client.put(
        "/api/gods/checkpoints/1",
        json={
            "name": "Unauthorized Point",
            "lat": 22.6928,
            "lng": 75.8676,
            "radius": 30.0,
            "clue": "Sample clue",
            "hint": "Sample hint",
        },
    )
    assert res.status_code == 401

    # Delete
    res = anon_client.delete("/api/gods/checkpoints/1")
    assert res.status_code == 401


# --- 4. Input Validation Tests ---


def test_create_checkpoint_validation_rules(admin_client):
    """Pydantic rejects out-of-bounds coords, out-of-range radius, and text over limits."""
    valid_lat = (config.CAMPUS_BOUNDS_SW_LAT + config.CAMPUS_BOUNDS_NE_LAT) / 2.0
    valid_lng = (config.CAMPUS_BOUNDS_SW_LNG + config.CAMPUS_BOUNDS_NE_LNG) / 2.0

    valid_payload = {
        "name": "Takshashila Main Entrance",
        "lat": valid_lat,
        "lng": valid_lng,
        "radius": 30.0,
        "clue": "Near the entrance arch",
        "hint": "Look for the large sign board",
        "story": "Built during initial expansion",
    }

    # 1. Coordinates outside campus bounds
    out_of_bounds = dict(valid_payload, lat=config.CAMPUS_BOUNDS_NE_LAT + 0.1)
    res = admin_client.post("/api/gods/checkpoints", json=out_of_bounds)
    assert res.status_code == 422

    # 2. Radius too small (< 25 m)
    too_small_radius = dict(valid_payload, radius=24.9)
    res = admin_client.post("/api/gods/checkpoints", json=too_small_radius)
    assert res.status_code == 422

    # 3. Radius too large (> 100 m)
    too_large_radius = dict(valid_payload, radius=100.1)
    res = admin_client.post("/api/gods/checkpoints", json=too_large_radius)
    assert res.status_code == 422

    # 4. Name too long (> 60 chars)
    long_name = dict(valid_payload, name="A" * 61)
    res = admin_client.post("/api/gods/checkpoints", json=long_name)
    assert res.status_code == 422

    # 5. Empty name
    empty_name = dict(valid_payload, name="")
    res = admin_client.post("/api/gods/checkpoints", json=empty_name)
    assert res.status_code == 422

    # 6. Clue too long (> 300 chars)
    long_clue = dict(valid_payload, clue="C" * 301)
    res = admin_client.post("/api/gods/checkpoints", json=long_clue)
    assert res.status_code == 422

    # 7. Hint too long (> 300 chars)
    long_hint = dict(valid_payload, hint="H" * 301)
    res = admin_client.post("/api/gods/checkpoints", json=long_hint)
    assert res.status_code == 422

    # 8. Story too long (> 300 chars)
    long_story = dict(valid_payload, story="S" * 301)
    res = admin_client.post("/api/gods/checkpoints", json=long_story)
    assert res.status_code == 422


# --- 5. Full Admin API CRUD Lifecycle ---


def test_checkpoint_api_lifecycle(admin_client):
    """Admin can list, create, edit, reorder, and delete checkpoints via API."""
    # Start with empty list
    res = admin_client.get("/api/gods/checkpoints")
    assert res.status_code == 200
    assert res.json() == []

    valid_lat = (config.CAMPUS_BOUNDS_SW_LAT + config.CAMPUS_BOUNDS_NE_LAT) / 2.0
    valid_lng = (config.CAMPUS_BOUNDS_SW_LNG + config.CAMPUS_BOUNDS_NE_LNG) / 2.0

    # Create checkpoint 1
    cp1_data = {
        "name": "Central Library",
        "lat": valid_lat,
        "lng": valid_lng,
        "radius": 35.0,
        "clue": "Where knowledge resides",
        "hint": "Books and silence",
        "story": "Established in 1964",
    }
    res = admin_client.post("/api/gods/checkpoints", json=cp1_data)
    assert res.status_code == 201
    created_cp1 = res.json()
    assert created_cp1["id"] > 0
    assert created_cp1["name"] == "Central Library"
    assert created_cp1["position"] == 1

    # Create checkpoint 2
    cp2_data = {
        "name": "Auditorium",
        "lat": valid_lat,
        "lng": valid_lng,
        "radius": 40.0,
        "clue": "Echoes of grand ceremonies",
        "hint": "Red brick building near the gate",
    }
    res = admin_client.post("/api/gods/checkpoints", json=cp2_data)
    assert res.status_code == 201
    created_cp2 = res.json()
    assert created_cp2["position"] == 2

    # Verify list returns 2 checkpoints
    res = admin_client.get("/api/gods/checkpoints")
    assert res.status_code == 200
    cps = res.json()
    assert len(cps) == 2

    # Update checkpoint 1
    update_data = {
        "name": "Central Library East Wing",
        "lat": valid_lat,
        "lng": valid_lng,
        "radius": 30.0,
        "clue": "Where journals reside",
        "hint": "East side entrance",
        "story": "Renovated recently",
        "position": 1,
    }
    res = admin_client.put(f"/api/gods/checkpoints/{created_cp1['id']}", json=update_data)
    assert res.status_code == 200
    updated = res.json()
    assert updated["name"] == "Central Library East Wing"
    assert updated["radius"] == 30.0

    # Delete checkpoint 1
    res = admin_client.delete(f"/api/gods/checkpoints/{created_cp1['id']}")
    assert res.status_code == 200
    assert res.json()["deleted_id"] == created_cp1["id"]

    # Verify remaining checkpoint has position 1 (compacted)
    res = admin_client.get("/api/gods/checkpoints")
    assert res.status_code == 200
    remaining = res.json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == created_cp2["id"]
    assert remaining[0]["position"] == 1

    # Attempting to delete or update non-existent checkpoint returns 404
    res = admin_client.delete("/api/gods/checkpoints/9999")
    assert res.status_code == 404

    res = admin_client.put("/api/gods/checkpoints/9999", json=update_data)
    assert res.status_code == 404
