"""Capture and redact GCP API responses as test fixture files.

Usage:
    # Capture all Phase 2 fixtures
    uv run python scripts/capture_gcp_fixtures.py --phase 2

    # Capture a single call
    uv run python scripts/capture_gcp_fixtures.py --call google-oidc-certs

    # Dry run (list what would be captured)
    uv run python scripts/capture_gcp_fixtures.py --phase 2 --dry-run

    # Redact an existing raw JSON file
    uv run python scripts/capture_gcp_fixtures.py --redact /tmp/raw.json --output fixtures/out.json

Prerequisites:
    export GOOGLE_APPLICATION_CREDENTIALS="/path/to/sa-key.json"
    export GCP_PROJECT="your-project-id"  (or read from SA key file)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "gcp"

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

# Patterns that indicate sensitive values
_TOKEN_PREFIXES = ("ya29.", "eyJhb", "1//", "GOCSPX-")
_PEM_PRIVATE_RE = re.compile(
    r"-----BEGIN (RSA )?PRIVATE KEY-----[\s\S]*?-----END (RSA )?PRIVATE KEY-----"
)
_SA_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.iam\.gserviceaccount\.com"
)
_CLIENT_ID_RE = re.compile(r"\d+[a-zA-Z0-9-]*\.apps\.googleusercontent\.com")
_CLIENT_SECRET_RE = re.compile(r"GOCSPX-[A-Za-z0-9_-]+")


def build_redactor(project_id: str | None = None) -> "Redactor":
    """Build a Redactor seeded with the current project ID."""
    return Redactor(project_id=project_id)


class Redactor:
    """Recursively redacts sensitive values from nested dicts/lists."""

    # Keys whose values are always redacted regardless of pattern matching
    SENSITIVE_KEYS = frozenset({
        "access_token",
        "refresh_token",
        "id_token",
        "token",
        "client_secret",
        "private_key",
        "private_key_id",
        "session_secret_key",
        "nextPageToken",
    })

    # Keys whose values get specific placeholder replacements
    KEY_REPLACEMENTS = {
        "access_token": "REDACTED_TOKEN",
        "refresh_token": "REDACTED_TOKEN",
        "id_token": "REDACTED_TOKEN",
        "token": "REDACTED_TOKEN",
        "client_secret": "REDACTED_CLIENT_SECRET",
        "private_key": "REDACTED_PRIVATE_KEY",
        "private_key_id": "REDACTED_KEY_ID",
        "session_secret_key": "REDACTED_SESSION_KEY",
        "nextPageToken": "REDACTED_PAGE_TOKEN",
        "sub": "REDACTED_SUB",
        "uniqueId": "000000000000000000000",
        "etag": "REDACTED_ETAG",
    }

    def __init__(self, project_id: str | None = None):
        self._project_id = project_id

    def redact(self, obj: object) -> object:
        """Recursively redact sensitive data from a JSON-like object."""
        if isinstance(obj, dict):
            return {k: self._redact_value(k, v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.redact(item) for item in obj]
        if isinstance(obj, str):
            return self._redact_string(obj)
        return obj

    def _redact_value(self, key: str, value: object) -> object:
        # Direct key-based replacement
        if key in self.KEY_REPLACEMENTS:
            return self.KEY_REPLACEMENTS[key]

        # Email fields in OAuth responses
        if key == "email" and isinstance(value, str) and "@" in value:
            return "user@REDACTED_DOMAIN"
        if key == "hd" and isinstance(value, str):
            return "REDACTED_DOMAIN"

        # client_id pattern
        if key == "client_id" and isinstance(value, str):
            return "REDACTED_CLIENT_ID"

        # Recurse into nested structures
        if isinstance(value, (dict, list)):
            return self.redact(value)

        # String-level redaction for non-keyed values
        if isinstance(value, str):
            return self._redact_string(value)

        return value

    def _redact_string(self, s: str) -> str:
        # SA email first (before project ID replacement breaks the pattern)
        s = _SA_EMAIL_RE.sub("REDACTED_SA_EMAIL", s)

        # Project ID replacement
        if self._project_id and self._project_id in s:
            s = s.replace(self._project_id, "REDACTED_PROJECT")

        # Client ID
        s = _CLIENT_ID_RE.sub("REDACTED_CLIENT_ID", s)

        # Client secret
        s = _CLIENT_SECRET_RE.sub("REDACTED_CLIENT_SECRET", s)

        # Private keys
        s = _PEM_PRIVATE_RE.sub("REDACTED_PRIVATE_KEY", s)

        # Token-like strings (only if the whole string looks like a token)
        if any(s.startswith(prefix) for prefix in _TOKEN_PREFIXES):
            return "REDACTED_TOKEN"

        return s


# ---------------------------------------------------------------------------
# GCP Call Definitions
# ---------------------------------------------------------------------------

# Each call is a dict with:
#   name: unique identifier
#   phase: which phase it belongs to
#   description: what it does
#   output_path: relative path under FIXTURES_DIR
#   capture_fn: callable(project_id, credentials_path) -> dict


def _capture_google_oidc_certs(**_kwargs: object) -> dict:
    """Fetch Google's public OIDC signing certificates."""
    import httpx

    url = "https://www.googleapis.com/oauth2/v1/certs"
    response = httpx.get(url, timeout=30)
    response.raise_for_status()
    return {
        "request": {"method": "GET", "url": url, "headers": {}},
        "response": {
            "status": response.status_code,
            "headers": {"content-type": response.headers.get("content-type", "")},
            "body": response.json(),
        },
    }


