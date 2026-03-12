# Implementation Progress

*Last updated: 2026-03-12*

## Current Phase: Phase 5 — RBAC
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

## New files (Phase 5)
- `src/dockmaster/rbac/models.py` — `Role`, `Grant`, `ServiceGrants` Pydantic models
- `src/dockmaster/rbac/authority.py` — `Authority` permission resolver with TTL cache
- `src/dockmaster/routes/permissions.py` — `GET /auth/has` endpoints (path + query variants)
- `tests/test_rbac_models.py` — 12 tests
- `tests/test_storage.py` — 11 tests
- `tests/test_authority.py` — 10 tests
- `tests/test_permissions.py` — 10 tests
- `tests/fixtures/rbac/role_viewer.json`
- `tests/fixtures/rbac/service_grants_example.json`
- `docs/GUIDE-secret-manager.md`

## Modified files (Phase 5)
- `src/dockmaster/config.py` — added `rbac_cache_ttl: int = 300`
- `src/dockmaster/rbac/storage.py` — added `_save_secret`, `_delete_secret`, `get_role`, `put_role`, `delete_role`, `get_service_grants`, `put_service_grants`, `delete_service_grants`
- `src/dockmaster/main.py` — Authority singleton in lifespan, permissions router registered

## Decisions log (Phase 5)
- 2026-03-12: No real GCP fixture capture needed — SM is gRPC-based, tests mock the Python client object directly
- 2026-03-12: `put_*`/`delete_*` methods implemented now (spec deferred to Phase 6) since Phase 6 is imminent
- 2026-03-12: `_save_secret` uses idempotent create (swallows `AlreadyExists`) then adds version
- 2026-03-12: Auth on permission endpoints uses existing `get_current_user` dependency (HTTPBearer + JWT verification)

## Test status (Phase 5)
- `tests/test_rbac_models.py` GREEN (12 tests)
- `tests/test_storage.py` GREEN (11 tests)
- `tests/test_authority.py` GREEN (10 tests)
- `tests/test_permissions.py` GREEN (10 tests)
- Full suite: 177 tests GREEN

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

## Next session: pick up at
"Phase 6 (RBAC Management — admin endpoints + admin UI pages)."
