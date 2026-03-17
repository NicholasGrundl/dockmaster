"""Tests for ServiceAccountSigner (JWT signing)."""

import time

import jwt


class TestServiceAccountSignerFromDict:
    """ServiceAccountSigner initialized from a parsed dict."""

    def test_creates_from_dict(self, fake_sa_key_data):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        assert su.client_email == "test-sa@test-project.iam.gserviceaccount.com"
        assert su.private_key_id == "test-key-id-001"

    def test_creates_from_file_path(self, fake_sa_key_path):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=str(fake_sa_key_path))
        assert su.client_email == "test-sa@test-project.iam.gserviceaccount.com"


class TestSign:
    """ServiceAccountSigner.sign() produces valid JWTs."""

    def test_returns_string(self, fake_sa_key_data, rsa_public_key_pem):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        token = su.sign(subject="user@example.com", audience="my-service")
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT structure

    def test_claims_iss_is_client_email(self, fake_sa_key_data, rsa_public_key_pem):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        token = su.sign(subject="user@example.com", audience="my-service")
        claims = jwt.decode(token, rsa_public_key_pem, algorithms=["RS256"], options={"verify_aud": False})
        assert claims["iss"] == "test-sa@test-project.iam.gserviceaccount.com"

    def test_claims_sub_and_email(self, fake_sa_key_data, rsa_public_key_pem):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        token = su.sign(subject="user@example.com", audience="my-service")
        claims = jwt.decode(token, rsa_public_key_pem, algorithms=["RS256"], options={"verify_aud": False})
        assert claims["sub"] == "user@example.com"
        assert claims["email"] == "user@example.com"

    def test_claims_aud_is_audience(self, fake_sa_key_data, rsa_public_key_pem):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        token = su.sign(subject="user@example.com", audience="my-service")
        claims = jwt.decode(token, rsa_public_key_pem, algorithms=["RS256"], options={"verify_aud": False})
        assert claims["aud"] == "my-service"

    def test_claims_iat_and_exp(self, fake_sa_key_data, rsa_public_key_pem):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        before = int(time.time())
        token = su.sign(subject="user@example.com", audience="my-service", expiry=3600)
        after = int(time.time())
        claims = jwt.decode(token, rsa_public_key_pem, algorithms=["RS256"], options={"verify_aud": False})

        assert before <= claims["iat"] <= after
        assert claims["exp"] == claims["iat"] + 3600

    def test_default_subject_is_client_email(self, fake_sa_key_data, rsa_public_key_pem):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        token = su.sign(subject=None, audience="my-service")
        claims = jwt.decode(token, rsa_public_key_pem, algorithms=["RS256"], options={"verify_aud": False})
        assert claims["sub"] == "test-sa@test-project.iam.gserviceaccount.com"
        assert claims["email"] == "test-sa@test-project.iam.gserviceaccount.com"

    def test_extra_payload_merged(self, fake_sa_key_data, rsa_public_key_pem):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        token = su.sign(subject="u@ex.com", audience="svc", payload={"role": "admin"})
        claims = jwt.decode(token, rsa_public_key_pem, algorithms=["RS256"], options={"verify_aud": False})
        assert claims["role"] == "admin"

    def test_header_contains_kid(self, fake_sa_key_data):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        token = su.sign(subject="u@ex.com", audience="svc")
        header = jwt.get_unverified_header(token)
        assert header["kid"] == "test-key-id-001"
        assert header["alg"] == "RS256"


class TestGetAuthorization:
    """ServiceAccountSigner.get_authorization() returns a Bearer string."""

    def test_returns_bearer_prefix(self, fake_sa_key_data):
        from dockmaster.auth.jwt_signers import ServiceAccountSigner

        su = ServiceAccountSigner(credentials=fake_sa_key_data)
        auth = su.get_authorization(subject="u@ex.com", audience="svc")
        assert auth.startswith("Bearer ")
        token = auth.removeprefix("Bearer ")
        assert token.count(".") == 2
