---
state: Draft
changelog:
  "2026-03-13 16h": "Major corrections — Type C everywhere, unified SA auth, /grants endpoint, SPA-direct flow"
  "2026-03-13 15h": "Comprehensive update — token lifecycle, latency estimates, updated Flow 2/4 diagrams"
  "2026-03-13 14h": "Initial auth flow analysis from planning interview"
---

# Phase 7 — Auth Flows Analysis

Visual reference for the four auth flows, token types, lifetimes, and latency in dockmaster.

---

## The Two JWT Types (Post Phase 7)

After Phase 7, there are only two JWT types. Type B (SA-signed dockmaster JWT) is fully replaced by Type C.

| | Type A: GCP SA JWT | Type C: Dockmaster JWT (Phase 7) |
|---|---|---|
| **Signed by** | GCP SA private key (on disk) | Ephemeral RSA key (RAM only) |
| **Verified by** | GCP SA public key (Google IAM API) | Ephemeral public key (JWKS endpoint) |
| **`kid`** | SA key ID from key file | Dockmaster-generated (e.g. `dk-2026-03-13-a1b2c3`) |
| **`iss`** | SA email (e.g. `my-sa@project.iam.gserviceaccount.com`) | `dockmaster` |
| **Claims** | `sub`, `email`, `aud`, `iat`, `exp` | `sub`, `email`, `aud`, `iat`, `exp`, `kid` |
| **Purpose** | "I am this service" — machine identity | "Dockmaster vouches for this user" — user identity |
| **Who creates** | Any service with a GCP SA key file (`ServiceUser`) | Dockmaster `DockTokenIssuer` (new) |
| **Who verifies** | Dockmaster (`ServiceRealm` + `ServiceAccountKeyCache`) | Anyone (fetch JWKS, no GCP needed) |
| **Lifetime** | ~1 hour (convention). Service self-signs new ones (<1ms). | `DOCKMASTER_TOKEN_TTL` (default 15min, configurable) |

### What changed from Type B → Type C

| | Type B (current, being replaced) | Type C (Phase 7) |
|---|---|---|
| Signing key | GCP SA private key (on disk) | Ephemeral RSA key (in RAM only) |
| If SA key leaks | Attacker can forge user JWTs | Attacker gets GCP access but **cannot** forge user tokens |
| Verification | Need GCP IAM API access | Just fetch JWKS endpoint (HTTP) |
| Provider coupling | Tied to Google SA identity | Provider-agnostic (`iss: dockmaster`) |

---

## Token & Session Lifecycle

All tokens and sessions in the system, their lifetimes, and what happens on expiry.

| Token/Session | Lifetime | Storage | On expiry | Who refreshes |
|---|---|---|---|---|
| **Google OAuth session** (browser ↔ Google) | Until user logs out of Google | Google manages | Google SSO prompt (may be seamless if still logged in) | User re-authenticates |
| **Dockmaster session cookie** | `SESSION_TTL` (configurable, e.g. 24h) | `InMemorySessionStore` (server) + signed cookie (browser) | Redirect to `/auth/login` → Google OAuth | User re-authenticates via Google |
| **Google refresh token** | Long-lived (months, until revoked) | Dockmaster stores during `/auth/refresh` flow | User must re-authenticate via full OAuth flow | N/A — it IS the refresh mechanism |
| **Type A: SA JWT** | ~1 hour (convention, configurable) | In-memory (service generates on demand) | Service generates a new one instantly (<1ms, no network) | Service self-signs with SA key |
| **Type C: Dockmaster JWT** | `DOCKMASTER_TOKEN_TTL` (default 15min, configurable) | Consumer stores (SPA memory, CLI local file, etc.) | Re-request via existing auth (see below) | Depends on consumer |
| **Auth code** (Phase 7) | Very short-lived (~5 min, single-use) | Dockmaster in-memory | Invalid — consumer must restart auth flow | N/A — single use |

### How each consumer refreshes a Type C JWT

