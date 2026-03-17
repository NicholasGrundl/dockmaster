"""Tests for CORS middleware configuration."""

import pytest
from fastapi.testclient import TestClient

from dockmaster.config import Settings
from dockmaster.main import create_app


@pytest.fixture
def cors_settings() -> Settings:
    """Settings with CORS origins configured."""
    return Settings(
        allowed_origins={"https://app.example.com", "https://other.example.com"},
        session_secret_key="test-secret",
        _env_file=None,
    )


@pytest.fixture
def cors_app(cors_settings: Settings):
    """App created with CORS middleware active."""
    return create_app(cors_settings)


@pytest.fixture
def cors_client(cors_app) -> TestClient:
    with TestClient(cors_app) as c:
        yield c


@pytest.fixture
def no_cors_client() -> TestClient:
    """App with no allowed_origins — CORS middleware should not be added."""
    settings = Settings(allowed_origins=set(), session_secret_key="test-secret", _env_file=None)
    application = create_app(settings)
    with TestClient(application) as c:
        yield c


class TestCORSHeaders:
    """CORS middleware adds correct headers for allowed origins."""

    def test_preflight_allowed_origin(self, cors_client: TestClient):
        """OPTIONS preflight from an allowed origin gets CORS headers."""
        resp = cors_client.options(
            "/auth/health",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers["access-control-allow-origin"] == "https://app.example.com"
        assert "GET" in resp.headers["access-control-allow-methods"]
        assert "POST" in resp.headers["access-control-allow-methods"]
        assert resp.headers["access-control-allow-credentials"] == "true"

    def test_preflight_disallowed_origin(self, cors_client: TestClient):
        """OPTIONS preflight from a non-allowed origin gets no CORS headers."""
        resp = cors_client.options(
            "/auth/health",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in resp.headers

    def test_simple_request_allowed_origin(self, cors_client: TestClient):
        """GET from an allowed origin gets CORS headers on the response."""
        resp = cors_client.get(
            "/auth/health",
            headers={"Origin": "https://other.example.com"},
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "https://other.example.com"

    def test_simple_request_no_origin(self, cors_client: TestClient):
        """Request without Origin header — no CORS headers added."""
        resp = cors_client.get("/auth/health")
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers

    def test_allowed_headers(self, cors_client: TestClient):
        """Preflight should allow Authorization and Content-Type headers."""
        resp = cors_client.options(
            "/auth/health",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        allowed = resp.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" in allowed
        assert "content-type" in allowed


class TestCORSDisabled:
    """When allowed_origins is empty, no CORS middleware is added."""

    def test_no_cors_headers_when_disabled(self, no_cors_client: TestClient):
        """Without allowed_origins, no CORS headers appear even with Origin."""
        resp = no_cors_client.get(
            "/auth/health",
            headers={"Origin": "https://app.example.com"},
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers
