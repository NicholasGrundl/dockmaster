"""Tests for CLI auth routes — /auth/cli/login, /auth/cli/callback, /auth/cli/token."""

import jwt as pyjwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from dockmaster.auth.jwt_signers import EphemeralKeypairSigner
from dockmaster.config import Settings
from dockmaster.routes.cli_routes import _validate_cli_redirect_uri


@pytest.fixture
def cli_settings() -> Settings:
    return Settings(
        log_level="DEBUG",
        client_id="test-client.apps.googleusercontent.com",
        client_secret="test-secret",
        session_secret_key="test-secret",
        authorized_domains={"example.com"},
    )


@pytest.fixture
def token_issuer() -> EphemeralKeypairSigner:
    return EphemeralKeypairSigner(ttl=900)


@pytest.fixture
def mock_oauth(mocker):
    """Mock Authlib OAuth client."""
    oauth = mocker.MagicMock()
    oauth.google = mocker.MagicMock()
    return oauth


@pytest.fixture
def cli_client(app: FastAPI, cli_settings: Settings, token_issuer: EphemeralKeypairSigner, fake_realm, mock_oauth) -> TestClient:
    """TestClient wired for CLI route tests."""
    app.state.settings = cli_settings
    with TestClient(app) as client:
        app.state.token_issuer = token_issuer
        app.state.realm = fake_realm
        app.state.oauth = mock_oauth
        yield client


# ---------------------------------------------------------------------------
# _validate_cli_redirect_uri
# ---------------------------------------------------------------------------


class TestValidateCliRedirectUri:
    """Unit tests for _validate_cli_redirect_uri."""

    def test_localhost_http_allowed(self):
        assert _validate_cli_redirect_uri("http://localhost:9876/callback") == "http://localhost:9876/callback"

    def test_localhost_no_port_allowed(self):
        assert _validate_cli_redirect_uri("http://localhost/callback") == "http://localhost/callback"

    def test_localhost_https_allowed(self):
        assert _validate_cli_redirect_uri("https://localhost:9876/callback") == "https://localhost:9876/callback"

    def test_127_0_0_1_allowed(self):
        assert _validate_cli_redirect_uri("http://127.0.0.1:8080/callback") == "http://127.0.0.1:8080/callback"

    def test_none_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_cli_redirect_uri(None)
        assert exc_info.value.status_code == 400
        assert "required" in exc_info.value.detail

    def test_empty_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_cli_redirect_uri("")
        assert exc_info.value.status_code == 400

    def test_external_url_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_cli_redirect_uri("https://evil.com/callback")
        assert exc_info.value.status_code == 400
        assert "localhost" in exc_info.value.detail

    def test_non_localhost_host_rejected(self):
        with pytest.raises(HTTPException):
            _validate_cli_redirect_uri("http://myapp.example.com:9876/callback")


# ---------------------------------------------------------------------------
# GET /auth/cli/login
# ---------------------------------------------------------------------------


class TestCliLogin:
    """GET /auth/cli/login."""

    def test_redirects_to_google(self, mocker, cli_client, mock_oauth):
        """CLI login with localhost redirect_uri redirects to Google."""
        from starlette.responses import RedirectResponse

        mock_oauth.google.authorize_redirect = mocker.AsyncMock(
            return_value=RedirectResponse(url="https://accounts.google.com/o/oauth2/auth?state=abc")
        )

        response = cli_client.get(
            "/auth/cli/login?redirect_uri=http://localhost:9876/callback",
            follow_redirects=False,
        )

        assert response.status_code in (302, 307)
        mock_oauth.google.authorize_redirect.assert_called_once()
        # Callback URI should point to /auth/cli/callback
        call_args = mock_oauth.google.authorize_redirect.call_args
        callback_uri = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("redirect_uri")
        assert "/auth/cli/callback" in callback_uri

    def test_stores_state(self, mocker, cli_client, mock_oauth):
        """CLI login stores CSRF state with redirect_uri."""
        from starlette.responses import RedirectResponse

        mock_oauth.google.authorize_redirect = mocker.AsyncMock(
            return_value=RedirectResponse(url="https://accounts.google.com/o/oauth2/auth")
        )

        oauth_state_store = cli_client.app.state.oauth_state_store
        before = len(oauth_state_store)

        cli_client.get(
            "/auth/cli/login?redirect_uri=http://localhost:9876/callback",
            follow_redirects=False,
        )

        assert len(oauth_state_store) == before + 1

    def test_missing_redirect_uri_returns_400(self, cli_client):
        """CLI login without redirect_uri returns 400."""
        response = cli_client.get("/auth/cli/login", follow_redirects=False)
        assert response.status_code == 400
        assert "required" in response.json()["detail"]

    def test_non_localhost_redirect_uri_returns_400(self, cli_client):
        """CLI login with non-localhost redirect_uri returns 400."""
        response = cli_client.get(
            "/auth/cli/login?redirect_uri=https://evil.com/callback",
            follow_redirects=False,
        )
        assert response.status_code == 400

    def test_503_when_oauth_not_configured(self, app, cli_settings):
        """Returns 503 when OAuth client is not available."""
        app.state.settings = cli_settings
        with TestClient(app) as client:
            app.state.oauth = None
            response = client.get(
                "/auth/cli/login?redirect_uri=http://localhost:9876/callback",
                follow_redirects=False,
            )
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# GET /auth/cli/callback
# ---------------------------------------------------------------------------


