"""Route: GET /auth/claims — return decoded JWT claims.

Auth pattern: Hard gate (``allow_jwt`` at router level). Uses ``get_jwt_claims``
to extract the decoded token data. Textbook example of the gate + info pattern.
"""

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
