"""FastAPI authentication dependencies.

Two-layer design:

**Utility functions** — pure logic, explicit typed args, no Depends, no app.state.
    verify_jwt, resolve_session, check_permission, verify_google_credential

**FastAPI dependencies** — inject via Depends/Cookie/HTTPBearer, call utilities.
    allow_jwt, allow_session, allow_jwt_or_session, allow_google_credential,
    allow_jwt_admin, allow_session_admin, needs_admin_storage
"""

import hashlib
from typing import Annotated, Literal

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
    cookie: str | None,
    session_store: object | None,
    secret_key: str,
) -> dict | None:
    """Resolve session data from a signed cookie value.

    Returns the session data dict if valid, or None if no cookie,
    bad signature, expired, or missing session store.
    """
    if not cookie or not session_store:
        return None

    signer = URLSafeSerializer(secret_key)
    try:
        session_id = signer.loads(cookie)
    except BadSignature:
        return None

    return await session_store.get(session_id)


async def check_permission(
    email: str,
    service: str,
    permission: str,
    authority: object | None,
    admin_emails: set[str],
) -> bool:
    """Check RBAC permission with admin email whitelist fallback.

    Returns True if the user has the permission via RBAC, or if the
    check is for ("dockmaster", "admin") and the email is in the
    admin whitelist.
    """
    if authority is not None:
        granted = await authority.has_permission(email, service, permission)
        if granted:
            return True

    if service == "dockmaster" and permission == "admin":
        return email in admin_emails

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
# FastAPI dependencies — inject via Depends, call utilities above
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
    """Gate: require valid session cookie. Returns session data dict.

    Use as a router-level gate for UI zones. Redirects to
    /ui/login if no valid session.
    """
    store = getattr(request.app.state, "session_store", None)
    data = await resolve_session(session_cookie, store, settings.session_secret_key)
    if data is None:
        raise HTTPException(status_code=307, headers={"Location": "/ui/login"})
    return data


async def allow_jwt_or_session(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(auto_error=False)),
    ],
    session_cookie: Annotated[str | None, Cookie(alias="session_id")] = None,
) -> str:
    """Gate: session cookie OR Bearer JWT. Returns email.

    Tries session first (browser clients), Bearer second (CLI/API).
    Use per-route for endpoints that accept either auth method.
    Raises 401 if neither succeeds.
    """
    # Try session first
    store = getattr(request.app.state, "session_store", None)
    data = await resolve_session(session_cookie, store, settings.session_secret_key)
    if data:
        return data.get("email", "")

    # Try Bearer JWT
    if credentials:
        realm = getattr(request.app.state, "realm", None)
        if realm:
            try:
                claims = verify_jwt(credentials.credentials, realm)
                return claims.get("email", "")
            except ValueError:
                pass

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

    if not await check_permission(email, "dockmaster", "admin", authority, settings.dockmaster_admin_emails):
        logger.warning("admin_access_denied", email=email, auth="jwt")
        raise HTTPException(status_code=403, detail="Access denied")

    return user


async def allow_session_admin(
    request: Request,
    user: Annotated[dict, Depends(allow_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Composed gate: session cookie + dockmaster admin permission.

    Session-based counterpart to allow_jwt_admin. For HTML/form-based
    admin pages. Redirects to /ui/login if no session, raises 403 if
    authenticated but not admin.
    """
    email = user.get("email", "")
    authority = getattr(request.app.state, "authority", None)

    if not await check_permission(email, "dockmaster", "admin", authority, settings.dockmaster_admin_emails):
        logger.warning("admin_access_denied", email=email, auth="session")
        raise HTTPException(status_code=403, detail="Access denied")

    return user


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


async def get_session_or_jwt_email(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session_cookie: Annotated[str | None, Cookie(alias="session_id")] = None,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(auto_error=False)),
    ] = None,
) -> str:
    """Info dependency: return email from session cookie or Bearer JWT.

    Tries session first, then Bearer JWT. Returns empty string if
    neither yields an email. Use alongside a router-level auth gate.
    """
    # Try session first
    store = getattr(request.app.state, "session_store", None)
    data = await resolve_session(session_cookie, store, settings.session_secret_key)
    if data:
        return data.get("email", "")

    # Try JWT
    if credentials:
        realm = getattr(request.app.state, "realm", None)
        if realm:
            try:
                claims = verify_jwt(credentials.credentials, realm)
                return claims.get("email", "")
            except ValueError:
                pass

    return ""


async def get_session_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session_cookie: Annotated[str | None, Cookie(alias="session_id")] = None,
) -> dict:
    """Info dependency: return the current session user's data.

    Calls resolve_session to extract user data from the session cookie.
    Returns an empty dict if no valid session. Use alongside a router-level
    auth gate — this dependency provides data, not auth enforcement.
    """
    store = getattr(request.app.state, "session_store", None)
    data = await resolve_session(session_cookie, store, settings.session_secret_key)
    return data or {}


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
