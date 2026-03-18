"""Routes: Admin UI — /ui/login, /ui/ (dashboard)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from dockmaster.auth.dependencies import check_permission, resolve_session
from dockmaster.config import Settings, get_settings
from dockmaster.ui.config import UIConfig

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _timestamp_to_datetime(ts: int | float) -> str:
    """Convert a Unix timestamp to a human-readable datetime string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


templates.env.filters["timestamp_to_datetime"] = _timestamp_to_datetime

# Public router — no auth guard
public_router = APIRouter(tags=["ui"])

# Protected router — requires active session
protected_router = APIRouter(tags=["ui"])


async def _get_session_user(request: Request) -> dict | None:
    """Extract user data from session cookie. Returns None if not authenticated."""
    settings = request.app.state.settings
    store = getattr(request.app.state, "session_store", None)
    cookie = request.cookies.get("session_id")
    return await resolve_session(cookie, store, settings.session_secret_key)


async def require_ui_session(request: Request) -> dict:
    """Dependency that ensures the user has an active session.

    Redirects to /ui/login if not authenticated.
    """
    user = await _get_session_user(request)
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
async def login_page(request: Request):
    """Branded login page with Google SSO button."""
    # If already logged in, redirect to dashboard
    user = await _get_session_user(request)
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
    settings: Annotated[Settings, Depends(get_settings)],
    user: dict = Depends(require_ui_session),
):
    """Admin dashboard — user's sessions, service status."""
    session_store = getattr(request.app.state, "session_store", None)
    if session_store:
        from dockmaster.rbac.admin_ops import list_sessions_by_email

        email = user.get("email", "")
        sessions = await list_sessions_by_email(session_store, email) if email else {}
    else:
        sessions = {}

    services = {
        "signer": getattr(request.app.state, "signer", None) is not None,
        "realm": getattr(request.app.state, "realm", None) is not None,
        "oauth": getattr(request.app.state, "oauth", None) is not None,
        "secrets": getattr(request.app.state, "secrets_storage", None) is not None,
    }

    # Check admin status for nav links
    authority = getattr(request.app.state, "authority", None)
    admin = await check_permission(
        user.get("email", ""), "dockmaster", "admin", authority, settings.dockmaster_admin_emails
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "ui": _ui_config(request),
            "user": user,
            "sessions": sessions,
            "services": services,
            "is_admin": admin,
        },
    )
