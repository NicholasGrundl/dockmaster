"""Tests for POST /auth/exchange endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockmaster.auth.jwt_verifier import ServiceRealm
from dockmaster.auth.jwt_signers import EphemeralKeypairSigner
from dockmaster.config import Settings


@pytest.fixture
def exchange_settings(fake_sa_key_data) -> Settings:
    """Settings tuned for exchange tests — signer's email is a trusted issuer."""
    return Settings(
        log_level="DEBUG",
        authorized_issuers={fake_sa_key_data["client_email"]},
        authorized_domains={"example.com"},
        authorized_audience={"test-service"},
    )


@pytest.fixture
def exchange_app(app: FastAPI, exchange_settings: Settings) -> FastAPI:
    """App with exchange-specific settings override."""
    app.state.settings = exchange_settings
    return app


@pytest.fixture
def token_issuer() -> EphemeralKeypairSigner:
    """Ephemeral token issuer for exchange tests."""
    return EphemeralKeypairSigner(ttl=900)


@pytest.fixture
def exchange_client(
    exchange_app: FastAPI, token_issuer: EphemeralKeypairSigner, fake_realm: ServiceRealm
) -> TestClient:
    """TestClient wired with token_issuer, realm, and exchange settings."""
    with TestClient(exchange_app) as c:
        exchange_app.state.token_issuer = token_issuer
        exchange_app.state.realm = fake_realm
        yield c


class _ExchangeTestClient:
    """Context manager that enters TestClient and overwrites token_issuer/realm after lifespan."""

    def __init__(
        self, app: FastAPI, settings: Settings, realm: ServiceRealm, token_issuer: EphemeralKeypairSigner | None = None
    ):
        self._app = app
        self._token_issuer = token_issuer or EphemeralKeypairSigner(ttl=900)
        self._realm = realm
        app.state.settings = settings

    def __enter__(self):
        self._client = TestClient(self._app)
        self._client.__enter__()
        self._app.state.token_issuer = self._token_issuer
        self._app.state.realm = self._realm
        return self._client

    def __exit__(self, *args):
        return self._client.__exit__(*args)


