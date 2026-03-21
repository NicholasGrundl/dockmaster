"""Tests for session-gated routes — /auth/session/principal, /auth/session/token, /auth/session/list."""

import asyncio
import time

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from dockmaster.auth.jwt_signers import EphemeralKeypairSigner
from dockmaster.config import Settings
from dockmaster.sessions.memory import InMemorySessionStore


@pytest.fixture
def session_settings() -> Settings:
    return Settings(
        log_level="DEBUG",
        session_secret_key="test-secret",
        authorized_domains={"example.com"},
    )


@pytest.fixture
def session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def token_issuer() -> EphemeralKeypairSigner:
    return EphemeralKeypairSigner(ttl=900)


@pytest.fixture
def session_client(
    app: FastAPI, session_settings: Settings, session_store: InMemorySessionStore, token_issuer: EphemeralKeypairSigner
) -> TestClient:
    """TestClient wired for session route tests."""
    app.state.settings = session_settings
    with TestClient(app) as client:
        app.state.session_store = session_store
        app.state.token_issuer = token_issuer
        yield client


def _seed_session(store: InMemorySessionStore, session_id: str, data: dict, ttl: int = 3600):
    """Directly seed a session into the store (no async needed)."""
    store._store[session_id] = (data, time.time() + ttl)


def _create_session_cookie(session_store: InMemorySessionStore, settings: Settings, email: str = "user@example.com") -> str:
    """Create a session and return the signed cookie value."""
    session_id = f"test-session-{email}"
    _seed_session(session_store, session_id, {"email": email, "name": "Test User"})
    signer = URLSafeSerializer(settings.session_secret_key)
    return signer.dumps(session_id)


# ------------------------------------------------------------------
# GET /auth/session/principal
# ------------------------------------------------------------------


class TestSessionPrincipal:
    """GET /auth/session/principal."""

    def test_returns_profile_with_active_session(self, session_client, session_store, session_settings):
        """Principal returns profile when session is active."""
        cookie = _create_session_cookie(session_store, session_settings)
        session_client.cookies.set("session_id", cookie)

        response = session_client.get("/auth/session/principal")

        assert response.status_code == 200
        assert response.json()["email"] == "user@example.com"

    def test_returns_401_without_cookie(self, session_client):
        """No session → 401."""
        response = session_client.get("/auth/session/principal")
        assert response.status_code == 401

    def test_returns_401_with_invalid_cookie(self, session_client):
        """Invalid cookie → 401."""
        session_client.cookies.set("session_id", "tampered-value")
        response = session_client.get("/auth/session/principal")
        assert response.status_code == 401


# ------------------------------------------------------------------
# POST /auth/session/token
# ------------------------------------------------------------------


class TestSessionToken:
    """POST /auth/session/token."""

    def test_returns_token_with_valid_session(self, session_client, session_store, session_settings):
        """Valid session + service param → 200 with Type C JWT."""
        cookie = _create_session_cookie(session_store, session_settings)
        session_client.cookies.set("session_id", cookie)

        response = session_client.post("/auth/session/token?service=billing")

        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900
        assert data["refresh_token"] is None

        claims = pyjwt.decode(data["access_token"], options={"verify_signature": False})
        assert claims["iss"] == "dockmaster"
        assert claims["sub"] == "user@example.com"
        assert claims["aud"] == "billing"

    def test_custom_service_audience(self, session_client, session_store, session_settings):
        """Service param controls the aud claim."""
        cookie = _create_session_cookie(session_store, session_settings)
        session_client.cookies.set("session_id", cookie)

        response = session_client.post("/auth/session/token?service=analytics")

        claims = pyjwt.decode(response.json()["access_token"], options={"verify_signature": False})
        assert claims["aud"] == "analytics"

    def test_missing_service_param(self, session_client, session_store, session_settings):
        """No ?service= → 400."""
        cookie = _create_session_cookie(session_store, session_settings)
        session_client.cookies.set("session_id", cookie)

        response = session_client.post("/auth/session/token")

        assert response.status_code == 400
        assert "service" in response.json()["detail"].lower()

    def test_no_auth_returns_401(self, session_client):
        """No session → 401."""
        response = session_client.post("/auth/session/token?service=billing")
        assert response.status_code == 401

    def test_503_when_issuer_not_configured(self, app, session_settings, session_store):
        """Returns 503 when token_issuer is not available."""
        app.state.settings = session_settings
        cookie = _create_session_cookie(session_store, session_settings)
        with TestClient(app) as client:
            app.state.token_issuer = None
            app.state.session_store = session_store
            client.cookies.set("session_id", cookie)
            response = client.post("/auth/session/token?service=billing")
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]


# ------------------------------------------------------------------
# GET /auth/session/list
# ------------------------------------------------------------------


class TestSessionList:
    """GET /auth/session/list."""

    def test_returns_current_user_sessions(self, session_client, session_store, session_settings):
        """Returns only sessions matching the current user's email."""
        signer = URLSafeSerializer(session_settings.session_secret_key)
        session_id = "my-session"
        signed = signer.dumps(session_id)

        _seed_session(session_store, session_id, {"email": "user@example.com", "name": "Me"})
        _seed_session(session_store, "other-session", {"email": "user@example.com", "name": "Me"})
        _seed_session(session_store, "bob-session", {"email": "bob@example.com", "name": "Bob"})

        session_client.cookies.set("session_id", signed)
        response = session_client.get("/auth/session/list")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert "my-session" in data
        assert "other-session" in data
        assert "bob-session" not in data

    def test_no_auth_returns_401(self, session_client):
        """No session → 401."""
        response = session_client.get("/auth/session/list")
        assert response.status_code == 401
