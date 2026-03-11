"""FastAPI authentication dependency."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


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
