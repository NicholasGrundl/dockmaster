"""Tests for Authority — permission resolution with TTL cache."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from dockmaster.rbac.authority import Authority
from dockmaster.rbac.models import Grant, Role, ServiceGrants
from dockmaster.rbac.storage import SecretsStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_storage() -> MagicMock:
    """Return a mock SecretsStorage."""
    return MagicMock(spec=SecretsStorage)


def _make_authority(storage: MagicMock | None = None, cache_ttl: int = 300) -> Authority:
    return Authority(storage=storage or _mock_storage(), cache_ttl=cache_ttl)


VIEWER_ROLE = Role(name="viewer", permissions=["read", "list"])
EDITOR_ROLE = Role(name="editor", permissions=["read", "write"])
ADMIN_ROLE = Role(name="admin", permissions=["read", "write", "delete", "experiment:approve"])

GRANTS = ServiceGrants(
    service="data-pipeline",
    grants=[
        Grant(subject="alice@example.com", roles=["viewer", "editor"]),
        Grant(subject="bob@example.com", roles=["viewer"]),
    ],
)


def _setup_storage(storage: MagicMock) -> None:
    """Configure mock storage to return test data."""

    def get_service_grants(service: str) -> ServiceGrants:
        if service == "data-pipeline":
            return GRANTS
        from google.api_core.exceptions import NotFound

        raise NotFound(f"service-grants-{service}")

    def get_role(name: str) -> Role:
        roles = {"viewer": VIEWER_ROLE, "editor": EDITOR_ROLE, "admin": ADMIN_ROLE}
        if name in roles:
            return roles[name]
        from google.api_core.exceptions import NotFound

        raise NotFound(f"role-{name}")

    storage.get_service_grants.side_effect = get_service_grants
    storage.get_role.side_effect = get_role


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------


class TestHasPermission:
    @pytest.fixture
    def authority(self) -> Authority:
        storage = _mock_storage()
        _setup_storage(storage)
        return _make_authority(storage)

    async def test_granted(self, authority: Authority):
        result = await authority.has_permission("alice@example.com", "data-pipeline", "read")
        assert result is True

    async def test_granted_from_second_role(self, authority: Authority):
        """Alice has 'write' via 'editor' role (not 'viewer')."""
        result = await authority.has_permission("alice@example.com", "data-pipeline", "write")
        assert result is True

    async def test_denied_no_permission(self, authority: Authority):
        """Bob has 'viewer' only — no 'write' permission."""
        result = await authority.has_permission("bob@example.com", "data-pipeline", "write")
        assert result is False

    async def test_denied_subject_not_in_grants(self, authority: Authority):
        result = await authority.has_permission("unknown@example.com", "data-pipeline", "read")
        assert result is False

    async def test_denied_target_not_found(self, authority: Authority):
        result = await authority.has_permission("alice@example.com", "nonexistent", "read")
        assert result is False

    async def test_permission_with_colon(self, authority: Authority):
        """Permissions like 'experiment:approve' use exact string matching."""
        storage = _mock_storage()
        storage.get_service_grants.return_value = ServiceGrants(
            service="experiments",
            grants=[Grant(subject="alice@example.com", roles=["admin"])],
        )
        storage.get_role.return_value = ADMIN_ROLE
        auth = _make_authority(storage)

        result = await auth.has_permission("alice@example.com", "experiments", "experiment:approve")
        assert result is True


# ---------------------------------------------------------------------------
# TTL cache behavior
# ---------------------------------------------------------------------------


class TestCache:
    async def test_cache_hit_no_second_sm_call(self):
        storage = _mock_storage()
        _setup_storage(storage)
        auth = _make_authority(storage, cache_ttl=300)

        await auth.has_permission("alice@example.com", "data-pipeline", "read")
        await auth.has_permission("alice@example.com", "data-pipeline", "write")

        # Service grants loaded once (cached), roles loaded once each
        assert storage.get_service_grants.call_count == 1

    async def test_cache_expiry_triggers_reload(self):
        storage = _mock_storage()
        _setup_storage(storage)
        auth = _make_authority(storage, cache_ttl=1)

        await auth.has_permission("alice@example.com", "data-pipeline", "read")
        assert storage.get_service_grants.call_count == 1

        # Wait for cache to expire
        with patch("dockmaster.rbac.authority.time") as mock_time:
            # First call used real time; simulate expiry
            mock_time.time.return_value = time.time() + 2
            await auth.has_permission("alice@example.com", "data-pipeline", "read")

        assert storage.get_service_grants.call_count == 2

    async def test_clear_cache_forces_reload(self):
        storage = _mock_storage()
        _setup_storage(storage)
        auth = _make_authority(storage, cache_ttl=300)

        await auth.has_permission("alice@example.com", "data-pipeline", "read")
        assert storage.get_service_grants.call_count == 1

        auth.clear_cache()

        await auth.has_permission("alice@example.com", "data-pipeline", "read")
        assert storage.get_service_grants.call_count == 2

    async def test_different_targets_cached_separately(self):
        storage = _mock_storage()
        sg1 = ServiceGrants(
            service="svc-a",
            grants=[Grant(subject="alice@example.com", roles=["viewer"])],
        )
        sg2 = ServiceGrants(
            service="svc-b",
            grants=[Grant(subject="alice@example.com", roles=["viewer"])],
        )
        storage.get_service_grants.side_effect = [sg1, sg2]
        storage.get_role.return_value = VIEWER_ROLE
        auth = _make_authority(storage, cache_ttl=300)

        await auth.has_permission("alice@example.com", "svc-a", "read")
        await auth.has_permission("alice@example.com", "svc-b", "read")

        assert storage.get_service_grants.call_count == 2
