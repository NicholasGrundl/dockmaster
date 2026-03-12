"""Tests for GET /auth/has — permission check endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockmaster.rbac.authority import Authority


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_authority() -> MagicMock:
    """Authority mock with async has_permission."""
    auth = MagicMock(spec=Authority)
    auth.has_permission = AsyncMock(return_value=True)
    return auth


@pytest.fixture
def perm_client(app: FastAPI, fake_realm, mock_authority: MagicMock) -> TestClient:
    """TestClient with realm + authority wired."""
    with TestClient(app) as c:
        app.state.realm = fake_realm
        app.state.authority = mock_authority
        yield c


# ---------------------------------------------------------------------------
# Path-based: GET /auth/has/{subject}/{target}/{permission}
# ---------------------------------------------------------------------------


class TestPathEndpoint:
    def test_granted_returns_204(self, perm_client, valid_token, mock_authority):
        mock_authority.has_permission.return_value = True
        resp = perm_client.get(
            "/auth/has/alice@example.com/data-pipeline/read",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 204
        assert resp.content == b""

    def test_denied_returns_403(self, perm_client, valid_token, mock_authority):
        mock_authority.has_permission.return_value = False
        resp = perm_client.get(
            "/auth/has/alice@example.com/data-pipeline/write",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body["status"] == "Error"
        assert "alice@example.com" in body["message"]
        assert "write" in body["message"]
        assert "data-pipeline" in body["message"]

    def test_requires_auth(self, perm_client):
        """No Bearer token → 401."""
        resp = perm_client.get("/auth/has/alice@example.com/data-pipeline/read")
        assert resp.status_code == 401

    def test_permission_with_colon(self, perm_client, valid_token, mock_authority):
        """Permissions like 'experiment:approve' work in path params."""
        mock_authority.has_permission.return_value = True
        resp = perm_client.get(
            "/auth/has/alice@example.com/experiments/experiment:approve",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 204
        mock_authority.has_permission.assert_called_with("alice@example.com", "experiments", "experiment:approve")


# ---------------------------------------------------------------------------
# Query-based: GET /auth/has?subject=X&target=Y&permission=Z
# ---------------------------------------------------------------------------


class TestQueryEndpoint:
    def test_granted_returns_204(self, perm_client, valid_token, mock_authority):
        mock_authority.has_permission.return_value = True
        resp = perm_client.get(
            "/auth/has",
            params={"subject": "alice@example.com", "target": "data-pipeline", "permission": "read"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 204

    def test_denied_returns_403(self, perm_client, valid_token, mock_authority):
        mock_authority.has_permission.return_value = False
        resp = perm_client.get(
            "/auth/has",
            params={"subject": "bob@example.com", "target": "data-pipeline", "permission": "write"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 403
        assert "bob@example.com" in resp.json()["message"]

    def test_requires_auth(self, perm_client):
        resp = perm_client.get(
            "/auth/has",
            params={"subject": "a@b.com", "target": "svc", "permission": "read"},
        )
        assert resp.status_code == 401

    def test_missing_params_returns_422(self, perm_client, valid_token):
        """Missing required query params → 422 (FastAPI validation)."""
        resp = perm_client.get(
            "/auth/has",
            params={"subject": "a@b.com"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_authority_exception_returns_500(self, perm_client, valid_token, mock_authority):
        mock_authority.has_permission.side_effect = RuntimeError("SM down")
        resp = perm_client.get(
            "/auth/has/alice@example.com/data-pipeline/read",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 500

    def test_no_authority_returns_503(self, app, fake_realm, valid_token):
        """Authority not configured → 503."""
        with TestClient(app) as c:
            app.state.realm = fake_realm
            app.state.authority = None
            resp = c.get(
                "/auth/has/alice@example.com/data-pipeline/read",
                headers={"Authorization": f"Bearer {valid_token}"},
            )
            assert resp.status_code == 503
