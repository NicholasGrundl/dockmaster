"""Tests for OAuth login routes — /auth/login, /auth/callback, /auth/logout, /auth/principal."""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from dockmaster.config import Settings
from dockmaster.sessions.memory import InMemorySessionStore


@pytest.fixture
def login_settings() -> Settings:
    """Settings for login tests."""
    return Settings(
        log_level="DEBUG",
        client_id="test-client.apps.googleusercontent.com",
        client_secret="test-secret",
        authorized_domains={"example.com"},
        authorized_issuers={"https://accounts.google.com"},
        authorized_audience={"test-client.apps.googleusercontent.com"},
        session_secret_key="test-session-secret",
        session_ttl=3600,
    )


@pytest.fixture
def session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def mock_oauth(mocker):
    """Mock Authlib OAuth client."""
    oauth = mocker.MagicMock()
    oauth.google = mocker.MagicMock()
    return oauth


@pytest.fixture
def login_client(app: FastAPI, login_settings, session_store, mock_oauth) -> TestClient:
    """TestClient wired for login tests."""
    app.state.settings = login_settings
    with TestClient(app) as c:
        app.state.session_store = session_store
        app.state.oauth = mock_oauth
        yield c


def _seed_session(store: InMemorySessionStore, session_id: str, data: dict, ttl: int = 3600):
    """Directly seed a session into the store (no async needed)."""
    store._store[session_id] = (data, time.time() + ttl)


class TestLogin:
    """GET /auth/login."""

    def test_login_redirects_to_google(self, mocker, login_client, mock_oauth):
        """Login should call oauth.google.authorize_redirect."""
        from starlette.responses import RedirectResponse

        mock_oauth.google.authorize_redirect = mocker.AsyncMock(
            return_value=RedirectResponse(url="https://accounts.google.com/o/oauth2/auth?state=abc")
        )

        response = login_client.get("/auth/login", follow_redirects=False)

        assert response.status_code in (302, 307)  # RedirectResponse default is 307
        mock_oauth.google.authorize_redirect.assert_called_once()
        call_kwargs = mock_oauth.google.authorize_redirect.call_args
        assert call_kwargs.kwargs.get("prompt") == "select_account"

    def test_login_stores_csrf_state(self, mocker, login_client, mock_oauth):
        """Login should store a CSRF state in the oauth_state_store."""
        from starlette.responses import RedirectResponse

        mock_oauth.google.authorize_redirect = mocker.AsyncMock(
            return_value=RedirectResponse(url="https://accounts.google.com/o/oauth2/auth")
        )

        oauth_state_store = login_client.app.state.oauth_state_store
        before = len(oauth_state_store)
        login_client.get("/auth/login", follow_redirects=False)

        assert len(oauth_state_store) == before + 1


class TestCallback:
    """GET /auth/callback."""

    def test_callback_creates_session_and_redirects(self, mocker, login_client, mock_oauth, session_store):
        """Valid callback -> session created, cookie set, redirect to /ui/."""
        oauth_state_store = login_client.app.state.oauth_state_store
        state_key = oauth_state_store.create({"redirect_uri": None})

        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {
                    "email": "user@example.com",
                    "name": "Test User",
                    "picture": "https://example.com/photo.jpg",
                    "given_name": "Test",
                    "family_name": "User",
                    "locale": "en",
                },
            }
        )

        response = login_client.get(
            f"/auth/callback?code=auth-code&state={state_key}",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/ui/"
        assert "session_id" in response.cookies

    def test_callback_invalid_state_returns_401(self, login_client):
        """Callback with wrong state -> 401."""
        response = login_client.get(
            "/auth/callback?code=auth-code&state=bad-state",
            follow_redirects=False,
        )

        assert response.status_code == 401

    def test_callback_domain_not_allowed_returns_403(self, mocker, login_client, mock_oauth):
        """Callback with unauthorized email domain -> 403."""
        oauth_state_store = login_client.app.state.oauth_state_store
        state_key = oauth_state_store.create({"redirect_uri": None})

        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@unauthorized.com"},
            }
        )

        response = login_client.get(
            f"/auth/callback?code=auth-code&state={state_key}",
            follow_redirects=False,
        )

        assert response.status_code == 403
        assert "Domain not allowed" in response.json()["detail"]


