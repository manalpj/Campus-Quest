"""Main FastAPI application entry point for Campus Quest.

Provides health checks, public configuration endpoints, and safe
static file delivery for the player and administrative interfaces.
"""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import auth
import config
import db
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


# Mount static files (must come after specific API and /gods routes)
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

