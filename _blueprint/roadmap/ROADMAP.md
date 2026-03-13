# Roadmap

Master plan and status for the dockmaster project. Single source of truth for what
is done, in progress, and planned.

**Goal**: Get dockmaster running for LLC domain to host projects behind SSO.

- Committed feature specs live in [`_blueprint/features/`](../features/)
- Backlogged ideas and draft specs live in [`feature-backlog.md`](./feature-backlog.md)
- Architecture decisions in [`decision-log.md`](./decision-log.md)

*Last updated: 2026-03-12*

---

## Overview

```
Phase 1: Config + Health + App Skeleton ............... ✅ COMPLETE
Phase 2: JWT Infrastructure .......................... ✅ COMPLETE
Phase 3: Token Exchange .............................. ✅ COMPLETE
Phase 4: OAuth Login + Session ....................... ✅ COMPLETE (4a, 4b, 4c)
Phase 5: RBAC ........................................ ✅ COMPLETE
Phase 6: RBAC Management (endpoints + admin UI) ...... IN PROGRESS
Phase 6b: Session Revocation ......................... PLANNED
Phase 6c: CLI + OAuth login flow ..................... PLANNED
Phase 7a: Auth + API Surface Audit ................... PLANNED
Phase 7b: Deployment + GCP Cleanup ................... PLANNED
Phase 8: UI Tests .................................... PLANNED
```

---

## Phase 1: Config + Health + App Skeleton — ✅ COMPLETE

> Foundation: config loading, FastAPI app, health endpoint, logging, test infra.

**Spec**: [`features/plan-phase1-scaffold.md`](../features/plan-phase1-scaffold.md)

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

**Spec**: [`features/phase2-jwt-infrastructure-v2.md`](../features/phase2-jwt-infrastructure-v2.md)
**Implementation guide**: [`features/implementation-phase2-jwt-infrastructure.md`](../features/implementation-phase2-jwt-infrastructure.md)

**Deliverables:**
- `ServiceUser` — JWT signing with GCP SA private key (RSA-SHA256)
- `ServiceRealm` — JWT verification with key caching
- `KeyCache` / `ServiceAccountKeyCache` — TTL-based public key fetching
- Auth middleware — FastAPI dependency for Bearer token extraction
- `GET /auth/key/{kid}` — serve public keys for external verification
- `GET /auth/claims` — return decoded JWT claims (debug/introspection)

**Dependencies:** `PyJWT>=2.0`, `cryptography`, `google-api-python-client`

**GCP Guide:** None (uses SA key from Phase 1 setup)

---

## Phase 3: Token Exchange — ✅ COMPLETE

> Exchange Google JWT or access token for a dockmaster JWT. Dual-mode verification with access token fallback.

**Spec**: [`features/phase3-token-exchange-v2.md`](../features/phase3-token-exchange-v2.md)
**Implementation guide**: [`features/implementation-phase3-token-exchange.md`](../features/implementation-phase3-token-exchange.md)

**Deliverables:**
- `POST /auth/exchange` — dual-mode token exchange endpoint
- Access token validation helper (Google tokeninfo API)
- Profile claim forwarding (name, picture, etc.)
- Legacy bug fix: `can_issue` flag checked during exchange

**Dependencies:** `httpx`

**GCP Guide:** None

---

## Phase 4: OAuth Login + Session — ✅ COMPLETE (4a, 4b, 4c)

> Browser-based Google OAuth2 login via Authlib, session management, token refresh, SecretsStorage, and admin dashboard UI.

**Spec**: [`features/phase4-oauth-login-v2.md`](../features/phase4-oauth-login-v2.md)
**Implementation guide**: [`features/implementation-phase4-oauth-login.md`](../features/implementation-phase4-oauth-login.md)

