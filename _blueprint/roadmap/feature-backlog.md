# Feature Backlog

Ideas and deferred features not yet scheduled for implementation. When an item is
committed, create a spec in [`_blueprint/features/`](../features/) and link it from
[`ROADMAP.md`](./ROADMAP.md).

*Last updated: 2026-03-13*

---

## Deferred Items (from Gap Analysis — 2026-03-09)

### CLI UX Refinement
- **Context**: Phase 6c CLI already uses named flags (`-p/--permission` for roles, `-r/--role` for grants) with positional args for subject/target (D14). The original concern about unintuitive positional-only args was partially addressed. Remaining UX considerations: interactive prompting for required args, a YAML/JSON config file approach for bulk operations, tab completion.
- **When**: Before the CLI is widely adopted by other developers or documented externally.
- **Options**: Interactive prompting, bulk YAML/JSON operations, shell completion via Typer.
- **Effort**: Small-Medium — Typer has built-in completion support; bulk ops require a new command or `--file` flag.

---

## Deferred Items (from Audit Polish — 2026-03-09)

### Key Cache Force-Refresh + Admin Invalidation
- **Context**: Phase 2 KeyCache uses TTL-only expiry. A compromised/revoked key stays valid until TTL expires. No mechanism to force-refresh or manually flush.
- **When**: When running in production with multiple users, or if key compromise becomes a concern.
- **Options**: Force-refresh on unknown `kid`, admin endpoint to flush cache, honor Google's `Cache-Control` headers.

### Rate Limiting on Public Endpoints
- **Context**: `/auth/key/{kid}` (Phase 2) and `/auth/exchange` (Phase 3) have no rate limiting. Exchange is the most attack-attractive endpoint.
- **When**: When the service is exposed to the public internet or has multiple users.
- **Scope**: Consider `slowapi` or similar middleware.

### Lightweight IAM Key Fetching (google-auth + REST)
- **Context**: Phase 2 uses `google-api-python-client` (~20MB) for IAM key listing. Could be replaced with `google-auth` + direct REST calls.
- **When**: If dependency size becomes a concern, or during a dependency audit.
- **Effort**: Medium — replace `googleapiclient.discovery.build('iam', 'v1')` with direct HTTP calls.

### Standard Error Response Schema
- **Context**: No consistent error response format across endpoints. JWT path returns `StatusResponse`, access token path returns `{"error": "..."}`. Both audits recommend standardization.
- **When**: Before building the client SDK, or when API consumers need predictable error handling.
- **Scope**: Define `{error: str, message: str, detail: dict}` schema, apply to all endpoints.

### Dual-Mode Fallback Refinement
- **Context**: Phase 3 exchange endpoint uses try-both strategy (JWT verification → tokeninfo fallback). If a JWT-shaped token fails verification, it still tries tokeninfo. Could be smarter: only fall back if the token doesn't look like a JWT.
- **When**: When security hardening is prioritized.
- **Effort**: Small — add a structural check before fallback.

### InMemorySessionStore Cleanup
- **Context**: Phase 4 `InMemorySessionStore` has no max-size protection. `list_all()` (Phase 4c) does lazy cleanup of expired sessions on access, which partially addresses accumulation. Still no periodic cleanup or max-size cap.
- **When**: If running multi-user or long-lived instances where memory growth is a concern.
- **Options**: Periodic cleanup task, max-size cap with LRU eviction, or just use Redis.

### Server-Side Refresh Token Storage
- **Context**: Phase 4 requires refresh tokens in the request body. An alternative is storing them in the server session so browser clients don't need to manage them.
- **When**: When building a more polished browser experience.
- **Effort**: Small — store refresh token in session during callback, retrieve on refresh.

### OAuth Redirect-Back for External SPAs + Open Redirect Prevention
- **Context**: Phase 6c added `redirect_uri` support on `/auth/login` — but only for localhost callbacks (CLI use case). The callback mints a short-lived JWT and redirects to the provided URI. For external SPAs, we need: (1) an allowlist of permitted redirect origins (per-service), (2) a token delivery mechanism suitable for browser clients (query param, fragment, or POST), (3) open redirect prevention. This is the "auth service as IdP" pattern.
- **Partial progress (Phase 6c)**: `redirect_uri` param accepted, localhost-only validation, JWT minting on callback. Server-side infrastructure exists — needs extension for non-localhost URIs.
- **Scheduled**: Phase 7 (Redirect URI + Ephemeral Keypair).
- **Planning needed**: Per-service redirect URI allowlist (Settings or SM?), token delivery mechanism for SPAs, PKCE for public clients.

