"""Route: GET /auth/claims — return decoded JWT claims."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dockmaster.auth.dependencies import get_current_user

router = APIRouter(tags=["jwt"])


@router.get("/claims")
async def get_claims(claims: dict = Depends(get_current_user)) -> dict:
    """Return the decoded claims from the Bearer token."""
    return claims
