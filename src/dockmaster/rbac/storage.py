"""Secret Manager storage backend for RBAC data and client secrets."""


import json

import structlog
from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud.secretmanager_v1 import SecretManagerServiceClient

from dockmaster.rbac.models import Role, ServiceGrants

logger = structlog.get_logger(__name__)


class SecretsStorage:
    """Read-only GCP Secret Manager backend for RBAC data and client secrets.

    Used by the runtime service account with ``secretAccessor`` permissions.
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

    def _secret_name(self, secret_id: str) -> str:
        """Return the resource name for a secret (no version)."""
        return f"projects/{self._project}/secrets/{secret_id}"

    def _parent(self) -> str:
        return f"projects/{self._project}"

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
    # RBAC: Roles (read-only)
    # ------------------------------------------------------------------

    def list_roles(self) -> list[str]:
        """List all role names from Secret Manager."""
        secrets = self._client.list_secrets(request={"parent": self._parent(), "filter": "name:role-"})
        prefix = "role-"
        return [s.name.split("/")[-1][len(prefix) :] for s in secrets]

    def get_role(self, name: str) -> Role:
        """Load a role from Secret Manager. Secret ID: ``role-{name}``."""
        data = self._load_secret(f"role-{name}")
        return Role.model_validate(data)

    # ------------------------------------------------------------------
    # RBAC: ServiceGrants (read-only)
    # ------------------------------------------------------------------

    def list_service_grants(self) -> list[str]:
        """List all service names that have grants in Secret Manager."""
        secrets = self._client.list_secrets(request={"parent": self._parent(), "filter": "name:service-grants-"})
        prefix = "service-grants-"
        return [s.name.split("/")[-1][len(prefix) :] for s in secrets]

    def get_service_grants(self, service: str) -> ServiceGrants:
        """Load service grants. Secret ID: ``service-grants-{service}``."""
        data = self._load_secret(f"service-grants-{service}")
        return ServiceGrants.model_validate(data)

    # ------------------------------------------------------------------
    # Client secret lookup
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


class AdminSecretsStorage(SecretsStorage):
    """Read + write GCP Secret Manager backend for admin RBAC operations.

    Used by the admin service account with ``secretmanager.admin`` permissions.
    Inherits all read methods from SecretsStorage and adds write operations.
    """

    # ------------------------------------------------------------------
    # Internal write helpers
    # ------------------------------------------------------------------

    def _save_secret(self, secret_id: str, data: dict) -> None:
        """Create secret (if needed) and add a new version with JSON payload."""
        # Idempotent create
        try:
            self._client.create_secret(
                request={
                    "parent": self._parent(),
                    "secret_id": secret_id,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
        except AlreadyExists:
            pass

        payload = json.dumps(data).encode("utf-8")
        self._client.add_secret_version(
            request={
                "parent": self._secret_name(secret_id),
                "payload": {"data": payload},
            }
        )

    def _delete_secret(self, secret_id: str) -> None:
        """Delete a secret entirely. Raises NotFound if it doesn't exist."""
        self._client.delete_secret(request={"name": self._secret_name(secret_id)})

    # ------------------------------------------------------------------
    # RBAC: Roles (write)
    # ------------------------------------------------------------------

    def put_role(self, name: str, role: Role) -> None:
        """Save a role to Secret Manager. Secret ID: ``role-{name}``."""
        self._save_secret(f"role-{name}", role.model_dump())

    def delete_role(self, name: str) -> None:
        """Delete a role from Secret Manager. Secret ID: ``role-{name}``."""
        self._delete_secret(f"role-{name}")

    # ------------------------------------------------------------------
    # RBAC: ServiceGrants (write)
    # ------------------------------------------------------------------

    def put_service_grants(self, service: str, grants: ServiceGrants) -> None:
        """Save service grants. Secret ID: ``service-grants-{service}``."""
        self._save_secret(f"service-grants-{service}", grants.model_dump())

    def delete_service_grants(self, service: str) -> None:
        """Delete service grants. Secret ID: ``service-grants-{service}``."""
        self._delete_secret(f"service-grants-{service}")
