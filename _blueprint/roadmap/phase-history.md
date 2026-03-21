# Phase History

Append-only narrative log of all completed phases. Records the full story — decisions,
sub-phases, detours, pivots, and what changed vs the original plan.

New entries are added during alignment sessions when completed phases are flushed from
`implementation-progress.md` and `decision-log.md`.

*Created: 2026-03-21*

---

## Phase 1: Config + Health + App Skeleton (2026-03-08)

**Summary**: Foundation — config loading, FastAPI app factory, health endpoint, logging, test infra.

**Spec**: `archive/features/[completed] plan-phase1-scaffold.md`

**Delivered**:
- `Settings` model (pydantic-settings) with comma-separated set parsing
- `create_app()` factory with lifespan, structlog integration
- `GET /auth/health` and `GET /` endpoints
- Test infrastructure: conftest fixtures, TestClient setup
- `.env.example` with documented env vars

**Dependencies added**: `structlog>=24.0`

**Key decisions**:
- D1 — Exchange before OAuth: Build JWT (Phase 2) and token exchange (Phase 3) before OAuth (Phase 4). Simpler, testable increments.
- D2 — Fix legacy bugs during rebuild rather than porting them.
- D3 — RBAC management via CLI + API + simple UI (API-first for automation, CLI for operators, UI for visual management).
- D4 — Async Secret Manager via `run_in_executor` + TTL cache. Sync client with `RBAC_CACHE_TTL` (300s default).
- D5 — PyJWT + google-auth for JWT. Authlib for OAuth. Typer for CLI.
- D6 — Doc structure: ROADMAP.md overview + per-phase feature specs in `_blueprint/features/`.
- D7 — Sessions: In-memory `SessionStore` protocol first, Redis later.

**Follow-up**: `docs/GUIDE-gcp-project-setup.md`

---

## Phase 2: JWT Infrastructure (2026-03-08 – 2026-03-10)

**Summary**: JWT signing (ServiceUser) and verification (ServiceRealm) with GCP service account keys, plus auth middleware and introspection endpoints.

**Spec**: `archive/features/[completed] phase2-jwt-infrastructure-v2.md`
**Implementation guide**: `archive/features/[completed] implementation-phase2-jwt-infrastructure.md`

**Delivered**:
- `ServiceUser` — JWT signing with GCP SA private key (RSA-SHA256)
- `ServiceRealm` — JWT verification with key caching
- `KeyCache` / `ServiceAccountKeyCache` — TTL-based public key fetching
- Auth middleware — FastAPI dependency for Bearer token extraction
- `GET /auth/key/{kid}` — serve public keys for external verification
- `GET /auth/claims` — return decoded JWT claims (debug/introspection)

**Dependencies added**: `PyJWT>=2.0`, `cryptography`, `google-api-python-client`

**Key decisions**:
- D-exchange-mode — `/auth/exchange` accepts both Google JWTs and access tokens. Try JWT verification first, fall back to access token validation via tokeninfo API.

**Tests**: 67 total

---

## Phase 3: Token Exchange (2026-03-10 – 2026-03-11)

**Summary**: Exchange Google JWT or access token for a dockmaster JWT. Dual-mode verification with access token fallback.

**Spec**: `archive/features/[completed] phase3-token-exchange-v2.md`
**Implementation guide**: `archive/features/[completed] implementation-phase3-token-exchange.md`

**Delivered**:
- `POST /auth/exchange` — dual-mode token exchange endpoint
- Access token validation helper (Google tokeninfo API)
- Profile claim forwarding (name, picture, etc.)
- Legacy bug fix: `can_issue` flag checked during exchange

**Dependencies added**: `httpx`

**Tests**: 83 total (16 new)

---

## Phase 4: OAuth Login + Session (2026-03-11 – 2026-03-12)

**Summary**: Browser-based Google OAuth2 login via Authlib, session management, token refresh, SecretsStorage, and admin dashboard UI.

