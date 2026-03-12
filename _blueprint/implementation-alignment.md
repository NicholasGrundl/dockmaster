# Implementation Alignment Report

*Generated: 2026-03-12*
*Last updated: 2026-03-12 (alignment session)*
*Purpose: Identify inconsistencies between blueprint docs and actual implementation state.*

---

## Resolved Items

The following were fixed during the 2026-03-12 alignment session:

1. **ROADMAP.md** — ✅ Fixed: statuses (Phases 2-4 → COMPLETE), all spec links (→ `-v2` suffix + implementation guides), Phase 4 description updated (sub-phases, Tailwind not HTMX), Phase 5/6 descriptions updated, Phase 6/6b split, date updated.

2. **decision-log.md** — ✅ Fixed: backfilled all 15+ Phase 4 decisions, added SA key split decision, added admin auth decision (RBAC-first, no API key), added Phase 6/6b split, added CLI auth decision (localhost-callback OAuth, 15min JWT).

3. **Phase 5 implementation spec** — ✅ Fixed: "already exists" annotations for SecretsStorage, lifespan singletons, `secrets_project` setting. Added SA read-only note.

4. **Phase 6 implementation spec** — ✅ Fixed: CLI moved to Phase 6b. Admin auth redesigned (RBAC-first + env whitelist, no API key). Capability gate added (503 for missing admin SA). "Already exists" section added. Admin UI pages spec added.

5. **Phase 4 implementation guide** — ✅ Marked COMPLETE in-place.

6. **Phase 4c plan** — ✅ Marked COMPLETE in-place.

7. **feature-backlog.md** — ✅ Fixed: Admin UI item updated (dashboard exists, Phase 6 extends it). FastHTML item updated (Tailwind not HTMX). Session cleanup item updated (list_all lazy cleanup noted).

8. **MEMORY.md** — ✅ Updated: current status reflects all completed phases through 4c, Phase 6/6b split.

9. **Duplicate file (polish-plan.md)** — ✅ Previously resolved (deleted).

10. **Phase 6 design spec split** — ✅ Split `phase6-rbac-management-v2.md` into Phase 6 (admin endpoints + UI) and `phase6b-cli-v2.md` (CLI + OAuth login). Both linked from ROADMAP.

11. **CLAUDE.md** — ✅ Phase status updated (Phases 2-4 COMPLETE, 6b added). Tech stack table updated (CLI → Phase 6b).

12. **`.claude/rules/development.md`** — ✅ Phase order updated to include Phase 6b.

---

## Deferred Items

### Settings edit for Phase 6 — `ADMIN_SA_KEY_FILE`
The Phase 6 spec documents the need for `ADMIN_SA_KEY_FILE` setting but the exact settings section edit was deferred (user rejected one edit). The information is captured in the "GCP SA Key Split" section and "Already Exists" section of the Phase 6 spec. Will be finalized during Phase 6 implementation planning.

### Broken reference — `PROMPT-development-approaches.md`
CLAUDE.md and `.claude/rules/development.md` reference `_blueprint/prompts/PROMPT-development-approaches.md` which doesn't exist. User will handle separately.

### CLAUDE.md — repo layout and established patterns
Repo layout section is incomplete (missing `src/`, `tests/`, `templates/`). Established patterns section is missing sessions, UI auth guard, UIConfig, SecretsStorage. Deferred — user chose status + tech stack fixes only.

---

## New Decisions Made During This Session

These are recorded in `decision-log.md` but summarized here for reference:

1. **Admin auth model**: RBAC-first (`has_permission(email, 'dockmaster', 'admin')`) + `DOCKMASTER_ADMIN_EMAILS` env whitelist fallback. No shared API key.
2. **Capability gate**: Admin SA key present → write ops enabled. Missing → 503 on writes. Reads always work.
3. **Phase 6/6b split**: Phase 6 = admin endpoints + UI. Phase 6b = CLI + OAuth login flow.
4. **CLI auth**: Localhost-callback OAuth, 15-minute JWT persisted via `platformdirs`, no refresh token.
5. **SA keys server-side only**: No SA keys on dev machines. CLI authenticates as a user via OAuth.
6. **Bootstrap**: First deploy sets `DOCKMASTER_ADMIN_EMAILS` → login → create admin role → grant to self → optionally remove whitelist.
