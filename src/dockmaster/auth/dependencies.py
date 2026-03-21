"""FastAPI authentication dependencies.

This module contains all auth-related FastAPI dependencies, organized by the
dependency prefix taxonomy::

    HARD (raise on failure — route never executes)
    ├── allow_*    → Auth enforcement (401/403)          [router-level]
    │   ├── allow_jwt                  Verify dockmaster Bearer JWT
    │   ├── allow_session              Verify session (cookie or refresh_token)
    │   ├── allow_google_credential    Verify Google JWT or access token
    │   └── allow_jwt_admin            allow_jwt + admin permission check
    ├── needs_*    → System capability check (503)       [router or route-level]
    │   ├── needs_admin_storage        Assert admin SM client is configured
    │   └── needs_session_store        Assert session store is configured
    │
    SOFT (never raise — route decides what to do)
    ├── check_*    → Auth evaluation → AuthResult        [route-level, UI only]
    │   └── check_ui_session(service?, permission?)
    └── get_*      → Data extraction → value or empty    [route-level]
        ├── get_jwt_claims             Decoded JWT claims (or {})
        ├── get_session_user           Session user data (or {})
        └── get_google_claims          Verified Google credential (or None)

**Two-layer design within this module:**

- **Utility functions** — pure logic, explicit typed args, no Depends, no app.state.
  ``verify_jwt``, ``resolve_session``, ``check_permission``, ``verify_google_credential``

- **FastAPI dependencies** — inject via Depends/Cookie/HTTPBearer, call utilities.
  All functions above with ``allow_*``, ``needs_*``, ``check_*``, or ``get_*`` prefixes.

State bridge ``get_*`` dependencies (``get_authority``, ``get_token_issuer``, etc.)
live in ``state.py``, not here — they access infrastructure, not credentials.
"""

import hashlib
from typing import Annotated, Callable, Literal

import structlog
from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel

from dockmaster.auth.token_validator import validate_access_token
from dockmaster.config import Settings, get_settings


# ═══════════════════════════════════════════════════════════════════
# Verified credential models
# ═══════════════════════════════════════════════════════════════════


class GoogleJWTCredential(BaseModel):
    """Verified Google-signed JWT. The ``aud`` claim is the target service."""

    email: str | None
    target_service: str
    raw_claims: dict
    credential_type: Literal["jwt"] = "jwt"


class GoogleAccessTokenCredential(BaseModel):
    """Verified Google access token via tokeninfo. The ``aud`` claim is the OAuth client ID."""

    email: str | None
    oauth_client_id: str
    raw_claims: dict
    credential_type: Literal["access_token"] = "access_token"


logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Utility functions — pure logic, explicit typed args
# ═══════════════════════════════════════════════════════════════════


def verify_jwt(token: str, realm: object) -> dict:
    """Verify a dockmaster JWT via the ServiceRealm.

    Returns decoded claims dict. Raises ValueError on any failure
    (expired, bad signature, unknown kid, etc.).
    """
    return realm.verify(token)


async def resolve_session(
    handle: str | None,
    session_store: object | None,
    secret_key: str,
) -> dict | None:
    """Resolve session data from a session handle
    - a signed cookie value
    - a refresh_token value

    Returns the session data dict if valid, or None if no cookie,
    bad signature, expired, or missing session store.
    """
    if not handle or not session_store:
        return None

    signer = URLSafeSerializer(secret_key)
    try:
        session_id = signer.loads(handle)
    except BadSignature:
        return None

    return await session_store.get(session_id)


async def check_permission(
    email: str,
    service: str,
    permission: str,
    authority: object | None,
    whitelist_emails: set[str] | None = None,
) -> bool:
    """Check RBAC permission with optional email whitelist bypass.

    Returns True if:
    1. The email is in ``whitelist_emails`` (if provided) — bypasses RBAC entirely.
    2. The RBAC authority grants the permission.

    The whitelist is a bootstrap/escape-hatch mechanism: callers must
    explicitly construct and pass the set, so scope is controlled at
    the call site.
    """
    if whitelist_emails and email in whitelist_emails:
        return True

    if authority is not None:
        granted = await authority.has_permission(email, service, permission)
        if granted:
            return True

    return False


