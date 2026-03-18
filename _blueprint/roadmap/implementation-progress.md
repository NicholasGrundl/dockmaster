# Implementation Progress

*Last updated: 2026-03-18*

## Current Phase: Phase 8e — App Architecture Conventions
**Approach**: Three pillars — settings DI bridge, auth conventions, middleware consolidation
**Status**: COMPLETE

**Spec**: `_blueprint/features/implementation-phase8e-auth-conventions.md`

## Phase 8e sub-tasks

### Pillar 3 — Settings DI Bridge — COMPLETE
- [x] 1. Add `get_settings(request)` bridge to `config.py`, migrate all route files from `request.app.state.settings` to `Annotated[Settings, Depends(get_settings)]`
  - `get_settings(request)` reads from `app.state.settings` (Depends bridge)
  - `create_settings()` is the standalone factory (used by `create_app`)
  - Routes use `Annotated[Settings, Depends(get_settings)]`
  - 412 tests GREEN after this step

### Pillar 1 — Auth Conventions — COMPLETE
- [x] 2a. Build utilities in `auth/dependencies.py`: `verify_jwt`, `resolve_session`, `check_permission`, `verify_google_credential`
- [x] 2b. Build gates in `auth/dependencies.py`: `allow_jwt`, `allow_session`, `allow_jwt_or_session`, `allow_google_credential`, `allow_jwt_admin`, `allow_session_admin`, `needs_admin_storage`
- [x] 2c. Build info dependencies: `get_jwt_claims`, `get_session_user`, `get_google_claims`, `get_session_or_jwt_email`
- [x] 2d. Migrate routers to gate pattern: `admin.py`, `admin_ui.py`, `claims.py`, `permissions.py`, `exchange.py`, `token.py`
- [x] 2e. Update test imports (`test_admin_auth.py`, `test_admin_endpoints.py`, `test_middleware.py`, `test_exchange.py`)
- [x] 2f. Fix 503 test failures — tests now provide valid auth so gates pass, then hit route-level 503 check
- [x] 2g. Removed `auth/admin.py` — zero references in src/ or tests/
- [x] 2h. Typed credential models — `GoogleJWTCredential` and `GoogleAccessTokenCredential` replace raw dicts for `verify_google_credential` return type. Eliminates brittle `iss`-sniffing for JWT vs access token `aud` semantics.
- [x] 2i. Removed unused `user` param from 8 admin_ui POST routes (form handlers that don't render templates). Eliminates the `session_cookie` / `{session_id}` path param collision in `revoke_session_form`.
- [x] 2j. Security review of exchange error messages — collapsed `"service argument is required for access tokens"` to `"service query parameter is required"` to avoid leaking credential type info.

### Pillar 2 — Middleware Consolidation — COMPLETE
- [x] 3. Extracted `setup_middleware(app, settings)` in `main.py` — all `add_middleware` calls consolidated into one function

### Close
- [x] 4. Full test suite (412 GREEN) + lint + format — all clean

## Test status (Phase 8e)
- 412 passed, 0 failed

## Files changed (Phase 8e so far)
**config.py**: `get_settings(request)` bridge + `create_settings()` factory, `Request` import
**auth/dependencies.py**: Full rewrite — utilities (`verify_jwt`, `resolve_session`, `check_permission`, `verify_google_credential`) + gates (`allow_jwt`, `allow_session`, `allow_jwt_or_session`, `allow_google_credential`, `allow_jwt_admin`, `allow_session_admin`) + info deps (`get_jwt_claims`, `get_session_user`, `get_google_claims`, `get_session_or_jwt_email`) + system check (`needs_admin_storage`)
**routes/admin.py**: Router-level `dependencies=[Depends(allow_jwt_admin)]`, removed per-route auth deps
**routes/admin_ui.py**: Router-level `dependencies=[Depends(allow_session_admin)]`, per-route `Annotated[dict, Depends(get_session_user)]` for user data
**routes/claims.py**: Router-level `dependencies=[Depends(allow_jwt)]`, per-route `Annotated[dict, Depends(get_jwt_claims)]`
**routes/permissions.py**: Router-level `dependencies=[Depends(allow_jwt)]`, removed per-route auth deps
**routes/exchange.py**: Router-level `dependencies=[Depends(allow_google_credential)]`, per-route `Annotated[dict, Depends(get_google_claims)]`
**routes/token.py**: Router-level `dependencies=[Depends(allow_jwt_or_session)]`, per-route `Annotated[str, Depends(get_session_or_jwt_email)]`
**routes/login.py**: Migrated to `resolve_session` utility, `Annotated[Settings, Depends(get_settings)]`
**routes/ui.py**: Migrated to `resolve_session` + `check_permission` from dependencies.py
**main.py**: `create_settings()` instead of `get_settings()`
**tests/**: Updated imports and mock targets across test_admin_auth, test_admin_endpoints, test_middleware, test_exchange

## Architecture decisions (Phase 8e)

### Planning session (2026-03-17)
- Two-layer design — pure utility functions (typed args, no Depends, no app.state) + FastAPI dependency wrappers (use Depends, inject via Cookie/HTTPBearer/get_settings, call utilities)
- Utilities: `verify_jwt(token, realm)`, `resolve_session(cookie, store, secret_key)`, `check_permission(email, service, permission, authority, admin_emails)`, `verify_google_credential(token, realm, issuers, audiences, url)` — all pure, no HTTPException
- `allow_google_credential` is a full gate with underlying `verify_google_credential` utility. All credential failures return 401 (per S-013 genericization).
- No module-level `_bearer` instance — use `HTTPBearer(auto_error=False)` inline in `Annotated` types
- Dependencies use `Annotated[Settings, Depends(get_settings)]` for settings injection, then extract individual typed args for utility calls
- `Cookie(alias="session_id")` for session cookie extraction — renamed param to `session_cookie` to avoid collision with `{session_id}` path params in admin_ui routes

### Implementation session (2026-03-18)
- **Gate vs info pattern**: Router-level `dependencies=[Depends(allow_*)]` for auth gates. Separate info dependencies (`get_jwt_claims`, `get_session_user`, `get_google_claims`, `get_session_or_jwt_email`) for route data injection. Gates and info deps are NEVER the same dependency — even if they call the same utility. This keeps auth enforcement and data retrieval as separate concerns.
- **Pillar 3 bridge**: `get_settings(request)` is the Depends bridge, `create_settings()` is the standalone factory. `get_settings` lives in `config.py` (not `main.py`) to avoid circular imports — `main.py` imports routes, routes can't import from `main.py`.
- **Exchange aud handling**: Replaced brittle `iss`-sniffing with typed models (`GoogleJWTCredential`, `GoogleAccessTokenCredential`). JWT `aud` = target service, access token `aud` = OAuth client ID — now unambiguous via `isinstance` check.
- **Exchange tests**: Issuer/audience rejection tests changed from 403 to 401 — credential verification now happens in the gate, which returns 401 for all failures per S-013.
- **email: str | None on credential models**: Utility verifies credential authenticity; route decides if email is required (business logic stays in route). Matches original pattern.
- **Error message security**: Collapsed credential-type-revealing error messages. Server logs full detail, client gets generic messages.
- **Unused user params**: Removed `get_session_user` from 8 admin_ui POST routes that never used the data — legacy from pre-gate auth pattern.

## Next session: pick up at
"Phase 8e is COMPLETE. Move spec to archive. Pick next phase from ROADMAP.md."

## Previous Phase: Phase 8a — Security Audit Fix Implementation
**Approach**: Walking through each finding with user (context → education → options → fix)
**Status**: COMPLETE

**Spec**: `_blueprint/features/implementation-phase8a-security-audit.md`
**Findings**: `_blueprint/features/audit-8a-security-findings.md`

## Phase 8a sub-tasks

### Pass 1 (audit) — COMPLETE
- [x] Endpoint inventory (46 endpoints cataloged)
- [x] Auth decision DAG (Mermaid)
- [x] Information leakage audit
- [x] Auth boundary analysis
- [x] Gap analysis (14 findings: S-001 through S-014)

### Pass 2 (fix implementation) — COMPLETE
- [x] S-001: OpenAPI docs disabled by default (`ENABLE_DOCS` setting, default `False`)
- [x] S-014: Root endpoint no longer exposes docs URL when disabled (fixed alongside S-001)
- [x] Settings refactor: removed `Depends(get_settings)` anti-pattern, settings via `app.state.settings`
- [x] Test infra: `create_app(settings)`, `test_app_factory`, `auth_client` in domain conftest
- [x] Reorganized `.env.example` into logical groups with Dev/Debug section
- [x] S-002: JWT decode errors — generic 401 message, structured warning log with token fingerprint (SHA-256 truncated)
- [x] S-003: 503 detail simplified to "Write operations are not available" + warning log
- [x] S-004: Security headers middleware (`SecurityHeadersMiddleware`) — X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy. `SECURITY_HEADERS` kill-switch setting.
- [x] S-005: OAuth CSRF state moved from module-level dict to `TTLStore[dict]` (10min TTL). `AuthCodeStore` refactored onto new `TTLStore` base class in `auth/ttl_store.py`.
- [x] S-006: `MAX_TOKEN_TTL` setting (default 3600s) caps `/auth/exchange` expiry. Over-cap requests silently clamped with server-side warning log.
- [x] S-007: Documented by design in `get_current_user` docstring — audience validation is receiver responsibility, dockmaster endpoints accept any valid dockmaster-issued JWT.
- [x] S-008: `/auth/refresh` removed entirely — CLI uses short-lived JWTs (15min) + re-login on expiry. Google refresh tokens are a larger liability than the problem they solve.
- [x] S-009: Resolved by S-008 removal — endpoint that returned Google tokens is gone.
- [x] S-010: Resolved by S-008 removal — last Type B (SA-signed) JWT issuer removed.
- [x] S-011: CLI callback page now calls `history.replaceState(null, '', '/done')` to scrub token from browser history. Documented in `_CallbackHandler` docstring.
- [x] S-012: Documented in `main.py` comment. Added middleware consolidation + SessionMiddleware investigation to feature backlog.
- [x] S-013: 403 messages genericized to "Access denied". Issuer/audience/domain details logged server-side only.

## Test status
- 412 tests GREEN (removed 14 refresh tests, added 1 exchange clamping test), lint clean, format clean

## Decisions log (Phase 8a fixes)
- 2026-03-17: S-001 fix: `ENABLE_DOCS` bool setting (default `False`), not a `DEV_MODE` meta-setting. DEV_MODE deferred until 8+ settings warrant it.
- 2026-03-17: Settings refactor: replaced `Depends(get_settings)` + `lru_cache` with `app.state.settings`. Routes read `request.app.state.settings`. `create_app()` accepts optional `Settings` param. All `dependency_overrides[get_settings]` removed from tests.
- 2026-03-17: Test infra: `test_app_factory` fixture returns `TestClient`, `auth_client` moved to domain conftest (auth, routes).

## Next session: pick up at
"Phase 8a complete. Move to Phase 9 (Deployment) or address remaining backlog items."

## Previous Phase: Phase 8d — Test Audit + Implementation
**Approach**: Audit (pass 1) + implementation of findings (pass 2)
**Status**: COMPLETE

## Previous Phase: Phase 8c — Deployment Readiness
**Approach**: Document only — interview + audit (no code changes)
**Status**: COMPLETE

**Spec**: `_blueprint/features/implementation-phase8c-deployment-readiness.md`
**Output**: `_blueprint/features/audit-8c-deployment-readiness-findings.md`

## Findings summary (Phase 8c)
- 7 findings: D-010 through D-016
- 2 blockers: proxy headers (D-010), session secret default (D-011)
- 2 warnings: OpenAPI docs exposed (D-012), JWKS registry persistence (D-014)
- 2 nice-to-haves: health endpoint depth (D-015), host/port config (D-016)
- Key decisions:
  - Domain: `auth.insilicostrategy.com` (subdomain-based routing)
  - Caddy stays as OS system service (not containerized)
  - Build: local build + transfer now, GCP Artifact Registry via GitHub Actions later
  - D-010 fix: uvicorn `--proxy-headers` + new `REQUIRE_PROXY_HEADERS` middleware (default `True`)
  - D-011 fix: remove default, make `SESSION_SECRET_KEY` required (no default)
  - GCP creds: SCP key files to droplet, mount as Docker volumes
- 15-item pre-deployment checklist for Phase 9

## Previous Phase: Phase 8b — Code Quality Review
**Approach**: Document only — no code changes (Pass 1)
**Status**: COMPLETE

**Spec**: `_blueprint/features/implementation-phase8b-code-quality.md`
**Output**: `_blueprint/features/audit-8b-code-quality-findings.md`

## Phase 8b sub-tasks
### Pass 1 (catalog)
- [x] 1. Read all route modules, catalog FastAPI patterns (DI, middleware, error handling, response models)
- [x] 2. Read all auth modules, catalog naming and vocab
- [x] 3. Read all models, storage, and service modules
- [x] 4. Audit docstrings across public interfaces
- [x] 5. Review API surface from consumer perspective
- [x] 6. Write findings doc with categorized recommendations (20 findings: 7 Medium, 13 Low)
- [x] 7. Review Pass 1 findings with user

### Pass 2 (interactive decisions)
- [x] 8. Walk through all 20 findings with user
- [x] 9. Produce action plan: 12 "do now" tasks, 8 "document/backlog" items, 2 "no action"
- [x] 10. Append action plan to findings doc

## Findings summary (Phase 8b)
- 20 code quality findings: Q-001 through Q-020
- 12 implementation tasks approved (see action plan in findings doc)
- 8 documentation/backlog items
- 2 no-action items
- Key decisions: rename ServiceUser→ServiceAccountSigner, migrate refresh to Type C, rename middleware.py→dependencies.py, extract session helper, standardize logger names to __name__, add response_model everywhere

## Previous Phase: Phase 8a — Security Audit
**Approach**: Document only — no code changes
**Status**: COMPLETE

**Spec**: `_blueprint/features/implementation-phase8a-security-audit.md`
**Output**: `_blueprint/features/audit-8a-security-findings.md`

## Phase 8a findings summary
- 46 endpoints cataloged (6 public, 5 semi-public, 35 protected)
- 14 security findings: S-001 through S-014
- Top 5 pre-deployment priorities: disable OpenAPI docs, security headers, cap token expiry, audience validation, sanitize JWT errors

## Previous Phase: Phase 7 — Ephemeral Keypair + Redirect URI + Token Issuance
**Approach**: TDD for foundation modules, unit tests for endpoints
**Status**: COMPLETE

**Spec**: `_blueprint/features/implementation-phase7-ephemeral-keypair-redirect.md`
**Reference**: `_blueprint/features/planning/phase7-auth-flows-analysis.md`

## Session plan

### Session 1 — Foundation (sub-tasks 1–4)
### Session 2 — Core Endpoints (sub-tasks 5–7)
### Session 3 — New Capabilities (sub-tasks 8–12)
### Session 4 — Wrap-up (sub-tasks 10, 12, 13)

## Phase 7 sub-tasks

### Session 1 — Foundation
- [x] 1. Settings — `DOCKMASTER_TOKEN_TTL` (int, default 900), `ALLOWED_REDIRECT_URIS` (str|set[str]), `ALLOWED_ORIGINS` (str|set[str]), `JWKS_REGISTRY_PATH` (str|None) + 11 tests GREEN
- [x] 2. JWTTokenIssuer (TDD) — `auth/token_issuer.py`: generates ephemeral RSA keypair on construction, holds private key + current kid in memory only, `sign(subject, audience, ttl, extra_claims) → str`, exposes `current_kid` + `current_public_jwk` property. No I/O, no file management. 14 tests GREEN
- [x] 3. EphemeralKeyCache(KeyCache) (TDD) — added to `auth/key_cache.py`: receives `(kid, public_jwk)` from issuer at construction, loads registry from platformdirs file, adds new key with `created_at`, prunes stale keys by absolute age (`now - created_at > retention_padded`), current key never pruned. `retention` defaults to 43200s (12h), padded 1%. Pruning only at construction. 14 tests GREEN
- [x] 4. Lifespan wiring + ServiceRealm update — `ServiceRealm(key_cache)` accepts `KeyCacheLike | list[KeyCacheLike]`, normalizes to list, checks in order. Added `realm.get_key(kid)` method (searches all caches). Updated `routes/keys.py` to use `realm.get_key()`. Lifespan creates issuer → ephemeral_cache → realm with `[ephemeral_cache, sa_cache]`. 4 new multi-cache tests GREEN

### Session 2 — Core Endpoints
- [~] 5. ~~JWKS + OIDC discovery~~ — DEFERRED to backlog. Consumers will use dockmaster SDK/middleware with `/auth/key/{kid}` instead of JWKS auto-discovery. No current consumer needs standard OIDC JWKS.
- [x] 6. ServiceRealm verification — 13 tests GREEN: Type C (ephemeral) and Type A/B (SA) tokens both verify through multi-cache realm, kid routing correct, cross-restart token verification works
- [x] 7. Exchange endpoint update — switched `/auth/exchange` from `signer.get_token()` (Type B) to `token_issuer.sign()` (Type C, iss="dockmaster"). 14 tests GREEN (2 new: Type C output assertion, 503 when issuer missing). Lint fixed.

### Session 3 — New Capabilities
- [x] 8. Token endpoint — `POST /auth/token?service=<target>`: dual auth (session cookie first, Bearer JWT fallback) → Type C JWT. Returns `{access_token, token_type, expires_in, refresh_token: null}`. New `routes/token.py`. Also switched `_handle_cli_callback` in `login.py` to `token_issuer.sign()` (Type C). 9 tests GREEN
- [x] 9. Grants endpoint — `GET /auth/grants?subject=X&target=Y`: Type A auth, resolves roles → flat `target:perm` list via `Authority.get_permissions()`. 6 endpoint tests + 4 authority tests GREEN
- [x] 10. Auth code flow — `AuthCodeStore` (in-memory, single-use, 5min expiry) in `auth/auth_code.py`, extended `_validate_redirect_uri()` to check `ALLOWED_REDIRECT_URIS`, updated `/auth/callback` to generate code for external redirects (localhost still gets direct JWT), new `POST /auth/code/exchange` endpoint, `CodeExchangeRequest` pydantic model. 8 store tests + 14 endpoint tests GREEN
- [x] 11. CLI `token` command — `cli/token.py`: `dockmaster token <service>`, calls `POST /auth/token`, prints JWT to stdout. 5 tests GREEN
- [x] 12. CORS middleware — `CORSMiddleware` in `create_app()` with `ALLOWED_ORIGINS` setting, conditional (only added when origins configured). 6 tests GREEN

### Wrap-up
- [x] 13. Lint + full suite green — 411 tests GREEN (28 new), ruff clean, format clean

## Design decisions (Phase 7 planning session)
- 2026-03-16: D21 — `JWTTokenIssuer` (not `DockTokenIssuer`) — name describes function, user preference
- 2026-03-16: D22 — JWTTokenIssuer owns the private key, EphemeralKeyCache is a dumb public key store. Private keys never touch cache objects. Consistent with ServiceAccountKeyCache pattern (holds GCP creds for API auth, not signing keys).
- 2026-03-16: D23 — ServiceRealm.key_cache accepts `KeyCacheLike | list[KeyCacheLike]`, normalizes to list. Check order = construction order. Ephemeral first (local, fast), SA second (GCP, slower). Backward compatible — single cache still works.
- 2026-03-16: D24 — EphemeralKeyCache retention defaults to 12h (43200s), NOT tied to token TTL. Padded 1% for clock drift. Configurable via param for future use. If retention < TTL, tokens just expire early (secure, user gets new token).
- 2026-03-16: D25 — Pruning only at construction (restart). No mid-process rotation. Keypair is ephemeral-per-process. Mid-process rotation noted as future enhancement.
- 2026-03-16: D26 — Pruning logic: keep if kid == current_kid OR (now - entry.created_at) <= retention_padded (absolute age check). Registry stores {kid, public_jwk, created_at} per key. Corrected from original "relative to current key" approach which would never prune on fresh starts.
- 2026-03-16: D27 — Removed `realm.key_cache` property. Added `realm.get_key(kid)` method that searches all caches in order. Updated `routes/keys.py` to use it. No backward-compat shim — clean break.
- 2026-03-16: D28 — JWKS + OIDC discovery endpoints deferred to backlog. Consumers will use dockmaster SDK/middleware with `/auth/key/{kid}` instead of standard JWKS auto-discovery. SA keys would require PEM→JWK conversion that no consumer needs. Will add when external OIDC middleware integration is needed.
- 2026-03-16: D29 — Vocab unification (ServiceUser.get_token vs JWTTokenIssuer.sign) added to Phase 8a audit scope. Not blocking for Phase 7.

## New files (Phase 7, Session 1)
- `src/dockmaster/auth/token_issuer.py` — JWTTokenIssuer (ephemeral RSA signing)
- `tests/test_token_issuer.py` — 14 tests
- `tests/test_ephemeral_key_cache.py` — 14 tests

## New files (Phase 7, Session 2)
- `tests/test_realm_e2e.py` — 13 tests (Type C + Type A/B coexistence, cross-restart verification)

## Modified files (Phase 7, Session 1)
- `src/dockmaster/config.py` — 4 new settings (dockmaster_token_ttl, allowed_redirect_uris, allowed_origins, jwks_registry_path)
- `src/dockmaster/auth/key_cache.py` — added EphemeralKeyCache class
- `src/dockmaster/auth/jwt_verifier.py` — ServiceRealm accepts list of caches, added get_key() method
- `src/dockmaster/main.py` — lifespan creates JWTTokenIssuer + EphemeralKeyCache, wires multi-cache ServiceRealm
- `src/dockmaster/routes/keys.py` — uses realm.get_key() instead of realm.key_cache.get_key()
- `tests/test_config.py` — 11 new Phase 7 settings tests + fixed admin_emails env leak
- `tests/test_jwt_verifier.py` — 4 new multi-cache tests

## Modified files (Phase 7, Session 2)
- `src/dockmaster/routes/exchange.py` — switched from `signer.get_token()` to `token_issuer.sign()` (Type C)
- `tests/test_exchange.py` — updated to wire `token_issuer` instead of `signer`, added Type C output test + 503 test (14 total)
- `tests/test_token_issuer.py` — removed unused imports (lint fix)

## Test status (Phase 7, Session 1)
- `tests/test_config.py` GREEN (31 tests)
- `tests/test_token_issuer.py` GREEN (14 tests)
- `tests/test_ephemeral_key_cache.py` GREEN (14 tests)
- `tests/test_jwt_verifier.py` GREEN (11 tests — 4 new)

## Test status (Phase 7, Session 2)
- `tests/test_realm_e2e.py` GREEN (13 tests — new)
- `tests/test_exchange.py` GREEN (14 tests — 2 new)
- Full suite at session 2 close: 359 tests GREEN (15 new)

## New files (Phase 7, Session 3)
- `src/dockmaster/routes/token.py` — POST /auth/token (dual auth: session cookie + Bearer JWT)
- `src/dockmaster/cli/token.py` — CLI `dockmaster token <service>` command
- `tests/test_token_endpoint.py` — 9 tests
- `tests/test_cli_token.py` — 5 tests

## Modified files (Phase 7, Session 3)
- `src/dockmaster/main.py` — registered token_router
- `src/dockmaster/cli/main.py` — registered token_command
- `src/dockmaster/routes/login.py` — CLI callback switched from signer.get_token() to token_issuer.sign() (Type C)
- `src/dockmaster/rbac/authority.py` — added get_permissions() method
- `src/dockmaster/routes/permissions.py` — added GET /auth/grants endpoint
- `tests/test_authority.py` — 4 new get_permissions tests
- `tests/test_permissions.py` — 6 new grants endpoint tests

## Test status (Phase 7, Session 3)
- `tests/test_token_endpoint.py` GREEN (9 tests — new)
- `tests/test_cli_token.py` GREEN (5 tests — new)
- `tests/test_authority.py` GREEN (14 tests — 4 new)
- `tests/test_permissions.py` GREEN (16 tests — 6 new)
- Full suite: 383 tests GREEN (39 new across sessions 2+3, 0 regressions)
- Manual E2E: `dockmaster token billing` verified against live dev server

## New files (Phase 7, Session 4)
- `src/dockmaster/auth/auth_code.py` — AuthCodeStore (in-memory, single-use, TTL-based expiry)
- `tests/test_auth_code.py` — 8 tests (create, consume, single-use, expiry, prune, uniqueness)
- `tests/test_auth_code_flow.py` — 14 tests (redirect URI allowlist, code exchange endpoint, callback external redirect)
- `tests/test_cors.py` — 6 tests (preflight, allowed/disallowed origins, credentials, disabled)
- `docs/GUIDE-auth-code-flow-e2e.md` — manual E2E test guide for auth code flow

## Modified files (Phase 7, Session 4)
- `src/dockmaster/main.py` — added CORSMiddleware (conditional), AuthCodeStore in lifespan
- `src/dockmaster/routes/login.py` — extended `_validate_redirect_uri()` with allowlist, added `_handle_external_callback()`, added `POST /auth/code/exchange` endpoint with `CodeExchangeRequest` model

## Test status (Phase 7, Session 4)
- `tests/test_auth_code.py` GREEN (8 tests — new)
- `tests/test_auth_code_flow.py` GREEN (14 tests — new)
- `tests/test_cors.py` GREEN (6 tests — new)
- Full suite: 411 tests GREEN (28 new, 0 regressions)

## Next session: pick up at
"Phase 8a: Security Audit — read route modules, build endpoint inventory, construct auth DAG"

## Phase 8 structure (planned 2026-03-16)
- 8a: Security Audit — endpoint inventory, auth DAG, info leakage, boundary analysis, gap analysis
- 8b: Code Quality Review — FastAPI patterns, naming/vocab, docstrings, API consistency (two-pass: catalog then optional interactive refactoring planning)
- 8c: Deployment Readiness — interview user on existing DO/Docker/Caddy stack, app readiness audit, integration plans, blockers
- 8d: Test Audit — coverage, organization, patterns, markers
- All sub-phases: document only, no code changes. Findings in `_blueprint/features/audit-8{a,b,c,d}-*-findings.md`

## Previous Phase: Phase 6c — CLI + OAuth Login
**Approach**: Build first, test after
**Status**: COMPLETE ✅

## Phase 6c sub-tasks

### Server-side prep
- [x] 1. Add `redirect_uri` param to `/auth/login` + `/auth/callback` — localhost-only validation, CLI callback mints short-lived JWT (15 min)

### CLI scaffold
- [x] 2. CLI package structure — `src/dockmaster/cli/`, Typer app, entry point in `pyproject.toml`
- [x] 3. Auth module — localhost callback server (dynamic port), browser open, token storage via `platformdirs`, expiry check

### CLI commands
- [x] 4. `login` / `logout` commands
- [x] 5. `role` command group — get, list, create, delete, add, remove (all with `-p/--permission`)
- [x] 6. `grant` command group — get, list, delete, add, remove (all with `-r/--role`)
- [x] 7. `check` command — subject + target positional, `-p/--permission` flag, Oui!/Non! output

### Wrap-up
- [x] 8. Manual E2E test — all commands verified against live server
- [x] 9. Add tests for CLI modules — 44 new tests
- [x] 10. Lint + full suite green — 301 tests, ruff clean
- [x] 11. Update progress file + spec

### Also done
- [x] Fixed dev deps: consolidated to `[dependency-groups]`, moved `pytest-mock` to dev-only
- [x] Fixed `grant add` for new services (allow_404 on GET)
- [x] Fixed `check` command to handle 204/403 response contract

## New files (Phase 6c)
- `src/dockmaster/cli/__init__.py`
- `src/dockmaster/cli/main.py` — Typer app entry point, command registration
- `src/dockmaster/cli/auth.py` — OAuth login flow (localhost callback + token storage)
- `src/dockmaster/cli/config.py` — server URL + credential path config
- `src/dockmaster/cli/http.py` — shared authenticated HTTP client
- `src/dockmaster/cli/roles.py` — role commands
- `src/dockmaster/cli/grants.py` — grant commands
- `src/dockmaster/cli/check.py` — check command
- `tests/test_cli_auth.py` — 12 tests (token storage, loading, expiry, delete)
- `tests/test_cli_roles.py` — 12 tests (list, get, create, delete, add, remove)
- `tests/test_cli_grants.py` — 12 tests (list, get, add, add-on-404, merge, remove, delete)
- `tests/test_cli_check.py` — 4 tests (granted, denied, error, flag required)
- `tests/test_cli_login_redirect.py` — 9 tests (redirect_uri validation, state storage)
- `docs/GUIDE-cli-e2e-test.md` — manual E2E test guide

## Modified files (Phase 6c)
- `src/dockmaster/routes/login.py` — `redirect_uri` param on `/auth/login`, CLI JWT minting on callback, `_pending_states` changed from `dict[str, bool]` to `dict[str, dict]`
- `pyproject.toml` — added `typer`, `platformdirs`, `[project.scripts]` entry point, consolidated `[dependency-groups]`
- `tests/test_login.py` — updated `_pending_states` format

## Test status (Phase 6c)
- `tests/test_cli_auth.py` GREEN (12 tests)
- `tests/test_cli_roles.py` GREEN (12 tests)
- `tests/test_cli_grants.py` GREEN (12 tests — includes 404 and merge scenarios)
- `tests/test_cli_check.py` GREEN (4 tests)
- `tests/test_cli_login_redirect.py` GREEN (9 tests — redirect_uri validation)
- Full suite: 301 tests GREEN (44 new)

## Decisions log (Phase 6c)
- 2026-03-12: D12 — `grant` group (not `service`) with `add`/`remove` verbs to avoid grant/grant verb collision
- 2026-03-12: D13 — `check` command (not `test`) for permission checks, with subject+target positional, -p/--permission flag
- 2026-03-12: D14 — `--permission`/`-p` for role commands, `--role`/`-r` for grant commands, short flags everywhere
- 2026-03-12: D15 — `token` command deferred to future phase (dockmaster-issued JWT design pending)
- 2026-03-12: D16 — `grant remove` without `-r` flags removes all roles for that subject
- 2026-03-12: D17 — Design full redirect URI system (for future external service redirects), build only localhost portion in 6c
- 2026-03-12: D18 — Build-first approach, test after. Single session target.
- 2026-03-12: D19 — `grant add` uses `allow_404=True` on GET (pragmatic read-modify-write pattern). Server-side merge endpoint deferred.
- 2026-03-12: D20 — Dev deps consolidated from `[project.optional-dependencies]` to `[dependency-groups]` (PEP 735 / uv standard)

## Deferred items (Phase 6c)
1. **`token` command** — deferred until dockmaster issues its own RS256 JWTs (unified token issuer design). Likely Phase 7a+ scope.
2. **External service redirect URIs** — `/auth/login` accepts `redirect_uri` but only validates localhost. Future: allowlisted per-service redirect URIs for non-dockmaster services to use dockmaster as identity broker.
3. **Server-side grant merge endpoint** — CLI does read-modify-write for `grant add/remove`. A `PATCH /admin/grants/{service}` would be atomic and simpler for future clients (SDK, other CLIs). Low priority until multi-client scenario exists.

## Previous Phase: Phase 6 — RBAC Management
**Approach**: TDD (all modules are pure logic with mocked SM client)
**Status**: COMPLETE ✅

## Phase 6 sub-tasks

### GCP setup (user-driven, before coding)
- [x] 1. Create `dockmaster-admin` SA — GCP console or `gcloud`, grant `roles/secretmanager.admin`
- [x] 2. Download admin SA key file — save locally, add `ADMIN_SA_KEY_FILE` path to `.env`
- [x] 3. Seed RBAC bootstrap data — `role-admin` + `service-grants-dockmaster` secrets created
- [x] 4. Verify admin SA works — `gcloud auth activate-service-account` + list/create/delete test

### Implementation (TDD)
- [x] 5. Settings — `ADMIN_SA_KEY_FILE`, `DOCKMASTER_ADMIN_EMAILS` in `config.py` + 6 tests GREEN
- [x] 6. SecretsStorage list methods + tests — `list_roles()`, `list_service_grants()` + 6 tests GREEN
- [x] 7. Admin auth dependencies + tests — `auth/admin.py`: `_is_admin()`, `require_admin_api`, `require_admin_writes` + 14 tests GREEN
- [x] 8. Admin ops service layer + tests — `rbac/admin_ops.py`: shared CRUD functions (storage + `authority.clear_cache()`) + 14 tests GREEN
- [x] 9. Lifespan wiring — `AdminSecretsStorage` in `main.py` (conditional on `ADMIN_SA_KEY_FILE`), `app.state.admin_storage`
- [x] 10. Admin CRUD endpoints — Roles + tests — `routes/admin.py`: `GET/POST/PUT/DELETE /admin/roles` + 17 tests GREEN
- [x] 11. Admin CRUD endpoints — Grants + tests — same file: `GET/POST/DELETE /admin/grants` (included in sub-task 10)
- [x] 12. Admin UI pages — templates + UI routes: roles page, grants page, admin nav, read-only mode
- [x] 13. Lint + full suite green — 234 tests GREEN, ruff clean

### Tracer bullet (user-driven, after code is written)
- [x] 14. Manual E2E verification — tests 1–5 PASS: create/update/delete roles, add/edit grants, all verified in SM via gcloud
- [x] 15. Fixture capture — `list_roles.json` + `list_service_grants.json` captured via Python scripts
- [x] 16. Update progress file

### Follow-up (before phase complete)
- [x] 17. Add "create new service grants" UI — form on grants list page, creates service with initial grant, redirects to detail page
- [~] 18. UI tests — DEFERRED to Phase 8 (UI still being tweaked, tests would churn)

## GCP setup checklist (Phase 6)
- [x] `dockmaster-admin` SA created
- [x] `dockmaster-admin` SA granted `roles/secretmanager.admin` on project
- [x] Admin SA key file downloaded and path added to `.env` as `ADMIN_SA_KEY_FILE`
- [x] `role-admin` secret created in SM with `{"name": "admin", "permissions": ["admin"]}`
- [x] `service-grants-dockmaster` secret created in SM with your email granted `admin` role
- [x] Verified admin SA can list/read/write secrets

## New files (Phase 6)
- `src/dockmaster/auth/admin.py` — admin auth dependencies (`_is_admin`, `require_admin_api`, `require_admin_ui`, `require_admin_writes`)
- `src/dockmaster/rbac/admin_ops.py` — shared CRUD service layer for roles + grants
- `src/dockmaster/routes/admin.py` — REST CRUD endpoints (`/admin/roles`, `/admin/grants`)
- `src/dockmaster/routes/admin_ui.py` — admin UI routes (`/ui/roles`, `/ui/grants`)
- `src/dockmaster/templates/roles.html` — roles list page with inline create/edit/delete
- `src/dockmaster/templates/grants.html` — service grants list page
- `src/dockmaster/templates/grants_detail.html` — grants detail page with inline edit
- `tests/test_admin_auth.py` — 14 tests
- `tests/test_admin_ops.py` — 14 tests
- `tests/test_admin_endpoints.py` — 17 tests
- `docs/GUIDE-admin-sa-setup.md` — admin SA setup guide (CLI + Console UI)

## Modified files (Phase 6)
- `src/dockmaster/config.py` — added `admin_sa_key_file`, `dockmaster_admin_emails`
- `src/dockmaster/rbac/storage.py` — split into `SecretsStorage` (read-only) + `AdminSecretsStorage` (writes), added `list_roles()`, `list_service_grants()`
- `src/dockmaster/main.py` — admin storage lifespan init, admin router + admin UI router registration
- `src/dockmaster/routes/ui.py` — `is_admin` context for nav links
- `src/dockmaster/templates/base.html` — admin nav links (Roles, Grants) visible when `is_admin`
- `.env.example` — documented `ADMIN_SA_KEY_FILE`, `DOCKMASTER_ADMIN_EMAILS`
- `tests/test_config.py` — 6 new admin settings tests
- `tests/test_storage.py` — 6 new list method tests, refactored for base/admin class split

## Test status (Phase 6)
- `tests/test_admin_auth.py` GREEN (14 tests)
- `tests/test_admin_ops.py` GREEN (14 tests)
- `tests/test_admin_endpoints.py` GREEN (17 tests)
- `tests/test_config.py` GREEN (20 tests — 6 new)
- `tests/test_storage.py` GREEN (17 tests — 6 new)
- Full suite: 234 tests GREEN

## Decisions log (Phase 6)
- 2026-03-12: D8 — Separate `require_admin_api` / `require_admin_ui` dependencies with shared `_is_admin()` helper. Follows Phase 4c pattern of keeping API (JWT) and UI (session) auth separate.
- 2026-03-12: D9 — Server-side form handling for UI admin pages. UI routes call shared service layer, not the API endpoints. No auth bridging needed.
- 2026-03-12: D10 — Service layer at `rbac/admin_ops.py`, admin auth at `auth/admin.py`. Both API and UI routes call `admin_ops` functions for CRUD.
- 2026-03-12: D11 — (revised) Split into `SecretsStorage` (read-only base) and `AdminSecretsStorage(SecretsStorage)` (adds write methods). Two instances with separate SM clients. Permission boundary enforced at GCP IAM level — base class physically cannot call write methods. Type annotations self-document: functions taking `SecretsStorage` are read-only, `AdminSecretsStorage` can write.

## Test plan (Phase 6)
- `tests/test_admin_auth.py` — admin auth: RBAC role, email whitelist fallback, 403 denied, capability gate 503
- `tests/test_admin_ops.py` — service layer: CRUD operations, cache invalidation calls
- `tests/test_admin_endpoints.py` — full CRUD cycle for roles and grants via API
- `tests/test_admin_ui.py` — admin UI pages: roles list, grants list, form submissions, read-only mode

## Previous Phase: Phase 5 — RBAC
**Approach**: TDD (all modules are pure logic with mocked SM client)
**Status**: COMPLETE ✅

## Phase 5 sub-tasks
- [x] 1. Fixture files — `tests/fixtures/rbac/role_viewer.json`, `service_grants_example.json`
- [x] 2. Pydantic models + tests (TDD) — `Role`, `Grant`, `ServiceGrants` + 12 tests GREEN
- [x] 3. Settings — `RBAC_CACHE_TTL: int = 300` added to config
- [x] 4. SecretsStorage RBAC methods + tests (TDD) — get/put/delete for roles + grants, `_save_secret`/`_delete_secret` + 11 tests GREEN
- [x] 5. Authority + tests (TDD) — TTL cache, `has_permission()` with `run_in_executor`, `clear_cache()` + 10 tests GREEN
- [x] 6. Permission routes + lifespan wiring + tests — `GET /auth/has/{s}/{t}/{p}`, `GET /auth/has` query, Authority singleton + 10 tests GREEN
- [x] 7. Lint + full suite green — 177 tests GREEN, ruff clean
- [x] 8. GCP Secret Manager guide — `docs/GUIDE-secret-manager.md`
- [x] 9. Update progress file

## Decisions log (Phase 5)
- 2026-03-12: No real GCP fixture capture needed — SM is gRPC-based, tests mock the Python client object directly
- 2026-03-12: `put_*`/`delete_*` methods implemented now (spec deferred to Phase 6) since Phase 6 is imminent
- 2026-03-12: `_save_secret` uses idempotent create (swallows `AlreadyExists`) then adds version
- 2026-03-12: Auth on permission endpoints uses existing `get_current_user` dependency (HTTPBearer + JWT verification)

## Previous Phase: Phase 4c — UI Polish + Admin Dashboard
**Pass**: 1 (complete — UI infrastructure, pages, tests all done)
**Status**: COMPLETE ✅

### Phase 4a: COMPLETE ✅

## Phase 4a sub-tasks
- [x] GCP setup checklist — OAuth consent screen, client ID, SM secret, redirect URI, test users
- [x] `.env` setup — ISSUER, AUTHORIZED_ISSUERS/DOMAINS/AUDIENCE, CLIENT_ID/SECRET, DEFAULT_CLIENT_ID
- [x] `SessionStore` protocol + `InMemorySessionStore` (TDD, 9 tests)
- [x] OAuth client setup (`auth/oauth.py` — Authlib + Google)
- [x] Login routes: `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/principal`
- [x] Wire routes + session store singleton in `main.py` lifespan
- [x] `tests/test_sessions.py` — 9 tests GREEN
- [x] `tests/test_login.py` — 11 tests GREEN (mocked OAuth)
- [x] Lint + full suite: 103 tests GREEN
- [x] Fixture capture guide written: `_blueprint/context/gcp-dev-setup/GUIDE-capture-oauth-fixtures.md`
- [x] Tracer bullet: captured 4 OAuth fixtures (token_exchange, userinfo, token_refresh, tokeninfo)

## Phase 4b sub-tasks
- [x] `SecretsStorage` class (partial — `_load_secret` + `get_client_secret`) in `src/dockmaster/rbac/storage.py`
- [x] Refresh route `POST /auth/refresh` (8-step flow) + `SecretsStorage` wiring in lifespan
- [x] `tests/test_refresh.py` — 14 tests GREEN (mocked Google + SM using captured fixture shapes)
- [x] Test UI: `/ui/test` minimal HTML template + route (no Jinja2 dep — manual rendering)
- [x] Lint + full suite green — 117 tests, ruff clean
- [x] Tracer bullet: SM fixture capture + E2E refresh validation (follow `GUIDE-capture-phase4b-fixtures.md`)
- [x] Manual UI testing: login ✅, session data ✅, refresh ✅, logout ✅, domain rejection ✅
- [x] Post-4b: UI polish pass (done in Phase 4c)

## Post-4b: Clean up + guides — DEFERRED TO PHASE 7
> Moved to Phase 7 (Deployment + GCP Cleanup). Will be planned after Phase 6b is complete.
- [ ] Fresh GCP setup from scratch (new client secret, rotate SA key) — purge any leaked secrets
- [ ] GCP setup guide doc (`docs/GUIDE-gcp-setup.md`)
- [ ] Local dev testing guide (`docs/GUIDE-local-dev.md`) — `.env`, uvicorn, curl/notebook walkthrough

## Phase 4c sub-tasks
- [x] 1. Install dependencies — `jinja2`, `pytest-playwright` (dev), Playwright chromium
- [x] 2. Screenshot helper — `scripts/screenshot.py` for visual verification
- [x] 3. UIConfig + theme system — `src/dockmaster/ui/config.py`, JSON config file, `UI_CONFIG_PATH` env var
- [x] 4. Base template architecture — `templates/base.html`, Tailwind CDN, CSS variables from UIConfig, nav + profile badge + footer
- [x] 5. Profile picture already in session — `PROFILE_CLAIM_KEYS` includes `picture` (no code change needed)
- [x] 6. Login page (`/ui/login`) — branded landing page with Google SSO button, public (no auth)
- [x] 7. Auth guard — `require_ui_session` dependency, redirects to `/ui/login` if unauthenticated
- [x] 8. `SessionStore.list_all()` + Dashboard page (`/ui/`) — sessions table w/ expiry, service status, replaces `/ui/test`
- [x] 9. Visual polish + screenshot iteration — GitHub-style login page, profile badge, sign out button, referrer fix for Google profile pics
- [x] 10. Tests + lint — 13 new UI tests, 4 new session tests, 134 total GREEN, ruff clean
- [x] 11. Update `implementation-progress.md`

## GCP setup checklist
- [x] OAuth consent screen configured (External, test user added)
- [x] OAuth2 Web client ID created
- [x] Client secret stored in Secret Manager as `client_id-525956676695-8o36ia4m8cvc4e00n4dhkjq2ko6ef4jk`
- [x] Secret Manager API enabled
- [x] Dockmaster SA has `roles/secretmanager.secretAccessor`
- [ ] Dockmaster SA IAM role for key enumeration — deferred, non-blocking (code handles gracefully)
- [x] Authorized redirect URI: `http://localhost:8000/auth/callback`
- [x] `.env` fully populated

## Fixtures to capture (Phase 4)
- [x] `tests/fixtures/gcp/google_oauth/token_exchange.json` — code → tokens
- [x] `tests/fixtures/gcp/google_oauth/userinfo.json` — UserInfo API response
- [x] `tests/fixtures/gcp/google_oauth/token_refresh.json` — refresh → new tokens
- [x] `tests/fixtures/gcp/google_oauth/tokeninfo.json` — tokeninfo validation
- [ ] `tests/fixtures/gcp/secret_manager/get_client_secret.json` — SM lookup (Phase 4b, capture via GUIDE-capture-phase4b-fixtures.md)

## Test status
- `tests/test_sessions.py` GREEN (13 tests — 4 new for `list_all()`)
- `tests/test_login.py` GREEN (11 tests)
- `tests/test_refresh.py` GREEN (14 tests)
- `tests/test_ui.py` GREEN (13 tests — new: login page, auth guard, dashboard)
- Full suite: 134 tests GREEN

## Decisions log
- 2026-03-11: Phase 4 split into 4a (sessions + login) and 4b (refresh + SM + UI)
- 2026-03-11: Secret Manager client pulled forward from Phase 5 into Phase 4b
- 2026-03-11: GCP setup + fixture capture done first (tracer bullet), then build with real data
- 2026-03-11: Post-4b: rotate all GCP secrets, write setup guide from scratch so nothing leaked
- 2026-03-11: `itsdangerous>=2.1` added as dependency (session cookie signing)
- 2026-03-11: `SessionMiddleware` from Starlette added (required by Authlib for OAuth state)
- 2026-03-11: `create_app()` calls `get_settings()` directly for middleware config (not overridable via DI)
- 2026-03-11: SA IAM role for key enumeration deferred — code handles failure gracefully
- 2026-03-11: Phase 4c — Jinja2 for templates (replaces manual renderer), Tailwind CSS via CDN
- 2026-03-11: Phase 4c — UIConfig as separate Pydantic model loaded from JSON file (not in core Settings, just `UI_CONFIG_PATH` pointer)
- 2026-03-11: Phase 4c — UI auth guard uses `Depends()` pattern (not middleware), redirects to `/ui/login`
- 2026-03-11: Phase 4c — API auth stays as middleware (JWT/header-based), UI auth is session/cookie-based — different patterns for different clients
- 2026-03-11: Phase 4c — Store Google profile picture URL in session data during OAuth callback
- 2026-03-12: Phase 4c — `no-referrer` meta tag needed for Google profile pic CDN (blocks requests with foreign referrer)
- 2026-03-12: Phase 4c — Refresh token tool removed from dashboard (was test-only, not admin-relevant)
- 2026-03-12: Phase 4c — Admin actions (session revoke, RBAC management) deferred to Phase 5+ when RBAC layer exists
- 2026-03-12: Phase 4c — `list_all()` returns `_expiry` metadata for display in sessions table
- 2026-03-12: Phase 4c — `jinja2` and `pytest-playwright` added as dependencies
- 2026-03-12: Phase 4c — TemplateResponse updated to new Starlette API (request as first arg)

## New files (Phase 4c)
- `src/dockmaster/ui/__init__.py`
- `src/dockmaster/ui/config.py` — `UIConfig` model + `load_ui_config()` (JSON file or defaults)
- `src/dockmaster/templates/base.html` — shared layout (Tailwind CDN, nav, profile badge, footer, CSS vars from UIConfig)
- `src/dockmaster/templates/login.html` — branded login page (no header, Google SSO button, GitHub-style)
- `src/dockmaster/templates/dashboard.html` — admin dashboard (sessions w/ expiry, service status)
- `scripts/screenshot.py` — Playwright screenshot helper
- `tests/test_ui.py` — 13 tests (login page, auth guard, dashboard)

## Modified files (Phase 4c)
- `src/dockmaster/config.py` — added `ui_config_path` setting
- `src/dockmaster/main.py` — load UIConfig in lifespan, split UI router into public + protected
- `src/dockmaster/routes/ui.py` — rewritten: Jinja2Templates, auth guard, login page, dashboard, custom `timestamp_to_datetime` filter
- `src/dockmaster/routes/login.py` — redirects changed `/ui/test` → `/ui/`
- `src/dockmaster/sessions/protocol.py` — added `list_all()` to protocol
- `src/dockmaster/sessions/memory.py` — implemented `list_all()` with TTL cleanup + `_expiry` metadata
- `tests/test_login.py` — updated redirect assertions
- `tests/test_sessions.py` — added 4 tests for `list_all()`

## New files (Phase 4b)
- `src/dockmaster/rbac/__init__.py`
- `src/dockmaster/rbac/storage.py` — `SecretsStorage` (partial: `_load_secret`, `_load_secret_raw`, `get_client_secret`)
- `src/dockmaster/routes/refresh.py` — `POST /auth/refresh` (8-step flow)
- `src/dockmaster/templates/login_test.html` — test UI template (superseded by 4c templates)
- `tests/test_refresh.py` — 14 tests

## New files (Phase 4a)
- `src/dockmaster/sessions/protocol.py` — `SessionStore` Protocol
- `src/dockmaster/sessions/memory.py` — `InMemorySessionStore`
- `src/dockmaster/auth/oauth.py` — Authlib Google config
- `src/dockmaster/routes/login.py` — login/callback/logout/principal
- `tests/test_sessions.py`, `tests/test_login.py`
- `_blueprint/context/gcp-dev-setup/GUIDE-capture-oauth-fixtures.md`

## Completed phases
- Phase 1: COMPLETE (scaffold, config, health endpoint, conftest)
- Phase 2: COMPLETE (JWT infrastructure — ServiceUser, ServiceRealm, KeyCache, middleware, routes — 67 tests)
- Phase 3: COMPLETE (Token exchange — token_validator, exchange endpoint — 16 new tests, 83 total)
- Phase 4a: COMPLETE (OAuth login + sessions — 20 new tests, 103 total)
- Phase 4b: COMPLETE (Refresh + SecretsStorage + test UI — 14 new tests, 117 total)
- Phase 4c: COMPLETE (Admin dashboard + UI polish — 17 new tests, 134 total)
- Phase 5: COMPLETE (RBAC — models, storage, authority, permission endpoints — 43 new tests, 177 total)

## Current Phase: Phase 6b — Session Revocation
**Approach**: TDD (all modules use in-memory session store, no external deps)
**Status**: COMPLETE ✅

## Phase 6b sub-tasks

### Implementation (TDD)
- [x] 1. Service layer functions + tests — 4 session functions in `admin_ops.py` + 8 tests GREEN
- [x] 2. Admin API endpoints + tests — `/admin/sessions/*` in `routes/admin.py` + 9 tests GREEN
- [x] 3. User endpoint + tests — `GET /auth/sessions` in `routes/login.py` + 3 tests GREEN
- [x] 4. Dashboard fix — filter sessions to current user, "Your Sessions" heading
- [x] 5. Admin UI sessions page — `sessions.html`, routes in `admin_ui.py`, nav link in `base.html`
- [x] 6. Lint + full suite green — 254 tests GREEN, ruff clean
- [x] 7. Update progress file

## Phase ordering (revised 2026-03-16)
- Phase 6: RBAC Management ✅
- Phase 6b: Session Revocation ✅
- Phase 6c: CLI + OAuth Login ✅
- Phase 7: Redirect URI + Ephemeral Keypair ✅
- Phase 8a: Security Audit (next)
- Phase 8b: Code Quality Review
- Phase 8c: Deployment Readiness
- Phase 8d: Test Audit
- Phase 9: Deployment + GCP Cleanup
- Phase 10: UI Tests (deferred until UI is stable)

## New files (Phase 6b)
- `src/dockmaster/templates/sessions.html` — admin sessions page with revoke controls

## Modified files (Phase 6b)
- `src/dockmaster/rbac/admin_ops.py` — added session ops: `list_sessions`, `list_sessions_by_email`, `revoke_session`, `revoke_sessions_by_email`
- `src/dockmaster/routes/admin.py` — added `/admin/sessions`, `/admin/sessions/email/{email}`, `/admin/sessions/id/{session_id}` endpoints
- `src/dockmaster/routes/login.py` — added `GET /auth/sessions` (current user's sessions)
- `src/dockmaster/routes/admin_ui.py` — added `/ui/sessions` page, revoke form handlers
- `src/dockmaster/routes/ui.py` — dashboard filters sessions to current user only
- `src/dockmaster/templates/base.html` — added "Sessions" admin nav link
- `src/dockmaster/templates/dashboard.html` — "Your Sessions" heading (was "Active Sessions")
- `tests/test_admin_ops.py` — 8 new session ops tests (22 total)
- `tests/test_admin_endpoints.py` — 9 new session endpoint tests (26 total)
- `tests/test_login.py` — 3 new /auth/sessions tests (14 total)
- `tests/test_ui.py` — updated "Your Sessions" assertion

## Test status (Phase 6b)
- Full suite: 257 tests GREEN (23 new)

## Next session: pick up at
"Phase 7 planning: Redirect URI + Ephemeral Keypair."
