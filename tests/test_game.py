"""Unit tests for pure domain geofencing and game rules in game.py."""

import pytest
from game import (
    accuracy_ok,
    adjusted_time,
    haversine_m,
    is_inside,
    next_streak,
    rank_teams,
    should_unlock,
    determine_awarded_powerup,
    compute_effective_radius,
    is_powerup_active,
    format_radar_label,
    speed_mps,
)


def test_haversine_equator_one_degree_longitude():
    """(0, 0) to (0, 1) along equator is about 111,194.9 m."""
    dist = haversine_m(0.0, 0.0, 0.0, 1.0)
    assert dist == pytest.approx(111194.9, abs=0.5)


def test_haversine_same_point():
    """The same point to itself is exactly 0.0 m."""
    dist = haversine_m(22.7000, 75.8000, 22.7000, 75.8000)
    assert dist == pytest.approx(0.0, abs=1e-6)


def test_haversine_latitude_delta_davv():
    """(22.7000, 75.8000) to (22.7003, 75.8000) is about 33.4 m."""
    dist = haversine_m(22.7000, 75.8000, 22.7003, 75.8000)
    assert dist == pytest.approx(33.4, abs=0.5)


def test_haversine_longitude_delta_davv():
    """(22.7000, 75.8000) to (22.7000, 75.8003) is about 30.8 m.

    A degree of longitude is shorter than a degree of latitude at 22.7 deg N
    because meridians converge toward the poles.
    """
    dist = haversine_m(22.7000, 75.8000, 22.7000, 75.8003)
    assert dist == pytest.approx(30.8, abs=0.5)


def test_is_inside_boundary():
    """A point exactly on the radius counts as inside; 1 metre beyond does not."""
    radius = 35.0
    # Exactly on radius
    assert is_inside(35.0, radius) is True
    # Inside radius
    assert is_inside(34.9, radius) is True
    # Exactly one metre beyond
    assert is_inside(36.0, radius) is False


def test_accuracy_ok():
    """Accuracy is OK when not worse than the limit (and non-negative)."""
    limit = 30.0
    # Better than limit
    assert accuracy_ok(15.0, limit) is True
    # Exactly at limit
    assert accuracy_ok(30.0, limit) is True
    # Worse than limit
    assert accuracy_ok(30.1, limit) is False
    assert accuracy_ok(50.0, limit) is False
    # Negative accuracy is invalid
    assert accuracy_ok(-1.0, limit) is False


def test_streak_and_unlock_flow():
    """Streak tracking and unlock rules.

    Sequence: 'in, in' unlocks at 2.
    Sequence: 'in, out, in' resets and does not unlock at 2.
    """
    # Sequence 1: in, in -> unlocks at 2
    streak = 0
    streak = next_streak(streak, inside=True)
    assert streak == 1
    assert should_unlock(streak, required=2) is False

    streak = next_streak(streak, inside=True)
    assert streak == 2
    assert should_unlock(streak, required=2) is True

    # Sequence 2: in, out, in -> resets, does not unlock
    streak = 0
    streak = next_streak(streak, inside=True)
    assert streak == 1
    assert should_unlock(streak, required=2) is False

    streak = next_streak(streak, inside=False)
    assert streak == 0
    assert should_unlock(streak, required=2) is False

    streak = next_streak(streak, inside=True)
    assert streak == 1
    assert should_unlock(streak, required=2) is False


def test_adjusted_time_calculation():
    """Adjusted time adds penalties, subtracts bonuses, and never falls below 0."""
    # Basic addition/subtraction
    assert adjusted_time(elapsed_at_last_unlock_s=120, penalty_s=60, bonus_s=20) == 160
    # Defaults
    assert adjusted_time(elapsed_at_last_unlock_s=300) == 300
    # Clamping negative time to 0
    assert adjusted_time(elapsed_at_last_unlock_s=30, penalty_s=0, bonus_s=120) == 0


def test_rank_teams_more_checkpoints_beats_faster_time():
    """A team that cleared more checkpoints ranks higher even with a much higher time."""
    teams = [
        {"team_id": 1, "name": "Speedy Few", "cleared": 2, "adjusted_time": 60, "last_unlock_ts": 100},
        {"team_id": 2, "name": "Steady Many", "cleared": 4, "adjusted_time": 600, "last_unlock_ts": 500},
    ]
    ranked = rank_teams(teams)
    assert ranked[0]["name"] == "Steady Many"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["name"] == "Speedy Few"
    assert ranked[1]["rank"] == 2


def test_rank_teams_tie_on_count_broken_by_adjusted_time():
    """When checkpoint counts tie, lower adjusted time ranks higher."""
    teams = [
        {"team_id": 1, "name": "Team High Penalty", "cleared": 3, "adjusted_time": 400, "last_unlock_ts": 300},
        {"team_id": 2, "name": "Team Clean Run", "cleared": 3, "adjusted_time": 250, "last_unlock_ts": 320},
    ]
    ranked = rank_teams(teams)
    assert ranked[0]["name"] == "Team Clean Run"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["name"] == "Team High Penalty"
    assert ranked[1]["rank"] == 2


