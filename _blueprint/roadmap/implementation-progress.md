# Implementation Progress

Active work across current phases. Completed phase details live in
[`phase-history.md`](./phase-history.md).

*Last updated: 2026-03-21*

---

## Current Phase: Phase 11 — Route Reorg + Refresh Token — COMPLETE

**Status**: COMPLETE
**Spec**: `_blueprint/features/implementation-phase11-route-reorg.md`
**Approach**: Incremental, isolated steps — each committable and testable independently

Key decisions:
- Cross-domain uses refresh tokens (different TLDs, cookies don't cross)
- Route reorg: session/service/cli namespaces
- Python SDK split to Phase 12 (separate scope)
- Session renewal deferred (1h SESSION_TTL acceptable for now, see feature-backlog)
- Logout uses content negotiation (JSON for API clients, redirect for browser)

### Completed

- [x] **Step 0 — Foundations** — `AuthResult` model, `check_ui_session` closure, `get_ui_config` + `get_token_issuer` state bridges
- [x] **Step 0-pre** — `from __future__ import annotations` removed from all source files
- [x] **Step 1 — Auth gate cleanup** — `allow_session` returns 401, UI routes use `check_ui_session`, `admin_ui.py` migrated, `token.py` gate → `allow_session`
- [x] **Step A — CLI OAuth extraction** — `cli_routes.py` with `/auth/cli/login`, `/auth/cli/callback`, `/auth/cli/token`. `allow_jwt` route-level on POST only.
- [x] **Step B — OAuthFlowStore** — `auth/oauth_flow_store.py` with `OAuthState`, `LoginTicket`, `OAuthFlowStore`
- [x] **Step C — Wire OAuthFlowStore** — `app.state.flow_store` replaces old stores, `get_flow_store` state bridge
- [x] **Step D — Rename callback** — `GET /auth/login/callback` (was `/auth/callback`)
- [x] **Step E — return_to support** — cookie flow + refresh token flow, open redirect prevention
- [x] **Step F — Rename exchange** — `POST /auth/login/exchange` (was `/auth/login/code` and `/auth/code/exchange`)
- [x] **State bridge standardization** — all `request.app.state` access replaced with `Depends(get_*)` bridges across all route modules. Added `get_oauth`, `get_realm` to `state.py`.
- [x] **Dependency taxonomy documentation** — `dependencies.py` and `state.py` module docstrings rewritten with full prefix taxonomy. Section dividers for allow_*/get_*/needs_*/check_* groups. Auth pattern docstrings added to all 10 route modules.
- [x] **Legacy endpoint removal** — deleted `/auth/principal` and `/auth/sessions` from `login.py` (replaced by `/auth/session/principal` and `/auth/session/list` in `session.py`)
- [x] **keys.py consistency** — `JSONResponse` errors → `HTTPException`, uses `get_realm` bridge
- [x] **Step G: Cleanup** — `PROFILE_CLAIM_KEYS` documented with cross-references in both login.py and service.py. `auth/auth_code.py` already removed. Lint + format clean.
- [x] **Step H: Logout content negotiation** — `POST /auth/logout` returns `{"ok": true}` JSON when `refresh_token` in body, redirects to `/ui/` for cookie-only requests.

### Test count
- 476 tests passing (as of 2026-03-21)

### Known design smells (not blocking)
- Edge 10: `PROFILE_CLAIM_KEYS` defined separately in login.py and service.py (intentional difference, documented with cross-reference comments)
- Edge 14: Both `allow_session` and `get_session_user` parse `request.json()` for refresh_token (safe due to FastAPI body caching)

---

## Next Phase: Phase 11b — Node.js Browser Auth SDK

**Status**: NEXT
**Spec**: `_blueprint/features/implementation-phase11b-js-sdk.md`
**Dependencies**: Phase 11 complete ✅

---

## Phase 9b — Documentation Overhaul — DEFERRED (post-deploy)

GUIDEs 01–03 complete. LEARNINGs and README updates deferred to after Phase 9c deployment.
See `feature-backlog.md` for the LEARNING outlines.
