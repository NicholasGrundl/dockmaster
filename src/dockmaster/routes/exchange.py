"""Route: POST /auth/exchange — exchange Google credentials for a dockmaster JWT."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from dockmaster.auth.token_validator import validate_access_token
from dockmaster.config import Settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["jwt"])
_bearer = HTTPBearer(auto_error=False)

PROFILE_CLAIM_KEYS = ("name", "picture", "given_name", "family_name", "locale")


class ExchangeResponse(BaseModel):
    token: str
    subject: str
    service: str
    expiry: int
    claims: dict = {}


@router.post("/exchange", response_model=ExchangeResponse)
async def exchange_token(
    request: Request,
) -> ExchangeResponse:
    """Exchange a Google JWT or access token for a dockmaster JWT."""

    settings: Settings = request.app.state.settings

    # --- Step 0: Ensure auth singletons are available ---
    token_issuer = getattr(request.app.state, "token_issuer", None)
    realm = getattr(request.app.state, "realm", None)
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Auth service not configured")

    # --- Step 1: Extract Bearer token ---
    credentials: HTTPAuthorizationCredentials | None = await _bearer(request)
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = credentials.credentials

    # --- Step 2: Try JWT verification first ---
    claims: dict | None = None
    aud: str | None = None

    if realm is not None:
        try:
            claims = realm.verify(token)
            logger.debug("jwt_verification_success")
        except ValueError as exc:
            logger.debug("jwt_verification_failed", reason=str(exc))

    if claims is not None:
        # JWT path: check issuer and audience
        iss = claims.get("iss", "")
        if iss not in settings.authorized_issuers:
            raise HTTPException(status_code=403, detail=f"Issuer not allowed: {iss}")

        token_aud = claims.get("aud", "")
        if token_aud not in settings.authorized_audience:
            raise HTTPException(status_code=403, detail=f"Audience not allowed: {token_aud}")

        aud = token_aud
        email = claims.get("email")
    else:
        # --- Step 3: Fall back to access token validation ---
        try:
            claims = await validate_access_token(
                token=token,
                authorized_audiences=settings.authorized_audience,
                tokeninfo_url=settings.access_token_endpoint,
            )
            logger.debug("access_token_validation_success")
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Not authenticated") from exc

        email = claims.get("email")

    # --- Step 4: Resolve service audience ---
    service = request.query_params.get("service") or aud
    if service is None:
        raise HTTPException(
            status_code=400,
            detail="The service argument is required for access tokens",
        )

    # --- Step 5: Validate email and domain ---
    if email is None:
        raise HTTPException(status_code=400, detail="The email claim is missing")

    domain = email.partition("@")[2]
    if domain not in settings.authorized_domains:
        raise HTTPException(status_code=403, detail=f"Domain not allowed: {domain}")

    # --- Step 6: Copy profile claims ---
    profile_claims = {k: claims[k] for k in PROFILE_CLAIM_KEYS if k in claims}

    # --- Step 7: Parse and cap expiry ---
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

    # --- Step 8: Sign Type C JWT (ephemeral-signed, iss="dockmaster") ---
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
