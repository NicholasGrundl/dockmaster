---
state: Finalized
changelog:
  "2026-03-08 16h": "Initial audit of Phases 2-6 implementation plans, roadmap, decision log, and backlog"
---

# Audit: Phases 2–6 Implementation Plan

> Comprehensive review of the dockmaster auth microservice implementation plan
> covering JWT infrastructure, token exchange, OAuth login, RBAC, and management tooling.

**Auditor**: Claude (Opus 4.6)
**Date**: 2026-03-08
**Documents reviewed**:
- `_blueprint/roadmap/ROADMAP.md`
- `_blueprint/roadmap/decision-log.md` (12 decisions)
- `_blueprint/roadmap/feature-backlog.md` (5 deferred items)
- `_blueprint/features/phase2-jwt-infrastructure.md`
- `_blueprint/features/phase3-token-exchange.md`
- `_blueprint/features/phase4-oauth-login.md`
- `_blueprint/features/phase5-rbac.md`
- `_blueprint/features/phase6-rbac-management.md`

---

## Executive Summary

The plan describes a clean-room rebuild of an auth microservice across five phases (2–6), building on a completed Phase 1 scaffold. The architecture is sound: JWT signing/verification → token exchange → OAuth browser login → RBAC → management tooling. Each phase has clear deliverables, dependency chains, file structures, and acceptance criteria.

**Strengths:**
- Well-ordered phase dependencies — each phase builds on the previous without circular dependencies
- Legacy bugs are explicitly documented and scheduled for fix during rebuild
- Decision log captures rationale for all major choices (library selection, caching strategy, phase ordering)
- Backlog is realistic and properly deferred (Redis sessions, async Secret Manager, client SDK)
- Consistent spec format across all phases makes navigation easy

**Concerns:**
- Several security-critical design details are absent (CSRF, token revocation, key rotation, admin authorization)
- Secret Manager as a primary RBAC store is unusual and may hit scaling/cost issues
- All specs claim "no open questions" — this is premature; the audit below surfaces several
- Error handling, observability, and operational concerns are largely unaddressed
- The plan lacks integration test strategy across phases

---

## Phase 2: JWT Infrastructure

### What's In It

Core JWT signing (`ServiceUser`) and verification (`ServiceRealm`) using GCP service account RSA keys. A `KeyCache` abstraction with TTL-based public key fetching from both the IAM API and Google OIDC certs endpoint. FastAPI auth middleware (`get_current_user` dependency) and two introspection endpoints (`/auth/key/{kid}`, `/auth/claims`).

### Assessment

The design is straightforward and follows well-established JWT patterns. Separating signing and verification into distinct classes is clean. The KeyCache hierarchy with IAM and OIDC sources is correct for supporting both SA-issued and Google-issued tokens.

### Blind Spots & Questions

1. **Key rotation strategy is missing.** What happens when a GCP SA key is rotated? The KeyCache fetches keys on cache miss, which handles new keys. But what about *revoked* keys? If a key is compromised, you need to actively reject it even if it's in cache. The TTL cache alone doesn't handle this — a compromised key stays valid for up to TTL seconds. Consider:
   - Adding a cache-invalidation mechanism (e.g., a force-refresh endpoint or admin hook)
   - Honoring Google's `Cache-Control` headers from the OIDC certs endpoint instead of (or in addition to) a fixed TTL

2. **`/auth/key/{kid}` is an unauthenticated public key endpoint.** This is fine in principle (public keys are public), but the spec doesn't mention rate limiting. An attacker could enumerate key IDs. Is this a concern? Probably not, but worth a conscious decision.

3. **`/auth/claims` is described as "debug/introspection."** Is it intended for production use? If it's debug-only, it should be gated behind a config flag or only enabled in dev mode. Exposing decoded claims in production is an information disclosure surface.

4. **The middleware pseudocode shows `authorization: str = Header(...)`.** This will return a 422 (validation error) if the header is missing, not a 401. Consider using `Optional[str]` and raising `HTTPException(401)` explicitly, or using FastAPI's `HTTPBearer` security scheme which returns 403/401 properly and also integrates with OpenAPI docs.

