"""Tests for the auth code flow: redirect URI allowlisting, code generation, code exchange."""

import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient

from dockmaster.config import Settings
from dockmaster.main import create_app
from dockmaster.routes.login import _pending_states, _validate_redirect_uri


# ---------------------------------------------------------------------------
# Redirect URI validation with allowlist
# ---------------------------------------------------------------------------


class TestValidateRedirectUriAllowlist:
    """Extended _validate_redirect_uri with ALLOWED_REDIRECT_URIS."""

    def test_allowlisted_uri_accepted(self):
        allowed = {"https://app.example.com/callback", "https://other.com/cb"}
        result = _validate_redirect_uri("https://app.example.com/callback", allowed)
        assert result == "https://app.example.com/callback"

    def test_non_allowlisted_uri_rejected(self):
        allowed = {"https://app.example.com/callback"}
        with pytest.raises(HTTPException) as exc_info:
            _validate_redirect_uri("https://evil.com/callback", allowed)
        assert exc_info.value.status_code == 400

    def test_localhost_still_allowed_without_allowlist(self):
        """Localhost URIs are always allowed, even with an empty allowlist."""
        result = _validate_redirect_uri("http://localhost:9876/callback", set())
        assert result == "http://localhost:9876/callback"

    def test_localhost_allowed_alongside_allowlist(self):
        """Localhost URIs work even when an allowlist is configured."""
        allowed = {"https://app.example.com/callback"}
        result = _validate_redirect_uri("http://localhost:9876/callback", allowed)
        assert result == "http://localhost:9876/callback"

    def test_empty_allowlist_rejects_external(self):
        with pytest.raises(HTTPException):
            _validate_redirect_uri("https://app.example.com/callback", set())

    def test_none_allowlist_rejects_external(self):
        with pytest.raises(HTTPException):
            _validate_redirect_uri("https://app.example.com/callback", None)


# ---------------------------------------------------------------------------
# Code exchange endpoint fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def code_exchange_settings() -> Settings:
    """Settings with allowed_redirect_uris configured."""
    return Settings(
        allowed_redirect_uris={"https://app.example.com/callback"},
        authorized_domains={"example.com"},
        session_secret_key="test-secret",
        _env_file=None,
    )


@pytest.fixture
def code_exchange_app(code_exchange_settings: Settings) -> FastAPI:
    return create_app(code_exchange_settings)


@pytest.fixture
def code_exchange_client(code_exchange_app: FastAPI) -> TestClient:
    with TestClient(code_exchange_app) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /auth/code/exchange tests
# ---------------------------------------------------------------------------


