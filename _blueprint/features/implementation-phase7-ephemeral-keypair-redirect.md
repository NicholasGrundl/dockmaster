---
state: Draft
changelog:
  "2026-03-13 17h": "Senior review complete — added CORS, OIDC discovery, updated decisions"
  "2026-03-13 16h": "Initial outline from planning interview — decisions made, flows defined"
---

# Phase 7 — Ephemeral Keypair + Redirect URI + Token Issuance

> Dockmaster issues its own identity JWTs (Type C) signed with an ephemeral RSA keypair,
> replacing GCP SA-signed tokens. External services integrate via auth code flow with
> redirect URI allowlisting.

**Status**: Draft (planning in progress)
**Priority**: P0
**Phase**: 7
**Last updated**: 2026-03-13

---

## Problem

Dockmaster currently signs user JWTs with the GCP service account private key (Type B tokens).
This creates three problems:

1. **Security:** If the SA key file leaks, an attacker can forge user identity tokens.
2. **Coupling:** Downstream services need GCP IAM API access to verify tokens. Every consumer
   needs Google credentials.
3. **Integration:** External SPAs and services have no standard way to authenticate users
   through dockmaster and get tokens for calling other services.

## Solution

### Overview

Three interconnected capabilities:

1. **Ephemeral Key Manager** — RSA keypair generated at startup (private key in RAM only).
   Public keys persisted to a local JSON registry for cross-restart verification.
2. **JWKS Endpoint** — Standard `/.well-known/jwks.json` serving public keys. Any service
   can verify dockmaster tokens with a simple HTTP fetch — no GCP credentials needed.
3. **Auth Code Flow** — External SPAs redirect users to dockmaster for Google SSO, receive
   an auth code, and exchange it for a Type C JWT. Redirect URIs are allowlisted via env var.

All dockmaster-issued tokens become Type C (ephemeral-signed, identity-only). Type B is retired.

### JWT Design (Type C)

Identity-only — no embedded grants. Downstream services check permissions via `/auth/has`
or `/auth/grants`.

```json
{
  "sub": "nick@example.com",
  "email": "nick@example.com",
  "iss": "dockmaster",
  "aud": "billing-service",
  "iat": 1741905900,
  "exp": 1741906800,
  "kid": "dk-2026-03-13-a1b2c3"
}
```

---

## Implementation Sections

### 1. Ephemeral Key Manager

New module: `src/dockmaster/auth/key_manager.py`

**Responsibilities:**
- Generate 2048-bit RSA keypair on construction
- Assign a unique `kid` (e.g. `dk-{date}-{uuid[:8]}`)
- Private key lives only in memory (never written to disk)
- Public key registry: load existing keys from JSON file, append new key, prune expired keys
- Registry persisted via `platformdirs` (e.g. `~/.local/share/dockmaster/jwks-registry.json`)

**Key retention:** Keep public keys for `max(DOCKMASTER_TOKEN_TTL * 2, 1 hour)` after the
keypair that signed them was retired (i.e. after a restart). This allows tokens signed by
the previous key to remain verifiable until they expire.

**Interface sketch:**
```
KeyManager:
  current_private_key: RSAPrivateKey  (in memory only)
  current_kid: str
  public_jwks: list[dict]             (all active public keys in JWK format)

  rotate()           → generate new keypair, append to registry, prune old
  get_jwks()         → {"keys": [...]}  (for JWKS endpoint)
  sign(claims)       → str             (JWT signed with current key)
```

### 2. JWKS Endpoint

New route module: `src/dockmaster/routes/jwks.py`

**Endpoints:**
- `GET /.well-known/jwks.json` — standard RFC 7517 path
- `GET /auth/jwks` — same data, under the `/auth` namespace

Both return `KeyManager.get_jwks()`. Public endpoint — no authentication required.

**Response format:**
```json
{
  "keys": [
    {
      "kty": "RSA",
      "alg": "RS256",
      "use": "sig",
      "kid": "dk-2026-03-13-a1b2c3",
      "n": "<base64url modulus>",
      "e": "AQAB"
    }
  ]
}
```

### 3. Token Issuer (`DockTokenIssuer`)

New module: `src/dockmaster/auth/token_issuer.py`

**Responsibilities:**
- Sign Type C JWTs using the `KeyManager`'s current ephemeral key
- Build standard claims: `sub`, `email`, `iss` ("dockmaster"), `aud`, `iat`, `exp`, `kid`
- Configurable TTL via `DOCKMASTER_TOKEN_TTL` setting

**Interface sketch:**
```
DockTokenIssuer:
  key_manager: KeyManager
  default_ttl: int

  issue(subject, audience, ttl=None, extra_claims=None) → str
```

**Replaces `ServiceUser` for all dockmaster-issued tokens.** `ServiceUser` continues to exist
for signing Type A SA JWTs (used by the CLI and service-to-service auth).

### 4. Token Endpoint

New endpoint in existing or new route module.

- `POST /auth/token?service=<target_service>`
- **Auth:** Session cookie (browser) or CLI credentials
- **Returns:** `{access_token, token_type: "bearer", expires_in, refresh_token: null}`
- **refresh_token is null** — seam for future refresh token support

