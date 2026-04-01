"""Routes: Admin CRUD for RBAC roles and grants — /admin/*."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from google.api_core.exceptions import NotFound
from pydantic import BaseModel

from dockmaster.auth.dependencies import allow_jwt_admin, needs_admin_storage, needs_session_store
from dockmaster.rbac import admin_ops
from dockmaster.rbac.admin_ops import RoleConflictError
from dockmaster.rbac.authority import Authority
from dockmaster.rbac.models import Grant, Role, ServiceGrants
from dockmaster.rbac.storage import AdminSecretsStorage
from dockmaster.sessions.protocol import SessionStore
from dockmaster.state import get_admin_storage, get_authority, get_session_store

router = APIRouter(
    tags=["admin-api"],
    dependencies=[Depends(allow_jwt_admin)],
)


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
# Role endpoints
# ------------------------------------------------------------------


@router.get("/roles", response_model=list[str])
async def list_roles(
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
):
    """List all role names."""
    return await admin_ops.list_roles(storage)


@router.get("/roles/{name}", response_model=Role)
async def get_role(
    name: str,
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
):
    """Get a single role by name."""
    try:
        role = await admin_ops.get_role(storage, name)
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Role '{name}' not found")
    return role.model_dump()


@router.post("/roles", status_code=201, response_model=Role)
async def create_role(
    body: CreateRoleRequest,
    _writes: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
):
    """Create a new role."""
    try:
        role = await admin_ops.create_role(storage, authority, body.name, body.permissions)
    except RoleConflictError:
        raise HTTPException(status_code=409, detail=f"Role '{body.name}' already exists")
    return role.model_dump()


@router.put("/roles/{name}", response_model=Role)
async def update_role(
    name: str,
    body: UpdateRoleRequest,
    _writes: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
):
    """Update a role's permissions."""
    role = await admin_ops.update_role(storage, authority, name, body.permissions)
    return role.model_dump()


@router.delete("/roles/{name}", status_code=204)
async def delete_role(
    name: str,
    _writes: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
):
    """Delete a role."""
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
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
):
    """List all service names that have grants."""
    return await admin_ops.list_service_grants(storage)


@router.get("/grants/{service}", response_model=ServiceGrants)
async def get_grants(
    service: str,
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
):
    """Get grants for a service."""
    try:
        sg = await admin_ops.get_service_grants(storage, service)
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Grants for '{service}' not found")
    return sg.model_dump()


@router.post("/grants/{service}", response_model=ServiceGrants)
async def put_grants(
    service: str,
    body: PutGrantsRequest,
    _writes: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
):
    """Create or replace grants for a service."""
    sg = await admin_ops.put_service_grants(storage, authority, service, body.grants)
    return sg.model_dump()


@router.delete("/grants/{service}", status_code=204)
async def delete_grants(
    service: str,
    _writes: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
):
    """Delete all grants for a service."""
    try:
        await admin_ops.delete_service_grants(storage, authority, service)
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Grants for '{service}' not found")
    return Response(status_code=204)


# ------------------------------------------------------------------
# Session endpoints
# ------------------------------------------------------------------


@router.get("/sessions", dependencies=[Depends(needs_session_store)])
async def list_sessions(
    store: Annotated[SessionStore | None, Depends(get_session_store)],
):
    """List all active sessions."""
    return await admin_ops.list_sessions(store)


@router.get("/sessions/email/{email}", dependencies=[Depends(needs_session_store)])
async def list_sessions_by_email(
    email: str,
    store: Annotated[SessionStore | None, Depends(get_session_store)],
):
    """List sessions for a specific user email."""
    return await admin_ops.list_sessions_by_email(store, email)


@router.delete(
    "/sessions/id/{session_id}", response_model=RevokeSessionResponse, dependencies=[Depends(needs_session_store)]
)
async def revoke_session(
    session_id: str,
    store: Annotated[SessionStore | None, Depends(get_session_store)],
):
    """Revoke a single session by ID."""
    revoked = await admin_ops.revoke_session(store, session_id)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"revoked": True, "session_id": session_id}


@router.delete(
    "/sessions/email/{email}", response_model=RevokeByEmailResponse, dependencies=[Depends(needs_session_store)]
)
async def revoke_sessions_by_email(
    email: str,
    store: Annotated[SessionStore | None, Depends(get_session_store)],
):
    """Revoke all sessions for a user email."""
    count = await admin_ops.revoke_sessions_by_email(store, email)
    return {"revoked": count, "email": email}
