# Implementation Progress

*Last updated: 2026-03-10*

## Current Phase: Phase 2 — JWT Infrastructure
**Pass**: 1 (Tracer Bullet + TDD for pure-logic modules)
**Status**: IN PROGRESS

## Sub-tasks for current session
- [x] Dep swap: replace `python-jose` with `PyJWT` + `cryptography`, add `pytest-mock`, add pytest markers
- [x] RSA test fixtures: session-scoped key pair in conftest + `tests/fixtures/fake_sa_key.json`
- [x] ServiceUser TDD (RED → GREEN) — `src/dockmaster/auth/jwt_signer.py` (11 tests)
- [x] ServiceRealm TDD (RED → GREEN) — `src/dockmaster/auth/jwt_verifier.py` (7 tests)
- [x] KeyCache base class TDD (TTL only) — `src/dockmaster/auth/key_cache.py` (9 tests)
- [ ] `ServiceAccountKeyCache.update()` — GCP IAM key enumeration + Google OIDC certs  ← PAUSED HERE
- [ ] Auth middleware — `get_current_user` FastAPI dependency
- [ ] Routes — `GET /auth/key/{kid}` and `GET /auth/claims`
- [ ] Lifespan wiring — wire singletons into `app.state`
- [ ] Acceptance gates — full test suite, lint, format

## Fixtures captured
- `tests/fixtures/gcp/iam/list_service_accounts.json` ❌ not yet
- `tests/fixtures/gcp/iam/list_keys__sa*.json` ❌ not yet
- `tests/fixtures/gcp/iam/get_public_key__sa*_key*.json` ❌ not yet
- `tests/fixtures/gcp/google_oidc/v1_certs.json` ❌ not yet

## Test status
- `tests/test_jwt_signer.py` GREEN ✅ (11 tests)
- `tests/test_jwt_verifier.py` GREEN ✅ (7 tests)
- `tests/test_key_cache.py` GREEN ✅ (9 tests)
- Full suite: 47 tests GREEN ✅

## Open decisions / blockers
- **BLOCKED**: `ServiceAccountKeyCache.update()` requires real GCP access.
  User needs to run `uv run python scripts/capture_gcp_fixtures.py --phase 2`
  to capture IAM + OIDC fixtures before we can write the subclass + unit tests.

## Next session: pick up at
"User runs GCP capture script → implement ServiceAccountKeyCache.update() → middleware → routes → lifespan wiring"
