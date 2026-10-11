"""Global pytest configuration and fixtures for Campus Quest.

Ensures rate limit buckets are cleared before and after every test
so test runs never interfere with each other.
"""

import pytest
import ratelimit


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset all in-memory rate limiter buckets for each test."""
    ratelimit.clear_rate_limits()
    yield
    ratelimit.clear_rate_limits()
