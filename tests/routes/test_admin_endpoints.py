"""Tests for admin CRUD endpoints — roles and grants."""

from __future__ import annotations

from pytest_mock import MockerFixture
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound

from dockmaster.config import Settings
from dockmaster.rbac.models import Grant, Role, ServiceGrants


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_app(
    mocker: MockerFixture,
    *,
    roles: dict[str, Role] | None = None,
    services: dict[str, ServiceGrants] | None = None,
    role_names: list[str] | None = None,
    service_names: list[str] | None = None,
    session_store: object | None = None,
) -> FastAPI:
    """Build an app with admin routes and mocked storage."""
    from dockmaster.routes.admin import router

    app = FastAPI()
    app.include_router(router, prefix="/admin")

    if session_store is not None:
        app.state.session_store = session_store

    test_settings = Settings(
        _env_file=None,
        dockmaster_admin_emails={"admin@co.com"},
    )
    app.state.settings = test_settings

    # Mock authority
    authority = mocker.AsyncMock()
    authority.has_permission.return_value = True
    authority.clear_cache = mocker.MagicMock()
    app.state.authority = authority

    # Mock admin storage (AdminSecretsStorage)
    admin_storage = mocker.MagicMock()
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
    admin_storage.put_role = mocker.MagicMock()
    admin_storage.delete_role = mocker.MagicMock()
    admin_storage.put_service_grants = mocker.MagicMock()
    admin_storage.delete_service_grants = mocker.MagicMock()

    app.state.admin_storage = admin_storage

    # Override JWT admin auth to return admin user
    from dockmaster.auth.dependencies import allow_jwt_admin

    app.dependency_overrides[allow_jwt_admin] = lambda: {"email": "admin@co.com"}

    return app


def _get_authority(app: FastAPI):
    return app.state.authority


def _get_admin_storage(app: FastAPI):
    return app.state.admin_storage


# ---------------------------------------------------------------------------
# Role endpoints
# ---------------------------------------------------------------------------


class TestListRoles:
    def test_returns_role_names(self, mocker):
        app = _admin_app(mocker, role_names=["viewer", "editor", "admin"])
        resp = TestClient(app).get("/admin/roles")
        assert resp.status_code == 200
        assert resp.json() == ["viewer", "editor", "admin"]

    def test_empty_list(self, mocker):
        app = _admin_app(mocker, role_names=[])
        resp = TestClient(app).get("/admin/roles")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetRole:
    def test_returns_role(self, mocker):
        role = Role(name="viewer", permissions=["read", "list"])
        app = _admin_app(mocker, roles={"viewer": role})
        resp = TestClient(app).get("/admin/roles/viewer")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "viewer"
        assert data["permissions"] == ["read", "list"]

    def test_not_found(self, mocker):
        app = _admin_app(mocker)
        resp = TestClient(app).get("/admin/roles/nonexistent")
        assert resp.status_code == 404


class TestCreateRole:
    def test_creates_role(self, mocker):
        app = _admin_app(mocker)
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

    def test_conflict_if_exists(self, mocker):
        role = Role(name="viewer", permissions=["read"])
        app = _admin_app(mocker, roles={"viewer": role})
        resp = TestClient(app).post(
            "/admin/roles",
            json={"name": "viewer", "permissions": ["read"]},
        )
        assert resp.status_code == 409