| Consumer | Their existing auth | How they get a new Type C JWT | User experience |
|---|---|---|---|
| **CLI** | Stored CLI credentials (from `dockmaster login`) | Run `dockmaster token <service>` again → `POST /auth/token` | Transparent (if CLI creds valid). If expired → `dockmaster login` |
| **Browser SPA (with backend)** | Dockmaster session (from auth code flow) | Backend calls `POST /auth/token?service=X` | Transparent (if session valid). If expired → re-redirect through OAuth |
| **Browser SPA (no backend)** | Auth code flow | Re-redirect user through dockmaster → Google OAuth | If dockmaster session active → seamless (no Google prompt). Otherwise → Google login |
| **Backend service** | SA key file (on disk, long-lived) | `POST /auth/exchange` with new Type A JWT | Fully automatic — service self-signs Type A instantly |

---

## Latency Estimates Per Operation

### One-time setup costs (cached afterward)

| Operation | Latency | When it happens | Cache duration |
|---|---|---|---|
| Fetch JWKS from dockmaster | ~5-50ms (local network) | First JWT verification by downstream service | Service caches JWKS (refresh on kid miss or TTL) |
| Fetch GCP SA public keys | ~100-300ms (Google IAM API) | Dockmaster startup / key cache miss | `ServiceAccountKeyCache` TTL (300s default) |
| Generate ephemeral RSA keypair | ~50-200ms | Dockmaster startup only | Lifetime of process |

### Per-request costs

| Operation | Latency | Notes |
|---|---|---|
| **Sign a Type A JWT** (SA key → JWT) | **<1ms** | Pure CPU: RSA sign with key already in memory. No network call. Service does this locally. |
| **Sign a Type C JWT** (ephemeral key → JWT) | **<1ms** | Same — RSA sign with key in memory. Dockmaster does this. |
| **Verify a JWT** (any type, key cached) | **<1ms** | Pure CPU: RSA verify with cached public key. No network call. |
| **Verify a JWT** (key cache miss) | **100-300ms** | Fetches public key from Google IAM (Type A) or JWKS endpoint (Type C), then caches. Rare. |
| **`/auth/exchange`** (Type A → Type C) | **~5-15ms** | Verify Type A (<1ms) + sign Type C (<1ms) + HTTP overhead. |
| **`/auth/token`** (session → Type C) | **~2-10ms** | Session lookup (in-memory) + sign Type C (<1ms). Very fast. |
| **`/auth/has`** (single permission check) | **~10-50ms** | Verify Type A + load RBAC from SM cache (in-memory if cached, ~200ms on cache miss). RBAC cache TTL is 300s. |
| **`/auth/grants`** (all grants for user+service) | **~10-50ms** | Verify Type A + resolve all grants for target service. Same RBAC lookup as `/has`. |
| **`/auth/code/exchange`** (auth code → Type C) | **~2-10ms** | Look up code (in-memory) + sign Type C (<1ms). |
| **Google OAuth redirect flow** | **1-5 seconds** | User-facing: browser redirects to Google, user authenticates, Google redirects back. One-time per session. |

### Key takeaway: SA JWT for permission calls is NOT slow

**Q: Does the service make a new Type A JWT for every `/has` or `/grants` call?**

No — and even if it did, signing a JWT is <1ms (pure CPU, no network). In practice, a service would:
1. Generate one Type A JWT at startup or on first request (valid for ~1 hour)
2. Reuse it for all dockmaster calls until it expires
3. Generate a new one when the old one expires (<1ms, no network)

The permission check itself is ~10-50ms depending on RBAC cache state. The SA JWT auth overhead is negligible.

---

## The Four Auth Flows (Phase 7 Proposed)

### Flow 1: Dockmaster Admin

Admin users manage RBAC via CLI or Admin UI.

