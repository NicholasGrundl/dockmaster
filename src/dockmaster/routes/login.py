"""Routes: OAuth login flow — /auth/login, /auth/callback, /auth/logout, /auth/principal."""

import uuid
from urllib.parse import urlencode

import structlog
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel

from dockmaster.auth.dependencies import resolve_session
from dockmaster.auth.oauth_flow_store import LoginTicket, OAuthFlowStore, OAuthState
from dockmaster.config import Settings, get_settings
from dockmaster.state import get_flow_store

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["oauth"])

# Includes "email" because Google's userinfo response puts it here (not in sub).
# service.py's PROFILE_CLAIM_KEYS omits "email" — there it's already the sub claim.
PROFILE_CLAIM_KEYS = ("email", "name", "picture", "given_name", "family_name", "locale")


def _get_signer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret_key)


def _validate_cookie_return_to(uri: str | None) -> str:
    """Validate return_to for cookie flow — relative paths only.

    Rejects absolute URLs to prevent open redirects. The browser will be
    redirected to this path on the same origin after login.
    Returns /ui/ if not provided or invalid.
    """
    if not uri:
        return "/ui/"
    if uri.startswith("/") and not uri.startswith("//"):
        return uri
    return "/ui/"


def _validate_external_return_to(
    uri: str | None,
    blocklist: set[str] | None = None,
) -> str | None:
    """Validate return_to for refresh token flow.

    The external app controls how it uses this value — dockmaster passes it
    through in the exchange response. Rejects values in the blocklist.
    Returns None if not provided.
    """
    if not uri:
        return None
    if blocklist and uri in blocklist:
        return None
    return uri


def _validate_redirect_uri(uri: str | None, allowed_redirect_uris: set[str] | None = None) -> str | None:
    """Validate and return the redirect URI, or None if not provided.

    Only accepts URIs in the ALLOWED_REDIRECT_URIS allowlist (external service flow).
    CLI flow uses /auth/cli/login instead.
    """
    if not uri:
        return None
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
    settings: Annotated[Settings, Depends(get_settings)],
    flow_store: Annotated[OAuthFlowStore | None, Depends(get_flow_store)],
    redirect_uri: str | None = None,
    return_to: str | None = None,
):
    """Redirect to Google OAuth2 authorization endpoint.

    If redirect_uri is provided (external app flow), the callback will redirect
    there with an auth code. Otherwise, creates a session cookie (browser flow).
    CLI flow uses /auth/cli/login instead.

    return_to is an optional post-login redirect target:
    - Cookie flow: browser redirects to this relative path after login (default /ui/)
    - Refresh token flow: passed through in the exchange response for the app to use
    """
    oauth = getattr(request.app.state, "oauth", None)
    if oauth is None:
        raise HTTPException(status_code=503, detail="OAuth not configured")
    if flow_store is None:
        raise HTTPException(status_code=503, detail="Flow store not configured")

    validated_redirect = _validate_redirect_uri(redirect_uri, settings.allowed_redirect_uris)
    state = flow_store.create_oauth_state(redirect_uri=validated_redirect, return_to=return_to)

    # GCP OAuth config: /auth/login/callback must be an authorized redirect URI
    # in the Google Cloud Console OAuth client configuration.
    callback_uri = str(request.url_for("login_callback"))
    return await oauth.google.authorize_redirect(
        request,
        callback_uri,
        state=state,
        prompt="select_account",
    )


@router.get("/login/callback")
async def login_callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    flow_store: Annotated[OAuthFlowStore | None, Depends(get_flow_store)],
):
    """Handle Google OAuth2 callback — exchange code for tokens, create session."""
    oauth = getattr(request.app.state, "oauth", None)
    if oauth is None:
        raise HTTPException(status_code=503, detail="OAuth not configured")
    if flow_store is None:
        raise HTTPException(status_code=503, detail="Flow store not configured")

    # Validate CSRF state
    state = request.query_params.get("state")
    state_entry = flow_store.consume(state) if state else None
    if not isinstance(state_entry, OAuthState):
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

    # Redirect flow: allowlisted URI → login ticket
    redirect_target = state_entry.redirect_uri
    profile_claims = {k: id_token_claims[k] for k in PROFILE_CLAIM_KEYS if k in id_token_claims}
    if redirect_target:
        validated_return_to = _validate_external_return_to(state_entry.return_to)
        return _handle_external_callback(
            flow_store,
            email,
            redirect_target,
            state,
            profile_claims,
            return_to=validated_return_to,
        )

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

    cookie_return_to = _validate_cookie_return_to(state_entry.return_to)
    response = RedirectResponse(url=cookie_return_to, status_code=302)
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


