# Guide 02: Consumer Howto

> Run Dockmaster locally and integrate your service. Covers environment setup, dev server, and walkthroughs for every auth flow.

**Audience**: Developers who want to run Dockmaster and have their services authenticate through it.
**Assumes**: GCP setup from [Guide 01](GUIDE-01-gcp-setup.md) is complete.

---

## 1. Prerequisites

You need three tools installed:

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | 3.12+ | Runtime |
| **uv** | Latest | Python package manager (replaces pip/venv) |
| **just** | Latest | Command runner (like make, but simpler) |

### Install Python 3.12+

```bash
# macOS (Homebrew)
brew install python@3.13

# Verify
python3 --version
```

For other platforms: https://www.python.org/downloads/

### Install uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify
uv --version
```

For other methods: https://docs.astral.sh/uv/getting-started/installation/

### Install just

```bash
# macOS (Homebrew)
brew install just

# Verify
just --version
```

For other platforms: https://github.com/casey/just#installation

---

## 2. Install & Configure

### 2a. Clone & Install Dependencies

```bash
git clone https://github.com/your-org/dockmaster.git
cd dockmaster
just install
```

Verify the package is importable:

```bash
uv run python -c "import dockmaster; print('OK')"
```

### 2b. Environment Setup (.env)

Copy the example environment file and fill in the values from [Guide 01](GUIDE-01-gcp-setup.md):

```bash
cp .env.example .env
```

Edit `.env` and set the values. Here's how Guide 01 outputs map to environment variables:

| Guide 01 Output | Environment Variable | Example |
|---|---|---|
| GCP project ID | `SECRETS_PROJECT` | `myorg-platform` |
| Runtime SA key file | `SA_KEY_FILE` | `secrets/service-account-dockmaster.json` |
| Admin SA key file | `ADMIN_SA_KEY_FILE` | `secrets/service-account-dockmaster-admin.json` |
| OAuth Client ID | `CLIENT_ID` | `123456-abc.apps.googleusercontent.com` |
| OAuth Client Secret | `CLIENT_SECRET` | `GOCSPX-...` |
| Your email (for admin) | `DOCKMASTER_ADMIN_EMAILS` | `you@yourcompany.com` |

You also need to set the authorization fields. These control which JWTs and users Dockmaster will trust:

| Variable | What to set | Example |
|---|---|---|
| `AUTHORIZED_ISSUERS` | Trusted JWT issuers (comma-separated) | `https://accounts.google.com` |
| `AUTHORIZED_DOMAINS` | Allowed email domains (comma-separated) | `yourcompany.com,gmail.com` |
| `AUTHORIZED_AUDIENCE` | Allowed JWT audience values | Your OAuth Client ID |

For local development, also set:

```bash
# Disable proxy header enforcement (no reverse proxy locally)
REQUIRE_PROXY_HEADERS=false

# Allow CLI and SPA redirects
ALLOWED_REDIRECT_URIS=http://localhost:3000/callback
ALLOWED_ORIGINS=http://localhost:3000

# Enable Swagger docs UI
ENABLE_DOCS=true

# Log level (DEBUG for verbose startup logs)
LOG_LEVEL=INFO
```

### 2c. Verify Configuration

Confirm your `.env` loads correctly:

```bash
uv run python -c "
from dockmaster.config import Settings
s = Settings()
print(f'Project:    {s.secrets_project}')
print(f'SA key:     {s.sa_key_file}')
print(f'Client ID:  {s.client_id}')
print(f'Domains:    {s.authorized_domains}')
print(f'Log level:  {s.log_level}')
"
```

If any required values are missing, you'll see `None` — go back and update `.env`.

---

## 3. Running the Dev Server

Start the server:

```bash
just dev
# or directly:
uv run uvicorn dockmaster.main:app --reload --port 8000
```

### What to Expect at Startup

A healthy startup produces log lines like these (in order):

