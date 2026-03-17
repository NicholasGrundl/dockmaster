"""FastAPI authentication dependencies.

Shared auth helpers used across route modules:
- get_current_user: Bearer JWT verification (API routes)
- get_session_data: Session cookie extraction (UI and semi-public routes)
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import BadSignature, URLSafeSerializer

from dockmaster.config import Settings

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
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    realm = getattr(request.app.state, "realm", None)
    if realm is None:
        raise HTTPException(status_code=503, detail="Auth service not configured")

    try:
        return realm.verify(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
