# Dockmaster Project Memory

## Model preferences
- **Sonnet 4.6** — default for most coding sessions (Pass 2 unit tests, refactoring, pattern-following work)
- **Opus 4.6** — phase kickoffs, Pass 1 tracer bullet, debugging hard failures, Phase 5/6 complex coordination
- **Gemini 3 Pro** — one-off use only: GCP setup review, architecture second opinions. Not for implementation sessions.
- Rule of thumb: starting fresh or stuck → Opus. Continuing known work → Sonnet.

## Current implementation status
- Phase 1: COMPLETE (scaffold, config, health endpoint, conftest)
- Phase 2–6: PLANNED — implementation docs in `_blueprint/features/implementation-phase{N}-*.md`
- Next: Phase 2 (JWT Infrastructure) — start with Pass 1 tracer bullet

## Key files to read at session start
- `_blueprint/implementation-progress.md` — session state (created at start of Phase 2)
- `_blueprint/prompts/PROMPT-development-approaches.md` — development methodology
- `_blueprint/features/implementation-phase{N}-*.md` — current phase spec
