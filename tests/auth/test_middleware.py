"""Tests for middleware: JWT auth dependency and proxy header enforcement."""

from fastapi.testclient import TestClient

from dockmaster.config import Settings
from dockmaster.main import create_app


class TestRequireProxyHeadersMiddleware:
    """Tests for RequireProxyHeadersMiddleware (default: enabled)."""

    def test_returns_502_when_header_missing(self):
        """Explicit require_proxy_headers=True — missing X-Forwarded-Proto returns 502."""
        settings = Settings(
            require_proxy_headers=True,
            session_secret_key="test-secret",
            _env_file=None,
        )
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/auth/health")
            assert response.status_code == 502
            assert "proxy" in response.json()["detail"].lower()

    def test_passes_when_header_present(self):
        """Requests with X-Forwarded-Proto pass through normally."""
        settings = Settings(
            session_secret_key="test-secret",
            _env_file=None,
        )
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/auth/health",
                headers={"X-Forwarded-Proto": "https"},
            )
            assert response.status_code == 200

    def test_disabled_allows_requests_without_header(self):
        """With require_proxy_headers=False, requests without the header pass through."""
        settings = Settings(
            require_proxy_headers=False,
            session_secret_key="test-secret",
            _env_file=None,
        )
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/auth/health")
            assert response.status_code == 200


class TestAllowJwt:
    def test_valid_token_returns_claims(self, auth_client, valid_token):
        response = auth_client.get("/auth/claims", headers={"Authorization": f"Bearer {valid_token}"})
        assert response.status_code == 200
        claims = response.json()
        assert claims["sub"] == "test@example.com"
        assert claims["email"] == "test@example.com"

    def test_missing_bearer_returns_401(self, auth_client):
        response = auth_client.get("/auth/claims")
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, auth_client):
        response = auth_client.get("/auth/claims", headers={"Authorization": "Bearer not.a.token"})
        assert response.status_code == 401

    def test_malformed_bearer_returns_401(self, auth_client):
        response = auth_client.get("/auth/claims", headers={"Authorization": "Bearer"})
        assert response.status_code == 401

    def test_realm_not_configured_returns_503(self, app, client):
        """When app.state.realm is None, auth returns 503."""
        app.state.realm = None
        response = client.get("/auth/claims", headers={"Authorization": "Bearer some.fake.token"})
        assert response.status_code == 503
