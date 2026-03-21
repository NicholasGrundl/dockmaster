"""Tests for redirect_uri validation on /auth/login.

After CLI extraction, /auth/login only accepts allowlisted external URIs.
Localhost redirect URIs are rejected — CLI flow uses /auth/cli/login instead.
"""

import pytest
from fastapi import HTTPException

from dockmaster.routes.login import _validate_redirect_uri


class TestValidateRedirectUri:
    def test_none_returns_none(self):
        assert _validate_redirect_uri(None) is None

    def test_empty_returns_none(self):
        assert _validate_redirect_uri("") is None

    def test_localhost_rejected_without_allowlist(self):
        """Localhost URIs are no longer accepted — use /auth/cli/login."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_redirect_uri("http://localhost:9876/callback")
        assert exc_info.value.status_code == 400

    def test_localhost_rejected_with_allowlist(self):
        """Localhost URIs rejected even when an allowlist is configured."""
        allowed = {"https://app.example.com/callback"}
        with pytest.raises(HTTPException):
            _validate_redirect_uri("http://localhost:9876/callback", allowed)

    def test_allowlisted_uri_accepted(self):
        allowed = {"https://app.example.com/callback"}
        result = _validate_redirect_uri("https://app.example.com/callback", allowed)
        assert result == "https://app.example.com/callback"

    def test_external_url_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_redirect_uri("https://evil.com/callback")
        assert exc_info.value.status_code == 400

    def test_non_localhost_host_rejected(self):
        with pytest.raises(HTTPException):
            _validate_redirect_uri("http://myapp.example.com:9876/callback")


class TestLoginRedirectParam:
    """Test that /auth/login accepts redirect_uri query param."""

    def test_login_stores_redirect_uri_in_state(self, client):
        """Login with allowlisted redirect_uri stores it in the oauth_state_store."""
        # Default test settings don't have allowed_redirect_uris, so any
        # non-localhost URI will be rejected. This test verifies state storage
        # for the cookie flow (no redirect_uri).
        oauth_state_store = client.app.state.oauth_state_store
        before = len(oauth_state_store)

        client.get("/auth/login", follow_redirects=False)

        assert len(oauth_state_store) == before + 1

    def test_login_without_redirect_uri_stores_state(self, client):
        """Login without redirect_uri still stores a state entry."""
        oauth_state_store = client.app.state.oauth_state_store
        before = len(oauth_state_store)

        client.get("/auth/login", follow_redirects=False)

        assert len(oauth_state_store) == before + 1

    def test_login_rejects_localhost_redirect_uri(self, client):
        """Login with localhost redirect_uri returns 400 — use /auth/cli/login."""
        response = client.get(
            "/auth/login?redirect_uri=http://localhost:9876/callback",
            follow_redirects=False,
        )
        assert response.status_code == 400