class TestCodeExchangeEndpoint:
    """POST /auth/code/exchange — exchange auth code for Type C JWT."""

    def test_valid_code_exchange(self, code_exchange_app: FastAPI, code_exchange_client: TestClient):
        """Valid code + matching redirect_uri returns a JWT."""
        auth_code_store = code_exchange_app.state.auth_code_store
        issuer = code_exchange_app.state.token_issuer
        code = auth_code_store.create(
            subject="user@example.com",
            redirect_uri="https://app.example.com/callback",
        )

        resp = code_exchange_client.post(
            "/auth/code/exchange",
            json={"code": code, "redirect_uri": "https://app.example.com/callback"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == issuer.default_ttl
        assert data["refresh_token"] is None

    def test_invalid_code_returns_400(self, code_exchange_client: TestClient):
        """Non-existent code returns 400."""
        resp = code_exchange_client.post(
            "/auth/code/exchange",
            json={"code": "bogus", "redirect_uri": "https://app.example.com/callback"},
        )
        assert resp.status_code == 400
        assert "Invalid or expired" in resp.json()["detail"]

    def test_wrong_redirect_uri_returns_400(self, code_exchange_app: FastAPI, code_exchange_client: TestClient):
        """Mismatched redirect_uri returns 400."""
        auth_code_store = code_exchange_app.state.auth_code_store
        code = auth_code_store.create(
            subject="user@example.com",
            redirect_uri="https://app.example.com/callback",
        )

        resp = code_exchange_client.post(
            "/auth/code/exchange",
            json={"code": code, "redirect_uri": "https://wrong.com/callback"},
        )
        assert resp.status_code == 400

    def test_code_single_use(self, code_exchange_app: FastAPI, code_exchange_client: TestClient):
        """Code can only be exchanged once."""
        auth_code_store = code_exchange_app.state.auth_code_store
        code = auth_code_store.create(
            subject="user@example.com",
            redirect_uri="https://app.example.com/callback",
        )

        # First exchange succeeds
        resp1 = code_exchange_client.post(
            "/auth/code/exchange",
            json={"code": code, "redirect_uri": "https://app.example.com/callback"},
        )
        assert resp1.status_code == 200

        # Second exchange fails (single-use)
        resp2 = code_exchange_client.post(
            "/auth/code/exchange",
            json={"code": code, "redirect_uri": "https://app.example.com/callback"},
        )
        assert resp2.status_code == 400

    def test_missing_fields_returns_422(self, code_exchange_client: TestClient):
        """Missing required fields returns 422 validation error."""
        resp = code_exchange_client.post("/auth/code/exchange", json={"code": "abc"})
        assert resp.status_code == 422

    def test_jwt_contains_correct_subject(self, code_exchange_app: FastAPI, code_exchange_client: TestClient):
        """The returned JWT contains the correct subject from the auth code."""
        import jwt

        auth_code_store = code_exchange_app.state.auth_code_store
        code = auth_code_store.create(
            subject="alice@example.com",
            redirect_uri="https://app.example.com/callback",
        )

        resp = code_exchange_client.post(
            "/auth/code/exchange",
            json={"code": code, "redirect_uri": "https://app.example.com/callback"},
        )

        token = resp.json()["access_token"]
        # Decode without verification (we trust the issuer in tests)
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["sub"] == "alice@example.com"
        assert claims["iss"] == "dockmaster"


# ---------------------------------------------------------------------------
# Callback external redirect tests
# ---------------------------------------------------------------------------


class TestCallbackExternalRedirect:
    """When callback has an external redirect_uri, it generates an auth code."""

    def test_external_redirect_generates_code(
        self, mocker, code_exchange_app: FastAPI, code_exchange_client: TestClient
    ):
        """Callback with an external redirect_uri redirects with code param."""
        # Set up a fake OAuth that returns a valid token response
        mock_oauth = mocker.MagicMock()
        mock_google = mocker.MagicMock()
        mock_google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@example.com", "name": "Test User"},
            }
        )
        mock_oauth.google = mock_google
        code_exchange_app.state.oauth = mock_oauth

        # Plant a pending state with an external redirect_uri
        state_id = "test-state-123"
        _pending_states[state_id] = {"redirect_uri": "https://app.example.com/callback"}

        resp = code_exchange_client.get(
            f"/auth/callback?state={state_id}&code=google-auth-code",
            follow_redirects=False,
        )

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("https://app.example.com/callback?")
        assert "code=" in location
        assert "state=" in location

    def test_localhost_redirect_still_returns_jwt(
        self, mocker, code_exchange_app: FastAPI, code_exchange_client: TestClient
    ):
        """Callback with a localhost redirect_uri still returns JWT directly."""
        mock_oauth = mocker.MagicMock()
        mock_google = mocker.MagicMock()
        mock_google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@example.com", "name": "Test User"},
            }
        )
        mock_oauth.google = mock_google
        code_exchange_app.state.oauth = mock_oauth

        state_id = "test-state-456"
        _pending_states[state_id] = {"redirect_uri": "http://localhost:9876/callback"}

        resp = code_exchange_client.get(
            f"/auth/callback?state={state_id}&code=google-auth-code",
            follow_redirects=False,
        )

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("http://localhost:9876/callback?")
        assert "token=" in location  # JWT, not auth code
        assert "code=" not in location
