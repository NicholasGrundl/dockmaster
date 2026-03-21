"""End-to-end ServiceRealm verification: both SA and ephemeral signers through multi-cache realm.

Phase 7, sub-task 6 — proves that Type A/B (SA-signed) and Type C (ephemeral-signed) JWTs
both verify correctly through a single ServiceRealm with [EphemeralKeyCache, SA cache].
"""


import json

import pytest

from dockmaster.auth.jwt_signers import EphemeralKeypairSigner, ServiceAccountSigner
from dockmaster.auth.jwt_verifier import ServiceRealm
from dockmaster.auth.key_cache import EphemeralKeyCache


class FakeKeyCache:
    """Minimal key cache for testing (same as in test_jwt_verifier.py)."""

    def __init__(self, keys: dict[str, str] | None = None):
        self._keys = keys or {}

    def get_key(self, kid: str) -> str | None:
        return self._keys.get(kid)

    def get_all_keys(self) -> dict[str, str]:
        return dict(self._keys)


@pytest.fixture
def issuer() -> EphemeralKeypairSigner:
    """Fresh ephemeral token issuer."""
    return EphemeralKeypairSigner(ttl=900)


@pytest.fixture
def ephemeral_cache(issuer: EphemeralKeypairSigner, tmp_path) -> EphemeralKeyCache:
    """EphemeralKeyCache wired to the test issuer's public key."""
    registry_path = str(tmp_path / "jwks-registry.json")
    return EphemeralKeyCache(
        kid=issuer.current_kid,
        public_jwk=issuer.current_public_jwk,
        registry_path=registry_path,
    )


@pytest.fixture
def sa_cache(rsa_public_key_pem, fake_sa_key_data) -> FakeKeyCache:
    """Fake SA key cache with the test RSA public key."""
    kid = fake_sa_key_data["private_key_id"]
    return FakeKeyCache({kid: rsa_public_key_pem})


@pytest.fixture
def multi_realm(ephemeral_cache, sa_cache) -> ServiceRealm:
    """ServiceRealm with [ephemeral, SA] cache ordering."""
    return ServiceRealm(key_cache=[ephemeral_cache, sa_cache])


class TestEphemeralTokenVerification:
    """Type C tokens (EphemeralKeypairSigner) through ServiceRealm."""

    def test_ephemeral_token_verifies(self, multi_realm, issuer):
        """Type C token signed by EphemeralKeypairSigner verifies through multi-cache realm."""
        token = issuer.sign(subject="user@example.com", audience="billing-service")
        claims = multi_realm.verify(token)

        assert claims["sub"] == "user@example.com"
        assert claims["iss"] == "dockmaster"
        assert claims["aud"] == "billing-service"
        assert claims["email"] == "user@example.com"

    def test_ephemeral_token_kid_in_header(self, multi_realm, issuer):
        """Type C token header contains the issuer's kid."""
        import jwt as pyjwt

        token = issuer.sign(subject="u@ex.com", audience="svc")
        header = pyjwt.get_unverified_header(token)

        assert header["kid"] == issuer.current_kid
        assert header["alg"] == "RS256"

    def test_ephemeral_token_with_extra_claims(self, multi_realm, issuer):
        """Extra claims are included in the verified token."""
        token = issuer.sign(
            subject="u@ex.com",
            audience="svc",
            extra_claims={"name": "Test User", "picture": "https://example.com/photo.jpg"},
        )
        claims = multi_realm.verify(token)

        assert claims["name"] == "Test User"
        assert claims["picture"] == "https://example.com/photo.jpg"

    def test_ephemeral_token_custom_ttl(self, multi_realm, issuer):
        """Custom TTL is reflected in exp claim."""
        token = issuer.sign(subject="u@ex.com", audience="svc", ttl=60)
        claims = multi_realm.verify(token)

        assert claims["exp"] - claims["iat"] == 60


class TestSATokenVerification:
    """Type A/B tokens (ServiceAccountSigner) through the same multi-cache realm."""

    def test_sa_token_verifies(self, multi_realm, fake_sa_key_data):
        """Type A/B token signed by ServiceAccountSigner verifies through multi-cache realm."""
        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        token = su.sign(subject="user@example.com", audience="test-service")
        claims = multi_realm.verify(token)

        assert claims["sub"] == "user@example.com"
        assert claims["iss"] == fake_sa_key_data["client_email"]

    def test_sa_token_found_in_second_cache(self, multi_realm, fake_sa_key_data):
        """SA token's kid is not in ephemeral cache, found in SA cache (second)."""
        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        token = su.sign(subject="u@ex.com", audience="svc")

        # Verify it works — the ephemeral cache won't have this kid,
        # so the realm must check the SA cache (second in order)
        claims = multi_realm.verify(token)
        assert claims["sub"] == "u@ex.com"