```
starting up                    log_level=INFO
sa_key_loaded                  email=dockmaster@myorg-platform.iam.gserviceaccount.com
sa_signer_initialized          email=dockmaster@myorg-platform.iam.gserviceaccount.com
token_issuer_initialized       kid=a1b2c3d4-...
ephemeral_key_cache_initialized
jwt_verifier_initialized       num_caches=2
auth_code_store_initialized    ttl=300
oauth_state_store_initialized
session_store_initialized      backend=in-memory
oauth_client_initialized
secrets_storage_initialized    project=myorg-platform
rbac_authority_initialized     cache_ttl=300
admin_storage_initialized
```

### Common Warnings

| Warning | Meaning | Impact |
|---------|---------|--------|
| `SESSION_SECRET_KEY not set — using auto-generated key` | No `SESSION_SECRET_KEY` in `.env` | Sessions won't survive server restarts. Fine for dev. |
| `SA_KEY_FILE not set — JWT signing disabled` | No service account key configured | `/auth/service/token` and SA-signed endpoints return 503 |
| `CLIENT_ID not set — OAuth login will return 503` | No OAuth credentials | `/auth/login` returns 503 — browser login won't work |
| `SECRETS_PROJECT not set — Secret Manager lookups will return 503` | No GCP project for RBAC | Permission checks and admin endpoints return 503 |
| `ADMIN_SA_KEY_FILE not set — RBAC write operations will return 503` | No admin SA key | Admin CRUD endpoints return 503 (reads still work) |

If you see all the "initialized" lines and no warnings, your setup is complete. Open http://localhost:8000/auth/health to confirm:

```bash
curl -s http://localhost:8000/auth/health | jq .
# → {"service": "dockmaster", "status": "ok"}
```

---

## 4. Walkthrough: Browser Login

This walkthrough uses Dockmaster's built-in UI to log in as a browser user and view the admin dashboard.

### Step 1: Open the Login Page

Navigate to http://localhost:8000/ui/login in your browser. You should see a login page with a "Sign in with Google" button.

### Step 2: Authenticate with Google

Click the button. You'll be redirected to Google's OAuth consent screen. Sign in with an account whose domain is in your `AUTHORIZED_DOMAINS` list.

### Step 3: Callback & Dashboard

After authenticating, Google redirects back to Dockmaster's `/auth/login/callback`. Dockmaster:
1. Exchanges the Google auth code for your user info
2. Validates your email domain
3. Creates a server-side session
4. Sets a signed `session_id` cookie in your browser
5. Redirects you to `/ui/` (the dashboard)

You should see the dashboard showing your email, profile picture, and active sessions.

### Step 4: Explore the Admin UI

If your email has the `admin` role (from the bootstrap data in Guide 01), you can access:

- **Roles** — http://localhost:8000/ui/roles — view and create RBAC roles
- **Grants** — http://localhost:8000/ui/grants — manage service grant assignments
- **Sessions** — http://localhost:8000/ui/sessions — view and revoke active sessions

### Step 5: Verify the Session Cookie

Open your browser's developer tools (F12) → **Application** tab → **Cookies**. You should see:

| Cookie | Value | Flags |
|--------|-------|-------|
| `session_id` | Signed token (long string) | HttpOnly |
| `session` | Starlette session data | HttpOnly |

The `session_id` cookie is Dockmaster's application session. It's signed with `itsdangerous` so tampering is detected server-side.

### Step 6: Sign Out

Click "Sign Out" on the dashboard, or navigate to http://localhost:8000/auth/logout. This destroys the server-side session and clears the cookie.

---

## 5. Walkthrough: CLI Usage

The Dockmaster CLI is included in the package — no separate install needed. All commands use `uv run dockmaster`.

### Login

```bash
uv run dockmaster login
```

This opens your browser to the Dockmaster login page. After authenticating with Google, the browser redirects to a local port where the CLI is listening. The CLI captures the JWT and stores it at `~/.local/share/dockmaster/`.

### Get a Token

Request a Type C JWT scoped to a target service:

```bash
uv run dockmaster token billing
```

This prints a JWT to stdout. You can decode it to inspect the claims:

