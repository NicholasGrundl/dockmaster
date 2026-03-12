# Feature Backlog

Ideas and deferred features not yet scheduled for implementation. When an item is
committed, create a spec in [`_blueprint/features/`](../features/) and link it from
[`ROADMAP.md`](./ROADMAP.md).

*Last updated: 2026-03-12*

---

## Deferred Items (from Gap Analysis — 2026-03-09)

### CLI UX Redesign
- **Context**: Phase 6 CLI uses positional arguments (`dockmaster service grant <service> <subject> <role1> [role2...]`). The argument order is functional but not intuitive — easy to misremember which position is service vs subject vs role. The legacy CLI had the same issue with its `subject:role1,role2` embedded-syntax approach.
- **When**: Before the CLI is widely adopted by other developers or documented externally.
- **Options**: Named flags (`--service`, `--subject`, `--role`), interactive prompting for required args, a YAML/JSON config file approach for bulk operations.
- **Effort**: Medium — Typer supports both positionals and named options; the underlying API calls don't change.

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
- **Context**: Currently the OAuth callback hardcodes redirect to `/ui/`. When dockmaster serves as the auth service for a separate SPA, we need to: (1) accept a `redirect_uri` or `return_to` param on `/auth/login`, (2) after successful auth, redirect back to the calling SPA with a token or code, (3) let the SPA handle its own routing. This is essentially the "auth service as IdP" pattern. Requires an allowlist of permitted redirect origins to prevent open redirect attacks.
- **When**: When an external frontend wants to use dockmaster for login and receive a token back.
- **Planning needed**: How does the SPA receive the token — query param, fragment, POST to a callback? What data does the SPA need (JWT, session cookie, both)? Should we support PKCE for public clients?

### Wildcard Target Matching for RBAC
- **Context**: Phase 5 uses exact string matching for targets. Both audits recommend glob/wildcard support (e.g., `projects/*`). Legacy also uses exact match.
- **When**: When the RBAC system needs to support hierarchical resources.
- **Decision needed**: Matching algorithm — `fnmatch` (glob), regex, or prefix match. Does `*` match nested paths?

### Role Deletion Referential Integrity
- **Context**: Phase 6 `DELETE /admin/roles/{name}` deletes without checking if service grants reference the role. Subjects silently lose permissions.
- **When**: When multiple users manage RBAC and accidental deletion is a risk.
- **Options**: Block deletion if in use (409 Conflict), warn but allow, cascade revocation.

### Admin UI — RBAC Management Pages
- **Context**: Admin dashboard already exists at `/ui/` (Phase 4c) with Jinja2 + Tailwind CSS. Phase 6 adds RBAC management pages (roles, grants CRUD) to this existing dashboard. This backlog item is partially resolved — the dashboard infrastructure exists, RBAC management pages are planned for Phase 6.
- **When**: Phase 6 (scheduled).
- **Status**: Planned — no longer deferred.

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

## Previously Deferred Items

### Redis Session Store
- **Context**: Phase 4 ships with in-memory `SessionStore`. Redis implementation uses the same `SessionStore` protocol.
- **When**: After Phase 4 in-memory is working, or when multi-instance deployment is needed.
- **Effort**: Small — implement `RedisSessionStore` against existing protocol.
- **Dependency**: `redis[hiredis]`

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
