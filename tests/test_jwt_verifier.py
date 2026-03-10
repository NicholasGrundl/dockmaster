"""Tests for ServiceRealm (JWT verification)."""

import jwt as pyjwt
import pytest


class FakeKeyCache:
    """Minimal key cache for testing ServiceRealm in isolation."""

    def __init__(self, keys: dict[str, str] | None = None):
        self._keys = keys or {}

    def get_key(self, kid: str) -> str | None:
        return self._keys.get(kid)

    def get_all_keys(self) -> dict[str, str]:
        return dict(self._keys)


class TestVerifyWithKid:
    """ServiceRealm.verify() when token has a kid header."""

    def test_round_trip_sign_verify(self, fake_sa_key_data, rsa_public_key_pem):
        from dockmaster.auth.jwt_signer import ServiceUser
        from dockmaster.auth.jwt_verifier import ServiceRealm

        su = ServiceUser(credentials=fake_sa_key_data)
        token = su.get_token(subject="user@example.com", service_name="svc")

        cache = FakeKeyCache({"test-key-id-001": rsa_public_key_pem})
        realm = ServiceRealm(key_cache=cache)
        claims = realm.verify(token)

        assert claims["sub"] == "user@example.com"
        assert claims["iss"] == "test-sa@test-project.iam.gserviceaccount.com"

    def test_unknown_kid_raises(self, fake_sa_key_data):
        from dockmaster.auth.jwt_signer import ServiceUser
        from dockmaster.auth.jwt_verifier import ServiceRealm

        su = ServiceUser(credentials=fake_sa_key_data)
        token = su.get_token(subject="u@ex.com", service_name="svc")

        cache = FakeKeyCache({"other-key": "not-a-real-pem"})
        realm = ServiceRealm(key_cache=cache)

        with pytest.raises(ValueError, match="Unknown key"):
            realm.verify(token)


class TestVerifyWithoutKid:
    """ServiceRealm.verify() when token has no kid header (fallback mode)."""

    def test_fallback_tries_all_keys(self, rsa_private_key_pem, rsa_public_key_pem):
        from dockmaster.auth.jwt_verifier import ServiceRealm

        # Sign a token without kid header
        token = pyjwt.encode(
            {"sub": "u@ex.com", "iss": "test"},
            rsa_private_key_pem,
            algorithm="RS256",
            # No kid header
        )

        cache = FakeKeyCache(
            {
                "wrong-key": "not-valid",
                "right-key": rsa_public_key_pem,
            }
        )
        realm = ServiceRealm(key_cache=cache)
        claims = realm.verify(token)
        assert claims["sub"] == "u@ex.com"

    def test_fallback_fails_when_no_key_matches(self, rsa_private_key_pem):
        from dockmaster.auth.jwt_verifier import ServiceRealm

        token = pyjwt.encode(
            {"sub": "u@ex.com"},
            rsa_private_key_pem,
            algorithm="RS256",
        )

        cache = FakeKeyCache({"k1": "bad-pem-1", "k2": "bad-pem-2"})
        realm = ServiceRealm(key_cache=cache)

        with pytest.raises(ValueError, match="No cached key"):
            realm.verify(token)


class TestVerifyEdgeCases:
    """Edge cases and malformed tokens."""

    def test_malformed_token_too_few_parts(self):
        from dockmaster.auth.jwt_verifier import ServiceRealm

        cache = FakeKeyCache()
        realm = ServiceRealm(key_cache=cache)

        with pytest.raises(ValueError, match="three"):
            realm.verify("only.two")

    def test_malformed_token_not_a_string(self):
        from dockmaster.auth.jwt_verifier import ServiceRealm

        cache = FakeKeyCache()
        realm = ServiceRealm(key_cache=cache)

        with pytest.raises((ValueError, TypeError)):
            realm.verify("")

    def test_expired_token_raises(self, fake_sa_key_data, rsa_public_key_pem):
        from dockmaster.auth.jwt_signer import ServiceUser
        from dockmaster.auth.jwt_verifier import ServiceRealm

        su = ServiceUser(credentials=fake_sa_key_data)
        # expiry=0 means it expires immediately
        token = su.get_token(subject="u@ex.com", service_name="svc", expiry=-1)

        cache = FakeKeyCache({"test-key-id-001": rsa_public_key_pem})
        realm = ServiceRealm(key_cache=cache)

        with pytest.raises(ValueError, match="[Ee]xpir"):
            realm.verify(token)
