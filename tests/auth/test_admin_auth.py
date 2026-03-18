"""Tests for admin authorization dependencies."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from dockmaster.config import Settings


# ---------------------------------------------------------------------------
# _is_admin — pure logic
# ---------------------------------------------------------------------------


class TestIsAdmin:
    @pytest.fixture(autouse=True)
    def _import(self):
        from dockmaster.auth.dependencies import check_permission

        self._is_admin = check_permission

    @pytest.mark.anyio
    async def test_rbac_admin_grants_access(self, mocker):
        authority = mocker.AsyncMock()
        authority.has_permission.return_value = True

        result = await self._is_admin("admin@co.com", "dockmaster", "admin", authority)
        assert result is True
        authority.has_permission.assert_called_once_with("admin@co.com", "dockmaster", "admin")

    @pytest.mark.anyio
    async def test_whitelist_bypasses_rbac(self, mocker):
        authority = mocker.AsyncMock()
        authority.has_permission.return_value = False

        result = await self._is_admin(
            "admin@co.com", "dockmaster", "admin", authority, whitelist_emails={"admin@co.com"}
        )
        assert result is True
        # Whitelist is checked first — RBAC is never called
        authority.has_permission.assert_not_called()

    @pytest.mark.anyio
    async def test_denied_when_no_rbac_no_whitelist(self, mocker):
        authority = mocker.AsyncMock()
        authority.has_permission.return_value = False

        result = await self._is_admin("nobody@co.com", "dockmaster", "admin", authority)
        assert result is False

    @pytest.mark.anyio
    async def test_denied_when_no_rbac_wrong_email(self, mocker):
        authority = mocker.AsyncMock()
        authority.has_permission.return_value = False

        result = await self._is_admin(
            "nobody@co.com", "dockmaster", "admin", authority, whitelist_emails={"admin@co.com"}
        )
        assert result is False

    @pytest.mark.anyio
    async def test_no_authority_uses_whitelist_only(self):
        result = await self._is_admin(
            "admin@co.com", "dockmaster", "admin", None, whitelist_emails={"admin@co.com"}
        )
        assert result is True

    @pytest.mark.anyio
    async def test_no_authority_no_whitelist_denied(self):
        result = await self._is_admin("admin@co.com", "dockmaster", "admin", None)
        assert result is False


# ---------------------------------------------------------------------------
# Helpers for endpoint tests
# ---------------------------------------------------------------------------


_SENTINEL = object()


def _admin_app(
    mocker,
    *,
    authority=None,
    admin_emails: set[str] | None = None,
    admin_storage: object | None = _SENTINEL,
) -> FastAPI:
    """Build a minimal app with admin-protected routes for testing."""
    from dockmaster.auth.dependencies import allow_jwt_admin, needs_admin_storage

    app = FastAPI()

    app.state.settings = Settings(
        _env_file=None,
        dockmaster_admin_emails=admin_emails or set(),
    )
    app.state.authority = authority
    app.state.admin_storage = mocker.MagicMock() if admin_storage is _SENTINEL else admin_storage

    @app.get("/admin/test-read")
    async def admin_read(admin: dict = Depends(allow_jwt_admin)):
        return {"status": "ok", "email": admin["email"]}

    @app.get("/admin/test-write")
    async def admin_write(
        admin: dict = Depends(allow_jwt_admin),
        _: None = Depends(needs_admin_storage),
    ):
        return {"status": "ok"}

    return app


def _override_jwt_user(app: FastAPI, email: str) -> None:
    """Override allow_jwt to return a user dict with the given email."""
    from dockmaster.auth.dependencies import allow_jwt

    app.dependency_overrides[allow_jwt] = lambda: {"email": email, "sub": email}


# ---------------------------------------------------------------------------
# allow_jwt_admin — JWT auth + admin check
# ---------------------------------------------------------------------------


class TestRequireAdminApi:
    def test_no_auth_returns_401(self, mocker):
        app = _admin_app(mocker)
        client = TestClient(app)
        resp = client.get("/admin/test-read")
        assert resp.status_code == 401

    def test_rbac_admin_passes(self, mocker):
        authority = mocker.AsyncMock()
        authority.has_permission.return_value = True
        app = _admin_app(mocker, authority=authority)
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@co.com"

    def test_whitelist_fallback_passes(self, mocker):
        authority = mocker.AsyncMock()
        authority.has_permission.return_value = False
        app = _admin_app(mocker, authority=authority, admin_emails={"admin@co.com"})
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 200

    def test_non_admin_returns_403(self, mocker):
        authority = mocker.AsyncMock()
        authority.has_permission.return_value = False
        app = _admin_app(mocker, authority=authority)
        _override_jwt_user(app, "nobody@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 403

    def test_no_authority_whitelist_works(self, mocker):
        app = _admin_app(mocker, authority=None, admin_emails={"admin@co.com"})
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 200

    def test_no_authority_no_whitelist_returns_403(self, mocker):
        app = _admin_app(mocker, authority=None)
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# needs_admin_storage — capability gate
# ---------------------------------------------------------------------------


class TestRequireAdminWrites:
    def test_write_with_admin_client_passes(self, mocker):
        authority = mocker.AsyncMock()
        authority.has_permission.return_value = True
        app = _admin_app(mocker, authority=authority, admin_storage=mocker.MagicMock())
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-write")
        assert resp.status_code == 200

    def test_write_without_admin_client_returns_503(self, mocker):
        authority = mocker.AsyncMock()
        authority.has_permission.return_value = True
        app = _admin_app(mocker, authority=authority, admin_storage=None)
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-write")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Write operations are not available"
