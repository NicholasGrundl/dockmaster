"""Tests for authorization code store."""

import time

from dockmaster.auth.auth_code import AuthCodeStore


class TestAuthCodeStore:
    """Auth code store: create, consume, expiry, single-use."""

    def test_create_returns_string(self):
        store = AuthCodeStore()
        code = store.create(subject="user@example.com", redirect_uri="https://app.example.com/callback")
        assert isinstance(code, str)
        assert len(code) > 20  # cryptographically random, should be long

    def test_consume_valid_code(self):
        store = AuthCodeStore()
        code = store.create(subject="user@example.com", redirect_uri="https://app.example.com/callback")
        entry = store.consume(code, redirect_uri="https://app.example.com/callback")
        assert entry is not None
        assert entry.subject == "user@example.com"
        assert entry.redirect_uri == "https://app.example.com/callback"

    def test_consume_single_use(self):
        """Consuming a code twice returns None the second time."""
        store = AuthCodeStore()
        code = store.create(subject="user@example.com", redirect_uri="https://app.example.com/callback")
        entry = store.consume(code, redirect_uri="https://app.example.com/callback")
        assert entry is not None
        # Second attempt
        entry2 = store.consume(code, redirect_uri="https://app.example.com/callback")
        assert entry2 is None

    def test_consume_nonexistent_code(self):
        store = AuthCodeStore()
        entry = store.consume("bogus-code", redirect_uri="https://app.example.com/callback")
        assert entry is None

    def test_consume_wrong_redirect_uri(self):
        """Mismatched redirect_uri consumes the code but returns None."""
        store = AuthCodeStore()
        code = store.create(subject="user@example.com", redirect_uri="https://app.example.com/callback")
        entry = store.consume(code, redirect_uri="https://evil.com/callback")
        assert entry is None
        # Code is now consumed — even correct URI won't work
        entry2 = store.consume(code, redirect_uri="https://app.example.com/callback")
        assert entry2 is None

    def test_consume_expired_code(self, monkeypatch):
        """Expired codes return None."""
        store = AuthCodeStore(ttl=60)
        code = store.create(subject="user@example.com", redirect_uri="https://app.example.com/callback")
        # Fast-forward time past TTL
        future = time.time() + 120
        monkeypatch.setattr(time, "time", lambda: future)
        entry = store.consume(code, redirect_uri="https://app.example.com/callback")
        assert entry is None

    def test_prune_expired_on_create(self, monkeypatch):
        """Expired codes are pruned when new codes are created."""
        store = AuthCodeStore(ttl=60)
        store.create(subject="old@example.com", redirect_uri="https://app.example.com/callback")
        assert len(store._codes) == 1

        # Fast-forward and create a new code
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 120)
        store.create(subject="new@example.com", redirect_uri="https://app.example.com/callback")
        # Old code should have been pruned, only new one remains
        assert len(store._codes) == 1

    def test_unique_codes(self):
        """Each call to create() generates a unique code."""
        store = AuthCodeStore()
        codes = {
            store.create(subject="user@example.com", redirect_uri="https://app.example.com/callback") for _ in range(50)
        }
        assert len(codes) == 50
