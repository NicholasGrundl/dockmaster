# Dockmaster Project Memory

## Model preferences
- **Sonnet 4.6** — default for most coding sessions (Pass 2 unit tests, refactoring, pattern-following work)
- **Opus 4.6** — phase kickoffs, Pass 1 tracer bullet, debugging hard failures, Phase 5/6 complex coordination
- **Gemini 3 Pro** — one-off use only: GCP setup review, architecture second opinions. Not for implementation sessions.
- Rule of thumb: starting fresh or stuck → Opus. Continuing known work → Sonnet.

## Current implementation status
- Phases 1–7: COMPLETE (scaffold through ephemeral keypair + CLI — 411 tests)
- Phase 8a: IN PROGRESS — Security audit findings (14 items), implementing fixes one by one
  - Done: S-001/S-014 (OpenAPI docs), settings refactor (app.state.settings)
  - Next: S-002 (JWT error sanitization)
- Phase 8b: COMPLETE (code quality — 20 findings, 12 implemented)
- Phase 8c: COMPLETE (deployment readiness audit — findings doc has open blockers for Phase 9)
- Phase 8d: COMPLETE (test audit — 8 findings, all implemented, 423 tests)
- Phase 9: PLANNED — Deployment (Dockerfile, Caddy, 8c blocker fixes)
- Phase 10: PLANNED — UI Tests

## Key files to read at session start
- `_blueprint/roadmap/implementation-progress.md` — session state
- `_blueprint/features/implementation-phase8a-security-audit.md` — current phase spec
- `_blueprint/features/audit-8a-security-findings.md` — security findings being fixed
- `_blueprint/features/audit-8c-deployment-readiness-findings.md` — deployment blockers (active, feeds Phase 9)
