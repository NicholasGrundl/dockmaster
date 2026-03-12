"""Tests for SecretsStorage RBAC methods — get/put/delete for roles and grants."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound

from dockmaster.rbac.models import Grant, Role, ServiceGrants
from dockmaster.rbac.storage import AdminSecretsStorage, SecretsStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_sm_client() -> MagicMock:
    """Return a mock SecretManagerServiceClient."""
    return MagicMock()


def _access_response(payload_bytes: bytes) -> MagicMock:
    """Build a mock AccessSecretVersionResponse."""
    resp = MagicMock()
    resp.payload.data = payload_bytes
    return resp


def _storage(client: MagicMock | None = None) -> SecretsStorage:
    return SecretsStorage(client=client or _mock_sm_client(), project="test-project")


def _admin_storage(client: MagicMock | None = None) -> AdminSecretsStorage:
    return AdminSecretsStorage(client=client or _mock_sm_client(), project="test-project")


# ---------------------------------------------------------------------------
# get_role
# ---------------------------------------------------------------------------


class TestGetRole:
    def test_loads_and_parses_role(self):
        client = _mock_sm_client()
        role_data = {"name": "viewer", "permissions": ["read", "list"]}
        client.access_secret_version.return_value = _access_response(json.dumps(role_data).encode())
        storage = _storage(client)

        role = storage.get_role("viewer")

        assert isinstance(role, Role)
        assert role.name == "viewer"
        assert role.permissions == ["read", "list"]
        client.access_secret_version.assert_called_once_with(
            request={"name": "projects/test-project/secrets/role-viewer/versions/latest"}
        )

    def test_legacy_kind_field_ignored(self):
        client = _mock_sm_client()
        role_data = {"kind": "Role", "name": "editor", "permissions": ["read", "write"]}
        client.access_secret_version.return_value = _access_response(json.dumps(role_data).encode())
        storage = _storage(client)

        role = storage.get_role("editor")
        assert role.name == "editor"
        assert not hasattr(role, "kind")

    def test_not_found_raises(self):
        client = _mock_sm_client()
        client.access_secret_version.side_effect = NotFound("not found")
        storage = _storage(client)

        with pytest.raises(NotFound):
            storage.get_role("nonexistent")


# ---------------------------------------------------------------------------
# put_role
# ---------------------------------------------------------------------------


class TestPutRole:
    def test_creates_secret_and_adds_version(self):
        client = _mock_sm_client()
        storage = _admin_storage(client)
        role = Role(name="viewer", permissions=["read", "list"])

        storage.put_role("viewer", role)

        # Should attempt create (idempotent) then add version
        client.create_secret.assert_called_once()
        client.add_secret_version.assert_called_once()

        # Verify the payload
        call_kwargs = client.add_secret_version.call_args
        payload_data = (
            call_kwargs[1]["request"]["payload"]["data"]
            if "request" in call_kwargs[1]
            else call_kwargs[0][0]["payload"]["data"]
        )
        stored = json.loads(payload_data)
        assert stored["name"] == "viewer"
        assert stored["permissions"] == ["read", "list"]

    def test_create_already_exists_is_idempotent(self):
        from google.api_core.exceptions import AlreadyExists

        client = _mock_sm_client()
        client.create_secret.side_effect = AlreadyExists("exists")
        storage = _admin_storage(client)
        role = Role(name="viewer", permissions=["read"])

        # Should not raise — AlreadyExists is swallowed
        storage.put_role("viewer", role)
        client.add_secret_version.assert_called_once()


# ---------------------------------------------------------------------------
# delete_role
# ---------------------------------------------------------------------------


class TestDeleteRole:
    def test_deletes_secret(self):
        client = _mock_sm_client()
        storage = _admin_storage(client)

        storage.delete_role("viewer")

        client.delete_secret.assert_called_once_with(request={"name": "projects/test-project/secrets/role-viewer"})

    def test_not_found_raises(self):
        client = _mock_sm_client()
        client.delete_secret.side_effect = NotFound("not found")
        storage = _admin_storage(client)

        with pytest.raises(NotFound):
            storage.delete_role("nonexistent")


# ---------------------------------------------------------------------------
# get_service_grants
# ---------------------------------------------------------------------------


class TestGetServiceGrants:
    def test_loads_and_parses(self):
        client = _mock_sm_client()
        data = {
            "service": "data-pipeline",
            "grants": [
                {"subject": "alice@example.com", "roles": ["viewer", "editor"]},
                {"subject": "bob@example.com", "roles": ["viewer"]},
            ],
        }
        client.access_secret_version.return_value = _access_response(json.dumps(data).encode())
        storage = _storage(client)

        sg = storage.get_service_grants("data-pipeline")

        assert isinstance(sg, ServiceGrants)
        assert sg.service == "data-pipeline"
        assert len(sg.grants) == 2
        assert sg.grants[0].roles == ["viewer", "editor"]
        client.access_secret_version.assert_called_once_with(
            request={"name": "projects/test-project/secrets/service-grants-data-pipeline/versions/latest"}
        )

    def test_not_found_raises(self):
        client = _mock_sm_client()
        client.access_secret_version.side_effect = NotFound("not found")
        storage = _storage(client)

        with pytest.raises(NotFound):
            storage.get_service_grants("nonexistent")


# ---------------------------------------------------------------------------
# put_service_grants
# ---------------------------------------------------------------------------


class TestPutServiceGrants:
    def test_creates_and_stores(self):
        client = _mock_sm_client()
        storage = _admin_storage(client)
        sg = ServiceGrants(
            service="data-pipeline",
            grants=[Grant(subject="alice@example.com", roles=["viewer"])],
        )

        storage.put_service_grants("data-pipeline", sg)

        client.create_secret.assert_called_once()
        client.add_secret_version.assert_called_once()


# ---------------------------------------------------------------------------
# delete_service_grants
# ---------------------------------------------------------------------------


class TestDeleteServiceGrants:
    def test_deletes_secret(self):
        client = _mock_sm_client()
        storage = _admin_storage(client)

        storage.delete_service_grants("data-pipeline")

        client.delete_secret.assert_called_once_with(
            request={"name": "projects/test-project/secrets/service-grants-data-pipeline"}
        )


# ---------------------------------------------------------------------------
# list_roles
# ---------------------------------------------------------------------------


def _mock_secret(name: str) -> MagicMock:
    """Build a mock Secret with a .name attribute (full resource path)."""
    secret = MagicMock()
    secret.name = f"projects/test-project/secrets/{name}"
    return secret


class TestListRoles:
    def test_returns_role_names(self):
        client = _mock_sm_client()
        client.list_secrets.return_value = [
            _mock_secret("role-viewer"),
            _mock_secret("role-editor"),
            _mock_secret("role-admin"),
        ]
        storage = _storage(client)

        result = storage.list_roles()

        assert result == ["viewer", "editor", "admin"]
        client.list_secrets.assert_called_once_with(request={"parent": "projects/test-project", "filter": "name:role-"})

    def test_returns_empty_list(self):
        client = _mock_sm_client()
        client.list_secrets.return_value = []
        storage = _storage(client)

        assert storage.list_roles() == []

    def test_strips_prefix(self):
        client = _mock_sm_client()
        client.list_secrets.return_value = [_mock_secret("role-finance-admin")]
        storage = _storage(client)

        result = storage.list_roles()
        assert result == ["finance-admin"]


# ---------------------------------------------------------------------------
# list_service_grants
# ---------------------------------------------------------------------------


class TestListServiceGrants:
    def test_returns_service_names(self):
        client = _mock_sm_client()
        client.list_secrets.return_value = [
            _mock_secret("service-grants-lims"),
            _mock_secret("service-grants-dockmaster"),
        ]
        storage = _storage(client)

        result = storage.list_service_grants()

        assert result == ["lims", "dockmaster"]
        client.list_secrets.assert_called_once_with(
            request={"parent": "projects/test-project", "filter": "name:service-grants-"}
        )

    def test_returns_empty_list(self):
        client = _mock_sm_client()
        client.list_secrets.return_value = []
        storage = _storage(client)

        assert storage.list_service_grants() == []

    def test_strips_prefix(self):
        client = _mock_sm_client()
        client.list_secrets.return_value = [_mock_secret("service-grants-data-pipeline")]
        storage = _storage(client)

        result = storage.list_service_grants()
        assert result == ["data-pipeline"]