def _handle_external_callback(
    flow_store: OAuthFlowStore,
    email: str,
    redirect_uri: str,
    state: str,
    profile: dict | None = None,
    return_to: str | None = None,
) -> RedirectResponse:
    """Generate a login ticket and redirect to the external service."""
    code = flow_store.create_login_ticket(
        subject=email,
        redirect_uri=redirect_uri,
        profile=profile or {},
        return_to=return_to,
    )
    target = f"{redirect_uri}?{urlencode({'code': code, 'state': state})}"
    logger.info("login_ticket_issued", email=email, redirect_uri=redirect_uri)
    return RedirectResponse(url=target, status_code=302)


@router.post("/logout")
async def logout(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Destroy session and clear cookie."""
    session_store = getattr(request.app.state, "session_store", None)
    signer = _get_signer(settings)

    # Try cookie first
    cookie = request.cookies.get("session_id")
    if cookie and session_store:
        try:
            session_id = signer.loads(cookie)
            await session_store.delete(session_id)
            logger.info("session_destroyed", session_id=session_id)
        except BadSignature:
            logger.warning("logout_bad_signature")

    # Try refresh_token from body
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except Exception:
        refresh_token = None

    if refresh_token and session_store:
        try:
            session_id = signer.loads(refresh_token)
            await session_store.delete(session_id)
            logger.info("session_destroyed", session_id=session_id)
        except BadSignature:
            logger.warning("logout_bad_refresh_token_signature")

    response = RedirectResponse(url="/ui/", status_code=302)
    response.delete_cookie(key="session_id", path="/")
    return response


@router.get("/principal")
async def get_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Return current session profile, or {} if not authenticated."""
    store = getattr(request.app.state, "session_store", None)
    cookie = request.cookies.get("session_id")
    data = await resolve_session(cookie, store, settings.session_secret_key)
    return data or {}


@router.get("/sessions")
async def get_sessions(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Return current user's active sessions, or {} if not authenticated."""
    store = getattr(request.app.state, "session_store", None)
    cookie = request.cookies.get("session_id")
    data = await resolve_session(cookie, store, settings.session_secret_key)
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


class LoginTicketExchangeRequest(BaseModel):
    """Request body for POST /auth/login/exchange."""

    code: str
    redirect_uri: str


class LoginTicketExchangeResponse(BaseModel):
    """Response for POST /auth/login/exchange."""

    refresh_token: str
    profile: dict
    return_to: str | None = None


@router.post("/login/exchange", response_model=LoginTicketExchangeResponse)
async def login_exchange(
    body: LoginTicketExchangeRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    flow_store: Annotated[OAuthFlowStore | None, Depends(get_flow_store)],
) -> LoginTicketExchangeResponse:
    """Exchange a login ticket for a session refresh token + profile.

    Validates the login ticket, creates a server-side session, and returns a
    signed refresh_token (for cross-domain clients) plus the user's profile.
    """
    if flow_store is None:
        raise HTTPException(status_code=503, detail="Flow store not configured")

    session_store = getattr(request.app.state, "session_store", None)
    if session_store is None:
        raise HTTPException(status_code=503, detail="Session store not configured")

    entry = flow_store.consume(body.code)
    if not isinstance(entry, LoginTicket) or entry.redirect_uri != body.redirect_uri:
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

    # Create session
    session_id = str(uuid.uuid4())
    session_data = {"email": entry.subject, **entry.profile}
    await session_store.set(session_id, session_data, ttl=settings.session_ttl)

    # Sign session ID as refresh token
    signer = _get_signer(settings)
    refresh_token = signer.dumps(session_id)

    logger.info("login_code_session_created", email=entry.subject, session_id=session_id)

    return LoginTicketExchangeResponse(
        refresh_token=refresh_token,
        profile=entry.profile,
        return_to=entry.return_to,
    )
