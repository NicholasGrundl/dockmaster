# Implementation Progress

*Last updated: 2026-03-12*

## Current Phase: Phase 6c — CLI + OAuth Login
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

## Phase ordering (revised 2026-03-12)
- Phase 6: RBAC Management (wrapping up)
- Phase 6b: Session Revocation (admin API + UI + admin_ops)
- Phase 6c: CLI (wraps admin API, includes revoke command)
- Phase 7a: Auth + API Surface Audit (expanded scope)
- Phase 7b: Deployment + GCP Cleanup
- Phase 8: UI Tests (deferred until UI is stable)

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
"Phase 6c planning: CLI + OAuth login flow."
