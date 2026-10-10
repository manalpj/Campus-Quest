"""Pure domain game logic for Campus Quest.

Contains zero HTTP, SQL, or database dependencies. All functions are
pure, deterministic, and safe to test in isolation.
"""

import math
from typing import Tuple

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance in metres between two GPS coordinates.

    Uses the Haversine formula with a spherical Earth radius of 6,371,000 metres.
    Written by hand using Python's standard math module.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clamp 'a' to [0.0, 1.0] to protect against slight floating point inaccuracies
    # that could otherwise trigger math domain errors in sqrt or asin.
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_M * c


def is_inside(distance_m: float, radius_m: float) -> bool:
    """Return True if distance is within or exactly on the geofence radius."""
    return distance_m <= radius_m


def accuracy_ok(accuracy_m: float, limit_m: float) -> bool:
    """Return True if GPS accuracy is valid and not worse than the limit in metres."""
    return 0.0 <= accuracy_m <= limit_m


def next_streak(current_streak: int, inside: bool) -> int:
    """Return updated consecutive inside fix count.

    Increments current streak by 1 if inside, otherwise resets to 0.
    """
    return current_streak + 1 if inside else 0


def should_unlock(streak: int, required: int = 2) -> bool:
    """Return True if the consecutive inside streak satisfies the unlock requirement."""
    return streak >= required



def is_within_campus_bounds(
    lat: float,
    lng: float,
    sw_lat: float,
    sw_lng: float,
    ne_lat: float,
    ne_lng: float,
    margin: float = 0.0005,
) -> bool:
    """Return True if coordinates fall within campus bounding box.

    Includes a slight tolerance margin (~50m) to accommodate campus building
    perimeters, entryways, and normal GPS boundary variations.
    """
    return (sw_lat - margin <= lat <= ne_lat + margin) and (sw_lng - margin <= lng <= ne_lng + margin)


def compute_target_position(
    requested_position: int | None,
    total_existing: int,
) -> int:
    """Determine the valid 1-indexed target sequence position.

    If requested_position is None or exceeds total_existing + 1,
    the item is appended to the end of the sequence (total_existing + 1).
    Position is clamped to minimum 1.
    """
    if requested_position is None or requested_position > total_existing + 1:
        return total_existing + 1
    if requested_position < 1:
        return 1
    return requested_position


def generate_team_code(name: str) -> str:
    """Generate a readable team code like PHX-4821.

    Uses first 3 alphabetical letters of the team name (uppercase),
    padded with random uppercase letters if fewer than 3 letters exist,
    followed by a hyphen and 4 cryptographically secure random digits.
    """
    import secrets
    import string

    clean_letters = [c.upper() for c in name if c.isalpha()]
    while len(clean_letters) < 3:
        clean_letters.append(secrets.choice(string.ascii_uppercase))

    prefix = "".join(clean_letters[:3])
    digits = f"{secrets.randbelow(10000):04d}"
    return f"{prefix}-{digits}"


def normalize_team_code(code: str) -> str:
    """Normalize input team code by trimming whitespace and capitalizing."""
    return code.strip().upper()