class TestCliCallback:
    """GET /auth/cli/callback."""

    def test_valid_callback_redirects_with_jwt(self, mocker, cli_client, mock_oauth, token_issuer):
        """Valid callback mints JWT and redirects to localhost."""
        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@example.com", "name": "Test User"},
            }
        )

        oauth_state_store = cli_client.app.state.oauth_state_store
        state_id = oauth_state_store.create({"redirect_uri": "http://localhost:9876/callback"})

        response = cli_client.get(
            f"/auth/cli/callback?code=google-auth-code&state={state_id}",
            follow_redirects=False,
        )

        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("http://localhost:9876/callback?")
        assert "token=" in location
        # No auth code — CLI gets JWT directly
        assert "code=" not in location

    def test_jwt_has_correct_claims(self, mocker, cli_client, mock_oauth, token_issuer):
        """The minted JWT has correct subject, audience, and issuer."""
        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "alice@example.com"},
            }
        )

        oauth_state_store = cli_client.app.state.oauth_state_store
        state_id = oauth_state_store.create({"redirect_uri": "http://localhost:9876/callback"})

        response = cli_client.get(
            f"/auth/cli/callback?code=google-auth-code&state={state_id}",
            follow_redirects=False,
        )

        location = response.headers["location"]
        token = location.split("token=")[1]
        claims = pyjwt.decode(token, options={"verify_signature": False})
        assert claims["sub"] == "alice@example.com"
        assert claims["aud"] == "dockmaster"
        assert claims["iss"] == "dockmaster"

    def test_invalid_state_returns_401(self, cli_client):
        """Callback with invalid CSRF state returns 401."""
        response = cli_client.get(
            "/auth/cli/callback?code=auth-code&state=bad-state",
            follow_redirects=False,
        )
        assert response.status_code == 401

    def test_missing_state_returns_401(self, cli_client):
        """Callback without state parameter returns 401."""
        response = cli_client.get(
            "/auth/cli/callback?code=auth-code",
            follow_redirects=False,
        )
        assert response.status_code == 401

    def test_unauthorized_domain_returns_403(self, mocker, cli_client, mock_oauth):
        """Callback with unauthorized email domain returns 403."""
        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@unauthorized.com"},
            }
        )

        oauth_state_store = cli_client.app.state.oauth_state_store
        state_id = oauth_state_store.create({"redirect_uri": "http://localhost:9876/callback"})

        response = cli_client.get(
            f"/auth/cli/callback?code=google-auth-code&state={state_id}",
            follow_redirects=False,
        )
        assert response.status_code == 403

    def test_no_email_returns_400(self, mocker, cli_client, mock_oauth):
        """Callback with no email in token response returns 400."""
        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={"userinfo": {}}
        )

        oauth_state_store = cli_client.app.state.oauth_state_store
        state_id = oauth_state_store.create({"redirect_uri": "http://localhost:9876/callback"})

        response = cli_client.get(
            f"/auth/cli/callback?code=google-auth-code&state={state_id}",
            follow_redirects=False,
        )
        assert response.status_code == 400

    def test_non_localhost_in_state_returns_400(self, mocker, cli_client, mock_oauth):
        """Callback with non-localhost redirect_uri in state returns 400."""
        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@example.com"},
            }
        )

        oauth_state_store = cli_client.app.state.oauth_state_store
        state_id = oauth_state_store.create({"redirect_uri": "https://evil.com/callback"})

        response = cli_client.get(
            f"/auth/cli/callback?code=google-auth-code&state={state_id}",
            follow_redirects=False,
        )
        assert response.status_code == 400

    def test_503_when_token_issuer_not_configured(self, mocker, cli_client, mock_oauth):
        """Returns 503 when token_issuer is not available."""
        mock_oauth.google.authorize_access_token = mocker.AsyncMock(
            return_value={
                "userinfo": {"email": "user@example.com"},
            }
        )

        oauth_state_store = cli_client.app.state.oauth_state_store
        state_id = oauth_state_store.create({"redirect_uri": "http://localhost:9876/callback"})

        cli_client.app.state.token_issuer = None

        response = cli_client.get(
            f"/auth/cli/callback?code=google-auth-code&state={state_id}",
            follow_redirects=False,
        )
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# POST /auth/cli/token
# ---------------------------------------------------------------------------


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

    def test_cli_login_does_not_require_bearer(self, mocker, cli_client, mock_oauth):
        """GET /auth/cli/login should work without a Bearer JWT (public route)."""
        from starlette.responses import RedirectResponse

        mock_oauth.google.authorize_redirect = mocker.AsyncMock(
            return_value=RedirectResponse(url="https://accounts.google.com/o/oauth2/auth")
        )

        response = cli_client.get(
            "/auth/cli/login?redirect_uri=http://localhost:9876/callback",
            follow_redirects=False,
        )
        # Should succeed — no 401 from allow_jwt
        assert response.status_code in (302, 307)
