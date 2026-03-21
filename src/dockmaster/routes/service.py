"""Routes: Service-to-service auth — POST /auth/service/token.

Exchange a Google credential (JWT or access token) for a dockmaster Type C JWT.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dockmaster.auth.dependencies import (
    GoogleAccessTokenCredential,
    GoogleJWTCredential,
    allow_google_credential,
    get_google_claims,
)
from dockmaster.config import Settings, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["service"],
    dependencies=[Depends(allow_google_credential)],
)

PROFILE_CLAIM_KEYS = ("name", "picture", "given_name", "family_name", "locale")


class ExchangeResponse(BaseModel):
    token: str
    subject: str
    service: str
    expiry: int
    claims: dict = {}


@router.post("/service/token", response_model=ExchangeResponse)
async def exchange_token(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    google_claims: Annotated[GoogleJWTCredential | GoogleAccessTokenCredential | None, Depends(get_google_claims)],
) -> ExchangeResponse:
    """Exchange a Google JWT or access token for a dockmaster JWT.

    Auth: Google JWT or access token (verified by allow_google_credential gate).
    The verified claims are injected via get_google_claims.
    """
    token_issuer = getattr(request.app.state, "token_issuer", None)
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Auth service not configured")

    email = google_claims.email
    if email is None:
        raise HTTPException(status_code=400, detail="The email claim is missing")

    # JWT credentials carry the target service in aud; access tokens do not.
    target_service = google_claims.target_service if isinstance(google_claims, GoogleJWTCredential) else None
    service = request.query_params.get("service") or target_service
    if service is None:
        raise HTTPException(
            status_code=400,
            detail="The service query parameter is required",
        )

    # Validate email domain
    domain = email.partition("@")[2]
    if domain not in settings.authorized_domains:
        logger.warning("domain_not_allowed", domain=domain, email=email)
        raise HTTPException(status_code=403, detail="Access denied")

    # Copy profile claims
    profile_claims = {k: google_claims.raw_claims[k] for k in PROFILE_CLAIM_KEYS if k in google_claims.raw_claims}

    # Parse and cap expiry
    max_ttl = settings.max_token_ttl
    requested_expiry = int(request.query_params.get("expiry", "3600"))
    expiry = min(requested_expiry, max_ttl)
    if requested_expiry > max_ttl:
        logger.warning(
            "token_expiry_clamped",
            requested=requested_expiry,
            clamped_to=max_ttl,
            email=email,
            service=service,
        )

    # Sign Type C JWT (ephemeral-signed, iss="dockmaster")
    dockmaster_token = token_issuer.sign(
        subject=email,
        audience=service,
        ttl=expiry,
        extra_claims=profile_claims,
    )

    return ExchangeResponse(
        token=dockmaster_token,
        subject=email,
        service=service,
        expiry=expiry,
        claims=profile_claims,
    )
