"""Route: POST /auth/token — issue a Type C JWT for a target service.

Dual auth: session cookie (browser) or Bearer JWT (CLI).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dockmaster.auth.dependencies import allow_jwt_or_session, get_session_or_jwt_email

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["authenticated"],
    dependencies=[Depends(allow_jwt_or_session)],
)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: None = None


@router.post("/token", response_model=TokenResponse)
async def issue_token(
    request: Request,
    email: Annotated[str, Depends(get_session_or_jwt_email)],
) -> TokenResponse:
    """Issue a Type C JWT for a target service.

    Auth: session cookie or Bearer JWT (verified by allow_jwt_or_session gate).
    Query params: service (required) — the target service audience.
    """
    token_issuer = getattr(request.app.state, "token_issuer", None)
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Token issuer not configured")

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