5. **No mention of audience validation strategy.** `ServiceRealm` is supposed to verify audience, but where does the expected audience value come from? Is it the dockmaster service URL? A configured value? This needs to be explicit in Settings and documented.

6. **`google-api-python-client` is listed as a dependency for IAM key listing.** This is a heavy dependency (~20MB+ with transitive deps). Consider using `google-auth` + direct REST calls to the IAM API instead, or `google-cloud-iam`. The decision log mentions `google-auth` but the spec says `google-api-python-client` — which is it?

7. **No error handling spec.** What does `ServiceRealm` return/raise when verification fails? Expired token vs. invalid signature vs. unknown kid should produce different error responses. The acceptance criteria say "401 for invalid" but don't differentiate failure modes.

---

## Phase 3: Token Exchange

### What's In It

A `POST /auth/exchange` endpoint that accepts Google JWTs or access tokens, validates them, and issues dockmaster JWTs. Dual-mode: try JWT verification first, fall back to Google's `tokeninfo` API for access tokens. Includes the `can_issue` flag enforcement (legacy bug fix).

### Assessment

Dual-mode exchange is pragmatic — it supports both service-to-service (JWT) and browser-context (access token) flows without requiring callers to specify which type they're sending. The `can_issue` bug fix is well-documented.

### Blind Spots & Questions

1. **The tokeninfo API (`/oauth2/v1/tokeninfo`) is deprecated.** Google recommends using the v3 endpoint or the `oauth2.googleapis.com/tokeninfo` endpoint. The legacy code may have used v1, but since this is a clean-room rebuild, use the current API. Check Google's current documentation.

2. **Dual-mode creates an ambiguous security boundary.** If a JWT fails verification (e.g., expired signature), the fallback tries it as an access token via tokeninfo. But a malformed or expired JWT is not an access token — sending it to tokeninfo will just fail. The concern is: what if an attacker crafts a string that fails JWT parsing but is somehow valid as an access token? This is extremely unlikely with Google tokens, but the fallback logic should be explicit:
   - Try JWT decode → if it *looks like* a JWT (3 dot-separated base64 segments) but fails verification, return 401 immediately
   - Only fall back to tokeninfo if the token does *not* look like a JWT

3. **No rate limiting on `/auth/exchange`.** This is the most attack-attractive endpoint — it accepts external tokens and issues internal ones. Consider rate limiting per source IP or per subject.

4. **Profile claim forwarding is underspecified.** "Copy profile claims (name, picture, email, etc.)" — what is the complete list? What if a claim is missing? Are profile claims optional in the dockmaster JWT, or will missing claims cause downstream failures?

5. **Token lifetime for issued dockmaster JWTs is not specified here.** Phase 2 says "configurable token lifetime (default 1 hour)" for ServiceUser. Does the exchange endpoint use the same default? Should it be configurable separately (exchange tokens might warrant shorter lifetimes)?

6. **No response schema for error cases.** The spec shows the 200 response but doesn't define 401/403 response bodies. Consistent error response schemas across all endpoints should be defined early.

7. **`can_issue` flag logic is unclear.** The spec says the flag is "set based on domain/audience checks" but the actual conditions for `can_issue = True` vs `False` are not documented. What domains are authorized? What audiences? These presumably come from Settings, but the spec doesn't show the config variables.

---

## Phase 4: OAuth Login + Session

### What's In It

Browser-based Google OAuth2 login via Authlib (authorization code flow with PKCE). Three login endpoints (`/auth/login`, `/auth/callback`, `/auth/logout`), a refresh endpoint (`/auth/refresh`), pluggable `SessionStore` protocol with in-memory implementation, and a Jinja2+HTMX test UI. Two legacy bug fixes: `data=` vs `params=` for the token endpoint, and `can_issue` enforcement in refresh.

### Assessment

This is the most complex phase and the one most likely to have implementation issues. OAuth2 flows are notoriously tricky. Using Authlib is the right call — it handles PKCE, discovery, and token exchange correctly. The pluggable SessionStore protocol is well-designed.

