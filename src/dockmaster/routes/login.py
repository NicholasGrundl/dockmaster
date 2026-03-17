"""Routes: OAuth login flow — /auth/login, /auth/callback, /auth/logout, /auth/principal."""

from __future__ import annotations

import re
import uuid
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel

from dockmaster.auth.dependencies import get_session_data
from dockmaster.auth.ttl_store import TTLStore
from dockmaster.config import Settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["oauth"])

PROFILE_CLAIM_KEYS = ("email", "name", "picture", "given_name", "family_name", "locale")

# Regex for allowed CLI redirect URIs (localhost only, any port)
_LOCALHOST_RE = re.compile(r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?(?:/.*)?$")

# OAuth state TTL — 10 minutes is generous for a login flow round-trip
OAUTH_STATE_TTL = 600


def _get_signer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret_key)


def _validate_redirect_uri(uri: str | None, allowed_redirect_uris: set[str] | None = None) -> str | None:
    """Validate and return the redirect URI, or None if not provided.

    Allows localhost URIs (CLI flow) and URIs in the ALLOWED_REDIRECT_URIS allowlist
    (external service flow).
    """
    if not uri:
        return None
    # Localhost always allowed (CLI flow)
    if _LOCALHOST_RE.match(uri):
        return uri
    # Check against configured allowlist
    if allowed_redirect_uris and uri in allowed_redirect_uris:
        return uri
    raise HTTPException(
        status_code=400,
        detail="Invalid redirect_uri: not in allowlist",
    )


@router.get("/login")
async def login(
    request: Request,
    redirect_uri: str | None = None,
):
    """Redirect to Google OAuth2 authorization endpoint.

    If redirect_uri is provided (CLI flow), the callback will redirect there
    with a JWT token instead of creating a session cookie.
    """
    oauth = getattr(request.app.state, "oauth", None)
    if oauth is None:
        raise HTTPException(status_code=503, detail="OAuth not configured")

    settings: Settings = request.app.state.settings
    validated_redirect = _validate_redirect_uri(redirect_uri, settings.allowed_redirect_uris)

    oauth_state_store: TTLStore[dict] = request.app.state.oauth_state_store
    state = oauth_state_store.create({"redirect_uri": validated_redirect})

    callback_uri = str(request.url_for("callback"))
    return await oauth.google.authorize_redirect(
        request,
        callback_uri,
        state=state,
        prompt="select_account",
    )


@router.get("/callback")
async def callback(request: Request):
    """Handle Google OAuth2 callback — exchange code for tokens, create session."""
    settings: Settings = request.app.state.settings
    oauth = getattr(request.app.state, "oauth", None)
    if oauth is None:
        raise HTTPException(status_code=503, detail="OAuth not configured")

    # Validate CSRF state
    state = request.query_params.get("state")
    oauth_state_store: TTLStore[dict] = request.app.state.oauth_state_store
    state_meta = oauth_state_store.consume(state) if state else None
    if state_meta is None:
        raise HTTPException(status_code=401, detail="Invalid OAuth state")

    # Exchange code for tokens
    token_response = await oauth.google.authorize_access_token(request)
    id_token_claims = token_response.get("userinfo", {})

    # Extract email and check domain
    email = id_token_claims.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email in token response")

    domain = email.partition("@")[2]
    if domain not in settings.authorized_domains:
        logger.warning("domain_not_allowed", domain=domain, email=email)
        raise HTTPException(status_code=403, detail="Access denied")

    # Redirect flow: allowlisted URI → auth code, localhost (CLI) → direct JWT
    redirect_target = state_meta.get("redirect_uri")
    if redirect_target:
        if redirect_target in settings.allowed_redirect_uris:
            return _handle_external_callback(request, email, redirect_target, state)
        if _LOCALHOST_RE.match(redirect_target):
            return _handle_cli_callback(request, email, redirect_target)
        # Should not reach here — _validate_redirect_uri would have rejected it
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")

    # Browser flow: create session and set cookie
    session_store = getattr(request.app.state, "session_store", None)
    if session_store is None:
        raise HTTPException(status_code=503, detail="Session store not configured")

    session_id = str(uuid.uuid4())
    session_data = {k: id_token_claims[k] for k in PROFILE_CLAIM_KEYS if k in id_token_claims}

    await session_store.set(session_id, session_data, ttl=settings.session_ttl)

    # Sign session ID and set cookie
    signer = _get_signer(settings)
    signed_session_id = signer.dumps(session_id)

    response = RedirectResponse(url="/ui/", status_code=302)
    response.set_cookie(
        key="session_id",
        value=signed_session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        max_age=settings.session_ttl,
    )
    logger.info("session_created", email=email, session_id=session_id)
    return response


