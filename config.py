"""Configuration loader for Campus Quest.

Reads settings from environment variables (and .env for local runs).
Converts types, provides safe defaults, validates production secrets,
and exposes safe public settings for clients.
"""

import os
from typing import Any, Dict
from dotenv import load_dotenv

# Load local .env file if present
load_dotenv()


def _get_str(key: str, default: str) -> str:
    """Read a string environment variable with a default fallback."""
    val = os.getenv(key)
    if val is None:
        return default
    val = val.strip()
    return val if val != "" else default


def _get_int(key: str, default: int) -> int:
    """Read an integer environment variable with a default fallback."""
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer for configuration key {key}: {val!r}") from exc


def _get_float(key: str, default: float) -> float:
    """Read a float environment variable with a default fallback."""
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid float for configuration key {key}: {val!r}") from exc


def _get_bool(key: str, default: bool) -> bool:
    """Parse a boolean environment variable (truthy: 1, true, yes, on)."""
    val = os.getenv(key)
    if val is None or val == "":
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# 1. Environment & Server Configuration
ENV: str = _get_str("ENV", "development").lower()
PORT: int = _get_int("PORT", 8000)
DB_PATH: str = _get_str("DB_PATH", "data/quest.db")
FORWARDED_ALLOW_IPS: str = _get_str("FORWARDED_ALLOW_IPS", "*")
MAX_BODY_BYTES: int = _get_int("MAX_BODY_BYTES", 65536)

# 2. Security & Admin Authentication
ADMIN_USER: str = _get_str("ADMIN_USER", "admin")
ADMIN_PASS: str = _get_str("ADMIN_PASS", "change-me-to-a-secure-passphrase")
SECRET_KEY: str = _get_str("SECRET_KEY", "change-me-to-a-random-32-byte-hex-token")
LOGIN_ATTEMPTS_PER_MIN: int = _get_int("LOGIN_ATTEMPTS_PER_MIN", 5)
JOIN_ATTEMPTS_PER_MIN: int = _get_int("JOIN_ATTEMPTS_PER_MIN", 10)

# 3. Campus Coordinates & Bounds
CAMPUS_NAME: str = _get_str("CAMPUS_NAME", "DAVV IET Campus")
CAMPUS_CENTER_LAT: float = _get_float("CAMPUS_CENTER_LAT", 22.6928)

CAMPUS_CENTER_LNG: float = _get_float("CAMPUS_CENTER_LNG", 75.8676)
CAMPUS_BOUNDS_SW_LAT: float = _get_float("CAMPUS_BOUNDS_SW_LAT", 22.6850)
CAMPUS_BOUNDS_SW_LNG: float = _get_float("CAMPUS_BOUNDS_SW_LNG", 75.8580)
CAMPUS_BOUNDS_NE_LAT: float = _get_float("CAMPUS_BOUNDS_NE_LAT", 22.7010)
CAMPUS_BOUNDS_NE_LNG: float = _get_float("CAMPUS_BOUNDS_NE_LNG", 75.8780)
CAMPUS_START_ZOOM: int = _get_int("CAMPUS_START_ZOOM", 17)
CAMPUS_MIN_ZOOM: int = _get_int("CAMPUS_MIN_ZOOM", 15)
CAMPUS_MAX_ZOOM: int = _get_int("CAMPUS_MAX_ZOOM", 19)

