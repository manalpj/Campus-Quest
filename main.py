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
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

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
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > config.MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request payload exceeds size limit"},
                )
        except ValueError:
            pass

    response = await call_next(request)
    # Ensure Referrer-Policy is never 'no-referrer' so OSM tiles load correctly
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(Exception)
def generic_exception_handler(request: Request, exc: Exception):
    """Prevent internal server details, SQL, or stack traces from leaking."""
    if isinstance(exc, HTTPException):
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
def get_public_config():
    """Return only safe, public settings needed by the client map and UI.

    Never exposes secrets, database paths, or admin credentials.
    """
    return config.get_public_config()


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/gods")
def gods_page():
    """Serve administrative control panel HTML without linking from player UI."""
    gods_file = STATIC_DIR / "gods.html"
    if not gods_file.is_file():
        raise HTTPException(status_code=404, detail="Admin page not found")
    return FileResponse(gods_file)


# --- Administrative API Endpoints ---


@app.post("/api/gods/login")
def gods_login(request: Request, response: Response, body: AdminLoginRequest):
    """Authenticate administrator, rate-limit attempts, and set signed session cookie.

    Does not log or return the password under any circumstance.
    """
    client_ip = ratelimit.get_client_ip(request)
    if ratelimit.is_rate_limited(
        client_ip,
        max_attempts=config.LOGIN_ATTEMPTS_PER_MIN,
        window_s=60.0,
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait before retrying.",
        )

    if not auth.verify_admin_credentials(body.username, body.password):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
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
    db.log_event(conn, "registration_opened", f"Registration opened by {admin_user}")
    return {"status": "ok", "registration_open": True}


@app.post("/api/gods/registration/close")
def close_registration(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Close team registration for players."""
    db.set_setting(conn, "registration_open", "0")
    db.log_event(conn, "registration_closed", f"Registration closed by {admin_user}")
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
        "game_started",
        f"Game started by {admin_user} with {config.COUNTDOWN_S}s countdown",
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
    db.log_event(conn, "game_ended", f"Game ended by {admin_user}")
    return {"status": "ok", "game_state": "ended"}


@app.get("/api/gods/game/status")
def get_gods_game_status(
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Return administrative overview of game state, registration, and checkpoints."""
    game_state = db.get_setting(conn, "game_state") or "setup"
    reg_open = (db.get_setting(conn, "registration_open") == "1")
    started_at_str = db.get_setting(conn, "started_at")
    started_at = float(started_at_str) if started_at_str else None
    now = time.time()
    cp_count = db.get_checkpoint_count(conn)

    return {
        "game_state": game_state,
        "registration_open": reg_open,
        "checkpoint_count": cp_count,
        "min_checkpoints": config.MIN_CHECKPOINTS,
        "server_now_ms": int(now * 1000),
        "started_at": started_at,
        "started_at_ms": int(started_at * 1000) if started_at else None,
        "countdown_s": config.COUNTDOWN_S,
    }


# --- Player Team & Device Endpoints ---


@app.post("/api/register", status_code=201)
def register_team(
    response: Response,
    body: TeamRegisterRequest,
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Register a new team, store hashed device token, and set HttpOnly device cookie."""
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
        client_ip,
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
    """Return active game state and team info for authenticated player device."""
    game_state = db.get_setting(conn, "game_state") or "setup"
    members = json.loads(team["members"]) if team["members"] else []
    now = time.time()
    started_at_str = db.get_setting(conn, "started_at")
    started_at = float(started_at_str) if started_at_str else None
    started_at_ms = int(started_at * 1000) if started_at else None

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
    if game_state == "running" and not team["finished_at"]:
        next_cp = db.get_team_next_checkpoint(conn, team["id"])
        if next_cp:
            current_clue = next_cp["clue"]

    return {
        "game_state": game_state,
        "server_now_ms": int(now * 1000),
        "started_at_ms": started_at_ms,
        "name": team["name"],
        "members": members,
        "code": team["code"],
        "device_status": "this phone is your team's device",
        "cleared": cleared_count,
        "total": total_count,
        "current_clue": current_clue,
        "cleared_checkpoints": cleared_checkpoints,
        "finished": bool(team["finished_at"]),
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
    Never exposes coordinates, radius, or distance in responses.
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

    # If team already completed all checkpoints
    if team["finished_at"]:
        _, total = db.get_team_progress_counts(conn, team["id"])
        return {
            "status": "completed",
            "cleared": total,
            "total": total,
        }

    # Accuracy check: ignore fix if worse than configured threshold
    if not game.accuracy_ok(body.accuracy, config.ACCURACY_LIMIT_M):
        db.touch_team_last_seen(conn, team["id"], now)
        return {"status": "weak_gps"}

    # Find next checkpoint (lowest position not in progress)
    next_cp = db.get_team_next_checkpoint(conn, team["id"])
    if not next_cp:
        _, total = db.get_team_progress_counts(conn, team["id"])
        return {
            "status": "completed",
            "cleared": total,
            "total": total,
        }

    # Haversine distance and inside test
    dist_m = game.haversine_m(body.lat, body.lng, next_cp["lat"], next_cp["lng"])
    inside = game.is_inside(dist_m, next_cp["radius"])

    # Consecutive inside streak computation
    current_streak = team["inside_streak"]
    new_streak = game.next_streak(current_streak, inside)

    # Check unlock condition
    if game.should_unlock(new_streak, config.STREAK_REQUIRED):
        elapsed_s = max(0, int(now - started_at))
        cleared_before, total = db.get_team_progress_counts(conn, team["id"])
        is_last = (cleared_before + 1 >= total)

        db.unlock_checkpoint(
            conn=conn,
            team_id=team["id"],
            checkpoint_id=next_cp["id"],
            unlocked_at=now,
            elapsed_s=elapsed_s,
            is_last=is_last,
            lat=body.lat,
            lng=body.lng,
        )

        subsequent_cp = db.get_team_next_checkpoint(conn, team["id"])
        cleared_after, _ = db.get_team_progress_counts(conn, team["id"])

        return {
            "status": "unlocked",
            "checkpoint_name": next_cp["name"],
            "story": next_cp["story"],
            "next_clue": subsequent_cp["clue"] if subsequent_cp else None,
            "cleared": cleared_after,
            "total": total,
        }
    else:
        db.update_team_fix_and_streak(
            conn=conn,
            team_id=team["id"],
            lat=body.lat,
            lng=body.lng,
            ts=now,
            streak=new_streak,
        )
        return {"status": "searching"}


# Mount static files (must come after specific API and /gods routes)
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")