class TestLogout:
    """GET /auth/logout."""

    def test_logout_clears_session_and_cookie(self, login_client, session_store, login_settings):
        """Logout should delete session and clear cookie."""
        signer = URLSafeSerializer(login_settings.session_secret_key)
        session_id = "test-session-id"
        signed = signer.dumps(session_id)
        _seed_session(session_store, session_id, {"email": "user@example.com"})

        login_client.cookies.set("session_id", signed)
        response = login_client.get("/auth/logout", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "/ui/"
        assert session_id not in session_store._store

    def test_logout_without_cookie_still_redirects(self, login_client):
        """Logout without a session cookie should still redirect."""
        response = login_client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302


class TestPrincipal:
    """GET /auth/principal."""

    def test_principal_with_active_session(self, login_client, session_store, login_settings):
        """Principal returns profile when session is active."""
        signer = URLSafeSerializer(login_settings.session_secret_key)
        session_id = "test-session-id"
        signed = signer.dumps(session_id)
        _seed_session(session_store, session_id, {"email": "user@example.com", "name": "Test User"})

        login_client.cookies.set("session_id", signed)
        response = login_client.get("/auth/principal")

        assert response.status_code == 200
        assert response.json() == {"email": "user@example.com", "name": "Test User"}

    def test_principal_without_cookie_returns_empty(self, login_client):
        """Principal returns {} when no session cookie."""
        response = login_client.get("/auth/principal")
        assert response.status_code == 200
        assert response.json() == {}

    def test_principal_with_invalid_cookie_returns_empty(self, login_client):
        """Principal returns {} when cookie signature is invalid."""
        login_client.cookies.set("session_id", "tampered-value")
        response = login_client.get("/auth/principal")
        assert response.status_code == 200
        assert response.json() == {}

    def test_principal_with_expired_session_returns_empty(self, login_client, session_store, login_settings):
        """Principal returns {} when session has expired."""
        signer = URLSafeSerializer(login_settings.session_secret_key)
        session_id = "test-session-id"
        signed = signer.dumps(session_id)
        # Seed with already-expired TTL
        session_store._store[session_id] = ({"email": "user@example.com"}, time.time() - 1)

        login_client.cookies.set("session_id", signed)
        response = login_client.get("/auth/principal")

        assert response.status_code == 200
        assert response.json() == {}


class TestSessions:
    """GET /auth/sessions."""

    def test_returns_current_user_sessions(self, login_client, session_store, login_settings):
        """Returns only sessions matching the current user's email."""
        signer = URLSafeSerializer(login_settings.session_secret_key)
        session_id = "my-session"
        signed = signer.dumps(session_id)

        # Seed sessions for current user and another user
        _seed_session(session_store, session_id, {"email": "user@example.com", "name": "Me"})
        _seed_session(session_store, "other-session", {"email": "user@example.com", "name": "Me"})
        _seed_session(session_store, "bob-session", {"email": "bob@example.com", "name": "Bob"})

        login_client.cookies.set("session_id", signed)
        response = login_client.get("/auth/sessions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert "my-session" in data
        assert "other-session" in data
        assert "bob-session" not in data

    def test_returns_empty_without_cookie(self, login_client):
        """Returns {} when no session cookie."""
        response = login_client.get("/auth/sessions")
        assert response.status_code == 200
        assert response.json() == {}

    def test_returns_empty_with_invalid_cookie(self, login_client):
        """Returns {} when cookie signature is invalid."""
        login_client.cookies.set("session_id", "tampered-value")
        response = login_client.get("/auth/sessions")
        assert response.status_code == 200
        assert response.json() == {}

    def test_returns_empty_with_expired_session(self, login_client, session_store, login_settings):
        """Returns {} when session has expired."""
        signer = URLSafeSerializer(login_settings.session_secret_key)
        session_id = "expired-session"
        signed = signer.dumps(session_id)
        session_store._store[session_id] = ({"email": "user@example.com"}, time.time() - 1)

        login_client.cookies.set("session_id", signed)
        response = login_client.get("/auth/sessions")
        assert response.status_code == 200
        assert response.json() == {}
