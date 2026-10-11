"""Main FastAPI application entry point for Campus Quest.

Provides health checks, public configuration endpoints, and safe
static file delivery for the player and administrative interfaces.
"""

from contextlib import asynccontextmanager
import json
import os
from typing import Optional
from pathlib import Path
import sqlite3
import time
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

import auth
import config
import db
import game
import ratelimit


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize SQLite database and ensure schema and default settings exist."""
    db.init_db()
    yield


app = FastAPI(
    title="Campus Quest",
    description="Geofenced clue hunt for the DAVV campus",
    version="0.1.0",
    lifespan=lifespan,
)


class AdminLoginRequest(BaseModel):
    """Validated input model for administrator login."""

    username: str = Field(..., min_length=1, max_length=64, description="Administrator username")
    password: str = Field(..., min_length=1, max_length=256, description="Administrator passphrase")


class AdminWipeRequest(BaseModel):
    """Validated input model for administrator event data wipe."""

    confirm: str = Field(..., description="Confirmation word, must be exactly WIPE")

    @field_validator("confirm")
    @classmethod
    def validate_confirm(cls, v: str) -> str:
        if v.strip() != "WIPE":
            raise ValueError("Confirmation must be exactly 'WIPE'")
        return v.strip()


class TeamRegisterRequest(BaseModel):
    """Validated input model for player team registration."""

    name: str = Field(..., min_length=2, max_length=30, description="Team name (2 to 30 characters)")
    members: list[str] = Field(..., min_length=1, description="List of team member names")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 2 or len(trimmed) > 30:
            raise ValueError("Team name must be between 2 and 30 characters")
        return trimmed

    @field_validator("members")
    @classmethod
    def validate_members(cls, v: list[str]) -> list[str]:
        cleaned = [m.strip() for m in v if isinstance(m, str) and m.strip()]
        if len(cleaned) < config.MIN_MEMBERS:
            raise ValueError(f"Team must have at least {config.MIN_MEMBERS} members")
        if len(cleaned) > config.MAX_MEMBERS:
            raise ValueError(f"Team cannot have more than {config.MAX_MEMBERS} members")
        for m in cleaned:
            if len(m) < 1 or len(m) > 30:
                raise ValueError("Member names must be between 1 and 30 characters")
        return cleaned


class TeamJoinRequest(BaseModel):
    """Validated input model for joining an existing team via code."""

    code: str = Field(..., min_length=1, max_length=20, description="Team code (e.g. PHX-4821)")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        trimmed = v.strip().upper()
        if not trimmed:
            raise ValueError("Team code cannot be blank")
        return trimmed


class PingRequest(BaseModel):
    """Validated input model for player location pings."""

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude coordinate (-90 to 90)")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude coordinate (-180 to 180)")
    accuracy: float = Field(..., ge=0.0, le=10000.0, description="GPS accuracy in metres (0 to 10000)")
    ts: Optional[float] = Field(default=None, description="Optional client timestamp")
    test: bool = Field(default=False, description="Flag indicating simulated/test location fix")


class TestModeToggleRequest(BaseModel):
    """Validated input model for toggling location test mode."""

    enabled: bool = Field(..., description="Whether test mode should be enabled or disabled")


class TeamAdjustRequest(BaseModel):
    """Validated input model for administrator team time adjustments."""

    minutes: int = Field(..., ge=-180, le=180, description="Minutes to add (+) or remove (-), cannot be 0")
    reason: str = Field(..., min_length=3, max_length=120, description="Reason for adjustment (3 to 120 chars)")

    @field_validator("minutes")
    @classmethod
    def validate_minutes(cls, v: int) -> int:
        if v == 0:
            raise ValueError("Adjustment minutes cannot be 0")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 3 or len(trimmed) > 120:
            raise ValueError("Reason must be between 3 and 120 characters")
        return trimmed


class TeamClearRequest(BaseModel):
    """Validated input model for administrator force-clearing a checkpoint."""

    reason: str = Field(..., min_length=3, max_length=120, description="Reason for force-clearing (3 to 120 chars)")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 3 or len(trimmed) > 120:
            raise ValueError("Reason must be between 3 and 120 characters")
        return trimmed


class CheckpointCreateRequest(BaseModel):
    """Validated input model for creating a route checkpoint."""

    name: str = Field(..., min_length=1, max_length=60, description="Checkpoint name")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude coordinate")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude coordinate")
    radius: float = Field(default=30.0, ge=25.0, le=100.0, description="Geofence radius in metres")
    clue: str = Field(..., min_length=1, max_length=300, description="Clue shown to players")
    hint: str = Field(..., min_length=1, max_length=300, description="Easier hint for +3 min penalty")
    story: Optional[str] = Field(default=None, max_length=300, description="Optional fact revealed after unlock")
    position: Optional[int] = Field(default=None, ge=1, description="Order position in route sequence")

    @model_validator(mode="after")
    def validate_bounds(self) -> "CheckpointCreateRequest":
        if not game.is_within_campus_bounds(
            self.lat,
            self.lng,
            config.CAMPUS_BOUNDS_SW_LAT,
            config.CAMPUS_BOUNDS_SW_LNG,
            config.CAMPUS_BOUNDS_NE_LAT,
            config.CAMPUS_BOUNDS_NE_LNG,
        ):
            raise ValueError("Coordinates must be within DAVV campus bounds")
        return self


class CheckpointUpdateRequest(BaseModel):
    """Validated input model for updating an existing route checkpoint."""

    name: str = Field(..., min_length=1, max_length=60, description="Checkpoint name")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude coordinate")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude coordinate")
    radius: float = Field(default=30.0, ge=25.0, le=100.0, description="Geofence radius in metres")
    clue: str = Field(..., min_length=1, max_length=300, description="Clue shown to players")
    hint: str = Field(..., min_length=1, max_length=300, description="Easier hint for +3 min penalty")
    story: Optional[str] = Field(default=None, max_length=300, description="Optional fact revealed after unlock")
    position: Optional[int] = Field(default=None, ge=1, description="Order position in route sequence")

    @model_validator(mode="after")
    def validate_bounds(self) -> "CheckpointUpdateRequest":
        if not game.is_within_campus_bounds(
            self.lat,
            self.lng,
            config.CAMPUS_BOUNDS_SW_LAT,
            config.CAMPUS_BOUNDS_SW_LNG,
            config.CAMPUS_BOUNDS_NE_LAT,
            config.CAMPUS_BOUNDS_NE_LNG,
        ):
            raise ValueError("Coordinates must be within DAVV campus bounds")
        return self


@app.middleware("http")
async def security_and_header_middleware(request: Request, call_next):
    """Enforce payload size boundaries and security headers."""
    te = request.headers.get("transfer-encoding", "").lower()
    if "chunked" in te and request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=400,
            content={"detail": "Chunked transfer encoding is not supported for API requests"},
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            cl = int(content_length)
            if cl < 0 or cl > config.MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request payload exceeds size limit"},
                )
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header"},
            )

    response = await call_next(request)
    # Ensure Referrer-Policy is never 'no-referrer' so OSM tiles load correctly
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if config.ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(StarletteHTTPException)
def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions, rendering HTML 404 for browser pages and JSON for API."""
    if exc.status_code == 404 and not request.url.path.startswith("/api/"):
        file_404 = STATIC_DIR / "404.html"
        if file_404.is_file():
            return FileResponse(file_404, status_code=404)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
