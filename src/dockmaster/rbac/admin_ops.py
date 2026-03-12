"""Admin CRUD operations for RBAC roles and grants.

Service layer shared by API routes and UI routes. Each write operation
calls storage then invalidates the Authority cache so changes take effect
immediately on the handling instance.

All storage calls use run_in_executor because the SM client is synchronous.
"""

from __future__ import annotations

import asyncio

from google.api_core.exceptions import NotFound

from dockmaster.rbac.models import Grant, Role, ServiceGrants
from dockmaster.rbac.storage import AdminSecretsStorage, SecretsStorage


class RoleConflictError(Exception):
    """Raised when attempting to create a role that already exists."""


# ------------------------------------------------------------------
# Roles
# ------------------------------------------------------------------


async def list_roles(storage: SecretsStorage) -> list[str]:
    """List all role names."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, storage.list_roles)


async def get_role(storage: SecretsStorage, name: str) -> Role:
    """Get a single role by name. Raises NotFound if missing."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, storage.get_role, name)


async def create_role(
    storage: AdminSecretsStorage,
    authority: object | None,
    name: str,
    permissions: list[str],
) -> Role:
    """Create a new role. Raises RoleConflictError if it already exists."""
    loop = asyncio.get_event_loop()

    # Check for conflict
    try:
        await loop.run_in_executor(None, storage.get_role, name)
        raise RoleConflictError(f"Role '{name}' already exists")
    except NotFound:
        pass

    role = Role(name=name, permissions=permissions)
    await loop.run_in_executor(None, storage.put_role, name, role)

    if authority is not None:
        authority.clear_cache()

    return role


async def update_role(
    storage: AdminSecretsStorage,
    authority: object | None,
    name: str,
    permissions: list[str],
) -> Role:
    """Update an existing role's permissions."""
    loop = asyncio.get_event_loop()
    role = Role(name=name, permissions=permissions)
    await loop.run_in_executor(None, storage.put_role, name, role)

    if authority is not None:
        authority.clear_cache()

    return role


async def delete_role(
    storage: AdminSecretsStorage,
    authority: object | None,
    name: str,
) -> None:
    """Delete a role. Raises NotFound if missing."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, storage.delete_role, name)

    if authority is not None:
        authority.clear_cache()


# ------------------------------------------------------------------
# Service Grants
# ------------------------------------------------------------------


async def list_service_grants(storage: SecretsStorage) -> list[str]:
    """List all service names that have grants."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, storage.list_service_grants)


async def get_service_grants(storage: SecretsStorage, service: str) -> ServiceGrants:
    """Get grants for a service. Raises NotFound if missing."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, storage.get_service_grants, service)


async def put_service_grants(
    storage: AdminSecretsStorage,
    authority: object | None,
    service: str,
    grants: list[Grant],
) -> ServiceGrants:
    """Create or replace grants for a service."""
    loop = asyncio.get_event_loop()
    sg = ServiceGrants(service=service, grants=grants)
    await loop.run_in_executor(None, storage.put_service_grants, service, sg)

    if authority is not None:
        authority.clear_cache()

    return sg


async def delete_service_grants(
    storage: AdminSecretsStorage,
    authority: object | None,
    service: str,
) -> None:
    """Delete all grants for a service. Raises NotFound if missing."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, storage.delete_service_grants, service)

    if authority is not None:
        authority.clear_cache()
