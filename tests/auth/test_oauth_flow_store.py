"""Tests for OAuthFlowStore — unified single-use store for OAuth login lifecycle."""

import time

import pytest

from dockmaster.auth.oauth_flow_store import LoginTicket, OAuthFlowStore, OAuthState


@pytest.fixture
def store() -> OAuthFlowStore:
    return OAuthFlowStore(oauth_state_ttl=600, login_ticket_ttl=300)


# ---------------------------------------------------------------------------
# OAuthState round-trip
# ---------------------------------------------------------------------------


class TestOAuthState:
    """create_oauth_state / consume round-trip."""

    def test_create_and_consume(self, store):
        key = store.create_oauth_state(redirect_uri="https://app.example.com/cb")
        entry = store.consume(key)
        assert isinstance(entry, OAuthState)
        assert entry.redirect_uri == "https://app.example.com/cb"

    def test_cookie_flow_no_redirect_uri(self, store):
        key = store.create_oauth_state()
        entry = store.consume(key)
        assert isinstance(entry, OAuthState)
        assert entry.redirect_uri is None

    def test_return_to_stored(self, store):
        key = store.create_oauth_state(return_to="/dashboard")
        entry = store.consume(key)
        assert entry.return_to == "/dashboard"

    def test_return_to_defaults_to_none(self, store):
        key = store.create_oauth_state()
        entry = store.consume(key)
        assert entry.return_to is None


# ---------------------------------------------------------------------------
# LoginTicket round-trip
# ---------------------------------------------------------------------------


class TestLoginTicket:
    """create_login_ticket / consume round-trip."""

    def test_create_and_consume(self, store):
        key = store.create_login_ticket(
            subject="user@example.com",
            redirect_uri="https://app.example.com/cb",
            profile={"name": "Test User"},
        )
        entry = store.consume(key)
        assert isinstance(entry, LoginTicket)
        assert entry.subject == "user@example.com"
        assert entry.redirect_uri == "https://app.example.com/cb"
        assert entry.profile == {"name": "Test User"}

    def test_return_to_forwarded(self, store):
        key = store.create_login_ticket(
            subject="user@example.com",
            redirect_uri="https://app.example.com/cb",
            return_to="/settings",
        )
        entry = store.consume(key)
        assert entry.return_to == "/settings"

    def test_empty_profile_default(self, store):
        key = store.create_login_ticket(
            subject="user@example.com",
            redirect_uri="https://app.example.com/cb",
        )
        entry = store.consume(key)
        assert entry.profile == {}


# ---------------------------------------------------------------------------
# Single-use semantics
# ---------------------------------------------------------------------------


class TestSingleUse:
    """Entries are consumed (deleted) on retrieval."""

    def test_oauth_state_single_use(self, store):
        key = store.create_oauth_state()
        assert store.consume(key) is not None
        assert store.consume(key) is None

    def test_login_ticket_single_use(self, store):
        key = store.create_login_ticket(
            subject="user@example.com",
            redirect_uri="https://app.example.com/cb",
        )
        assert store.consume(key) is not None
        assert store.consume(key) is None


# ---------------------------------------------------------------------------
# Unknown / expired keys
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Unknown keys, expired entries."""

    def test_unknown_key_returns_none(self, store):
        assert store.consume("nonexistent-key") is None

    def test_expired_oauth_state_returns_none(self):
        store = OAuthFlowStore(oauth_state_ttl=0)
        key = store.create_oauth_state()
        # TTL=0 means immediately expired
        time.sleep(0.01)
        assert store.consume(key) is None

    def test_expired_login_ticket_returns_none(self):
        store = OAuthFlowStore(login_ticket_ttl=0)
        key = store.create_login_ticket(
            subject="user@example.com",
            redirect_uri="https://app.example.com/cb",
        )
        time.sleep(0.01)
        assert store.consume(key) is None


# ---------------------------------------------------------------------------
# Type discrimination
# ---------------------------------------------------------------------------


class TestTypeDiscrimination:
    """isinstance() correctly distinguishes OAuthState from LoginTicket."""

    def test_oauth_state_is_not_login_ticket(self, store):
        key = store.create_oauth_state()
        entry = store.consume(key)
        assert isinstance(entry, OAuthState)
        assert not isinstance(entry, LoginTicket)

    def test_login_ticket_is_not_oauth_state(self, store):
        key = store.create_login_ticket(
            subject="user@example.com",
            redirect_uri="https://app.example.com/cb",
        )
        entry = store.consume(key)
        assert isinstance(entry, LoginTicket)
        assert not isinstance(entry, OAuthState)

    def test_keys_do_not_collide(self, store):
        """OAuth state and login ticket keys occupy separate namespaces."""
        state_key = store.create_oauth_state()
        ticket_key = store.create_login_ticket(
            subject="user@example.com",
            redirect_uri="https://app.example.com/cb",
        )
        assert state_key != ticket_key

        state_entry = store.consume(state_key)
        ticket_entry = store.consume(ticket_key)
        assert isinstance(state_entry, OAuthState)
        assert isinstance(ticket_entry, LoginTicket)