```bash
TOKEN=$(uv run dockmaster token billing)
echo "$TOKEN" | cut -d. -f2 | tr '_-' '/+' | \
  awk '{while(length%4)$0=$0"=";print}' | base64 -d | jq .
```

Expected claims: `iss: "dockmaster"`, `aud: "billing"`, `sub: "you@yourcompany.com"`.

### Check Permissions

```bash
uv run dockmaster check you@yourcompany.com dockmaster -p admin
```

Prints `Oui!` if the permission is granted, `Non!` if denied.

### Manage Roles

```bash
# List all roles
uv run dockmaster role list

# Get a specific role
uv run dockmaster role get admin

# Create a role
uv run dockmaster role create editor -p read -p write -p list

# Delete a role
uv run dockmaster role delete editor
```

### Manage Grants

```bash
# List all services with grants
uv run dockmaster grant list

# Get grants for a specific service
uv run dockmaster grant get dockmaster
```

---

## 6. Walkthrough: Service Integration

This section covers how your service authenticates with Dockmaster programmatically. There are several integration patterns depending on your use case.

### 6a. Service-to-Service Token Exchange

If your service has a GCP service account, you can exchange a Google-signed JWT for a Dockmaster Type C JWT. This is the primary pattern for backend services.

```bash
BASE="http://localhost:8000"

# Step 1: Sign a JWT with your service account
SA_JWT=$(uv run python -c "
from dockmaster.auth.jwt_signers import ServiceAccountSigner
signer = ServiceAccountSigner('secrets/service-account-dockmaster.json')
print(signer.sign(subject=signer.client_email, audience='dockmaster', expiry=300))
")

# Step 2: Exchange for a Dockmaster Type C JWT
curl -s -X POST "$BASE/auth/service/token?service=my-target-service" \
  -H "Authorization: Bearer $SA_JWT" | jq .
```

Response:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}
```

The `access_token` is a Type C JWT signed by Dockmaster's ephemeral keypair. It contains the caller's identity (`sub`, `email`) and is scoped to the requested service (`aud`).

### 6b. Auth Code Flow (SPA / External App)

If your application has browser users, use the auth code flow. This is similar to OAuth — Dockmaster acts as the identity provider.

**Step 1**: Redirect the user to Dockmaster's login with your callback URL:

```
http://localhost:8000/auth/login?redirect_uri=http://localhost:3000/callback
```

> The `redirect_uri` must be in `ALLOWED_REDIRECT_URIS` or the request is rejected.

**Step 2**: After the user authenticates with Google, Dockmaster redirects to your callback with an auth code:

```
http://localhost:3000/callback?code=abc123&state=xyz
```

**Step 3**: Exchange the login ticket for a refresh token and profile:

```bash
curl -s -X POST "$BASE/auth/login/exchange" \
  -H "Content-Type: application/json" \
  -d '{"code": "abc123", "redirect_uri": "http://localhost:3000/callback"}' | jq .
```

The code is single-use and expires after 5 minutes. The `redirect_uri` must match exactly what was used in step 1.

### 6c. Permission Checks

Once your service has a JWT (Type A from a SA, or Type C from Dockmaster), you can check RBAC permissions:

```bash
# Check if alice@co.com has "read" permission on "data-pipeline"
curl -s "$BASE/auth/has/alice@co.com/data-pipeline/read" \
  -H "Authorization: Bearer $SA_JWT"
```

Returns `204 No Content` if granted, `403 Forbidden` if denied.

You can also get the full resolved grants for a subject on a target:

```bash
curl -s "$BASE/auth/grants?subject=alice@co.com&target=data-pipeline" \
  -H "Authorization: Bearer $SA_JWT" | jq .
```

### 6d. Token Verification in Your Service

To verify a Dockmaster Type C JWT in your own service without calling Dockmaster on every request:

**Step 1**: Extract the `kid` (Key ID) from the JWT header:

```python
import jwt

unverified_header = jwt.get_unverified_header(token)
kid = unverified_header["kid"]
```

**Step 2**: Fetch the public key from Dockmaster (cache this — it doesn't change until restart):

```bash
curl -s http://localhost:8000/auth/key/{kid}
# Returns PEM-encoded public key
```

**Step 3**: Verify the JWT:

```python
import jwt
import requests

