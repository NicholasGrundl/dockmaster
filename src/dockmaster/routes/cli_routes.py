"""Routes: CLI auth — POST /auth/cli/token.

Issue a Type C JWT from a valid dockmaster Bearer JWT (CLI path).
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dockmaster.auth.dependencies import allow_jwt, get_jwt_claims

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["cli"],
    dependencies=[Depends(allow_jwt)],
)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: None = None


@router.post("/cli/token", response_model=TokenResponse)
async def issue_cli_token(
    request: Request,
    claims: Annotated[dict, Depends(get_jwt_claims)],
) -> TokenResponse:
    """Issue a Type C JWT for a target service.

    Auth: Bearer JWT (verified by allow_jwt gate).
    Query params: service (required) — the target service audience.
    """
    email = claims.get("email", "")
    token_issuer = getattr(request.app.state, "token_issuer", None)
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Token issuer not configured")

    service = request.query_params.get("service")
    if not service:
        raise HTTPException(status_code=400, detail="The service query parameter is required")

    access_token = token_issuer.sign(
        subject=email,
        audience=service,
    )

    logger.info("cli_token_issued", email=email, service=service)

    return TokenResponse(
        access_token=access_token,
        expires_in=token_issuer.default_ttl,
    )