async def verify_google_credential(
    token: str,
    realm: object | None,
    authorized_issuers: set[str],
    authorized_audiences: set[str],
    tokeninfo_url: str,
) -> GoogleJWTCredential | GoogleAccessTokenCredential:
    """Verify a Google JWT or access token. Returns a typed credential.

    Tries JWT verification first (via realm), checking issuer and audience.
    Falls back to Google's tokeninfo API for access tokens.
    Raises ValueError on credential verification failure.
    """
    # Try JWT verification first
    jwt_claims = None
    if realm is not None:
        try:
            jwt_claims = realm.verify(token)
        except ValueError:
            pass  # Not a valid JWT — fall through to access token

    if jwt_claims is not None:
        iss = jwt_claims.get("iss", "")
        if iss not in authorized_issuers:
            raise ValueError(f"Issuer not allowed: {iss}")
        aud = jwt_claims.get("aud", "")
        if aud not in authorized_audiences:
            raise ValueError(f"Audience not allowed: {aud}")
        return GoogleJWTCredential(
            email=jwt_claims.get("email"),
            target_service=aud,
            raw_claims=jwt_claims,
        )

    # Fallback: Google access token via tokeninfo
    claims = await validate_access_token(
        token=token,
        authorized_audiences=authorized_audiences,
        tokeninfo_url=tokeninfo_url,
    )
    return GoogleAccessTokenCredential(
        email=claims.get("email"),
        oauth_client_id=claims.get("aud", ""),
        raw_claims=claims,
    )


# ═══════════════════════════════════════════════════════════════════
# HARD dependencies — allow_* (auth gates, raise on failure)
# Applied at router-level via dependencies=[Depends(allow_*)].
# ═══════════════════════════════════════════════════════════════════


async def allow_jwt(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(auto_error=False)),
    ],
) -> dict:
    """Gate: require valid dockmaster Bearer JWT. Returns decoded claims.

    Use as a router-level gate for API zones requiring a valid
    dockmaster JWT. Raises 401 if no token or invalid/expired.

    Note: does NOT validate the ``aud`` (audience) claim. Dockmaster
    endpoints accept any valid dockmaster-issued JWT. Audience validation
    is the responsibility of downstream services.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    realm = getattr(request.app.state, "realm", None)
    if realm is None:
        raise HTTPException(status_code=503, detail="Auth service not configured")

    try:
        return verify_jwt(credentials.credentials, realm)
    except ValueError as exc:
        token_fingerprint = hashlib.sha256(credentials.credentials.encode()).hexdigest()[:8]
        logger.warning(
            "jwt_verification_failed",
            error=str(exc),
            token_fingerprint=token_fingerprint,
        )
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


async def allow_session(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session_cookie: Annotated[str | None, Cookie(alias="session_id")] = None,
) -> dict:
    """Gate: require valid session handle. Returns session data dict.

    Searches for session handle in this order:
    - tries cookie first
    - looks for refresh_token in JSON body as fallback

    Use as a router-level gate for session
    """
    store = getattr(request.app.state, "session_store", None)

    # Try cookie first
    data = await resolve_session(session_cookie, store, settings.session_secret_key)
    if data is not None:
        return data

    # Try refresh_token freom request body
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except Exception:
        refresh_token = None

    data = await resolve_session(refresh_token, store, settings.session_secret_key)
    if data is not None:
        return data

    raise HTTPException(status_code=401, detail="Not authenticated")


async def allow_google_credential(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(auto_error=False)),
    ],
) -> GoogleJWTCredential | GoogleAccessTokenCredential:
    """Gate: require valid Google JWT or access token. Returns typed credential.

    Use as a router-level gate for the exchange router. Verifies the
    credential as a Google JWT (issuer + audience check) or falls back
    to Google's tokeninfo API for access tokens.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    realm = getattr(request.app.state, "realm", None)

    try:
        return await verify_google_credential(
            token=credentials.credentials,
            realm=realm,
            authorized_issuers=settings.authorized_issuers,
            authorized_audiences=settings.authorized_audience,
            tokeninfo_url=settings.access_token_endpoint,
        )
    except ValueError as exc:
        logger.warning("google_credential_failed", error=str(exc))
        raise HTTPException(status_code=401, detail="Not authenticated") from exc


