# Dockmaster Development Guide

Complete overview of dockmaster's auth flows and manual verification tests.

## Prerequisites

```bash
# Dev server running
uv run uvicorn dockmaster.main:app --reload

# .env configured with:
#   - Google OAuth credentials (CLIENT_ID, CLIENT_SECRET)
#   - SA_KEY_FILE, SECRETS_PROJECT
#   - ADMIN_SA_KEY_FILE, DOCKMASTER_ADMIN_EMAILS
#   - AUTHORIZED_DOMAINS, AUTHORIZED_ISSUERS, AUTHORIZED_AUDIENCE
#   - ALLOWED_REDIRECT_URIS=http://localhost:3000/callback
#   - ALLOWED_ORIGINS=http://localhost:3000
```

### Shell helpers

Paste these into your terminal once per session. All tests below use them.

```bash
BASE="http://localhost:8000"

# Decode a JWT payload (handles base64url padding)
decode_jwt() {
  echo "$1" | cut -d. -f2 | tr '_-' '/+' | awk '{while(length%4)$0=$0"=";print}' | base64 -d | jq .
}

# Extract a query param from a URL
get_param() {
  echo "$1" | sed "s/.*[?&]$2=\([^&]*\).*/\1/"
}
```

---

## 1. Architecture Overview

### Token Types

| Type | Issuer | Signed with | Purpose |
|------|--------|-------------|---------|
| **A** | Google (SA) | GCP SA private key | Service-to-service auth |
| **B** | Dockmaster (legacy) | GCP SA private key | Deprecated — replaced by Type C |
| **C** | Dockmaster | Ephemeral RSA keypair | User identity tokens |

### Auth Flows

**Flow 1: Browser SSO (session cookie)**

```
Browser → /auth/login → Google OAuth → /auth/callback
  → session cookie set → /ui/ dashboard
```

**Flow 2: CLI login (direct JWT)**

```
CLI → /auth/login?redirect_uri=http://localhost:<port>/callback
  → Google OAuth → /auth/callback
  → 302 to localhost with ?token=<Type C JWT>
  → CLI captures JWT, stores to disk
```

**Flow 3: Auth code flow (external service)**

```
SPA → /auth/login?redirect_uri=https://app.example.com/callback
  → Google OAuth → /auth/callback
  → 302 to redirect_uri with ?code=<auth_code>&state=<state>
  → SPA calls POST /auth/code/exchange {code, redirect_uri}
  → Type C JWT returned
```

**Flow 4: Token exchange (service-to-service)**

```
Service (with Google SA JWT or access token)
  → POST /auth/exchange?service=<target> [Bearer: <Google JWT>]
  → Type C JWT for target service
```

**Flow 5: Token issuance (authenticated user)**

```
Browser or CLI (with session cookie or Bearer JWT)
  → POST /auth/token?service=<target>
  → Type C JWT for target service
```

**Flow 6: Permission check**

```
Service (with Type A SA JWT)
  → GET /auth/has/<subject>/<target>/<permission>
  → 204 (granted) or 403 (denied)
```

