"""Route: POST /auth/token — issue a Type C JWT for a target service.

Dual auth: session cookie (browser) or Bearer JWT (CLI).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from dockmaster.auth.dependencies import get_session_data
from dockmaster.config import Settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["jwt"])
_bearer = HTTPBearer(auto_error=False)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: None = None


async def _email_from_session(request: Request, settings: Settings) -> str | None:
    """Try to extract email from session cookie. Returns None if not authenticated."""
    data = await get_session_data(request, settings)
    if not data:
        return None
    return data.get("email")


async def _email_from_bearer(request: Request) -> str | None:
    """Try to extract email from Bearer JWT. Returns None if not authenticated."""
    credentials: HTTPAuthorizationCredentials | None = await _bearer(request)
    if credentials is None:
        return None

    realm = getattr(request.app.state, "realm", None)
    if realm is None:
        return None

    try:
        claims = realm.verify(credentials.credentials)
        return claims.get("email")
    except ValueError:
        return None


@router.post("/token", response_model=TokenResponse)
async def issue_token(
    request: Request,
) -> TokenResponse:
    """Issue a Type C JWT for a target service.

    Auth: session cookie (browser) or Bearer JWT (CLI).
    Query params: service (required) — the target service audience.
    """
    settings: Settings = request.app.state.settings
    token_issuer = getattr(request.app.state, "token_issuer", None)
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Token issuer not configured")

    # Dual auth: try session first, then Bearer
    email = await _email_from_session(request, settings)
    if email is None:
        email = await _email_from_bearer(request)
    if email is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Require service param
    service = request.query_params.get("service")
    if not service:
        raise HTTPException(status_code=400, detail="The service query parameter is required")

    # Sign Type C JWT
    access_token = token_issuer.sign(
        subject=email,
        audience=service,
    )

    logger.info("token_issued", email=email, service=service)

    return TokenResponse(
        access_token=access_token,
        expires_in=token_issuer.default_ttl,
    )
