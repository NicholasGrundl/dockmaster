"""Tests for health and root info endpoints."""

import dockmaster


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

    def test_root_response_body(self, client):
        response = client.get("/")
        data = response.json()
        assert data["service"] == "dockmaster"
        assert data["version"] == dockmaster.__version__
        assert data["health"] == "/auth/health"
        assert data["docs"] == "/docs"


class TestOpenAPI:
    """Test OpenAPI schema availability."""

    def test_openapi_available(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "/auth/health" in schema["paths"]
