"""Tests for POST /auth/refresh — exchange Google refresh token for dockmaster JWT."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockmaster.config import Settings


# ---------------------------------------------------------------------------
# Fixture data (shaped from captured tests/fixtures/gcp/google_oauth/)
# ---------------------------------------------------------------------------

GOOGLE_TOKEN_RESPONSE = {
    "access_token": "ya29.test-access-token",
    "expires_in": 3599,
    "scope": "openid email profile",
    "token_type": "Bearer",
    "id_token": "eyJhbGciOiJSUzI1NiJ9.test-id-token",
}

GOOGLE_USERINFO_RESPONSE = {
    "sub": "1234567890",
    "name": "Test User",
    "given_name": "Test",
    "family_name": "User",
    "picture": "https://example.com/photo.jpg",
    "email": "user@example.com",
    "email_verified": True,
    "hd": "example.com",
}

ID_TOKEN_CLAIMS = {
    "iss": "https://accounts.google.com",
    "aud": "test-client.apps.googleusercontent.com",
    "sub": "1234567890",
    "email": "user@example.com",
    "email_verified": True,
    "iat": 1700000000,
    "exp": 1700003600,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def refresh_settings() -> Settings:
    return Settings(
        log_level="DEBUG",
        client_id="test-client.apps.googleusercontent.com",
        client_secret="test-secret",
        default_client_id="test-client.apps.googleusercontent.com",
        authorized_domains={"example.com"},
        authorized_issuers={"https://accounts.google.com"},
        authorized_audience={"test-client.apps.googleusercontent.com"},
        session_secret_key="test-session-secret",
        userinfo_endpoint="https://www.googleapis.com/oauth2/v3/userinfo",
    )


@pytest.fixture
def mock_secrets_storage(mocker):
    """Mock SecretsStorage that returns a test client secret."""
    storage = mocker.MagicMock()
    storage.get_client_secret.return_value = "test-client-secret-value"
    return storage


@pytest.fixture
def mock_realm(mocker):
    """Mock ServiceRealm that returns valid id_token claims."""
    realm = mocker.MagicMock()
    realm.verify.return_value = ID_TOKEN_CLAIMS.copy()
    return realm


@pytest.fixture
def mock_token_issuer(mocker):
    """Mock EphemeralKeypairSigner that returns a predictable dockmaster JWT."""
    issuer = mocker.MagicMock()
    issuer.sign.return_value = "dockmaster.test.jwt"
    issuer.default_ttl = 900
    return issuer


def _mock_httpx_response(status_code: int, json_data: dict) -> httpx.Response:
    """Build a fake httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("POST", "https://example.com"),
    )


@pytest.fixture
def refresh_client(
    app: FastAPI,
    refresh_settings: Settings,
    mock_secrets_storage,
    mock_realm,
    mock_token_issuer,
) -> TestClient:
    """TestClient wired for refresh tests with all dependencies mocked."""
    app.state.settings = refresh_settings
    with TestClient(app) as c:
        app.state.secrets_storage = mock_secrets_storage
        app.state.realm = mock_realm
        app.state.token_issuer = mock_token_issuer
        yield c


# ---------------------------------------------------------------------------
# Helper to build mock httpx client
# ---------------------------------------------------------------------------


def _build_mock_httpx(mocker, token_response=None, token_status=200, userinfo_response=None, userinfo_status=200):
    """Return a mock for httpx.AsyncClient that handles token + userinfo calls."""
    token_resp = _mock_httpx_response(token_status, token_response or GOOGLE_TOKEN_RESPONSE)
    userinfo_resp = _mock_httpx_response(userinfo_status, userinfo_response or GOOGLE_USERINFO_RESPONSE)

    async def mock_post(url, **kwargs):
        return token_resp

    async def mock_get(url, **kwargs):
        return userinfo_resp

    mock_client = mocker.MagicMock()
    mock_client.post = mock_post
    mock_client.get = mock_get
    mock_client.__aenter__ = lambda self: _async_return(mock_client)
    mock_client.__aexit__ = lambda self, *args: _async_return(None)

    return mock_client


async def _async_return(value):
    return value


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRefreshHappyPath:
    """POST /auth/refresh — valid refresh token."""

    def test_valid_refresh_returns_dockmaster_jwt(self, mocker, refresh_client, mock_token_issuer):
        mock_client = _build_mock_httpx(mocker)
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["token"] == "dockmaster.test.jwt"
        assert data["subject"] == "user@example.com"
        assert data["id_token"] == GOOGLE_TOKEN_RESPONSE["id_token"]
        assert data["access_token"] == GOOGLE_TOKEN_RESPONSE["access_token"]
        assert data["claims"]["name"] == "Test User"

    def test_issuer_called_with_correct_args(self, mocker, refresh_client, mock_token_issuer):
        mock_client = _build_mock_httpx(mocker)
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token", "service": "my-service", "expiry": 7200},
        )

        mock_token_issuer.sign.assert_called_once_with(
            subject="user@example.com",
            audience="my-service",
            ttl=7200,
            extra_claims={
                "name": "Test User",
                "given_name": "Test",
                "family_name": "User",
                "picture": "https://example.com/photo.jpg",
            },
        )

    def test_service_defaults_to_id_token_audience(self, mocker, refresh_client):
        """When no service in request, service falls back to id_token aud."""
        mock_client = _build_mock_httpx(mocker)
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.json()["service"] == "test-client.apps.googleusercontent.com"

    def test_google_token_called_with_form_data(self, mocker, refresh_client):
        """Verify Google token endpoint is called with data= (form body), not params=."""
        calls = []

        async def capture_post(url, **kwargs):
            calls.append({"url": url, "kwargs": kwargs})
            return _mock_httpx_response(200, GOOGLE_TOKEN_RESPONSE)

        mock_client = _build_mock_httpx(mocker)
        mock_client.post = capture_post
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert len(calls) == 1
        assert "data" in calls[0]["kwargs"]
        assert calls[0]["kwargs"]["data"]["grant_type"] == "refresh_token"


