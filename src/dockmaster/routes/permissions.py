"""Routes: GET /auth/has — permission check endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from dockmaster.auth.middleware import get_current_user

logger = structlog.get_logger("dockmaster.permissions")

router = APIRouter(tags=["permissions"])


async def _check_permission(request: Request, subject: str, target: str, permission: str) -> Response:
    """Shared permission check logic for both endpoint variants."""
    authority = getattr(request.app.state, "authority", None)
    if authority is None:
        raise HTTPException(status_code=503, detail="RBAC service not configured")

    try:
        granted = await authority.has_permission(subject, target, permission)
    except Exception:
        logger.exception("permission_check_error", subject=subject, target=target, permission=permission)
        raise HTTPException(status_code=500, detail="Internal server error")

    if granted:
        return Response(status_code=204)

    return JSONResponse(
        status_code=403,
        content={
            "status": "Error",
            "message": f"{subject} does not have {permission} for {target}",
        },
    )


@router.get("/has/{subject}/{target}/{permission}")
async def has_permission_path(
    request: Request,
    subject: str,
    target: str,
    permission: str,
    _user: dict = Depends(get_current_user),
) -> Response:
    """Check permission via path parameters."""
    return await _check_permission(request, subject, target, permission)


@router.get("/has")
async def has_permission_query(
    request: Request,
    subject: str,
    target: str,
    permission: str,
    _user: dict = Depends(get_current_user),
) -> Response:
    """Check permission via query parameters."""
    return await _check_permission(request, subject, target, permission)
