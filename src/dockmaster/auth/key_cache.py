"""KeyCache — TTL-based public key cache with pluggable update()."""

from __future__ import annotations

import time


class KeyCache:
    """Base class for public key caches with TTL-based expiry.

    Subclasses override ``update()`` to populate ``_keys`` from a real source
    (e.g., GCP IAM, Google OIDC certs).
    """

    def __init__(self, expiry: int = 300) -> None:
        self._keys: dict[str, str] = {}
        self._updated_at: float = 0
        self._expiry = expiry

    def get_key(self, kid: str) -> str | None:
        """Return the PEM for *kid*, refreshing if the cache is stale."""
        if self._is_expired():
            self.update()
        return self._keys.get(kid)

    def get_all_keys(self) -> dict[str, str]:
        """Return a copy of all cached ``{kid: pem}`` pairs."""
        if self._is_expired():
            self.update()
        return dict(self._keys)

    def update(self) -> None:
        """Refresh the key cache. Override in subclasses."""

    def _is_expired(self) -> bool:
        return time.time() - self._updated_at >= self._expiry
