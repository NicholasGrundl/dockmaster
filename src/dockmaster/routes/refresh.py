"""Route: POST /auth/refresh — exchange a Google refresh token for a dockmaster JWT."""

from __future__ import annotations

import asyncio

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dockmaster.config import Settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["jwt"])

PROFILE_CLAIM_KEYS = ("name", "picture", "given_name", "family_name", "locale")


class RefreshTokenRequest(BaseModel):
    """Request body for POST /auth/refresh."""

    refresh_token: str
    client_id: str | None = None
    service: str | None = None
    expiry: int = 3600


class RefreshResponse(BaseModel):
    """Response body for POST /auth/refresh."""

    token: str
    subject: str
    service: str
    expiry: int
    claims: dict
    id_token: str
    access_token: str


@router.post("/refresh")
async def refresh(
    body: RefreshTokenRequest,
    request: Request,
) -> RefreshResponse:
    """Exchange a Google refresh token for a dockmaster JWT.

    8-step flow:
    1. Resolve client_id
    2. Load client secret from Secret Manager
    3. Exchange refresh token with Google
    4. Verify returned id_token
    5. Check can_issue (issuer, audience, domain)
    6. Call Google UserInfo API for profile
    7. Resolve service audience
    8. Sign dockmaster JWT
    """
    settings: Settings = request.app.state.settings

    # --- Step 1: Resolve client_id ---
    client_id = body.client_id or settings.default_client_id
    if not client_id:
        raise HTTPException(status_code=400, detail="No client_id was specified and there is no default")

    # Normalize: if no dot, append suffix
    if "." not in client_id:
        client_id = f"{client_id}{settings.client_id_suffix}"

    # --- Step 2: Load client secret from Secret Manager ---
    secrets_storage = getattr(request.app.state, "secrets_storage", None)
    if secrets_storage is None:
        raise HTTPException(status_code=503, detail="Secrets storage not configured")

    try:
        client_secret = await asyncio.get_running_loop().run_in_executor(
            None, secrets_storage.get_client_secret, client_id
        )
    except Exception:
        logger.warning("client_secret_lookup_failed", client_id=client_id)
        raise HTTPException(status_code=400, detail="Invalid client_id value")

    # --- Step 3: Exchange refresh token with Google ---
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=30.0)) as http:
        token_resp = await http.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": body.refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )

    if token_resp.status_code != 200:
        logger.warning("google_refresh_failed", status=token_resp.status_code, body=token_resp.text)
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_data = token_resp.json()
    google_id_token = token_data.get("id_token", "")
    google_access_token = token_data.get("access_token", "")

    # --- Step 4: Verify returned id_token ---
    realm = getattr(request.app.state, "realm", None)
    if realm is None:
        raise HTTPException(status_code=503, detail="JWT verifier not configured")

    try:
        id_claims = realm.verify(google_id_token)
    except ValueError as exc:
        logger.warning("id_token_verification_failed", error=str(exc))
        raise HTTPException(status_code=401, detail="Not authenticated")

    # --- Step 5: Check can_issue ---
    issuer = id_claims.get("iss", "")
    audience = id_claims.get("aud", "")
    email = id_claims.get("email", "")
    domain = email.partition("@")[2]

    if issuer not in settings.authorized_issuers:
        raise HTTPException(status_code=403, detail=f"Issuer not allowed: {issuer}")
    if audience not in settings.authorized_audience:
        raise HTTPException(status_code=403, detail=f"Audience not allowed: {audience}")
    if domain not in settings.authorized_domains:
        raise HTTPException(status_code=403, detail=f"Domain not allowed: {domain}")

    # --- Step 6: Call Google UserInfo API for profile ---
    profile_claims: dict = {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=10.0)) as http:
            userinfo_resp = await http.get(
                settings.userinfo_endpoint,
                headers={"Authorization": f"Bearer {google_access_token}"},
            )
        if userinfo_resp.status_code == 200:
            userinfo = userinfo_resp.json()
            profile_claims = {k: userinfo[k] for k in PROFILE_CLAIM_KEYS if k in userinfo}
        else:
            logger.warning("userinfo_fetch_failed", status=userinfo_resp.status_code)
    except Exception:
        logger.warning("userinfo_fetch_error", exc_info=True)

    # --- Step 7: Resolve service audience ---
    service = body.service or audience

    # --- Step 8: Sign dockmaster JWT (Type C — ephemeral keypair) ---
    token_issuer = getattr(request.app.state, "token_issuer", None)
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Token issuer not configured")

    dockmaster_token = token_issuer.sign(
        subject=email,
        audience=service,
        ttl=body.expiry,
        extra_claims=profile_claims,
    )

    return RefreshResponse(
        token=dockmaster_token,
        subject=email,
        service=service,
        expiry=body.expiry,
        claims=profile_claims,
        id_token=google_id_token,
        access_token=google_access_token,
    )