def _capture_iam_list_service_accounts(
    project_id: str, credentials_path: str, **_kwargs: object
) -> dict:
    """List all service accounts in the project via IAM API."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    service = build("iam", "v1", credentials=creds)

    request = service.projects().serviceAccounts().list(
        name=f"projects/{project_id}", pageSize=50
    )
    result = request.execute()

    return {
        "request": {
            "method": "GET",
            "url": f"https://iam.googleapis.com/v1/projects/{project_id}/serviceAccounts?pageSize=50",
            "headers": {},
        },
        "response": {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "body": result,
        },
    }


def _capture_iam_list_keys(
    project_id: str, credentials_path: str, **_kwargs: object
) -> list[dict]:
    """List keys for each service account. Returns multiple fixtures."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    service = build("iam", "v1", credentials=creds)

    # First get the list of SAs
    sa_request = service.projects().serviceAccounts().list(
        name=f"projects/{project_id}", pageSize=50
    )
    sa_result = sa_request.execute()
    accounts = sa_result.get("accounts", [])

    fixtures = []
    for i, account in enumerate(accounts):
        sa_email = account["email"]
        sa_name = f"projects/{project_id}/serviceAccounts/{sa_email}"

        keys_request = service.projects().serviceAccounts().keys().list(
            name=sa_name, keyTypes=["USER_MANAGED"]
        )
        keys_result = keys_request.execute()

        fixtures.append({
            "sa_index": i,
            "sa_email": sa_email,
            "fixture": {
                "request": {
                    "method": "GET",
                    "url": f"https://iam.googleapis.com/v1/{sa_name}/keys?keyTypes=USER_MANAGED",
                    "headers": {},
                },
                "response": {
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": keys_result,
                },
            },
        })

    return fixtures


def _capture_iam_get_public_key(
    project_id: str, credentials_path: str, **_kwargs: object
) -> list[dict]:
    """Get public key PEM for each user-managed key. Returns multiple fixtures."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    service = build("iam", "v1", credentials=creds)

    # Walk: SAs -> keys -> get each key
    sa_request = service.projects().serviceAccounts().list(
        name=f"projects/{project_id}", pageSize=50
    )
    sa_result = sa_request.execute()

    fixtures = []
    sa_index = 0
    for account in sa_result.get("accounts", []):
        sa_email = account["email"]
        sa_name = f"projects/{project_id}/serviceAccounts/{sa_email}"

        keys_request = service.projects().serviceAccounts().keys().list(
            name=sa_name, keyTypes=["USER_MANAGED"]
        )
        keys_result = keys_request.execute()

        for key_index, key in enumerate(keys_result.get("keys", [])):
            key_name = key["name"]
            key_request = service.projects().serviceAccounts().keys().get(
                name=key_name, publicKeyType="TYPE_X509_PEM_FILE"
            )
            key_result = key_request.execute()

            fixtures.append({
                "sa_index": sa_index,
                "key_index": key_index,
                "fixture": {
                    "request": {
                        "method": "GET",
                        "url": f"https://iam.googleapis.com/v1/{key_name}?publicKeyType=TYPE_X509_PEM_FILE",
                        "headers": {},
                    },
                    "response": {
                        "status": 200,
                        "headers": {"content-type": "application/json"},
                        "body": key_result,
                    },
                },
            })
        sa_index += 1

    return fixtures


# Registry of all capturable calls
CALLS: dict[str, dict] = {
    "google-oidc-certs": {
        "phase": 2,
        "description": "Google OIDC public signing certs (v1, PEM format)",
        "output_path": "google_oidc/v1_certs.json",
        "capture_fn": _capture_google_oidc_certs,
        "multi": False,
    },
    "iam-list-service-accounts": {
        "phase": 2,
        "description": "List all service accounts in the GCP project",
        "output_path": "iam/list_service_accounts.json",
        "capture_fn": _capture_iam_list_service_accounts,
        "multi": False,
    },
    "iam-list-keys": {
        "phase": 2,
        "description": "List user-managed keys for each service account",
        "output_path": "iam/list_keys__sa{sa_index}.json",
        "capture_fn": _capture_iam_list_keys,
        "multi": True,
    },
    "iam-get-public-key": {
        "phase": 2,
        "description": "Get X.509 PEM for each user-managed key",
        "output_path": "iam/get_public_key__sa{sa_index}_key{key_index}.json",
        "capture_fn": _capture_iam_get_public_key,
        "multi": True,
    },
}

# Phases 3-6 calls will be added here as those phases begin.
# Placeholder entries for planning visibility:
PLANNED_CALLS: dict[str, dict] = {
    "google-tokeninfo": {"phase": 3, "description": "Validate access token via tokeninfo endpoint"},
    "google-oauth-token-exchange": {"phase": 4, "description": "Exchange auth code for tokens"},
    "google-oauth-token-refresh": {"phase": 4, "description": "Refresh access token"},
    "google-userinfo": {"phase": 4, "description": "Fetch user profile"},
    "secret-manager-get": {"phase": 4, "description": "Read secret version"},
    "secret-manager-list": {"phase": 5, "description": "List secrets"},
    "secret-manager-create": {"phase": 6, "description": "Create secret + version"},
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_project_and_creds() -> tuple[str, str]:
    """Read project ID and credentials path from env or SA key file."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not creds_path or not Path(creds_path).exists():
        print("ERROR: GOOGLE_APPLICATION_CREDENTIALS not set or file not found.", file=sys.stderr)
        print("  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json", file=sys.stderr)
        sys.exit(1)

    project_id = os.environ.get("GCP_PROJECT", "")
    if not project_id:
        # Try to read from the SA key file
        with open(creds_path) as f:
            key_data = json.load(f)
        project_id = key_data.get("project_id", "")

    if not project_id:
        print("ERROR: GCP_PROJECT not set and not found in SA key file.", file=sys.stderr)
        sys.exit(1)

    return project_id, creds_path


