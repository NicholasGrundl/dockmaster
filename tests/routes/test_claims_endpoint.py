"""Tests for GET /auth/claims."""


class TestGetClaims:
    def test_valid_auth_returns_claims(self, auth_client, valid_token):
        response = auth_client.get("/auth/claims", headers={"Authorization": f"Bearer {valid_token}"})
        assert response.status_code == 200
        claims = response.json()
        assert "sub" in claims
        assert "email" in claims
        assert "exp" in claims
        assert "iat" in claims

    def test_no_auth_returns_401(self, auth_client):
        response = auth_client.get("/auth/claims")
        assert response.status_code == 401

    def test_expired_token_returns_401(self, signer, auth_client):
        token = signer.sign(subject="test@example.com", audience="test-service", expiry=-1)
        response = auth_client.get("/auth/claims", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
