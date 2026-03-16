"""ServiceRealm — JWT verification using cached public keys."""

from __future__ import annotations

from typing import Protocol

import jwt


class KeyCacheLike(Protocol):
    """Minimal interface that ServiceRealm expects from a key cache."""

    def get_key(self, kid: str) -> str | None: ...
    def get_all_keys(self) -> dict[str, str]: ...


class ServiceRealm:
    """Verifies RS256 JWTs against public keys from one or more KeyCaches.

    Supports two modes:
    - kid present: look up the specific key across all caches (in order)
    - kid absent: try all cached keys from all caches (fallback for Google tokens that omit kid)

    When multiple caches are provided, they are checked in construction order.
    Place faster/local caches first (e.g. ephemeral) and slower/remote caches
    second (e.g. GCP SA).
    """

    def __init__(self, key_cache: KeyCacheLike | list[KeyCacheLike]) -> None:
        if isinstance(key_cache, list):
            self._caches = key_cache
        else:
            self._caches = [key_cache]

    def get_key(self, kid: str) -> str | None:
        """Look up a public key by kid across all caches (in order)."""
        for cache in self._caches:
            key = cache.get_key(kid)
            if key is not None:
                return key
        return None

    def verify(self, token: str) -> dict:
        """Decode and verify a JWT, returning its claims.

        Raises ValueError on any verification failure.
        """
        if not token or token.count(".") != 2:
            raise ValueError("Token must have three dot-separated parts")

        try:
            header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError as exc:
            raise ValueError(f"Invalid token header: {exc}") from exc
        kid = header.get("kid")

        if kid:
            return self._verify_with_kid(token, kid)
        return self._verify_without_kid(token)

    def _verify_with_kid(self, token: str, kid: str) -> dict:
        for cache in self._caches:
            key = cache.get_key(kid)
            if key is not None:
                try:
                    return jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
                except jwt.ExpiredSignatureError as e:
                    raise ValueError(f"Token expired: {e}") from e
                except jwt.InvalidTokenError as e:
                    raise ValueError(f"Invalid token: {e}") from e

        raise ValueError(f"Unknown key {kid}")

    def _verify_without_kid(self, token: str) -> dict:
        last_error: Exception | None = None
        any_keys = False

        for cache in self._caches:
            all_keys = cache.get_all_keys()
            any_keys = any_keys or bool(all_keys)
            for _kid, key in all_keys.items():
                try:
                    return jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
                except jwt.ExpiredSignatureError as e:
                    raise ValueError(f"Token expired: {e}") from e
                except (jwt.InvalidTokenError, jwt.exceptions.InvalidKeyError) as e:
                    last_error = e
                    continue

        if not any_keys:
            raise ValueError("No cached keys available for verification")
        raise ValueError(f"No cached key could verify the token: {last_error}")