**Spec**: `archive/features/[completed] phase4-oauth-login-v2.md`
**Implementation guide**: `archive/features/[completed] implementation-phase4-oauth-login.md`

### Sub-phase split

Phase 4 was originally one phase but was too large. Split into three sub-phases:

**4a — Sessions + Login** (2026-03-11):
- `SessionStore` protocol + `InMemorySessionStore` (TDD, 9 tests)
- OAuth client setup (Authlib + Google)
- Login routes: `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/principal`
- GCP setup done first (tracer bullet): OAuth consent screen, client ID, SM secret, redirect URI
- Fixture capture: 4 OAuth fixtures (token_exchange, userinfo, token_refresh, tokeninfo)
- Tests: 103 total (20 new)

**4b — Refresh + SecretsStorage + Test UI** (2026-03-11):
- `SecretsStorage` class (partial — `_load_secret`, `get_client_secret`) pulled forward from Phase 5
- `POST /auth/refresh` (8-step flow)
- Test UI: `/ui/test` minimal HTML template
- Tests: 117 total (14 new)

**4c — Admin Dashboard + UI Polish** (2026-03-12):
- Jinja2 + Tailwind CSS (CDN) admin dashboard at `/ui/`
- `UIConfig` system (JSON file, `UI_CONFIG_PATH` setting)
- Auth guard (`require_ui_session` dependency)
- Login page, dashboard with sessions table
- `list_all()` on SessionStore with `_expiry` metadata
- Tests: 134 total (17 new)

### Key decisions (Phase 4)

