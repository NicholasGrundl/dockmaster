"""Admin authorization dependencies — RBAC-first with email whitelist fallback."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from dockmaster.auth.dependencies import get_current_user
from dockmaster.config import Settings, get_settings


async def _is_admin(
    email: str,
    authority: object | None,
    admin_emails: set[str],
) -> bool:
    """Check if email has admin access via RBAC or whitelist fallback.

    Check 1: RBAC — authority.has_permission(email, "dockmaster", "admin")
    Check 2: Bootstrap fallback — email in DOCKMASTER_ADMIN_EMAILS
    """
    if authority is not None:
        granted = await authority.has_permission(email, "dockmaster", "admin")
        if granted:
            return True

    return email in admin_emails


async def require_admin_api(
    request: Request,
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Admin gate for API endpoints (JWT Bearer auth).

    Returns the user dict if admin, raises 403 otherwise.
    """
    email = user.get("email", "")
    authority = getattr(request.app.state, "authority", None)

    if not await _is_admin(email, authority, settings.dockmaster_admin_emails):
        raise HTTPException(status_code=403, detail="Admin access required")

    return user


async def require_admin_ui(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Admin gate for UI pages (session cookie auth).

    Returns the user dict if admin, redirects to /ui/login if no session,
    raises 403 if authenticated but not admin.
    """
    from dockmaster.routes.ui import require_ui_session

    user = await require_ui_session(request, settings)
    email = user.get("email", "")
    authority = getattr(request.app.state, "authority", None)

    if not await _is_admin(email, authority, settings.dockmaster_admin_emails):
        raise HTTPException(status_code=403, detail="Admin access required")

    return user


async def require_admin_writes(request: Request) -> None:
    """Capability gate — ensures admin SM client is configured for write operations.

    Returns None if writes are available, raises 503 otherwise.
    """
    admin_client = getattr(request.app.state, "admin_storage", None)
    if admin_client is None:
        raise HTTPException(
            status_code=503,
            detail="RBAC write operations not configured (admin SA key not set)",
        )
