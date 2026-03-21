"""Generic in-memory TTL store for single-use, short-lived entries.

Provides a base class for storing key→value pairs that expire after a
configurable TTL and are consumed (deleted) on retrieval. Keys are
cryptographically random tokens generated via `secrets.token_urlsafe`.

Used by:
    - AuthCodeStore: OAuth authorization codes (subject + redirect_uri)
    - OAuth state store: CSRF state tokens (redirect_uri metadata)
"""

import secrets
import time
from typing import Generic, TypeVar

V = TypeVar("V")


class TTLStore(Generic[V]):
    """In-memory store for single-use entries with TTL-based expiry.

    Entries are pruned lazily — expired entries are cleaned up whenever a new
    entry is created. This keeps memory bounded without requiring a background
    timer.

    Args:
        ttl: Time-to-live in seconds for each entry. Defaults to 300 (5 min).
    """

    def __init__(self, ttl: int = 300) -> None:
        self._entries: dict[str, tuple[float, V]] = {}
        self._ttl = ttl

    def create(self, value: V) -> str:
        """Store a value and return a cryptographically random key."""
        self._prune_expired()
        key = secrets.token_urlsafe(32)
        self._entries[key] = (time.time(), value)
        return key

    def consume(self, key: str) -> V | None:
        """Pop an entry by key if it exists and hasn't expired.

        Returns the value, or None if the key doesn't exist or is expired.
        Consumed entries are deleted (single-use).
        """
        entry = self._entries.pop(key, None)
        if entry is None:
            return None
        created_at, value = entry
        if time.time() - created_at > self._ttl:
            return None
        return value

    def _prune_expired(self) -> None:
        """Remove all expired entries."""
        now = time.time()
        expired = [k for k, (created_at, _) in self._entries.items() if now - created_at > self._ttl]
        for k in expired:
            del self._entries[k]

    def __len__(self) -> int:
        return len(self._entries)
