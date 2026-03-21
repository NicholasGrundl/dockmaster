"""KeyCache — TTL-based public key cache with pluggable update().

Includes:
- KeyCache: base class with TTL expiry
- ServiceAccountKeyCache: GCP IAM + Google OIDC public keys
- EphemeralKeyCache: local ephemeral public key registry with file persistence
"""

import base64
import json
import time
from pathlib import Path

import httpx
import structlog
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = structlog.get_logger(__name__)


def _cert_to_public_key_pem(pem: str) -> str:
    """Extract the public key PEM from an X.509 certificate PEM.

    If the input is already a public key (BEGIN PUBLIC KEY), return as-is.
    """
    if "BEGIN CERTIFICATE" in pem:
        cert = x509.load_pem_x509_certificate(pem.encode())
        return (
            cert.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
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
            logger.warning("failed_to_fetch_google_oidc_certs", exc_info=True)

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
                        logger.warning("failed_to_fetch_sa_keys", sa_email=sa_email, exc_info=True)
                request = iam.projects().serviceAccounts().list_next(request, result)
        except Exception:
            logger.warning("failed_to_enumerate_sa_keys", exc_info=True)

        self._keys = new_keys
        self._updated_at = time.time()


class EphemeralKeyCache(KeyCache):
    """Public key registry for ephemeral RSA keypairs with file persistence.

    Receives the current public key from JWTTokenIssuer at construction.
    Loads/saves a registry file so public keys from previous process instances
    remain available for verifying in-flight tokens after a restart.

    No private key material ever touches this class.
    """

    DEFAULT_RETENTION = 43200  # 12 hours
    SAFETY_FACTOR = 1.01  # 1% padding for clock drift

    def __init__(
        self,
        kid: str,
        public_jwk: dict,
        registry_path: str,
        retention: int = DEFAULT_RETENTION,
    ) -> None:
        # Skip TTL-based expiry from base class — keys are static for process lifetime
        super().__init__(expiry=999_999_999)

        self._current_kid = kid
        self._retention = retention
        self._retention_padded = retention * self.SAFETY_FACTOR
        self._registry_path = Path(registry_path)

        # Load existing registry, add current key, prune stale, save, populate _keys
        entries = self._load_registry()
        entries = self._add_current_key(entries, kid, public_jwk)
        entries = self._prune_stale(entries)
        self._save_registry(entries)
        self._populate_keys(entries)

    def update(self) -> None:
        """No-op — keys are static for the process lifetime."""

    def _load_registry(self) -> list[dict]:
        """Load key entries from registry file. Returns empty list on any failure."""
        try:
            data = json.loads(self._registry_path.read_text())
            return data.get("keys", [])
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _add_current_key(self, entries: list[dict], kid: str, public_jwk: dict) -> list[dict]:
        """Add or update the current key entry."""
        # Remove any existing entry with the same kid (handles re-registration)
        entries = [e for e in entries if e["kid"] != kid]
        entries.append(
            {
                "kid": kid,
                "public_jwk": public_jwk,
                "created_at": time.time(),
            }
        )
        return entries

    def _prune_stale(self, entries: list[dict]) -> list[dict]:
        """Remove entries older than retention, except the current key."""
        now = time.time()
        return [
            e for e in entries if e["kid"] == self._current_kid or (now - e["created_at"]) <= self._retention_padded
        ]

    def _save_registry(self, entries: list[dict]) -> None:
        """Persist the registry to disk."""
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._registry_path.write_text(json.dumps({"keys": entries}, indent=2))

    def _populate_keys(self, entries: list[dict]) -> None:
        """Build the in-memory _keys dict from registry entries.

        Converts JWK dicts to PEM strings for compatibility with ServiceRealm's
        jwt.decode() which expects PEM keys.
        """
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        for entry in entries:
            jwk = entry["public_jwk"]
            try:
                n = int.from_bytes(base64.urlsafe_b64decode(jwk["n"] + "=="), "big")
                e = int.from_bytes(base64.urlsafe_b64decode(jwk["e"] + "=="), "big")
                pub_key = RSAPublicNumbers(e, n).public_key()
                pem = pub_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
                self._keys[entry["kid"]] = pem
            except Exception:
                logger.warning("failed_to_load_ephemeral_key", kid=entry["kid"])

        self._updated_at = time.time()
