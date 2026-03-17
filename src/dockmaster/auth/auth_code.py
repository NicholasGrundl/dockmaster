"""In-memory authorization code store for OAuth auth code flow.

Codes are single-use, cryptographically random, and expire after a configurable TTL.
"""

from __future__ import annotations

import secrets
import time

from pydantic import BaseModel, Field


class AuthCodeEntry(BaseModel):
    """A pending authorization code."""

    subject: str
    redirect_uri: str
    created_at: float = Field(default_factory=time.time)


class AuthCodeStore:
    """In-memory store for single-use authorization codes."""

    def __init__(self, ttl: int = 300) -> None:
        self._codes: dict[str, AuthCodeEntry] = {}
        self._ttl = ttl

    def create(self, subject: str, redirect_uri: str) -> str:
        """Generate a new auth code and store it. Returns the code string."""
        self._prune_expired()
        code = secrets.token_urlsafe(32)
        self._codes[code] = AuthCodeEntry(subject=subject, redirect_uri=redirect_uri)
        return code

    def consume(self, code: str, redirect_uri: str) -> AuthCodeEntry | None:
        """Consume a code if valid. Returns the entry or None.

        A code is invalid if it doesn't exist, is expired, or the redirect_uri
        doesn't match. Consumed codes are deleted (single-use).
        """
        entry = self._codes.pop(code, None)
        if entry is None:
            return None
        if time.time() - entry.created_at > self._ttl:
            return None
        if entry.redirect_uri != redirect_uri:
            # Put it back? No — single-use. A failed attempt consumes the code.
            return None
        return entry

    def _prune_expired(self) -> None:
        """Remove expired codes."""
        now = time.time()
        expired = [k for k, v in self._codes.items() if now - v.created_at > self._ttl]
        for k in expired:
            del self._codes[k]
