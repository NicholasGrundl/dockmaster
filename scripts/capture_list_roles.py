"""Capture list_secrets response for role- prefixed secrets.

Prints fixture JSON to stdout.

Usage:
    uv run python scripts/capture_list_roles.py
    uv run python scripts/capture_list_roles.py > tests/fixtures/gcp/secret_manager/list_roles.json
"""

import json
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

    client = SecretManagerServiceClient()
    parent = f"projects/{project}"
    secrets = list(client.list_secrets(
        request={"parent": parent, "filter": "name:role-"}
    ))

    fixture = {
        "request": {
            "method": "gRPC",
            "service": "google.cloud.secretmanager.v1.SecretManagerService",
            "rpc": "ListSecrets",
            "parent": parent,
            "filter": "name:role-",
        },
        "response": {
            "status": "OK",
            "secrets": [{"name": s.name} for s in secrets],
            "notes": "Each secret .name is the full resource path. Code strips 'role-' prefix to get role name.",
        },
    }

    print(json.dumps(fixture, indent=2))


if __name__ == "__main__":
    main()
