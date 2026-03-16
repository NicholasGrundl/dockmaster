"""Tests for JWTTokenIssuer — ephemeral RSA keypair JWT signing."""

import jwt

from dockmaster.auth.token_issuer import JWTTokenIssuer


class TestJWTTokenIssuerConstruction:
    """Test keypair generation and properties on construction."""

    def test_generates_kid_on_construction(self):
        issuer = JWTTokenIssuer(ttl=900)
        assert issuer.current_kid is not None
        assert issuer.current_kid.startswith("dk-")

    def test_kid_contains_date_and_uuid(self):
        issuer = JWTTokenIssuer(ttl=900)
        parts = issuer.current_kid.split("-")
        # dk-YYYY-MM-DD-uuid8
        assert parts[0] == "dk"
        assert len(parts) == 5
        assert len(parts[-1]) == 8  # uuid[:8]

    def test_generates_unique_kids(self):
        a = JWTTokenIssuer(ttl=900)
        b = JWTTokenIssuer(ttl=900)
        assert a.current_kid != b.current_kid

    def test_current_public_jwk_format(self):
        issuer = JWTTokenIssuer(ttl=900)
        jwk = issuer.current_public_jwk
        assert jwk["kty"] == "RSA"
        assert jwk["alg"] == "RS256"
        assert jwk["use"] == "sig"
        assert jwk["kid"] == issuer.current_kid
        assert "n" in jwk  # modulus
        assert "e" in jwk  # exponent

    def test_public_jwk_does_not_contain_private_fields(self):
        issuer = JWTTokenIssuer(ttl=900)
        jwk = issuer.current_public_jwk
        # RSA private key fields must not be present
        for field in ("d", "p", "q", "dp", "dq", "qi"):
            assert field not in jwk

    def test_default_ttl_stored(self):
        issuer = JWTTokenIssuer(ttl=1800)
        assert issuer.default_ttl == 1800


class TestJWTTokenIssuerSigning:
    """Test JWT signing behavior."""

    def test_sign_returns_valid_jwt(self):
        issuer = JWTTokenIssuer(ttl=900)
        token = issuer.sign(subject="nick@example.com", audience="billing-service")
        # Should be a three-part JWT
        assert token.count(".") == 2

    def test_sign_claims_content(self):
        issuer = JWTTokenIssuer(ttl=900)
        token = issuer.sign(subject="nick@example.com", audience="billing-service")
        # Decode without verification to inspect claims
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["sub"] == "nick@example.com"
        assert claims["email"] == "nick@example.com"
        assert claims["iss"] == "dockmaster"
        assert claims["aud"] == "billing-service"
        assert "iat" in claims
        assert "exp" in claims

    def test_sign_uses_default_ttl(self):
        issuer = JWTTokenIssuer(ttl=900)
        token = issuer.sign(subject="nick@example.com", audience="svc")
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["exp"] - claims["iat"] == 900

    def test_sign_ttl_override(self):
        issuer = JWTTokenIssuer(ttl=900)
        token = issuer.sign(subject="nick@example.com", audience="svc", ttl=3600)
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["exp"] - claims["iat"] == 3600

    def test_sign_kid_in_header(self):
        issuer = JWTTokenIssuer(ttl=900)
        token = issuer.sign(subject="nick@example.com", audience="svc")
        header = jwt.get_unverified_header(token)
        assert header["kid"] == issuer.current_kid
        assert header["alg"] == "RS256"

    def test_sign_extra_claims(self):
        issuer = JWTTokenIssuer(ttl=900)
        token = issuer.sign(
            subject="nick@example.com",
            audience="svc",
            extra_claims={"name": "Nick", "picture": "https://example.com/pic.jpg"},
        )
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["name"] == "Nick"
        assert claims["picture"] == "https://example.com/pic.jpg"

    def test_sign_extra_claims_cannot_override_core(self):
        """Extra claims should not override sub, iss, aud, etc."""
        issuer = JWTTokenIssuer(ttl=900)
        token = issuer.sign(
            subject="nick@example.com",
            audience="svc",
            extra_claims={"iss": "evil", "sub": "attacker@evil.com"},
        )
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["iss"] == "dockmaster"
        assert claims["sub"] == "nick@example.com"

    def test_sign_verifiable_with_public_key(self):
        """Token signed by issuer should be verifiable with its public JWK."""
        issuer = JWTTokenIssuer(ttl=900)
        token = issuer.sign(subject="nick@example.com", audience="svc")

        # Build public key from JWK
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        import base64

        jwk = issuer.current_public_jwk
        n = int.from_bytes(base64.urlsafe_b64decode(jwk["n"] + "=="), "big")
        e = int.from_bytes(base64.urlsafe_b64decode(jwk["e"] + "=="), "big")
        pub_key = RSAPublicNumbers(e, n).public_key()
        pub_pem = pub_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

        claims = jwt.decode(token, pub_pem, algorithms=["RS256"], audience="svc")
        assert claims["sub"] == "nick@example.com"
