"""Unit tests for pure domain geofencing and game rules in game.py."""

import pytest
from game import (
    accuracy_ok,
    haversine_m,
    is_inside,
    next_streak,
    should_unlock,
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
