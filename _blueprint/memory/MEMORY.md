# Dockmaster Project Memory

## Model preferences
- **Sonnet 4.6** — default for most coding sessions (Pass 2 unit tests, refactoring, pattern-following work)
- **Opus 4.6** — phase kickoffs, Pass 1 tracer bullet, debugging hard failures, Phase 5/6 complex coordination
- **Gemini 3 Pro** — one-off use only: GCP setup review, architecture second opinions. Not for implementation sessions.
- Rule of thumb: starting fresh or stuck → Opus. Continuing known work → Sonnet.

## Current implementation status
- Phase 1: COMPLETE (scaffold, config, health endpoint, conftest)
- Phase 2: COMPLETE (JWT infrastructure — ServiceUser, ServiceRealm, KeyCache, middleware, routes — 67 tests)
- Phase 3: COMPLETE (Token exchange — token_validator, exchange endpoint — 83 total tests)
- Phase 4a: COMPLETE (OAuth login + sessions — 103 total tests)
- Phase 4b: COMPLETE (Refresh + SecretsStorage + test UI — 117 total tests)
- Phase 4c: COMPLETE (Admin dashboard + UI polish — 134 total tests)
- Phase 5: COMPLETE (RBAC — models, storage, authority, permission endpoints — 177 total tests)
- Phase 6: NEAR COMPLETE (RBAC Management — admin endpoints + admin UI pages, 234 tests)
  - Remaining: UI tests, fixture capture
- Phase 6b: PLANNED (CLI + OAuth login flow)
- Phase 6c: PLANNED (Auth Surface Audit — before deployment)
- Phase 6d: PLANNED (Admin Session Revocation — admin UI to revoke user sessions, after 6c audit)
- Phase 7: PLANNED (Deployment + GCP Cleanup — after all feature phases)
- Next: Phase 6 wrap-up (UI tests, fixture capture, commit)

## Key files to read at session start
- `_blueprint/implementation-progress.md` — session state (created at start of Phase 2)
- `_blueprint/features/implementation-phase{N}-*.md` — current phase spec
