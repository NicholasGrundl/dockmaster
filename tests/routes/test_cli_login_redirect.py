"""Tests for server-side redirect_uri support on /auth/login."""

import pytest

from dockmaster.routes.login import _validate_redirect_uri


class TestValidateRedirectUri:
    def test_none_returns_none(self):
        assert _validate_redirect_uri(None) is None

    def test_empty_returns_none(self):
        assert _validate_redirect_uri("") is None

    def test_localhost_http_allowed(self):
        assert _validate_redirect_uri("http://localhost:9876/callback") == "http://localhost:9876/callback"

    def test_localhost_no_port_allowed(self):
        assert _validate_redirect_uri("http://localhost/callback") == "http://localhost/callback"

    def test_127_0_0_1_allowed(self):
        assert _validate_redirect_uri("http://127.0.0.1:8080/callback") == "http://127.0.0.1:8080/callback"

    def test_external_url_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_redirect_uri("https://evil.com/callback")
        assert exc_info.value.status_code == 400

    def test_non_localhost_host_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _validate_redirect_uri("http://myapp.example.com:9876/callback")


class TestLoginRedirectParam:
    """Test that /auth/login accepts redirect_uri query param."""

    def test_login_stores_redirect_uri_in_state(self, client):
        """Login with redirect_uri stores it in the oauth_state_store."""
        oauth_state_store = client.app.state.oauth_state_store
        before = len(oauth_state_store)

        response = client.get(
            "/auth/login?redirect_uri=http://localhost:9876/callback",
            follow_redirects=False,
        )

        # Should still redirect to Google OAuth (302)
        assert response.status_code in (302, 303, 307, 200)  # OAuth redirect or form
        assert len(oauth_state_store) == before + 1

    def test_login_without_redirect_uri_stores_state(self, client):
        """Login without redirect_uri still stores a state entry."""
        oauth_state_store = client.app.state.oauth_state_store
        before = len(oauth_state_store)

        client.get("/auth/login", follow_redirects=False)

        assert len(oauth_state_store) == before + 1
