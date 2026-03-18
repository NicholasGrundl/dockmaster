# Roadmap

Master plan and status for the dockmaster project. Single source of truth for what
is done, in progress, and planned.

**Goal**: Get dockmaster running for LLC domain to host projects behind SSO.

- Committed feature specs live in [`_blueprint/features/`](../features/)
- Completed specs archived in [`_blueprint/archive/features/`](../archive/features/)
- Backlogged ideas and draft specs live in [`feature-backlog.md`](./feature-backlog.md)
- Architecture decisions in [`decision-log.md`](./decision-log.md)

*Last updated: 2026-03-18*

---

## Overview

```
Phase 1: Config + Health + App Skeleton ............... ✅ COMPLETE
Phase 2: JWT Infrastructure .......................... ✅ COMPLETE
Phase 3: Token Exchange .............................. ✅ COMPLETE
Phase 4: OAuth Login + Session ....................... ✅ COMPLETE (4a, 4b, 4c)
Phase 5: RBAC ........................................ ✅ COMPLETE
Phase 6: RBAC Management (endpoints + admin UI) ...... ✅ COMPLETE
Phase 6b: Session Revocation ......................... ✅ COMPLETE
Phase 6c: CLI + OAuth Login Flow ..................... ✅ COMPLETE
Phase 7: Redirect URI + Ephemeral Keypair ............ ✅ COMPLETE
Phase 8a: Security Audit ............................. ✅ COMPLETE
Phase 8b: Code Quality Review ........................ ✅ COMPLETE
Phase 8c: Deployment Readiness ....................... ✅ COMPLETE
Phase 8d: Test Audit ................................. ✅ COMPLETE
Phase 8e: Auth Dependency Conventions ................ ✅ COMPLETE
Phase 9: Deployment + GCP Cleanup .................... PLANNED (next)
Phase 10: UI Tests ................................... PLANNED
```

**Test count**: 412 tests (as of Phase 8e completion)

---

## Phase 1: Config + Health + App Skeleton — ✅ COMPLETE

> Foundation: config loading, FastAPI app, health endpoint, logging, test infra.

**Spec**: [`archive/features/plan-phase1-scaffold.md`](../archive/features/[completed]%20plan-phase1-scaffold.md)

**Deliverables:**
- `Settings` model (pydantic-settings) with comma-separated set parsing
- `create_app()` factory with lifespan, structlog integration
- `GET /auth/health` and `GET /` endpoints
- Test infrastructure: conftest fixtures, TestClient setup
- `.env.example` with documented env vars

**Dependencies added:** `structlog>=24.0`

**GCP Guide:** `docs/GUIDE-gcp-project-setup.md` (follow-up)

---

## Phase 2: JWT Infrastructure — ✅ COMPLETE

> JWT signing (ServiceUser) and verification (ServiceRealm) with GCP service account keys, plus auth middleware and introspection endpoints.

**Spec**: [`archive/features/phase2-jwt-infrastructure-v2.md`](../archive/features/[completed]%20phase2-jwt-infrastructure-v2.md)
**Implementation guide**: [`archive/features/implementation-phase2-jwt-infrastructure.md`](../archive/features/[completed]%20implementation-phase2-jwt-infrastructure.md)

**Deliverables:**
- `ServiceUser` — JWT signing with GCP SA private key (RSA-SHA256)
- `ServiceRealm` — JWT verification with key caching
- `KeyCache` / `ServiceAccountKeyCache` — TTL-based public key fetching
- Auth middleware — FastAPI dependency for Bearer token extraction
- `GET /auth/key/{kid}` — serve public keys for external verification
- `GET /auth/claims` — return decoded JWT claims (debug/introspection)

**Dependencies:** `PyJWT>=2.0`, `cryptography`, `google-api-python-client`

---

## Phase 3: Token Exchange — ✅ COMPLETE

> Exchange Google JWT or access token for a dockmaster JWT. Dual-mode verification with access token fallback.

**Spec**: [`archive/features/phase3-token-exchange-v2.md`](../archive/features/[completed]%20phase3-token-exchange-v2.md)
**Implementation guide**: [`archive/features/implementation-phase3-token-exchange.md`](../archive/features/[completed]%20implementation-phase3-token-exchange.md)

**Deliverables:**
- `POST /auth/exchange` — dual-mode token exchange endpoint
- Access token validation helper (Google tokeninfo API)
- Profile claim forwarding (name, picture, etc.)
- Legacy bug fix: `can_issue` flag checked during exchange

**Dependencies:** `httpx`

---

## Phase 4: OAuth Login + Session — ✅ COMPLETE (4a, 4b, 4c)

> Browser-based Google OAuth2 login via Authlib, session management, token refresh, SecretsStorage, and admin dashboard UI.