### Wildcard Target Matching for RBAC
- **Context**: Phase 5 uses exact string matching for targets. Both audits recommend glob/wildcard support (e.g., `projects/*`). Legacy also uses exact match.
- **When**: When the RBAC system needs to support hierarchical resources.
- **Decision needed**: Matching algorithm — `fnmatch` (glob), regex, or prefix match. Does `*` match nested paths?

### Role Deletion Referential Integrity
- **Context**: Phase 6 `DELETE /admin/roles/{name}` deletes without checking if service grants reference the role. Subjects silently lose permissions.
- **When**: When multiple users manage RBAC and accidental deletion is a risk.
- **Options**: Block deletion if in use (409 Conflict), warn but allow, cascade revocation.

### ~~Admin UI — RBAC Management Pages~~ ✅ DONE
- **Resolved**: Phase 6 (COMPLETE). Admin UI pages for roles, grants, and sessions are live at `/ui/roles`, `/ui/grants`, `/ui/sessions`. Includes create/edit/delete forms, read-only mode when admin SA not configured.

### Distributed Cache Invalidation
- **Context**: Phase 6 clears the Authority cache on the instance handling the admin request. Other instances keep stale cache for up to TTL (300s).
- **When**: Multi-instance deployment behind a load balancer.
- **Options**: Redis Pub/Sub invalidation, shorter TTL, webhook-based invalidation.

### Direct Secret Manager CLI Access
- **Context**: Phase 6 CLI always goes through the API. The legacy CLI talked directly to Secret Manager using GCP credentials. Direct SM access bypasses API cache invalidation (split-brain risk).
- **When**: When operating without a running dockmaster API instance (emergency access, migration).

### Pagination on Admin List Endpoints
- **Context**: Phase 6 `GET /admin/roles` and `GET /admin/grants` return all data. No pagination.
- **When**: When the number of roles/grants grows large enough to matter.
- **Effort**: Small — add `?limit=` and `?offset=` query params.

### Observability (Structured Auth Logging + Metrics)
- **Context**: Both audits note no observability requirements in any phase spec. Phase 1 set up structlog, but later phases don't reference it.
- **When**: Before production deployment.
- **Scope**: Structured log events for every auth decision, metrics (token exchange rate, cache hit ratio, permission check latency), request tracing.

### Token Revocation Strategy
- **Context**: No mechanism to revoke a dockmaster JWT before it expires. A revoked user's JWT remains valid for up to 1 hour. Both audits flag this.
- **Decision**: Accept the 1-hour window for MVP. Options for later: shorter lifetimes (5-15 min) + forced refresh, revocation list, or accept the tradeoff.

### Integration Testing Strategy
- **Context**: Each phase has unit tests but no integration test strategy across phases (full OAuth flow, token exchange → permission check end-to-end).
- **When**: After Phase 5+ when the full pipeline exists.
- **Scope**: `tests/integration/` directory or documented integration test approach.

---

## Future Features

### User Whitelisting via Secret Manager
- **Context**: Currently access control is domain-level (`AUTHORIZED_DOMAINS`) + admin email list (`DOCKMASTER_ADMIN_EMAILS`). No per-user whitelist for non-admin users outside the authorized domain.
- **Approach**: Option B — SM-based allowed-users secret, admin-manageable via UI. Needs a proper design session to make it flexible (not just a flat list — consider groups, expiry, invitation flow).
- **When**: After core features are deployed and real multi-user access patterns emerge.
- **Planning needed**: Data model (flat list vs structured), admin UI for managing users, how it interacts with domain-level auth, invitation/onboarding flow.

---

## Previously Deferred Items

### Redis Session Store
- **Context**: Phase 4 ships with in-memory `SessionStore`. Redis implementation uses the same `SessionStore` protocol. Single Docker Compose instance is fine for now — in-memory store works since there's only one process.
- **When**: When multi-instance deployment is needed (load balancer, horizontal scaling).
- **Effort**: Small — implement `RedisSessionStore` against existing protocol.
- **Dependency**: `redis[hiredis]`
- **Note (2026-03-12)**: Also needed for session revocation to work across instances. Phase 6b session revocation works fine in-memory for single-instance. Phase 6b `revoke_sessions_by_email` uses list_all + filter + delete loop — Redis could optimize this with native SCAN+DEL or secondary index by email. Consider adding `delete_by_email(email) -> int` to the protocol when implementing Redis backend.

### FastHTML + MonsterUI Admin Dashboard Evaluation
- **Context**: Admin UI uses Jinja2 + Tailwind CSS (no HTMX). FastHTML+MonsterUI could provide a richer SPA-like experience with Python-only components.
- **When**: After Phase 6 ships and we have real usage feedback on the admin UI.
- **Decision needed**: Whether the Jinja2 + Tailwind approach is sufficient or warrants replacement.

