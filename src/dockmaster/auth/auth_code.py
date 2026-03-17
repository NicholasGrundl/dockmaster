"""In-memory authorization code store for OAuth auth code flow.

Codes are single-use, cryptographically random, and expire after a configurable TTL.
Built on TTLStore for key generation, TTL, and pruning.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from dockmaster.auth.ttl_store import TTLStore


class AuthCodeEntry(BaseModel):
    """A pending authorization code."""

    subject: str
    redirect_uri: str
    created_at: float = Field(default_factory=time.time)


class AuthCodeStore:
    """In-memory store for single-use authorization codes.

    Wraps TTLStore with domain-specific create/consume signatures that
    enforce redirect_uri matching on consumption.
    """

    def __init__(self, ttl: int = 300) -> None:
        self._store = TTLStore[AuthCodeEntry](ttl=ttl)

    def create(self, subject: str, redirect_uri: str) -> str:
        """Generate a new auth code and store it. Returns the code string."""
        entry = AuthCodeEntry(subject=subject, redirect_uri=redirect_uri)
        return self._store.create(entry)

    def consume(self, code: str, redirect_uri: str) -> AuthCodeEntry | None:
        """Consume a code if valid. Returns the entry or None.

        A code is invalid if it doesn't exist, is expired, or the redirect_uri
        doesn't match. Consumed codes are deleted (single-use).
        """
        entry = self._store.consume(code)
        if entry is None:
            return None
        if entry.redirect_uri != redirect_uri:
            # Mismatched URI — code is still consumed (single-use).
            return None
        return entry

    @property
    def _codes(self) -> dict:
        """Expose internal entries for test assertions."""
        return self._store._entries