class TestUpdateRole:
    def test_updates_role(self, mocker):
        app = _admin_app(mocker)
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
    def test_deletes_role(self, mocker):
        role = Role(name="viewer", permissions=["read"])
        app = _admin_app(mocker, roles={"viewer": role})
        resp = TestClient(app).delete("/admin/roles/viewer")
        assert resp.status_code == 204
        _get_admin_storage(app).delete_role.assert_called_once()
        _get_authority(app).clear_cache.assert_called_once()

    def test_not_found(self, mocker):
        app = _admin_app(mocker)
        storage = _get_admin_storage(app)
        storage.delete_role.side_effect = NotFound("not found")
        resp = TestClient(app).delete("/admin/roles/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Grant endpoints
# ---------------------------------------------------------------------------


class TestListGrants:
    def test_returns_service_names(self, mocker):
        app = _admin_app(mocker, service_names=["lims", "dockmaster"])
        resp = TestClient(app).get("/admin/grants")
        assert resp.status_code == 200
        assert resp.json() == ["lims", "dockmaster"]


class TestGetGrants:
    def test_returns_grants(self, mocker):
        sg = ServiceGrants(
            service="lims",
            grants=[Grant(subject="alice@co.com", roles=["viewer"])],
        )
        app = _admin_app(mocker, services={"lims": sg})
        resp = TestClient(app).get("/admin/grants/lims")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "lims"
        assert len(data["grants"]) == 1

    def test_not_found(self, mocker):
        app = _admin_app(mocker)
        resp = TestClient(app).get("/admin/grants/nonexistent")
        assert resp.status_code == 404


class TestPutGrants:
    def test_creates_grants(self, mocker):
        app = _admin_app(mocker)
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
    def test_deletes_grants(self, mocker):
        sg = ServiceGrants(service="lims", grants=[])
        app = _admin_app(mocker, services={"lims": sg})
        resp = TestClient(app).delete("/admin/grants/lims")
        assert resp.status_code == 204
        _get_admin_storage(app).delete_service_grants.assert_called_once()
        _get_authority(app).clear_cache.assert_called_once()

    def test_not_found(self, mocker):
        app = _admin_app(mocker)
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

    def test_write_without_admin_storage_returns_503(self, mocker):
        from dockmaster.routes.admin import router

        app = FastAPI()
        app.include_router(router, prefix="/admin")

        test_settings = Settings(_env_file=None, dockmaster_admin_emails={"admin@co.com"})
        app.state.settings = test_settings
        app.state.authority = mocker.AsyncMock()
        app.state.authority.has_permission.return_value = True
        app.state.admin_storage = None

        from dockmaster.auth.dependencies import allow_jwt_admin

        app.dependency_overrides[allow_jwt_admin] = lambda: {"email": "admin@co.com"}

        resp = TestClient(app).post(
            "/admin/roles",
            json={"name": "viewer", "permissions": ["read"]},
        )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


def _session_store_with_data():
    """Return an InMemorySessionStore pre-populated with test sessions."""
    import time

    from dockmaster.sessions.memory import InMemorySessionStore

    store = InMemorySessionStore()
    now = time.time()
    store._store["sess-1"] = ({"email": "alice@co.com", "name": "Alice"}, now + 3600)
    store._store["sess-2"] = ({"email": "alice@co.com", "name": "Alice"}, now + 3600)
    store._store["sess-3"] = ({"email": "bob@co.com", "name": "Bob"}, now + 3600)
    return store


class TestListSessions:
    def test_returns_all_sessions(self, mocker):
        store = _session_store_with_data()
        app = _admin_app(mocker, session_store=store)
        resp = TestClient(app).get("/admin/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert "sess-1" in data
        assert "sess-3" in data

    def test_returns_empty_when_no_sessions(self, mocker):
        from dockmaster.sessions.memory import InMemorySessionStore

        app = _admin_app(mocker, session_store=InMemorySessionStore())
        resp = TestClient(app).get("/admin/sessions")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_503_when_session_store_not_configured(self, mocker):
        app = _admin_app(mocker)
        resp = TestClient(app).get("/admin/sessions")
        assert resp.status_code == 503


class TestListSessionsByEmail:
    def test_filters_by_email(self, mocker):
        store = _session_store_with_data()
        app = _admin_app(mocker, session_store=store)
        resp = TestClient(app).get("/admin/sessions/email/alice@co.com")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(v["email"] == "alice@co.com" for v in data.values())

    def test_no_match_returns_empty(self, mocker):
        store = _session_store_with_data()
        app = _admin_app(mocker, session_store=store)
        resp = TestClient(app).get("/admin/sessions/email/nobody@co.com")
        assert resp.status_code == 200
        assert resp.json() == {}


class TestRevokeSessionById:
    def test_revokes_session(self, mocker):
        store = _session_store_with_data()
        app = _admin_app(mocker, session_store=store)
        resp = TestClient(app).delete("/admin/sessions/id/sess-1")
        assert resp.status_code == 200
        assert resp.json()["revoked"] is True
        # Verify session is gone
        resp2 = TestClient(app).get("/admin/sessions")
        assert "sess-1" not in resp2.json()

    def test_not_found_returns_404(self, mocker):
        store = _session_store_with_data()
        app = _admin_app(mocker, session_store=store)
        resp = TestClient(app).delete("/admin/sessions/id/nonexistent")
        assert resp.status_code == 404


class TestRevokeSessionsByEmail:
    def test_revokes_all_for_email(self, mocker):
        store = _session_store_with_data()
        app = _admin_app(mocker, session_store=store)
        resp = TestClient(app).delete("/admin/sessions/email/alice@co.com")
        assert resp.status_code == 200
        assert resp.json()["revoked"] == 2
        # Bob's session still there
        resp2 = TestClient(app).get("/admin/sessions")
        data = resp2.json()
        assert len(data) == 1
        assert "sess-3" in data

    def test_no_match_returns_zero(self, mocker):
        store = _session_store_with_data()
        app = _admin_app(mocker, session_store=store)
        resp = TestClient(app).delete("/admin/sessions/email/nobody@co.com")
        assert resp.status_code == 200
        assert resp.json()["revoked"] == 0


class TestSessionAdminAuth:
    def test_unauthenticated_list_returns_401(self):
        from dockmaster.routes.admin import router

        app = FastAPI()
        app.include_router(router, prefix="/admin")
        app.state.authority = None
        app.state.admin_storage = None
        app.state.session_store = None

        resp = TestClient(app).get("/admin/sessions")
        assert resp.status_code == 401

    def test_unauthenticated_revoke_returns_401(self):
        from dockmaster.routes.admin import router

        app = FastAPI()
        app.include_router(router, prefix="/admin")
        app.state.authority = None
        app.state.admin_storage = None
        app.state.session_store = None

        resp = TestClient(app).delete("/admin/sessions/id/some-id")
        assert resp.status_code == 401
