# Implementation Alignment Report

*Generated: 2026-03-16*
*Last updated: 2026-03-18*
*Purpose: Identify inconsistencies between blueprint docs and actual implementation state.*

---

## Resolved Items

1. ~~Routes had local `_get_*` helpers instead of using dependencies~~ — DONE (2026-03-18)
   - Created `state.py` with bridge dependencies (`get_admin_storage`, `get_authority`, `get_session_store`)
   - Migrated `admin.py` and `admin_ui.py` to `Annotated[X, Depends(...)]` params
   - Only `_admin_writes_enabled` remains as a local helper (template rendering hint, not a dependency)

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

## ToDo Items

Clean up the allow gate versus info patterns in routers and dependencies.
- allow gates should be on routers only
- info dependencies should work for cookie or refresh etc.
- id like the routes to generally Depend on the pure objects they need (DI bridges) and then decide if its a refresh or cookie or jwt at the route, then delegate to the right utility based on that. seems like cleaner logic.
- ASK for a diagram and tree like map or table of what routes need what etc. it should be a DAG and i basically want the DI DAG to be as clean or ordered as it can be

---

## Phase 11 Implementation Edges (discovered 2026-03-19)

Attempted Phase 11 route reorg and hit several structural issues that need resolution
before implementation can proceed cleanly. Reverted all code changes.

### Edge 1: `allow_session` raises 307 redirect (UI concern in auth gate)

**Problem**: `allow_session` in `dependencies.py` raises `HTTPException(status_code=307, headers={"Location": "/ui/login"})` on failure. This bakes UI redirect behavior into a pure auth gate. The new session API routes (`/auth/session/*`) need `allow_session` to return 401 (pure gate), but changing it breaks the admin UI.

**Consumers today**:
- `allow_session_admin` (chains on `allow_session`) → used by `admin_ui.py` router-level dep
- That's it. `ui.py` has its own independent `require_ui_session` that handles redirects separately.

**Decision needed**: How to decouple auth failure (401) from UI redirect (307). Options explored:
1. App-level exception handler converting 401→redirect for `/ui/*` paths — works but the handler catches ALL HTTPExceptions and must preserve headers (Location for 307s from other sources), gets messy fast.
2. Deprecated shim gates (`deprecated_allow_session_ui`, `deprecated_allow_session_admin`) — functional but ugly naming, tech debt.
3. Proper fix: `allow_*` gates always return 401/403. UI routes handle redirects at their layer.

**Recommendation**: Fix this as part of a broader UI cleanup (see backlog item "Admin UI Cleanup"). For Phase 11, the temporary deprecated shim approach works but should be planned as a pre-step with clear naming.

### Edge 2: Two separate session auth paths

**Current state**: There are two independent session-checking mechanisms:
1. `allow_session` in `dependencies.py` — used by `allow_session_admin` → `admin_ui.py`
2. `require_ui_session` in `routes/ui.py` — used by dashboard route

Both check cookie → session store, but they're completely separate implementations. Neither supports refresh_token.

**Impact on Phase 11**: The new `allow_session` needs to support both cookie and refresh_token. The `get_session_user` info dependency also needs refresh_token support. This means extracting refresh_token from JSON body (`_extract_refresh_token` helper), which adds complexity to the dependency.

### Edge 3: `get_session_user` info dep needs refresh_token support

**Problem**: `get_session_user` currently only resolves from cookie. The new session routes need it to also check refresh_token in the request body (same resolution order as `allow_session`).

**Design question**: Should info deps do body parsing? The `_extract_refresh_token` helper reads `request.json()` which consumes the body. FastAPI caches it, but it's a non-obvious side effect for an info dependency.

### Edge 4: Profile claims on AuthCodeEntry

**Problem**: `POST /auth/login/code` needs to return `{refresh_token, profile}`. The profile data (name, picture) exists during the OAuth callback but not during code exchange. The auth code only carries `subject` (email) and `redirect_uri`.

**Resolution**: Add `profile: dict` field to `AuthCodeEntry`. The code is short-lived (5 min, single-use), so carrying profile data is safe. `_handle_external_callback` passes profile claims from the OAuth callback through the auth code.

### Edge 5: Test blast radius

**Observation**: Route reorg touches 4 test files with ~80 test failures:
- `tests/auth/test_auth_code_flow.py` — path change (`/auth/code/exchange` → `/auth/login/code`) + response format change (returns refresh_token+profile instead of access_token)
- `tests/routes/test_exchange.py` — path change (`/auth/exchange` → `/auth/service/token`)
- `tests/routes/test_login.py` — removed endpoints (principal, sessions moved to session.py), logout GET→POST
- `tests/routes/test_token_endpoint.py` — path change (`/auth/token` → split to `/auth/session/token` + `/auth/cli/token`)

**Recommendation**: Plan test updates as explicit sub-tasks with clear mapping of old→new paths and expected behavior changes.

### Edge 6: Admin UI cleanup needed (captured in backlog)

The admin UI grew piecemeal and has several issues:
- Non-admin UI may be unnecessary (only reason to log in is admin ops)
- `is_admin` flag passed to templates to show/hide nav — excess if no non-admin UI
- Inconsistent auth patterns across `ui.py` and `admin_ui.py`
- Added to `feature-backlog.md` under "Admin UI Cleanup"

### Pre-steps before Phase 11 implementation

Based on the edges above, the recommended order is:
1. **Resolve auth gate pattern** — decide on allow_session 401 vs deprecated shims vs UI cleanup first
2. **Map the full DI DAG** — diagram all routes, their auth gates, info deps, and state bridges
3. **Then implement route reorg** — with clean patterns established, the mechanical work is straightforward
4. **Then refresh token** — builds on clean routes
5. **Then SDK** — independent workstream