def test_rank_teams_tie_on_count_and_time_broken_by_earlier_unlock():
    """When both count and adjusted time tie, the earlier last unlock wins."""
    teams = [
        {"team_id": 1, "name": "Late Finisher", "cleared": 3, "adjusted_time": 300, "last_unlock_ts": 1200.0},
        {"team_id": 2, "name": "Early Finisher", "cleared": 3, "adjusted_time": 300, "last_unlock_ts": 900.0},
    ]
    ranked = rank_teams(teams)
    assert ranked[0]["name"] == "Early Finisher"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["name"] == "Late Finisher"
    assert ranked[1]["rank"] == 2


def test_rank_teams_zero_cleared_at_bottom():
    """Teams with 0 checkpoints cleared always appear below teams with >=1 clear."""
    teams = [
        {"team_id": 1, "name": "Zero Hero", "cleared": 0, "adjusted_time": 0, "last_unlock_ts": None},
        {"team_id": 2, "name": "Slow One", "cleared": 1, "adjusted_time": 9999, "last_unlock_ts": 5000.0},
        {"team_id": 3, "name": "Zero Two", "cleared": 0, "adjusted_time": 0, "last_unlock_ts": None},
    ]
    ranked = rank_teams(teams)
    assert ranked[0]["name"] == "Slow One"
    assert ranked[0]["rank"] == 1
    # Both zero-cleared teams are at the bottom
    zero_names = {ranked[1]["name"], ranked[2]["name"]}
    assert zero_names == {"Zero Hero", "Zero Two"}
    assert ranked[1]["rank"] == 2
    assert ranked[2]["rank"] == 3


def test_determine_awarded_powerup():
    """Alternates Radar (odd clears) and Boost (even clears)."""
    assert determine_awarded_powerup(1) == "radar"
    assert determine_awarded_powerup(2) == "boost"
    assert determine_awarded_powerup(3) == "radar"
    assert determine_awarded_powerup(4) == "boost"
    assert determine_awarded_powerup(0) is None
    assert determine_awarded_powerup(-1) is None


def test_compute_effective_radius():
    """Expands base radius by percentage only when boost is active."""
    assert compute_effective_radius(30.0, boost_active=False) == 30.0
    assert compute_effective_radius(30.0, boost_active=True, boost_percent=0.30) == 39.0
    assert compute_effective_radius(50.0, boost_active=True, boost_percent=0.30) == 65.0
    assert compute_effective_radius(25.0, boost_active=True, boost_percent=0.20) == 30.0


def test_is_powerup_active():
    """Powerup is active only when until_ts is greater than now."""
    assert is_powerup_active(150.0, now=100.0) is True
    assert is_powerup_active(100.0, now=100.0) is False
    assert is_powerup_active(90.0, now=100.0) is False
    assert is_powerup_active(None, now=100.0) is False


def test_format_radar_label():
    """Formats radar distance with special text when close."""
    assert format_radar_label(18.5) == "You're very close!"
    assert format_radar_label(30.0) == "You're very close!"
    assert format_radar_label(30.5) == "31 m"
    assert format_radar_label(142.2) == "142 m"


def test_speed_mps_rejected_200m_in_2s():
    """200 m in 2 seconds gives ~100 m/s which exceeds MAX_SPEED_MPS (12)."""
    # 22.700000 to 22.701806 is ~200.7 metres
    speed = speed_mps(22.700000, 75.800000, 100.0, 22.701806, 75.800000, 102.0)
    assert speed == pytest.approx(100.3, rel=1e-2)
    assert speed > 12.0


def test_speed_mps_accepted_20m_in_10s():
    """20 m in 10 seconds gives ~2 m/s which is well within walking/cycling limits."""
    # 22.700000 to 22.700180 is ~20.0 metres
    speed = speed_mps(22.700000, 75.800000, 100.0, 22.700180, 75.800000, 110.0)
    assert speed == pytest.approx(2.0, rel=1e-2)
    assert speed <= 12.0


def test_speed_mps_accepted_600m_in_5_minutes():
    """600 m across 300 s (5 mins) gives ~2 m/s (legitimate jump after signal loss)."""
    # 22.700000 to 22.705417 is ~601.9 metres
    speed = speed_mps(22.700000, 75.800000, 100.0, 22.705417, 75.800000, 400.0)
    assert speed == pytest.approx(2.0, rel=1e-2)
    assert speed <= 12.0


def test_speed_mps_minimum_time_gap():
    """Sub-second time gap is clamped to 1.0 s minimum divisor to avoid division blow-up."""
    # 5 metres apart
    # In 0.1 s, without clamp would be 50 m/s; with 1.0 s clamp it is 5 m/s
    speed = speed_mps(22.700000, 75.800000, 100.0, 22.700045, 75.800000, 100.1)
    assert speed == pytest.approx(5.0, rel=1e-1)
    assert speed <= 12.0

    # Same timestamp (0 s gap) also divides by 1.0 rather than raising ZeroDivisionError
    speed_zero_gap = speed_mps(22.700000, 75.800000, 100.0, 22.700045, 75.800000, 100.0)
    assert speed_zero_gap == pytest.approx(5.0, rel=1e-1)


