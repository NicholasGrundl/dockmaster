"""Tests for access token validation via Google tokeninfo API."""

from unittest.mock import AsyncMock

import httpx
import pytest

from dockmaster.auth.token_validator import validate_access_token


@pytest.fixture
def mock_httpx_client(monkeypatch):
    """Return a mock httpx.AsyncClient whose .get() can be configured per test."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def tokeninfo_response() -> dict:
    """A realistic tokeninfo response from Google."""
    return {
        "azp": "test-client-id.apps.googleusercontent.com",
        "aud": "test-client-id.apps.googleusercontent.com",
        "sub": "1234567890",
        "scope": "openid email profile",
        "exp": "9999999999",
        "expires_in": "3600",
        "email": "user@example.com",
        "email_verified": "true",
        "access_type": "online",
    }


class TestValidateAccessToken:
    """Unit tests for validate_access_token()."""

    async def test_valid_token_returns_claims(self, mock_httpx_client, tokeninfo_response):
        mock_httpx_client.get.return_value = httpx.Response(
            200, json=tokeninfo_response, request=httpx.Request("GET", "https://example.com")
        )

        result = await validate_access_token(
            token="valid-access-token",
            authorized_audiences={"test-client-id.apps.googleusercontent.com"},
            http_client=mock_httpx_client,
        )

        assert result["email"] == "user@example.com"
        assert result["aud"] == "test-client-id.apps.googleusercontent.com"
        mock_httpx_client.get.assert_called_once()

    async def test_non_200_raises_value_error(self, mock_httpx_client):
        mock_httpx_client.get.return_value = httpx.Response(
            400,
            json={"error_description": "Invalid Value"},
            request=httpx.Request("GET", "https://example.com"),
        )

        with pytest.raises(ValueError, match="Invalid access token"):
            await validate_access_token(
                token="bad-token",
                authorized_audiences={"test-client-id"},
                http_client=mock_httpx_client,
            )

    async def test_audience_not_allowed_raises_value_error(self, mock_httpx_client, tokeninfo_response):
        mock_httpx_client.get.return_value = httpx.Response(
            200, json=tokeninfo_response, request=httpx.Request("GET", "https://example.com")
        )

        with pytest.raises(ValueError, match="Audience not allowed"):
            await validate_access_token(
                token="valid-token",
                authorized_audiences={"some-other-audience"},
                http_client=mock_httpx_client,
            )

    async def test_tokeninfo_url_constructed_correctly(self, mock_httpx_client, tokeninfo_response):
        mock_httpx_client.get.return_value = httpx.Response(
            200, json=tokeninfo_response, request=httpx.Request("GET", "https://example.com")
        )

        await validate_access_token(
            token="my-token",
            authorized_audiences={"test-client-id.apps.googleusercontent.com"},
            http_client=mock_httpx_client,
            tokeninfo_url="https://oauth2.googleapis.com/tokeninfo",
        )

        call_args = mock_httpx_client.get.call_args
        assert "access_token" in str(call_args)