def generic_exception_handler(request: Request, exc: Exception):
    """Prevent internal server details, SQL, or stack traces from leaking."""
    if isinstance(exc, StarletteHTTPException):
        if exc.status_code == 404 and not request.url.path.startswith("/api/"):
            file_404 = STATIC_DIR / "404.html"
            if file_404.is_file():
                return FileResponse(file_404, status_code=404)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Note: Endpoints are plain def, not async def, per architecture rules
@app.get("/healthz")
def healthz():
    """Health check endpoint for container orchestrators and monitors."""
    return {"status": "ok"}


@app.get("/api/config")
def get_public_config(conn: sqlite3.Connection = Depends(db.get_db)):
    """Return safe public settings needed by client map and UI, including test mode."""
    cfg = config.get_public_config()
    cfg["test_mode"] = (db.get_setting(conn, "test_mode") == "1")
    cfg["allow_test_mode"] = config.ALLOW_TEST_MODE
    return cfg


@app.get("/api/rules")
def get_rules():
    """Build rules and FAQ dynamically from configuration parameters.

    Ensures numerical values, durations, and penalties can never go out of date
    with config.py settings.
    """
    hint_min = config.HINT_PENALTY_S // 60
    skip_wait_min = config.SKIP_WAIT_S // 60
    skip_pen_min = config.SKIP_PENALTY_S // 60
    boost_pct = int(round(config.BOOST_PERCENT * 100))

    return {
        "rules": [
            {
                "title": "Quest Objective",
                "text": f"Walk across the DAVV campus together to find and unlock {config.MIN_CHECKPOINTS} or more hidden checkpoints in sequence.",
            },
            {
                "title": "Unlocking Checkpoints",
                "text": f"Follow each clue to its physical location. Stay inside the geofence zone (25 to 100 m radius) until your device logs {config.STREAK_REQUIRED} consecutive GPS fixes.",
            },
            {
                "title": "GPS & Speed Limits",
                "text": f"Locations with GPS accuracy worse than {int(config.ACCURACY_LIMIT_M)} m are ignored to prevent drift unlocks. Moving faster than {int(config.MAX_SPEED_MPS)} m/s ({int(config.MAX_SPEED_MPS * 3.6)} km/h) resets your streak.",
            },
            {
                "title": "Power-ups",
                "text": f"Hint adds a {hint_min}-minute penalty (+{config.HINT_PENALTY_S}s) and reveals a clear clue. Radar shows live distance for {config.RADAR_DURATION_S}s. Radius Boost expands geofences by {boost_pct}% for {config.BOOST_DURATION_S}s.",
            },
            {
                "title": "Skipping Checkpoints",
                "text": f"If stuck on a checkpoint for at least {skip_wait_min} minutes ({config.SKIP_WAIT_S}s), your team can skip it for a {skip_pen_min}-minute penalty (+{config.SKIP_PENALTY_S}s).",
            },
        ],
        "faq": [
            {
                "q": "GPS is not working",
                "a": f"Ensure browser location permission is set to Allow. Move outdoors away from thick concrete walls or dense trees. Fixes worse than {int(config.ACCURACY_LIMIT_M)} m accuracy are held until satellite reception improves.",
            },
            {
                "q": "My phone died",
                "a": "Visit an organizer at the desk to release your team's device. Another member can then enter your team code on their phone to continue without losing progress.",
            },
            {
                "q": "I am standing at the spot but it does not unlock",
                "a": f"GPS signals drift near large campus buildings. Hold your phone still for a few seconds to let accuracy settle under {int(config.ACCURACY_LIMIT_M)} m and record {config.STREAK_REQUIRED} consecutive fixes inside the zone, or activate a Radius Boost.",
            },
            {
                "q": "What does a Hint cost",
                "a": f"Using a hint adds {hint_min} minutes (+{config.HINT_PENALTY_S}s) to your total adjusted time. Only one hint is available per checkpoint.",
            },
            {
                "q": "How do I win",
                "a": "Teams are ranked first by most checkpoints cleared, then by lowest adjusted time (elapsed time + penalties − bonuses), and lastly by earliest final unlock time.",
            },
        ],
        "values": {
            "hint_penalty_s": config.HINT_PENALTY_S,
            "skip_wait_s": config.SKIP_WAIT_S,
            "skip_penalty_s": config.SKIP_PENALTY_S,
            "radar_duration_s": config.RADAR_DURATION_S,
            "boost_duration_s": config.BOOST_DURATION_S,
            "boost_percent": boost_pct,
            "accuracy_limit_m": config.ACCURACY_LIMIT_M,
            "streak_required": config.STREAK_REQUIRED,
            "max_speed_mps": config.MAX_SPEED_MPS,
            "min_checkpoints": config.MIN_CHECKPOINTS,
            "min_members": config.MIN_MEMBERS,
        },
    }


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/gods")
def gods_page():
    """Serve administrative control panel HTML without linking from player UI."""
    gods_file = STATIC_DIR / "gods.html"
    if not gods_file.is_file():
        raise HTTPException(status_code=404, detail="Admin page not found")
    return FileResponse(gods_file)


@app.get("/board")
def board_page():
    """Serve big-screen leaderboard HTML for projector display."""
    board_file = STATIC_DIR / "board.html"
    if not board_file.is_file():
        raise HTTPException(status_code=404, detail="Board page not found")
    return FileResponse(board_file)