async def allow_jwt_admin(
    request: Request,
    user: Annotated[dict, Depends(allow_jwt)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Composed gate: Bearer JWT + dockmaster admin permission.

    Wraps allow_jwt, then checks admin permission via RBAC with
    email whitelist fallback. Raises 403 if not admin.
    """
    email = user.get("email", "")
    authority = getattr(request.app.state, "authority", None)

    if not await check_permission(
        email, "dockmaster", "admin", authority, whitelist_emails=settings.dockmaster_admin_emails or None
    ):
        logger.warning("admin_access_denied", email=email, auth="jwt")
        raise HTTPException(status_code=403, detail="Access denied")

    return user


# ═══════════════════════════════════════════════════════════════════
# SOFT dependencies — get_* (data extraction, never raise)
# Used at route-level alongside a router-level allow_* gate.
# Return data or empty/None — the route decides what to do.
# ═══════════════════════════════════════════════════════════════════


async def get_google_claims(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(auto_error=False)),
    ],
) -> GoogleJWTCredential | GoogleAccessTokenCredential | None:
    """Info dependency: return verified Google credential from Bearer token.

    Calls verify_google_credential to verify as Google JWT or access token.
    Returns None if no valid credential. Use alongside a router-level
    auth gate — this dependency provides data, not auth enforcement.
    """
    if credentials is None:
        return None
    realm = getattr(request.app.state, "realm", None)
    try:
        return await verify_google_credential(
            token=credentials.credentials,
            realm=realm,
            authorized_issuers=settings.authorized_issuers,
            authorized_audiences=settings.authorized_audience,
            tokeninfo_url=settings.access_token_endpoint,
        )
    except ValueError:
        return None


async def get_jwt_claims(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(auto_error=False)),
    ],
) -> dict:
    """Info dependency: return decoded JWT claims from Bearer token.

    Calls verify_jwt to decode the token. Returns an empty dict if no
    valid token. Use alongside a router-level auth gate — this dependency
    provides data, not auth enforcement.
    """
    if credentials is None:
        return {}
    realm = getattr(request.app.state, "realm", None)
    if realm is None:
        return {}
    try:
        return verify_jwt(credentials.credentials, realm)
    except ValueError:
        return {}


async def get_session_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session_cookie: Annotated[str | None, Cookie(alias="session_id")] = None,
) -> dict:
    """Info dependency: return the current session user's data.

    Calls resolve_session to extract user data from the session
    handle (e.g. cookie or refresh_token).

    Returns an empty dict if no valid session. Use alongside a router-level
    auth gate — this dependency provides data, not auth enforcement.
    """
    store = getattr(request.app.state, "session_store", None)

    # Try cookie first
    data = await resolve_session(session_cookie, store, settings.session_secret_key)
    if data is not None:
        return data

    # Try refresh_token freom request body
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except Exception:
        refresh_token = None

    data = await resolve_session(refresh_token, store, settings.session_secret_key)
    if data is not None:
        return data

    return {}


# ═══════════════════════════════════════════════════════════════════
# HARD dependencies — needs_* (system capability checks, raise 503)
# Check what the system can do, not what the user is allowed to do.
# ═══════════════════════════════════════════════════════════════════


async def needs_admin_storage(request: Request) -> None:
    """System capability check: admin SM client is configured for writes.

    Raises 503 if admin_storage is not on app.state. This checks what the
    system can do, not what the user is allowed to do.
    """
    if getattr(request.app.state, "admin_storage", None) is None:
        logger.warning(
            "admin_writes_unavailable",
            error="admin_storage not configured on app.state",
        )
        raise HTTPException(
            status_code=503,
            detail="Write operations are not available",
        )


async def needs_session_store(request: Request) -> None:
    """System capability check: session store is configured.

    Raises 503 if session_store is not on app.state.
    """
    if getattr(request.app.state, "session_store", None) is None:
        logger.warning(
            "session_store_unavailable",
            error="session_store not configured on app.state",
        )
        raise HTTPException(
            status_code=503,
            detail="Session store not configured",
        )


# ═══════════════════════════════════════════════════════════════════
# SOFT dependencies — check_* (auth evaluation, never raise)
# UI routes use these instead of allow_* gates because every branch
# (no session, no permission, success) must produce HTML, not JSON.
# The route owns the full decision tree.
# ═══════════════════════════════════════════════════════════════════


class AuthResult(BaseModel):
    is_authenticated: bool
    has_permission: bool | None
    user: dict


def check_ui_session(service: str | None = None, permission: str | None = None) -> Callable[..., AuthResult]:
    """Soft auth check for UI routes. Returns AuthResult, never raises.

    With no args: checks session only (has_permission = None).
    With service + permission: also checks RBAC (has_permission = True/False).

    Also returns user session data if available
    """

    async def _check(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        session_cookie: Annotated[str | None, Cookie(alias="session_id")] = None,
    ) -> AuthResult:
        store = getattr(request.app.state, "session_store", None)

        # Check is user in session
        data = await resolve_session(session_cookie, store, settings.session_secret_key)
        if not data:
            return AuthResult(is_authenticated=False, has_permission=None, user={})
        # Check permissions if passed
        if service is not None and permission is not None:
            authority = getattr(request.app.state, "authority", None)
            permitted = await check_permission(
                data.get("email", ""),
                service,
                permission,
                authority,
                whitelist_emails=settings.dockmaster_admin_emails or None,
            )
            return AuthResult(is_authenticated=True, has_permission=permitted, user=data)

        return AuthResult(is_authenticated=True, has_permission=None, user=data)

    return _check