**Sub-phases:**
- **4a**: OAuth login flow, `SessionStore` protocol + `InMemorySessionStore`, login/callback/logout/principal routes
- **4b**: `POST /auth/refresh` (8-step flow), `SecretsStorage` (partial — pulled forward from Phase 5), test UI
- **4c**: Admin dashboard with Jinja2 + Tailwind CSS, `UIConfig` system, auth guard (`require_ui_session`), `list_all()` on SessionStore

**Deliverables:**
- Google OAuth2 browser login flow (authorize → callback → session)
- `POST /auth/refresh` — refresh token exchange
- Pluggable `SessionStore` protocol with in-memory implementation (incl. `list_all()`)
- `SecretsStorage` (partial: `_load_secret`, `get_client_secret`) — GCP Secret Manager
- Admin dashboard at `/ui/` with Jinja2 + Tailwind CSS (sessions table, service status)
- `UIConfig` — theme/branding config loaded from JSON file
- Auth guard (`require_ui_session`) — session-based auth for UI routes (separate from JWT middleware for API)
- Legacy bug fixes: `can_issue` enforcement, `data=` vs `params=` for token endpoint

**Dependencies:** `authlib>=1.0`, `jinja2`, `itsdangerous`, `pytest-playwright` (dev)

**GCP Guide:** `_blueprint/context/gcp-dev-setup/GUIDE-capture-oauth-fixtures.md`

---

## Phase 5: RBAC — ✅ COMPLETE

> Role-based access control with RBAC data model, permission resolution engine, and permission-check endpoints. Extends existing SecretsStorage with RBAC read methods.

**Spec**: [`features/phase5-rbac-v2.md`](../features/phase5-rbac-v2.md)
**Implementation guide**: [`features/implementation-phase5-rbac.md`](../features/implementation-phase5-rbac.md)

**Deliverables:**
- RBAC data model — `Role`, `Grant`, `ServiceGrants` (pydantic)
- Extend `SecretsStorage` with RBAC read methods (`get_role`, `get_service_grants`) — base class and `_load_secret` already exist from Phase 4b
- `Authority` — permission resolution engine with TTL cache (RBAC_CACHE_TTL)
- `GET /auth/has/{subject}/{target}/{permission}` — path-based permission check
- `GET /auth/has` — query-based permission check
- Legacy bug fix: "status" → "subject" error message typo

**Dependencies:** `google-cloud-secret-manager` (already installed from Phase 4b)

**Note:** Uses read-only SA credentials. Write methods (`_save_secret`, `_delete_secret`) deferred to Phase 6.

**GCP Guide:** `docs/GUIDE-secret-manager.md`

---

## Phase 6: RBAC Management — PLANNED

> Admin CRUD endpoints for roles/grants, admin UI pages in existing dashboard. CLI moved to Phase 6b.

**Spec**: [`features/phase6-rbac-management-v2.md`](../features/phase6-rbac-management-v2.md)
**Implementation guide**: [`features/implementation-phase6-rbac-management.md`](../features/implementation-phase6-rbac-management.md)

**Deliverables:**
- Extend `SecretsStorage` with write methods (`_save_secret`, `_delete_secret`, `put_role`, `put_service_grants`) — requires admin SA with SM write access
- RBAC CRUD REST endpoints at `/admin/*`
- RBAC management pages added to existing `/ui/` dashboard (extends Phase 4c admin UI)
- Admin auth (`require_admin`): RBAC role check (`has_permission(email, 'dockmaster', 'admin')`) + `DOCKMASTER_ADMIN_EMAILS` env whitelist fallback for bootstrap
- Capability gate (`require_admin_writes`): write endpoints return 503 when admin SA key not configured; read-only admin endpoints always work
- Read-only UI mode when admin SA missing (view roles/grants but no create/edit/delete)

**Dependencies:** None new (all deps already installed)

**Note:** Write operations require a separate admin SA (`dockmaster-admin`) with SM write permissions. See decision log for SA key split architecture. No shared API key (`DOCKMASTER_ADMIN_KEY` dropped).

**GCP Guide:** None

