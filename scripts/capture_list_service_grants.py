"""Capture list_secrets response for service-grants- prefixed secrets.

Prints fixture JSON to stdout.

Usage:
    uv run python scripts/capture_list_service_grants.py
    uv run python scripts/capture_list_service_grants.py > tests/fixtures/gcp/secret_manager/list_service_grants.json
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
        request={"parent": parent, "filter": "name:service-grants-"}
    ))

    fixture = {
        "request": {
            "method": "gRPC",
            "service": "google.cloud.secretmanager.v1.SecretManagerService",
            "rpc": "ListSecrets",
            "parent": parent,
            "filter": "name:service-grants-",
        },
        "response": {
            "status": "OK",
            "secrets": [{"name": s.name} for s in secrets],
            "notes": "Each secret .name is the full resource path. Code strips 'service-grants-' prefix to get service name.",
        },
    }

    print(json.dumps(fixture, indent=2))


if __name__ == "__main__":
    main()