def verify_dockmaster_token(token: str, dockmaster_url: str) -> dict:
    """Verify a Dockmaster Type C JWT and return the claims."""
    header = jwt.get_unverified_header(token)
    kid = header["kid"]

    # Fetch public key (cache this in production)
    resp = requests.get(f"{dockmaster_url}/auth/key/{kid}")
    resp.raise_for_status()
    public_key = resp.text

    # Verify signature and decode claims
    claims = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        options={"verify_aud": False},  # or set audience to your service name
    )
    return claims
```

In production, cache the public key by `kid` — it only changes when Dockmaster restarts (generating a new ephemeral keypair).

---

## 7. Environment Variable Reference

All configuration is via environment variables or `.env` file. Variables are grouped by function.

### Service

| Variable | Type | Default | Description |
|---|---|---|---|
| `SA_KEY_FILE` | `str` | `None` | Path to runtime SA JSON key file. Required for JWT signing, key enumeration, and SM reads. |
| `SECRETS_PROJECT` | `str` | `None` | GCP project ID for Secret Manager. Required for RBAC. |
| `LOG_LEVEL` | `str` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `ENABLE_DOCS` | `bool` | `false` | Enable Swagger UI at `/docs` and ReDoc at `/redoc`. |
| `SECURITY_HEADERS` | `bool` | `true` | Add security headers (CSP, X-Frame-Options, etc.) to responses. |

### Authorization

| Variable | Type | Default | Description |
|---|---|---|---|
| `AUTHORIZED_ISSUERS` | `comma-separated` | _(empty)_ | Trusted JWT issuers (e.g. `https://accounts.google.com`). |
| `AUTHORIZED_DOMAINS` | `comma-separated` | _(empty)_ | Allowed email domains for login and token exchange. |
| `AUTHORIZED_AUDIENCE` | `comma-separated` | _(empty)_ | Allowed JWT audience values. |

### OAuth

| Variable | Type | Default | Description |
|---|---|---|---|
| `CLIENT_ID` | `str` | `None` | Google OAuth client ID. Required for browser login. |
| `CLIENT_SECRET` | `str` | `None` | Google OAuth client secret. |
| `CLIENT_ID_SUFFIX` | `str` | `.apps.googleusercontent.com` | Suffix appended when matching audience to client IDs. |

### Token Issuance

| Variable | Type | Default | Description |
|---|---|---|---|
| `DOCKMASTER_TOKEN_TTL` | `int` | `900` | Default TTL (seconds) for issued Type C JWTs. |
| `MAX_TOKEN_TTL` | `int` | `3600` | Maximum allowed TTL for token requests. |
| `ALLOWED_REDIRECT_URIS` | `comma-separated` | _(empty)_ | Allowed redirect URIs for auth code flow and CLI login. |
| `ALLOWED_ORIGINS` | `comma-separated` | _(empty)_ | Allowed CORS origins for cross-origin requests. |
| `JWKS_REGISTRY_PATH` | `str` | `~/.local/share/dockmaster/jwks-registry.json` | Path to ephemeral JWKS registry file. |

### Admin

| Variable | Type | Default | Description |
|---|---|---|---|
| `ADMIN_SA_KEY_FILE` | `str` | `None` | Path to admin SA JSON key file. Required for RBAC write operations. |
| `DOCKMASTER_ADMIN_EMAILS` | `comma-separated` | _(empty)_ | Email addresses with admin access (bootstrap fallback). |

### RBAC

| Variable | Type | Default | Description |
|---|---|---|---|
| `RBAC_CACHE_TTL` | `int` | `300` | TTL (seconds) for cached RBAC data from Secret Manager. |

### Session

