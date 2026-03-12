"""Routes: Admin UI — /ui/login, /ui/ (dashboard)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from dockmaster.config import Settings, get_settings
from dockmaster.ui.config import UIConfig

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _timestamp_to_datetime(ts: int | float) -> str:
    """Convert a Unix timestamp to a human-readable datetime string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


templates.env.filters["timestamp_to_datetime"] = _timestamp_to_datetime

# Public router — no auth guard
public_router = APIRouter()

# Protected router — requires active session
protected_router = APIRouter()


async def _get_session_user(request: Request, settings: Settings) -> dict | None:
    """Extract user data from session cookie. Returns None if not authenticated."""
    session_store = getattr(request.app.state, "session_store", None)
    cookie = request.cookies.get("session_id")
    if not cookie or not session_store:
        return None

    signer = URLSafeSerializer(settings.session_secret_key)
    try:
        session_id = signer.loads(cookie)
        return await session_store.get(session_id)
    except BadSignature:
        return None


async def require_ui_session(
    request: Request, settings: Settings = Depends(get_settings)
) -> dict:
    """Dependency that ensures the user has an active session.

    Redirects to /ui/login if not authenticated.
    """
    user = await _get_session_user(request, settings)
    if not user:
        raise _redirect_to_login()
    return user


def _redirect_to_login():
    """Create an HTTPException-like redirect to the login page."""
    from fastapi import HTTPException

    raise HTTPException(status_code=307, headers={"Location": "/ui/login"})


def _ui_config(request: Request) -> UIConfig:
    return getattr(request.app.state, "ui_config", UIConfig())


# ── Public routes ──


@public_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, settings: Settings = Depends(get_settings)):
    """Branded login page with Google SSO button."""
    # If already logged in, redirect to dashboard
    user = await _get_session_user(request, settings)
    if user:
        return RedirectResponse(url="/ui/", status_code=302)

    return templates.TemplateResponse(
        request,
        "login.html",
        {"ui": _ui_config(request), "user": None},
    )


# ── Protected routes ──


@protected_router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: dict = Depends(require_ui_session),
):
    """Admin dashboard — active sessions, service status."""
    session_store = getattr(request.app.state, "session_store", None)
    sessions = await session_store.list_all() if session_store else {}

    services = {
        "signer": getattr(request.app.state, "signer", None) is not None,
        "realm": getattr(request.app.state, "realm", None) is not None,
        "oauth": getattr(request.app.state, "oauth", None) is not None,
        "secrets": getattr(request.app.state, "secrets_storage", None) is not None,
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "ui": _ui_config(request),
            "user": user,
            "sessions": sessions,
            "services": services,
        },
    )