# 4. Map Tile Settings
TILE_URL: str = _get_str("TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
TILE_ATTRIBUTION: str = _get_str(
    "TILE_ATTRIBUTION",
    '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
)

# 5. Client Polling & Ping Intervals (Milliseconds)
PING_INTERVAL_MS: int = _get_int("PING_INTERVAL_MS", 4000)
POLL_INTERVAL_MS: int = _get_int("POLL_INTERVAL_MS", 4000)

# 6. Core Game Rules & Geofence Parameters
MIN_CHECKPOINTS: int = _get_int("MIN_CHECKPOINTS", 5)
MIN_MEMBERS: int = _get_int("MIN_MEMBERS", 2)
COUNTDOWN_S: int = _get_int("COUNTDOWN_S", 10)
ACCURACY_LIMIT_M: float = _get_float("ACCURACY_LIMIT_M", 30.0)
STREAK_REQUIRED: int = _get_int("STREAK_REQUIRED", 2)
MAX_SPEED_MPS: float = _get_float("MAX_SPEED_MPS", 12.0)

# 7. Power-up & Recovery Durations & Penalties (Seconds)
HINT_PENALTY_S: int = _get_int("HINT_PENALTY_S", 180)
RADAR_DURATION_S: int = _get_int("RADAR_DURATION_S", 60)
BOOST_DURATION_S: int = _get_int("BOOST_DURATION_S", 120)
BOOST_EXTRA_RADIUS_M: float = _get_float("BOOST_EXTRA_RADIUS_M", 20.0)
SKIP_WAIT_S: int = _get_int("SKIP_WAIT_S", 600)
SKIP_PENALTY_S: int = _get_int("SKIP_PENALTY_S", 600)

# 8. Organizer Contact & Testing Controls
ORGANIZER_NAME: str = _get_str("ORGANIZER_NAME", "GDGoC DAVV Organizing Team")
ORGANIZER_CONTACT: str = _get_str("ORGANIZER_CONTACT", "gdgoc@davv.ac.in")
ALLOW_TEST_MODE: bool = _get_bool("ALLOW_TEST_MODE", False)


def validate_production_secrets() -> None:
    """Ensure sensitive credentials are secure in production.

    Raises RuntimeError with an actionable message if any secret is missing
    or still holds default placeholder text containing 'change-me'.
    """
    if ENV != "production":
        return

    problems = []
    if not ADMIN_USER or "change-me" in ADMIN_USER.lower():
        problems.append("ADMIN_USER must be set to a non-default username.")
    if not ADMIN_PASS or "change-me" in ADMIN_PASS.lower():
        problems.append("ADMIN_PASS must be replaced with a secure passphrase.")
    if not SECRET_KEY or "change-me" in SECRET_KEY.lower():
        problems.append(
            "SECRET_KEY must be set to a random 32-byte hex string (generate with: python -c 'import secrets; print(secrets.token_hex(32))')."
        )

    if problems:
        error_msg = (
            "FATAL: Insecure configuration detected in production environment:\n"
            + "\n".join(f" - {p}" for p in problems)
        )
        raise RuntimeError(error_msg)


# Validate secrets on import to catch misconfiguration immediately
validate_production_secrets()


def get_public_config() -> Dict[str, Any]:
    """Return only safe, public settings needed by the client.

    Never includes ADMIN_USER, ADMIN_PASS, SECRET_KEY, DB_PATH, or internals.
    """
    return {
        "campus_name": CAMPUS_NAME,
        "center": {
            "lat": CAMPUS_CENTER_LAT,
            "lng": CAMPUS_CENTER_LNG,
        },
        "bounds": {
            "sw": {
                "lat": CAMPUS_BOUNDS_SW_LAT,
                "lng": CAMPUS_BOUNDS_SW_LNG,
            },
            "ne": {
                "lat": CAMPUS_BOUNDS_NE_LAT,
                "lng": CAMPUS_BOUNDS_NE_LNG,
            },
        },
        "zoom": {
            "start": CAMPUS_START_ZOOM,
            "min": CAMPUS_MIN_ZOOM,
            "max": CAMPUS_MAX_ZOOM,
        },
        "tile_url": TILE_URL,
        "tile_attribution": TILE_ATTRIBUTION,
        "ping_interval_ms": PING_INTERVAL_MS,
        "poll_interval_ms": POLL_INTERVAL_MS,
        "min_checkpoints": MIN_CHECKPOINTS,
    }
