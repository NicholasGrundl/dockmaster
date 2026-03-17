"""Routes: Admin CRUD for RBAC roles and grants — /admin/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.api_core.exceptions import NotFound
from pydantic import BaseModel

from dockmaster.auth.admin import require_admin_api, require_admin_writes
from dockmaster.rbac import admin_ops
from dockmaster.rbac.admin_ops import RoleConflictError
from dockmaster.rbac.models import Grant, Role, ServiceGrants

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


class RevokeSessionResponse(BaseModel):
    revoked: bool
    session_id: str


class RevokeByEmailResponse(BaseModel):
    revoked: int
    email: str


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_admin_storage(request: Request):
    return getattr(request.app.state, "admin_storage", None)


def _get_authority(request: Request):
    return getattr(request.app.state, "authority", None)


def _get_session_store(request: Request):
    store = getattr(request.app.state, "session_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Session store not configured")
    return store


# ------------------------------------------------------------------
# Role endpoints
# ------------------------------------------------------------------


@router.get("/roles", response_model=list[str])
async def list_roles(
    request: Request,
    _admin: dict = Depends(require_admin_api),
):
    """List all role names."""
    storage = _get_admin_storage(request)
    return await admin_ops.list_roles(storage)


@router.get("/roles/{name}", response_model=Role)
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


@router.post("/roles", status_code=201, response_model=Role)
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


@router.put("/roles/{name}", response_model=Role)
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


@router.get("/grants", response_model=list[str])
async def list_grants(
    request: Request,
    _admin: dict = Depends(require_admin_api),
):
    """List all service names that have grants."""
    storage = _get_admin_storage(request)
    return await admin_ops.list_service_grants(storage)


@router.get("/grants/{service}", response_model=ServiceGrants)
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


@router.post("/grants/{service}", response_model=ServiceGrants)
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


# ------------------------------------------------------------------
# Session endpoints
# ------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    request: Request,
    _admin: dict = Depends(require_admin_api),
):
    """List all active sessions."""
    store = _get_session_store(request)
    return await admin_ops.list_sessions(store)


@router.get("/sessions/email/{email}")
async def list_sessions_by_email(
    request: Request,
    email: str,
    _admin: dict = Depends(require_admin_api),
):
    """List sessions for a specific user email."""
    store = _get_session_store(request)
    return await admin_ops.list_sessions_by_email(store, email)


@router.delete("/sessions/id/{session_id}", response_model=RevokeSessionResponse)
async def revoke_session(
    request: Request,
    session_id: str,
    _admin: dict = Depends(require_admin_api),
):
    """Revoke a single session by ID."""
    store = _get_session_store(request)
    revoked = await admin_ops.revoke_session(store, session_id)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"revoked": True, "session_id": session_id}


@router.delete("/sessions/email/{email}", response_model=RevokeByEmailResponse)
async def revoke_sessions_by_email(
    request: Request,
    email: str,
    _admin: dict = Depends(require_admin_api),
):
    """Revoke all sessions for a user email."""
    store = _get_session_store(request)
    count = await admin_ops.revoke_sessions_by_email(store, email)
    return {"revoked": count, "email": email}
