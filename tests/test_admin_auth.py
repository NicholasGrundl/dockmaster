"""Tests for admin authorization dependencies."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from dockmaster.config import Settings, get_settings


# ---------------------------------------------------------------------------
# _is_admin — pure logic
# ---------------------------------------------------------------------------


class TestIsAdmin:
    @pytest.fixture(autouse=True)
    def _import(self):
        from dockmaster.auth.admin import _is_admin

        self._is_admin = _is_admin

    @pytest.mark.anyio
    async def test_rbac_admin_grants_access(self):
        authority = AsyncMock()
        authority.has_permission.return_value = True

        result = await self._is_admin("admin@co.com", authority, set())
        assert result is True
        authority.has_permission.assert_called_once_with("admin@co.com", "dockmaster", "admin")

    @pytest.mark.anyio
    async def test_email_whitelist_fallback(self):
        authority = AsyncMock()
        authority.has_permission.return_value = False

        result = await self._is_admin("admin@co.com", authority, {"admin@co.com"})
        assert result is True

    @pytest.mark.anyio
    async def test_denied_when_no_rbac_no_whitelist(self):
        authority = AsyncMock()
        authority.has_permission.return_value = False

        result = await self._is_admin("nobody@co.com", authority, set())
        assert result is False

    @pytest.mark.anyio
    async def test_denied_when_no_rbac_wrong_email(self):
        authority = AsyncMock()
        authority.has_permission.return_value = False

        result = await self._is_admin("nobody@co.com", authority, {"admin@co.com"})
        assert result is False

    @pytest.mark.anyio
    async def test_no_authority_uses_whitelist_only(self):
        result = await self._is_admin("admin@co.com", None, {"admin@co.com"})
        assert result is True

    @pytest.mark.anyio
    async def test_no_authority_no_whitelist_denied(self):
        result = await self._is_admin("admin@co.com", None, set())
        assert result is False


# ---------------------------------------------------------------------------
# Helpers for endpoint tests
# ---------------------------------------------------------------------------


def _admin_app(
    *,
    authority: AsyncMock | None = None,
    admin_emails: set[str] | None = None,
    admin_storage: object | None = MagicMock(),
) -> FastAPI:
    """Build a minimal app with admin-protected routes for testing."""
    from dockmaster.auth.admin import require_admin_api, require_admin_writes

    app = FastAPI()

    test_settings = Settings(
        _env_file=None,
        dockmaster_admin_emails=admin_emails or set(),
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.state.authority = authority
    app.state.admin_storage = admin_storage

    @app.get("/admin/test-read")
    async def admin_read(admin: dict = Depends(require_admin_api)):
        return {"status": "ok", "email": admin["email"]}

    @app.get("/admin/test-write")
    async def admin_write(
        admin: dict = Depends(require_admin_api),
        _: None = Depends(require_admin_writes),
    ):
        return {"status": "ok"}

    return app


def _override_jwt_user(app: FastAPI, email: str) -> None:
    """Override get_current_user to return a user dict with the given email."""
    from dockmaster.auth.middleware import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"email": email, "sub": email}


# ---------------------------------------------------------------------------
# require_admin_api — JWT auth + admin check
# ---------------------------------------------------------------------------


class TestRequireAdminApi:
    def test_no_auth_returns_401(self):
        app = _admin_app()
        client = TestClient(app)
        resp = client.get("/admin/test-read")
        assert resp.status_code == 401

    def test_rbac_admin_passes(self):
        authority = AsyncMock()
        authority.has_permission.return_value = True
        app = _admin_app(authority=authority)
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@co.com"

    def test_whitelist_fallback_passes(self):
        authority = AsyncMock()
        authority.has_permission.return_value = False
        app = _admin_app(authority=authority, admin_emails={"admin@co.com"})
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 200

    def test_non_admin_returns_403(self):
        authority = AsyncMock()
        authority.has_permission.return_value = False
        app = _admin_app(authority=authority)
        _override_jwt_user(app, "nobody@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 403

    def test_no_authority_whitelist_works(self):
        app = _admin_app(authority=None, admin_emails={"admin@co.com"})
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 200

    def test_no_authority_no_whitelist_returns_403(self):
        app = _admin_app(authority=None)
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-read")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# require_admin_writes — capability gate
# ---------------------------------------------------------------------------


class TestRequireAdminWrites:
    def test_write_with_admin_client_passes(self):
        authority = AsyncMock()
        authority.has_permission.return_value = True
        app = _admin_app(authority=authority, admin_storage=MagicMock())
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-write")
        assert resp.status_code == 200

    def test_write_without_admin_client_returns_503(self):
        authority = AsyncMock()
        authority.has_permission.return_value = True
        app = _admin_app(authority=authority, admin_storage=None)
        _override_jwt_user(app, "admin@co.com")

        resp = TestClient(app).get("/admin/test-write")
        assert resp.status_code == 503
        assert "admin SA" in resp.json()["detail"].lower() or "not configured" in resp.json()["detail"].lower()
