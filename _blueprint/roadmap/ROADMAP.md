# Roadmap

Master plan and status for the dockmaster project. Single source of truth for what
is done, in progress, and planned.

**Goal**: Get dockmaster running for LLC domain to host projects behind SSO.

- Committed feature specs live in [`_blueprint/features/`](../features/)
- Backlogged ideas and draft specs live in [`feature-backlog.md`](./feature-backlog.md)
- Architecture decisions in [`decision-log.md`](./decision-log.md)

*Last updated: 2026-03-08*

---

## Overview

```
Phase 1: Config + Health + App Skeleton ............... ✅ COMPLETE
Phase 2: JWT Infrastructure .......................... PLANNED
Phase 3: Token Exchange .............................. PLANNED
Phase 4: OAuth Login + Session ....................... PLANNED
Phase 5: RBAC ........................................ PLANNED
Phase 6: RBAC Management + CLI ....................... PLANNED
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

## Phase 2: JWT Infrastructure — PLANNED

> JWT signing (ServiceUser) and verification (ServiceRealm) with GCP service account keys, plus auth middleware and introspection endpoints.

**Spec**: [`features/phase2-jwt-infrastructure.md`](../features/phase2-jwt-infrastructure.md)

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

## Phase 3: Token Exchange — PLANNED

> Exchange Google JWT or access token for a dockmaster JWT. Dual-mode verification with access token fallback.

**Spec**: [`features/phase3-token-exchange.md`](../features/phase3-token-exchange.md)

**Deliverables:**
- `POST /auth/exchange` — dual-mode token exchange endpoint
- Access token validation helper (Google tokeninfo API)
- Profile claim forwarding (name, picture, etc.)
- Legacy bug fix: `can_issue` flag checked during exchange

**Dependencies:** `httpx`

**GCP Guide:** None

---

## Phase 4: OAuth Login + Session — PLANNED

> Browser-based Google OAuth2 login via Authlib, session management, and test UI.

**Spec**: [`features/phase4-oauth-login.md`](../features/phase4-oauth-login.md)

**Deliverables:**
- Google OAuth2 browser login flow (authorize → callback → session)
- `POST /auth/refresh` — refresh token exchange
- Pluggable `SessionStore` protocol with in-memory implementation
- Minimal Jinja2+HTMX test UI for browser login testing
- Legacy bug fixes: `can_issue` enforcement, `data=` vs `params=` for token endpoint

**Dependencies:** `authlib>=1.0`, `jinja2`, `itsdangerous`

**GCP Guide:** `docs/GUIDE-oauth-consent-screen.md`

---

## Phase 5: RBAC — PLANNED

> Role-based access control with GCP Secret Manager storage, TTL-cached permission resolution.

**Spec**: [`features/phase5-rbac.md`](../features/phase5-rbac.md)

**Deliverables:**
- RBAC data model — `Role`, `Grant`, `ServiceGrants` (pydantic)
- `SecretsStorage` — GCP Secret Manager backend for RBAC data
- `Authority` — permission resolution engine with TTL cache (RBAC_CACHE_TTL)
- `GET /auth/has/{subject}/{target}/{permission}` — path-based permission check
- `GET /auth/has` — query-based permission check
- Legacy bug fix: "status" → "subject" error message typo

**Dependencies:** `google-cloud-secret-manager`

**GCP Guide:** `docs/GUIDE-secret-manager.md`

---

## Phase 6: RBAC Management + CLI — PLANNED

> CRUD endpoints for roles/grants, Typer CLI tool, and minimal admin UI.

**Spec**: [`features/phase6-rbac-management.md`](../features/phase6-rbac-management.md)

**Deliverables:**
- RBAC CRUD REST endpoints at `/admin/*` (new — not in legacy)
- CLI tool via Typer: role, service, test, token commands
- Admin UI — Jinja2+HTMX at `/admin/*` with roles/grants tables
- Legacy bug fixes: revoke wildcard off-by-one, role remove ValueError

**Dependencies:** `typer>=0.9`

**GCP Guide:** None