### Endpoint Map

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/auth/health` | None | Health check |
| `GET` | `/auth/key/{kid}` | None | Public key (PEM) for JWT verification |
| `GET` | `/auth/login` | None | Start OAuth login |
| `GET` | `/auth/callback` | None | OAuth callback |
| `GET` | `/auth/logout` | Session | Destroy session |
| `GET` | `/auth/principal` | Session | Current user profile |
| `GET` | `/auth/sessions` | Session | Current user's sessions |
| `GET` | `/auth/claims` | Bearer | Decoded JWT claims |
| `POST` | `/auth/exchange` | Bearer (Type A) | Google JWT → Type C JWT |
| `POST` | `/auth/token` | Session or Bearer | Issue Type C JWT for a service |
| `POST` | `/auth/code/exchange` | None (code is credential) | Auth code → Type C JWT |
| `POST` | `/auth/refresh` | None (refresh token) | Google refresh token → JWT |
| `GET` | `/auth/has/{s}/{t}/{p}` | Bearer (Type A) | Permission check |
| `GET` | `/auth/grants` | Bearer (Type A) | Resolved grants for subject+target |
| `GET` | `/admin/roles` | Bearer (admin) | List roles |
| `GET` | `/admin/roles/{name}` | Bearer (admin) | Get role |
| `POST` | `/admin/roles` | Bearer (admin) | Create role |
| `PUT` | `/admin/roles/{name}` | Bearer (admin) | Update role |
| `DELETE` | `/admin/roles/{name}` | Bearer (admin) | Delete role |
| `GET` | `/admin/grants` | Bearer (admin) | List service grants |
| `GET` | `/admin/grants/{svc}` | Bearer (admin) | Get grants for service |
| `POST` | `/admin/grants/{svc}` | Bearer (admin) | Create/replace grants |
| `DELETE` | `/admin/grants/{svc}` | Bearer (admin) | Delete grants |
| `GET` | `/admin/sessions` | Bearer (admin) | List all sessions |
| `DELETE` | `/admin/sessions/id/{id}` | Bearer (admin) | Revoke session |
| `DELETE` | `/admin/sessions/email/{e}` | Bearer (admin) | Revoke user's sessions |

### UI Pages

| Path | Auth | Page |
|------|------|------|
| `/ui/login` | None | Login page (Google SSO button) |
| `/ui/` | Session | Dashboard (your sessions, service status) |
| `/ui/roles` | Session (admin) | Manage RBAC roles |
| `/ui/grants` | Session (admin) | Manage service grants |
| `/ui/grants/{svc}` | Session (admin) | Edit grants for a service |
| `/ui/sessions` | Session (admin) | Manage all sessions |

---

## 2. Manual Tests

### Test A: Health + Info

```bash
curl -s "$BASE/auth/health" | jq .
curl -s "$BASE/" | jq .
```

Expected: `{"service": "dockmaster", "status": "ok"}` and service info.

---

### Test B: Browser SSO Login

1. Open `http://localhost:8000/ui/login` in your browser
2. Click "Sign in with Google"
3. Complete Google sign-in
4. You should land on `/ui/` (dashboard) showing your sessions

**Verify:**
- [ ] Login page renders with Google SSO button
- [ ] Google OAuth redirect works
- [ ] Dashboard shows your email and sessions
- [ ] Sign Out button works (redirects back to login)

---

### Test C: Auth Code Flow (external service)

```bash
# Step 1: Open in browser
open "$BASE/auth/login?redirect_uri=http://localhost:3000/callback"
# Complete Google sign-in, then copy the redirect URL from the browser
```

```bash
# Step 2: Paste the full redirect URL
REDIRECT_URL="<paste here>"
CODE=$(get_param "$REDIRECT_URL" code)
echo "Code: $CODE"
```

```bash
# Step 3: Exchange code for JWT
RESPONSE=$(curl -s -X POST "$BASE/auth/code/exchange" \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"$CODE\", \"redirect_uri\": \"http://localhost:3000/callback\"}")
echo "$RESPONSE" | jq .

TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')
decode_jwt "$TOKEN"
```

**Verify:**
- [ ] Redirect URL contains `?code=...&state=...`
- [ ] Exchange returns `access_token`, `token_type: "bearer"`, `expires_in: 900`
- [ ] JWT claims: `iss: "dockmaster"`, `sub` is your email

```bash
# Step 4: Replay (should fail — single-use)
curl -s -X POST "$BASE/auth/code/exchange" \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"$CODE\", \"redirect_uri\": \"http://localhost:3000/callback\"}" | jq .
```

- [ ] Returns 400: "Invalid or expired authorization code"

---

### Test D: Reject bad redirect URIs

```bash
# Non-allowlisted redirect_uri at login
curl -s "$BASE/auth/login?redirect_uri=https://evil.com/callback" | jq .
```

- [ ] Returns 400: "Invalid redirect_uri: not in allowlist"

