"""JWT signers — ServiceAccountSigner and EphemeralKeypairSigner.

Two signer classes that produce RS256 JWTs with different key sources:

- ServiceAccountSigner: signs with a GCP service account private key (persistent, external)
- EphemeralKeypairSigner: signs with a self-generated RSA keypair (ephemeral, in-memory)
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat


class ServiceAccountSigner:
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

    def sign(
        self,
        subject: str | None,
        audience: str,
        expiry: int = 3600,
        payload: dict | None = None,
    ) -> str:
        """Sign and return a JWT string.

        Args:
            subject: The `sub` and `email` claim. Falls back to client_email if None.
            audience: The `aud` claim (target service).
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
            "aud": audience,
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
        audience: str = "",
        expiry: int = 3600,
        payload: dict | None = None,
    ) -> str:
        """Return a ``Bearer <token>`` string for use in Authorization headers."""
        token = self.sign(subject=subject, audience=audience, expiry=expiry, payload=payload)
        return f"Bearer {token}"


class EphemeralKeypairSigner:
    """Signs identity JWTs using an ephemeral RSA keypair generated at construction.

    The private key lives only in memory — never written to disk.
    Exposes the current kid and public JWK for use by EphemeralKeyCache and JWKS endpoints.
    """

    def __init__(self, ttl: int = 900) -> None:
        self.default_ttl = ttl

        # Generate ephemeral RSA keypair
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Assign unique kid: dk-{date}-{uuid[:8]}
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.current_kid = f"dk-{date_str}-{uuid.uuid4().hex[:8]}"

    @property
    def current_public_jwk(self) -> dict:
        """Return the current public key as a JWK dict (RFC 7517)."""
        pub_numbers = self._private_key.public_key().public_numbers()

        def _int_to_base64url(n: int) -> str:
            length = (n.bit_length() + 7) // 8
            return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

        return {
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "kid": self.current_kid,
            "n": _int_to_base64url(pub_numbers.n),
            "e": _int_to_base64url(pub_numbers.e),
        }

    def sign(
        self,
        subject: str,
        audience: str,
        ttl: int | None = None,
        extra_claims: dict | None = None,
    ) -> str:
        """Sign and return a Type C JWT string.

        Args:
            subject: The email / identity for sub and email claims.
            audience: The target service for the aud claim.
            ttl: Token lifetime in seconds. Defaults to self.default_ttl.
            extra_claims: Additional claims to include. Cannot override core claims.
        """
        now = int(time.time())
        effective_ttl = ttl if ttl is not None else self.default_ttl

        # Build claims — extra_claims go first so core claims override them
        claims = {**(extra_claims or {})}
        claims.update(
            {
                "sub": subject,
                "email": subject,
                "iss": "dockmaster",
                "aud": audience,
                "iat": now,
                "exp": now + effective_ttl,
            }
        )

        pem = self._private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        )

        return jwt.encode(
            claims,
            pem,
            algorithm="RS256",
            headers={"kid": self.current_kid},
        )