```
CLI flow:
  admin user
       |
       |-- dockmaster login ---------> dockmaster
       |   (opens browser)                |
       |                            Google OAuth (~2-5s, one-time)
       |                                  |
       |<-- Type C JWT (15min) -----------|
       |   (stored locally via            |
       |    platformdirs)                 |
       |                                  |
       |-- dockmaster role list --------->|  (~5-15ms)
       |   Authorization: Bearer <Type C> |
       |                                  | require_admin_api
       |<-- role data --------------------|

Admin UI flow:
  admin user (browser)
       |
       |-- GET /ui/login -------------> dockmaster
       |                                  |
       |                            Google OAuth (~2-5s, one-time)
       |                                  |
       |<-- session cookie ---------------|
       |   (SESSION_TTL, e.g. 24h)        |
       |                                  |
       |-- GET /ui/roles --------------->|  (~5-15ms)
       |   Cookie: session_id             |
       |                                  | require_admin_ui
       |<-- HTML (roles page) -----------|
```

**Status:** Mostly built (Phase 6/6c). Phase 7 change: CLI login returns Type C JWT (was Type B).

### Flow 2: Service-to-Service

Backend service receives user requests and checks permissions via dockmaster.

**Two sub-scenarios depending on whether the service already has a user token.**

```
Flow 2a: Service already has user's Type C JWT (e.g. from SPA Authorization header)

  SPA frontend              billing-service               dockmaster
       |                        |                            |
       |-- POST /api/invoices ->|                            |
       |   Auth: Bearer         |                            |
       |   <user's Type C JWT>  |                            |
       |                        |                            |
       |                   billing-service:                   |
       |                   1. verify Type C (JWKS, <1ms)     |
       |                   2. extract sub (nick@example.com) |
       |                   3. check permissions:              |
       |                        |                            |
       |                        |-- GET /auth/has ---------->|  (~10-50ms)
       |                        |   /nick@.../billing/write  |
       |                        |   Auth: Bearer <Type A>    |
       |                        |   (service's own SA JWT,   |
       |                        |    reused ~1hr)            |
       |                        |                            | verify Type A (<1ms)
       |                        |                            | check RBAC (cached)
       |                        |<-- 204 (granted) ----------|
       |                        |                            |
       |<-- 201 Created --------|                            |

  Alternative: /grants for complex permission logic

       |                        |-- GET /auth/grants ------->|  (~10-50ms)
       |                        |   ?subject=nick@...        |
       |                        |   &target=billing-service  |
       |                        |   Auth: Bearer <Type A>    |
       |                        |                            |
       |                        |<-- {subject, target,       |
       |                        |     grants: [              |
       |                        |       "billing:read",      |
       |                        |       "billing:write"      |
       |                        |     ]}                     |
       |                        |                            |
       |                   billing-service:                   |
       |                   check grants locally for          |
       |                   multiple permissions at once      |
```

```
Flow 2b: Service acts on behalf of user (no Type C JWT available)
         e.g. background job, cron task, service-initiated action

  billing-service               dockmaster
       |                            |
       |== STEP 1: Get Type C JWT on behalf of user ==
       |                            |
       |-- POST /auth/exchange ---->|  (~5-15ms)
       |   Auth: Bearer <Type A>    |
       |   ?service=billing-service |
       |   ?subject=nick@example.com|
       |                            | verify Type A (<1ms)
       |                            | check domain/issuer
       |                            | sign Type C (<1ms)
       |<-- Type C JWT -------------|
       |   sub: nick@example.com    |
       |   aud: billing-service     |
       |   iss: dockmaster          |
       |                            |
       |== STEP 2: Check permissions (same as 2a) ==
       |                            |
       |-- GET /auth/has ---------->|  (~10-50ms)
       |   /nick@.../billing/write  |
       |   Auth: Bearer <Type A>    |
       |<-- 204 (granted) ----------|
```

**Key points:**
- All service → dockmaster calls use **Type A SA JWT** for auth (one pattern)
- `/auth/has` and `/auth/grants` both require Type A auth
- `/auth/exchange` is for when a service needs a Type C token (to pass to other services or return to a caller) — not needed just for permission checks

### Flow 3: External SPA Browser Login (with backend)

End user on an external SPA authenticates via Google SSO through dockmaster.
The SPA has a backend server that handles the callback and token exchange.

