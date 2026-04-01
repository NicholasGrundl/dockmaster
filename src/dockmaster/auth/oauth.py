"""Authlib OAuth2 client for Google login."""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from dockmaster.config import Settings

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


def create_oauth(settings: Settings) -> OAuth:
    """Create and configure an Authlib OAuth instance for Google."""
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.client_id,
        client_secret=settings.client_secret.get_secret_value() if settings.client_secret else None,
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",
        },
    )
    return oauth