| Variable | Type | Default | Description |
|---|---|---|---|
| `SESSION_SECRET_KEY` | `str` | _(auto-generated)_ | Secret for signing session cookies. Auto-generated if not set (sessions won't survive restarts). Generate with: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `SESSION_TTL` | `int` | `3600` | Session expiry in seconds. |
| `REDIS_URL` | `str` | `None` | Redis connection URL for session storage. Currently unused (in-memory only). |

### Deployment

| Variable | Type | Default | Description |
|---|---|---|---|
| `REQUIRE_PROXY_HEADERS` | `bool` | `true` | Require `X-Forwarded-Proto` header. Set to `false` for local dev without a reverse proxy. |

### Logging

| Variable | Type | Default | Description |
|---|---|---|---|
| `LOG_FILE` | `str` | `None` | Path to log file. When set, JSON logs are written with rotation. |
| `LOG_FILE_MAX_BYTES` | `int` | `10485760` | Max log file size before rotation (default 10 MB). |
| `LOG_FILE_BACKUP_COUNT` | `int` | `5` | Number of rotated log files to keep. |

---

## 8. Endpoints Reference

### Health & Info

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | None | Service info (name, version, links) |
| `GET` | `/auth/health` | None | Health check — `{"status": "ok"}` |

### Auth Flows

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/auth/login` | None | Start OAuth login. Optional `?redirect_uri=` for SPA flows, `?return_to=` for post-login redirect. |
| `GET` | `/auth/login/callback` | None | OAuth callback (Google redirects here). |
| `POST` | `/auth/login/exchange` | None (code) | Exchange login ticket for `{refresh_token, profile, return_to}`. Body: `{"code", "redirect_uri"}`. |
| `POST` | `/auth/logout` | Session or refresh_token | Destroy session, clear cookie. |
| `GET` | `/auth/session/principal` | Session | Current user profile (email, name, picture). |
| `GET` | `/auth/session/list` | Session | Current user's active sessions. |
| `GET` | `/auth/cli/login` | None | Start CLI OAuth login (localhost redirect_uri only). |
| `GET` | `/auth/cli/callback` | None | CLI OAuth callback → JWT → redirect to localhost. |
| `POST` | `/auth/cli/token` | Bearer JWT | Issue a Type C JWT from a Bearer JWT. |

### Token Operations

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/auth/claims` | Bearer | Decode and return JWT claims. |
| `POST` | `/auth/service/token` | Bearer (Type A) | Exchange Google JWT/access token for Type C JWT. `?service=` sets audience. |
| `POST` | `/auth/session/token` | Session or refresh_token | Issue a new Type C JWT. `?service=` sets audience. |

### Public Keys

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/auth/key/{kid}` | None | Public key (PEM) for JWT verification by Key ID. |
| `GET` | `/auth/keys` | None | JWKS endpoint — all active public keys. |

### RBAC

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/auth/has/{subject}/{target}/{permission}` | Bearer (Type A) | Permission check — `204` granted, `403` denied. |
| `GET` | `/auth/grants` | Bearer (Type A) | Resolved grants for `?subject=&target=`. |

### Admin API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/admin/roles` | Admin | List all roles. |
| `GET` | `/admin/roles/{name}` | Admin | Get role by name. |
| `POST` | `/admin/roles` | Admin | Create a role. |
| `PUT` | `/admin/roles/{name}` | Admin | Update a role. |
| `DELETE` | `/admin/roles/{name}` | Admin | Delete a role. |
| `GET` | `/admin/grants` | Admin | List all services with grants. |
| `GET` | `/admin/grants/{service}` | Admin | Get grants for a service. |
| `POST` | `/admin/grants/{service}` | Admin | Create/replace grants for a service. |
| `DELETE` | `/admin/grants/{service}` | Admin | Delete grants for a service. |
| `GET` | `/admin/sessions` | Admin | List all active sessions. |
| `DELETE` | `/admin/sessions/id/{id}` | Admin | Revoke a session by ID. |
| `DELETE` | `/admin/sessions/email/{email}` | Admin | Revoke all sessions for an email. |

### UI Pages

| Path | Auth | Page |
|------|------|------|
| `/ui/login` | None | Login page (Google SSO button) |
| `/ui/` | Session | Dashboard (sessions, service status) |
| `/ui/roles` | Session (admin) | Manage RBAC roles |
| `/ui/grants` | Session (admin) | Manage service grants |
| `/ui/grants/{service}` | Session (admin) | Edit grants for a service |
| `/ui/sessions` | Session (admin) | Manage all sessions |

---

## Appendix A: Manual Curl Tests

A comprehensive test catalog for verifying every endpoint. Run these against a dev server to confirm your setup is working end-to-end.

### A1. Shell Helpers

Paste these into your terminal once per session. All tests below use them.

```bash
BASE="http://localhost:8000"

# Decode a JWT payload (handles base64url padding)
decode_jwt() {
  echo "$1" | cut -d. -f2 | tr '_-' '/+' | \
    awk '{while(length%4)$0=$0"=";print}' | base64 -d | jq .
}

# Extract a query param from a URL
get_param() {
  echo "$1" | sed "s/.*[?&]$2=\([^&]*\).*/\1/"
}
```

### A2. Health & Info

```bash
# Health check
curl -s "$BASE/auth/health" | jq .
# → {"service": "dockmaster", "status": "ok"}

# Service info
curl -s "$BASE/" | jq .
# → {"service": "dockmaster", "version": "...", "health": "/auth/health", ...}
```

### A3. Browser Login Flow

1. Open http://localhost:8000/ui/login in your browser
2. Click "Sign in with Google" and complete sign-in
3. You should land on `/ui/` (dashboard) showing your sessions

**Verify:**
- [ ] Login page renders with Google SSO button
- [ ] Google OAuth redirect works
- [ ] Dashboard shows your email and sessions
- [ ] Sign Out button works (redirects back to login)

### A4. CLI Login Flow

```bash
# Login via browser — opens browser, captures JWT
uv run dockmaster login

# Get a token for a service
TOKEN=$(uv run dockmaster token billing)
decode_jwt "$TOKEN"
```

**Verify:**
- [ ] `dockmaster login` opens browser, captures JWT
- [ ] JWT claims: `iss: "dockmaster"`, `aud: "billing"`, `sub` is your email

### A5. Token Exchange

```bash
# Sign a JWT with your SA
SA_JWT=$(uv run python -c "
from dockmaster.auth.jwt_signers import ServiceAccountSigner
signer = ServiceAccountSigner('secrets/service-account-dockmaster.json')
print(signer.sign(subject=signer.client_email, audience='dockmaster', expiry=300))
")

# Exchange for a Dockmaster Type C JWT
RESPONSE=$(curl -s -X POST "$BASE/auth/service/token?service=billing" \
  -H "Authorization: Bearer $SA_JWT")
echo "$RESPONSE" | jq .
TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')
decode_jwt "$TOKEN"
```

**Verify:**
- [ ] Returns `access_token`, `token_type: "bearer"`, `expires_in: 900`
- [ ] JWT claims: `iss: "dockmaster"`, `aud: "billing"`, `sub` is the SA email

### A6. Auth Code Exchange

```bash
# Step 1: Open in browser (requires ALLOWED_REDIRECT_URIS=http://localhost:3000/callback)
open "$BASE/auth/login?redirect_uri=http://localhost:3000/callback"
# Complete Google sign-in, then copy the full redirect URL from the browser

# Step 2: Extract the code
REDIRECT_URL="<paste full redirect URL here>"
CODE=$(get_param "$REDIRECT_URL" code)
echo "Code: $CODE"

# Step 3: Exchange code for refresh_token + profile
RESPONSE=$(curl -s -X POST "$BASE/auth/login/exchange" \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"$CODE\", \"redirect_uri\": \"http://localhost:3000/callback\"}")
echo "$RESPONSE" | jq .

# Step 4: Replay (should fail — single-use)
curl -s -X POST "$BASE/auth/login/exchange" \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"$CODE\", \"redirect_uri\": \"http://localhost:3000/callback\"}" | jq .
```

**Verify:**
- [ ] Redirect URL contains `?code=...&state=...`
- [ ] Exchange returns `refresh_token`, `profile`, `return_to`
- [ ] Replay returns 400: "Invalid or expired authorization code"

### A7. Token Issuance

```bash
# Using a session cookie or refresh_token
curl -s -X POST "$BASE/auth/session/token?service=billing" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "THE_REFRESH_TOKEN"}' | jq .
```

**Verify:**
- [ ] Returns a new Type C JWT with `aud: "billing"`

### A8. Permission Checks

```bash
# Check a permission (requires a Type A SA JWT)
curl -s "$BASE/auth/has/you@yourcompany.com/dockmaster/admin" \
  -H "Authorization: Bearer $SA_JWT"
# → 204 (granted)

curl -s "$BASE/auth/has/nobody@example.com/dockmaster/admin" \
  -H "Authorization: Bearer $SA_JWT"
# → 403 (denied)
```

### A9. Admin Endpoints

```bash
# Sign an admin JWT
ADMIN_EMAIL="you@yourcompany.com"
ADMIN_JWT=$(uv run python -c "
from dockmaster.auth.jwt_signers import ServiceAccountSigner
signer = ServiceAccountSigner('secrets/service-account-dockmaster.json')
print(signer.sign(subject='$ADMIN_EMAIL', audience='dockmaster', expiry=900))
")

# List roles
curl -s "$BASE/admin/roles" -H "Authorization: Bearer $ADMIN_JWT" | jq .

# Get a role
curl -s "$BASE/admin/roles/admin" -H "Authorization: Bearer $ADMIN_JWT" | jq .

# Create a role
curl -s -X POST "$BASE/admin/roles" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"name": "test-role", "permissions": ["read", "write"]}' | jq .

# Delete the test role
curl -s -X DELETE "$BASE/admin/roles/test-role" \
  -H "Authorization: Bearer $ADMIN_JWT" | jq .

# List sessions
curl -s "$BASE/admin/sessions" -H "Authorization: Bearer $ADMIN_JWT" | jq .

# Revoke a session by ID
curl -s -X DELETE "$BASE/admin/sessions/id/SESSION_ID" \
  -H "Authorization: Bearer $ADMIN_JWT" | jq .
```

### A10. Public Key Retrieval

```bash
# Get the current kid from a token
TOKEN=$(uv run dockmaster token billing)
KID=$(echo "$TOKEN" | cut -d. -f1 | tr '_-' '/+' | \
  awk '{while(length%4)$0=$0"=";print}' | base64 -d | jq -r '.kid')
echo "KID: $KID"

# Fetch the public key
curl -s "$BASE/auth/key/$KID"
# → -----BEGIN PUBLIC KEY-----  ...

# Unknown kid returns 404
curl -s "$BASE/auth/key/nonexistent" | jq .
# → {"detail": "Key not found"}
```

### A11. Reject Bad Redirect URIs

```bash
curl -s "$BASE/auth/login?redirect_uri=https://evil.com/callback" | jq .
# → 400: "Invalid redirect_uri: not in allowlist"
```

### A12. CORS Headers

```bash
# Allowed origin
curl -s -D - -o /dev/null -X OPTIONS "$BASE/auth/login/exchange" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type"
# → access-control-allow-origin: http://localhost:3000

# Disallowed origin
curl -s -D - -o /dev/null -X OPTIONS "$BASE/auth/login/exchange" \
  -H "Origin: https://evil.com" \
  -H "Access-Control-Request-Method: POST"
# → No access-control-allow-origin header
```

### Test Checklist

| # | Test | Status |
|---|------|--------|
| A2 | Health + Info | [ ] |
| A3 | Browser SSO Login | [ ] |
| A4 | CLI Login + Token | [ ] |
| A5 | Token Exchange | [ ] |
| A6 | Auth Code Exchange | [ ] |
| A7 | Token Issuance | [ ] |
| A8 | Permission Checks | [ ] |
| A9 | Admin Endpoints | [ ] |
| A10 | Public Key Retrieval | [ ] |
| A11 | Reject Bad Redirect URIs | [ ] |
| A12 | CORS Headers | [ ] |
