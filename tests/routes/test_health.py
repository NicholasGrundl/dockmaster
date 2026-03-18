"""Tests for health and root info endpoints."""

import dockmaster

from dockmaster.config import Settings


class TestHealthEndpoint:
    """Test GET /auth/health."""

    def test_health_returns_200(self, client):
        response = client.get("/auth/health")
        assert response.status_code == 200

    def test_health_response_body(self, client):
        response = client.get("/auth/health")
        data = response.json()
        assert data == {"service": "dockmaster", "status": "ok"}

    def test_health_content_type(self, client):
        response = client.get("/auth/health")
        assert response.headers["content-type"] == "application/json"


class TestRootEndpoint:
    """Test GET / (service info)."""

    def test_root_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_includes_docs_when_enabled(self, test_app_factory):
        """When enable_docs=True, docs URL is included in root response."""
        with test_app_factory(Settings(enable_docs=True, session_secret_key="test", require_proxy_headers=False)) as c:
            data = c.get("/").json()
            assert data["service"] == "dockmaster"
            assert data["version"] == dockmaster.__version__
            assert data["health"] == "/auth/health"
            assert data["docs"] == "/docs"

    def test_root_hides_docs_when_disabled(self, test_app_factory):
        """When enable_docs=False (production default), docs URL is null."""
        with test_app_factory(Settings(enable_docs=False, session_secret_key="test", require_proxy_headers=False)) as c:
            data = c.get("/").json()
            assert data["docs"] is None


class TestOpenAPI:
    """Test OpenAPI schema availability."""

    def test_openapi_available_when_enabled(self, test_app_factory):
        """When enable_docs=True, OpenAPI schema is served."""
        with test_app_factory(Settings(enable_docs=True, session_secret_key="test", require_proxy_headers=False)) as c:
            response = c.get("/openapi.json")
            assert response.status_code == 200
            schema = response.json()
            assert "/auth/health" in schema["paths"]

    def test_openapi_disabled_by_default(self, test_app_factory):
        """When enable_docs=False (production default), OpenAPI returns 404."""
        with test_app_factory(Settings(enable_docs=False, session_secret_key="test", require_proxy_headers=False)) as c:
            assert c.get("/openapi.json").status_code == 404
            assert c.get("/docs").status_code == 404
            assert c.get("/redoc").status_code == 404
