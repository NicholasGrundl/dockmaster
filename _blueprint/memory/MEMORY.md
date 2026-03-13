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
- Phase 6: COMPLETE (RBAC Management — admin endpoints + admin UI, 234 tests)
- Phase 6b: COMPLETE (Session Revocation — admin API + UI + admin_ops — 257 tests)
- Phase 6c: COMPLETE (CLI + OAuth login — Typer CLI, browser OAuth, role/grant/check commands — 301 tests)
  - Deferred: `token` command (awaiting ephemeral keypair — Phase 7), external service redirect URIs (Phase 7), server-side grant merge endpoint
- Phase 7: PLANNED — Redirect URI + Ephemeral Keypair (next)
- Phase 8a/b/c: PLANNED — Audit subphases (inventory, auth testing, API+Caddy)
- Phase 9: PLANNED — Deployment + GCP Cleanup
- Phase 10: PLANNED — UI Tests
- Next: Phase 7 planning (Redirect URI + Ephemeral Keypair)

## Key files to read at session start
- `_blueprint/roadmap/implementation-progress.md` — session state (created at start of Phase 2)
- `_blueprint/features/implementation-phase{N}-*.md` — current phase spec
- `_blueprint/features/research-phase7-rsa256-keypair.md` — research doc for Phase 7 keypair design
