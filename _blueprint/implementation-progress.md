# Implementation Progress

*Last updated: 2026-03-11*

## Current Phase: Phase 4a — OAuth Login + Session
**Pass**: 1 (Tracer Bullet — GCP setup + fixture capture first)
**Status**: IN PROGRESS

## Phase 4a sub-tasks
- [x] GCP setup checklist — OAuth consent screen, client ID, SM secret, redirect URI, test users
- [x] `.env` setup — ISSUER, AUTHORIZED_ISSUERS/DOMAINS/AUDIENCE, CLIENT_ID/SECRET, DEFAULT_CLIENT_ID
- [ ] `SessionStore` protocol + `InMemorySessionStore` (TDD)  <- current
- [ ] Tracer bullet: curl real Google OAuth endpoints, capture fixtures to `tests/fixtures/gcp/google_oauth/`
- [ ] OAuth client setup (`auth/oauth.py` — Authlib + Google)
- [ ] Login routes: `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/principal`
- [ ] Wire routes + session store singleton in `main.py` lifespan
- [ ] `tests/test_sessions.py` — set/get/delete/TTL (TDD)
- [ ] `tests/test_login.py` — mocked OAuth using captured fixtures
- [ ] Lint + full suite green

## Phase 4b sub-tasks (next session)
- [ ] Tracer bullet: curl Google refresh + userinfo endpoints, capture fixtures
- [ ] Secret Manager client for client secret lookup (moved forward from Phase 5)
- [ ] Refresh route: `POST /auth/refresh` (full 8-step flow)
- [ ] `tests/test_refresh.py` — mocked Google + SM using captured fixtures
- [ ] Test UI: `/ui/test` Jinja2 template + route
- [ ] Lint + full suite green

## Post-4b: Clean up + guides
- [ ] Fresh GCP setup from scratch (new client secret, rotate SA key) — purge any leaked secrets
- [ ] GCP setup guide doc (`docs/GUIDE-gcp-setup.md`)
- [ ] Local dev testing guide (`docs/GUIDE-local-dev.md`) — `.env`, uvicorn, curl/notebook walkthrough

## GCP setup checklist (verify — assume nothing works)
- [ ] OAuth consent screen configured (project, scopes, test users)
- [ ] OAuth2 Web client ID created
- [ ] Client secret generated and stored in Secret Manager as `client_id-{name}`
- [ ] Secret Manager API enabled on project
- [ ] Dockmaster SA has `roles/secretmanager.secretAccessor`
- [ ] Dockmaster SA has `roles/iam.serviceAccountKeyAdmin` (Phase 2 key enumeration)
- [ ] Authorized redirect URI: `http://localhost:8000/auth/callback`
- [ ] `.env` populated: `GOOGLE_CLIENT_ID`, `AUTHORIZED_DOMAINS`, `AUTHORIZED_ISSUERS`, `AUTHORIZED_AUDIENCE`

## Fixtures to capture (Phase 4)
- [ ] `tests/fixtures/gcp/google_oauth/token_exchange.json` — code → tokens
- [ ] `tests/fixtures/gcp/google_oauth/userinfo.json` — UserInfo API response
- [ ] `tests/fixtures/gcp/google_oauth/token_refresh.json` — refresh → new tokens
- [ ] `tests/fixtures/gcp/secret_manager/get_client_secret.json` — SM lookup

## Test status
- Full suite: 83 tests GREEN (Phase 1–3)

## Decisions log
- 2026-03-11: Phase 4 split into 4a (sessions + login) and 4b (refresh + SM + UI)
- 2026-03-11: Secret Manager client pulled forward from Phase 5 into Phase 4b
- 2026-03-11: GCP setup + fixture capture done first (tracer bullet), then build with real data
- 2026-03-11: Post-4b: rotate all GCP secrets, write setup guide from scratch so nothing leaked

## Completed phases
- Phase 1: COMPLETE (scaffold, config, health endpoint, conftest)
- Phase 2: COMPLETE (JWT infrastructure — ServiceUser, ServiceRealm, KeyCache, middleware, routes — 67 tests)
- Phase 3: COMPLETE (Token exchange — token_validator, exchange endpoint — 16 new tests, 83 total)

## Next: start Phase 4a step 1
GCP setup checklist — verify all prerequisites before writing code.
