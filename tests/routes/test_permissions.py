"""Tests for GET /auth/has — permission check endpoints."""


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockmaster.rbac.authority import Authority


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_authority(mocker):
    """Authority mock with async has_permission."""
    auth = mocker.MagicMock(spec=Authority)
    auth.has_permission = mocker.AsyncMock(return_value=True)
    return auth


@pytest.fixture
def perm_client(app: FastAPI, fake_realm, mock_authority) -> TestClient:
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
        assert "alice@example.com" in body["detail"]
        assert "write" in body["detail"]
        assert "data-pipeline" in body["detail"]

    def test_requires_auth(self, perm_client):
        """No Bearer token -> 401."""
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
        assert "bob@example.com" in resp.json()["detail"]

    def test_requires_auth(self, perm_client):
        resp = perm_client.get(
            "/auth/has",
            params={"subject": "a@b.com", "target": "svc", "permission": "read"},
        )
        assert resp.status_code == 401

    def test_missing_params_returns_422(self, perm_client, valid_token):
        """Missing required query params -> 422 (FastAPI validation)."""
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
        """Authority not configured -> 503."""
        with TestClient(app) as c:
            app.state.realm = fake_realm
            app.state.authority = None
            resp = c.get(
                "/auth/has/alice@example.com/data-pipeline/read",
                headers={"Authorization": f"Bearer {valid_token}"},
            )
            assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /auth/grants — grants resolution
# ---------------------------------------------------------------------------


class TestGrantsEndpoint:
    def test_returns_resolved_grants(self, mocker, perm_client, valid_token, mock_authority):
        """Grants endpoint returns resolved permissions as target:perm strings."""
        mock_authority.get_permissions = mocker.AsyncMock(return_value={"read", "write"})
        resp = perm_client.get(
            "/auth/grants",
            params={"subject": "alice@example.com", "target": "billing"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["subject"] == "alice@example.com"
        assert data["target"] == "billing"
        assert sorted(data["grants"]) == ["billing:read", "billing:write"]

    def test_empty_grants_for_unknown_subject(self, mocker, perm_client, valid_token, mock_authority):
        """Unknown subject returns empty grants list."""
        mock_authority.get_permissions = mocker.AsyncMock(return_value=set())
        resp = perm_client.get(
            "/auth/grants",
            params={"subject": "nobody@example.com", "target": "billing"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["grants"] == []

    def test_requires_auth(self, perm_client):
        """No Bearer token -> 401."""
        resp = perm_client.get(
            "/auth/grants",
            params={"subject": "alice@example.com", "target": "billing"},
        )
        assert resp.status_code == 401

    def test_missing_params_returns_422(self, perm_client, valid_token):
        """Missing required query params -> 422."""
        resp = perm_client.get(
            "/auth/grants",
            params={"subject": "alice@example.com"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 422

    def test_authority_error_returns_500(self, mocker, perm_client, valid_token, mock_authority):
        mock_authority.get_permissions = mocker.AsyncMock(side_effect=RuntimeError("SM down"))
        resp = perm_client.get(
            "/auth/grants",
            params={"subject": "alice@example.com", "target": "billing"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 500

    def test_no_authority_returns_503(self, app, fake_realm, valid_token):
        """Authority not configured -> 503."""
        with TestClient(app) as c:
            app.state.realm = fake_realm
            app.state.authority = None
            resp = c.get(
                "/auth/grants",
                params={"subject": "alice@example.com", "target": "billing"},
                headers={"Authorization": f"Bearer {valid_token}"},
            )
            assert resp.status_code == 503
