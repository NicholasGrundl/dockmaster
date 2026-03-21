"""Dockmaster FastAPI application."""


import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from dockmaster.middleware import RequireProxyHeadersMiddleware, SecurityHeadersMiddleware

from dockmaster.auth.jwt_signers import EphemeralKeypairSigner, ServiceAccountSigner
from dockmaster.auth.jwt_verifier import ServiceRealm
from dockmaster.auth.key_cache import EphemeralKeyCache, ServiceAccountKeyCache
from dockmaster.auth.auth_code import AuthCodeStore
from dockmaster.auth.ttl_store import TTLStore
from dockmaster.auth.oauth import create_oauth
from dockmaster.config import Settings, create_settings, session_secret_was_auto_generated
from dockmaster.logging import setup_logging
from dockmaster.routes.claims import router as claims_router
from dockmaster.routes.exchange import router as exchange_router
from dockmaster.routes.health import root_info, router as health_router
from dockmaster.routes.keys import router as keys_router
from dockmaster.routes.login import router as login_router
from dockmaster.routes.admin import router as admin_router
from dockmaster.routes.permissions import router as permissions_router
from dockmaster.routes.token import router as token_router
from dockmaster.routes.session import router as session_router
from dockmaster.routes.service import router as service_router
from dockmaster.routes.cli_routes import router as cli_router
from dockmaster.routes.admin_ui import router as admin_ui_router
from dockmaster.routes.ui import router as ui_router
from dockmaster.sessions.memory import InMemorySessionStore
from dockmaster.ui.config import load_ui_config


def _load_sa_key(path: str | None, log: structlog.stdlib.BoundLogger) -> dict | None:
    """Load SA key JSON from file path. Returns None if not configured or missing."""
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text())
        log.info("sa_key_loaded", email=data.get("client_email"), key_id=data.get("private_key_id"))
        return data
    except FileNotFoundError:
        log.error("sa_key_file_not_found", path=path)
        return None