**Spec**: [`archive/features/phase4-oauth-login-v2.md`](../archive/features/[completed]%20phase4-oauth-login-v2.md)
**Implementation guide**: [`archive/features/implementation-phase4-oauth-login.md`](../archive/features/[completed]%20implementation-phase4-oauth-login.md)

**Sub-phases:**
- **4a**: OAuth login flow, `SessionStore` protocol + `InMemorySessionStore`, login/callback/logout/principal routes
- **4b**: `POST /auth/refresh` (8-step flow), `SecretsStorage` (partial — pulled forward from Phase 5), test UI
- **4c**: Admin dashboard with Jinja2 + Tailwind CSS, `UIConfig` system, auth guard (`require_ui_session`), `list_all()` on SessionStore

**Dependencies:** `authlib>=1.0`, `jinja2`, `itsdangerous`, `pytest-playwright` (dev)

---

## Phase 5: RBAC — ✅ COMPLETE

> Role-based access control with RBAC data model, permission resolution engine, and permission-check endpoints.

**Spec**: [`archive/features/phase5-rbac-v2.md`](../archive/features/[completed]%20phase5-rbac-v2.md)
**Implementation guide**: [`archive/features/implementation-phase5-rbac.md`](../archive/features/[completed]%20implementation-phase5-rbac.md)

**Deliverables:**
- RBAC data model — `Role`, `Grant`, `ServiceGrants` (pydantic)
- `SecretsStorage` extended with RBAC read methods + write methods (pulled forward from Phase 6)
- `Authority` — permission resolution engine with TTL cache (RBAC_CACHE_TTL)
- Permission check endpoints: `GET /auth/has/{s}/{t}/{p}` and `GET /auth/has`

**Dependencies:** `google-cloud-secret-manager`

---

## Phase 6: RBAC Management — ✅ COMPLETE

> Admin CRUD endpoints for roles/grants, admin UI pages in existing dashboard.

**Spec**: [`archive/features/phase6-rbac-management-v2.md`](../archive/features/[completed]%20phase6-rbac-management-v2.md)
**Implementation guide**: [`archive/features/implementation-phase6-rbac-management.md`](../archive/features/[completed]%20implementation-phase6-rbac-management.md)

**Deliverables:**
- `SecretsStorage` / `AdminSecretsStorage` split (read-only base + write subclass, separate SM clients)
- RBAC CRUD REST endpoints at `/admin/*`
- RBAC management pages at `/ui/roles`, `/ui/grants`
- Admin auth: RBAC-first + `DOCKMASTER_ADMIN_EMAILS` env whitelist fallback
- Capability gate: 503 on writes when admin SA not configured

---

## Phase 6b: Session Revocation — ✅ COMPLETE

> Admin session management — API endpoints, admin_ops layer, and admin UI.

**Spec**: [`archive/features/implementation-phase6b-session-revocation.md`](../archive/features/[completed]%20implementation-phase6b-session-revocation.md)

**Deliverables:**
- Admin session endpoints (`/admin/sessions`) — list all, list by email, revoke by ID/email
- User endpoint (`GET /auth/sessions`) — current user's sessions
- Admin UI page (`/ui/sessions`) with revoke controls
- Dashboard filtered to current user's sessions only

---

## Phase 6c: CLI + OAuth Login Flow — ✅ COMPLETE

> Typer CLI with browser-based OAuth login for RBAC management from the terminal.

**Spec**: [`archive/features/phase6c-cli-v2.md`](../archive/features/[completed]%20phase6c-cli-v2.md)

**Deliverables:**
- Typer CLI: `login`/`logout`, `role` (get/list/create/delete/add/remove with `-p`), `grant` (get/list/delete/add/remove with `-r`), `check` (Oui!/Non!)
- Localhost-callback OAuth login flow (dynamic port, browser opens, CLI captures JWT)
- 15-minute JWT persisted to disk via `platformdirs`
- Server-side `redirect_uri` support on `/auth/login` (localhost-only validation)

**Dependencies:** `typer>=0.9`, `platformdirs`

**Deferred:** `token` command (awaiting ephemeral keypair design — Phase 7), external redirect URIs (Phase 7), server-side grant merge endpoint

---

## Phase 7: Redirect URI + Ephemeral Keypair — ✅ COMPLETE

> Two related enhancements: (1) full redirect URI system for external services to use dockmaster as identity broker, (2) ephemeral RS256 keypair for dockmaster-issued JWTs with JWKS endpoint.

**Spec**: [`archive/features/[completed] implementation-phase7-ephemeral-keypair-redirect.md`](../archive/features/[completed]%20implementation-phase7-ephemeral-keypair-redirect.md)

