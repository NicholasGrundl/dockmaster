"""Dockmaster FastAPI application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

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
from dockmaster.sessions.memory import InMemorySessionStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    settings = get_settings()
    setup_logging(settings.log_level)
    log = structlog.get_logger("dockmaster")
    log.info("starting up", log_level=settings.log_level)

    if settings.issuer:
        app.state.signer = ServiceUser(settings.issuer)
        cache = ServiceAccountKeyCache(credentials=settings.issuer, expiry=300)
        app.state.realm = ServiceRealm(key_cache=cache)
        log.info("auth singletons initialized", issuer=settings.issuer)
    else:
        app.state.signer = None
        app.state.realm = None
        log.warning("ISSUER not set — auth endpoints will return 503")

    # Session store
    app.state.session_store = InMemorySessionStore()
    log.info("session store initialized", backend="in-memory")

    # OAuth client (requires client_id)
    if settings.client_id:
        app.state.oauth = create_oauth(settings)
        log.info("oauth client initialized")
    else:
        app.state.oauth = None
        log.warning("CLIENT_ID not set — OAuth login will return 503")

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
    application.add_api_route("/", root_info, methods=["GET"], tags=["info"])
    return application


app = create_app()
