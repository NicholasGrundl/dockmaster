"""Routes: CLI auth — /auth/cli/login, /auth/cli/callback, /auth/cli/token.

CLI OAuth flow: localhost-only redirect_uri, direct JWT issuance (no sessions).
Token endpoint: exchange a valid dockmaster Bearer JWT for a Type C JWT.

Auth pattern: Mixed. CLI OAuth routes (login, callback) are public entry points.
``POST /auth/cli/token`` uses ``allow_jwt`` at route level. Uses ``get_flow_store``,
``get_oauth``, and ``get_token_issuer`` state bridges.
"""

import re
from typing import Annotated
from urllib.parse import urlencode

import structlog
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from dockmaster.auth.dependencies import allow_jwt, get_jwt_claims
from dockmaster.auth.jwt_signers import EphemeralKeypairSigner
from dockmaster.auth.oauth_flow_store import OAuthFlowStore, OAuthState
from dockmaster.config import Settings, get_settings
from dockmaster.state import get_flow_store, get_oauth, get_token_issuer

logger = structlog.get_logger(__name__)

# No router-level auth gate — CLI OAuth routes are public entry points.
# allow_jwt is applied at route-level on POST /cli/token only.
router = APIRouter(tags=["cli"])

# Regex for allowed CLI redirect URIs (localhost only, any port)
_LOCALHOST_RE = re.compile(r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?(?:/.*)?$")

# CLI tokens are short-lived (15 minutes)
CLI_TOKEN_TTL = 900


def _validate_cli_redirect_uri(uri: str | None) -> str:
    """Validate that a redirect URI is a localhost address.

    CLI flow only allows localhost redirect URIs.
    Raises 400 if missing or not localhost.
    """
    if not uri:
        raise HTTPException(
            status_code=400,
            detail="redirect_uri is required for CLI login",
        )
    if not _LOCALHOST_RE.match(uri):
        raise HTTPException(
            status_code=400,
            detail="CLI login only accepts localhost redirect URIs",
        )
    return uri


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: None = None


@router.get("/cli/login")
async def cli_login(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    flow_store: Annotated[OAuthFlowStore | None, Depends(get_flow_store)],
    oauth: Annotated[OAuth | None, Depends(get_oauth)],
    redirect_uri: str | None = None,
):
    """Start CLI OAuth flow — redirect to Google with localhost callback.

    The redirect_uri must be a localhost address (CLI's local HTTP server).
    After Google auth, the callback at /auth/cli/callback mints a JWT and
    redirects back to the CLI's localhost server.
    """
    if oauth is None:
        raise HTTPException(status_code=503, detail="OAuth not configured")
    if flow_store is None:
        raise HTTPException(status_code=503, detail="Flow store not configured")

    validated_redirect = _validate_cli_redirect_uri(redirect_uri)
    state = flow_store.create_oauth_state(redirect_uri=validated_redirect)

    # GCP OAuth config: /auth/cli/callback must be an authorized redirect URI
    # in the Google Cloud Console OAuth client configuration.
    callback_uri = str(request.url_for("cli_callback"))
    return await oauth.google.authorize_redirect(
        request,
        callback_uri,
        state=state,
        prompt="select_account",
    )


@router.get("/cli/callback")
async def cli_callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    flow_store: Annotated[OAuthFlowStore | None, Depends(get_flow_store)],
    oauth: Annotated[OAuth | None, Depends(get_oauth)],
    token_issuer: Annotated[EphemeralKeypairSigner | None, Depends(get_token_issuer)],
):
    """Handle Google OAuth callback for CLI flow.

    Validates CSRF state, exchanges Google auth code for tokens,
    checks email domain, mints a short-lived JWT, and redirects
    to the CLI's localhost server with the token.
    """
    if oauth is None:
        raise HTTPException(status_code=503, detail="OAuth not configured")
    if flow_store is None:
        raise HTTPException(status_code=503, detail="Flow store not configured")

    # Validate CSRF state
    state = request.query_params.get("state")
    state_entry = flow_store.consume(state) if state else None
    if not isinstance(state_entry, OAuthState):
        raise HTTPException(status_code=401, detail="Invalid OAuth state")

    redirect_target = state_entry.redirect_uri
    if not redirect_target or not _LOCALHOST_RE.match(redirect_target):
        raise HTTPException(status_code=400, detail="Invalid CLI redirect URI in state")

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

    # Mint short-lived JWT and redirect to CLI's localhost server
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Token issuer not configured")

    token = token_issuer.sign(
        subject=email,
        audience="dockmaster",
        ttl=CLI_TOKEN_TTL,
    )

    # Token is passed as a query parameter because HTTP 302 redirects cannot carry
    # a POST body. This is standard for CLI OAuth flows (gcloud, gh auth, etc.).
    # Risks (browser history, server logs, Referer leakage) are mitigated by:
    #   - Target is always localhost (no proxies/external servers logging URLs)
    #   - JWT has a 15-minute TTL
    #   - CLI's local HTTP server processes the token and shuts down immediately
    # If stronger isolation is needed, consider a polling pattern (see backlog).
    target = f"{redirect_target}?{urlencode({'token': token})}"
    logger.info("cli_token_issued", email=email, redirect_uri=redirect_target)
    return RedirectResponse(url=target, status_code=302)


@router.post("/cli/token", response_model=TokenResponse, dependencies=[Depends(allow_jwt)])
async def issue_cli_token(
    request: Request,
    claims: Annotated[dict, Depends(get_jwt_claims)],
    token_issuer: Annotated[EphemeralKeypairSigner | None, Depends(get_token_issuer)],
) -> TokenResponse:
    """Issue a Type C JWT for a target service.

    Auth: Bearer JWT (verified by allow_jwt gate at route level).
    Query params: service (required) — the target service audience.
    """
    email = claims.get("email", "")
    if token_issuer is None:
        raise HTTPException(status_code=503, detail="Token issuer not configured")

    service = request.query_params.get("service")
    if not service:
        raise HTTPException(status_code=400, detail="The service query parameter is required")

    access_token = token_issuer.sign(
        subject=email,
        audience=service,
    )

    logger.info("cli_token_issued", email=email, service=service)

    return TokenResponse(
        access_token=access_token,
        expires_in=token_issuer.default_ttl,
    )