### Blind Spots & Questions

1. **CSRF protection is not mentioned anywhere.** The OAuth2 `state` parameter provides CSRF protection for the authorization flow itself, but what about the other session-based endpoints? If sessions are cookie-based:
   - `/auth/logout` needs CSRF protection (logout CSRF is a real attack)
   - `/auth/refresh` needs CSRF protection
   - The admin UI (Phase 6) needs CSRF tokens on all forms
   - Consider using `SameSite=Lax` or `Strict` cookies, plus explicit CSRF tokens

2. **Session transport is not specified.** How does the session ID get to the browser? Cookie? If cookie:
   - What are the cookie attributes? (`HttpOnly`, `Secure`, `SameSite`, `Path`, `Domain`)
   - Is the session ID signed? (`itsdangerous` is listed as a dependency, suggesting yes, but the spec doesn't describe it)
   - What's the cookie name?

   If not cookie-based, how does the test UI maintain session state?

3. **`/auth/callback` does too many things.** It validates state, exchanges code for tokens, extracts claims, creates a session, issues a dockmaster JWT, and redirects. This should be broken into smaller functions for testability. The spec's file structure has `login.py` handling all three login endpoints — this could get large.

4. **Refresh token storage is not addressed.** The `/auth/refresh` endpoint accepts a refresh token in the request body. But:
   - Where is the refresh token stored on the client side? In the session? In a cookie? In localStorage (XSS risk)?
   - If the refresh token is in the session, why does the client need to send it in the request body?
   - If it's in the body, the client needs to persist it somewhere — the spec doesn't address this

5. **`/auth/refresh` calls Google's refresh endpoint directly.** But Authlib already has refresh token handling built in. Is there a reason to bypass Authlib for this? Using Authlib's `fetch_access_token(grant_type='refresh_token')` would be more consistent.

6. **InMemorySessionStore has no max-size protection.** "Lazy cleanup on access" means sessions only get cleaned up when accessed. If many sessions are created but never re-accessed, they accumulate forever. Add either:
   - A periodic cleanup task
   - A max-size cap with LRU eviction
   - Or just document this as acceptable for dev-only use

7. **The test UI serves at what path?** The spec mentions "test UI" but doesn't specify the route. If it's at `/`, it conflicts with the existing `GET /` endpoint from Phase 1. If it's at a different path, what path?

8. **No mention of redirect URI validation.** After OAuth callback, where does the user get redirected? Is the redirect target configurable? Open redirect vulnerabilities are common in OAuth implementations.

9. **The `client_secret` loading path is inconsistent.** The refresh endpoint spec says "Loads client secret from Secret Manager (or config for dev)" — but Secret Manager isn't introduced until Phase 5. During Phase 4, it should be config-only. This suggests either the Phase 4 spec is looking ahead, or there's a dependency ordering issue.

---

## Phase 5: RBAC

### What's In It

RBAC data model (Role, Grant, ServiceGrants as Pydantic models), GCP Secret Manager storage backend, permission resolution engine (Authority) with TTL-based in-memory caching, and two permission-check endpoints (`GET /auth/has/{subject}/{target}/{permission}` and query-param variant).

### Assessment

The data model is simple and workable for a small-scale system. The Authority class with TTL caching is a reasonable approach. However, this phase has the most significant architectural concerns.

### Blind Spots & Questions

1. **Secret Manager as an RBAC database is unconventional and potentially problematic.**
   - **Cost**: Secret Manager charges per access operation ($0.03/10K access operations, $0.06/10K admin operations). With multiple services checking permissions frequently, costs could add up. The TTL cache mitigates this, but cache misses after TTL expiry across multiple instances will generate bursts.
   - **Latency**: Secret Manager access latency is typically 50-200ms. Even with caching, cold starts and cache misses will cause visible latency spikes.
   - **Listing**: The spec needs to list all roles and all service grants. Secret Manager doesn't have efficient prefix-based listing — you'd need to list all secrets and filter client-side, or maintain a separate index.
   - **Versioning/Atomicity**: Updating a role requires reading, modifying, and writing a secret. There's no atomic compare-and-swap. Concurrent updates will cause data loss (last-write-wins).
   - **Size limits**: Secret Manager has a 64KB limit per secret version. A role with many grants or a service with many subjects could exceed this.

   **Question**: Was a lightweight database (SQLite, Firestore, Cloud SQL) considered? The decision log says "GCP Secret Manager backend" but doesn't compare it to alternatives. For an auth service that checks permissions on every request, a database is more natural than a secrets store.

2. **The `ServiceGrants` model conflates two concepts.** `roles: dict[str, str]` maps `subject_email → role_name`, but:
   - A subject might need multiple roles for the same service
   - The model doesn't capture who granted the role or when (no audit trail)
   - There's no way to set expiring grants (temporary access)

3. **Wildcard matching on targets is underspecified.** The spec says `"projects/*"` is supported, but:
   - What is the matching algorithm? Glob? Regex? Simple prefix?
   - Does `"projects/*"` match `"projects/foo/bar"` (nested) or only `"projects/foo"` (single level)?
   - Can you have `"projects/*/settings"` (interior wildcard)?
   - What about `"*"` (match everything)?

4. **The permission check endpoint returns 403 for "no permission."** This leaks information — it confirms that the subject and target exist. Consider returning 200 with `has_permission: false` for all cases, and reserve 403 for "you don't have permission to check permissions" (meta-permission). Or, if the endpoint is internal-only, document this as an accepted trade-off.

5. **Cache invalidation problem.** With a 300-second TTL:
   - Granting a new permission takes up to 5 minutes to take effect
   - Revoking a permission takes up to 5 minutes to take effect (security concern!)
   - There's no mechanism to force cache invalidation after an RBAC change

   Phase 6 adds CRUD endpoints for RBAC management, but those endpoints don't seem to invalidate the Authority cache. This needs to be explicit — when you `PUT /admin/roles/{name}`, the Authority cache must be invalidated.

6. **No authorization on the permission-check endpoints.** Who can call `GET /auth/has/{subject}/{target}/{permission}`? Anyone with a valid JWT? This means any authenticated user can check any other user's permissions — that's an information disclosure issue. Consider requiring either:
   - The caller's JWT subject matches the `subject` being checked, OR
   - The caller has an `admin` or `rbac:read` permission

7. **`run_in_executor` wrapping needs care.** The spec says Secret Manager calls are wrapped with `run_in_executor`, but:
   - Which executor? The default `ThreadPoolExecutor`? With how many threads?
   - If many concurrent requests trigger cache misses simultaneously, they'll all call Secret Manager in parallel via the executor. This could cause thundering herd on Secret Manager.
   - Consider a lock per cache key to prevent duplicate fetches (single-flight pattern)

8. **The `has_permission` resolution path is unclear.** The pseudocode shows: look up service grants → find subject's role → check role's grants. But:
   - How does the system know which "service" a subject belongs to? Is the service derived from the subject's email domain? Or does the caller specify it?
   - The endpoint path is `/auth/has/{subject}/{target}/{permission}` — there's no `service` parameter. So how does the Authority know which `ServiceGrants` to look up?

---

## Phase 6: RBAC Management + CLI

### What's In It

CRUD REST endpoints at `/admin/*` for roles and grants. A Typer CLI with subcommands for role management, service grant management, permission testing, and token generation. A Jinja2+HTMX admin dashboard. Two legacy bug fixes: revoke wildcard off-by-one and role remove ValueError.

### Assessment

This phase is well-scoped as a management layer on top of Phase 5. The three-interface approach (API, CLI, UI) sharing the same backend is clean. Typer is a good choice for the CLI.

### Blind Spots & Questions

1. **Admin endpoint authorization is critically underspecified.** The spec says "All endpoints require authentication (auth middleware from Phase 2)" — but authentication is not authorization. Who is allowed to:
   - Create/delete roles? Only super-admins? Any authenticated user?
   - Grant/revoke roles for a service? Only the service owner? Any admin?
   - View all roles and grants? Anyone authenticated?

   This is the most important security decision in the entire system and it's punted to "auth middleware." You need explicit authorization rules for admin endpoints, likely using the RBAC system itself (bootstrapping problem — see below).

2. **Bootstrapping problem.** If admin endpoints require RBAC permissions, and RBAC permissions are managed through admin endpoints, how do you create the first admin user? Options:
   - A seed/bootstrap command in the CLI that creates an initial admin role and grants it
   - A config-based super-admin email list that bypasses RBAC checks
   - First-run detection that grants admin to the first authenticated user

   This needs to be addressed in the spec.

3. **Route path collision between REST API and admin UI.** Both the CRUD endpoints and the admin UI are at `/admin/*`. How are they disambiguated? Content negotiation (Accept header)? Separate prefixes (`/admin/api/*` vs `/admin/*`)? The spec doesn't address this.

4. **CLI authentication.** The CLI needs to authenticate against the dockmaster API. How?
   - Does it use a service account key file? (likely, since `dockmaster token` generates JWTs)
   - Does it support OAuth login? (probably not needed for a CLI)
   - Where does it get the dockmaster API URL from? Environment variable? Config file?
   - The spec shows CLI commands but no connection/config subcommands

5. **Cache invalidation (again).** When the admin API creates/updates/deletes a role or grant, the Authority's TTL cache must be invalidated. This is not mentioned in the Phase 6 spec. Without it, CRUD operations appear to have no effect for up to 5 minutes.

6. **No pagination on list endpoints.** `GET /admin/roles` returns all roles. `GET /admin/grants` returns all service grants. For a small system this is fine, but the spec doesn't mention pagination, filtering, or max results. At minimum, document that these endpoints return all data and pagination is a future enhancement.

7. **The CLI `dockmaster token` command generates JWTs.** This is a powerful command — it can create tokens for any subject with any audience. Is there any access control on who can run this? If the CLI uses a SA key file, then anyone with the key file can generate tokens. This is expected for operators but should be documented as a security consideration.

8. **Admin UI CSRF protection.** The HTMX inline editing and deletion forms need CSRF tokens. HTMX can include CSRF tokens via `hx-headers`, but this needs to be wired up. This is related to the Phase 4 CSRF gap.

9. **No confirmation/soft-delete for destructive operations.** `DELETE /admin/roles/{name}` permanently deletes a role. If a role is in use by service grants, what happens? The spec doesn't address referential integrity — you could delete a role that subjects are still assigned, silently breaking their permissions.

---

## Cross-Cutting Concerns

These issues span multiple phases and are not addressed in any individual spec:

### 1. Error Response Schema
No consistent error response format is defined. Each phase mentions 401 or 403 but doesn't show the response body. Define a standard error schema early:
```json
{
  "error": "invalid_token",
  "message": "Token signature verification failed",
  "detail": { ... }
}
```

### 2. Observability
No mention of logging, metrics, or tracing in any phase spec. For an auth service, you want:
- Structured log events for every auth decision (permit/deny)
- Metrics: token exchange rate, cache hit ratio, permission check latency
- Request tracing (correlation IDs)
Phase 1 set up structlog, but none of the subsequent phases reference it.

### 3. Integration Testing
Each phase has unit test files but no integration test strategy. How do you test:
- The full OAuth flow (login → callback → session → refresh)?
- Token exchange → permission check (end-to-end)?
- CLI → API → Secret Manager?
Consider a `tests/integration/` directory or at least document the integration test approach.

### 4. Configuration Growth
Phase 1 established a `Settings` model. Phases 2–6 add many new config variables (`authorized_issuers`, `authorized_domains`, `authorized_audience`, `client_id`, `client_secret`, `RBAC_CACHE_TTL`, etc.). No spec shows the cumulative Settings model. There's a risk of the Settings class becoming unwieldy. Consider grouping settings into sub-models (e.g., `Settings.jwt`, `Settings.oauth`, `Settings.rbac`).

### 5. Deployment & Multi-Instance
The plan uses in-memory caching (KeyCache, Authority cache, InMemorySessionStore). In a multi-instance deployment:
- Each instance has its own cache, so TTL expiry is unsynchronized
- Session affinity is required for in-memory sessions (or sticky sessions via load balancer)
- Cache invalidation from admin API only affects the instance that handled the request
The backlog mentions Redis for sessions, but doesn't address the cache invalidation issue for RBAC data.

### 6. Token Revocation
There is no mechanism to revoke a dockmaster JWT before it expires. If a user's access is revoked via RBAC, their existing JWT remains valid until expiry. For a 1-hour default lifetime, that's a significant window. Options:
- Short token lifetimes (5-15 minutes) + forced refresh
- A revocation list (adds complexity but addresses the gap)
- Accept the window as a trade-off (document it)

### 7. Health Check Evolution
Phase 1 delivered `GET /auth/health`. As phases add dependencies (GCP IAM, Secret Manager, Google OAuth), the health check should evolve to include dependency status. None of the phase specs mention updating the health endpoint.

---

## Decision Log Assessment

The 12 decisions are well-documented with clear rationale. A few observations:

- **Decision quality is high.** Phase ordering rationale is sound. Library choices (PyJWT, Authlib, Typer) are mainstream and appropriate.
- **Missing decisions:**
  - Error response format standardization
  - Admin authorization policy (who can manage RBAC?)
  - CSRF strategy
  - Token revocation approach (or explicit acceptance of the gap)
  - Secret Manager vs. database for RBAC storage (trade-offs not documented)

## Feature Backlog Assessment

The five deferred items are appropriately scoped and prioritized:
- Redis sessions, async Secret Manager, and deployment guides are correctly deferred
- **The client library/SDK is more urgent than it appears.** If other services need to verify dockmaster JWTs and check permissions, they need *something* from day one. Even a simple example or documentation of "how to call `/auth/has`" would help.
- **FastHTML evaluation** is fine to defer but may never be needed if the Jinja2+HTMX UI meets requirements

---

## Conclusion

The plan is **well-structured and demonstrates clear architectural thinking**. The phase ordering is correct, the dependency chain is sound, and the decision log shows disciplined reasoning. The specs are consistent in format and level of detail, and the legacy bug fixes are well-documented.

However, the plan has **significant gaps in security design** that must be addressed before implementation:

1. **Admin authorization is the biggest gap.** An auth service without a clear policy for who can manage the auth rules is a critical omission. This includes the bootstrapping problem (first admin user) and the meta-permission question (who can check permissions).

2. **CSRF protection is absent.** For a service with browser-based login and session cookies, this is not optional.

3. **Cache invalidation across RBAC mutations is not wired up.** Without this, admin CRUD operations will appear broken for up to 5 minutes.

4. **Secret Manager as RBAC storage should be explicitly justified against database alternatives.** The current decision log states the choice without comparing trade-offs (cost, latency, atomicity, listing efficiency).

5. **Token revocation strategy needs a conscious decision**, even if that decision is "we accept the 1-hour window."

**Recommendations before starting Phase 2:**

| Priority | Action |
|----------|--------|
| **Must** | Define admin authorization policy and bootstrapping flow |
| **Must** | Add CSRF strategy to Phase 4 spec |
| **Must** | Add cache invalidation to Phase 6 spec (Authority cache clear on RBAC mutation) |
| **Should** | Standardize error response schema across all endpoints |
| **Should** | Decide on Secret Manager vs. database for RBAC (or document the trade-off analysis) |
| **Should** | Specify wildcard matching algorithm for targets |
| **Should** | Clarify session transport (cookie attributes, signing) |
| **Could** | Add observability requirements (structured auth logs, metrics) |
| **Could** | Define integration test strategy |
| **Could** | Consider shorter token lifetimes or revocation mechanism |

None of these gaps are fatal — they're the kind of details that often get resolved during implementation. But for a security-critical service, resolving them *before* writing code will prevent costly rework and security incidents. The specs would benefit from a "Security Considerations" section in each phase that explicitly addresses authentication, authorization, and abuse prevention for the endpoints being added.
