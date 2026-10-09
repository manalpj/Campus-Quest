"""Tests for Task 2: Leaflet campus map and static assets."""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    """Create a FastAPI test client instance."""
    return TestClient(app)


def test_index_contains_leaflet_and_map_elements(client):
    """Verify index.html includes Leaflet stylesheet, Leaflet JS, app.js, and map controls."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Leaflet 1.9.4 assets
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" in html
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" in html

    # Client app script
    assert 'src="/app.js"' in html

    # UI controls
    assert 'id="map"' in html
    assert 'id="gps-status"' in html
    assert 'id="btn-nav"' in html
    assert 'id="btn-leaderboard"' in html
    assert 'id="btn-powerup"' in html

    # Accessibility attributes
    assert 'role="region"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html


def test_app_js_is_served(client):
    """Verify /app.js is served by static files with 200 OK and contains geolocation watch logic."""
    response = client.get("/app.js")
    assert response.status_code == 200
    js = response.text

    # Fetches config dynamically
    assert "fetch('/api/config')" in js or 'fetch("/api/config")' in js

    # Geolocation configuration
    assert "enableHighAccuracy: true" in js
    assert "maximumAge: 0" in js
    assert "timeout: 15000" in js

    # Uses config parameters rather than hard-coding
    assert "cfg.tile_url" in js
    assert "cfg.tile_attribution" in js
    assert "campusBounds" in js