---

### Test E: CLI Login + Token

```bash
# Login via browser
uv run dockmaster login

# Get a token for a service
uv run dockmaster token billing

# Decode it
TOKEN=$(uv run dockmaster token billing)
decode_jwt "$TOKEN"
```

**Verify:**
- [ ] `dockmaster login` opens browser, captures JWT
- [ ] `dockmaster token billing` prints a JWT
- [ ] JWT claims: `iss: "dockmaster"`, `aud: "billing"`, `sub` is your email

---

### Test F: CLI RBAC Commands

```bash
# List roles
uv run dockmaster role list

# Get a specific role
uv run dockmaster role get admin

# Create a test role
uv run dockmaster role create test-role -p read -p write

# List grants
uv run dockmaster grant list

# Get grants for a service
uv run dockmaster grant get dockmaster

# Check a permission
uv run dockmaster check your@email.com dockmaster -p admin
```

**Verify:**
- [ ] `role list` shows role names
- [ ] `role get` shows role with permissions
- [ ] `role create` creates the role (verify with `role get test-role`)
- [ ] `grant list` shows services
- [ ] `grant get` shows grants for a service
- [ ] `check` prints Oui! or Non!

```bash
# Cleanup
uv run dockmaster role delete test-role
```

---

### Test G: Public Key Endpoint

```bash
# Get the current ephemeral kid from a token
TOKEN=$(uv run dockmaster token billing)
KID=$(echo "$TOKEN" | cut -d. -f1 | tr '_-' '/+' | awk '{while(length%4)$0=$0"=";print}' | base64 -d | jq -r '.kid')
echo "KID: $KID"

# Fetch the public key
curl -s "$BASE/auth/key/$KID"
```

**Verify:**
- [ ] Returns PEM-encoded public key (starts with `-----BEGIN PUBLIC KEY-----`)

```bash
# Unknown kid returns 404
curl -s "$BASE/auth/key/nonexistent" | jq .
```

- [ ] Returns 404

---

### Test H: Admin UI Pages

Login via browser first (`http://localhost:8000/ui/login`), then visit:

1. **Dashboard**: `http://localhost:8000/ui/`
2. **Roles**: `http://localhost:8000/ui/roles`
3. **Grants**: `http://localhost:8000/ui/grants`
4. **Sessions**: `http://localhost:8000/ui/sessions`

**Verify:**
- [ ] Dashboard shows your sessions and service status
- [ ] Roles page lists all roles, create form works
- [ ] Grants page lists services, can click into detail
- [ ] Grants detail page shows subject/role mappings
- [ ] Sessions page shows all active sessions with revoke buttons
- [ ] Revoking a session works (session disappears from list)

---

### Test I: CORS Headers

```bash
# Allowed origin
curl -s -D - -o /dev/null -X OPTIONS "$BASE/auth/code/exchange" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type"
```

- [ ] Has `access-control-allow-origin: http://localhost:3000`
- [ ] Has `access-control-allow-credentials: true`

```bash
# Disallowed origin
curl -s -D - -o /dev/null -X OPTIONS "$BASE/auth/code/exchange" \
  -H "Origin: https://evil.com" \
  -H "Access-Control-Request-Method: POST"
```

- [ ] No `access-control-allow-origin` header

---

### Test J: FastAPI Docs

Open `http://localhost:8000/docs` in your browser.

- [ ] Swagger UI renders
- [ ] All endpoints listed with correct methods and paths

---

## Checklist Summary

| # | Test | Status |
|---|------|--------|
| A | Health + Info | [ ] |
| B | Browser SSO Login | [ ] |
| C | Auth Code Flow | [ ] |
| D | Reject bad redirect URIs | [ ] |
| E | CLI Login + Token | [ ] |
| F | CLI RBAC Commands | [ ] |
| G | Public Key Endpoint | [ ] |
| H | Admin UI Pages | [ ] |
| I | CORS Headers | [ ] |
| J | FastAPI Docs | [ ] |
