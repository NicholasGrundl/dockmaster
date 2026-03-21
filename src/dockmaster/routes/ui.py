"""Routes: UI pages — /ui/login, /ui/ (dashboard).

Auth pattern: Soft gate (``check_ui_session`` at route level, no router-level gate).
UI routes never raise on auth failure — they redirect to login or render
conditional content based on ``AuthResult``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dockmaster.auth.dependencies import AuthResult, check_ui_session
from dockmaster.rbac.admin_ops import list_sessions_by_email
from dockmaster.sessions.protocol import SessionStore
from dockmaster.state import get_session_store, get_ui_config
from dockmaster.ui.config import UIConfig, templates

router = APIRouter(tags=["ui"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    auth: Annotated[AuthResult, Depends(check_ui_session())],
    ui_config: Annotated[UIConfig, Depends(get_ui_config)],
):
    """Branded login page with Google SSO button."""

    # Auth Check, no permissions
    if not auth.is_authenticated:
        # Send to login page
        return templates.TemplateResponse(
            request,
            "login.html",
            {"ui": ui_config, "user": None},
        )

    # Authenticated/logged in, redirect to dashboard
    return RedirectResponse(url="/ui/", status_code=302)


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    auth: Annotated[AuthResult, Depends(check_ui_session("dockmaster", "admin"))],
    ui_config: Annotated[UIConfig, Depends(get_ui_config)],
    session_store: Annotated[SessionStore | None, Depends(get_session_store)],
):
    """Admin dashboard — user's sessions, service status."""
    # Auth Check
    if not auth.is_authenticated:
        return RedirectResponse("/ui/login", 307)
    is_admin = bool(auth.has_permission)
    user = auth.user

    if session_store:
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

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "ui": ui_config,
            "user": user,
            "sessions": sessions,
            "services": services,
            "is_admin": is_admin,
        },
    )
