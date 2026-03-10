"""ServiceRealm — JWT verification using cached public keys."""

from __future__ import annotations

from typing import Protocol

import jwt


class KeyCacheLike(Protocol):
    """Minimal interface that ServiceRealm expects from a key cache."""

    def get_key(self, kid: str) -> str | None: ...
    def get_all_keys(self) -> dict[str, str]: ...


class ServiceRealm:
    """Verifies RS256 JWTs against public keys from a KeyCache.

    Supports two modes:
    - kid present: look up the specific key
    - kid absent: try all cached keys (fallback for Google tokens that omit kid)
    """

    def __init__(self, key_cache: KeyCacheLike) -> None:
        self.key_cache = key_cache

    def verify(self, token: str) -> dict:
        """Decode and verify a JWT, returning its claims.

        Raises ValueError on any verification failure.
        """
        if not token or token.count(".") != 2:
            raise ValueError("Token must have three dot-separated parts")

        header = jwt.get_unverified_header(token)
        kid = header.get("kid")

        if kid:
            return self._verify_with_kid(token, kid)
        return self._verify_without_kid(token)

    def _verify_with_kid(self, token: str, kid: str) -> dict:
        key = self.key_cache.get_key(kid)
        if key is None:
            raise ValueError(f"Unknown key {kid}")

        try:
            return jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
        except jwt.ExpiredSignatureError as e:
            raise ValueError(f"Token expired: {e}") from e
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {e}") from e

    def _verify_without_kid(self, token: str) -> dict:
        all_keys = self.key_cache.get_all_keys()
        if not all_keys:
            raise ValueError("No cached keys available for verification")

        last_error: Exception | None = None
        for _kid, key in all_keys.items():
            try:
                return jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
            except jwt.ExpiredSignatureError as e:
                raise ValueError(f"Token expired: {e}") from e
            except (jwt.InvalidTokenError, jwt.exceptions.InvalidKeyError) as e:
                last_error = e
                continue

        raise ValueError(f"No cached key could verify the token: {last_error}")
