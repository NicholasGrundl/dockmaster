# Implementation Alignment Report

*Generated: 2026-03-16*
*Last updated: 2026-03-21*
*Purpose: Temporary triage file. Items get dispatched to feature-backlog or implementation-progress, then removed.*

---

## Resolved (this session — 2026-03-21 alignment)

All items from prior sessions have been dispatched or resolved:

1. ~~Routes had local `_get_*` helpers~~ → DONE (2026-03-18, state bridges)
2. ~~Edge 1: `allow_session` raises 307 redirect~~ → DONE (2026-03-19)
3. ~~Edge 2: Two separate session auth paths~~ → DONE (2026-03-19)
4. ~~Edge 4: Profile claims on AuthCodeEntry~~ → DONE (2026-03-19)
5. ~~Edge 7: Duplicate endpoints~~ → DONE (2026-03-21, old routes deleted)
6. ~~Edge 9: `allow_jwt_or_session` dead code~~ → DONE (2026-03-21, deleted)
7. ~~Edge 12: `from __future__ import annotations`~~ → DONE (2026-03-20, clean sweep)
8. ~~Edge 13: main.py imports OAUTH_STATE_TTL~~ → DONE (2026-03-21, OAuthFlowStore)
9. ~~ROADMAP status mismatches (Phase 9)~~ → FIXED (2026-03-21, split into 9a/9b/9c)
10. ~~Decision log gaps for completed phases~~ → FLUSHED to phase-history.md (2026-03-21)
11. ~~implementation-progress.md bloated with completed phases~~ → TRIMMED (2026-03-21, only active phases remain)

## Dispatched to implementation-progress.md (Phase 11 remaining steps)

- Edge 10: `PROFILE_CLAIM_KEYS` — noted in Step G cleanup
- Edge 14: Double body parsing — noted as known design smell
- Step H: Logout content negotiation — remaining implementation item

## Dispatched to feature-backlog.md

(No new items dispatched this session — existing backlog items are current.)

## Spring cleaning completed

- Created `phase-history.md` — append-only narrative log for all completed phases
- Slimmed `ROADMAP.md` — now a scannable index
- Trimmed `decision-log.md` — only active phase decisions; completed phases flushed to history
- Trimmed `implementation-progress.md` — only current phases (11, 9b)
- Established file role conventions (documented in this report)

### File role conventions

| File | Role | Lifecycle |
|---|---|---|
| `ROADMAP.md` | Slim index — status, one-liner, spec link per phase | Permanent |
| `phase-history.md` | Append-only narrative for completed phases | Grows during alignment sessions |
| `decision-log.md` | Working decisions for active/recent phases | Flushed to history during cleanup |
| `implementation-progress.md` | Deep index of current phase only | Trimmed when phases complete |
| `implementation-alignment.md` | Temporary triage file | Items dispatched, then cleared |
| `feature-backlog.md` | Plans for non-active phases + backlog ideas | Permanent |
