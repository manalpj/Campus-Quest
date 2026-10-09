"""Authentication and signed session management for Campus Quest.

Handles constant-time credential verification, HMAC-SHA256 signed admin cookies,
and the require_admin dependency protecting administrative routes.
"""

import hashlib
import hmac
import sqlite3
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


# --- Player Device Authentication ---

DEVICE_COOKIE_NAME = "quest_device"
DEVICE_SESSION_DURATION_S = 7 * 24 * 3600  # 7 days


def generate_device_token() -> str:
    """Generate a high-entropy URL-safe random token for player device binding."""
    import secrets

    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    """Compute the SHA-256 hexadecimal hash of a player device token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_device_token(token: str, stored_hash: str) -> bool:
    """Verify that a plaintext device token matches the stored SHA-256 hash."""
    if not token or not stored_hash:
        return False
    computed_hash = hash_device_token(token)
    return hmac.compare_digest(computed_hash, stored_hash)


def set_device_cookie(response: Response, token: str) -> None:
    """Attach secure HttpOnly quest_device cookie to response."""
    response.set_cookie(
        key=DEVICE_COOKIE_NAME,
        value=token,
        max_age=DEVICE_SESSION_DURATION_S,
        httponly=True,
        samesite="lax",
        secure=(config.ENV == "production"),
    )


def clear_device_cookie(response: Response) -> None:
    """Clear quest_device cookie."""
    response.delete_cookie(
        key=DEVICE_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=(config.ENV == "production"),
    )


def require_team_device(
    request: Request,
) -> sqlite3.Row:
    """FastAPI dependency: verifies quest_device cookie against stored device_hash in SQLite.

    Returns the validated sqlite3.Row representing the team.
    Raises 401 Unauthorized if cookie is missing, empty, or fails hash verification.
    """
    import db

    cookie_val = request.cookies.get(DEVICE_COOKIE_NAME)
    if not cookie_val:
        raise HTTPException(
            status_code=401,
            detail="Device authentication required",
        )

    token_hash = hash_device_token(cookie_val)
    conn = db.get_connection()
    try:
        team = db.get_team_by_device_hash(conn, token_hash)
        if not team or not team["device_hash"]:
            raise HTTPException(
                status_code=401,
                detail="Invalid or unbound device token",
            )

        if not hmac.compare_digest(token_hash, team["device_hash"]):
            raise HTTPException(
                status_code=401,
                detail="Device token verification failed",
            )

        return team
    finally:
        conn.close()

