"""Shared pytest fixtures for dockmaster tests."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockmaster.config import Settings, get_settings
from dockmaster.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    """Settings with safe test defaults - no real GCP credentials."""
    return Settings(
        log_level="DEBUG",
        authorized_issuers={"https://accounts.google.com"},
        authorized_domains={"example.com"},
        authorized_audience={"test-audience"},
        client_id="test-client-id",
        client_secret="test-client-secret",
        session_secret_key="test-secret-key",
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    """FastAPI app wired with test settings."""
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: test_settings
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Synchronous test client for the app."""
    with TestClient(app) as c:
        yield c
