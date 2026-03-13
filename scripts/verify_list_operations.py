"""Verify list + get operations work end-to-end against real Secret Manager.

Prints results to stdout (not JSON — human-readable verification output).

Usage:
    uv run python scripts/verify_list_operations.py
"""

import os
from pathlib import Path


def load_env() -> dict[str, str]:
    env = {}
    for line in Path(".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def main() -> None:
    env = load_env()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = env["ADMIN_SA_KEY_FILE"]
    project = env["SECRETS_PROJECT"]

    from google.cloud.secretmanager_v1 import SecretManagerServiceClient

    from dockmaster.rbac.storage import SecretsStorage

    client = SecretManagerServiceClient()
    storage = SecretsStorage(client=client, project=project)

    roles = storage.list_roles()
    print(f"Roles ({len(roles)}): {roles}")
    for r in roles:
        role = storage.get_role(r)
        print(f"  role/{r}: {role.permissions}")

    services = storage.list_service_grants()
    print(f"Services ({len(services)}): {services}")
    for s in services:
        sg = storage.get_service_grants(s)
        print(f"  service/{s}: {len(sg.grants)} grants")

    print("\nAll list + get operations verified.")


if __name__ == "__main__":
    main()
