"""Routes: Session-gated endpoints — /auth/session/principal, /auth/session/token, /auth/session/list."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dockmaster.auth.dependencies import allow_session, get_session_user
from dockmaster.rbac.admin_ops import list_sessions_by_email

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["session"],
    dependencies=[Depends(allow_session)],
)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: None = None


@router.get("/session/principal")
async def get_principal(
    user: Annotated[dict, Depends(get_session_user)],
) -> dict:
    """Return current session profile."""
    return user


@router.post("/session/token", response_model=TokenResponse)
async def issue_token(
    request: Request,
    user: Annotated[dict, Depends(get_session_user)],
) -> TokenResponse:
    """Issue a Type C JWT for a target service.

    Auth: session cookie or refresh_token (verified by allow_session gate).
    Query params: service (required) — the target service audience.
    """
    email = user.get("email", "")
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

    logger.info("token_issued", email=email, service=service)

    return TokenResponse(
        access_token=access_token,
        expires_in=token_issuer.default_ttl,
    )


@router.get("/session/list")
async def list_sessions(
    request: Request,
    user: Annotated[dict, Depends(get_session_user)],
) -> dict:
    """Return current user's active sessions."""
    email = user.get("email", "")
    if not email:
        return {}

    session_store = getattr(request.app.state, "session_store", None)
    if session_store is None:
        return {}

    return await list_sessions_by_email(session_store, email)