**Deliverables:**
- Per-service redirect URI allowlist (`ALLOWED_REDIRECT_URIS` setting)
- External redirect callback with auth code flow (code + state params)
- `EphemeralKeypairSigner` — in-memory RS256 keypair, rotated on restart
- `EphemeralKeyCache` with JWKS registry persistence
- `GET /auth/keys` endpoint serving public keys
- `POST /auth/token` — issue Type C JWT for a target service (session or Bearer auth)
- `POST /auth/code/exchange` — exchange auth code for JWT
- `token` CLI command

**Dependencies:** Phase 6c complete

---

## Phase 8a: Security Audit — ✅ COMPLETE

> Security audit + implementation of all 14 findings.

**Spec**: [`archive/features/[completed] implementation-phase8a-security-audit.md`](../archive/features/[completed]%20implementation-phase8a-security-audit.md)

**Deliverables:**
- 14 security findings identified and implemented (S-001 through S-014)
- SecurityHeadersMiddleware (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- Generic error messages for auth failures (no internal leakage)
- OAuth CSRF state management via TTLStore
- Removed Google refresh token endpoint
- Auth code flow with redirect URI validation

**Dependencies:** Phase 7 complete

---

## Phase 8b: Code Quality Review — ✅ COMPLETE

> Naming, vocab, FastAPI patterns, docstrings, and API surface consistency audit.

**Spec**: [`archive/features/[completed] implementation-phase8b-code-quality.md`](../archive/features/[completed]%20implementation-phase8b-code-quality.md)

**Dependencies:** Phase 8a complete

---

## Phase 8c: Deployment Readiness — ✅ COMPLETE

> Audit app for deployment blockers. Plan Caddy + Docker Compose integration for existing DO stack.

**Spec**: [`archive/features/[completed] implementation-phase8c-deployment-readiness.md`](../archive/features/[completed]%20implementation-phase8c-deployment-readiness.md)

**Dependencies:** Phase 8a, 8b complete

---

## Phase 8d: Test Audit — ✅ COMPLETE

> Audit test suite coverage, organization, patterns, and markers against pytest best practices.

**Spec**: [`archive/features/[completed] implementation-phase8d-test-audit.md`](../archive/features/[completed]%20implementation-phase8d-test-audit.md)

**Dependencies:** Phase 8a–8c complete

---

## Phase 8e: App Architecture Conventions — ✅ COMPLETE

> Standardize three cross-cutting concerns: auth dependency conventions,
> middleware organization, and settings injection.

**Spec**: [`archive/features/[completed] implementation-phase8e-auth-conventions.md`](../archive/features/[completed]%20implementation-phase8e-auth-conventions.md)

**Deliverables:**
- **Pillar 1 — Auth conventions**: Two-layer design (pure utilities + FastAPI dependencies). 6 auth gates, 4 info deps, 2 system checks in `auth/dependencies.py`. Typed credential models (`GoogleJWTCredential`, `GoogleAccessTokenCredential`). Router-level `dependencies=[...]` on all non-public routers. `auth/admin.py` removed.
- **Pillar 2 — Middleware consolidation**: `setup_middleware(app, settings)` helper in `main.py`.
- **Pillar 3 — Settings DI bridge**: `get_settings(request)` bridge in `config.py`. All routes use `Annotated[Settings, Depends(get_settings)]`.
- **App state bridges**: `state.py` module with `get_admin_storage`, `get_authority`, `get_session_store` bridge dependencies. Admin routes use `Annotated[X, Depends(...)]` instead of local helpers.

---

## Phase 9: Deployment + GCP Cleanup — PLANNED

> GCP credential rotation, setup/dev guides, and deployment configuration.

**Spec**: To be created during Phase 9 planning

**Deliverables (tentative — needs planning):**
- Rotate all GCP secrets (new client secret, rotate SA keys) — purge any credentials exposed during development
- GCP setup guide (`docs/GUIDE-gcp-setup.md`) — from-scratch setup instructions
- Local dev testing guide (`docs/GUIDE-local-dev.md`) — `.env`, uvicorn, curl/notebook walkthrough
- Deployment configuration (Docker Compose, Caddy reverse proxy, DO droplet)
- Admin SA (`dockmaster-admin`) setup guide
- Fix any deployment-blocking issues from Phase 8 audit

**Dependencies:** Phase 8 audit complete

---

## Phase 10: UI Tests — PLANNED

> Comprehensive UI test coverage for all admin pages. Deferred until UI is finalized and stable.

**Spec**: To be created during Phase 10 planning

**Deliverables:**
- Admin UI page tests (roles list, grants list, grants detail, session management)
- Form submission tests (create, edit, delete flows)
- Read-only mode tests (when admin SA not configured)
- Auth guard tests for admin UI routes

**Dependencies:** All UI-affecting phases complete (through Phase 7 at minimum)
