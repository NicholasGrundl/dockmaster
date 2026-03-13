# GCP Call Tracing & Fixture Capture Guide

> How to log, capture, and redact GCP API calls during tracer bullet passes.
> Reusable across all phases.

**Last updated**: 2026-03-10

---

## Purpose

During Pass 1 (tracer bullet) for each phase, we run against real GCP services.
Every request + response must be captured as a JSON fixture file so that:

1. Pass 2 unit tests use real response shapes (not guessed mocks)
2. Pass 3 fake classes replay real behavior
3. Contributors without GCP access can run the full test suite

This guide covers:
- What GCP calls each phase makes
- How to capture them (script + manual)
- How to redact sensitive data automatically
- Where to store the fixtures

---

## GCP Calls by Phase

### Phase 2 — JWT Infrastructure

| Call | Method | Endpoint / API | Returns |
|------|--------|----------------|---------|
| Google OIDC public certs | `GET` | `https://www.googleapis.com/oauth2/v1/certs` | `{kid: pem_cert}` dict |
| List service accounts | `GET` | IAM `projects.serviceAccounts.list` | Paginated SA list |
| List SA keys | `GET` | IAM `projects.serviceAccounts.keys.list` | Key metadata per SA |
| Get SA public key | `GET` | IAM `projects.serviceAccounts.keys.get` | Base64 X.509 PEM |

**Library**: `google-api-python-client` discovery client (`iam` v1)

### Phase 3 — Token Exchange

| Call | Method | Endpoint / API | Returns |
|------|--------|----------------|---------|
| Validate access token | `GET` | `https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=...` | Token metadata (email, scope, expiry) |

**Library**: `httpx` (plain HTTP)

### Phase 4 — OAuth Login + Session

| Call | Method | Endpoint / API | Returns |
|------|--------|----------------|---------|
| Exchange auth code for tokens | `POST` | `https://oauth2.googleapis.com/token` | `{access_token, refresh_token, id_token, ...}` |
| Refresh access token | `POST` | `https://oauth2.googleapis.com/token` | `{access_token, id_token, ...}` |
| Fetch user profile | `GET` | `https://www.googleapis.com/oauth2/v3/userinfo` | `{sub, email, name, picture, hd, ...}` |
| Get OAuth client secret | `GET` | Secret Manager `projects.secrets.versions.access` | Secret payload bytes |

**Library**: `authlib` (OAuth), `google-cloud-secret-manager` (secrets)

### Phase 5 — RBAC

| Call | Method | Endpoint / API | Returns |
|------|--------|----------------|---------|
| Read role/grant secret | `GET` | Secret Manager `projects.secrets.versions.access` | JSON role/grant definition |
| List secrets | `GET` | Secret Manager `projects.secrets.list` | Paginated secret list |

**Library**: `google-cloud-secret-manager`

### Phase 6 — RBAC Management + CLI

| Call | Method | Endpoint / API | Returns |
|------|--------|----------------|---------|
| Create/update secret | `POST`/`PATCH` | Secret Manager `projects.secrets.create` / `addSecretVersion` | Secret metadata |
| Delete secret version | `POST` | Secret Manager `projects.secrets.versions.destroy` | Version metadata |

**Library**: `google-cloud-secret-manager`

---

## Prerequisites

Before running any capture:

1. **GCP project** with IAM API and Secret Manager API enabled
2. **Service account key** (JSON) with roles:
   - `roles/iam.serviceAccountKeyAdmin` (read SA keys)
   - `roles/secretmanager.secretAccessor` (read secrets, Phase 4+)
3. **Environment variables** set:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/sa-key.json"
   export GCP_PROJECT="your-project-id"
   ```

---

## Capture Methods

### Method 1: Capture Script (recommended)

Use `scripts/capture_gcp_fixtures.py` to exercise each GCP call and dump
redacted fixtures automatically.

```bash
# Capture Phase 2 fixtures
uv run python scripts/capture_gcp_fixtures.py --phase 2

# Capture a specific call
uv run python scripts/capture_gcp_fixtures.py --call google-oidc-certs

# Dry run (prints what would be captured, no GCP calls)
uv run python scripts/capture_gcp_fixtures.py --phase 2 --dry-run
```

Output lands in `tests/fixtures/gcp/<service>/<call>.json`.

### Method 2: curl (one-off manual capture)

For plain HTTP endpoints (no auth required):

```bash
# Google OIDC certs
curl -s https://www.googleapis.com/oauth2/v1/certs | python -m json.tool > /tmp/google_oidc_certs_raw.json
```

For authenticated endpoints, use a bearer token from `gcloud`:

```bash
TOKEN=$(gcloud auth print-access-token)

# List service accounts
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://iam.googleapis.com/v1/projects/${GCP_PROJECT}/serviceAccounts?pageSize=50" \
  | python -m json.tool > /tmp/list_service_accounts_raw.json
```

Then run the redaction script on the raw file:

```bash
uv run python scripts/capture_gcp_fixtures.py --redact /tmp/list_service_accounts_raw.json \
  --output tests/fixtures/gcp/iam/list_service_accounts.json
```

### Method 3: httpx logging transport (in-app capture)

For captures during actual app execution (integration tests), wrap httpx with
a logging transport that dumps each request/response:

```python
import httpx
import json
from pathlib import Path

