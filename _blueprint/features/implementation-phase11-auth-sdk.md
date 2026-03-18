# Phase 11: Auth SDK & Cross-Domain Consumer Support

> Server-side refresh token support, route reorganization, and Python consumer SDK
> for backend services verifying dockmaster-issued JWTs and checking permissions.

**Status**: Planned
**Priority**: P1
**Phase**: 11
**Last updated**: 2026-03-18

---

## Problem

Dockmaster is a working auth microservice (412 tests, Phases 1-8e complete). But consuming
services have no turnkey integration path, and cross-domain browser users have no way to
maintain sessions.

**Concrete deployment scenario:**
- **Domain A** (`domainA.com`): Dockmaster + multiple FastAPI backend APIs on the same server
  (Docker Compose). APIs need to verify Type C JWTs and check RBAC permissions.
- **Domain B** (`domainB.com`): A separate website (different TLD) where users log in via
  dockmaster, access protected pages, and call Domain A APIs. Different top-level domain means
  cookies cannot be shared — refresh tokens are required.

**What's missing today:**
1. No refresh token for cross-domain consumers — JWT expires after 15 min, user must re-login
2. No lightweight client for consuming APIs — manual key fetching, JWT verification, HTTP calls
3. Route structure evolved incrementally and mixes concerns (session, API, CLI, service auth)

---

## Solution Overview

Three workstreams:

1. **Route reorganization** — clean endpoint hierarchy with clear auth tiers
2. **Refresh token support** — cross-domain session handles backed by existing SessionStore
3. **Python consumer SDK** — `DockmasterClient` for JWT verification + permission checks

---

## Token Glossary

| Token | What it is | Who gets it | Lifetime | How it's used |
|---|---|---|---|---|
| **Google OAuth token** | Proof of Google login | Dockmaster internally | Consumed immediately | Dockmaster verifies, never exposes to client |
| **Auth code** | One-time code proving OAuth succeeded | Domain B client | 5 minutes | Exchanged for a session handle (single-use) |
| **Session handle** | Proof of active session | Browser users | SESSION_TTL (1 hour) | Domain A: `session_id` cookie. Domain B: `refresh_token` string. Same session in SessionStore. |
| **Type C JWT** | Short-lived API credential | Anyone calling APIs | 15 minutes | Bearer token for API calls. Verifiable by any service with dockmaster's public keys. |
| **Google SA JWT** | Signed by a Google service account key | Backend services | Short | Exchanged at dockmaster for a Type C JWT |

**Key insight**: The refresh token is not a new concept. It's the session ID (signed with
itsdangerous) delivered as a token instead of a cookie. Both resolve to the same session entry
in SessionStore. Admin revocation, TTL, and listing work identically for both.

---

## Route Reorganization

### Design principles

1. **Session-gated routes** accept cookie OR refresh_token (both = session handle)
2. **API-gated routes** accept only Bearer JWT Type C (the workhorse endpoints, stay top-level)
3. **CLI routes** are isolated (special admin case, own namespace)
4. **Service routes** are namespaced for SA-based auth
5. Login/logout are top-level and simple

### Endpoint map

