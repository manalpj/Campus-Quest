"""In-memory sliding-window rate limiter for Campus Quest.

Tracks request timestamps per client IP within a sliding window.
Purges expired timestamps on access to bound memory usage.
"""

import time
from collections import defaultdict
from typing import Dict, List
from fastapi import Request

import config

# In-memory storage: IP/key -> list of float unix timestamps
_buckets: Dict[str, List[float]] = defaultdict(list)


def get_client_ip(request: Request) -> str:
    """Extract client IP address, handling reverse proxy headers when configured.

    When FORWARDED_ALLOW_IPS is configured (e.g. on Railway), parses X-Forwarded-For.
    In a reverse-proxy chain where proxies append hops, the last entry is the immediate
    client connecting to the proxy, preventing attackers from injecting arbitrary spoofed IPs
    in the first position.
    """
    if config.FORWARDED_ALLOW_IPS:
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            parts = [p.strip() for p in x_forwarded_for.split(",") if p.strip()]
            if parts:
                return parts[-1]

    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"


def is_rate_limited(key: str, max_attempts: int, window_s: float = 60.0) -> bool:
    """Evaluate sliding-window rate limit for a key.

    Returns True if key has reached or exceeded max_attempts in window_s seconds.
    If allowed, records the current timestamp and returns False.
    """
    now = time.time()
    cutoff = now - window_s

    # Retain only timestamps within the active sliding window
    timestamps = [ts for ts in _buckets[key] if ts > cutoff]

    if len(timestamps) >= max_attempts:
        _buckets[key] = timestamps
        return True

    timestamps.append(now)
    _buckets[key] = timestamps
    return False


def clear_rate_limits() -> None:
    """Reset rate limiter state (used primarily in test fixtures)."""
    _buckets.clear()