class FixtureCaptureTransport(httpx.BaseTransport):
    """Wraps a real transport; logs every request/response to a fixture file."""

    def __init__(self, transport: httpx.BaseTransport, output_dir: Path):
        self._transport = transport
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._transport.handle_request(request)
        self._counter += 1
        fixture = {
            "request": {
                "method": str(request.method),
                "url": str(request.url),
                "headers": dict(request.headers),
            },
            "response": {
                "status": response.status_code,
                "headers": dict(response.headers),
                "body": _try_parse_json(response.text),
            },
        }
        path = self._output_dir / f"capture_{self._counter:03d}.json"
        path.write_text(json.dumps(fixture, indent=2))
        return response


def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
```

This is useful for Phase 4 OAuth flows where authlib drives the HTTP calls
internally.

---

## Fixture File Format

Each fixture is a JSON file with request + response:

```json
{
  "request": {
    "method": "GET",
    "url": "https://iam.googleapis.com/v1/projects/REDACTED_PROJECT/serviceAccounts",
    "headers": {}
  },
  "response": {
    "status": 200,
    "headers": {
      "content-type": "application/json"
    },
    "body": {
      "accounts": [
        {
          "name": "projects/REDACTED_PROJECT/serviceAccounts/REDACTED_SA_EMAIL",
          "email": "REDACTED_SA_EMAIL",
          "uniqueId": "000000000000000000000"
        }
      ]
    }
  }
}
```

---

## Fixture Directory Layout

```
tests/fixtures/gcp/
├── iam/
│   ├── list_service_accounts.json
│   ├── list_keys__sa1.json
│   ├── get_public_key__sa1_key1.json
│   └── get_public_key__sa1_key2.json
├── google_oidc/
│   └── v1_certs.json
├── secret_manager/
│   ├── get_secret_version.json
│   ├── list_secrets.json
│   └── create_secret.json
├── google_oauth/
│   ├── token_exchange.json
│   ├── token_refresh.json
│   └── userinfo.json
└── google_tokeninfo/
    └── tokeninfo.json
```

---

## Redaction Rules

All fixtures are redacted before committing. The capture script applies these
automatically. The following fields are replaced with deterministic placeholder
values:

| Field Pattern | Replacement | Example |
|---------------|-------------|---------|
| GCP project ID | `REDACTED_PROJECT` | `my-prod-project` → `REDACTED_PROJECT` |
| Service account email | `REDACTED_SA_EMAIL` | `my-sa@proj.iam.gserviceaccount.com` → `REDACTED_SA_EMAIL` |
| Service account unique ID | `000000000000000000000` | `117...` → `000000000000000000000` |
| Private key (PEM) | `REDACTED_PRIVATE_KEY` | Full PEM block → `REDACTED_PRIVATE_KEY` |
| Access/refresh/ID tokens | `REDACTED_TOKEN` | `ya29.a0...` → `REDACTED_TOKEN` |
| Client ID | `REDACTED_CLIENT_ID` | `1234...apps.googleusercontent.com` → `REDACTED_CLIENT_ID` |
| Client secret | `REDACTED_CLIENT_SECRET` | `GOCSPX-...` → `REDACTED_CLIENT_SECRET` |
| Key resource name | Preserves structure, redacts IDs | `projects/REDACTED_PROJECT/serviceAccounts/REDACTED_SA_EMAIL/keys/REDACTED_KEY_ID` |
| `publicKeyData` (base64 PEM) | Replaced with test key's base64 PEM | Real cert → test cert |
| OAuth `sub` claim | `REDACTED_SUB` | `1180...` → `REDACTED_SUB` |
| Email in OAuth responses | `user@REDACTED_DOMAIN` | `nick@company.com` → `user@REDACTED_DOMAIN` |
| `hd` (hosted domain) | `REDACTED_DOMAIN` | `company.com` → `REDACTED_DOMAIN` |

### What we keep (not sensitive)

- Response structure and field names (the whole point of fixtures)
- HTTP status codes and content-type headers
- Google's public OIDC cert PEMs (these are literally public)
- Key types (`USER_MANAGED`, `SYSTEM_MANAGED`)
- Algorithm names (`RS256`)
- Pagination structure (`nextPageToken` presence, but value redacted)
- Error response shapes (for error-case fixtures)

---

## Workflow: Capturing Fixtures for a Phase

1. **Set up env**: export `GOOGLE_APPLICATION_CREDENTIALS` and `GCP_PROJECT`
2. **Run capture**: `uv run python scripts/capture_gcp_fixtures.py --phase N`
3. **Review output**: check `tests/fixtures/gcp/` — verify redaction looks right
4. **Commit fixtures**: `git add tests/fixtures/gcp/`
5. **Write tests**: import fixtures in unit tests via `conftest.py` helpers

### Loading fixtures in tests

```python
# tests/conftest.py addition
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "gcp"

@pytest.fixture
def iam_list_service_accounts():
    return json.loads((FIXTURES_DIR / "iam" / "list_service_accounts.json").read_text())

@pytest.fixture
def google_oidc_certs():
    return json.loads((FIXTURES_DIR / "google_oidc" / "v1_certs.json").read_text())
```

---

## Notes

- **Google OIDC certs are public** — no redaction needed for the PEM values
  themselves, but we still redact the request headers (in case auth headers
  leak in)
- **Rate limits**: IAM API has generous quotas but paginate properly (50 per
  page). Don't hammer it in a loop.
- **`publicKeyData`**: The IAM API returns X.509 certs base64-encoded. During
  redaction, we swap in a test cert generated from our test RSA key pair so
  that unit tests can actually verify JWTs against the fixture data.