CLI_TOKEN_TTL = 900  # 15 minutes


def _handle_external_callback(
    request: Request,
    email: str,
    redirect_uri: str,
    state: str,
) -> RedirectResponse:
    """Generate an auth code and redirect to the external service."""
    auth_code_store = getattr(request.app.state, "auth_code_store", None)
    if auth_code_store is None:
        raise HTTPException(status_code=503, detail="Auth code store not configured")

    code = auth_code_store.create(subject=email, redirect_uri=redirect_uri)
    target = f"{redirect_uri}?{urlencode({'code': code, 'state': state})}"
    logger.info("auth_code_issued", email=email, redirect_uri=redirect_uri)
    return RedirectResponse(url=target, status_code=302)


def _handle_cli_callback(request: Request, email: str, redirect_uri: str) -> RedirectResponse:
    """Mint a short-lived Type C JWT and redirect to the CLI's localhost callback."""
    token_issuer = getattr(request.app.state, "token_issuer", None)
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Token issuer not configured")

    token = token_issuer.sign(
        subject=email,
        audience="dockmaster",
        ttl=CLI_TOKEN_TTL,
    )

    target = f"{redirect_uri}?{urlencode({'token': token})}"
    logger.info("cli_token_issued", email=email, redirect_uri=redirect_uri)
    return RedirectResponse(url=target, status_code=302)


@router.get("/logout")
async def logout(request: Request):
    """Destroy session and clear cookie."""
    settings: Settings = request.app.state.settings
    session_store = getattr(request.app.state, "session_store", None)

    # Try to read and delete the session
    cookie = request.cookies.get("session_id")
    if cookie and session_store:
        signer = _get_signer(settings)
        try:
            session_id = signer.loads(cookie)
            await session_store.delete(session_id)
            logger.info("session_destroyed", session_id=session_id)
        except BadSignature:
            logger.warning("logout_bad_signature")

    response = RedirectResponse(url="/ui/", status_code=302)
    response.delete_cookie(key="session_id", path="/")
    return response


@router.get("/principal")
async def get_principal(request: Request) -> dict:
    """Return current session profile, or {} if not authenticated."""
    settings: Settings = request.app.state.settings
    data = await get_session_data(request, settings)
    return data or {}


@router.get("/sessions")
async def get_sessions(request: Request) -> dict:
    """Return current user's active sessions, or {} if not authenticated."""
    settings: Settings = request.app.state.settings
    data = await get_session_data(request, settings)
    if not data:
        return {}

    email = data.get("email")
    if not email:
        return {}

    session_store = getattr(request.app.state, "session_store", None)
    if session_store is None:
        return {}

    from dockmaster.rbac.admin_ops import list_sessions_by_email

    return await list_sessions_by_email(session_store, email)


class CodeExchangeRequest(BaseModel):
    """Request body for POST /auth/code/exchange."""

    code: str
    redirect_uri: str


@router.post("/code/exchange")
async def code_exchange(body: CodeExchangeRequest, request: Request) -> dict:
    """Exchange an authorization code for a Type C JWT.

    The code must be valid (exists, not expired, not already used) and the
    redirect_uri must match the one used when the code was created.
    """
    auth_code_store = getattr(request.app.state, "auth_code_store", None)
    if auth_code_store is None:
        raise HTTPException(status_code=503, detail="Auth code store not configured")

    token_issuer = getattr(request.app.state, "token_issuer", None)
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Token issuer not configured")

    entry = auth_code_store.consume(body.code, redirect_uri=body.redirect_uri)
    if entry is None:
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

    token = token_issuer.sign(
        subject=entry.subject,
        audience="dockmaster",
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": token_issuer.default_ttl,
        "refresh_token": None,
    }
