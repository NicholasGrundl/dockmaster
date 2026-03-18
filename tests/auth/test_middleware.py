"""Tests for allow_jwt auth dependency (via /auth/claims endpoint)."""


class TestAllowJwt:
    def test_valid_token_returns_claims(self, auth_client, valid_token):
        response = auth_client.get("/auth/claims", headers={"Authorization": f"Bearer {valid_token}"})
        assert response.status_code == 200
        claims = response.json()
        assert claims["sub"] == "test@example.com"
        assert claims["email"] == "test@example.com"

    def test_missing_bearer_returns_401(self, auth_client):
        response = auth_client.get("/auth/claims")
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, auth_client):
        response = auth_client.get("/auth/claims", headers={"Authorization": "Bearer not.a.token"})
        assert response.status_code == 401

    def test_malformed_bearer_returns_401(self, auth_client):
        response = auth_client.get("/auth/claims", headers={"Authorization": "Bearer"})
        assert response.status_code == 401

    def test_realm_not_configured_returns_503(self, app, client):
        """When app.state.realm is None, auth returns 503."""
        app.state.realm = None
        response = client.get("/auth/claims", headers={"Authorization": "Bearer some.fake.token"})
        assert response.status_code == 503