```
  user browser              SPA backend                  dockmaster
       |                    (inventory.app)                  |
       |                        |                            |
       |-- clicks "Login" ----->|                            |
       |                        |                            |
       |<-- 302 redirect -------|                            |
       |   to dockmaster/auth/login?                         |
       |   redirect_uri=https://inventory.app/callback       |
       |                        |                            |
       |-- GET /auth/login ------------------------------------>|
       |                                                     |
       |                                                     | validate redirect_uri
       |                                                     |   against ALLOWED_REDIRECT_URIS
       |                                                     | generate CSRF state
       |                                                     |
       |<-- 302 to Google OAuth -----------------------------|  (~2-5s user-facing)
       |                                                     |
       |-- Google login (SSO, may be seamless) ------------->|
       |                                                     |
       |<-- 302 to /auth/callback --------------------------|
       |                                                     |
       |                                                dockmaster:
       |                                                - exchange code with Google
       |                                                - verify id_token
       |                                                - check domain
       |                                                - generate auth code (single-use, ~5min)
       |                                                - create dockmaster session
       |                                                     |
       |<-- 302 to inventory.app/callback?code=XYZ ----------|
       |                        |                            |
       |-- GET /callback ------>|                            |
       |   ?code=XYZ            |                            |
       |                        |-- POST /auth/code/exchange ->|  (~2-10ms)
       |                        |   {code: XYZ,              |
       |                        |    redirect_uri: https://  |
       |                        |    inventory.app/callback}  |
       |                        |                            | validate code + redirect_uri
       |                        |                            | sign Type C (<1ms)
       |                        |<-- response ---------------|
       |                        |   {access_token: "eyJ...", |
       |                        |    token_type: "bearer",   |
       |                        |    expires_in: 900,        |
       |                        |    refresh_token: null}     |
       |                        |                            |
       |<-- SPA stores JWT -----|                            |
       |   (httpOnly cookie     |                            |
       |    set by backend)     |                            |
```

**Token refresh:** When the Type C JWT expires (15min), the SPA backend can re-redirect the user through dockmaster. If the dockmaster session is still active (`SESSION_TTL`), the Google OAuth step is skipped — dockmaster issues a new auth code immediately. The user sees a brief redirect flash (~100ms), not a full Google login.

**Integration pattern:** The SPA backend needs a small set of standard routes:
- `GET /callback` — receives auth code from dockmaster, exchanges for Type C JWT, stores it
- `GET /login` — redirects to dockmaster with its redirect_uri
- `GET /logout` — clears stored JWT

This is what future middleware templates / SDK will provide as a guide or package.

### Flow 3b: External SPA Browser Login (no backend — SPA-direct)

SPA runs entirely in the browser. No backend server.
The SPA itself handles the callback and calls services directly.

```
  user browser (SPA)                                 dockmaster
       |                                                 |
       |-- clicks "Login"                                |
       |   (SPA JS redirects to)                         |
       |                                                 |
       |-- GET /auth/login ------------------------------>|
       |   ?redirect_uri=https://myapp.com/callback      |
       |                                                 |
       |                                                 | validate redirect_uri
       |                                                 |
       |<-- 302 to Google OAuth -------------------------|  (~2-5s user-facing)
       |                                                 |
       |-- Google login --------------------------------->|
       |                                                 |
       |<-- 302 to /auth/callback -----------------------|
       |                                                 |
       |                                            dockmaster:
       |                                            - verify Google token
       |                                            - generate auth code
       |                                                 |
       |<-- 302 to myapp.com/callback?code=XYZ ----------|
       |                                                 |
       |   SPA JS handles callback:                      |
       |                                                 |
       |-- POST /auth/code/exchange -------------------->|  (~2-10ms)
       |   {code: XYZ,                                   |
       |    redirect_uri: https://myapp.com/callback}    |
       |                                                 | validate code
       |                                                 | sign Type C
       |<-- {access_token, expires_in, ...} -------------|
       |                                                 |
       |   SPA stores Type C JWT in memory               |
       |   (NOT localStorage — security)                 |
       |                                                 |
       |   SPA can now call services directly:           |
       |                                                 |
       |-- POST https://billing-api.com/invoices --------|-------> billing-service
       |   Authorization: Bearer <Type C JWT>            |              |
       |                                                 |         verify via JWKS
       |                                                 |         check via /has
       |<-- 201 Created ---------------------------------|---------|
```

