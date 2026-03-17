"""FastAPI authentication dependencies.

Shared auth helpers used across route modules:
- get_current_user: Bearer JWT verification (API routes)
- get_session_data: Session cookie extraction (UI and semi-public routes)
"""

from __future__ import annotations

import hashlib

import structlog
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import BadSignature, URLSafeSerializer

from dockmaster.config import Settings

logger = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def get_session_data(request: Request, settings: Settings) -> dict | None:
    """Extract session data from the session cookie.

    Returns the session dict if valid, or None if no cookie, bad signature,
    or expired session.
    """
    session_store = getattr(request.app.state, "session_store", None)
    cookie = request.cookies.get("session_id")
    if not cookie or not session_store:
        return None

    signer = URLSafeSerializer(settings.session_secret_key)
    try:
        session_id = signer.loads(cookie)
    except BadSignature:
        return None

    return await session_store.get(session_id)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Verify the Bearer token and return decoded claims.

    Raises HTTP 401 for missing or invalid tokens.

    Note: This dependency intentionally does NOT validate the ``aud`` (audience)
    claim. Dockmaster is the token issuer, and its own endpoints (permission
    checks, claims introspection) are designed to accept any valid
    dockmaster-issued JWT regardless of which downstream service the token is
    scoped to. Audience validation is the responsibility of downstream services
    — they check ``aud`` to confirm a token was intended for them, preventing
    lateral replay across services.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    realm = getattr(request.app.state, "realm", None)
    if realm is None:
        raise HTTPException(status_code=503, detail="Auth service not configured")

    try:
        return realm.verify(credentials.credentials)
    except ValueError as exc:
        token_fingerprint = hashlib.sha256(
            credentials.credentials.encode()
        ).hexdigest()[:8]
        logger.warning(
            "jwt_verification_failed",
            error=str(exc),
            token_fingerprint=token_fingerprint,
        )
        raise HTTPException(
            status_code=401, detail="Invalid or expired token"
        ) from exc
