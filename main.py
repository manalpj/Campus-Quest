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
    """Update checkpoint details and safely adjust sequence order if position changes."""
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
    if not row:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return dict(row)


@app.delete("/api/gods/checkpoints/{checkpoint_id}")
def delete_checkpoint(
    checkpoint_id: int,
    admin_user: str = Depends(auth.require_admin),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """Delete checkpoint and renumber subsequent checkpoints to maintain continuous ordering."""
    deleted = db.delete_checkpoint(conn, checkpoint_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return {"status": "ok", "deleted_id": checkpoint_id}


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

    return {
        "game_state": game_state,
        "name": team["name"],
        "members": members,
        "code": team["code"],
        "device_status": "this phone is your team's device",
    }


# Mount static files (must come after specific API and /gods routes)
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


