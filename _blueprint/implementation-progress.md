# Implementation Progress

*Last updated: 2026-03-11*

## Current Phase: Phase 2 — JWT Infrastructure
**Pass**: 2 (unit tests written, all passing)
**Status**: COMPLETE ✅

## Completed sub-tasks
- [x] Dep swap: replace `python-jose` with `PyJWT` + `cryptography`, add `pytest-mock`, add pytest markers
- [x] RSA test fixtures: session-scoped key pair in conftest + `tests/fixtures/fake_sa_key.json`
- [x] ServiceUser TDD (RED → GREEN) — `src/dockmaster/auth/jwt_signer.py` (11 tests)
- [x] ServiceRealm TDD (RED → GREEN) — `src/dockmaster/auth/jwt_verifier.py` (7 tests)
- [x] KeyCache base class TDD (TTL only) — `src/dockmaster/auth/key_cache.py` (9 tests)
- [x] GCP fixtures captured manually — IAM + OIDC certs in `tests/fixtures/gcp/`
- [x] `ServiceAccountKeyCache.update()` — GCP IAM key enumeration + Google OIDC certs (8 tests)
- [x] Auth middleware — `get_current_user` FastAPI dependency (`src/dockmaster/auth/middleware.py`)
- [x] Routes — `GET /auth/key/{kid}` and `GET /auth/claims`
- [x] Lifespan wiring — singletons in `app.state`
- [x] Full suite: 67 tests GREEN ✅

## Fixtures captured
- `tests/fixtures/gcp/iam/list_service_accounts.json` ✅
- `tests/fixtures/gcp/iam/list_keys__sa0.json` ✅
- `tests/fixtures/gcp/iam/get_public_key__sa0_key0.json` ✅
- `tests/fixtures/gcp/google_oidc/v1_certs.json` ✅

## Open items / notes
- SA key permissions TBD — the dockmaster SA may need role adjustments for IAM key enumeration
  (see `.envrc` and `_blueprint/context/gcp-dev-setup/` for setup context)
- Pass 3 (Fake classes) skipped — mocks in tests are sufficient for current scope

## Next session: Phase 3 — Token Exchange
Read `_blueprint/features/implementation-phase3-*.md` and begin Pass 1 tracer bullet.
