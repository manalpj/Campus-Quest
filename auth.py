"""Authentication and signed session management for Campus Quest.

Handles constant-time credential verification, HMAC-SHA256 signed admin cookies,
and the require_admin dependency protecting administrative routes.
"""

import hashlib
import hmac
import time
from typing import Optional
from fastapi import HTTPException, Request, Response

import config

ADMIN_COOKIE_NAME = "quest_admin"
SESSION_DURATION_S = 8 * 3600  # 8 hours


def verify_admin_credentials(username: str, password: str) -> bool:
    """Verify administrator username and password using constant-time comparison.

    Uses hmac.compare_digest to prevent timing attacks that deduce characters
    based on CPU comparison delays.
    """
    if not isinstance(username, str) or not isinstance(password, str):
        return False

    user_match = hmac.compare_digest(
        username.encode("utf-8"),
        config.ADMIN_USER.encode("utf-8"),
    )
    pass_match = hmac.compare_digest(
        password.encode("utf-8"),
        config.ADMIN_PASS.encode("utf-8"),
    )
    return user_match and pass_match


def create_admin_cookie_value(username: str, expires_at: Optional[int] = None) -> str:
    """Generate signed cookie value containing username, expiry, and HMAC-SHA256 signature."""
    if expires_at is None:
        expires_at = int(time.time()) + SESSION_DURATION_S

    payload = f"{username}:{expires_at}"
    signature = hmac.new(
        config.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return f"{payload}:{signature}"


def verify_admin_cookie(cookie_val: Optional[str]) -> Optional[str]:
    """Validate signed cookie integrity, expiry timestamp, and administrator identity.

    Returns the verified admin username, or None if invalid, tampered, or expired.
    """
    if not cookie_val or not isinstance(cookie_val, str):
        return None

    parts = cookie_val.rsplit(":", 2)
    if len(parts) != 3:
        return None

    username, expires_str, signature = parts

    try:
        expires_at = int(expires_str)
    except ValueError:
        return None

    # Enforce session expiration against server clock
    if expires_at <= int(time.time()):
        return None

    expected_payload = f"{username}:{expires_str}"
    expected_sig = hmac.new(
        config.SECRET_KEY.encode("utf-8"),
        expected_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Validate signature and username in constant time
    sig_valid = hmac.compare_digest(signature, expected_sig)
    user_valid = hmac.compare_digest(username.encode("utf-8"), config.ADMIN_USER.encode("utf-8"))

    if sig_valid and user_valid:
        return username

    return None


def set_admin_cookie(response: Response, username: str) -> None:
    """Attach secure HttpOnly quest_admin cookie to response."""
    cookie_val = create_admin_cookie_value(username)
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=cookie_val,
        max_age=SESSION_DURATION_S,
        httponly=True,
        samesite="strict",
        secure=(config.ENV == "production"),
    )


def clear_admin_cookie(response: Response) -> None:
    """Remove quest_admin cookie on logout."""
    response.delete_cookie(
        key=ADMIN_COOKIE_NAME,
        httponly=True,
        samesite="strict",
        secure=(config.ENV == "production"),
    )


def require_admin(request: Request) -> str:
    """FastAPI dependency: protects administrative endpoints.

    Checks the signed quest_admin cookie on incoming requests.
    Raises 401 Unauthorized if missing, expired, or tampered with.
    """
    cookie_val = request.cookies.get(ADMIN_COOKIE_NAME)
    if not cookie_val:
        raise HTTPException(
            status_code=401,
            detail="Admin authentication required",
        )

    admin_user = verify_admin_cookie(cookie_val)
    if not admin_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired admin session",
        )

    return admin_user