**Key differences from Flow 3 (with backend):**
- The SPA's JavaScript makes the `/auth/code/exchange` call directly (requires CORS on dockmaster)
- Type C JWT is stored in JS memory (lost on page refresh — acceptable for short-lived tokens)
- SPA calls backend services directly with the Type C JWT
- No server-side token storage

**CORS requirement:** Dockmaster needs to allow CORS from configured origins for the `/auth/code/exchange` endpoint (and potentially `/auth/token`).

### Flow 4: External SPA API Calls

This flow is the same regardless of whether the SPA has a backend or not.
The SPA has a Type C JWT (obtained via Flow 3 or 3b) and calls backend services.

```
  user browser              SPA (frontend)           billing-service API         dockmaster
       |                        |                        |                        |
       |-- clicks "Create       |                        |                        |
       |   Invoice" ----------->|                        |                        |
       |                        |                        |                        |
       |                        |-- POST /api/invoices ->|                        |
       |                        |   Authorization:       |                        |
       |                        |   Bearer <Type C JWT>  |                        |
       |                        |                        |                        |
       |                        |                   billing-service:              |
       |                        |                   1. verify Type C JWT          |
       |                        |                      (JWKS cached, <1ms)       |
       |                        |                   2. extract sub (email)        |
       |                        |                                                |
       |                        |                   Permission check              |
       |                        |                   (one of two patterns):        |
       |                        |                                                |
       |                        |                   GET /auth/has/ ------------->|  (~10-50ms)
       |                        |                     nick@../billing/write      |
       |                        |                     Auth: Bearer <Type A>      |
       |                        |                   → 204 or 403       <---------|
       |                        |                                                |
       |                        |                   — OR —                       |
       |                        |                                                |
       |                        |                   GET /auth/grants ----------->|  (~10-50ms)
       |                        |                     ?subject=nick@..           |
       |                        |                     &target=billing            |
       |                        |                     Auth: Bearer <Type A>      |
       |                        |                   → {grants: [...]}  <---------|
       |                        |                   check locally                |
       |                        |                                                |
       |                        |                   5. process request            |
       |                        |<-- 201 Created --------|                        |
       |<-- "Invoice created" --|                        |                        |
```

**Latency breakdown for a typical SPA → backend API call:**
- JWT verification: <1ms (JWKS cached)
- Permission check via `/has` or `/grants`: ~10-50ms (one network call to dockmaster)
- **Total auth overhead: ~10-50ms per request**

---

## Permission Check Endpoints — Unified Auth Pattern

**Both endpoints require Type A SA JWT authentication.** This proves the calling service is authorized and identifies which service is asking.

| Endpoint | Auth | Input | Output | Use case |
|---|---|---|---|---|
| `GET /auth/has/{subject}/{target}/{permission}` | Type A SA JWT | subject, target, permission in URL | 204 (granted) / 403 (denied) | Simple single-permission gate |
| `GET /auth/grants?subject=X&target=Y` | Type A SA JWT | subject + target as query params | `{subject, target, grants: ["svc:perm", ...]}` | Complex authz logic, load all permissions at once |

### Endpoint vocabulary

```
Browser user:     /principal     → "who am I?"       (session-based, cookie auth)
Service + JWT:    /claims        → "who is this?"    (raw JWT decode, Type A/C auth)
Service + SA:     /has           → "can they do X?"  (single permission, Type A auth)
Service + SA:     /grants        → "what can they do?" (all grants, Type A auth) [NEW Phase 7]
```

---

## Decisions Made So Far

