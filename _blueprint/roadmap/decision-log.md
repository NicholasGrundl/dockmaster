# Architecture Decision Log

Record key decisions here so future-you remembers why.

*Last updated: 2026-03-12*

---

## 2026-03-08: Returning to this project to get auth behind my public domains

**Decision**: First get dockmaster running for my LLC domain to host projects behind SSO.
**Rationale**: Need to be able to access stuff from outside my home network.

---

## 2026-03-08: Phase ordering — Exchange before OAuth

**Decision**: Build JWT infrastructure (Phase 2) and token exchange (Phase 3) before OAuth login (Phase 4).
**Rationale**: Simpler, testable increments. JWT core → /exchange → OAuth login. Each phase builds on the previous without requiring browser flows or external OAuth setup until Phase 4.

## 2026-03-08: Legacy bugs — Fix during rebuild

**Decision**: Fix known legacy bugs during the clean-room rebuild rather than porting them.
**Rationale**: Clean-room implementation. Document what changed vs legacy in each phase spec.

## 2026-03-08: RBAC management — CLI + API + simple UI

**Decision**: Provide RBAC management through CRUD REST endpoints, a Typer CLI, and an admin dashboard UI.
**Rationale**: API-first for automation, CLI for operators, UI for visual management. All three share the same backend logic.
**Updated 2026-03-12**: Admin UI built with Jinja2 + Tailwind CSS at `/ui/` (Phase 4c). Phase 6 extends this existing dashboard with RBAC management pages rather than creating a separate `/admin/*` UI. HTMX not used.

## 2026-03-08: Async + Secret Manager — run_in_executor + TTL cache

**Decision**: Wrap synchronous Secret Manager calls with `run_in_executor`. Use TTL-based in-memory cache to minimize blocking calls.
**Rationale**: Secret Manager Python client is sync-only. TTL cache (RBAC_CACHE_TTL) makes the sync overhead acceptable. Document `AsyncClient` as a future optimization path.

## 2026-03-08: RBAC caching — TTL-based in-memory

**Decision**: Use TTL-based in-memory cache for RBAC data. Config var `RBAC_CACHE_TTL` with default 300s.
**Rationale**: Simple, no external dependencies. Cache miss triggers Secret Manager fetch. Acceptable staleness for permission data that changes infrequently.

## 2026-03-08: JWT library — PyJWT + google-auth

**Decision**: Use PyJWT for JWT encode/decode and google-auth for GCP SA credentials and IAM key fetching.
**Rationale**: PyJWT is the standard Python JWT library. google-auth handles GCP-specific credential management, SA key loading, and IAM API integration.

## 2026-03-08: OAuth library — Authlib

**Decision**: Use Authlib for OAuth2/OIDC client integration.
**Rationale**: Full OAuth2/OIDC client with FastAPI integration, handles PKCE + discovery. More complete than rolling our own.

## 2026-03-08: Doc structure — ROADMAP.md + per-phase feature specs

**Decision**: Master roadmap with phase summaries, detailed specs in `_blueprint/features/` (one per phase).
**Rationale**: Overview stays scannable; implementation details live in dedicated specs. New sessions can read ROADMAP.md → find current phase → read its spec.

## 2026-03-08: Sessions — In-memory first → Redis later

**Decision**: Implement a pluggable `SessionStore` protocol. Ship in-memory dict implementation first, Redis as follow-up.
**Rationale**: Unblocks development without infrastructure dependency. Protocol ensures drop-in replacement when Redis is needed.

## 2026-03-08: /exchange mode — Keep dual-mode

**Decision**: `/auth/exchange` accepts both Google JWTs and access tokens. Try JWT verification first, fall back to access token validation via tokeninfo API.
**Rationale**: Matches legacy behavior for backwards compatibility. Services with JWTs get fast local verification; browser contexts with access tokens still work.

## 2026-03-08: CLI framework — Typer

**Decision**: Use Typer for the CLI tool.
**Rationale**: Modern Click wrapper, type-hint driven, auto-completion support. Minimal boilerplate for CRUD-style commands.

## 2026-03-08: GCP guides — Separate per-phase

**Decision**: Create GCP setup guides as separate docs, one per phase that needs GCP configuration.
**Rationale**: Each guide is self-contained and only relevant when that phase is being deployed. Guides: `GUIDE-gcp-project-setup.md` (done), `GUIDE-oauth-consent-screen.md` (P4), `GUIDE-secret-manager.md` (P5).

---

## Phase 4 Decisions (2026-03-11 – 2026-03-12)

