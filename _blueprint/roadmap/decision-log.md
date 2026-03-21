# Architecture Decision Log

Working decisions for the active phase. When a phase completes, decisions are flushed
to [`phase-history.md`](./phase-history.md) during alignment sessions.

For decisions from completed phases (1–9a), see [`phase-history.md`](./phase-history.md).

*Last updated: 2026-03-21*

---

## Phase 11 Replan Decisions (2026-03-20)

### D21 — SDK split to Phase 12

**Decision**: Python consumer SDK (DockmasterClient, HTTPKeyCache) moved from Phase 11 to Phase 12.
**Rationale**: Route reorg + refresh tokens are independent of the SDK. Splitting keeps Phase 11 focused and shippable. SDK depends on stable route endpoints.

### D22 — CLI OAuth gets own route pair

**Decision**: CLI login uses `GET /auth/cli/login` + `GET /auth/cli/callback` instead of branching in the main callback.
**Rationale**: Simplifies the main login callback from 3 branches (cookie, external, CLI) to 2 (cookie, external). CLI flow is completely isolated.

### D23 — OAuthFlowStore consolidation

**Decision**: Replace `oauth_state_store` (TTLStore[dict]) + `auth_code_store` (AuthCodeStore) with a single `OAuthFlowStore` containing two internal TTLStores and typed Pydantic models (`OAuthState`, `LoginTicket`).
**Rationale**: Typed models replace raw dicts. Single `consume()` searches both stores — keys are globally unique. "Login ticket" naming avoids confusion with Google's auth code.

### D24 — Session TTL for refresh tokens (1h, no renewal)

**Decision**: Refresh tokens are signed session IDs. They die with the session (SESSION_TTL default 1h). No session renewal on use.
**Rationale**: Simple and secure. Cross-domain users re-auth hourly. Session renewal (extend TTL on each refresh token use) deferred to feature backlog.

### D25 — Logout content negotiation

**Decision**: `POST /auth/logout` returns JSON `{"ok": true}` if request has `refresh_token` in body, redirects to `/ui/` for cookie-only requests.
**Rationale**: API clients (cross-domain apps) need a JSON response. Browser clients expect a redirect. Simple heuristic: presence of refresh_token body = API client.

### D26 — Remove `from __future__ import annotations` project-wide

**Decision**: Clean sweep of `from __future__ import annotations` from all source and test files.
**Rationale**: CLAUDE.md convention prohibits TYPE_CHECKING guards and future annotations. One file used TYPE_CHECKING to defer a SessionStore import — converted to a real import. Prevents isinstance issues with Pydantic models at runtime.

---

## Phase 11 Consistency Decisions (2026-03-21)

### D27 — Dependency prefix taxonomy documented in code

**Decision**: Document the `allow_*`/`needs_*`/`check_*`/`get_*` prefix taxonomy directly in module docstrings and section dividers, not just in planning docs.
**Rationale**: The taxonomy was well-documented across three blueprint docs but the actual code didn't reflect it. A developer reading `dependencies.py` or a route module should understand the pattern without reading planning docs.

### D28 — All app.state access through state bridges

**Decision**: Replace all `request.app.state.X` access in route modules with `Depends(get_*)` bridges from `state.py`. Added `get_oauth` and `get_realm` bridges to complete coverage.
**Rationale**: Consistency with the `get_*` prefix convention established in Phase 8e. Makes dependencies visible in FastAPI's dependency graph and function signatures.

### D29 — Legacy `/auth/principal` and `/auth/sessions` removed

**Decision**: Delete `GET /auth/principal` and `GET /auth/sessions` from `login.py` (and their tests).
**Rationale**: Duplicated by `GET /auth/session/principal` and `GET /auth/session/list` in `session.py`. The old endpoints had no auth gate, used inline session parsing, and `get_sessions` had an inline import.

### D30 — keys.py error responses: JSONResponse → HTTPException

**Decision**: Change `keys.py` from returning `JSONResponse` for errors to raising `HTTPException`.
**Rationale**: Every other route module uses `HTTPException` for errors. `JSONResponse` bypasses FastAPI's exception handler pipeline.
