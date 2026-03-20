"""Route: GET /auth/key/{kid} — unauthenticated public key endpoint."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

router = APIRouter(tags=["jwt"])


@router.get("/key/{kid}")
async def get_public_key(kid: str, request: Request) -> PlainTextResponse:
    """Return the PEM certificate for a key ID.

    Used by consuming services to verify JWTs signed by dockmaster service accounts.
    Unauthenticated — requiring auth would be circular.
    """
    realm = getattr(request.app.state, "realm", None)
    if realm is None:
        return JSONResponse(status_code=503, content={"error": "Auth service not configured"})

    pem = realm.get_key(kid)
    if pem is None:
        return JSONResponse(status_code=404, content={"error": f"Key {kid} was not found."})

    return PlainTextResponse(content=pem, media_type="application/x-pem-file")
