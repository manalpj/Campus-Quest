"""Tests for project scaffold, configuration, and health endpoints."""

import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from main import app
import config


@pytest.fixture
def client():
    """Create a FastAPI test client instance."""
    return TestClient(app)


def test_healthz_endpoint(client):
    """GET /healthz returns 200 and {'status': 'ok'}."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_config_returns_public_settings_only(client):
    """GET /api/config returns public map & interval settings and never leaks secrets."""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()

    # Required public keys
    assert "campus_name" in data
    assert "center" in data
    assert "lat" in data["center"] and "lng" in data["center"]
    assert "bounds" in data
    assert "sw" in data["bounds"] and "ne" in data["bounds"]
    assert "zoom" in data
    assert "tile_url" in data
    assert "tile_attribution" in data
    assert "ping_interval_ms" in data
    assert "poll_interval_ms" in data

    # Verify sensitive settings are NEVER exposed
    forbidden_keys = [
        "ADMIN_USER",
        "ADMIN_PASS",
        "SECRET_KEY",
        "DB_PATH",
        "admin_user",
        "admin_pass",
        "secret_key",
        "db_path",
        "FORWARDED_ALLOW_IPS",
    ]
    for key in forbidden_keys:
        assert key not in data, f"Sensitive key {key} leaked in /api/config"


def test_static_index_page_is_served(client):
    """GET / serves the static index.html page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>Campus Quest</title>" in response.text
    assert "Welcome to Campus Quest" in response.text


def test_static_path_traversal_is_blocked(client):
    """Path traversal attempts via static route must not leak repository files."""
    response = client.get("/../config.py")
    assert response.status_code in {400, 404}

    response = client.get("/%2e%2e/config.py")
    assert response.status_code in {400, 404}


def test_referrer_policy_compatible_with_osm(client):
    """Response headers must not set Referrer-Policy to no-referrer."""
    response = client.get("/healthz")
    referrer_policy = response.headers.get("referrer-policy", "").lower()
    assert referrer_policy != "no-referrer"


def test_production_secrets_validation_fails_on_defaults(monkeypatch):
    """When ENV=production, default or 'change-me' secrets raise RuntimeError."""
    monkeypatch.setattr(config, "ENV", "production")
    monkeypatch.setattr(config, "ADMIN_USER", "admin")
    monkeypatch.setattr(config, "ADMIN_PASS", "change-me-to-a-secure-passphrase")
    monkeypatch.setattr(config, "SECRET_KEY", "change-me-to-a-random-32-byte-hex-token")

    with pytest.raises(RuntimeError) as exc_info:
        config.validate_production_secrets()

    assert "FATAL: Insecure configuration detected in production" in str(exc_info.value)
    assert "ADMIN_PASS" in str(exc_info.value)
    assert "SECRET_KEY" in str(exc_info.value)


def test_production_secrets_validation_succeeds_on_custom_values(monkeypatch):
    """When ENV=production and secrets are securely set, validation succeeds."""
    monkeypatch.setattr(config, "ENV", "production")
    monkeypatch.setattr(config, "ADMIN_USER", "real_admin")
    monkeypatch.setattr(config, "ADMIN_PASS", "strong_and_unique_passphrase_here")
    monkeypatch.setattr(
        config,
        "SECRET_KEY",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )

    # Should not raise
    config.validate_production_secrets()
