"""Secret Manager storage backend for RBAC data and client secrets."""

from __future__ import annotations

import json

import structlog
from google.api_core.exceptions import NotFound
from google.cloud.secretmanager_v1 import SecretManagerServiceClient

logger = structlog.get_logger("dockmaster.rbac.storage")


class SecretsStorage:
    """GCP Secret Manager backend.

    Phase 4b: ``get_client_secret`` for OAuth refresh flow.
    Phase 5 will add ``get_role``, ``put_role``, ``get_service_grants``, etc.
    """

    def __init__(self, client: SecretManagerServiceClient, project: str) -> None:
        self._client = client
        self._project = project

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _secret_path(self, secret_id: str) -> str:
        """Return the resource name for the latest version of a secret."""
        return f"projects/{self._project}/secrets/{secret_id}/versions/latest"

    def _load_secret(self, secret_id: str) -> dict:
        """Access the latest version of a secret and parse as JSON."""
        name = self._secret_path(secret_id)
        response = self._client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("utf-8")
        return json.loads(payload)

    def _load_secret_raw(self, secret_id: str) -> str:
        """Access the latest version of a secret and return raw string."""
        name = self._secret_path(secret_id)
        response = self._client.access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8")

    # ------------------------------------------------------------------
    # Phase 4b: client secret lookup
    # ------------------------------------------------------------------

    def get_client_secret(self, client_id: str) -> str:
        """Load an OAuth client secret from Secret Manager.

        Secret naming convention: ``client_id-{part_before_first_dot}``
        Example: client_id ``109370504310.apps.googleusercontent.com``
                 → secret ``client_id-109370504310``

        Returns the raw secret string (the client secret value).

        Raises ``NotFound`` if the secret does not exist.
        """
        name = client_id.partition(".")[0]
        secret_id = f"client_id-{name}"
        logger.debug("loading_client_secret", secret_id=secret_id)
        try:
            return self._load_secret_raw(secret_id)
        except NotFound:
            logger.warning("client_secret_not_found", secret_id=secret_id)
            raise
