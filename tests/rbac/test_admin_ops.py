"""Tests for admin ops service layer — CRUD operations with cache invalidation."""


import pytest
from google.api_core.exceptions import NotFound
from pytest_mock import MockerFixture

from dockmaster.rbac.models import Grant, Role, ServiceGrants


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_storage(mocker: MockerFixture):
    """Return a mock SecretsStorage."""
    return mocker.MagicMock()


def _mock_authority(mocker: MockerFixture):
    """Return a mock Authority with clear_cache."""
    authority = mocker.MagicMock()
    authority.clear_cache = mocker.MagicMock()
    return authority


# ---------------------------------------------------------------------------
# Role operations
# ---------------------------------------------------------------------------


class TestListRoles:
    @pytest.mark.anyio
    async def test_returns_role_names(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import list_roles

        storage = _mock_storage(mocker)
        storage.list_roles.return_value = ["viewer", "editor"]

        result = await list_roles(storage)
        assert result == ["viewer", "editor"]

    @pytest.mark.anyio
    async def test_does_not_clear_cache(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import list_roles

        storage = _mock_storage(mocker)
        storage.list_roles.return_value = []
        authority = _mock_authority(mocker)

        await list_roles(storage)
        authority.clear_cache.assert_not_called()


class TestGetRole:
    @pytest.mark.anyio
    async def test_returns_role(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import get_role

        storage = _mock_storage(mocker)
        role = Role(name="viewer", permissions=["read"])
        storage.get_role.return_value = role

        result = await get_role(storage, "viewer")
        assert result == role
        storage.get_role.assert_called_once_with("viewer")

    @pytest.mark.anyio
    async def test_not_found_propagates(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import get_role

        storage = _mock_storage(mocker)
        storage.get_role.side_effect = NotFound("not found")

        with pytest.raises(NotFound):
            await get_role(storage, "nonexistent")


class TestCreateRole:
    @pytest.mark.anyio
    async def test_creates_and_clears_cache(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import create_role

        storage = _mock_storage(mocker)
        storage.get_role.side_effect = NotFound("not found")
        authority = _mock_authority(mocker)

        role = await create_role(storage, authority, "viewer", ["read", "list"])

        assert role.name == "viewer"
        assert role.permissions == ["read", "list"]
        storage.put_role.assert_called_once_with("viewer", role)
        authority.clear_cache.assert_called_once()

    @pytest.mark.anyio
    async def test_conflict_if_exists(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import create_role, RoleConflictError

        storage = _mock_storage(mocker)
        storage.get_role.return_value = Role(name="viewer", permissions=["read"])

        with pytest.raises(RoleConflictError):
            await create_role(storage, _mock_authority(mocker), "viewer", ["read"])


class TestUpdateRole:
    @pytest.mark.anyio
    async def test_updates_and_clears_cache(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import update_role

        storage = _mock_storage(mocker)
        authority = _mock_authority(mocker)

        role = await update_role(storage, authority, "viewer", ["read", "write"])

        assert role.name == "viewer"
        assert role.permissions == ["read", "write"]
        storage.put_role.assert_called_once_with("viewer", role)
        authority.clear_cache.assert_called_once()


class TestDeleteRole:
    @pytest.mark.anyio
    async def test_deletes_and_clears_cache(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import delete_role

        storage = _mock_storage(mocker)
        authority = _mock_authority(mocker)

        await delete_role(storage, authority, "viewer")

        storage.delete_role.assert_called_once_with("viewer")
        authority.clear_cache.assert_called_once()

    @pytest.mark.anyio
    async def test_not_found_propagates(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import delete_role

        storage = _mock_storage(mocker)
        storage.delete_role.side_effect = NotFound("not found")

        with pytest.raises(NotFound):
            await delete_role(storage, _mock_authority(mocker), "nonexistent")


# ---------------------------------------------------------------------------
# Grant operations
# ---------------------------------------------------------------------------


class TestListServiceGrants:
    @pytest.mark.anyio
    async def test_returns_service_names(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import list_service_grants

        storage = _mock_storage(mocker)
        storage.list_service_grants.return_value = ["lims", "dockmaster"]

        result = await list_service_grants(storage)
        assert result == ["lims", "dockmaster"]


class TestGetServiceGrants:
    @pytest.mark.anyio
    async def test_returns_grants(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import get_service_grants

        storage = _mock_storage(mocker)
        sg = ServiceGrants(
            service="lims",
            grants=[Grant(subject="alice@co.com", roles=["viewer"])],
        )
        storage.get_service_grants.return_value = sg

        result = await get_service_grants(storage, "lims")
        assert result == sg

    @pytest.mark.anyio
    async def test_not_found_propagates(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import get_service_grants

        storage = _mock_storage(mocker)
        storage.get_service_grants.side_effect = NotFound("not found")

        with pytest.raises(NotFound):
            await get_service_grants(storage, "nonexistent")


class TestPutServiceGrants:
    @pytest.mark.anyio
    async def test_saves_and_clears_cache(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import put_service_grants

        storage = _mock_storage(mocker)
        authority = _mock_authority(mocker)
        grants = [Grant(subject="alice@co.com", roles=["viewer"])]

        result = await put_service_grants(storage, authority, "lims", grants)

        assert result.service == "lims"
        assert len(result.grants) == 1
        storage.put_service_grants.assert_called_once()
        authority.clear_cache.assert_called_once()


class TestDeleteServiceGrants:
    @pytest.mark.anyio
    async def test_deletes_and_clears_cache(self, mocker: MockerFixture):
        from dockmaster.rbac.admin_ops import delete_service_grants

        storage = _mock_storage(mocker)
        authority = _mock_authority(mocker)

        await delete_service_grants(storage, authority, "lims")

        storage.delete_service_grants.assert_called_once_with("lims")
        authority.clear_cache.assert_called_once()


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------


def _session_store_with_data():
    """Return an InMemorySessionStore pre-populated with test sessions."""
    from dockmaster.sessions.memory import InMemorySessionStore

    store = InMemorySessionStore()
    # Manually insert sessions (bypass async set for simplicity)
    import time

    now = time.time()
    store._store["sess-1"] = ({"email": "alice@example.com", "name": "Alice"}, now + 3600)
    store._store["sess-2"] = ({"email": "alice@example.com", "name": "Alice"}, now + 3600)
    store._store["sess-3"] = ({"email": "bob@example.com", "name": "Bob"}, now + 3600)
    return store


class TestListSessions:
    @pytest.mark.anyio
    async def test_returns_all_sessions(self):
        from dockmaster.rbac.admin_ops import list_sessions

        store = _session_store_with_data()
        result = await list_sessions(store)

        assert len(result) == 3
        assert "sess-1" in result
        assert "sess-2" in result
        assert "sess-3" in result

    @pytest.mark.anyio
    async def test_empty_store(self):
        from dockmaster.rbac.admin_ops import list_sessions
        from dockmaster.sessions.memory import InMemorySessionStore

        store = InMemorySessionStore()
        result = await list_sessions(store)
        assert result == {}


class TestListSessionsByEmail:
    @pytest.mark.anyio
    async def test_filters_by_email(self):
        from dockmaster.rbac.admin_ops import list_sessions_by_email

        store = _session_store_with_data()
        result = await list_sessions_by_email(store, "alice@example.com")

        assert len(result) == 2
        assert "sess-1" in result
        assert "sess-2" in result
        assert "sess-3" not in result

    @pytest.mark.anyio
    async def test_no_match_returns_empty(self):
        from dockmaster.rbac.admin_ops import list_sessions_by_email

        store = _session_store_with_data()
        result = await list_sessions_by_email(store, "nobody@example.com")
        assert result == {}


class TestRevokeSession:
    @pytest.mark.anyio
    async def test_revokes_existing_session(self):
        from dockmaster.rbac.admin_ops import revoke_session

        store = _session_store_with_data()
        result = await revoke_session(store, "sess-1")

        assert result is True
        assert await store.get("sess-1") is None
        # Other sessions unaffected
        assert await store.get("sess-3") is not None

    @pytest.mark.anyio
    async def test_returns_false_for_missing_session(self):
        from dockmaster.rbac.admin_ops import revoke_session

        store = _session_store_with_data()
        result = await revoke_session(store, "nonexistent")
        assert result is False


class TestRevokeSessionsByEmail:
    @pytest.mark.anyio
    async def test_revokes_all_for_email(self):
        from dockmaster.rbac.admin_ops import revoke_sessions_by_email

        store = _session_store_with_data()
        count = await revoke_sessions_by_email(store, "alice@example.com")

        assert count == 2
        assert await store.get("sess-1") is None
        assert await store.get("sess-2") is None
        # Bob's session unaffected
        assert await store.get("sess-3") is not None

    @pytest.mark.anyio
    async def test_returns_zero_for_no_match(self):
        from dockmaster.rbac.admin_ops import revoke_sessions_by_email

        store = _session_store_with_data()
        count = await revoke_sessions_by_email(store, "nobody@example.com")
        assert count == 0
