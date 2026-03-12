"""Routes: OAuth login flow — /auth/login, /auth/callback, /auth/logout, /auth/principal."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer

from dockmaster.config import Settings, get_settings

logger = structlog.get_logger("dockmaster.login")

router = APIRouter()

PROFILE_CLAIM_KEYS = ("email", "name", "picture", "given_name", "family_name", "locale")

# In-memory CSRF state store (maps state → True). Consumed on callback.
_pending_states: dict[str, bool] = {}


def _get_signer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret_key)


@router.get("/login")
async def login(request: Request, settings: Settings = Depends(get_settings)):
    """Redirect to Google OAuth2 authorization endpoint."""
    oauth = getattr(request.app.state, "oauth", None)
    if oauth is None:
        raise HTTPException(status_code=503, detail="OAuth not configured")

    state = str(uuid.uuid4())
    _pending_states[state] = True

    redirect_uri = str(request.url_for("callback"))
    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
        state=state,
        prompt="select_account",
    )


@router.get("/callback")
async def callback(request: Request, settings: Settings = Depends(get_settings)):
    """Handle Google OAuth2 callback — exchange code for tokens, create session."""
    oauth = getattr(request.app.state, "oauth", None)
    if oauth is None:
        raise HTTPException(status_code=503, detail="OAuth not configured")

    # Validate CSRF state
    state = request.query_params.get("state")
    if not state or state not in _pending_states:
        raise HTTPException(status_code=401, detail="Invalid OAuth state")
    del _pending_states[state]

    # Exchange code for tokens
    token_response = await oauth.google.authorize_access_token(request)
    id_token_claims = token_response.get("userinfo", {})

    # Extract email and check domain
    email = id_token_claims.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email in token response")

    domain = email.partition("@")[2]
    if domain not in settings.authorized_domains:
        raise HTTPException(status_code=403, detail=f"Domain not allowed: {domain}")

    # Create session
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


@router.get("/logout")
async def logout(request: Request, settings: Settings = Depends(get_settings)):
    """Destroy session and clear cookie."""
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
async def get_principal(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    """Return current session profile, or {} if not authenticated."""
    session_store = getattr(request.app.state, "session_store", None)
    if session_store is None:
        return {}

    cookie = request.cookies.get("session_id")
    if not cookie:
        return {}

    signer = _get_signer(settings)
    try:
        session_id = signer.loads(cookie)
    except BadSignature:
        return {}

    data = await session_store.get(session_id)
    return data or {}