| # | Decision | Rationale |
|---|---|---|
| D21 | Both capabilities (keypair + redirect) equally important | Keypair decouples auth from Google; redirect enables microservice integration |
| D22 | Public key registry persisted via platformdirs JSON file | Simple, local, sensible defaults |
| D23 | Redirect URIs configured via env var (start), SM + admin UI (future) | Start simple, extend later |
| D24 | Dockmaster-issued JWTs carry identity only (no embedded grants) | Matches legacy pattern; permissions checked via /has or /grants endpoints |
| D25 | Lightweight auth code flow (no client registration/scopes) | Internal services, RBAC handles authorization |
| D26 | `GET /auth/grants` returns resolved grants for a subject+target | Replaces N × `/has` calls. Rich response for complex authz logic. |
| D27 | Redirect URI validation only for code exchange (no client secret) | Simple, SPAs + backends both work. Future: optional SA JWT for extra security |
| D28 | Both `/has` (simple) and `/grants` (rich) require Type A SA JWT auth | One auth pattern for all service → dockmaster calls. Service identity always known. |
| D29 | CLI `token` command: positional arg (`dockmaster token <service>`) | Matches existing CLI patterns |
| D30 | JWKS served at both `/.well-known/jwks.json` and `/auth/jwks` | Standard discovery + consistent URL namespace |
| D31 | Refresh tokens deferred — design seam in token response (`refresh_token: null`) | Keep Phase 7 focused, add refresh later |
| D32 | `/auth/exchange` switches from Type B (SA-signed) to Type C (ephemeral-signed) | Natural evolution, same flow, better security |
| D33 | `ServiceRealm` extended to verify both GCP SA keys and ephemeral keys | Single verification path, kid-based lookup handles both |
| D34 | No user-facing dockmaster UI login needed | Dockmaster UI is admin-only |
| D35 | Auth code flow for external SPA browser login | Standard OAuth2 pattern, most secure |
| D36 | Token endpoint (`POST /auth/token`) for browser + CLI token requests | Session or CLI auth → Type C JWT for target service |
| D37 | All service → dockmaster calls authenticated via Type A SA JWT | One pattern. Service identity always known. |
| D38 | Configurable token TTL (`DOCKMASTER_TOKEN_TTL`, default 15min) | Short-lived + refresh pattern handles staleness |
| D39 | Support both SPA-with-backend and SPA-direct (no backend) patterns | Different apps have different architectures. Auth code flow works for both. |
| D40 | Renamed `/auth/verify` → `/auth/grants` | Clearer name — endpoint resolves grants, not verifying a token |
| D41 | Keep `iss: "dockmaster"` (not URL-based) for now | Move to URL-based issuer when OIDC third-party compat needed |
| D42 | CORS middleware included in Phase 7 | `ALLOWED_ORIGINS` setting. Required for SPA-direct (Flow 3b) |
| D43 | No forward auth (Caddy) pattern | Auth stays in dockmaster code. Testable > configurable. |
| D44 | Ephemeral private key (RAM only) — no disk persistence | Public key registry handles cross-restart verification. Restart = brief disruption, self-healing. |
| D45 | Session persistence (Redis) deferred | InMemorySessionStore acceptable for single-instance. Redis when scale demands. |
| D46 | Permission caching deferred to middleware templates | Cache-Control headers + consumer-side caching are middleware template concerns |
| D47 | System-to-system calls (Type A without user) noted for middleware templates | Middleware must distinguish Type A (system) vs Type C (user) tokens |
| D48 | OIDC discovery endpoint included in Phase 7 | `/.well-known/openid-configuration` — standard, lightweight |
| D49 | Admin UI CSRF deferred to Phase 8 audit | Same-origin + SameSite=lax sufficient for now |

## Future Roadmap Items (noted, not Phase 7)

- Refresh tokens for dockmaster-issued JWTs
- Grants-in-JWT option (`include_grants=true` on token endpoint)
- SM-backed redirect URI storage + admin UI management
- Optional SA JWT authentication on code exchange
- URL-based issuer (`iss: "https://auth.mydomain.com"`) for full OIDC compat
- Redis-backed session persistence
- Admin UI CSRF tokens (Phase 8 audit)
- Cache-Control headers on `/has` and `/grants` responses
- Middleware templates / SDK for downstream integration (FastAPI, Flask, Next.js, etc.)
  - Must handle Type A (system) vs Type C (user) token distinction
  - Should include consumer-side permission caching (60s recommended)
- Additional SSO providers beyond Google