### 2026-03-11: Phase 4 split into sub-phases (4a, 4b, 4c)

**Decision**: Split Phase 4 into three sub-phases: 4a (sessions + login), 4b (refresh + SecretsStorage + test UI), 4c (admin dashboard + UI polish).
**Rationale**: Phase 4 scope was too large for a single pass. Sub-phases kept each implementation session focused and testable.

### 2026-03-11: SecretsStorage pulled forward from Phase 5 into Phase 4b

**Decision**: Implement partial `SecretsStorage` (`_load_secret`, `get_client_secret`) in Phase 4b instead of waiting for Phase 5.
**Rationale**: The refresh endpoint needs to fetch the OAuth client secret from GCP Secret Manager. Building this in Phase 4b means the refresh flow works end-to-end against real GCP.

### 2026-03-11: GCP setup + fixture capture first (tracer bullet)

**Decision**: Do GCP setup and fixture capture before writing application code for each sub-phase.
**Rationale**: Tracer bullet methodology — get real GCP responses first, then build against real data. Captured fixtures become test mock data.

### 2026-03-11: Post-4b — Rotate all GCP secrets

**Decision**: After Phase 4b, rotate all GCP secrets and write setup guide from scratch.
**Rationale**: Development involved creating/exposing real credentials. Clean rotation ensures nothing leaked persists.

### 2026-03-11: itsdangerous for session cookie signing

**Decision**: Add `itsdangerous>=2.1` as dependency for session cookie signing.
**Rationale**: Industry-standard library for signed cookies. Used by Starlette's SessionMiddleware.

### 2026-03-11: Starlette SessionMiddleware for OAuth state

**Decision**: Add `SessionMiddleware` from Starlette for OAuth state management.
**Rationale**: Authlib requires server-side session storage for OAuth state/nonce. Starlette's middleware provides this with signed cookies.

### 2026-03-11: create_app() calls get_settings() directly for middleware

**Decision**: `create_app()` calls `get_settings()` directly for middleware configuration (not overridable via DI).
**Rationale**: Middleware is configured at app creation time, before the DI container is available. Tests that need different settings must set env vars before app creation.

### 2026-03-11: SA IAM role for key enumeration deferred

**Decision**: Defer granting the dockmaster SA the IAM role needed for key enumeration.
**Rationale**: Code handles the failure gracefully (falls back to single-key mode). Non-blocking for development.

### 2026-03-11: Jinja2 + Tailwind CSS for UI (not HTMX)

**Decision**: Use Jinja2 templates with Tailwind CSS via CDN for the admin dashboard. No HTMX.
**Rationale**: Tailwind provides a polished look with minimal effort. HTMX not needed — the admin UI is simple enough that full-page renders work fine. Can add HTMX later if interactivity needs grow.

### 2026-03-11: UIConfig as separate Pydantic model (not in core Settings)

**Decision**: UI theming/branding lives in a `UIConfig` Pydantic model loaded from a JSON file, pointed to by `UI_CONFIG_PATH` in Settings.
**Rationale**: Keeps UI config (colors, branding, text) separate from core app settings (GCP credentials, auth config). JSON file can be swapped per deployment without touching env vars.

### 2026-03-11: UI auth guard via Depends() (not middleware)

**Decision**: UI route authentication uses a `require_ui_session` FastAPI dependency, not middleware.
**Rationale**: More granular — some UI routes (login page) are public, others require auth. Dependency injection is the FastAPI-native pattern and easier to test.

### 2026-03-11: Separate auth patterns — session/cookie (UI) vs JWT/header (API)

**Decision**: UI routes use session cookie authentication (`require_ui_session`). API routes use JWT Bearer token authentication (middleware from Phase 2).
**Rationale**: Different clients, different auth patterns. Browsers naturally use cookies; services naturally use Bearer tokens. Keeping them separate avoids forcing one pattern on both.

### 2026-03-11: Store Google profile picture URL in session data

**Decision**: Capture the Google profile picture URL from the OAuth userinfo response and store it in session data.
**Rationale**: Enables displaying user avatars in the admin dashboard without additional API calls.

### 2026-03-12: no-referrer meta tag for Google profile pic CDN

**Decision**: Add `<meta name="referrer" content="no-referrer">` to HTML templates.
**Rationale**: Google's profile picture CDN blocks requests with foreign referrer headers. The no-referrer policy prevents the browser from sending the dockmaster URL as referrer.

### 2026-03-12: Refresh token tool removed from dashboard

