"""Tests for POST /auth/cli/token — issue Type C JWT via Bearer JWT (CLI path)."""

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockmaster.auth.jwt_signers import EphemeralKeypairSigner
from dockmaster.config import Settings


@pytest.fixture
def cli_settings() -> Settings:
    return Settings(
        log_level="DEBUG",
        session_secret_key="test-secret",
        authorized_domains={"example.com"},
    )


@pytest.fixture
def token_issuer() -> EphemeralKeypairSigner:
    return EphemeralKeypairSigner(ttl=900)


@pytest.fixture
def cli_client(app: FastAPI, cli_settings: Settings, token_issuer: EphemeralKeypairSigner, fake_realm) -> TestClient:
    """TestClient wired for CLI route tests."""
    app.state.settings = cli_settings
    with TestClient(app) as client:
        app.state.token_issuer = token_issuer
        app.state.realm = fake_realm
        yield client


class TestCliToken:
    """POST /auth/cli/token."""

    def test_bearer_auth_returns_token(self, cli_client, signer, token_issuer):
        """Valid Bearer JWT + service → 200 with Type C JWT."""
        input_token = signer.sign(subject="cli-user@example.com", audience="dockmaster")

        response = cli_client.post(
            "/auth/cli/token?service=billing",
            headers={"Authorization": f"Bearer {input_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900

        claims = pyjwt.decode(data["access_token"], options={"verify_signature": False})
        assert claims["iss"] == "dockmaster"
        assert claims["sub"] == "cli-user@example.com"
        assert claims["aud"] == "billing"

    def test_missing_service_param(self, cli_client, signer):
        """Bearer auth without ?service= → 400."""
        input_token = signer.sign(subject="user@example.com", audience="dockmaster")

        response = cli_client.post(
            "/auth/cli/token",
            headers={"Authorization": f"Bearer {input_token}"},
        )

        assert response.status_code == 400

    def test_no_bearer_returns_401(self, cli_client):
        """No Authorization header → 401."""
        response = cli_client.post("/auth/cli/token?service=billing")
        assert response.status_code == 401

    def test_invalid_bearer_returns_401(self, cli_client):
        """Invalid Bearer token → 401."""
        response = cli_client.post(
            "/auth/cli/token?service=billing",
            headers={"Authorization": "Bearer not.a.valid.token"},
        )
        assert response.status_code == 401

    def test_503_when_issuer_not_configured(self, app, cli_settings, signer, fake_realm):
        """Returns 503 when token_issuer is not available."""
        app.state.settings = cli_settings
        input_token = signer.sign(subject="user@example.com", audience="dockmaster")
        with TestClient(app) as client:
            app.state.token_issuer = None
            app.state.realm = fake_realm
            response = client.post(
                "/auth/cli/token?service=billing",
                headers={"Authorization": f"Bearer {input_token}"},
            )
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]
