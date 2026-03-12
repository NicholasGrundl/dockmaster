"""Routes: Admin CRUD for RBAC roles and grants — /admin/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.api_core.exceptions import NotFound
from pydantic import BaseModel

from dockmaster.auth.admin import require_admin_api, require_admin_writes
from dockmaster.rbac import admin_ops
from dockmaster.rbac.admin_ops import RoleConflictError
from dockmaster.rbac.models import Grant

router = APIRouter(tags=["admin"])


# ------------------------------------------------------------------
# Request/response models
# ------------------------------------------------------------------


class CreateRoleRequest(BaseModel):
    name: str
    permissions: list[str]


class UpdateRoleRequest(BaseModel):
    permissions: list[str]


class PutGrantsRequest(BaseModel):
    grants: list[Grant]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_admin_storage(request: Request):
    return getattr(request.app.state, "admin_storage", None)


def _get_authority(request: Request):
    return getattr(request.app.state, "authority", None)


# ------------------------------------------------------------------
# Role endpoints
# ------------------------------------------------------------------


@router.get("/roles")
async def list_roles(
    request: Request,
    _admin: dict = Depends(require_admin_api),
):
    """List all role names."""
    storage = _get_admin_storage(request)
    return await admin_ops.list_roles(storage)


@router.get("/roles/{name}")
async def get_role(
    request: Request,
    name: str,
    _admin: dict = Depends(require_admin_api),
):
    """Get a single role by name."""
    storage = _get_admin_storage(request)
    try:
        role = await admin_ops.get_role(storage, name)
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Role '{name}' not found")
    return role.model_dump()


@router.post("/roles", status_code=201)
async def create_role(
    request: Request,
    body: CreateRoleRequest,
    _admin: dict = Depends(require_admin_api),
    _writes: None = Depends(require_admin_writes),
):
    """Create a new role."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)
    try:
        role = await admin_ops.create_role(storage, authority, body.name, body.permissions)
    except RoleConflictError:
        raise HTTPException(status_code=409, detail=f"Role '{body.name}' already exists")
    return role.model_dump()


@router.put("/roles/{name}")
async def update_role(
    request: Request,
    name: str,
    body: UpdateRoleRequest,
    _admin: dict = Depends(require_admin_api),
    _writes: None = Depends(require_admin_writes),
):
    """Update a role's permissions."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)
    role = await admin_ops.update_role(storage, authority, name, body.permissions)
    return role.model_dump()


@router.delete("/roles/{name}", status_code=204)
async def delete_role(
    request: Request,
    name: str,
    _admin: dict = Depends(require_admin_api),
    _writes: None = Depends(require_admin_writes),
):
    """Delete a role."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)
    try:
        await admin_ops.delete_role(storage, authority, name)
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Role '{name}' not found")
    return Response(status_code=204)


# ------------------------------------------------------------------
# Grant endpoints
# ------------------------------------------------------------------


@router.get("/grants")
async def list_grants(
    request: Request,
    _admin: dict = Depends(require_admin_api),
):
    """List all service names that have grants."""
    storage = _get_admin_storage(request)
    return await admin_ops.list_service_grants(storage)


@router.get("/grants/{service}")
async def get_grants(
    request: Request,
    service: str,
    _admin: dict = Depends(require_admin_api),
):
    """Get grants for a service."""
    storage = _get_admin_storage(request)
    try:
        sg = await admin_ops.get_service_grants(storage, service)
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Grants for '{service}' not found")
    return sg.model_dump()


@router.post("/grants/{service}")
async def put_grants(
    request: Request,
    service: str,
    body: PutGrantsRequest,
    _admin: dict = Depends(require_admin_api),
    _writes: None = Depends(require_admin_writes),
):
    """Create or replace grants for a service."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)
    sg = await admin_ops.put_service_grants(storage, authority, service, body.grants)
    return sg.model_dump()


@router.delete("/grants/{service}", status_code=204)
async def delete_grants(
    request: Request,
    service: str,
    _admin: dict = Depends(require_admin_api),
    _writes: None = Depends(require_admin_writes),
):
    """Delete all grants for a service."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)
    try:
        await admin_ops.delete_service_grants(storage, authority, service)
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Grants for '{service}' not found")
    return Response(status_code=204)
