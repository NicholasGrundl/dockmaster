"""Tests for KeyCache base class (TTL logic only, no GCP)."""

import time


from dockmaster.auth.key_cache import KeyCache


class TrackingKeyCache(KeyCache):
    """KeyCache subclass that counts update() calls."""

    def __init__(self, keys: dict[str, str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._staged_keys = keys or {}
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1
        self._keys = dict(self._staged_keys)
        self._updated_at = time.time()


class TestKeyCacheInit:
    def test_starts_empty(self):
        cache = KeyCache()
        assert cache.get_all_keys() == {}

    def test_starts_expired(self):
        cache = KeyCache(expiry=300)
        assert cache._is_expired() is True


class TestKeyCacheTTL:
    def test_not_expired_after_update(self):
        cache = TrackingKeyCache(expiry=300)
        cache.update()
        assert cache._is_expired() is False

    def test_expired_after_ttl(self):
        cache = TrackingKeyCache(expiry=0)
        cache.update()
        # expiry=0 means it's always expired
        assert cache._is_expired() is True


class TestGetKey:
    def test_get_key_triggers_update_when_expired(self):
        cache = TrackingKeyCache(keys={"k1": "pem1"}, expiry=300)
        assert cache.update_count == 0
        result = cache.get_key("k1")
        assert result == "pem1"
        assert cache.update_count == 1

    def test_get_key_does_not_update_when_fresh(self):
        cache = TrackingKeyCache(keys={"k1": "pem1"}, expiry=300)
        cache.update()  # make it fresh
        assert cache.update_count == 1
        cache.get_key("k1")
        assert cache.update_count == 1  # no additional update

    def test_get_key_returns_none_for_unknown_kid(self):
        cache = TrackingKeyCache(keys={"k1": "pem1"}, expiry=300)
        assert cache.get_key("unknown") is None

    def test_get_all_keys_returns_copy(self):
        cache = TrackingKeyCache(keys={"k1": "pem1", "k2": "pem2"}, expiry=300)
        cache.update()
        all_keys = cache.get_all_keys()
        assert all_keys == {"k1": "pem1", "k2": "pem2"}
        # Modifying returned dict shouldn't affect cache
        all_keys["k3"] = "pem3"
        assert "k3" not in cache.get_all_keys()


class TestBaseUpdateIsNoop:
    def test_base_update_does_not_raise(self):
        cache = KeyCache()
        cache.update()  # should be a no-op