class TestBothSignersCoexist:
    """Both signers work through a single realm without interference."""

    def test_mixed_tokens_both_verify(self, multi_realm, issuer, fake_sa_key_data):
        """Both Type C and Type A/B tokens verify through the same realm."""
        # Type C (ephemeral)
        type_c_token = issuer.sign(subject="alice@example.com", audience="billing")
        type_c_claims = multi_realm.verify(type_c_token)

        # Type A/B (SA)
        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        type_ab_token = su.sign(subject="bob@example.com", audience="billing")
        type_ab_claims = multi_realm.verify(type_ab_token)

        # Both verified successfully with correct issuers
        assert type_c_claims["iss"] == "dockmaster"
        assert type_ab_claims["iss"] == fake_sa_key_data["client_email"]

    def test_kid_routing_is_correct(self, multi_realm, issuer, fake_sa_key_data):
        """Realm routes to correct cache based on kid — no cross-contamination."""
        # Ephemeral kid resolves from ephemeral cache
        ephemeral_key = multi_realm.get_key(issuer.current_kid)
        assert ephemeral_key is not None

        # SA kid resolves from SA cache
        sa_kid = fake_sa_key_data["private_key_id"]
        sa_key = multi_realm.get_key(sa_kid)
        assert sa_key is not None

        # Keys are different
        assert ephemeral_key != sa_key

    def test_unknown_kid_fails_across_both_caches(self, multi_realm):
        """A kid that doesn't exist in either cache raises ValueError."""
        import jwt as pyjwt

        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

        # Generate a completely separate key
        rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rogue_pem = rogue_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

        token = pyjwt.encode(
            {"sub": "attacker@evil.com"},
            rogue_pem,
            algorithm="RS256",
            headers={"kid": "rogue-kid-not-in-any-cache"},
        )

        with pytest.raises(ValueError, match="Unknown key"):
            multi_realm.verify(token)


class TestEphemeralKeyCacheIntegration:
    """EphemeralKeyCache correctly converts JWK → PEM for realm verification."""

    def test_cache_has_key_for_issuer_kid(self, ephemeral_cache, issuer):
        """EphemeralKeyCache contains a PEM key for the issuer's kid."""
        pem = ephemeral_cache.get_key(issuer.current_kid)
        assert pem is not None
        assert "BEGIN PUBLIC KEY" in pem

    def test_cache_persists_to_registry(self, issuer, tmp_path):
        """Registry file is written with the current key."""
        registry_path = str(tmp_path / "registry.json")
        EphemeralKeyCache(
            kid=issuer.current_kid,
            public_jwk=issuer.current_public_jwk,
            registry_path=registry_path,
        )

        data = json.loads((tmp_path / "registry.json").read_text())
        kids = [e["kid"] for e in data["keys"]]
        assert issuer.current_kid in kids

    def test_previous_key_survives_new_cache(self, tmp_path):
        """A key from a previous process instance survives when a new cache is created."""
        registry_path = str(tmp_path / "registry.json")

        # Process 1: create issuer + cache
        issuer1 = EphemeralKeypairSigner(ttl=900)
        EphemeralKeyCache(
            kid=issuer1.current_kid,
            public_jwk=issuer1.current_public_jwk,
            registry_path=registry_path,
        )

        # Process 2: new issuer + cache (loads registry from disk)
        issuer2 = EphemeralKeypairSigner(ttl=900)
        cache2 = EphemeralKeyCache(
            kid=issuer2.current_kid,
            public_jwk=issuer2.current_public_jwk,
            registry_path=registry_path,
        )

        # Both keys should be available
        assert cache2.get_key(issuer1.current_kid) is not None
        assert cache2.get_key(issuer2.current_kid) is not None

    def test_previous_process_token_still_verifies(self, tmp_path, fake_sa_key_data, rsa_public_key_pem):
        """A Type C token from a previous process verifies after restart."""
        registry_path = str(tmp_path / "registry.json")
        sa_cache = FakeKeyCache({fake_sa_key_data["private_key_id"]: rsa_public_key_pem})

        # Process 1: sign a token
        issuer1 = EphemeralKeypairSigner(ttl=900)
        token = issuer1.sign(subject="alice@example.com", audience="billing")
        EphemeralKeyCache(
            kid=issuer1.current_kid,
            public_jwk=issuer1.current_public_jwk,
            registry_path=registry_path,
        )

        # Process 2: new issuer, new cache (loads old key from registry)
        issuer2 = EphemeralKeypairSigner(ttl=900)
        cache2 = EphemeralKeyCache(
            kid=issuer2.current_kid,
            public_jwk=issuer2.current_public_jwk,
            registry_path=registry_path,
        )
        realm2 = ServiceRealm(key_cache=[cache2, sa_cache])

        # Token from process 1 should still verify in process 2
        claims = realm2.verify(token)
        assert claims["sub"] == "alice@example.com"
        assert claims["iss"] == "dockmaster"
