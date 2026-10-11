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
EVENT_GAME_RESET = "game_reset"
EVENT_TEAMS_PROGRESS_RESET = "teams_progress_reset"
EVENT_TEAM_RESET = "team_reset"
EVENT_ADMIN_LOGIN_SUCCESS = "admin_login_success"
EVENT_ADMIN_LOGIN_FAILURE = "admin_login_failure"
EVENT_SPEED_REJECTED = "speed_rejected"
EVENT_DEVICE_RELEASED = "device_released"
EVENT_TIME_ADJUSTED = "time_adjusted"
EVENT_TEAM_DELETED = "team_deleted"
EVENT_CHECKPOINT_SKIPPED = "checkpoint_skipped"
EVENT_CHECKPOINT_FORCE_CLEARED = "checkpoint_force_cleared"
EVENT_TEST_PING_REFUSED = "test_ping_refused"
EVENT_TEST_MODE_TOGGLED = "test_mode_toggled"
EVENT_EVENT_WIPED = "event_wiped"

EVENT_TYPES = frozenset({
    EVENT_TEAM_REGISTERED,
    EVENT_DEVICE_BOUND,
    EVENT_CHECKPOINT_UNLOCKED,
    EVENT_HINT_USED,
    EVENT_RADAR_USED,
    EVENT_GAME_STARTED,
    EVENT_GAME_ENDED,
    EVENT_GAME_RESET,
    EVENT_TEAMS_PROGRESS_RESET,
    EVENT_TEAM_RESET,
    EVENT_ADMIN_LOGIN_SUCCESS,
    EVENT_ADMIN_LOGIN_FAILURE,
    EVENT_SPEED_REJECTED,
    EVENT_DEVICE_RELEASED,
    EVENT_TIME_ADJUSTED,
    EVENT_TEAM_DELETED,
    EVENT_CHECKPOINT_SKIPPED,
    EVENT_CHECKPOINT_FORCE_CLEARED,
    EVENT_TEST_PING_REFUSED,
    EVENT_TEST_MODE_TOGGLED,
    EVENT_EVENT_WIPED,
})


def is_skip_allowed(elapsed_on_checkpoint_s: float, wait_limit_s: int = 600) -> bool:
    """Return True if team has spent at least wait_limit_s on current checkpoint."""
    return elapsed_on_checkpoint_s >= float(wait_limit_s)


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


def award_for(
    cleared_count: int,
    time_to_find_s: float | None = None,
    time_limit_s: float = 150.0,
) -> str | None:
    """Determine power-up awarded for cleared checkpoint count and search time.

    Rules:
    1. Alternate checkpoints only: only odd clears (1st, 3rd, 5th, ...) can earn a power-up.
       Even clears (2nd, 4th, 6th, ...) always return None.
    2. Time challenge: checkpoint must be found within the time limit (<= 2m 30s / 150s).
       If time_to_find_s exceeds time_limit_s, returns None.
    3. Eligible clears alternate between "radar" (1st, 5th, ...) and "boost" (3rd, 7th, ...).
    """
    if cleared_count <= 0:
        return None

    # Alternate checkpoints only: 1, 3, 5, ...
    if cleared_count % 2 == 0:
        return None

    # Time-to-find check: 2 minutes 30 seconds limit
    if time_to_find_s is not None and time_to_find_s > time_limit_s:
        return None

    # Alternate between Radar and Boost across eligible stops:
    # 1st clear -> index 0 (radar)
    # 3rd clear -> index 1 (boost)
    # 5th clear -> index 2 (radar)
    eligible_index = (cleared_count - 1) // 2
    return "radar" if (eligible_index % 2 == 0) else "boost"


determine_awarded_powerup = award_for


def compute_effective_radius(
    base_radius_m: float,
    boost_active: bool,
    boost_percent: float = 0.30,
) -> float:
    """Return effective geofence radius in metres.

    If Radius boost is currently active, increases the base radius
    by boost_percent (e.g. 0.30 = +30%).
    """
    if boost_active:
        return base_radius_m * (1.0 + boost_percent)
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


def speed_mps(
    prev_lat: float,
    prev_lng: float,
    prev_ts: float,
    lat: float,
    lng: float,
    ts: float,
) -> float:
    """Calculate speed in metres per second between two GPS fixes.

    Uses great-circle Haversine distance and server receive timestamps.
    Enforces a minimum time gap of 1.0 second to avoid division by zero or
    unrealistic speed spikes on rapid consecutive pings.
    """
    dist_m = haversine_m(prev_lat, prev_lng, lat, lng)
    dt_s = max(1.0, ts - prev_ts)
    return dist_m / dt_s