def _write_fixture(path: Path, data: dict, redactor: Redactor) -> None:
    """Redact and write a fixture file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    redacted = redactor.redact(data)
    path.write_text(json.dumps(redacted, indent=2) + "\n")
    print(f"  wrote: {path.relative_to(Path.cwd())}")


def cmd_capture(args: argparse.Namespace) -> None:
    """Capture GCP fixtures for a phase or specific call."""
    if args.call:
        calls_to_run = {args.call: CALLS[args.call]}
    elif args.phase:
        calls_to_run = {k: v for k, v in CALLS.items() if v["phase"] == args.phase}
    else:
        calls_to_run = CALLS

    if not calls_to_run:
        print(f"No calls defined for phase {args.phase}.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("Dry run — would capture:")
        for name, info in calls_to_run.items():
            print(f"  [{name}] {info['description']}")
            print(f"    → {FIXTURES_DIR / info['output_path']}")
        if args.phase:
            planned = {k: v for k, v in PLANNED_CALLS.items() if v["phase"] == args.phase}
            if planned:
                print("\nPlanned (not yet implemented):")
                for name, info in planned.items():
                    print(f"  [{name}] {info['description']}")
        return

    project_id, creds_path = _resolve_project_and_creds()
    redactor = build_redactor(project_id)

    print(f"Capturing {len(calls_to_run)} call(s) for project={project_id}")
    print(f"Fixtures dir: {FIXTURES_DIR}\n")

    for name, info in calls_to_run.items():
        print(f"[{name}] {info['description']}...")
        try:
            result = info["capture_fn"](project_id=project_id, credentials_path=creds_path)

            if info.get("multi"):
                # Result is a list of {sa_index, key_index, fixture} dicts
                for item in result:
                    path_template = info["output_path"]
                    path_str = path_template.format(**{k: v for k, v in item.items() if k != "fixture"})
                    _write_fixture(FIXTURES_DIR / path_str, item["fixture"], redactor)
                if not result:
                    print("  (no results — no user-managed keys found)")
            else:
                _write_fixture(FIXTURES_DIR / info["output_path"], result, redactor)

        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            if not args.continue_on_error:
                raise

    print("\nDone.")


def cmd_redact(args: argparse.Namespace) -> None:
    """Redact an existing JSON file."""
    input_path = Path(args.redact)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found.", file=sys.stderr)
        sys.exit(1)

    project_id = os.environ.get("GCP_PROJECT", "")
    redactor = build_redactor(project_id or None)

    raw = json.loads(input_path.read_text())
    redacted = redactor.redact(raw)

    output_path = Path(args.output) if args.output else input_path.with_suffix(".redacted.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(redacted, indent=2) + "\n")
    print(f"Redacted: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture and redact GCP API responses as test fixtures."
    )
    parser.add_argument("--phase", type=int, help="Capture all calls for this phase (2-6)")
    parser.add_argument("--call", choices=list(CALLS.keys()), help="Capture a specific call")
    parser.add_argument("--dry-run", action="store_true", help="List calls without executing")
    parser.add_argument("--continue-on-error", action="store_true", help="Don't stop on first error")
    parser.add_argument("--redact", metavar="FILE", help="Redact an existing raw JSON file")
    parser.add_argument("--output", metavar="FILE", help="Output path for --redact")

    args = parser.parse_args()

    if args.redact:
        cmd_redact(args)
    elif args.phase or args.call or args.dry_run:
        cmd_capture(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
