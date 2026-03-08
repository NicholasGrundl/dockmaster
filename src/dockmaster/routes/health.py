"""Health and service info endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

import dockmaster


class HealthResponse(BaseModel):
    service: str = "dockmaster"
    status: str = "ok"


class ServiceInfo(BaseModel):
    service: str = "dockmaster"
    version: str = dockmaster.__version__
    health: str = "/auth/health"
    docs: str = "/docs"


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


async def root_info() -> ServiceInfo:
    return ServiceInfo()
