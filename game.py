"""Pure domain game logic for Campus Quest.

Contains zero HTTP, SQL, or database dependencies. All functions are
pure, deterministic, and safe to test in isolation.
"""

from typing import Tuple


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

