"""Tests for admin ops service layer — CRUD operations with cache invalidation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound

from dockmaster.rbac.models import Grant, Role, ServiceGrants


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_storage() -> MagicMock:
    """Return a mock SecretsStorage."""
    return MagicMock()


def _mock_authority() -> MagicMock:
    """Return a mock Authority with clear_cache."""
    authority = MagicMock()
    authority.clear_cache = MagicMock()
    return authority


# ---------------------------------------------------------------------------
# Role operations
# ---------------------------------------------------------------------------


class TestListRoles:
    @pytest.mark.anyio
    async def test_returns_role_names(self):
        from dockmaster.rbac.admin_ops import list_roles

        storage = _mock_storage()
        storage.list_roles.return_value = ["viewer", "editor"]

        result = await list_roles(storage)
        assert result == ["viewer", "editor"]

    @pytest.mark.anyio
    async def test_does_not_clear_cache(self):
        from dockmaster.rbac.admin_ops import list_roles

        storage = _mock_storage()
        storage.list_roles.return_value = []
        authority = _mock_authority()

        await list_roles(storage)
        authority.clear_cache.assert_not_called()


class TestGetRole:
    @pytest.mark.anyio
    async def test_returns_role(self):
        from dockmaster.rbac.admin_ops import get_role

        storage = _mock_storage()
        role = Role(name="viewer", permissions=["read"])
        storage.get_role.return_value = role

        result = await get_role(storage, "viewer")
        assert result == role
        storage.get_role.assert_called_once_with("viewer")

    @pytest.mark.anyio
    async def test_not_found_propagates(self):
        from dockmaster.rbac.admin_ops import get_role

        storage = _mock_storage()
        storage.get_role.side_effect = NotFound("not found")

        with pytest.raises(NotFound):
            await get_role(storage, "nonexistent")


class TestCreateRole:
    @pytest.mark.anyio
    async def test_creates_and_clears_cache(self):
        from dockmaster.rbac.admin_ops import create_role

        storage = _mock_storage()
        storage.get_role.side_effect = NotFound("not found")
        authority = _mock_authority()

        role = await create_role(storage, authority, "viewer", ["read", "list"])

        assert role.name == "viewer"
        assert role.permissions == ["read", "list"]
        storage.put_role.assert_called_once_with("viewer", role)
        authority.clear_cache.assert_called_once()

    @pytest.mark.anyio
    async def test_conflict_if_exists(self):
        from dockmaster.rbac.admin_ops import create_role, RoleConflictError

        storage = _mock_storage()
        storage.get_role.return_value = Role(name="viewer", permissions=["read"])

        with pytest.raises(RoleConflictError):
            await create_role(storage, _mock_authority(), "viewer", ["read"])


class TestUpdateRole:
    @pytest.mark.anyio
    async def test_updates_and_clears_cache(self):
        from dockmaster.rbac.admin_ops import update_role

        storage = _mock_storage()
        authority = _mock_authority()

        role = await update_role(storage, authority, "viewer", ["read", "write"])

        assert role.name == "viewer"
        assert role.permissions == ["read", "write"]
        storage.put_role.assert_called_once_with("viewer", role)
        authority.clear_cache.assert_called_once()


class TestDeleteRole:
    @pytest.mark.anyio
    async def test_deletes_and_clears_cache(self):
        from dockmaster.rbac.admin_ops import delete_role

        storage = _mock_storage()
        authority = _mock_authority()

        await delete_role(storage, authority, "viewer")

        storage.delete_role.assert_called_once_with("viewer")
        authority.clear_cache.assert_called_once()

    @pytest.mark.anyio
    async def test_not_found_propagates(self):
        from dockmaster.rbac.admin_ops import delete_role

        storage = _mock_storage()
        storage.delete_role.side_effect = NotFound("not found")

        with pytest.raises(NotFound):
            await delete_role(storage, _mock_authority(), "nonexistent")


# ---------------------------------------------------------------------------
# Grant operations
# ---------------------------------------------------------------------------


class TestListServiceGrants:
    @pytest.mark.anyio
    async def test_returns_service_names(self):
        from dockmaster.rbac.admin_ops import list_service_grants

        storage = _mock_storage()
        storage.list_service_grants.return_value = ["lims", "dockmaster"]

        result = await list_service_grants(storage)
        assert result == ["lims", "dockmaster"]


class TestGetServiceGrants:
    @pytest.mark.anyio
    async def test_returns_grants(self):
        from dockmaster.rbac.admin_ops import get_service_grants

        storage = _mock_storage()
        sg = ServiceGrants(
            service="lims",
            grants=[Grant(subject="alice@co.com", roles=["viewer"])],
        )
        storage.get_service_grants.return_value = sg

        result = await get_service_grants(storage, "lims")
        assert result == sg

    @pytest.mark.anyio
    async def test_not_found_propagates(self):
        from dockmaster.rbac.admin_ops import get_service_grants

        storage = _mock_storage()
        storage.get_service_grants.side_effect = NotFound("not found")

        with pytest.raises(NotFound):
            await get_service_grants(storage, "nonexistent")


class TestPutServiceGrants:
    @pytest.mark.anyio
    async def test_saves_and_clears_cache(self):
        from dockmaster.rbac.admin_ops import put_service_grants

        storage = _mock_storage()
        authority = _mock_authority()
        grants = [Grant(subject="alice@co.com", roles=["viewer"])]

        result = await put_service_grants(storage, authority, "lims", grants)

        assert result.service == "lims"
        assert len(result.grants) == 1
        storage.put_service_grants.assert_called_once()
        authority.clear_cache.assert_called_once()


class TestDeleteServiceGrants:
    @pytest.mark.anyio
    async def test_deletes_and_clears_cache(self):
        from dockmaster.rbac.admin_ops import delete_service_grants

        storage = _mock_storage()
        authority = _mock_authority()

        await delete_service_grants(storage, authority, "lims")

        storage.delete_service_grants.assert_called_once_with("lims")
        authority.clear_cache.assert_called_once()
