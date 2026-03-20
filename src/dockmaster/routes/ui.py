"""Routes: Admin UI — /ui/login, /ui/ (dashboard)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dockmaster.ui.config import UIConfig, templates
from dockmaster.state import get_ui_config
from dockmaster.auth.dependencies import check_ui_session, AuthResult

router = APIRouter(tags=["ui"])

@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    auth: Annotated[AuthResult, Depends(check_ui_session())],
    ui_config : Annotated[UIConfig,Depends(get_ui_config)],
    ):
    """Branded login page with Google SSO button."""
    
    # Auth Check, no permissions
    if not auth.is_authenticated:
        #Send to login page
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
    ui_config : Annotated[UIConfig,Depends(get_ui_config)],
):
    """Admin dashboard — user's sessions, service status."""
    # Auth Check
    if not auth.is_authenticated:
        return RedirectResponse("/ui/login", 307)
    if not auth.has_permission:                  
        is_admin = False
    else:
        is_admin = True
    user = auth.user

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
