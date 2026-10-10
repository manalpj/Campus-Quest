"""Pure domain game logic for Campus Quest.

Contains zero HTTP, SQL, or database dependencies. All functions are
pure, deterministic, and safe to test in isolation.
"""

import math
from typing import Tuple

EARTH_RADIUS_M = 6_371_000.0

# Event type constants for audit logging
EVENT_TEAM_REGISTERED = "team_registered"
EVENT_DEVICE_BOUND = "device_bound"
EVENT_CHECKPOINT_UNLOCKED = "checkpoint_unlocked"
EVENT_HINT_USED = "hint_used"
EVENT_RADAR_USED = "radar_used"
EVENT_GAME_STARTED = "game_started"
EVENT_GAME_ENDED = "game_ended"
EVENT_ADMIN_LOGIN_SUCCESS = "admin_login_success"
EVENT_ADMIN_LOGIN_FAILURE = "admin_login_failure"

EVENT_TYPES = frozenset({
    EVENT_TEAM_REGISTERED,
    EVENT_DEVICE_BOUND,
    EVENT_CHECKPOINT_UNLOCKED,
    EVENT_HINT_USED,
    EVENT_RADAR_USED,
    EVENT_GAME_STARTED,
    EVENT_GAME_ENDED,
    EVENT_ADMIN_LOGIN_SUCCESS,
    EVENT_ADMIN_LOGIN_FAILURE,
})


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


def adjusted_time(
    elapsed_at_last_unlock_s: int,
    penalty_s: int = 0,
    bonus_s: int = 0,
) -> int:
    """Calculate team adjusted time in seconds.

    Adjusted time = elapsed time at last unlock + penalties - bonuses.
    Clamped to minimum 0.
    """
    return max(0, elapsed_at_last_unlock_s + penalty_s - bonus_s)


def rank_teams(rows: list[dict]) -> list[dict]:
    """Sort teams and assign 1-indexed ranks based on Campus Quest ranking rules.

    Sorting hierarchy:
    1. Checkpoints cleared (descending, most cleared wins)
    2. Adjusted time in seconds (ascending, lowest adjusted time wins)
    3. Last unlock timestamp (ascending, earlier unlock wins)
    4. Stable tie-break (team_id ascending)

    Teams that have not cleared anything yet appear at the bottom.
    Returns a new list of team dictionaries with a 'rank' key added.
    """
    def _sort_key(row: dict):
        cleared = row.get("cleared", 0)
        adj_time = row.get("adjusted_time", 0)
        last_unlock = row.get("last_unlock_ts")
        last_unlock_val = float("inf") if last_unlock is None else float(last_unlock)
        team_id = row.get("team_id", 0)
        return (-cleared, adj_time, last_unlock_val, team_id)

    sorted_rows = sorted(rows, key=_sort_key)
    result = []
    for idx, item in enumerate(sorted_rows, start=1):
        ranked_item = dict(item)
        ranked_item["rank"] = idx
        result.append(ranked_item)
    return result


def award_for(cleared_count: int) -> str | None:
    """Determine power-up awarded for cleared checkpoint count.

    Rule: Teams start with none. Clearing a checkpoint awards exactly one,
    alternating Radar on odd clears (1st, 3rd, ...) and Radius boost on
    even clears (2nd, 4th, ...).
    """
    if cleared_count <= 0:
        return None
    return "radar" if (cleared_count % 2 == 1) else "boost"


determine_awarded_powerup = award_for


def compute_effective_radius(
    base_radius_m: float,
    boost_active: bool,
    boost_extra_m: float = 20.0,
) -> float:
    """Return effective geofence radius in metres.

    If Radius boost is currently active, adds boost_extra_m (default 20m)
    to the base checkpoint radius.
    """
    if boost_active:
        return base_radius_m + boost_extra_m
    return base_radius_m


def is_powerup_active(until_ts: float | None, now: float) -> bool:
    """Return True if power-up duration timestamp is strictly in the future."""
    if until_ts is None:
        return False
    return until_ts > now


def format_radar_label(distance_m: float) -> str:
    """Format distance reading for Radar HUD display.

    Returns 'You're very close!' when distance is within 30 metres,
    otherwise rounded metres string (e.g. '142 m').
    """
    if distance_m <= 30.0:
        return "You're very close!"
    return f"{int(distance_m + 0.5)} m"