- SecretsStorage pulled forward from Phase 5 into 4b — refresh endpoint needs client secret from SM.
- GCP setup + fixture capture first (tracer bullet) — get real responses, then build against real data.
- `itsdangerous>=2.1` for session cookie signing (Starlette's SessionMiddleware).
- `SessionMiddleware` added for Authlib OAuth state management.
- `create_app()` calls `get_settings()` directly for middleware (not overridable via DI).
- SA IAM role for key enumeration deferred — code handles failure gracefully.
- Jinja2 + Tailwind CSS for UI, not HTMX. Simple enough for full-page renders.
- `UIConfig` as separate Pydantic model loaded from JSON (not in core Settings).
- UI auth guard via `Depends()` not middleware — some UI routes are public.
- Separate auth patterns: session/cookie for UI, JWT/header for API.
- Google profile picture URL stored in session data for avatars.
- `no-referrer` meta tag for Google profile pic CDN.
- Refresh token tool removed from dashboard (test-only, not admin function).
- `list_all()` returns `_expiry` metadata alongside session data.
- TemplateResponse updated to new Starlette API (`request` as first positional arg).

**Dependencies added**: `authlib>=1.0`, `jinja2`, `itsdangerous`, `pytest-playwright` (dev)

**Deferred**: Admin actions (session revoke, RBAC management) → Phase 5+ when RBAC exists. GCP secret rotation → Phase 7.

---

## Phase 5: RBAC (2026-03-12)

**Summary**: Role-based access control with data model, Secret Manager persistence, permission resolution engine, and check endpoints.

**Spec**: `archive/features/[completed] phase5-rbac-v2.md`
**Implementation guide**: `archive/features/[completed] implementation-phase5-rbac.md`

**Delivered**:
- RBAC data model — `Role`, `Grant`, `ServiceGrants` (pydantic)
- `SecretsStorage` extended with RBAC read + write methods (writes pulled forward from Phase 6)
- `Authority` — permission resolution engine with TTL cache (`RBAC_CACHE_TTL`)
- Permission check endpoints: `GET /auth/has/{s}/{t}/{p}` and `GET /auth/has`

**Key decisions**:
- No real GCP fixture capture — SM is gRPC-based, tests mock the Python client directly.
- `put_*`/`delete_*` methods implemented early (Phase 6 was imminent).
- `_save_secret` uses idempotent create (swallows `AlreadyExists`, then adds version).
- Permission endpoints use existing `get_current_user` auth (HTTPBearer + JWT verification).

**Dependencies added**: `google-cloud-secret-manager`

**Tests**: 177 total (43 new)

---

## Phase 6: RBAC Management (2026-03-12)

**Summary**: Admin CRUD endpoints for roles/grants, admin UI pages in existing dashboard.

**Spec**: `archive/features/[completed] phase6-rbac-management-v2.md`
**Implementation guide**: `archive/features/[completed] implementation-phase6-rbac-management.md`

**Delivered**:
- `SecretsStorage` / `AdminSecretsStorage` split (read-only base + write subclass, separate SM clients)
- RBAC CRUD REST endpoints at `/admin/*`
- RBAC management pages at `/ui/roles`, `/ui/grants`
- Admin auth: RBAC-first + `DOCKMASTER_ADMIN_EMAILS` env whitelist fallback
- Capability gate: 503 on writes when admin SA not configured
- Service layer in `rbac/admin_ops.py` shared by API and UI routes

### Architecture decisions

- D8 — Separate `require_admin_api` / `require_admin_ui` dependencies with shared `_is_admin()` helper.
- D9 — UI routes call shared service layer (`admin_ops`) directly, not API endpoints. No auth bridging.
- D10 — Service layer at `rbac/admin_ops.py`, admin auth at `auth/admin.py`.
- D11 — `SecretsStorage` (read-only base) / `AdminSecretsStorage` (writes). Two instances, separate SM clients. Permission boundary at GCP IAM level.

**GCP setup**: `dockmaster-admin` SA created with `roles/secretmanager.admin`. Bootstrap data seeded (`role-admin`, `service-grants-dockmaster`).

**Tests**: 234 total

---

## Phase 6b: Session Revocation (2026-03-12)

**Summary**: Admin session management — API endpoints, admin_ops layer, and admin UI.

**Spec**: `archive/features/[completed] implementation-phase6b-session-revocation.md`

**Delivered**:
- Admin session endpoints (`/admin/sessions`) — list all, list by email, revoke by ID/email
- User endpoint (`GET /auth/sessions`) — current user's sessions
- Admin UI page (`/ui/sessions`) with revoke controls
- Dashboard filtered to current user's sessions only

**Tests**: 257 total (23 new)

---

## Phase 6c: CLI + OAuth Login Flow (2026-03-12)

**Summary**: Typer CLI with browser-based OAuth login for RBAC management from the terminal.

**Spec**: `archive/features/[completed] phase6c-cli-v2.md`

**Delivered**:
- Typer CLI: `login`/`logout`, `role` (get/list/create/delete/add/remove with `-p`), `grant` (get/list/delete/add/remove with `-r`), `check` (Oui!/Non!)
- Localhost-callback OAuth login flow (dynamic port, browser opens, CLI captures JWT)
- 15-minute JWT persisted to disk via `platformdirs`
- Server-side `redirect_uri` support on `/auth/login` (localhost-only validation)

### Key decisions

- D12 — `grant` command group (not `service`) to avoid verb collision.
- D13 — `check` command (not `test`) for permission testing.
- D14 — Named flags: `--permission`/`-p` for roles, `--role`/`-r` for grants.
- D15 — `token` command deferred (awaiting ephemeral keypair design).
- D16 — `grant remove` without `-r` flags removes all roles for that subject.
- D17 — Localhost-only redirect URI; full system designed in Phase 7.
- D18 — Build-first, test after approach. Single session target.
- D19 — `grant add` uses `allow_404=True` on GET (read-modify-write pattern).
- D20 — Dev deps consolidated to `[dependency-groups]` (PEP 735 / uv standard).

**Dependencies added**: `typer>=0.9`, `platformdirs`

**Deferred**: `token` command → Phase 7. External redirect URIs → Phase 7. Server-side grant merge endpoint.

**Tests**: 301 total (44 new)

---

## Phase 7: Redirect URI + Ephemeral Keypair (2026-03-16)

**Summary**: Full redirect URI system for external services + ephemeral RS256 keypair for dockmaster-issued JWTs with JWKS endpoint.

**Spec**: `archive/features/[completed] implementation-phase7-ephemeral-keypair-redirect.md`

**Delivered** (across 4 sessions):
- Per-service redirect URI allowlist (`ALLOWED_REDIRECT_URIS` setting)
- External redirect callback with auth code flow (code + state params)
- `JWTTokenIssuer` — in-memory RS256 keypair, Type C JWT signing
- `EphemeralKeyCache` with JWKS registry persistence
- `GET /auth/keys` endpoint serving public keys
- `POST /auth/token` — issue Type C JWT for a target service (session or Bearer auth)
- `POST /auth/code/exchange` — exchange auth code for JWT
- `token` CLI command
- CORS middleware (`ALLOWED_ORIGINS` setting)
- `AuthCodeStore` — in-memory, single-use, 5min expiry

### Key decisions

- D21 — `JWTTokenIssuer` naming (not `DockTokenIssuer`). Name describes function.
- D22 — JWTTokenIssuer owns private key; EphemeralKeyCache is a dumb public key store. Private keys never touch cache objects.
- D23 — `ServiceRealm` accepts `KeyCacheLike | list[KeyCacheLike]`. Ephemeral first (local, fast), SA second (GCP, slower).
- D24 — EphemeralKeyCache retention 12h (43200s), NOT tied to token TTL. Configurable for future use.
- D25 — Pruning only at construction (restart). No mid-process rotation. Keypair is ephemeral-per-process.
- D26 — Pruning logic: keep if `kid == current_kid` OR `(now - created_at) <= retention_padded`. Absolute age check.
- D27 — Removed `realm.key_cache` property, added `realm.get_key(kid)` method. Clean break, no compat shim.
- D28 — JWKS + OIDC discovery endpoints deferred to backlog. Consumers use dockmaster SDK with `/auth/key/{kid}`.
- D29 — Vocab unification (`ServiceUser.get_token` vs `JWTTokenIssuer.sign`) added to Phase 8a scope.

### Detours

- JWKS + OIDC discovery endpoints were in the original spec but deferred — no consumer needs standard OIDC auto-discovery yet.
- Switched `/auth/exchange` from `signer.get_token()` (Type B, SA-signed) to `token_issuer.sign()` (Type C, ephemeral). All dockmaster-issued JWTs now use ephemeral keypair.
- CLI `_handle_cli_callback` also switched to Type C tokens.

**Tests**: 411 total (28 new in final session, ~110 new across all sessions)

---

## Phase 8a: Security Audit (2026-03-17)

**Summary**: Security audit of all endpoints + implementation of all 14 findings.

**Spec**: `archive/features/[completed] implementation-phase8a-security-audit.md`

### Pass 1 — Audit (document only)

- 46 endpoints cataloged (6 public, 5 semi-public, 35 protected)
- Auth decision DAG (Mermaid)
- 14 security findings: S-001 through S-014
- Top 5 pre-deployment priorities: disable OpenAPI docs, security headers, cap token expiry, audience validation, sanitize JWT errors

### Pass 2 — Fix Implementation

All 14 findings fixed:
- S-001: `ENABLE_DOCS` bool setting (default `False`). Not a `DEV_MODE` meta-setting.
- S-002: JWT decode errors — generic 401 message, structured warning log with SHA-256 fingerprint.
- S-003: 503 detail simplified to "Write operations are not available."
- S-004: `SecurityHeadersMiddleware` — CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy. `SECURITY_HEADERS` kill-switch.
- S-005: OAuth CSRF state moved to `TTLStore[dict]` (10min TTL). `AuthCodeStore` refactored onto `TTLStore` base.
- S-006: `MAX_TOKEN_TTL` setting (default 3600s) caps `/auth/exchange` expiry.
- S-007: Audience validation documented by design — receiver responsibility.
- S-008: `/auth/refresh` removed entirely. Google refresh tokens are a larger liability than the problem they solve.
- S-009, S-010: Resolved by S-008 removal.
- S-011: CLI callback scrubs token from browser history via `history.replaceState`.
- S-012: Documented in `main.py` comment. Middleware consolidation → backlog.
- S-013: 403 messages genericized to "Access denied." Details logged server-side only.
- S-014: Root endpoint no longer exposes docs URL when disabled.

### Key decisions

- S-001 fix: `ENABLE_DOCS` bool (not `DEV_MODE` meta-setting). DEV_MODE deferred.
- Settings refactor: replaced `Depends(get_settings)` + `lru_cache` with `app.state.settings`. `create_app()` accepts optional `Settings` param.
- Test infra: `test_app_factory` fixture returns `TestClient`, `auth_client` moved to domain conftest.

**Tests**: 412 (removed 14 refresh tests, added 1 exchange clamping test)

---

## Phase 8b: Code Quality Review (2026-03-17)

**Summary**: Naming, vocab, FastAPI patterns, docstrings, and API surface consistency audit. Document only — no code changes.

**Spec**: `archive/features/[completed] implementation-phase8b-code-quality.md`

### Findings

- 20 code quality findings (Q-001 through Q-020): 7 Medium, 13 Low
- 12 implementation tasks approved ("do now")
- 8 documentation/backlog items
- 2 no-action items

### Key decisions for future phases

- Rename `ServiceUser` → `ServiceAccountSigner`
- Migrate refresh to Type C
- Rename `middleware.py` → `dependencies.py`
- Standardize logger names to `__name__`
- Add `response_model` everywhere
- Extract session helper

---

## Phase 8c: Deployment Readiness (2026-03-17)

**Summary**: Audit app for deployment blockers. Plan Caddy + Docker Compose integration for existing DO stack. Document only — no code changes.

**Spec**: `archive/features/[completed] implementation-phase8c-deployment-readiness.md`

### Findings

- 7 findings: D-010 through D-016
- 2 blockers: proxy headers (D-010), session secret default (D-011)
- 2 warnings: OpenAPI docs exposed (D-012), JWKS registry persistence (D-014)
- 2 nice-to-haves: health endpoint depth (D-015), host/port config (D-016)

### Key decisions

- Domain: `auth.insilicostrategy.com` (subdomain-based routing)
- Caddy stays as OS system service (not containerized)
- Build: local build + transfer now, GCP Artifact Registry via GitHub Actions later
- D-010 fix: uvicorn `--proxy-headers` + `REQUIRE_PROXY_HEADERS` middleware (default True)
- D-011 fix: make `SESSION_SECRET_KEY` required (no default)
- GCP creds: SCP key files to droplet, mount as Docker volumes
- 15-item pre-deployment checklist for Phase 9

---

## Phase 8d: Test Audit (2026-03-17)

**Summary**: Audit test suite coverage, organization, patterns, and markers against pytest best practices. Document only.

**Spec**: `archive/features/[completed] implementation-phase8d-test-audit.md`

---

## Phase 8e: App Architecture Conventions (2026-03-17 – 2026-03-18)

**Summary**: Standardize three cross-cutting concerns: auth dependency conventions, middleware organization, and settings injection.

**Spec**: `archive/features/[completed] implementation-phase8e-auth-conventions.md`

### Pillar 1 — Auth Conventions

- Two-layer design: pure utility functions + FastAPI dependency wrappers
- 6 auth gates, 4 info deps, 2 system checks in `auth/dependencies.py`
- Typed credential models (`GoogleJWTCredential`, `GoogleAccessTokenCredential`)
- Router-level `dependencies=[...]` on all non-public routers
- `auth/admin.py` removed (admin auth folded into dependencies.py)
- Dependency prefix taxonomy (`allow_*`/`needs_*`/`check_*`/`get_*`) documented in module docstrings

### Pillar 2 — Middleware Consolidation

- `setup_middleware(app, settings)` helper in `main.py`

### Pillar 3 — Settings DI Bridge

- `get_settings(request)` bridge in `config.py` (not `main.py` — avoids circular imports)
- All routes use `Annotated[Settings, Depends(get_settings)]`

### Key decisions

- Two-layer design — pure utilities (typed args, no Depends) + FastAPI wrappers (inject via Cookie/HTTPBearer/get_settings, call utilities)
- Gate vs info pattern: router-level `dependencies=[Depends(allow_*)]` for auth enforcement, separate info dependencies for data injection. Never the same dependency.
- `get_settings` lives in `config.py`, `create_settings()` is the standalone factory
- Exchange aud handling: typed credential models replace brittle `iss`-sniffing
- Error message security: collapsed credential-type-revealing messages
- Removed unused `user` param from 8 admin_ui POST routes

**Tests**: 412 passed

---

## Phase 9a: Deployment Readiness Cherry-Picks (2026-03-18 – 2026-03-19)

**Summary**: Extracted deployment-critical fixes from Phase 8c findings and implemented them ahead of the full deployment phase.

**Delivered**:
- Auto-generate `session_secret_key` via `default_factory` + module flag accessor
- `CommaSeparatedSet` type using `Annotated[..., BeforeValidator(...)]` — eliminates all `object.__setattr__`
- `field_validator` for `log_level` normalization, removed `model_validator` entirely
- `RequireProxyHeadersMiddleware` (default enabled, 502 if `X-Forwarded-Proto` missing)
- File-based structured logging with `RotatingFileHandler` (`LOG_FILE`, `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT`)

**Deferred to Phase 9c**: Dockerfile, docker-compose.yml, Caddyfile, .env templates, monitoring guide

---

## Phase 9b: Documentation Overhaul (2026-03-19 – ongoing)

**Summary**: Comprehensive documentation rewrite — GUIDEs (setup & howto) from greenfield perspective.

**Completed**:
- `GUIDE-01-gcp-setup.md` — GCP project, APIs, both SAs, Secret Manager, OAuth, Appendix A (direnv)
- `GUIDE-02-consumer-howto.md` — Prerequisites, install, dev server, browser login, CLI, service integration, env var reference, endpoints reference, Appendix A (12 curl tests)
- `GUIDE-03-developer-howto.md` — Repo layout, dev commands, code patterns, adding endpoints (three-layer protection model), test patterns, linting/types, Appendix A (security model + checklist). Also: generalized `check_permission` — renamed `admin_emails` → `whitelist_emails`.

**Planned (not yet written)**:
- `LEARNING-01-overview.md` through `LEARNING-04-internals.md` — conceptual architecture docs
- `GUIDE-04-production-deployment.md` — deferred to Phase 9c

---

## Phase 11b Planning Session (2026-03-18)

**Summary**: Planning session for Node.js Browser Auth SDK. No implementation — spec produced.

**Key decisions**:
- TypeScript, ESM only, single dependency (`jose` for JWT decoding)
- Framework-agnostic core (no React hooks or Astro middleware yet)
- Two modes: `cookie` (same-domain) and `token` (cross-domain refresh tokens)
- Refresh token in sessionStorage, JWT in memory. Tab close = logout.
- Monorepo: `packages/auth-js/` subdirectory in dockmaster repo
- GCP Artifact Registry for publishing, npm public deferred
- React hooks, Astro middleware, SSR middleware all deferred
- Small server addition: `return_to` param on `GET /auth/login` for cookie mode