class TestRefreshClientIdResolution:
    """Client ID resolution — request body vs default vs missing."""

    def test_missing_client_id_no_default_returns_400(self, refresh_client, refresh_settings):
        """No client_id in request and no default -> 400."""
        # Override default_client_id to None (explicit to prevent .env leaking in)
        refresh_settings_no_default = Settings(
            log_level="DEBUG",
            default_client_id=None,
            client_id=None,
            client_secret=None,
            authorized_domains={"example.com"},
            authorized_issuers={"https://accounts.google.com"},
            authorized_audience={"test-client.apps.googleusercontent.com"},
            session_secret_key="test-session-secret",
        )
        refresh_client.app.state.settings = refresh_settings_no_default

        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 400
        assert "No client_id" in response.json()["detail"]

    def test_short_client_id_gets_suffix_appended(self, mocker, refresh_client, mock_secrets_storage):
        """Short client_id without dot gets suffix appended."""
        mock_client = _build_mock_httpx(mocker)
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token", "client_id": "109370504310"},
        )

        # SM lookup should receive the full client_id with suffix
        mock_secrets_storage.get_client_secret.assert_called_once_with("109370504310.apps.googleusercontent.com")


class TestRefreshSecretManagerErrors:
    """Secret Manager lookup failures."""

    def test_sm_lookup_failure_returns_400(self, refresh_client, mock_secrets_storage):
        """SM raises exception -> 400 Invalid client_id."""
        from google.api_core.exceptions import NotFound

        mock_secrets_storage.get_client_secret.side_effect = NotFound("secret not found")

        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 400
        assert "Invalid client_id" in response.json()["detail"]

    def test_secrets_storage_not_configured_returns_503(self, refresh_client):
        """No secrets_storage on app.state -> 503."""
        refresh_client.app.state.secrets_storage = None

        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 503
        assert "Secrets storage" in response.json()["detail"]


class TestRefreshGoogleErrors:
    """Google token endpoint and verification failures."""

    def test_google_refresh_non_200_returns_401(self, mocker, refresh_client):
        """Google token endpoint returns non-200 -> 401."""
        mock_client = _build_mock_httpx(mocker, token_status=401, token_response={"error": "invalid_grant"})
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "bad-refresh-token"},
        )

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    def test_id_token_verification_failure_returns_401(self, mocker, refresh_client, mock_realm):
        """ServiceRealm.verify raises ValueError -> 401."""
        mock_realm.verify.side_effect = ValueError("signature verification failed")
        mock_client = _build_mock_httpx(mocker)
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 401


class TestRefreshCanIssue:
    """can_issue enforcement — issuer, audience, domain checks."""

    def test_issuer_not_allowed_returns_403(self, mocker, refresh_client, mock_realm):
        """id_token issuer not in AUTHORIZED_ISSUERS -> 403."""
        claims = ID_TOKEN_CLAIMS.copy()
        claims["iss"] = "https://evil.example.com"
        mock_realm.verify.return_value = claims

        mock_client = _build_mock_httpx(mocker)
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 403
        assert "Issuer not allowed" in response.json()["detail"]

    def test_audience_not_allowed_returns_403(self, mocker, refresh_client, mock_realm):
        """id_token audience not in AUTHORIZED_AUDIENCE -> 403."""
        claims = ID_TOKEN_CLAIMS.copy()
        claims["aud"] = "wrong-audience"
        mock_realm.verify.return_value = claims

        mock_client = _build_mock_httpx(mocker)
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 403
        assert "Audience not allowed" in response.json()["detail"]

    def test_domain_not_allowed_returns_403(self, mocker, refresh_client, mock_realm):
        """Email domain not in AUTHORIZED_DOMAINS -> 403."""
        claims = ID_TOKEN_CLAIMS.copy()
        claims["email"] = "user@unauthorized.com"
        mock_realm.verify.return_value = claims

        mock_client = _build_mock_httpx(mocker)
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 403
        assert "Domain not allowed" in response.json()["detail"]


class TestRefreshUserInfoFailure:
    """UserInfo API failure is non-fatal."""

    def test_userinfo_failure_returns_empty_claims(self, mocker, refresh_client):
        """UserInfo non-200 -> warning logged, empty profile claims, still succeeds."""
        mock_client = _build_mock_httpx(mocker, userinfo_status=500, userinfo_response={"error": "server error"})
        mocker.patch("dockmaster.routes.refresh.httpx.AsyncClient", return_value=mock_client)
        response = refresh_client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 200
        assert response.json()["claims"] == {}