### SecretManagerAsyncClient Evaluation
- **Context**: Currently using sync client with `run_in_executor` + TTL cache. Google may stabilize an async client.
- **When**: When google-cloud-secret-manager ships a stable async API, or if blocking calls become a performance bottleneck.
- **Decision needed**: Whether the async client is stable enough for production use.

### Client Library / Python SDK
- **Context**: Other services (behind dockmaster auth) need to call dockmaster APIs to verify tokens and check permissions.
- **When**: After Phase 5 when the full API surface is stable.
- **Scope**: Python package with `DockMasterClient` class — token exchange, permission checks, middleware integration.

### Deployment Guides
- **Context**: Need operational guides for various deployment targets.
- **When**: After Phase 5+ when the service is feature-complete enough to deploy.
- **Scope**: Docker standalone, GCP Cloud Run, Kubernetes (Helm chart), Caddy reverse proxy integration.

### Ephemeral Key Retention Tied to Token TTL
- **Context**: Phase 7 EphemeralKeyCache uses a fixed 12h retention for old public keys. Could optionally be configured to use `DOCKMASTER_TOKEN_TTL` as the retention period (with safety padding) for tighter key lifecycle management.
- **When**: If operational requirements demand tighter key hygiene or shorter retention windows.
- **Effort**: Small — `EphemeralKeyCache` already accepts `retention` param, just needs a setting to wire it.

### JWKS Endpoint + OIDC Discovery
- **Context**: Phase 7 spec included `GET /.well-known/jwks.json`, `GET /auth/jwks`, and `GET /.well-known/openid-configuration`. Deferred because: (1) consumers will use dockmaster's own SDK/middleware which calls `/auth/key/{kid}` directly, (2) serving SA keys in JWK format requires PEM→JWK conversion that no consumer needs today, (3) ephemeral-only JWKS would be incomplete.
- **When**: When external services need standard OIDC/JWT middleware integration (auto-discovery via JWKS URL).
- **Effort**: Small-Medium — ephemeral keys have JWK data natively, SA keys need PEM→JWK conversion. Consider adding `get_all_jwks()` to base `KeyCache` at that time.
- **Prerequisite**: Decide scope (ephemeral-only vs all keys) and whether to add JWK conversion to `KeyCache` base class.

### Middleware Consolidation
- **Context**: Middleware is currently spread across multiple locations: `SecurityHeadersMiddleware` in `middleware.py`, `CORSMiddleware` and `SessionMiddleware` configured inline in `main.py:create_app()`. Should consolidate all middleware into a single `middleware.py` module with consistent patterns. Additionally, Starlette's `SessionMiddleware` (which creates a separate `session` cookie) may no longer be needed — it was added for Authlib's OAuth state management, but OAuth CSRF state is now handled by `TTLStore` (S-005). Investigate whether Authlib still uses the Starlette session during token exchange; if not, remove `SessionMiddleware` and eliminate the dual-cookie architecture (S-012).
- **When**: Next code quality pass or before deployment.
- **Effort**: Small-Medium — move CORS/Session config into middleware module, test Authlib without SessionMiddleware.

### Vocab Unification: ServiceUser.get_token() vs JWTTokenIssuer.sign()
- **Context**: Two JWT signing classes exist with different method names: `ServiceUser.get_token(subject, service_name, expiry, payload)` and `JWTTokenIssuer.sign(subject, audience, ttl, extra_claims)`. Both do the same thing (sign a JWT), but the naming divergence adds cognitive load. Parameters also differ (`service_name` vs `audience`, `expiry` vs `ttl`, `payload` vs `extra_claims`).
- **When**: Phase 8a (Audit — Endpoint Inventory). Fits naturally into the naming consistency pass.
- **Effort**: Small — rename methods and params to a consistent convention, update all callers and tests.
- **Options**: (1) Unify both to `.sign()` with consistent param names, (2) keep `ServiceUser` as-is since it's legacy/GCP-facing, only document the mapping, (3) extract a shared `TokenSigner` protocol.

### Mid-Process Ephemeral Key Rotation
- **Context**: Phase 7 ephemeral keypair lives for the lifetime of the process. No mid-process rotation. For long-running instances, rotation would limit blast radius of a memory dump.
- **When**: When dockmaster runs as a long-lived process (weeks+) in production.
- **Effort**: Medium — JWTTokenIssuer.rotate() + EphemeralKeyCache.add_key() + background timer.
