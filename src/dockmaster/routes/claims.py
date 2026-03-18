"""Route: GET /auth/claims — return decoded JWT claims."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from dockmaster.auth.dependencies import allow_jwt, get_jwt_claims

router = APIRouter(
    tags=["authenticated"],
    dependencies=[Depends(allow_jwt)],
)


@router.get("/claims")
async def get_claims(claims: Annotated[dict, Depends(get_jwt_claims)]) -> dict:
    """Return the decoded claims from the Bearer token."""
    return claims