@app.get("/privacy")
def privacy_page():
    """Serve the plain language privacy notice HTML with organizer contact."""
    privacy_file = STATIC_DIR / "privacy.html"
    if not privacy_file.is_file():
        raise HTTPException(status_code=404, detail="Privacy page not found")
    content = privacy_file.read_text(encoding="utf-8")
    content = content.replace("{{ORGANIZER_NAME}}", config.ORGANIZER_NAME)
    content = content.replace("{{ORGANIZER_CONTACT}}", config.ORGANIZER_CONTACT)
    return HTMLResponse(content)


@app.get("/terms")
def terms_page():
    """Serve the short event rules and terms HTML with organizer contact."""
    terms_file = STATIC_DIR / "terms.html"
    if not terms_file.is_file():
        raise HTTPException(status_code=404, detail="Terms page not found")
    content = terms_file.read_text(encoding="utf-8")
    content = content.replace("{{ORGANIZER_NAME}}", config.ORGANIZER_NAME)
    content = content.replace("{{ORGANIZER_CONTACT}}", config.ORGANIZER_CONTACT)
    return HTMLResponse(content)


@app.get("/favicon.ico")
def favicon():
    """Serve the SVG favicon for browser icon requests."""
    fav_file = STATIC_DIR / "favicon.svg"
    if not fav_file.is_file():
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(fav_file, media_type="image/svg+xml")



# --- Administrative API Endpoints ---