class TestExchangeJWTPath:
    """Tests for the JWT verification path."""

    def test_valid_jwt_returns_dockmaster_token(self, exchange_client, signer):
        """Valid JWT with matching settings -> 200 with dockmaster JWT."""
        token = signer.sign(
            subject="user@example.com",
            audience="test-service",
            payload={"name": "Test User", "picture": "https://example.com/photo.jpg"},
        )

        response = exchange_client.post(
            "/auth/exchange",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["subject"] == "user@example.com"
        assert data["service"] == "test-service"
        assert data["expiry"] == 3600
        assert "token" in data
        assert data["claims"]["name"] == "Test User"
        assert data["claims"]["picture"] == "https://example.com/photo.jpg"

    def test_issuer_not_allowed(self, app, signer, fake_realm):
        """JWT with untrusted issuer -> 403."""
        settings = Settings(
            authorized_issuers={"https://accounts.google.com"},
            authorized_domains={"example.com"},
            authorized_audience={"test-service"},
        )
        token = signer.sign(subject="user@example.com", audience="test-service")

        with _ExchangeTestClient(app, settings, fake_realm) as client:
            response = client.post(
                "/auth/exchange",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    def test_audience_not_allowed(self, app, signer, fake_realm, fake_sa_key_data):
        """JWT with wrong audience -> 401 (rejected by credential gate)."""
        settings = Settings(
            authorized_issuers={fake_sa_key_data["client_email"]},
            authorized_domains={"example.com"},
            authorized_audience={"allowed-service"},
        )
        token = signer.sign(subject="user@example.com", audience="wrong-service")

        with _ExchangeTestClient(app, settings, fake_realm) as client:
            response = client.post(
                "/auth/exchange",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    def test_domain_not_allowed(self, app, signer, fake_realm, fake_sa_key_data):
        """JWT with unauthorized email domain -> 403."""
        settings = Settings(
            authorized_issuers={fake_sa_key_data["client_email"]},
            authorized_domains={"shipyard.com"},
            authorized_audience={"test-service"},
        )
        token = signer.sign(subject="user@example.com", audience="test-service")

        with _ExchangeTestClient(app, settings, fake_realm) as client:
            response = client.post(
                "/auth/exchange",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def test_custom_expiry(self, exchange_client, signer):
        """?expiry within cap is honored."""
        token = signer.sign(subject="user@example.com", audience="test-service")

        response = exchange_client.post(
            "/auth/exchange?expiry=1800",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["expiry"] == 1800

    def test_expiry_clamped_to_max(self, exchange_client, signer):
        """?expiry above max_token_ttl is silently clamped."""
        token = signer.sign(subject="user@example.com", audience="test-service")

        response = exchange_client.post(
            "/auth/exchange?expiry=86400",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        # Default max_token_ttl is 3600
        assert response.json()["expiry"] == 3600

    def test_profile_claims_forwarded(self, exchange_client, signer):
        """Profile claims from JWT are forwarded to dockmaster token."""
        token = signer.sign(
            subject="user@example.com",
            audience="test-service",
            payload={
                "name": "Jane Doe",
                "given_name": "Jane",
                "family_name": "Doe",
                "locale": "en",
            },
        )

        response = exchange_client.post(
            "/auth/exchange",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        claims = response.json()["claims"]
        assert claims["name"] == "Jane Doe"
        assert claims["given_name"] == "Jane"
        assert claims["family_name"] == "Doe"
        assert claims["locale"] == "en"

    def test_profile_claims_absent_when_not_in_jwt(self, exchange_client, signer):
        """JWT without profile claims -> empty claims dict."""
        token = signer.sign(subject="user@example.com", audience="test-service")

        response = exchange_client.post(
            "/auth/exchange",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["claims"] == {}

    def test_output_token_is_type_c(self, exchange_client, signer, token_issuer):
        """Exchange output is a Type C token (iss='dockmaster', ephemeral kid)."""
        import jwt as pyjwt

        input_token = signer.sign(subject="user@example.com", audience="test-service")
        response = exchange_client.post(
            "/auth/exchange",
            headers={"Authorization": f"Bearer {input_token}"},
        )

        assert response.status_code == 200
        output_token = response.json()["token"]

        # Decode without verification to inspect claims
        claims = pyjwt.decode(output_token, options={"verify_signature": False})
        header = pyjwt.get_unverified_header(output_token)

        assert claims["iss"] == "dockmaster"
        assert claims["sub"] == "user@example.com"
        assert claims["aud"] == "test-service"
        assert header["kid"] == token_issuer.current_kid
        assert header["alg"] == "RS256"


class TestExchangeAccessTokenPath:
    """Tests for the access token (tokeninfo) fallback path."""

    def test_valid_access_token(self, mocker, app, fake_realm, fake_sa_key_data):
        """Valid access token with mocked tokeninfo -> 200."""
        settings = Settings(
            authorized_issuers={fake_sa_key_data["client_email"]},
            authorized_domains={"example.com"},
            authorized_audience={"test-client-id"},
        )
        tokeninfo_response = {
            "aud": "test-client-id",
            "email": "user@example.com",
            "scope": "openid email",
            "expires_in": "3600",
        }

        mocker.patch(
            "dockmaster.auth.dependencies.validate_access_token",
            new_callable=mocker.AsyncMock,
            return_value=tokeninfo_response,
        )
        with _ExchangeTestClient(app, settings, fake_realm) as client:
            response = client.post(
                "/auth/exchange?service=my-service",
                headers={"Authorization": "Bearer opaque-access-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["subject"] == "user@example.com"
        assert data["service"] == "my-service"
        assert data["claims"] == {}

    def test_access_token_without_service_param(self, mocker, app, fake_realm, fake_sa_key_data):
        """Access token without ?service= -> 400."""
        settings = Settings(
            authorized_issuers={fake_sa_key_data["client_email"]},
            authorized_domains={"example.com"},
            authorized_audience={"test-client-id"},
        )
        tokeninfo_response = {
            "aud": "test-client-id",
            "email": "user@example.com",
            "scope": "openid email",
        }

        mocker.patch(
            "dockmaster.auth.dependencies.validate_access_token",
            new_callable=mocker.AsyncMock,
            return_value=tokeninfo_response,
        )
        with _ExchangeTestClient(app, settings, fake_realm) as client:
            response = client.post(
                "/auth/exchange",
                headers={"Authorization": "Bearer opaque-access-token"},
            )

        assert response.status_code == 400
        assert "service query parameter is required" in response.json()["detail"]

    def test_access_token_no_profile_claims(self, mocker, app, fake_realm, fake_sa_key_data):
        """Access token path has no profile claims in response."""
        settings = Settings(
            authorized_issuers={fake_sa_key_data["client_email"]},
            authorized_domains={"example.com"},
            authorized_audience={"test-client-id"},
        )
        tokeninfo_response = {
            "aud": "test-client-id",
            "email": "user@example.com",
            "scope": "openid email",
        }

        mocker.patch(
            "dockmaster.auth.dependencies.validate_access_token",
            new_callable=mocker.AsyncMock,
            return_value=tokeninfo_response,
        )
        with _ExchangeTestClient(app, settings, fake_realm) as client:
            response = client.post(
                "/auth/exchange?service=my-service",
                headers={"Authorization": "Bearer opaque-access-token"},
            )

        assert response.status_code == 200
        assert response.json()["claims"] == {}


class TestExchangeErrors:
    """Error cases for /auth/exchange."""

    def test_missing_bearer_token(self, exchange_client):
        """No Authorization header -> 401."""
        response = exchange_client.post("/auth/exchange")
        assert response.status_code == 401

    def test_503_when_token_issuer_not_configured(self, app, signer, fake_realm, exchange_settings):
        """Returns 503 when token_issuer is not available.

        Uses a valid JWT so the auth gate passes, but token_issuer=None
        so the route's 503 check triggers.
        """
        token = signer.sign(subject="user@example.com", audience="test-service")
        app.state.settings = exchange_settings
        with TestClient(app) as client:
            app.state.token_issuer = None
            app.state.realm = fake_realm
            response = client.post(
                "/auth/exchange",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]

    def test_invalid_token_both_paths_fail(self, mocker, app, fake_realm):
        """Token that fails both JWT and tokeninfo -> 401."""
        settings = Settings(
            authorized_issuers=set(),
            authorized_domains={"example.com"},
            authorized_audience={"test"},
        )

        mocker.patch(
            "dockmaster.auth.dependencies.validate_access_token",
            new_callable=mocker.AsyncMock,
            side_effect=ValueError("Invalid access token"),
        )
        with _ExchangeTestClient(app, settings, fake_realm) as client:
            response = client.post(
                "/auth/exchange",
                headers={"Authorization": "Bearer garbage-token"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"
