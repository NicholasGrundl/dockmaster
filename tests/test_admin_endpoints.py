"""Tests for admin CRUD endpoints — roles and grants."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound

from dockmaster.config import Settings, get_settings
from dockmaster.rbac.models import Grant, Role, ServiceGrants


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_app(
    *,
    roles: dict[str, Role] | None = None,
    services: dict[str, ServiceGrants] | None = None,
    role_names: list[str] | None = None,
    service_names: list[str] | None = None,
) -> FastAPI:
    """Build an app with admin routes and mocked storage."""
    from dockmaster.routes.admin import router

    app = FastAPI()
    app.include_router(router, prefix="/admin")

    test_settings = Settings(
        _env_file=None,
        dockmaster_admin_emails={"admin@co.com"},
    )
    app.dependency_overrides[get_settings] = lambda: test_settings

    # Mock authority
    authority = AsyncMock()
    authority.has_permission.return_value = True
    authority.clear_cache = MagicMock()
    app.state.authority = authority

    # Mock admin storage (AdminSecretsStorage)
    admin_storage = MagicMock()
    _roles = roles or {}
    _services = services or {}

    def _get_role(name):
        if name in _roles:
            return _roles[name]
        raise NotFound(f"role-{name}")

    def _get_service_grants(service):
        if service in _services:
            return _services[service]
        raise NotFound(f"service-grants-{service}")

    admin_storage.get_role.side_effect = _get_role
    admin_storage.get_service_grants.side_effect = _get_service_grants
    admin_storage.list_roles.return_value = role_names or list(_roles.keys())
    admin_storage.list_service_grants.return_value = service_names or list(_services.keys())
    admin_storage.put_role = MagicMock()
    admin_storage.delete_role = MagicMock()
    admin_storage.put_service_grants = MagicMock()
    admin_storage.delete_service_grants = MagicMock()

    app.state.admin_storage = admin_storage

    # Override JWT auth to return admin user
    from dockmaster.auth.middleware import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"email": "admin@co.com"}

    return app


def _get_authority(app: FastAPI) -> MagicMock:
    return app.state.authority


def _get_admin_storage(app: FastAPI) -> MagicMock:
    return app.state.admin_storage


# ---------------------------------------------------------------------------
# Role endpoints
# ---------------------------------------------------------------------------


class TestListRoles:
    def test_returns_role_names(self):
        app = _admin_app(role_names=["viewer", "editor", "admin"])
        resp = TestClient(app).get("/admin/roles")
        assert resp.status_code == 200
        assert resp.json() == ["viewer", "editor", "admin"]

    def test_empty_list(self):
        app = _admin_app(role_names=[])
        resp = TestClient(app).get("/admin/roles")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetRole:
    def test_returns_role(self):
        role = Role(name="viewer", permissions=["read", "list"])
        app = _admin_app(roles={"viewer": role})
        resp = TestClient(app).get("/admin/roles/viewer")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "viewer"
        assert data["permissions"] == ["read", "list"]

    def test_not_found(self):
        app = _admin_app()
        resp = TestClient(app).get("/admin/roles/nonexistent")
        assert resp.status_code == 404


class TestCreateRole:
    def test_creates_role(self):
        app = _admin_app()
        resp = TestClient(app).post(
            "/admin/roles",
            json={"name": "viewer", "permissions": ["read", "list"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "viewer"
        assert data["permissions"] == ["read", "list"]
        _get_admin_storage(app).put_role.assert_called_once()
        _get_authority(app).clear_cache.assert_called_once()

    def test_conflict_if_exists(self):
        role = Role(name="viewer", permissions=["read"])
        app = _admin_app(roles={"viewer": role})
        resp = TestClient(app).post(
            "/admin/roles",
            json={"name": "viewer", "permissions": ["read"]},
        )
        assert resp.status_code == 409


class TestUpdateRole:
    def test_updates_role(self):
        app = _admin_app()
        resp = TestClient(app).put(
            "/admin/roles/viewer",
            json={"permissions": ["read", "write"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "viewer"
        assert data["permissions"] == ["read", "write"]
        _get_admin_storage(app).put_role.assert_called_once()
        _get_authority(app).clear_cache.assert_called_once()


class TestDeleteRole:
    def test_deletes_role(self):
        role = Role(name="viewer", permissions=["read"])
        app = _admin_app(roles={"viewer": role})
        resp = TestClient(app).delete("/admin/roles/viewer")
        assert resp.status_code == 204
        _get_admin_storage(app).delete_role.assert_called_once()
        _get_authority(app).clear_cache.assert_called_once()

    def test_not_found(self):
        app = _admin_app()
        storage = _get_admin_storage(app)
        storage.delete_role.side_effect = NotFound("not found")
        resp = TestClient(app).delete("/admin/roles/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Grant endpoints
# ---------------------------------------------------------------------------


class TestListGrants:
    def test_returns_service_names(self):
        app = _admin_app(service_names=["lims", "dockmaster"])
        resp = TestClient(app).get("/admin/grants")
        assert resp.status_code == 200
        assert resp.json() == ["lims", "dockmaster"]


class TestGetGrants:
    def test_returns_grants(self):
        sg = ServiceGrants(
            service="lims",
            grants=[Grant(subject="alice@co.com", roles=["viewer"])],
        )
        app = _admin_app(services={"lims": sg})
        resp = TestClient(app).get("/admin/grants/lims")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "lims"
        assert len(data["grants"]) == 1

    def test_not_found(self):
        app = _admin_app()
        resp = TestClient(app).get("/admin/grants/nonexistent")
        assert resp.status_code == 404


class TestPutGrants:
    def test_creates_grants(self):
        app = _admin_app()
        resp = TestClient(app).post(
            "/admin/grants/lims",
            json={"grants": [{"subject": "alice@co.com", "roles": ["viewer"]}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "lims"
        _get_admin_storage(app).put_service_grants.assert_called_once()
        _get_authority(app).clear_cache.assert_called_once()


class TestDeleteGrants:
    def test_deletes_grants(self):
        sg = ServiceGrants(service="lims", grants=[])
        app = _admin_app(services={"lims": sg})
        resp = TestClient(app).delete("/admin/grants/lims")
        assert resp.status_code == 204
        _get_admin_storage(app).delete_service_grants.assert_called_once()
        _get_authority(app).clear_cache.assert_called_once()

    def test_not_found(self):
        app = _admin_app()
        storage = _get_admin_storage(app)
        storage.delete_service_grants.side_effect = NotFound("not found")
        resp = TestClient(app).delete("/admin/grants/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth checks (verify admin dependencies are wired)
# ---------------------------------------------------------------------------


class TestAdminAuth:
    def test_unauthenticated_returns_401(self):
        from dockmaster.routes.admin import router

        app = FastAPI()
        app.include_router(router, prefix="/admin")
        app.state.authority = None
        app.state.admin_storage = None

        resp = TestClient(app).get("/admin/roles")
        assert resp.status_code == 401

    def test_write_without_admin_storage_returns_503(self):
        from dockmaster.routes.admin import router

        app = FastAPI()
        app.include_router(router, prefix="/admin")

        test_settings = Settings(_env_file=None, dockmaster_admin_emails={"admin@co.com"})
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.state.authority = AsyncMock()
        app.state.authority.has_permission.return_value = True
        app.state.admin_storage = None

        from dockmaster.auth.middleware import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {"email": "admin@co.com"}

        resp = TestClient(app).post(
            "/admin/roles",
            json={"name": "viewer", "permissions": ["read"]},
        )
        assert resp.status_code == 503
