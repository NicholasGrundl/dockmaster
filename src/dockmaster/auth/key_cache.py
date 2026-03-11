"""KeyCache — TTL-based public key cache with pluggable update()."""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from google.oauth2 import service_account
from googleapiclient.discovery import build

_log = logging.getLogger(__name__)


def _cert_to_public_key_pem(pem: str) -> str:
    """Extract the public key PEM from an X.509 certificate PEM.

    If the input is already a public key (BEGIN PUBLIC KEY), return as-is.
    """
    if "BEGIN CERTIFICATE" in pem:
        cert = x509.load_pem_x509_certificate(pem.encode())
        return cert.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
    return pem


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


class ServiceAccountKeyCache(KeyCache):
    """KeyCache backed by GCP IAM (all SA keys) + Google OIDC certs.

    On each ``update()`` call, fetches:
    - Google's public OIDC signing certs (for verifying Google id_tokens)
    - X.509 PEM for every user-managed key across all service accounts in
      the project (for verifying service-to-service JWTs)

    Each source failure is non-fatal — a warning is logged and the other
    source is still loaded.

    Credentials: pass SA key data (dict) for explicit auth, or None to
    fall back to Application Default Credentials (ADC).
    """

    def __init__(
        self,
        credentials: str | dict | None = None,
        project: str | None = None,
        expiry: int = 300,
    ) -> None:
        super().__init__(expiry=expiry)
        if isinstance(credentials, str):
            cred_data: dict | None = json.loads(Path(credentials).read_text())
        elif isinstance(credentials, dict):
            cred_data = dict(credentials)
        else:
            cred_data = None
        self._cred_data = cred_data
        self._project = project or (cred_data.get("project_id", "") if cred_data else "")

    def update(self) -> None:
        new_keys: dict[str, str] = {}

        # --- Google OIDC certs ---
        try:
            resp = httpx.get("https://www.googleapis.com/oauth2/v1/certs", timeout=30)
            resp.raise_for_status()
            for kid, cert_pem in resp.json().items():
                new_keys[kid] = _cert_to_public_key_pem(cert_pem)
        except Exception:
            _log.warning("Failed to fetch Google OIDC certs", exc_info=True)

        # --- GCP IAM service account keys ---
        try:
            if self._cred_data:
                creds = service_account.Credentials.from_service_account_info(
                    self._cred_data,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            else:
                import google.auth

                creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            iam = build("iam", "v1", credentials=creds)
            request = iam.projects().serviceAccounts().list(name=f"projects/{self._project}", pageSize=50)
            while request is not None:
                result = request.execute()
                for account in result.get("accounts", []):
                    sa_email = account["email"]
                    sa_name = f"projects/{self._project}/serviceAccounts/{sa_email}"
                    try:
                        keys_result = (
                            iam.projects()
                            .serviceAccounts()
                            .keys()
                            .list(name=sa_name, keyTypes=["USER_MANAGED"])
                            .execute()
                        )
                        for key in keys_result.get("keys", []):
                            key_name = key["name"]
                            kid = key_name.split("/")[-1]
                            key_data = (
                                iam.projects()
                                .serviceAccounts()
                                .keys()
                                .get(
                                    name=key_name,
                                    publicKeyType="TYPE_X509_PEM_FILE",
                                )
                                .execute()
                            )
                            raw_pem = base64.b64decode(key_data["publicKeyData"]).decode()
                            new_keys[kid] = _cert_to_public_key_pem(raw_pem)
                    except Exception:
                        _log.warning("Failed to fetch keys for SA %s", sa_email, exc_info=True)
                request = iam.projects().serviceAccounts().list_next(request, result)
        except Exception:
            _log.warning("Failed to enumerate SA keys from IAM", exc_info=True)

        self._keys = new_keys
        self._updated_at = time.time()
