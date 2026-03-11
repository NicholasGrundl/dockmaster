# Implementation Progress

*Last updated: 2026-03-11*

## Current Phase: Phase 3 — Token Exchange
**Pass**: 2 (unit tests written, all passing)
**Status**: COMPLETE ✅

## Sub-tasks
- [x] Settings update — `access_token_endpoint` URL updated to `https://oauth2.googleapis.com/tokeninfo` (D2)
- [x] `token_validator.py` TDD — `validate_access_token()` async function with mocked httpx (4 tests)
- [x] `ExchangeResponse` model + `routes/exchange.py` — full 8-step flow (JWT-first → tokeninfo fallback → can_issue → sign)
- [x] Route wired in `main.py` — `exchange_router` registered at `/auth`
- [x] `tests/test_exchange.py` — 12 tests (JWT path, access token path, error cases)
- [x] `tests/test_token_validator.py` — 4 tests (valid, non-200, audience mismatch, URL construction)
- [x] Lint + full suite: 83 tests GREEN ✅

## Test status
- `tests/test_token_validator.py` GREEN (4 tests)
- `tests/test_exchange.py` GREEN (12 tests)
- Full suite: 83 tests GREEN

## Decisions log
- 2026-03-11: `access_token_endpoint` default changed from v1 URL to `oauth2.googleapis.com/tokeninfo` per D2
- 2026-03-11: Exchange route uses `Depends(get_settings)` for proper test overrides (not direct `get_settings()` call)
- 2026-03-11: `ExchangeResponse` includes `claims: dict` field matching design spec
- 2026-03-11: Issuer check only applies to JWT path (tokeninfo has no `iss` field)
- 2026-03-11: Pass 1 tracer bullet skipped — no real GCP calls needed (tokeninfo is mocked, JWT uses test keys)

## Open items / notes
- No integration test against real Google tokeninfo — all tests use mocked httpx
- `_ExchangeTestClient` helper in test_exchange.py works around lifespan re-triggering real GCP clients
- SA key permissions TBD from Phase 2 still open

## Completed phases
- Phase 1: COMPLETE (scaffold, config, health endpoint, conftest)
- Phase 2: COMPLETE (JWT infrastructure — ServiceUser, ServiceRealm, KeyCache, middleware, routes — 67 tests)
- Phase 3: COMPLETE (Token exchange — token_validator, exchange endpoint — 16 new tests, 83 total)

## Next session: Phase 4 — OAuth Login + Session
Read `_blueprint/features/implementation-phase4-*.md` and begin planning.
