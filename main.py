"""Main FastAPI application entry point for Campus Quest.

Provides health checks, public configuration endpoints, and safe
static file delivery for the player and administrative interfaces.
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import config

app = FastAPI(
    title="Campus Quest",
    description="Geofenced clue hunt for the DAVV campus",
    version="0.1.0",
)


@app.middleware("http")
async def security_and_header_middleware(request: Request, call_next):
    """Enforce security headers compatible with OpenStreetMap tiles."""
    response = await call_next(request)
    # Ensure Referrer-Policy is never 'no-referrer' so OSM tiles load correctly
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(Exception)
def generic_exception_handler(request: Request, exc: Exception):
    """Prevent internal server details, SQL, or stack traces from leaking."""
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


# Mount static files (must come after specific API routes)
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