@app.post("/api/gods/login")
def gods_login(
    request: Request,
    response: Response,
    body: AdminLoginRequest,
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Authenticate administrator, rate-limit attempts, and set signed session cookie.

    Does not log or return the password under any circumstance.
    """
    client_ip = ratelimit.get_client_ip(request)
    if ratelimit.is_rate_limited(
        f"login:{client_ip}",
        max_attempts=config.LOGIN_ATTEMPTS_PER_MIN,
        window_s=60.0,
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait before retrying.",
        )

    if not auth.verify_admin_credentials(body.username, body.password):
        db.log_event(
            conn,
            None,
            game.EVENT_ADMIN_LOGIN_FAILURE,
            f"ip={client_ip} result=failed",
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    db.log_event(
        conn,
        None,
        game.EVENT_ADMIN_LOGIN_SUCCESS,
        f"ip={client_ip}",
    )
    auth.set_admin_cookie(response, body.username)
    return {"status": "ok", "username": body.username}


@app.post("/api/gods/logout")
def gods_logout(response: Response, admin_user: str = Depends(auth.require_admin)):
    """Terminate administrator session by clearing the quest_admin cookie."""
    auth.clear_admin_cookie(response)
    return {"status": "ok"}


@app.get("/api/gods/me")
def gods_me(admin_user: str = Depends(auth.require_admin)):
    """Return the username of the active authenticated administrator."""
    return {"username": admin_user}


@app.get("/api/gods/events")
def get_gods_events(
    limit: int = Query(default=100, ge=1, le=500, description="Max number of recent events to return"),
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Retrieve recent operational and game events ordered newest first.

    Guarded behind administrator authentication. Limit bounded between 1 and 500.
    """
    rows = db.get_latest_events(conn, limit=limit)
    return [
        {
            "id": row["id"],
            "ts": row["ts"],
            "team_id": row["team_id"],
            "type": row["type"],
            "detail": row["detail"],
        }
        for row in rows
    ]


# --- Checkpoint Management Endpoints ---


@app.get("/api/gods/checkpoints")
def list_checkpoints(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Retrieve all route checkpoints ordered by sequence position."""
    rows = db.get_checkpoints(conn)
    return [dict(r) for r in rows]


@app.post("/api/gods/checkpoints", status_code=201)
def create_checkpoint(
    body: CheckpointCreateRequest,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Create a new checkpoint, automatically shifting existing positions to avoid duplicates."""
    game_state = db.get_setting(conn, "game_state") or "setup"
    if game_state != "setup":
        raise HTTPException(
            status_code=400,
            detail="Cannot add checkpoints once the game has started",
        )

    row = db.create_checkpoint(
        conn,
        name=body.name.strip(),
        lat=body.lat,
        lng=body.lng,
        radius=body.radius,
        clue=body.clue.strip(),
        hint=body.hint.strip(),
        story=body.story.strip() if body.story else None,
        position=body.position,
    )
    return dict(row)


@app.put("/api/gods/checkpoints/{checkpoint_id}")
def update_checkpoint(
    checkpoint_id: int,
    body: CheckpointUpdateRequest,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Update checkpoint details and safely adjust sequence order if position changes.

    Locking rule: once the game has started, changes to location, radius,
    and order are rejected. Only clue, hint, and story text may be updated.
    """
    existing = db.get_checkpoint_by_id(conn, checkpoint_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    game_state = db.get_setting(conn, "game_state") or "setup"
    if game_state != "setup":
        lat_changed = abs(existing["lat"] - body.lat) > 1e-6
        lng_changed = abs(existing["lng"] - body.lng) > 1e-6
        radius_changed = abs(existing["radius"] - body.radius) > 1e-6
        pos_changed = (body.position is not None) and (body.position != existing["position"])

        if lat_changed or lng_changed or radius_changed or pos_changed:
            raise HTTPException(
                status_code=400,
                detail="Checkpoint location, radius, and order are locked once the game has started. Only clue, hint, and story text may be edited.",
            )

    row = db.update_checkpoint(
        conn,
        checkpoint_id=checkpoint_id,
        name=body.name.strip(),
        lat=body.lat,
        lng=body.lng,
        radius=body.radius,
        clue=body.clue.strip(),
        hint=body.hint.strip(),
        story=body.story.strip() if body.story else None,
        position=body.position,
    )
    return dict(row)


@app.delete("/api/gods/checkpoints/{checkpoint_id}")
def delete_checkpoint(
    checkpoint_id: int,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Delete checkpoint and renumber subsequent checkpoints to maintain continuous ordering.

    Locking rule: checkpoints cannot be deleted once the game has started.
    """
    game_state = db.get_setting(conn, "game_state") or "setup"
    if game_state != "setup":
        raise HTTPException(
            status_code=400,
            detail="Checkpoints cannot be deleted once the game has started",
        )

    deleted = db.delete_checkpoint(conn, checkpoint_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return {"status": "ok", "deleted_id": checkpoint_id}


# --- Game Control Endpoints ---


@app.post("/api/gods/registration/open")
def open_registration(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Open team registration for players."""
    db.set_setting(conn, "registration_open", "1")
    return {"status": "ok", "registration_open": True}


@app.post("/api/gods/registration/close")
def close_registration(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Close team registration for players."""
    db.set_setting(conn, "registration_open", "0")
    return {"status": "ok", "registration_open": False}


@app.post("/api/gods/game/start")
def start_game(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Start the game, requiring at least MIN_CHECKPOINTS checkpoints.

    Sets game_state = 'running' and started_at = server_time + COUNTDOWN_S.
    """
    game_state = db.get_setting(conn, "game_state") or "setup"
    if game_state == "running":
        raise HTTPException(status_code=400, detail="Game is already running")
    if game_state == "ended":
        raise HTTPException(status_code=400, detail="Game has already ended")

    cp_count = db.get_checkpoint_count(conn)
    if cp_count < config.MIN_CHECKPOINTS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start game: at least {config.MIN_CHECKPOINTS} checkpoints required (currently {cp_count})",
        )

    now = time.time()
    started_at = now + config.COUNTDOWN_S
    db.set_setting(conn, "game_state", "running")
    db.set_setting(conn, "started_at", str(started_at))
    db.log_event(
        conn,
        None,
        game.EVENT_GAME_STARTED,
        f"countdown_s={config.COUNTDOWN_S}",
    )
    return {
        "status": "ok",
        "game_state": "running",
        "started_at": started_at,
        "started_at_ms": int(started_at * 1000),
        "countdown_s": config.COUNTDOWN_S,
    }


@app.post("/api/gods/game/end")
def end_game(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """End the active game session."""
    game_state = db.get_setting(conn, "game_state") or "setup"
    if game_state == "ended":
        raise HTTPException(status_code=400, detail="Game has already ended")

    db.set_setting(conn, "game_state", "ended")
    db.log_event(conn, None, game.EVENT_GAME_ENDED, None)
    return {"status": "ok", "game_state": "ended"}


@app.post("/api/gods/game/reset")
def reset_game(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Reset game state back to setup and clear all teams' gameplay progress."""
    db.set_setting(conn, "game_state", "setup")
    db.set_setting(conn, "started_at", "")
    teams_reset = db.reset_all_teams_progress(conn)
    invalidate_leaderboard_cache()
    db.log_event(conn, None, game.EVENT_GAME_RESET, f"teams_reset={teams_reset}")
    return {"status": "ok", "game_state": "setup", "teams_reset": teams_reset}


@app.get("/api/gods/game/status")
def get_gods_game_status(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Return administrative overview of game state, registration, checkpoints, and test mode."""
    game_state = db.get_setting(conn, "game_state") or "setup"
    reg_open = (db.get_setting(conn, "registration_open") == "1")
    started_at_str = db.get_setting(conn, "started_at")
    started_at = float(started_at_str) if started_at_str else None
    now = time.time()
    cp_count = db.get_checkpoint_count(conn)
    test_mode = (db.get_setting(conn, "test_mode") == "1")

    return {
        "game_state": game_state,
        "registration_open": reg_open,
        "checkpoint_count": cp_count,
        "min_checkpoints": config.MIN_CHECKPOINTS,
        "server_now_ms": int(now * 1000),
        "started_at": started_at,
        "started_at_ms": int(started_at * 1000) if started_at else None,
        "countdown_s": config.COUNTDOWN_S,
        "test_mode": test_mode,
        "allow_test_mode": config.ALLOW_TEST_MODE,
    }


@app.post("/api/gods/game/test-mode")
def set_gods_test_mode(
    body: TestModeToggleRequest,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Enable or disable location test mode.

    Can only be turned on if ALLOW_TEST_MODE is true in the environment.
    Note: This protects only the built-in app feature; the server cannot detect
    location spoofing performed outside the app (e.g. mock GPS apps or DevTools Sensors).
    """
    if not config.ALLOW_TEST_MODE:
        raise HTTPException(
            status_code=403,
            detail="Test mode is disabled in this environment (ALLOW_TEST_MODE is false).",
        )

    val = "1" if body.enabled else "0"
    db.set_setting(conn, "test_mode", val)
    db.log_event(
        conn,
        None,
        game.EVENT_TEST_MODE_TOGGLED,
        f"enabled={body.enabled} by={admin_user}",
    )
    return {"status": "ok", "test_mode": body.enabled}


# --- Admin Teams Management Endpoints ---


@app.get("/api/gods/teams")
def list_gods_teams(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Retrieve overview of all registered teams with device status, timing, and progress."""
    rows = db.get_admin_teams_data(conn)
    result = []
    now = time.time()
    for r in rows:
        adj_s = game.adjusted_time(
            elapsed_at_last_unlock_s=r["elapsed_at_last_unlock_s"],
            penalty_s=r["penalty_s"],
            bonus_s=r["bonus_s"],
        )
        members = json.loads(r["members"]) if r["members"] else []
        device_status = "bound" if r["device_hash"] else "free"
        last_seen = r["last_seen"]
        last_seen_s_ago = int(max(0, now - last_seen)) if last_seen else None

        result.append({
            "id": r["id"],
            "name": r["name"],
            "code": r["code"],
            "members": members,
            "device_status": device_status,
            "last_seen": last_seen,
            "last_seen_s_ago": last_seen_s_ago,
            "cleared": r["cleared"],
            "total": r["total"],
            "adjusted_time_s": adj_s,
            "adjusted_time": f"{adj_s // 60:02d}:{adj_s % 60:02d}",
            "penalty_s": r["penalty_s"],
            "bonus_s": r["bonus_s"],
            "finished": bool(r["finished_at"]),
        })
    return result


@app.post("/api/gods/teams/{team_id}/release")
def release_gods_team_device(
    team_id: int,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Clear device hash for team, allowing a replacement device to bind via team code."""
    success = db.release_team_device(conn, team_id)
    if not success:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"status": "ok", "team_id": team_id, "device_status": "free"}


@app.post("/api/gods/teams/{team_id}/adjust")
def adjust_gods_team_time(
    team_id: int,
    body: TeamAdjustRequest,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Add or remove minutes from a team's score with a mandatory logged reason."""
    success, penalty_s, bonus_s = db.adjust_team_time(
        conn,
        team_id=team_id,
        minutes=body.minutes,
        reason=body.reason,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Team not found")
    invalidate_leaderboard_cache()
    return {
        "status": "ok",
        "team_id": team_id,
        "minutes_adjusted": body.minutes,
        "penalty_s": penalty_s,
        "bonus_s": bonus_s,
    }


@app.post("/api/gods/teams/{team_id}/clear")
def force_clear_gods_team_checkpoint(
    team_id: int,
    body: TeamClearRequest,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Admin force-clears the current checkpoint for a team with a required reason.

    No penalty added, no power-up awarded, how='admin'.
    """
    team = db.get_team_by_id(conn, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if team["finished_at"]:
        raise HTTPException(status_code=409, detail="Team has already finished the quest")

    next_cp = db.get_team_next_checkpoint(conn, team_id)
    if not next_cp:
        raise HTTPException(status_code=409, detail="No active checkpoint remaining for this team")

    started_at_str = db.get_setting(conn, "started_at")
    started_at = float(started_at_str) if started_at_str else time.time()
    now = time.time()
    elapsed_s = max(0, int(now - started_at))

    cleared_before, total = db.get_team_progress_counts(conn, team_id)
    cleared_after = cleared_before + 1
    is_last = (cleared_after >= total)

    success = db.admin_force_clear_checkpoint(
        conn=conn,
        team_id=team_id,
        checkpoint_id=next_cp["id"],
        unlocked_at=now,
        elapsed_s=elapsed_s,
        reason=body.reason,
        is_last=is_last,
    )
    if not success:
        raise HTTPException(status_code=409, detail="Checkpoint was already cleared")

    invalidate_leaderboard_cache()

    subsequent_cp = db.get_team_next_checkpoint(conn, team_id)
    return {
        "status": "ok",
        "team_id": team_id,
        "checkpoint_id": next_cp["id"],
        "checkpoint_name": next_cp["name"],
        "cleared": cleared_after,
        "total": total,
        "next_clue": subsequent_cp["clue"] if subsequent_cp else None,
    }


@app.delete("/api/gods/teams/{team_id}")
def delete_gods_team(
    team_id: int,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Delete a team, cascading to its progress and hints, and audit-logging the action."""
    deleted = db.delete_team(conn, team_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Team not found")
    invalidate_leaderboard_cache()
    return {"status": "ok", "deleted_id": team_id}


@app.post("/api/gods/teams/reset")
def reset_all_teams_endpoint(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Reset progress, powerups, streaks, and completion state for all teams."""
    teams_reset = db.reset_all_teams_progress(conn)
    invalidate_leaderboard_cache()
    return {"status": "ok", "teams_reset": teams_reset}


@app.post("/api/gods/teams/{team_id}/reset")
def reset_single_team_endpoint(
    team_id: int,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Reset progress, powerups, streak, and completion state for a single team."""
    success = db.reset_team_progress(conn, team_id)
    if not success:
        raise HTTPException(status_code=404, detail="Team not found")
    invalidate_leaderboard_cache()
    return {"status": "ok", "team_id": team_id}


@app.post("/api/gods/wipe")
def wipe_event_data_endpoint(
    body: AdminWipeRequest,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Wipe all teams, player progress, hints, and event history.

    Requires require_admin and typing the word WIPE.
    Preserves checkpoints and settings.
    Logs nothing afterwards except that a wipe happened.
    """
    db.wipe_event_data(conn)
    invalidate_leaderboard_cache()
    return {"status": "ok", "detail": "Event data wiped successfully"}


# --- Player Team & Device Endpoints ---


@app.post("/api/register", status_code=201)
def register_team(
    request: Request,
    response: Response,
    body: TeamRegisterRequest,
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Register a new team, store hashed device token, and set HttpOnly device cookie."""
    client_ip = ratelimit.get_client_ip(request)
    if ratelimit.is_rate_limited(
        f"register:{client_ip}",
        max_attempts=config.REGISTER_ATTEMPTS_PER_MIN,
        window_s=60.0,
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many registration attempts. Please wait before retrying.",
        )

    reg_open = db.get_setting(conn, "registration_open")
    if reg_open != "1":
        raise HTTPException(
            status_code=403,
            detail="Registration is currently closed by the organizer.",
        )

    try:
        team_row, device_token = db.create_team(
            conn,
            name=body.name,
            members=body.members,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    auth.set_device_cookie(response, device_token)
    return {
        "id": team_row["id"],
        "name": team_row["name"],
        "code": team_row["code"],
        "members": json.loads(team_row["members"]),
    }


@app.post("/api/join")
def join_team(
    request: Request,
    response: Response,
    body: TeamJoinRequest,
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Bind client device to an existing team via team code.

    Rate limited per IP. Returns 409 if a device is already bound to the team.
    """
    client_ip = ratelimit.get_client_ip(request)
    if ratelimit.is_rate_limited(
        f"join:{client_ip}",
        max_attempts=config.JOIN_ATTEMPTS_PER_MIN,
        window_s=60.0,
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many join attempts. Please wait before retrying.",
        )

    code = game.normalize_team_code(body.code)
    team = db.get_team_by_code(conn, code)
    if not team:
        raise HTTPException(status_code=404, detail="Team code not found")

    # If the team already has an active bound device
    if team["device_hash"]:
        raise HTTPException(
            status_code=409,
            detail="This team is already playing on another device.",
        )

    # Team has no bound device (e.g. newly created unbound or organizer released)
    device_token = auth.generate_device_token()
    device_hash = auth.hash_device_token(device_token)
    db.bind_team_device(conn, team["id"], device_hash)

    auth.set_device_cookie(response, device_token)
    return {
        "id": team["id"],
        "name": team["name"],
        "code": team["code"],
        "members": json.loads(team["members"]),
    }


@app.get("/api/state")
def get_game_state(
    team: sqlite3.Row = Depends(auth.require_team_device),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Return active game state, powerups, and team info for authenticated player device."""
    game_state = db.get_setting(conn, "game_state") or "setup"
    members = json.loads(team["members"]) if team["members"] else []
    now = time.time()
    started_at_str = db.get_setting(conn, "started_at")
    started_at = float(started_at_str) if started_at_str else None
    started_at_ms = int(started_at * 1000) if started_at else None

    # Fetch latest team row to capture real-time powerup counts and timers
    team_row = db.get_team_by_id(conn, team["id"]) or team

    cleared_count, total_count = db.get_team_progress_counts(conn, team["id"])
    cleared_rows = db.get_team_cleared_checkpoints(conn, team["id"])
    cleared_checkpoints = [
        {
            "id": row["id"],
            "name": row["name"],
            "lat": row["lat"],
            "lng": row["lng"],
            "story": row["story"],
            "position": row["position"],
        }
        for row in cleared_rows
    ]

    current_clue = None
    active_hint = None
    can_skip = False
    checkpoint_started_at_ms = None
    skip_wait_s = config.SKIP_WAIT_S
    skip_penalty_s = config.SKIP_PENALTY_S
    if game_state == "running" and not team_row["finished_at"]:
        next_cp = db.get_team_next_checkpoint(conn, team["id"])
        if next_cp:
            current_clue = next_cp["clue"]
            active_hint = db.get_active_hint_for_team(conn, team["id"], next_cp["id"])
            if started_at is not None:
                cp_start_ts = db.get_team_current_checkpoint_start(conn, team["id"], started_at)
                checkpoint_started_at_ms = int(cp_start_ts * 1000)
                elapsed_cp_s = max(0.0, now - cp_start_ts)
                can_skip = game.is_skip_allowed(elapsed_cp_s, config.SKIP_WAIT_S)

    radar_active = game.is_powerup_active(team_row["radar_until"], now)
    radar_left_s = max(0, int(team_row["radar_until"] - now)) if radar_active else 0
    boost_active = game.is_powerup_active(team_row["boost_until"], now)
    boost_left_s = max(0, int(team_row["boost_until"] - now)) if boost_active else 0

    return {
        "game_state": game_state,
        "server_now_ms": int(now * 1000),
        "started_at_ms": started_at_ms,
        "name": team_row["name"],
        "members": members,
        "code": team_row["code"],
        "device_status": "this phone is your team's device",
        "cleared": cleared_count,
        "total": total_count,
        "current_clue": current_clue,
        "active_hint": active_hint,
        "radar_left": team_row["radar_left"],
        "boost_left": team_row["boost_left"],
        "radar_active": radar_active,
        "radar_left_s": radar_left_s,
        "boost_active": boost_active,
        "boost_left_s": boost_left_s,
        "penalty_s": team_row["penalty_s"],
        "bonus_s": team_row["bonus_s"],
        "cleared_checkpoints": cleared_checkpoints,
        "finished": bool(team_row["finished_at"]),
        "can_skip": can_skip,
        "checkpoint_started_at_ms": checkpoint_started_at_ms,
        "skip_wait_s": skip_wait_s,
        "skip_penalty_s": skip_penalty_s,
        "test_mode": (db.get_setting(conn, "test_mode") == "1"),
    }


@app.post("/api/skip")
def skip_current_checkpoint(
    team: sqlite3.Row = Depends(auth.require_team_device),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Skip the current checkpoint after waiting at least SKIP_WAIT_S.

    Adds SKIP_PENALTY_S to penalty, records progress with how='skipped',
    awards NO power-up, returns no story, and returns the next clue.
    """
    game_state = db.get_setting(conn, "game_state") or "setup"
    if game_state != "running":
        raise HTTPException(status_code=409, detail="Game is not running")

    started_at_str = db.get_setting(conn, "started_at")
    if not started_at_str:
        raise HTTPException(status_code=409, detail="Game has not started yet")

    try:
        started_at = float(started_at_str)
    except ValueError:
        raise HTTPException(status_code=409, detail="Invalid started_at setting")

    now = time.time()
    if now < started_at:
        raise HTTPException(status_code=409, detail="Game countdown has not finished yet")

    fresh_team = db.get_team_by_id(conn, team["id"]) or team
    if fresh_team["finished_at"]:
        raise HTTPException(status_code=409, detail="Team has already finished the quest")

    next_cp = db.get_team_next_checkpoint(conn, team["id"])
    if not next_cp:
        raise HTTPException(status_code=409, detail="No active checkpoint remaining")

    cp_start_ts = db.get_team_current_checkpoint_start(conn, team["id"], started_at)
    elapsed_cp_s = max(0.0, now - cp_start_ts)
    if not game.is_skip_allowed(elapsed_cp_s, config.SKIP_WAIT_S):
        wait_remaining_s = int(config.SKIP_WAIT_S - elapsed_cp_s)
        raise HTTPException(
            status_code=403,
            detail=f"Skip is not available yet. Must wait at least {config.SKIP_WAIT_S}s on the current checkpoint ({wait_remaining_s}s remaining).",
        )

    cleared_before, total = db.get_team_progress_counts(conn, team["id"])
    cleared_after = cleared_before + 1
    is_last = (cleared_after >= total)
    elapsed_s = max(0, int(now - started_at))

    success, new_penalty_s = db.skip_checkpoint(
        conn=conn,
        team_id=team["id"],
        checkpoint_id=next_cp["id"],
        unlocked_at=now,
        elapsed_s=elapsed_s,
        penalty_s=config.SKIP_PENALTY_S,
        is_last=is_last,
    )
    if not success:
        raise HTTPException(status_code=409, detail="Checkpoint was already cleared")

    invalidate_leaderboard_cache()

    subsequent_cp = db.get_team_next_checkpoint(conn, team["id"])
    return {
        "status": "skipped",
        "checkpoint_name": next_cp["name"],
        "story": None,
        "next_clue": subsequent_cp["clue"] if subsequent_cp else None,
        "cleared": cleared_after,
        "total": total,
        "penalty_s": new_penalty_s,
        "penalty_added_s": config.SKIP_PENALTY_S,
    }


@app.post("/api/powerup/{powerup_type}")
def activate_powerup(
    powerup_type: str,
    team: sqlite3.Row = Depends(auth.require_team_device),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Activate a player power-up (hint, radar, boost).

    Requires authenticated team device. Game must be running.
    - hint: adds HINT_PENALTY_S (+3m) penalty, reveals checkpoint hint. Max 1 per checkpoint.
    - radar: consumes 1 radar, activates live distance tracking for RADAR_DURATION_S (60s).
    - boost: consumes 1 boost, expands geofence radius by BOOST_PERCENT (+30%) for BOOST_DURATION_S (120s).
    """
    valid_types = {"hint", "radar", "boost"}
    clean_type = powerup_type.strip().lower()
    if clean_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown power-up type. Valid types: {', '.join(sorted(valid_types))}",
        )

    game_state = db.get_setting(conn, "game_state") or "setup"
    if game_state != "running":
        raise HTTPException(status_code=409, detail="Game is not running")

    started_at_str = db.get_setting(conn, "started_at")
    now = time.time()
    if not started_at_str or now < float(started_at_str):
        raise HTTPException(status_code=409, detail="Game countdown has not finished yet")

    fresh_team = db.get_team_by_id(conn, team["id"]) or team
    if fresh_team["finished_at"]:
        raise HTTPException(status_code=409, detail="Team has already finished the quest")

    next_cp = db.get_team_next_checkpoint(conn, team["id"])
    if not next_cp:
        raise HTTPException(status_code=409, detail="No active checkpoint remaining")

    if clean_type == "hint":
        first_time, hint_text, new_penalty = db.use_hint(
            conn=conn,
            team_id=team["id"],
            checkpoint_id=next_cp["id"],
            penalty_s=config.HINT_PENALTY_S,
            now=now,
        )
        if first_time:
            invalidate_leaderboard_cache()
        return {
            "powerup": "hint",
            "hint": hint_text,
            "penalty_added_s": config.HINT_PENALTY_S if first_time else 0,
            "penalty_s": new_penalty,
            "already_revealed": not first_time,
        }

    elif clean_type == "radar":
        if game.is_powerup_active(fresh_team["radar_until"], now):
            raise HTTPException(status_code=400, detail="Radar is already active")
        success, radar_until, remaining = db.use_radar(
            conn=conn,
            team_id=team["id"],
            duration_s=config.RADAR_DURATION_S,
            now=now,
        )
        if not success:
            raise HTTPException(status_code=400, detail="No Radar power-ups remaining")
        return {
            "powerup": "radar",
            "radar_left": remaining,
            "radar_until_ms": int(radar_until * 1000),
            "duration_s": config.RADAR_DURATION_S,
        }

    elif clean_type == "boost":
        if game.is_powerup_active(fresh_team["boost_until"], now):
            raise HTTPException(status_code=400, detail="Radius boost is already active")
        success, boost_until, remaining = db.use_boost(
            conn=conn,
            team_id=team["id"],
            duration_s=config.BOOST_DURATION_S,
            now=now,
        )
        if not success:
            raise HTTPException(status_code=400, detail="No Radius boost power-ups remaining")
        return {
            "powerup": "boost",
            "boost_left": remaining,
            "boost_until_ms": int(boost_until * 1000),
            "duration_s": config.BOOST_DURATION_S,
            "boost_percent": int(round(config.BOOST_PERCENT * 100)),
        }


@app.post("/api/ping")
def ping_location(
    body: PingRequest,
    team: sqlite3.Row = Depends(auth.require_team_device),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Process a player device GPS location ping.

    Validates coordinates, rejects if game is not running or countdown has not finished,
    filters weak accuracy fixes, calculates geofence distance to next checkpoint,
    manages the 2-in-a-row inside streak, and atomically unlocks checkpoints.
    Applies active Radius boost if running.
    Exposes Radar distance only while Radar is actively running.
    """
    game_state = db.get_setting(conn, "game_state") or "setup"
    if game_state != "running":
        raise HTTPException(
            status_code=409,
            detail="Game is not running",
        )

    started_at_str = db.get_setting(conn, "started_at")
    if not started_at_str:
        raise HTTPException(
            status_code=409,
            detail="Game has not started yet",
        )

    try:
        started_at = float(started_at_str)
    except ValueError:
        raise HTTPException(status_code=409, detail="Invalid started_at setting")

    now = time.time()
    if now < started_at:
        raise HTTPException(
            status_code=409,
            detail="Game countdown has not finished yet",
        )

    # Fetch latest team row for up-to-date power-up timers
    fresh_team = db.get_team_by_id(conn, team["id"]) or team

    # If team already completed all checkpoints
    if fresh_team["finished_at"]:
        _, total = db.get_team_progress_counts(conn, team["id"])
        return {
            "status": "completed",
            "cleared": total,
            "total": total,
        }

    # Test mode verification:
    # If the ping claims test: true, the server refuses it unless test mode is active in settings.
    # Note: This protects only the built-in app feature; the server cannot detect location spoofing
    # performed outside the app (e.g. mock GPS apps or DevTools Sensors).
    test_mode_on = (db.get_setting(conn, "test_mode") == "1")
    if body.test and not test_mode_on:
        db.log_event(
            conn,
            team["id"],
            game.EVENT_TEST_PING_REFUSED,
            f"test_ping_refused lat={body.lat} lng={body.lng}",
        )
        raise HTTPException(
            status_code=403,
            detail="Test mode is not active on the server.",
        )

    # Accuracy check: ignore fix if worse than configured threshold
    if not game.accuracy_ok(body.accuracy, config.ACCURACY_LIMIT_M):
        db.touch_team_last_seen(conn, team["id"], now)
        return {"status": "weak_gps"}

    # Speed plausibility check: reject teleporting fixes (> MAX_SPEED_MPS)
    # Test pings bypass this check so testers can simulate fixes across campus without rejection.
    if (
        not body.test
        and fresh_team["last_fix_lat"] is not None
        and fresh_team["last_fix_lng"] is not None
        and fresh_team["last_fix_ts"] is not None
    ):
        speed = game.speed_mps(
            prev_lat=fresh_team["last_fix_lat"],
            prev_lng=fresh_team["last_fix_lng"],
            prev_ts=fresh_team["last_fix_ts"],
            lat=body.lat,
            lng=body.lng,
            ts=now,
        )
        if speed > config.MAX_SPEED_MPS:
            db.reset_team_streak(conn, team["id"], now)
            db.log_event(
                conn,
                team["id"],
                game.EVENT_SPEED_REJECTED,
                f"speed_mps={speed:.2f} max={config.MAX_SPEED_MPS}",
            )
            return {"status": "implausible"}


    # Find next checkpoint (lowest position not in progress)
    next_cp = db.get_team_next_checkpoint(conn, team["id"])
    if not next_cp:
        _, total = db.get_team_progress_counts(conn, team["id"])
        return {
            "status": "completed",
            "cleared": total,
            "total": total,
        }

    # Haversine distance
    dist_m = game.haversine_m(body.lat, body.lng, next_cp["lat"], next_cp["lng"])

    # Boost test: check if radius boost is active
    boost_active = game.is_powerup_active(fresh_team["boost_until"], now)
    effective_radius = game.compute_effective_radius(
        next_cp["radius"],
        boost_active=boost_active,
        boost_percent=config.BOOST_PERCENT,
    )
    inside = game.is_inside(dist_m, effective_radius)

    # Radar test: check if radar is active
    radar_active = game.is_powerup_active(fresh_team["radar_until"], now)
    radar_info = {}
    if radar_active:
        radar_info = {
            "radar_distance_m": round(dist_m),
            "radar_label": game.format_radar_label(dist_m),
        }

    # Consecutive inside streak computation
    current_streak = fresh_team["inside_streak"]
    new_streak = game.next_streak(current_streak, inside)

    # Check unlock condition
    if game.should_unlock(new_streak, config.STREAK_REQUIRED):
        elapsed_s = max(0, int(now - started_at))
        cleared_before, total = db.get_team_progress_counts(conn, team["id"])
        cleared_after = cleared_before + 1
        is_last = (cleared_after >= total)

        # Alternating power-up award: 1st/3rd -> Radar, 2nd/4th -> Boost
        awarded = game.award_for(cleared_after)

        unlocked = db.unlock_checkpoint(
            conn=conn,
            team_id=team["id"],
            checkpoint_id=next_cp["id"],
            unlocked_at=now,
            elapsed_s=elapsed_s,
            is_last=is_last,
            lat=body.lat,
            lng=body.lng,
            awarded_powerup=awarded,
        )
        invalidate_leaderboard_cache()

        if not unlocked:
            subsequent_cp = db.get_team_next_checkpoint(conn, team["id"])
            fresh_team = db.get_team_by_id(conn, team["id"]) or team
            cleared_current, total_current = db.get_team_progress_counts(conn, team["id"])
            if fresh_team["finished_at"] or (total_current > 0 and cleared_current >= total_current):
                return {
                    "status": "completed",
                    "cleared": total_current,
                    "total": total_current,
                }
            resp = {"status": "searching"}
            if radar_active:
                resp.update(radar_info)
            return resp

        subsequent_cp = db.get_team_next_checkpoint(conn, team["id"])

        resp = {
            "status": "unlocked",
            "checkpoint_name": next_cp["name"],
            "story": next_cp["story"],
            "next_clue": subsequent_cp["clue"] if subsequent_cp else None,
            "cleared": cleared_after,
            "total": total,
            "awarded_powerup": awarded,
        }
        if radar_active:
            resp.update(radar_info)
        return resp
    else:
        db.update_team_fix_and_streak(
            conn=conn,
            team_id=team["id"],
            lat=body.lat,
            lng=body.lng,
            ts=now,
            streak=new_streak,
        )
        resp = {"status": "searching"}
        if radar_active:
            resp.update(radar_info)
        return resp


LEADERBOARD_CACHE_TTL_S = 1.0
_leaderboard_cache = {
    "cached_at": 0.0,
    "data": [],
}


def invalidate_leaderboard_cache() -> None:
    """Clear the in-memory leaderboard cache immediately."""
    global _leaderboard_cache
    _leaderboard_cache = {"cached_at": 0.0, "data": []}


@app.get("/api/leaderboard")
def get_leaderboard(
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Retrieve current ranked leaderboard.

    Computes ranking at most once per second and caches in memory.
    Cache is invalidated immediately on every checkpoint unlock.
    Returns rank, team name, code, cleared/total, adjusted time, and finished status.
    """
    global _leaderboard_cache
    now = time.time()
    if (now - _leaderboard_cache["cached_at"]) < LEADERBOARD_CACHE_TTL_S and _leaderboard_cache["data"]:
        return _leaderboard_cache["data"]

    rows = db.get_leaderboard_data(conn)
    team_data = []
    for r in rows:
        adj_s = game.adjusted_time(
            elapsed_at_last_unlock_s=r["elapsed_at_last_unlock_s"],
            penalty_s=r["penalty_s"],
            bonus_s=r["bonus_s"],
        )
        team_data.append({
            "team_id": r["team_id"],
            "name": r["name"],
            "code": r["code"],
            "cleared": r["cleared"],
            "total": r["total"],
            "adjusted_time": adj_s,
            "last_unlock_ts": r["last_unlock_ts"],
            "finished": bool(r["finished_at"]),
        })

    ranked = game.rank_teams(team_data)

    formatted = [
        {
            "rank": t["rank"],
            "name": t["name"],
            "code": t["code"],
            "cleared": t["cleared"],
            "total": t["total"],
            "adjusted_time_s": t["adjusted_time"],
            "adjusted_time": f"{t['adjusted_time'] // 60:02d}:{t['adjusted_time'] % 60:02d}",
            "finished": t["finished"],
        }
        for t in ranked
    ]

    _leaderboard_cache = {
        "cached_at": now,
        "data": formatted,
    }
    return formatted


@app.get("/api/board")
def get_board(
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Retrieve public big-screen leaderboard data and game state.

    Reuses the cached leaderboard function. Returns only rank, team name,
    cleared/total, and adjusted time. No members, codes, or locations.
    """
    raw_state = db.get_setting(conn, "game_state") or "setup"
    state_map = {
        "setup": ("waiting", "Waiting"),
        "running": ("running", "Running"),
        "ended": ("ended", "Ended"),
    }
    state_key, state_label = state_map.get(raw_state, ("waiting", "Waiting"))

    leaderboard = get_leaderboard(conn)
    teams = [
        {
            "rank": t["rank"],
            "name": t["name"],
            "cleared": t["cleared"],
            "total": t["total"],
            "adjusted_time": t["adjusted_time"],
        }
        for t in leaderboard
    ]

    return {
        "game_state": state_key,
        "status_label": state_label,
        "teams": teams,
    }


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
def api_not_found(path: str):
    """Catch-all for unmatched API endpoints to ensure JSON 404 is returned."""
    return JSONResponse(status_code=404, content={"detail": "Not found"})


# Mount static files (must come after specific API and /gods routes)
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")