**Decision**: Remove the refresh token testing tool from the admin dashboard.
**Rationale**: Was a development/testing aid, not an admin function. Admin actions (session revoke, RBAC management) deferred to Phase 5+ when RBAC layer exists.

### 2026-03-12: Admin actions deferred to Phase 5+

**Decision**: Session revocation and RBAC management UI deferred until the RBAC layer exists.
**Rationale**: Admin actions require authorization checks. Building them before RBAC means no way to restrict who can perform admin operations.

### 2026-03-12: list_all() returns _expiry metadata

**Decision**: `SessionStore.list_all()` returns `_expiry` metadata alongside session data.
**Rationale**: Dashboard needs to display session expiry times. Storing expiry in the returned dict avoids a separate lookup.

### 2026-03-12: TemplateResponse updated to new Starlette API

**Decision**: Use `TemplateResponse(request, ...)` (request as first positional arg) instead of the deprecated `TemplateResponse(name, context)` pattern.
**Rationale**: Starlette deprecated the old API. Using the new signature avoids deprecation warnings.

### 2026-03-12: pytest-playwright added as dev dependency

**Decision**: Add `pytest-playwright` for UI testing and visual verification via screenshots.
**Rationale**: Enables screenshot-based visual testing of the admin dashboard during development.

---

## Architecture Decisions (2026-03-12)

### 2026-03-12: GCP SA key split — Read-only vs Admin

**Decision**: Use two separate GCP service accounts: `dockmaster` (read-only) for runtime operations and `dockmaster-admin` (write access) for RBAC management operations.
**Rationale**: Least-privilege principle. The runtime SA only needs to read secrets (JWT keys, client secrets, RBAC data). Write access to Secret Manager (creating/updating roles and grants) is restricted to the admin SA, used only by Phase 6 admin endpoints and CLI. This limits blast radius if the runtime SA key is compromised.
**Implications**:
- Phase 5 (RBAC reads): Uses existing runtime SA — no change needed.
- Phase 6 (RBAC writes): Needs `ADMIN_SA_KEY_FILE` setting and a second SM client initialized with admin credentials.
- Two credential paths in the app: runtime client (lifespan singleton) + admin client (Phase 6 lifespan addition).

### 2026-03-12: Admin authorization — RBAC-first with settings fallback (no API key)

**Decision**: Admin access is determined by the RBAC system first (`has_permission(email, 'dockmaster', 'admin')`), with `DOCKMASTER_ADMIN_EMAILS` in Settings as a bootstrap/emergency fallback. No shared API key (`DOCKMASTER_ADMIN_KEY` dropped).
**Rationale**: Once RBAC exists, admin status should come from RBAC itself. The bootstrap problem (can't assign admin role if you need admin to access RBAC) requires a settings-based override. Shared API key dropped to reduce credential surface — SA keys stay server-side only.
**Bootstrap flow**: First deploy sets `DOCKMASTER_ADMIN_EMAILS` with admin's email → login via UI → create "admin" role in RBAC → grant to self → optionally remove env whitelist.

### 2026-03-12: Admin capability gate — 503 for missing admin SA

**Decision**: Write admin endpoints (`POST`, `PUT`, `DELETE` at `/admin/*`) return 503 Service Unavailable when `ADMIN_SA_KEY_FILE` is not configured. Read-only admin endpoints (`GET`) always work using the runtime SA.
**Rationale**: 503 signals a configuration issue (not an auth failure, which is 403). Allows inspecting RBAC state even without write capability. Clean separation of "can the server do this?" (503) vs "are you allowed?" (403).

### 2026-03-12: Phase 6 / 6b split — CLI moved to separate phase

**Decision**: Phase 6 delivers admin CRUD endpoints + admin UI pages. Phase 6b adds the Typer CLI with browser-based OAuth login flow.
**Rationale**: Phase 6 is fully usable via the browser (admin logs in, manages RBAC via UI). CLI adds a second interface but requires building an OAuth login flow (localhost callback, token storage). Splitting lets Phase 6 ship faster.

### 2026-03-12: CLI auth — localhost-callback OAuth with 15-minute JWT

**Decision**: CLI authenticates via localhost-callback OAuth flow (browser opens, user authenticates, CLI captures token). 15-minute JWT persisted to disk via `platformdirs`. No refresh token.
**Rationale**: Same pattern as gcloud, gh, firebase CLIs. Short TTL is acceptable — admin CLI sessions are bursty (login, run a few commands, done). No refresh token keeps the implementation simple. `platformdirs` for cross-platform token storage location.
