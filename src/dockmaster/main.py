"""Dockmaster FastAPI application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from dockmaster.config import get_settings
from dockmaster.logging import setup_logging
from dockmaster.routes.health import root_info, router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    settings = get_settings()
    setup_logging(settings.log_level)
    log = structlog.get_logger("dockmaster")
    log.info("starting up", log_level=settings.log_level)
    yield
    log.info("shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="Dockmaster",
        version="0.1.0",
        description="Auth microservice for fine-grained RBAC via Google services",
        lifespan=lifespan,
    )
    application.include_router(health_router, prefix="/auth")
    application.add_api_route("/", root_info, methods=["GET"], tags=["info"])
    return application


app = create_app()
