"""Tests for POST /auth/token — issue Type C JWT for a target service."""

from __future__ import annotations

import asyncio

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from dockmaster.auth.jwt_signers import EphemeralKeypairSigner
from dockmaster.config import Settings, get_settings
from dockmaster.sessions.memory import InMemorySessionStore


@pytest.fixture
def token_issuer() -> EphemeralKeypairSigner:
    return EphemeralKeypairSigner(ttl=900)


@pytest.fixture
def session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def token_settings() -> Settings:
    return Settings(
        log_level="DEBUG",
        session_secret_key="test-secret",
        authorized_domains={"example.com"},
    )


@pytest.fixture
def token_client(
    app: FastAPI, token_settings: Settings, token_issuer: EphemeralKeypairSigner, session_store: InMemorySessionStore
) -> TestClient:
    """TestClient with token_issuer and session_store wired."""
    app.dependency_overrides[get_settings] = lambda: token_settings
    with TestClient(app) as client:
        app.state.token_issuer = token_issuer
        app.state.session_store = session_store
        yield client


def _create_session_cookie(
    session_store: InMemorySessionStore, settings: Settings, email: str = "user@example.com", ttl: int = 3600
) -> str:
    """Create a session and return the signed cookie value."""
    session_id = f"test-session-{email}"
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(session_store.set(session_id, {"email": email, "name": "Test User"}, ttl=ttl))
    finally:
        loop.close()
    signer = URLSafeSerializer(settings.session_secret_key)
    return signer.dumps(session_id)


class TestTokenEndpointSessionAuth:
    """POST /auth/token with session cookie auth (browser path)."""

    def test_session_auth_returns_token(self, token_client, token_issuer, session_store, token_settings):
        """Valid session + service param → 200 with Type C JWT."""
        cookie = _create_session_cookie(session_store, token_settings)
        token_client.cookies.set("session_id", cookie)

        response = token_client.post("/auth/token?service=billing")

        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900
        assert data["refresh_token"] is None
        assert "access_token" in data

        # Verify the output is a Type C JWT
        claims = pyjwt.decode(data["access_token"], options={"verify_signature": False})
        assert claims["iss"] == "dockmaster"
        assert claims["sub"] == "user@example.com"
        assert claims["aud"] == "billing"

    def test_session_auth_custom_service(self, token_client, session_store, token_settings):
        """Service param controls the aud claim."""
        cookie = _create_session_cookie(session_store, token_settings)
        token_client.cookies.set("session_id", cookie)

        response = token_client.post("/auth/token?service=analytics")

        claims = pyjwt.decode(response.json()["access_token"], options={"verify_signature": False})
        assert claims["aud"] == "analytics"

    def test_missing_service_param(self, token_client, session_store, token_settings):
        """No ?service= → 400."""
        cookie = _create_session_cookie(session_store, token_settings)
        token_client.cookies.set("session_id", cookie)

        response = token_client.post("/auth/token")

        assert response.status_code == 400
        assert "service" in response.json()["detail"].lower()


class TestTokenEndpointBearerAuth:
    """POST /auth/token with Bearer JWT auth (CLI path)."""

    def test_bearer_auth_returns_token(self, token_client, app, signer, fake_realm, token_issuer):
        """Valid Bearer JWT + service → 200 with Type C JWT."""
        app.state.realm = fake_realm
        input_token = signer.sign(subject="cli-user@example.com", audience="dockmaster")

        response = token_client.post(
            "/auth/token?service=billing",
            headers={"Authorization": f"Bearer {input_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"

        claims = pyjwt.decode(data["access_token"], options={"verify_signature": False})
        assert claims["iss"] == "dockmaster"
        assert claims["sub"] == "cli-user@example.com"
        assert claims["aud"] == "billing"

    def test_bearer_auth_missing_service(self, token_client, app, signer, fake_realm):
        """Bearer auth without ?service= → 400."""
        app.state.realm = fake_realm
        input_token = signer.sign(subject="user@example.com", audience="dockmaster")

        response = token_client.post(
            "/auth/token",
            headers={"Authorization": f"Bearer {input_token}"},
        )

        assert response.status_code == 400


class TestTokenEndpointErrors:
    """Error cases for /auth/token."""

    def test_no_auth_returns_401(self, token_client):
        """No session cookie and no Bearer token → 401."""
        response = token_client.post("/auth/token?service=billing")
        assert response.status_code == 401

    def test_invalid_session_cookie_falls_through(self, token_client):
        """Invalid session cookie + no Bearer → 401."""
        token_client.cookies.set("session_id", "garbage")
        response = token_client.post("/auth/token?service=billing")
        assert response.status_code == 401

    def test_expired_session_falls_through(self, token_client, session_store, token_settings):
        """Expired session + no Bearer → 401."""
        cookie = _create_session_cookie(session_store, token_settings, ttl=0)
        token_client.cookies.set("session_id", cookie)

        response = token_client.post("/auth/token?service=billing")
        assert response.status_code == 401

    def test_503_when_issuer_not_configured(self, app, test_settings):
        """Returns 503 when token_issuer is not available."""
        app.dependency_overrides[get_settings] = lambda: test_settings
        with TestClient(app) as client:
            app.state.token_issuer = None
            response = client.post("/auth/token?service=billing")
        assert response.status_code == 503
