"""Routes: Session-gated endpoints — /auth/session/principal, /auth/session/token, /auth/session/list.

Auth pattern: Hard gate (``allow_session`` at router level). All routes require
a valid session (cookie or refresh_token). Uses ``get_session_user`` for user
data and ``get_token_issuer``/``get_session_store`` state bridges.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dockmaster.auth.dependencies import allow_session, get_session_user
from dockmaster.auth.jwt_signers import EphemeralKeypairSigner
from dockmaster.rbac.admin_ops import list_sessions_by_email
from dockmaster.sessions.protocol import SessionStore
from dockmaster.state import get_session_store, get_token_issuer

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
    token_issuer: Annotated[EphemeralKeypairSigner | None, Depends(get_token_issuer)],
) -> TokenResponse:
    """Issue a Type C JWT for a target service.

    Auth: session cookie or refresh_token (verified by allow_session gate).
    Query params: service (required) — the target service audience.
    """
    email = user.get("email", "")
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
    session_store: Annotated[SessionStore | None, Depends(get_session_store)],
) -> dict:
    """Return current user's active sessions."""
    email = user.get("email", "")
    if not email:
        return {}

    if session_store is None:
        return {}

    return await list_sessions_by_email(session_store, email)
