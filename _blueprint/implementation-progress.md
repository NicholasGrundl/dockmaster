# Implementation Progress

*Last updated: 2026-03-11*

## Current Phase: Phase 4b — Refresh + SM + Test UI
**Pass**: 2 (unit tests written, all passing)
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
- [ ] Post-4b: UI polish pass (deferred)

## Post-4b: Clean up + guides
- [ ] Fresh GCP setup from scratch (new client secret, rotate SA key) — purge any leaked secrets
- [ ] GCP setup guide doc (`docs/GUIDE-gcp-setup.md`)
- [ ] Local dev testing guide (`docs/GUIDE-local-dev.md`) — `.env`, uvicorn, curl/notebook walkthrough

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
- `tests/test_sessions.py` GREEN (9 tests)
- `tests/test_login.py` GREEN (11 tests)
- `tests/test_refresh.py` GREEN (14 tests)
- Full suite: 117 tests GREEN

## Decisions log
- 2026-03-11: Phase 4 split into 4a (sessions + login) and 4b (refresh + SM + UI)
- 2026-03-11: Secret Manager client pulled forward from Phase 5 into Phase 4b
- 2026-03-11: GCP setup + fixture capture done first (tracer bullet), then build with real data
- 2026-03-11: Post-4b: rotate all GCP secrets, write setup guide from scratch so nothing leaked
- 2026-03-11: `itsdangerous>=2.1` added as dependency (session cookie signing)
- 2026-03-11: `SessionMiddleware` from Starlette added (required by Authlib for OAuth state)
- 2026-03-11: `create_app()` calls `get_settings()` directly for middleware config (not overridable via DI)
- 2026-03-11: SA IAM role for key enumeration deferred — code handles failure gracefully

## New files (Phase 4b)
- `src/dockmaster/rbac/__init__.py`
- `src/dockmaster/rbac/storage.py` — `SecretsStorage` (partial: `_load_secret`, `_load_secret_raw`, `get_client_secret`)
- `src/dockmaster/routes/refresh.py` — `POST /auth/refresh` (8-step flow)
- `src/dockmaster/routes/ui.py` — `GET /ui/test` (minimal HTML test page)
- `src/dockmaster/templates/login_test.html` — test UI template
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

## Next session: pick up at
"Post-4b cleanup: UI polish pass, then fresh GCP setup + guides. After that, Phase 5 (RBAC)."
