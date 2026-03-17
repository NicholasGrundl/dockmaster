"""Tests for GET /auth/key/{kid}."""


class TestGetPublicKey:
    def test_known_kid_returns_pem(self, auth_client, fake_sa_key_data):
        kid = fake_sa_key_data["private_key_id"]
        response = auth_client.get(f"/auth/key/{kid}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-pem-file")
        assert "BEGIN" in response.text

    def test_unknown_kid_returns_404(self, auth_client):
        response = auth_client.get("/auth/key/nonexistent-kid")
        assert response.status_code == 404
        assert "nonexistent-kid" in response.json()["error"]

    def test_no_auth_required(self, auth_client):
        """Key endpoint is public — no Authorization header needed."""
        kid = "any-kid"
        response = auth_client.get(f"/auth/key/{kid}")
        # 404 (not found) is fine — what matters is it's not 401/403
        assert response.status_code in (200, 404)
        assert response.status_code != 401
        assert response.status_code != 403

    def test_realm_not_configured_returns_503(self, app, client):
        app.state.realm = None
        response = client.get("/auth/key/some-kid")
        assert response.status_code == 503
