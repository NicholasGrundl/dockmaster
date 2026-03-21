"""Routes: GET /auth/has, GET /auth/grants — permission check and grants resolution.

Auth pattern: Hard gate (``allow_jwt`` at router level). All routes require
a valid dockmaster Bearer JWT. Uses ``get_authority`` state bridge for RBAC.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from dockmaster.auth.dependencies import allow_jwt
from dockmaster.rbac.authority import Authority
from dockmaster.state import get_authority

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["authenticated"],
    dependencies=[Depends(allow_jwt)],
)


async def _check_permission(authority: Authority | None, subject: str, target: str, permission: str) -> Response:
    """Shared permission check logic for both endpoint variants."""
    if authority is None:
        raise HTTPException(status_code=503, detail="RBAC service not configured")

    try:
        granted = await authority.has_permission(subject, target, permission)
    except Exception:
        logger.exception("permission_check_error", subject=subject, target=target, permission=permission)
        raise HTTPException(status_code=500, detail="Internal server error")

    if granted:
        return Response(status_code=204)

    raise HTTPException(
        status_code=403,
        detail=f"{subject} does not have {permission} for {target}",
    )


@router.get("/has/{subject}/{target}/{permission}")
async def has_permission_path(
    request: Request,
    subject: str,
    target: str,
    permission: str,
    authority: Annotated[Authority | None, Depends(get_authority)],
) -> Response:
    """Check permission via path parameters."""
    return await _check_permission(authority, subject, target, permission)


@router.get("/has")
async def has_permission_query(
    request: Request,
    subject: str,
    target: str,
    permission: str,
    authority: Annotated[Authority | None, Depends(get_authority)],
) -> Response:
    """Check permission via query parameters."""
    return await _check_permission(authority, subject, target, permission)


class GrantsResponse(BaseModel):
    subject: str
    target: str
    grants: list[str]


@router.get("/grants", response_model=GrantsResponse)
async def get_grants(
    request: Request,
    subject: str,
    target: str,
    authority: Annotated[Authority | None, Depends(get_authority)],
) -> GrantsResponse:
    """Return all resolved permissions for a subject on a target service.

    Auth: Bearer JWT (Type A SA JWT).
    Returns a flat list of "target:permission" strings.
    """
    if authority is None:
        raise HTTPException(status_code=503, detail="RBAC service not configured")

    try:
        permissions = await authority.get_permissions(subject, target)
    except Exception:
        logger.exception("grants_resolution_error", subject=subject, target=target)
        raise HTTPException(status_code=500, detail="Internal server error")

    return GrantsResponse(
        subject=subject,
        target=target,
        grants=sorted(f"{target}:{p}" for p in permissions),
    )