Used by:
- Browser SPAs with a dockmaster session (from auth code flow)
- CLI `dockmaster token <service>` command

### 5. Grants Endpoint

New endpoint: `GET /auth/grants`

- **Auth:** Type A SA JWT (same as `/auth/has`)
- **Query params:** `subject`, `target`
- **Returns:** `{subject, target, grants: ["service:perm", ...]}`
- **Resolves:** Loads service grants from RBAC storage, resolves roles → permissions,
  returns flat `service:permission` list

Complements `/auth/has` (single permission check) with a bulk grants lookup.

### 6. Exchange Endpoint Update

Modify: `src/dockmaster/routes/exchange.py`

- Switch signing from `ServiceUser` (Type B) to `DockTokenIssuer` (Type C)
- Same input: Type A SA JWT with subject + service params
- Output: Type C JWT (ephemeral-signed, `iss: "dockmaster"`)
- No breaking changes to the API contract — just the token format changes

### 7. Auth Code Flow

New module: `src/dockmaster/auth/auth_code.py` (or extend login routes)

**Components:**

**a. Auth code store** (in-memory):
- Maps code → `{subject, redirect_uri, created_at}`
- Codes are single-use, expire after ~5 minutes
- Codes are cryptographically random (e.g. `secrets.token_urlsafe(32)`)

**b. Redirect URI allowlisting:**
- New setting: `ALLOWED_REDIRECT_URIS` (comma-separated, parsed to `set[str]`)
- Extend `_validate_redirect_uri()` in login routes to check against this allowlist
  (in addition to existing localhost validation for CLI)

**c. Updated `/auth/callback`:**
- When `redirect_uri` is an allowlisted external URI (not localhost):
  - Generate auth code
  - Redirect to `{redirect_uri}?code={code}&state={state}`
- When `redirect_uri` is localhost (CLI flow):
  - Keep current behavior (mint Type C JWT directly, redirect with token)

**d. New endpoint: `POST /auth/code/exchange`:**
- **Auth:** None (the code itself is the credential)
- **Input:** `{code, redirect_uri}`
- **Validates:** code exists, not expired, not used, redirect_uri matches
- **Returns:** `{access_token, token_type, expires_in, refresh_token: null}`
- **Signs:** Type C JWT with `DockTokenIssuer`

### 8. ServiceRealm Extension

Modify: `src/dockmaster/auth/key_cache.py` (or `ServiceRealm`)

- Add ephemeral public keys from `KeyManager` to the key lookup
- `ServiceRealm.verify()` already does kid-based lookup — just needs to find ephemeral
  keys alongside GCP SA keys
- **Approach:** Either inject ephemeral keys into `ServiceAccountKeyCache`, or give
  `ServiceRealm` a second key source. TBD during implementation.

### 9. CLI `token` Command

New module: `src/dockmaster/cli/token.py`

- `dockmaster token <service>` (positional arg)
- Loads stored CLI credentials (from `dockmaster login`)
- Calls `POST /auth/token?service=<service>` with Bearer auth
- Prints the Type C JWT to stdout
- Exit 1 if not logged in or token request fails

Register in `src/dockmaster/cli/main.py`.

### 10. CORS Middleware

Modify: `src/dockmaster/main.py`

- Add `CORSMiddleware` from Starlette
- New setting: `ALLOWED_ORIGINS` (comma-separated, parsed to `set[str]`)
- Apply to endpoints that browser SPAs call cross-origin:
  - `POST /auth/code/exchange`
  - `POST /auth/token`
  - `GET /.well-known/jwks.json`
  - `GET /.well-known/openid-configuration`
- Allow headers: `Authorization`, `Content-Type`
- Allow methods: `GET`, `POST`
- Allow credentials: `True`

### 11. OIDC Discovery Endpoint

New route (in JWKS route module or standalone).

- `GET /.well-known/openid-configuration`
- Public endpoint — no authentication required
- Returns static JSON with endpoint locations

