"""Tests for OAuth login routes — /auth/login, /auth/login/callback, /auth/logout."""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from dockmaster.config import Settings
from dockmaster.routes.login import _validate_cookie_return_to, _validate_external_return_to
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
        """Login should store a CSRF state in the flow_store."""
        from starlette.responses import RedirectResponse

        mock_oauth.google.authorize_redirect = mocker.AsyncMock(
            return_value=RedirectResponse(url="https://accounts.google.com/o/oauth2/auth")
        )

        flow_store = login_client.app.state.flow_store
        before = len(flow_store._oauth_states)
        login_client.get("/auth/login", follow_redirects=False)

        assert len(flow_store._oauth_states) == before + 1


class TestCallback:
    """GET /auth/login/callback."""

    def test_callback_creates_session_and_redirects(self, mocker, login_client, mock_oauth, session_store):
        """Valid callback -> session created, cookie set, redirect to /ui/."""
        flow_store = login_client.app.state.flow_store
        state_key = flow_store.create_oauth_state(redirect_uri=None)

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
            f"/auth/login/callback?code=auth-code&state={state_key}",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/ui/"
        assert "session_id" in response.cookies

    def test_callback_invalid_state_returns_401(self, login_client):
        """Callback with wrong state -> 401."""
        response = login_client.get(
            "/auth/login/callback?code=auth-code&state=bad-state",
            follow_redirects=False,
        )

        assert response.status_code == 401

    def test_callback_domain_not_allowed_returns_403(self, mocker, login_client, mock_oauth):
        """Callback with unauthorized email domain -> 403."""
        flow_store = login_client.app.state.flow_store
        state_key = flow_store.create_oauth_state(redirect_uri=None)

        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@unauthorized.com"},
            }
        )

        response = login_client.get(
            f"/auth/login/callback?code=auth-code&state={state_key}",
            follow_redirects=False,
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"


class TestValidateCookieReturnTo:
    """Unit tests for _validate_cookie_return_to."""

    def test_none_defaults_to_ui(self):
        assert _validate_cookie_return_to(None) == "/ui/"

    def test_empty_defaults_to_ui(self):
        assert _validate_cookie_return_to("") == "/ui/"

    def test_relative_path_accepted(self):
        assert _validate_cookie_return_to("/dashboard") == "/dashboard"

    def test_relative_path_with_segments(self):
        assert _validate_cookie_return_to("/ui/roles") == "/ui/roles"

    def test_absolute_url_rejected(self):
        assert _validate_cookie_return_to("https://evil.com/steal") == "/ui/"

    def test_protocol_relative_rejected(self):
        assert _validate_cookie_return_to("//evil.com/steal") == "/ui/"

    def test_bare_domain_rejected(self):
        assert _validate_cookie_return_to("evil.com") == "/ui/"


class TestValidateExternalReturnTo:
    """Unit tests for _validate_external_return_to."""

    def test_none_returns_none(self):
        assert _validate_external_return_to(None) is None

    def test_empty_returns_none(self):
        assert _validate_external_return_to("") is None

    def test_relative_path_accepted(self):
        assert _validate_external_return_to("/settings") == "/settings"

    def test_absolute_url_accepted(self):
        assert _validate_external_return_to("https://app.example.com/dash") == "https://app.example.com/dash"

    def test_blocklisted_uri_rejected(self):
        blocklist = {"https://bad.com/phish"}
        assert _validate_external_return_to("https://bad.com/phish", blocklist) is None

    def test_non_blocklisted_uri_accepted(self):
        blocklist = {"https://bad.com/phish"}
        assert _validate_external_return_to("https://good.com/ok", blocklist) == "https://good.com/ok"

    def test_empty_blocklist_accepts_all(self):
        assert _validate_external_return_to("https://anything.com", set()) == "https://anything.com"


class TestReturnTo:
    """return_to support in cookie flow callback."""

    def test_cookie_flow_uses_return_to(self, mocker, login_client, mock_oauth, session_store):
        """Cookie flow callback redirects to return_to instead of /ui/."""
        flow_store = login_client.app.state.flow_store
        state_key = flow_store.create_oauth_state(redirect_uri=None, return_to="/dashboard")

        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@example.com", "name": "Test User"},
            }
        )

        response = login_client.get(
            f"/auth/login/callback?code=auth-code&state={state_key}",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

    def test_cookie_flow_defaults_to_ui(self, mocker, login_client, mock_oauth, session_store):
        """Cookie flow callback defaults to /ui/ when no return_to."""
        flow_store = login_client.app.state.flow_store
        state_key = flow_store.create_oauth_state(redirect_uri=None)

        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@example.com", "name": "Test User"},
            }
        )

        response = login_client.get(
            f"/auth/login/callback?code=auth-code&state={state_key}",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/ui/"

    def test_cookie_flow_rejects_absolute_return_to(self, mocker, login_client, mock_oauth, session_store):
        """Cookie flow ignores absolute URL return_to and defaults to /ui/."""
        flow_store = login_client.app.state.flow_store
        state_key = flow_store.create_oauth_state(redirect_uri=None, return_to="https://evil.com")

        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@example.com", "name": "Test User"},
            }
        )

        response = login_client.get(
            f"/auth/login/callback?code=auth-code&state={state_key}",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/ui/"


class TestLogout:
    """POST /auth/logout."""

    def test_logout_clears_session_and_cookie(self, login_client, session_store, login_settings):
        """Logout should delete session and clear cookie."""
        signer = URLSafeSerializer(login_settings.session_secret_key)
        session_id = "test-session-id"
        signed = signer.dumps(session_id)
        _seed_session(session_store, session_id, {"email": "user@example.com"})

        login_client.cookies.set("session_id", signed)
        response = login_client.post("/auth/logout", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "/ui/"
        assert session_id not in session_store._store

    def test_logout_without_cookie_still_redirects(self, login_client):
        """Logout without a session cookie should still redirect."""
        response = login_client.post("/auth/logout", follow_redirects=False)
        assert response.status_code == 302