---

## Phase 6b: Session Revocation — PLANNED

> Admin session management — API endpoints, admin_ops layer, and admin UI for viewing and revoking user sessions. Mirrors the RBAC CRUD pattern from Phase 6.

**Spec**: To be created during Phase 6b planning (`implementation-phase6b-session-revocation.md`)

**Deliverables:**
- Admin session management endpoints (`/admin/sessions`) — list, revoke
- Shared `admin_ops` functions for session management (used by API + UI)
- Admin UI page for session management (view active sessions, revoke)
- Uses existing admin auth (`require_admin_api`, `require_admin_writes`)

**Dependencies:** Phase 6 complete

**GCP Guide:** None

---

## Phase 6c: CLI + OAuth Login Flow — PLANNED

> Typer CLI with browser-based OAuth login, enabling RBAC management and session revocation from the terminal.

**Spec**: [`features/phase6b-cli-v2.md`](../features/phase6b-cli-v2.md)
**Implementation guide**: To be created during Phase 6c planning (`implementation-phase6c-cli.md`)

**Deliverables:**
- Typer CLI: role, service, test, token, session commands (all go through dockmaster API)
- Localhost-callback OAuth login flow (browser opens, authenticates, CLI captures token)
- 15-minute JWT persisted to disk via `platformdirs` (no refresh token)
- Session revoke command (calls `/admin/sessions` endpoint)
- Legacy bug fixes: revoke wildcard off-by-one, role remove ValueError

**Dependencies:** `typer>=0.9`, `platformdirs`

**GCP Guide:** None

---

## Phase 7a: Auth + API Surface Audit — PLANNED

> Comprehensive audit of all HTTP endpoints, auth decision paths, and API surface before deployment. Produces a unified Mermaid DAG showing every request path through the system, an endpoint inventory, reverse proxy (Caddy) readiness check, and gap analysis. Expanded scope: also audits API completeness and CLI coverage.

**Spec**: [`features/implementation-phase6c-auth-audit.md`](../features/implementation-phase6c-auth-audit.md)

**Deliverables:**
- Endpoint inventory table (every route, auth mechanism, public/protected)
- Unified Mermaid DAG of all auth decision paths (entry → auth check → outcome)
- API surface audit — completeness, consistency, missing operations
- Caddy reverse proxy readiness doc (headers, cookies, redirects, TLS)
- Gap analysis with risk ratings
- Audit + document only — no code changes

**Dependencies:** Phases 6, 6b, 6c complete (audit the full surface area)

---

## Phase 7b: Deployment + GCP Cleanup — PLANNED

> GCP credential rotation, setup/dev guides, and deployment configuration. Plan this phase after all feature phases are complete.

**Spec**: To be created during Phase 7b planning

**Deliverables (tentative — needs planning):**
- Rotate all GCP secrets (new client secret, rotate SA keys) — purge any credentials exposed during development
- GCP setup guide (`docs/GUIDE-gcp-setup.md`) — from-scratch setup instructions
- Local dev testing guide (`docs/GUIDE-local-dev.md`) — `.env`, uvicorn, curl/notebook walkthrough
- Deployment configuration (Docker Compose, Caddy reverse proxy, DO droplet)
- Admin SA (`dockmaster-admin`) setup guide

**Dependencies:** All feature phases complete (6, 6b, 6c) + Phase 7a audit

**GCP Guide:** This phase IS the guide phase

---

## Phase 8: UI Tests — PLANNED

> Comprehensive UI test coverage for all admin pages. Deferred until UI is finalized and stable.

**Spec**: To be created during Phase 8 planning

**Deliverables:**
- Admin UI page tests (roles list, grants list, grants detail, session management)
- Form submission tests (create, edit, delete flows)
- Read-only mode tests (when admin SA not configured)
- Auth guard tests for admin UI routes

**Dependencies:** All UI-affecting phases complete (6, 6b, 6c, 7a)