```json
{
  "issuer": "dockmaster",
  "jwks_uri": "/.well-known/jwks.json",
  "token_endpoint": "/auth/token",
  "authorization_endpoint": "/auth/login",
  "grant_types_supported": ["authorization_code"],
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

### 12. Settings

New settings in `src/dockmaster/config.py`:

| Setting | Type | Default | Description |
|---|---|---|---|
| `DOCKMASTER_TOKEN_TTL` | `int` | `900` (15min) | Default TTL for Type C JWTs |
| `ALLOWED_REDIRECT_URIS` | `str \| set[str]` | `set()` | Comma-separated allowlist of external redirect URIs |
| `ALLOWED_ORIGINS` | `str \| set[str]` | `set()` | Comma-separated CORS allowed origins |
| `JWKS_REGISTRY_PATH` | `str \| None` | `None` (platformdirs default) | Override path for JWKS public key registry file |

### 13. Lifespan Wiring

Modify: `src/dockmaster/main.py`

- Initialize `KeyManager` (generates keypair, loads/updates registry)
- Initialize `DockTokenIssuer` with `KeyManager`
- Attach both to `app.state`
- Register JWKS routes (including `/.well-known/jwks.json` without `/auth` prefix)
- Extend `ServiceRealm` key cache to include ephemeral public keys

### 14. Testing Approach

| Module | Approach | Key test cases |
|---|---|---|
| `KeyManager` | TDD | Key generation, JWK export, registry persistence, key pruning |
| `DockTokenIssuer` | TDD | Token signing, claims validation, TTL, kid in header |
| JWKS endpoint | Unit | Response format, both paths serve same data, no auth required |
| `/auth/grants` | TDD | Grants resolution, Type A auth required, unknown subject/target |
| `/auth/token` | Unit | Session auth, CLI auth, missing service param, response format |
| Auth code flow | TDD | Code generation, expiry, single-use, redirect_uri validation |
| `/auth/code/exchange` | Unit | Valid exchange, expired code, wrong redirect_uri, replay |
| Exchange update | Unit | Returns Type C (not Type B), claims format, iss = "dockmaster" |
| CLI `token` | Unit | Happy path, not logged in, service arg |
| ServiceRealm extension | Unit | Verifies both SA and ephemeral JWTs by kid |
| OIDC discovery | Unit | Response format, correct endpoint URLs |
| CORS | Unit | Allowed origins get CORS headers, others don't |

---

## Dependencies

- **Requires:** Phase 6c complete (CLI infrastructure, redirect_uri on `/auth/login`)
- **Enables:** Middleware templates, additional SSO providers, refresh tokens

## Open Questions

All questions from the senior review have been resolved. No open questions remain.

## Senior Review Decisions

Review completed 2026-03-13. Key items and resolutions:

| # | Review Item | Resolution |
|---|---|---|
| R1 | Issuer format (`dockmaster` vs URL) | Keep `dockmaster` for now. Move to URL-based issuer when needed for OIDC compat. |
| R2 | CORS for SPA-direct flow | Added to Phase 7 scope: `ALLOWED_ORIGINS` setting + CORS middleware. |
| R3 | Forward auth (Caddy pattern) | Rejected. Auth stays in dockmaster code, not Caddy config. Testable > configurable. |
| R4 | Private key persistence | Keep ephemeral (RAM only). Public key registry handles cross-restart verification. Restart impact acceptable for single-instance. |
| R5 | Session persistence (InMemorySessionStore) | Accepted as-is. Redis-backed sessions is a known future item when scale demands it. |
| R6 | Runtime dependency bottleneck (/has latency) | Cache-Control headers and consumer-side caching noted for middleware templates planning. Not a dockmaster code change. |
| R7 | Service-to-service without user context | Noted for middleware templates. Middleware must distinguish Type A (system) vs Type C (user) tokens. Not a dockmaster change. |
| R8 | OIDC discovery endpoint | Added to Phase 7 scope: `/.well-known/openid-configuration`. |
| R9 | Admin UI CSRF protection | Deferred to Phase 8 auth audit. Same-origin + SameSite=lax is sufficient for now. |

## Acceptance Criteria

- [ ] Dockmaster generates ephemeral RSA keypair at startup (private key never on disk)
- [ ] `/.well-known/jwks.json` serves public keys
- [ ] `/.well-known/openid-configuration` serves OIDC discovery metadata
- [ ] All dockmaster-issued tokens are Type C (ephemeral-signed, `iss: "dockmaster"`)
- [ ] `/auth/exchange` returns Type C tokens
- [ ] `/auth/token` endpoint: session or CLI auth → Type C JWT for target service
- [ ] `/auth/grants` endpoint: Type A auth → resolved grants for subject+target
- [ ] Auth code flow: redirect URI allowlisting, code generation, code exchange
- [ ] CLI `dockmaster token <service>` command works
- [ ] `ServiceRealm` verifies both SA and ephemeral JWTs
- [ ] Public key registry survives restarts (tokens from previous key remain verifiable)
- [ ] CORS middleware configured for cross-origin SPA access
- [ ] All existing tests pass (no regressions)
- [ ] New tests for all Phase 7 modules

---

## Planning References

- `_blueprint/features/planning/phase7-auth-flows-analysis.md` — flow diagrams, token lifecycle,
  latency estimates, decision log (D21–D40)
- `_blueprint/archive/features/[completed]-research-phase7-rsa256-keypair.md` — original research notes

## Future Roadmap (noted, not Phase 7 scope)

- Refresh tokens for dockmaster-issued JWTs
- Grants-in-JWT option (`include_grants=true` on token endpoint)
- SM-backed redirect URI storage + admin UI management
- Optional SA JWT authentication on code exchange (extra security for backend services)
- URL-based issuer (`iss: "https://auth.mydomain.com"`) for full OIDC compat
- Redis-backed session persistence (when scale demands it)
- Admin UI CSRF tokens (Phase 8 audit)
- Cache-Control headers on `/has` and `/grants` responses
- Middleware templates / SDK for downstream integration (FastAPI, Flask, Next.js, etc.)
  - Must handle Type A (system) vs Type C (user) token distinction
  - Should include consumer-side permission caching (60s recommended)
- Additional SSO providers beyond Google
