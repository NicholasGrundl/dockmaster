# Implementation Alignment Report

*Generated: 2026-03-16*
*Last updated: 2026-03-20*
*Purpose: Identify inconsistencies between blueprint docs and actual implementation state.*

---

## Resolved Items (from prior sessions)

1. ~~Routes had local `_get_*` helpers instead of using dependencies~~ — DONE (2026-03-18)
   - Created `state.py` with bridge dependencies
   - Migrated `admin.py` and `admin_ui.py` to `Annotated[X, Depends(...)]` params

2. ~~Edge 1: `allow_session` raises 307 redirect~~ — DONE (2026-03-19)
   - `allow_session` now returns 401
   - `check_ui_session` handles UI redirect logic at the route layer

3. ~~Edge 2: Two separate session auth paths~~ — DONE (2026-03-19)
   - `require_ui_session` removed from `ui.py`
   - `ui.py` and `admin_ui.py` both use `check_ui_session`

4. ~~Edge 4: Profile claims on AuthCodeEntry~~ — DONE (2026-03-19)
   - `AuthCodeEntry.profile` field added
   - `_handle_external_callback` passes profile claims

## Established Pattern

```
allow_* gates are at the router level via dependencies=[...]

individual routes with permission or additional requirements use needs_* gates

routes that need information the allow or require gate returns should:
- add an information-only dependency to auth/dependencies.py (get_*)
- call it on the route specifically via Annotated[X, Depends(get_*)]
- this makes the Depends tree easy to follow (even if it duplicates some code from allow gates)

route modules should not make helpers for app.state access
- use state.py bridges as Annotated[X, Depends(...)] dependencies
- only use local helpers for route-specific logic (template rendering, form parsing, etc.)
```

---

## Active Edges (discovered 2026-03-20 replan session)

### Edge 7: Duplicate endpoints live simultaneously

**Problem**: `main.py` registers BOTH old routes (token_router, exchange_router) AND new routes
(session_router, service_router, cli_router). Both `/auth/token` and `/auth/session/token` exist.
Both `/auth/exchange` and `/auth/service/token` exist.

**Impact**: Tests pass, but the duplication creates confusion about canonical endpoints.
**Fix**: Step G (cleanup) removes old routes from `main.py`.

### Edge 8: POST /auth/logout returns redirect for all clients

**Problem**: Cross-domain clients sending `{"refresh_token": "..."}` get a 302 redirect to `/ui/`,
which makes no sense for API consumers.

**Decision (2026-03-20)**: Content negotiation — if request has refresh_token body, return JSON
`{"ok": true}`. If cookie-only, redirect. Added as Step H in implementation plan.

### Edge 9: `allow_jwt_or_session` is dead code

**Problem**: Nobody imports or uses it. Sitting in dependencies.py alongside commented-out
`allow_session_admin` and `get_session_or_jwt_email`.

**Fix**: Delete in Step G cleanup.

### Edge 10: `PROFILE_CLAIM_KEYS` inconsistency

**Problem**: login.py includes `"email"` in the tuple, service.py/exchange.py exclude it.
Not a bug (email handled differently in each context), but a pattern divergence.

**Fix**: Address in Step G cleanup — centralize the tuple or document the intentional difference.

### Edge 11: Refresh token session lifetime

**Problem**: Refresh token = signed session_id. Valid as long as session exists (SESSION_TTL,
default 1 hour). Cross-domain users must redo OAuth every hour.

**Decision (2026-03-20)**: Acceptable for now. Session renewal (extend TTL on use) added to
feature backlog. Inline comment added where refresh token is created.

### Edge 12: `from __future__ import annotations` in 20+ source files

**Problem**: CLAUDE.md says no TYPE_CHECKING guards or future annotations. Most non-route files
still have it. Can cause isinstance issues with Pydantic models at runtime.

**Decision (2026-03-20)**: Clean sweep as standalone commit (Step 0, done immediately).

### Edge 13: main.py imports OAUTH_STATE_TTL from login.py

**Problem**: Lifespan does `from dockmaster.routes.login import OAUTH_STATE_TTL` — route module
exporting config to app factory. Breaks when OAuthFlowStore (Step B) encapsulates the TTL.

**Fix**: Resolved by Step C (wire OAuthFlowStore).

### Edge 14: Double body parsing in session routes

**Problem**: Both `allow_session` (router gate) and `get_session_user` (info dep) parse
`request.json()` to check refresh_token. FastAPI caches body so it works.

**Decision (2026-03-20)**: Known design smell, not blocking. Note and fix later if needed.
FastAPI's body caching makes this safe.

---

## Scope Decisions (2026-03-20 replan session)

1. **SDK split**: Python SDK (DockmasterClient) moved from Phase 11 to Phase 12.
   Phase 11 focuses on route reorg + refresh tokens only.

2. **Phase 11 implementation plan**: Login-reorg doc (Steps A-G) is the canonical
   implementation checklist. Updated to Steps 0-H incorporating all edges above.
   See `implementation-progress.md` for the revised task list.

3. **v1 plan archived**: `plan-phase11-implementation.md` moved to archive (superseded by v2).
