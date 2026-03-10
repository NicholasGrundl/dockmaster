"""ServiceUser — JWT signing for service-to-service auth."""

from __future__ import annotations

import json
import time
from pathlib import Path

import jwt


class ServiceUser:
    """Signs JWTs using a GCP service account private key.

    Initialized once at app startup (lifespan singleton). The key file is
    parsed on construction, not per-request.
    """

    def __init__(self, credentials: str | dict) -> None:
        if isinstance(credentials, str):
            data = json.loads(Path(credentials).read_text())
        else:
            data = credentials

        self._private_key: str = data["private_key"]
        self.private_key_id: str = data["private_key_id"]
        self.client_email: str = data["client_email"]

    def get_token(
        self,
        subject: str | None,
        service_name: str,
        expiry: int = 3600,
        payload: dict | None = None,
    ) -> str:
        """Sign and return a JWT string.

        Args:
            subject: The `sub` and `email` claim. Falls back to client_email if None.
            service_name: The `aud` claim (target service).
            expiry: Token lifetime in seconds (default 3600).
            payload: Extra claims to merge into the token.
        """
        payload = payload or {}
        now = int(time.time())
        effective_subject = subject or self.client_email

        claims = {
            "iss": self.client_email,
            "sub": effective_subject,
            "email": effective_subject,
            "aud": service_name,
            "iat": now,
            "exp": now + expiry,
            **payload,
        }

        return jwt.encode(
            claims,
            self._private_key,
            algorithm="RS256",
            headers={"kid": self.private_key_id},
        )

    def get_authorization(
        self,
        subject: str | None = None,
        service_name: str = "",
        expiry: int = 3600,
        payload: dict | None = None,
    ) -> str:
        """Return a ``Bearer <token>`` string for use in Authorization headers."""
        token = self.get_token(subject=subject, service_name=service_name, expiry=expiry, payload=payload)
        return f"Bearer {token}"
