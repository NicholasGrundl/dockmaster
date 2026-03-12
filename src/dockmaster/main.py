"""Dockmaster FastAPI application."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from dockmaster.auth.jwt_signer import ServiceUser
from dockmaster.auth.jwt_verifier import ServiceRealm
from dockmaster.auth.key_cache import ServiceAccountKeyCache
from dockmaster.auth.oauth import create_oauth
from dockmaster.config import get_settings
from dockmaster.logging import setup_logging
from dockmaster.routes.claims import router as claims_router
from dockmaster.routes.exchange import router as exchange_router
from dockmaster.routes.health import root_info, router as health_router
from dockmaster.routes.keys import router as keys_router
from dockmaster.routes.login import router as login_router
from dockmaster.routes.refresh import router as refresh_router
from dockmaster.routes.ui import protected_router as ui_protected_router
from dockmaster.routes.ui import public_router as ui_public_router
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
    # TODO(phase5): Research whether broad cloud-platform scope is appropriate
    # vs narrower scopes. See https://developers.google.com/identity/protocols/oauth2/scopes
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
    settings = get_settings()
    setup_logging(settings.log_level)
    log = structlog.get_logger("dockmaster")
    log.info("starting up", log_level=settings.log_level)

    # --- Load SA key (shared across all GCP consumers) ---
    sa_key_data = _load_sa_key(settings.sa_key_file, log)

    # --- JWT signer (requires SA key — no ADC fallback, needs private key) ---
    if sa_key_data:
        app.state.signer = ServiceUser(sa_key_data)
        log.info("jwt_signer_initialized", email=sa_key_data.get("client_email"))
    else:
        app.state.signer = None
        log.warning("SA_KEY_FILE not set — JWT signing disabled (auth endpoints will return 503)")

    # --- Key cache + JWT verifier (SA key preferred, ADC fallback for IAM calls) ---
    cache = ServiceAccountKeyCache(
        credentials=sa_key_data,
        project=settings.secrets_project,
        expiry=300,
    )
    app.state.realm = ServiceRealm(key_cache=cache)
    log.info("jwt_verifier_initialized", auth_source="sa_key" if sa_key_data else "adc")

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
    else:
        app.state.secrets_storage = None
        log.warning("SECRETS_PROJECT not set — Secret Manager lookups will return 503")

    yield
    log.info("shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    application = FastAPI(
        title="Dockmaster",
        version="0.1.0",
        description="Auth microservice for fine-grained RBAC via Google services",
        lifespan=lifespan,
    )
    # Starlette SessionMiddleware is required by Authlib for OAuth state management
    application.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
    application.include_router(health_router, prefix="/auth")
    application.include_router(keys_router, prefix="/auth")
    application.include_router(claims_router, prefix="/auth")
    application.include_router(exchange_router, prefix="/auth")
    application.include_router(login_router, prefix="/auth")
    application.include_router(refresh_router, prefix="/auth")
    application.include_router(ui_public_router, prefix="/ui")
    application.include_router(ui_protected_router, prefix="/ui")
    application.add_api_route("/", root_info, methods=["GET"], tags=["info"])
    return application


app = create_app()
