"""Health and service info endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

import dockmaster


class HealthResponse(BaseModel):
    service: str = "dockmaster"
    status: str = "ok"


class ServiceInfo(BaseModel):
    service: str = "dockmaster"
    version: str = dockmaster.__version__
    health: str = "/auth/health"
    docs: str | None = None


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


async def root_info(request: Request) -> ServiceInfo:
    docs_url = request.app.docs_url
    return ServiceInfo(docs=docs_url)
