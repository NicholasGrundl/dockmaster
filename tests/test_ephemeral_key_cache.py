"""Tests for EphemeralKeyCache — public key registry with persistence."""

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from dockmaster.auth.key_cache import EphemeralKeyCache


def _generate_jwk(kid: str) -> dict:
    """Generate a real RSA JWK using cryptography directly."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_numbers = private_key.public_key().public_numbers()

    def _int_to_b64url(n: int) -> str:
        length = (n.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

    return {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": kid,
        "n": _int_to_b64url(pub_numbers.n),
        "e": _int_to_b64url(pub_numbers.e),
    }


@pytest.fixture
def sample_jwk():
    """A real RSA JWK for testing."""
    return _generate_jwk("dk-2026-03-16-abc12345")


@pytest.fixture
def registry_path(tmp_path):
    """A temporary registry file path."""
    return str(tmp_path / "jwks-registry.json")


class TestEphemeralKeyCacheConstruction:
    """Test cache construction and key serving."""

    def test_serves_current_key(self, sample_jwk, registry_path):
        cache = EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=registry_path,
        )
        assert cache.get_key(sample_jwk["kid"]) is not None

    def test_get_key_returns_none_for_unknown_kid(self, sample_jwk, registry_path):
        cache = EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=registry_path,
        )
        assert cache.get_key("unknown-kid") is None

    def test_get_all_keys_includes_current(self, sample_jwk, registry_path):
        cache = EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=registry_path,
        )
        all_keys = cache.get_all_keys()
        assert sample_jwk["kid"] in all_keys

    def test_creates_registry_file(self, sample_jwk, registry_path):
        EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=registry_path,
        )
        with open(registry_path) as f:
            data = json.load(f)
        assert len(data["keys"]) == 1
        assert data["keys"][0]["kid"] == sample_jwk["kid"]

    def test_registry_entry_has_created_at(self, sample_jwk, registry_path):
        before = time.time()
        EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=registry_path,
        )
        with open(registry_path) as f:
            data = json.load(f)
        created_at = data["keys"][0]["created_at"]
        assert created_at >= before
        assert created_at <= time.time()


class TestEphemeralKeyCacheRegistryPersistence:
    """Test that keys from previous restarts survive."""

    def test_retains_keys_from_previous_instance(self, registry_path):
        """Simulate two restarts — both keys should be present."""
        jwk_a = _generate_jwk("dk-old-aaa")
        jwk_b = _generate_jwk("dk-new-bbb")

        EphemeralKeyCache(kid="dk-old-aaa", public_jwk=jwk_a, registry_path=registry_path)
        cache = EphemeralKeyCache(kid="dk-new-bbb", public_jwk=jwk_b, registry_path=registry_path)

        assert cache.get_key("dk-old-aaa") is not None
        assert cache.get_key("dk-new-bbb") is not None

    def test_handles_missing_registry_file(self, sample_jwk, tmp_path):
        """First-ever startup — no registry file exists."""
        path = str(tmp_path / "nonexistent" / "jwks-registry.json")
        cache = EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=path,
        )
        assert cache.get_key(sample_jwk["kid"]) is not None

    def test_handles_corrupt_registry_file(self, sample_jwk, registry_path):
        """Corrupt registry file — should start fresh."""
        with open(registry_path, "w") as f:
            f.write("not json!!!")
        cache = EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=registry_path,
        )
        assert cache.get_key(sample_jwk["kid"]) is not None
        all_keys = cache.get_all_keys()
        assert len(all_keys) == 1


class TestEphemeralKeyCachePruning:
    """Test that stale keys are pruned at construction."""

    def test_recent_old_keys_not_pruned(self, registry_path):
        """Old keys within retention window should be kept."""
        now = time.time()
        jwk_old = _generate_jwk("dk-recent-old")
        old_entry = {"kid": "dk-recent-old", "public_jwk": jwk_old, "created_at": now - 1000}
        with open(registry_path, "w") as f:
            json.dump({"keys": [old_entry]}, f)

        jwk_new = _generate_jwk("dk-new")
        cache = EphemeralKeyCache(
            kid="dk-new",
            public_jwk=jwk_new,
            registry_path=registry_path,
            retention=3600,
        )
        assert cache.get_key("dk-recent-old") is not None
        assert cache.get_key("dk-new") is not None

    def test_old_keys_beyond_retention_are_pruned(self, registry_path):
        """Keys older than retention (by created_at age) should be pruned."""
        now = time.time()
        jwk_ancient = _generate_jwk("dk-ancient")
        jwk_recent = _generate_jwk("dk-recent")
        ancient_entry = {"kid": "dk-ancient", "public_jwk": jwk_ancient, "created_at": now - 200000}
        recent_entry = {"kid": "dk-recent", "public_jwk": jwk_recent, "created_at": now - 50000}
        with open(registry_path, "w") as f:
            json.dump({"keys": [ancient_entry, recent_entry]}, f)

        jwk_new = _generate_jwk("dk-new")
        cache = EphemeralKeyCache(
            kid="dk-new",
            public_jwk=jwk_new,
            registry_path=registry_path,
            retention=100000,
        )
        assert cache.get_key("dk-ancient") is None  # 200000s old > 100000 retention
        assert cache.get_key("dk-recent") is not None  # 50000s old < 100000 retention
        assert cache.get_key("dk-new") is not None

    def test_current_key_never_pruned_even_if_old(self, registry_path):
        """The current key is never pruned regardless of age."""
        now = time.time()
        jwk = _generate_jwk("dk-current")
        old_current = {"kid": "dk-current", "public_jwk": jwk, "created_at": now - 999999}
        with open(registry_path, "w") as f:
            json.dump({"keys": [old_current]}, f)

        cache = EphemeralKeyCache(
            kid="dk-current",
            public_jwk=jwk,
            registry_path=registry_path,
            retention=1,
        )
        assert cache.get_key("dk-current") is not None


class TestEphemeralKeyCacheRetention:
    """Test retention and padding configuration."""

    def test_default_retention(self, sample_jwk, registry_path):
        cache = EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=registry_path,
        )
        assert cache._retention == 43200

    def test_custom_retention(self, sample_jwk, registry_path):
        cache = EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=registry_path,
            retention=7200,
        )
        assert cache._retention == 7200

    def test_update_is_noop(self, sample_jwk, registry_path):
        """update() should not change the keys."""
        cache = EphemeralKeyCache(
            kid=sample_jwk["kid"],
            public_jwk=sample_jwk,
            registry_path=registry_path,
        )
        keys_before = cache.get_all_keys()
        cache.update()
        keys_after = cache.get_all_keys()
        assert keys_before == keys_after
