"""Tests for UI routes — /ui/login, /ui/ (dashboard)."""

import time

import pytest
from fastapi import FastAPI
from itsdangerous import URLSafeSerializer
from starlette.testclient import TestClient

from dockmaster.sessions.memory import InMemorySessionStore


@pytest.fixture
def session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def ui_client(app: FastAPI, session_store: InMemorySessionStore) -> TestClient:
    """TestClient with a session store wired in."""
    with TestClient(app) as c:
        # Override after lifespan creates the default store
        app.state.session_store = session_store
        yield c


def _seed_session(store: InMemorySessionStore, session_id: str, data: dict, ttl: int = 3600):
    """Seed a session directly into the store's internal dict."""
    store._store[session_id] = (data, time.time() + ttl)


def _create_signed_cookie(secret_key: str, session_id: str) -> str:
    """Create a signed session cookie value."""
    signer = URLSafeSerializer(secret_key)
    return signer.dumps(session_id)


class TestLoginPage:
    """GET /ui/login — public login page."""

    def test_login_page_renders(self, ui_client):
        response = ui_client.get("/ui/login")
        assert response.status_code == 200
        assert "Sign in with Google" in response.text

    def test_login_page_has_no_nav_header(self, ui_client):
        response = ui_client.get("/ui/login")
        assert "Dashboard" not in response.text

    def test_login_page_shows_brand_name(self, ui_client):
        response = ui_client.get("/ui/login")
        assert "Dockmaster" in response.text

    def test_login_page_links_to_auth_login(self, ui_client):
        response = ui_client.get("/ui/login")
        assert 'href="/auth/login"' in response.text


class TestAuthGuard:
    """GET /ui/ — requires active session."""

    def test_unauthenticated_redirects_to_login(self, ui_client):
        response = ui_client.get("/ui/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/ui/login"

    def test_invalid_cookie_redirects_to_login(self, ui_client):
        ui_client.cookies.set("session_id", "garbage-value")
        response = ui_client.get("/ui/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/ui/login"

    def test_expired_session_redirects_to_login(self, ui_client, session_store):
        session_store._store["expired-sid"] = ({"email": "a@example.com"}, time.time() - 1)
        cookie = _create_signed_cookie("test-secret-key", "expired-sid")
        ui_client.cookies.set("session_id", cookie)
        response = ui_client.get("/ui/", follow_redirects=False)
        assert response.status_code == 307


class TestDashboard:
    """GET /ui/ — authenticated dashboard."""

    @pytest.fixture
    def authed_client(self, ui_client, session_store) -> TestClient:
        """Client with a valid session cookie."""
        _seed_session(session_store, "test-sid", {"email": "user@example.com", "name": "Test User"})
        cookie = _create_signed_cookie("test-secret-key", "test-sid")
        ui_client.cookies.set("session_id", cookie)
        return ui_client

    def test_dashboard_renders(self, authed_client):
        response = authed_client.get("/ui/")
        assert response.status_code == 200
        assert "Dashboard" in response.text

    def test_dashboard_shows_user_email(self, authed_client):
        response = authed_client.get("/ui/")
        assert "user@example.com" in response.text

    def test_dashboard_shows_session_table(self, authed_client):
        response = authed_client.get("/ui/")
        assert "Your Sessions" in response.text

    def test_dashboard_shows_service_status(self, authed_client):
        response = authed_client.get("/ui/")
        assert "Service Status" in response.text

    def test_dashboard_shows_sign_out(self, authed_client):
        response = authed_client.get("/ui/")
        assert "Sign out" in response.text

    def test_login_page_redirects_to_dashboard_when_authed(self, authed_client):
        response = authed_client.get("/ui/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/ui/"