**OAuth lifecycle (no auth):**

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/auth/login` | Start OAuth (both flows) | None. `redirect_uri` param for Domain B. |
| GET | `/auth/callback` | Internal (Google redirects here) | None (OAuth state validated) |
| POST | `/auth/login/code` | Exchange auth code for session | None (auth code validated). Returns `{refresh_token, profile}`. |
| POST | `/auth/logout` | Destroy session | Cookie or refresh_token in body |

**Session-gated (`/auth/session/*` — cookie OR refresh_token):**

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/auth/session/principal` | Who am I? | Cookie or refresh_token |
| POST | `/auth/session/token` | Get Type C JWT for a service | Cookie or refresh_token. `service` param required. |
| GET | `/auth/session/list` | My active sessions | Cookie or refresh_token |

**API-gated (top-level — Bearer JWT Type C):**

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/auth/has/{s}/{t}/{p}` | Permission check | Bearer JWT |
| GET | `/auth/claims` | JWT introspection | Bearer JWT |
| GET | `/auth/keys` | Public keys (JWKS) | None |

**Service account (`/auth/service/*`):**

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/auth/service/token` | Google SA token -> Type C JWT | Google JWT/access token |

**CLI (`/auth/cli/*`):**

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/auth/cli/token` | Dockmaster JWT -> service JWT | Bearer JWT (dockmaster audience) |

### Route rename mapping (old -> new)

| Old path | New path | Notes |
|---|---|---|
| `POST /auth/code/exchange` | `POST /auth/login/code` | Now also creates session, returns refresh_token |
| `GET /auth/logout` | `POST /auth/logout` | Method change. Optional: GET returns 405 with helpful message. |
| `GET /auth/principal` | `GET /auth/session/principal` | Moved to session namespace |
| `POST /auth/token` | `POST /auth/session/token` | Moved to session namespace. No longer accepts Bearer JWT. |
| `GET /auth/sessions` | `GET /auth/session/list` | Moved + renamed for clarity |
| `POST /auth/exchange` | `POST /auth/service/token` | Moved to service namespace |
| (new) | `POST /auth/cli/token` | Extracted from old `/auth/token` Bearer JWT path |

### Auth dependency changes

The existing `allow_jwt_or_session` dependency splits into:

- **`allow_session`** (cookie OR refresh_token): For `/auth/session/*` routes. Checks:
  1. `session_id` cookie -> unsign -> SessionStore.get()
  2. `refresh_token` in request body -> unsign -> SessionStore.get()
- **`allow_jwt`** (Bearer only): For API-gated routes. Unchanged.
- **CLI auth**: Separate dependency that verifies Bearer JWT with `aud=dockmaster`.

---

## Refresh Token Support

### Implementation

**In `POST /auth/login/code`** (replaces `POST /auth/code/exchange`):

1. Validate auth code (existing logic from `code_exchange`)
2. Create session in SessionStore (same as browser login in callback):
   ```
   session_id = uuid4()
   session_data = {email, name, picture, ...} (from auth code entry)
   session_store.set(session_id, session_data, ttl=SESSION_TTL)
   ```
3. Sign session ID: `signer.dumps(session_id)` -> refresh_token
4. Return: `{refresh_token: "<signed>", profile: {email, name, picture, ...}}`

**Note**: The auth code entry currently only stores `subject` (email) and `redirect_uri`.
To include profile data in the response, the auth code entry needs to carry profile claims
from the OAuth callback. Update `AuthCodeEntry` to include profile claims, and
`_handle_external_callback` to pass them through.

**In `POST /auth/session/token`**:

Accept refresh_token in request body as alternative to cookie:
```
Body: { "refresh_token": "...", "service": "billing" }
  OR
Cookie: session_id=<signed>   Query: ?service=billing
```

Both resolve to a session ID -> SessionStore.get() -> extract email -> issue Type C JWT.

**In `POST /auth/logout`**:

Accept refresh_token in request body as alternative to cookie:
```
Body: { "refresh_token": "..." }
  OR
Cookie: session_id=<signed>
```

Both resolve to session ID -> SessionStore.delete().

### CORS

Domain B needs to call these endpoints cross-origin:
- `POST /auth/login/code`
- `POST /auth/session/token`
- `POST /auth/logout`

All use request body (not cookies) for auth, so CORS is straightforward:
- Add Domain B's origin to `ALLOWED_ORIGINS` (existing setting)
- `credentials: false` (no cookies sent cross-origin)
- Standard `Content-Type: application/json`

### Session TTL

Refresh token sessions share the same `SESSION_TTL` as cookie sessions (default 1 hour).
No separate setting. One TTL, one revocation mechanism, one admin view.

---

## Python Consumer SDK

### Purpose

Lightweight client for Domain A backend APIs that receive Type C JWTs from callers (browser
SPAs or other services) and need to verify them + check permissions.

### Components

**`src/dockmaster/client/__init__.py` — `DockmasterClient`**

```python
from dockmaster.client import DockmasterClient

client = DockmasterClient(url="https://auth.domainA.com")
# Or: reads DOCKMASTER_URL env var if url not provided

# Verify incoming JWT (result cached by token hash + TTL)
claims = client.verify_jwt(token)
# -> {"sub": "user@example.com", "aud": "billing", "exp": ..., ...}

# Check permission (result cached by subject+target+permission + TTL)
has_access = await client.has_permission(
    bearer_token=token,       # forwarded from the request
    subject=claims["sub"],
    target="billing",
    permission="read",
)
# -> True / False
```

**`src/dockmaster/client/key_cache.py` — `HTTPKeyCache`**

- Fetches public keys from `GET /auth/keys` via httpx
- Implements `KeyCacheLike` protocol (defined in `auth/jwt_verifier.py`)
- TTL-based refresh (same pattern as existing `KeyCache` base class)
- Dependencies: `httpx` only (no GCP)

**Verification**: `DockmasterClient` uses `ServiceRealm` (from `auth/jwt_verifier.py`) +
`HTTPKeyCache`. ServiceRealm already has no heavy deps — only PyJWT.

### Dependencies (consumer path only)

- `httpx` — already in project
- `PyJWT` + `cryptography` — already in project
- `pydantic` — already in project (for config)

No new dependencies. No `google-auth`, `authlib`, `structlog`, `fastapi` required.

### Configuration

`DockmasterClient(url=None, cache_ttl=300, permission_cache_ttl=60)`

- `url`: Dockmaster base URL. Falls back to `DOCKMASTER_URL` env var.
- `cache_ttl`: How long to cache public keys (seconds).
- `permission_cache_ttl`: How long to cache permission check results (seconds).

---

## Import Hygiene

No formal `pyproject.toml` core/service split. Instead:

**Rule**: `dockmaster.client.*` modules may only import from:
- Standard library
- `httpx`
- `jwt` (PyJWT) + `cryptography`
- `pydantic`
- `dockmaster.auth.jwt_verifier` (ServiceRealm — clean, only PyJWT)

**Must NOT import from**: `dockmaster.config`, `dockmaster.routes`, `dockmaster.sessions`,
`dockmaster.main`, or anything pulling in `authlib`, `google-auth`, `google-cloud-*`,
`structlog`, `fastapi`.

**Validation**: Test that `from dockmaster.client import DockmasterClient` succeeds
without service-only deps.

---

## User Flows (end-to-end)

### Domain A browser user (session cookie)

```
1. Click Login
   GET /auth/login -> Google OAuth -> GET /auth/callback
   -> Session created, cookie set, redirect to /ui/

2. Call billing API
   POST /auth/session/token?service=billing  (cookie auto-sent)
   -> Type C JWT (aud: billing, 15 min)
   -> Call billing API with Bearer: <JWT>

3. JWT expired
   POST /auth/session/token?service=billing  (cookie still valid)
   -> New Type C JWT

4. Logout
   POST /auth/logout  (cookie sent)
   -> Session deleted
```

### Domain B browser user (refresh token)

```
1. Click Login
   GET /auth/login?redirect_uri=https://domainB.com/callback
   -> Google OAuth -> GET /auth/callback
   -> Auth code issued, redirect to Domain B with ?code=...&state=...
   POST /auth/login/code {code, redirect_uri}
   -> {refresh_token, profile: {email, name, picture}}
   -> Store refresh_token

2. Call billing API
   POST /auth/session/token {refresh_token, service: "billing"}
   -> Type C JWT (aud: billing, 15 min)
   -> Call billing API with Bearer: <JWT>

3. JWT expired
   POST /auth/session/token {refresh_token}  (session still valid)
   -> New Type C JWT

4. Logout
   POST /auth/logout {refresh_token}
   -> Session deleted
```

### Backend API (receiving calls, using SDK)

```
1. Receive API call with Bearer: <Type C JWT>

2. Verify JWT
   client.verify_jwt(token) -> claims
   Check claims["aud"] == "billing"

3. Check permission
   client.has_permission(
       bearer_token=token,
       subject=claims["sub"],
       target="billing",
       permission="read",
   ) -> True

4. Process request and return data
```

### Service-to-service (SA exchange)

```
1. Service has Google SA key (provisioned by admin)
   Sign Google JWT with SA key
   POST /auth/service/token {google_jwt}
   -> Type C JWT (aud: target-service, 15 min)

2. Call target service with Bearer: <Type C JWT>

3. JWT expired -> sign new Google JWT, exchange again
   (No refresh concept — SA key never expires, just rotated by admin)
```

---

## Files to Create

| File | Purpose |
|---|---|
| `src/dockmaster/client/__init__.py` | `DockmasterClient` class |
| `src/dockmaster/client/key_cache.py` | `HTTPKeyCache` (fetches from /auth/keys) |
| `src/dockmaster/routes/session.py` | Session-gated routes (principal, token, list) |
| `src/dockmaster/routes/service.py` | Service account routes (token exchange) |
| `src/dockmaster/routes/cli_routes.py` | CLI token route |
| `tests/client/conftest.py` | SDK test fixtures |
| `tests/client/test_client.py` | DockmasterClient tests |
| `tests/client/test_key_cache.py` | HTTPKeyCache tests |

## Files to Modify

| File | Changes |
|---|---|
| `src/dockmaster/routes/login.py` | Replace `code_exchange` with `login_code`. Update `_handle_external_callback` to pass profile claims. Change logout to POST. |
| `src/dockmaster/routes/token.py` | Remove (logic moves to `session.py` and `cli_routes.py`) |
| `src/dockmaster/routes/exchange.py` | Remove (logic moves to `service.py`) |
| `src/dockmaster/auth/dependencies.py` | Add refresh_token resolution to session auth. Split `allow_jwt_or_session`. |
| `src/dockmaster/auth/auth_code.py` | Extend `AuthCodeEntry` with profile claims |
| `src/dockmaster/main.py` | Update router registrations for new route modules |
| `src/dockmaster/templates/*.html` | Update logout link (GET -> POST form) |
| `tests/` | Update all route tests for new paths |

---

## Testing Approach

**Server-side (route reorg + refresh token):**
- Route rename tests: all existing route tests updated for new paths
- `POST /auth/login/code`: returns refresh_token + profile from valid auth code
- `POST /auth/session/token`: accepts refresh_token in body, returns Type C JWT
- `POST /auth/logout`: accepts refresh_token, deletes session
- Session revocation kills refresh token access
- CORS headers on cross-origin requests

**Python SDK:**
- `HTTPKeyCache`: mock httpx responses, test TTL refresh, test error handling
- `DockmasterClient.verify_jwt`: test with real keypair (reuse existing test fixtures)
- `DockmasterClient.has_permission`: mock httpx, test caching TTL, test bearer passthrough
- Integration test: full flow against running dockmaster (`@pytest.mark.integration`)

**Import hygiene:**
- Test that `from dockmaster.client import DockmasterClient` works without service deps

---

## Deferred Items (explicitly out of scope)

- **JS/npm SDK** — Domain B calls REST endpoints directly for now
- **`pyproject.toml` core/service split** — defer until external consumer demand
- **SA token exchange in SDK** — add `client.get_service_token()` in future phase
- **Refresh token rotation** — implement without rotation first, add as security enhancement
- **Cross-domain cookie sharing** — not applicable (different TLDs)
- **Service registry** — service names are convention-based
- **FastAPI integration layer for SDK** — consumers wire their own dependencies

---

## Dependencies

- **Requires**: Phase 9 (deployment readiness) — but route reorg can start in parallel
- **Enables**: First consuming services on Domain A and Domain B
- **Enables**: Future Phase 12+ work (JS SDK, packaging split, SA exchange in SDK)

## Acceptance Criteria

- [ ] `POST /auth/login/code` returns `{refresh_token, profile}` from auth code
- [ ] `POST /auth/session/token` accepts cookie or refresh_token, returns Type C JWT
- [ ] `POST /auth/logout` destroys session via cookie or refresh_token
- [ ] All route renames applied (login/code, session/*, service/token, cli/token)
- [ ] `DockmasterClient.verify_jwt()` verifies JWTs via `/auth/keys` (no GCP deps)
- [ ] `DockmasterClient.has_permission()` calls `/auth/has` with bearer passthrough + caching
- [ ] `dockmaster.client` imports cleanly without service-only dependencies
- [ ] All existing tests updated and passing with new routes
- [ ] Integration guide documents Domain A API and Domain B SPA patterns