def _build_gcp_credentials(sa_key_data: dict | None, log: structlog.stdlib.BoundLogger):
    """Build GCP credentials from SA key data, or fall back to ADC.

    Returns a google.auth.credentials.Credentials instance.
    """
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]

    if sa_key_data:
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_info(sa_key_data, scopes=scopes)
        log.info("gcp_credentials_from_sa_key", email=sa_key_data.get("client_email"))
        return creds

    import google.auth

    creds, project = google.auth.default(scopes=scopes)
    log.info("gcp_credentials_from_adc", project=project)
    return creds


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    settings = app.state.settings
    setup_logging(
        settings.log_level,
        log_file=settings.log_file,
        log_file_max_bytes=settings.log_file_max_bytes,
        log_file_backup_count=settings.log_file_backup_count,
    )
    log = structlog.get_logger(__name__)
    log.info("starting up", log_level=settings.log_level, log_file=settings.log_file)

    if session_secret_was_auto_generated():
        log.warning(
            "SESSION_SECRET_KEY not set — using auto-generated key. "
            "Sessions will not survive restarts. "
            "Generate a stable key with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )

    # --- Load SA key (shared across all GCP consumers) ---
    sa_key_data = _load_sa_key(settings.sa_key_file, log)

    # --- JWT signer (requires SA key — no ADC fallback, needs private key) ---
    if sa_key_data:
        app.state.signer = ServiceAccountSigner(sa_key_data)
        log.info("sa_signer_initialized", email=sa_key_data.get("client_email"))
    else:
        app.state.signer = None
        log.warning("SA_KEY_FILE not set — JWT signing disabled (auth endpoints will return 503)")

    # --- Ephemeral token issuer (always available — generates keypair in memory) ---
    app.state.token_issuer = EphemeralKeypairSigner(ttl=settings.dockmaster_token_ttl)
    log.info("token_issuer_initialized", kid=app.state.token_issuer.current_kid)

    # --- Key caches + JWT verifier ---
    key_caches: list = []

    # Ephemeral key cache (local, fast — checked first)
    registry_path = settings.jwks_registry_path
    if registry_path is None:
        from platformdirs import user_data_dir

        registry_path = str(Path(user_data_dir("dockmaster")) / "jwks-registry.json")
    ephemeral_cache = EphemeralKeyCache(
        kid=app.state.token_issuer.current_kid,
        public_jwk=app.state.token_issuer.current_public_jwk,
        registry_path=registry_path,
    )
    key_caches.append(ephemeral_cache)
    log.info("ephemeral_key_cache_initialized", registry_path=registry_path)

    # SA key cache (GCP IAM + Google OIDC — checked second)
    sa_cache = ServiceAccountKeyCache(
        credentials=sa_key_data,
        project=settings.secrets_project,
        expiry=300,
    )
    key_caches.append(sa_cache)

    app.state.realm = ServiceRealm(key_cache=key_caches)
    log.info("jwt_verifier_initialized", num_caches=len(key_caches))

    # --- Auth code store (for OAuth auth code flow with external redirects) ---
    app.state.auth_code_store = AuthCodeStore(ttl=300)
    log.info("auth_code_store_initialized", ttl=300)

    # --- OAuth state store (CSRF state tokens for login flow) ---
    from dockmaster.routes.login import OAUTH_STATE_TTL

    app.state.oauth_state_store = TTLStore[dict](ttl=OAUTH_STATE_TTL)
    log.info("oauth_state_store_initialized", ttl=OAUTH_STATE_TTL)

    # --- UI config ---
    app.state.ui_config = load_ui_config(settings.ui_config_path)

    # --- Session store ---
    app.state.session_store = InMemorySessionStore()
    log.info("session_store_initialized", backend="in-memory")

    # --- OAuth client (requires client_id) ---
    if settings.client_id:
        app.state.oauth = create_oauth(settings)
        log.info("oauth_client_initialized")
    else:
        app.state.oauth = None
        log.warning("CLIENT_ID not set — OAuth login will return 503")

    # --- Secrets storage (SA key preferred, ADC fallback) ---
    if settings.secrets_project:
        from google.cloud.secretmanager_v1 import SecretManagerServiceClient

        from dockmaster.rbac.storage import SecretsStorage

        gcp_creds = _build_gcp_credentials(sa_key_data, log)
        sm_client = SecretManagerServiceClient(credentials=gcp_creds)
        app.state.secrets_storage = SecretsStorage(client=sm_client, project=settings.secrets_project)
        log.info("secrets_storage_initialized", project=settings.secrets_project)

        from dockmaster.rbac.authority import Authority

        app.state.authority = Authority(
            storage=app.state.secrets_storage,
            cache_ttl=settings.rbac_cache_ttl,
        )
        log.info("rbac_authority_initialized", cache_ttl=settings.rbac_cache_ttl)
    else:
        app.state.secrets_storage = None
        app.state.authority = None
        log.warning("SECRETS_PROJECT not set — Secret Manager lookups will return 503")

    # --- Admin storage (separate SA with SM write permissions) ---
    admin_sa_key_data = _load_sa_key(settings.admin_sa_key_file, log)
    if admin_sa_key_data and settings.secrets_project:
        from google.cloud.secretmanager_v1 import SecretManagerServiceClient as SMClient

        from dockmaster.rbac.storage import AdminSecretsStorage

        admin_creds = _build_gcp_credentials(admin_sa_key_data, log)
        admin_sm_client = SMClient(credentials=admin_creds)
        app.state.admin_storage = AdminSecretsStorage(client=admin_sm_client, project=settings.secrets_project)
        log.info(
            "admin_storage_initialized",
            project=settings.secrets_project,
            email=admin_sa_key_data.get("client_email"),
        )
    else:
        app.state.admin_storage = None
        if not settings.admin_sa_key_file:
            log.warning("ADMIN_SA_KEY_FILE not set — RBAC write operations will return 503")

    yield
    log.info("shutting down")


def setup_middleware(app: FastAPI, settings: Settings) -> None:
    """Configure all application middleware.

    Order matters — Starlette executes middleware in reverse-add order
    (last added runs first on the request path).
    """
    # Proxy header check — must be outermost (first added = last to run on request)
    if settings.require_proxy_headers:
        app.add_middleware(RequireProxyHeadersMiddleware)
    # Security headers — safe defaults regardless of reverse proxy config
    if settings.security_headers:
        app.add_middleware(SecurityHeadersMiddleware)
    # CORS — allow configured origins for SPA cross-origin access
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=sorted(settings.allowed_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=True,
        )
    # Starlette SessionMiddleware — creates a separate "session" cookie used internally
    # by Authlib during the OAuth redirect flow. This is distinct from the application's
    # own "session_id" cookie (server-side sessions via InMemorySessionStore + itsdangerous).
    # Both cookies are signed with session_secret_key. The Starlette session cookie may
    # be removable now that OAuth CSRF state is managed by TTLStore (see S-005/S-012),
    # but requires verifying Authlib doesn't use it during token exchange.
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = create_settings()
    application = FastAPI(
        title="Dockmaster",
        version="0.1.0",
        description="Auth microservice for fine-grained RBAC via Google services",
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    application.state.settings = settings
    setup_middleware(application, settings)
    application.include_router(health_router, prefix="/auth")
    application.include_router(keys_router, prefix="/auth")
    application.include_router(claims_router, prefix="/auth")
    application.include_router(exchange_router, prefix="/auth")
    application.include_router(login_router, prefix="/auth")
    application.include_router(permissions_router, prefix="/auth")
    application.include_router(token_router, prefix="/auth")
    application.include_router(session_router, prefix="/auth")
    application.include_router(service_router, prefix="/auth")
    application.include_router(cli_router, prefix="/auth")
    application.include_router(admin_router, prefix="/admin")
    application.include_router(ui_router, prefix="/ui")
    application.include_router(admin_ui_router, prefix="/ui")
    application.add_api_route("/", root_info, methods=["GET"], tags=["info"])
    return application


app = create_app()
