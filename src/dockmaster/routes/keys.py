"""Route: GET /auth/key/{kid} — unauthenticated public key endpoint.

Auth pattern: Public (no gate). Requiring auth would be circular — consumers
need the public key to verify JWTs in the first place.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from dockmaster.auth.jwt_verifier import ServiceRealm
from dockmaster.state import get_realm

router = APIRouter(tags=["jwt"])


@router.get("/key/{kid}")
async def get_public_key(
    kid: str,
    request: Request,
    realm: Annotated[ServiceRealm | None, Depends(get_realm)],
) -> PlainTextResponse:
    """Return the PEM certificate for a key ID.

    Used by consuming services to verify JWTs signed by dockmaster service accounts.
    Unauthenticated — requiring auth would be circular.
    """
    if realm is None:
        raise HTTPException(status_code=503, detail="Auth service not configured")

    pem = realm.get_key(kid)
    if pem is None:
        raise HTTPException(status_code=404, detail=f"Key {kid} was not found.")

    return PlainTextResponse(content=pem, media_type="application/x-pem-file")
