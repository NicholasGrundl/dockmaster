# Phase 11 Implementation Plan — Revised

> Revised implementation plan after red-teaming the original Phase 11 spec. The original
> spec (`implementation-phase11-auth-sdk.md`) remains as reference for the end-state design.
> This plan addresses structural edges found during first implementation attempt and
> incorporates the auth gate taxonomy redesign.

**Created**: 2026-03-19
**Status**: Ready to implement
**Reference**: `_blueprint/features/planning/proposal-auth-gates.md` (auth taxonomy)
**Reference**: `_blueprint/features/implementation-phase11-auth-sdk.md` (original spec)

---

## Why This Plan Exists

The original Phase 11 spec assumed clean auth patterns. In practice, the codebase has:
- `allow_session` that throws 307 (UI redirect baked into auth gate)
- 5 different session-checking paths across modules
- Local helpers in UI routes bypassing the DI system
- Mixed-mode dependencies (`allow_jwt_or_session`) that need splitting

Attempting route reorg without fixing these first caused ~80 test failures and tangled
edge cases. This plan front-loads the auth cleanup so that route reorg and refresh token
support land cleanly.

---

## Step 0 — Foundations

> Add the new building blocks. No existing behavior changes.

### 0a. AuthResult model + check_ui_session dependency

Create `AuthResult` model and `check_ui_session` closure in `auth/dependencies.py`:

```python
class AuthResult(BaseModel):
    is_authenticated: bool
    has_permission: bool | None  # None = not checked
    user: dict                   # session data, {} if not authenticated

def check_ui_session(service: str | None = None, permission: str | None = None):
    """Soft auth check for UI routes. Returns AuthResult, never raises."""
    async def _check(...) -> AuthResult:
        ...
    return _check
```

- Default args `None` = session-only check (`has_permission = None`)
- With `service` + `permission` = also checks RBAC (`has_permission = True/False`)
- Uses `resolve_session` utility + `check_permission` utility internally

### 0b. New state bridges

Add to `state.py`:

```python
def get_ui_config(request: Request) -> UIConfig:
    return getattr(request.app.state, "ui_config", UIConfig())

def get_token_issuer(request: Request) -> EphemeralKeypairSigner | None:
    return getattr(request.app.state, "token_issuer", None)
```

### 0c. Tests for new building blocks

- Test `AuthResult` model construction
- Test `check_ui_session()` with no args returns `has_permission=None`
- Test `check_ui_session("dockmaster", "admin")` returns `has_permission=True/False`
- Test with no session → `is_authenticated=False`

### Definition of done
- [ ] `AuthResult` model exists in `auth/dependencies.py`
- [ ] `check_ui_session` closure exists in `auth/dependencies.py`
- [ ] `get_ui_config` and `get_token_issuer` exist in `state.py`
- [ ] Unit tests for `check_ui_session` pass
- [ ] All existing tests still pass (no behavior changes)

---

## Step 1 — Auth Gate Cleanup

> Fix all routes to use the consistent auth taxonomy. Same route names and paths.
> Same behavior. Just clean auth patterns.

### 1a. Fix `allow_session` — return 401 not 307

Change `allow_session` in `dependencies.py`:
- **Before**: raises `HTTPException(307, headers={"Location": "/ui/login"})`
- **After**: raises `HTTPException(401, detail="Not authenticated")`

This will break admin_ui.py (expects 307 from router gate). That's fixed in step 1c.

### 1b. Remove deprecated deps from `dependencies.py`

Remove:
- `allow_session_admin` — replaced by `check_ui_session` (step 0a)
- `allow_jwt_or_session` — split into separate `allow_session` + `allow_jwt`
- `get_session_or_jwt_email` — no longer needed

### 1c. Migrate `admin_ui.py` to soft auth

- Remove router-level `dependencies=[Depends(allow_session_admin)]`
- Add `check_ui_session("dockmaster", "admin")` as route-level dep on every route
- Each route: `if not auth.is_authenticated: return RedirectResponse("/ui/login", 307)`
- Each route: `if not auth.has_permission: return 403 template or redirect`
- Replace `get_session_user` info dep with `auth.user` (from AuthResult)
- Replace `_ui_config` import from `ui.py` with `get_ui_config` state bridge
- Remove `templates` import from `ui.py` — admin_ui should have its own templates ref
  or import from a shared location
- Fix grants GET routes: replace manual `request.app.state.secrets_storage` fallback
  with a proper pattern (e.g., `get_read_storage` bridge or explicit in route)

### 1d. Migrate `ui.py` to soft auth

- Collapse `public_router` + `protected_router` into single `router`
- Remove local helpers: `_get_session_user`, `require_ui_session`, `_redirect_to_login`, `_ui_config`
- Login page: use `check_ui_session()` (no permission args) to check if already logged in
  → redirect to dashboard
- Dashboard: use `check_ui_session("dockmaster", "admin")`
  → `if not auth.is_authenticated: redirect`
  → Use `auth.user` + `auth.has_permission` for template context
- Replace all `request.app.state.*` accesses with state bridges

### 1e. Fix `permissions.py` local helper

- Replace `_check_permission` local helper that accesses `request.app.state.authority`
  with `get_authority` state bridge as route-level dep
- Consider adding `needs_authority` system check (503) — or keep inline

### 1f. Fix `token.py` gate

- Change router gate from `allow_jwt_or_session` to `allow_jwt_or_session`... wait,
  this module gets split in Step 3. For now, keep it working with the remaining deps.
- If `allow_jwt_or_session` is removed in 1b, temporarily use `allow_session` as the gate
  (the JWT path for this endpoint moves to `cli_routes.py` in Step 3).
- Or: defer removing `allow_jwt_or_session` until Step 3 when token.py is split.

**Decision point**: Remove `allow_jwt_or_session` in Step 1 or Step 3?
- **Option A**: Remove in Step 1, temporarily gate token.py with `allow_session`.
  CLI token issuance (Bearer JWT path) breaks until Step 3 creates cli_routes.py.
- **Option B** (recommended): Keep `allow_jwt_or_session` alive until Step 3.
  Mark it deprecated. Remove when token.py is split.

### 1g. Remove `from __future__ import annotations`

Remove from all route files — violates CLAUDE.md coding preferences:
- `ui.py`, `admin_ui.py`, `login.py`, `token.py`, `exchange.py`, `claims.py`,
  `keys.py`, `admin.py`

### 1h. Update tests

Expected test changes:
- Tests asserting 307 from `allow_session` on API routes → now expect 401
- Tests importing `allow_session_admin` → removed
- Tests importing `allow_jwt_or_session` → still works if Option B
- Admin UI tests: may need adjustment for new auth pattern (check_ui_session)
- UI tests: may need adjustment for collapsed router

### Definition of done
- [ ] `allow_session` returns 401 on failure
- [ ] `allow_session_admin` removed (or marked deprecated)
- [ ] `admin_ui.py` uses `check_ui_session` per-route
- [ ] `ui.py` uses single router + `check_ui_session`
- [ ] All local helpers removed from UI routes
- [ ] `permissions.py` uses state bridge
- [ ] `from __future__ import annotations` removed from all route files
- [ ] All existing tests pass (with adjustments for 401 vs 307)

---

## Step 2 — Refresh Token Support

> Add refresh_token as an alternative to cookie for session resolution.
> No route reorg yet — just expand the session auth to accept both.

### 2a. Expand `resolve_session` utility

Update `resolve_session` in `dependencies.py` to accept a generic "handle" parameter
(cookie value OR refresh_token value — both are signed session IDs):

```python
async def resolve_session(
    handle: str | None,       # was: cookie
    session_store: object | None,
    secret_key: str,
) -> dict | None:
```

No behavior change — the function already just unsigns and looks up. The rename
clarifies that it works with any signed session handle, not just cookies.

### 2b. Update `allow_session` for refresh_token

`allow_session` tries cookie first, then refresh_token from request body:
1. Check `session_id` cookie → unsign → SessionStore.get()
2. If no cookie, check request body for `refresh_token` → unsign → SessionStore.get()
3. If neither → raise 401

Note: reading request body in a dependency — FastAPI caches it, so it's safe for
the route to also read the body later.

### 2c. Update `get_session_user` for refresh_token

Same resolution order as `allow_session`: cookie first, then refresh_token body.

### 2d. Update `check_ui_session` — cookie only

`check_ui_session` should NOT accept refresh_token. Admin UI is browser-only,
cookies are the right mechanism. No change needed (it already only checks cookie).

### 2e. Change logout to POST

In `login.py`:
- Change `GET /auth/logout` to `POST /auth/logout`
- Accept cookie OR refresh_token in request body
- Both resolve to session ID → SessionStore.delete()
- Update all templates: logout `<a>` links → `<form method="POST">`

### 2f. Tests

- Test `allow_session` with cookie → success
- Test `allow_session` with refresh_token body → success
- Test `allow_session` with neither → 401
- Test `POST /auth/logout` with cookie → session deleted
- Test `POST /auth/logout` with refresh_token body → session deleted
- Test `GET /auth/logout` → 405 Method Not Allowed
- Manual test: login via browser, verify cookie-based UI still works

### Definition of done
- [ ] `resolve_session` accepts generic handle (renamed param)
- [ ] `allow_session` checks cookie then refresh_token body
- [ ] `get_session_user` checks cookie then refresh_token body
- [ ] `check_ui_session` remains cookie-only
- [ ] Logout is POST, accepts cookie or refresh_token
- [ ] Templates updated (logout form)
- [ ] Tests pass for both cookie and refresh_token paths
- [ ] Manual browser test confirms cookie UI still works

---

## Step 2.5 — AuthCodeEntry Profile Claims

> Prerequisite for `POST /auth/login/code` which returns `{refresh_token, profile}`.

### 2.5a. Extend AuthCodeEntry

In `auth/auth_code.py`, add profile fields to `AuthCodeEntry`:

```python
class AuthCodeEntry(BaseModel):
    subject: str
    redirect_uri: str
    profile: dict = {}  # name, picture, etc. from OAuth callback
```

### 2.5b. Update `_handle_external_callback`

In `login.py`, pass profile claims from OAuth callback through to auth code:

```python
def _handle_external_callback(request, email, redirect_uri, state, profile_claims):
    code = auth_code_store.create(
        subject=email,
        redirect_uri=redirect_uri,
        profile=profile_claims,
    )
```

The callback already has `id_token_claims` with profile data — just pass it through.

### 2.5c. Tests

- Test `AuthCodeEntry` with profile data
- Test `_handle_external_callback` passes profile to auth code store

### Definition of done
- [ ] `AuthCodeEntry` has `profile: dict` field
- [ ] `_handle_external_callback` passes profile claims
- [ ] `AuthCodeStore.create()` accepts and stores profile
- [ ] Tests pass

---

## Step 3 — Route Reorganization

> With clean auth patterns and refresh token support in place, the mechanical
> route reorg should land cleanly.

### 3a. Create `routes/session.py`

New session-gated routes:

```
Router gate: allow_session (cookie OR refresh_token → 401)

GET  /auth/session/principal  — return session user data
POST /auth/session/token      — issue Type C JWT for a service
GET  /auth/session/list       — list current user's sessions
```

Move logic from:
- `login.py:get_principal` → `session.py:get_principal`
- `login.py:get_sessions` → `session.py:list_sessions`
- `token.py:issue_token` → `session.py:issue_token` (session path only)

### 3b. Create `routes/service.py`

Move exchange logic:

```
Router gate: allow_google_credential

POST /auth/service/token  — exchange Google credential for Type C JWT
```

Move from `exchange.py`. Use `get_token_issuer` state bridge.

### 3c. Create `routes/cli_routes.py`

Extract CLI token issuance:

```
Router gate: allow_jwt (Bearer JWT with aud=dockmaster)

POST /auth/cli/token  — issue Type C JWT from dockmaster JWT
```

This is the Bearer JWT path from old `token.py`.

### 3d. Create `POST /auth/login/code`

In `login.py`, replace `POST /auth/code/exchange` with `POST /auth/login/code`:

```python
@router.post("/login/code")
async def login_code(body: LoginCodeRequest, request: Request):
    # Validate auth code (existing logic)
    entry = auth_code_store.consume(body.code, redirect_uri=body.redirect_uri)
    # Create session (new)
    session_id = str(uuid4())
    session_data = {"email": entry.subject, **entry.profile}
    await session_store.set(session_id, session_data, ttl=SESSION_TTL)
    # Sign as refresh token
    refresh_token = signer.dumps(session_id)
    return {"refresh_token": refresh_token, "profile": entry.profile}
```

### 3e. Add `return_to` param on `GET /auth/login`

For cookie-mode post-login redirect (instead of hardcoded `/ui/`):
- Store `return_to` in OAuth state alongside `redirect_uri`
- After cookie set in callback, redirect to `return_to` (default `/ui/`)

### 3f. Remove old modules

- Delete `routes/token.py` (split into session.py + cli_routes.py)
- Delete `routes/exchange.py` (moved to service.py)
- Remove old endpoints from `login.py` (principal, sessions, code/exchange)

### 3g. Update `main.py` router registrations

```python
# Remove
# from dockmaster.routes.token import router as token_router
# from dockmaster.routes.exchange import router as exchange_router

# Add
from dockmaster.routes.session import router as session_router
from dockmaster.routes.service import router as service_router
from dockmaster.routes.cli_routes import router as cli_router

# Register
app.include_router(session_router, prefix="/auth")
app.include_router(service_router, prefix="/auth")
app.include_router(cli_router, prefix="/auth")
```

### 3h. Update all tests

Route rename mapping for tests:

| Old path | New path | Test file(s) |
|---|---|---|
| `POST /auth/code/exchange` | `POST /auth/login/code` | `tests/auth/test_auth_code_flow.py` |
| `POST /auth/exchange` | `POST /auth/service/token` | `tests/routes/test_exchange.py` |
| `GET /auth/principal` | `GET /auth/session/principal` | `tests/routes/test_login.py` |
| `GET /auth/sessions` | `GET /auth/session/list` | `tests/routes/test_login.py` |
| `POST /auth/token` | `POST /auth/session/token` + `POST /auth/cli/token` | `tests/routes/test_token_endpoint.py` |
| `GET /auth/logout` | `POST /auth/logout` | `tests/routes/test_login.py` |

### Definition of done
- [ ] `routes/session.py` created with all session-gated endpoints
- [ ] `routes/service.py` created (exchange → service/token)
- [ ] `routes/cli_routes.py` created (CLI token issuance)
- [ ] `POST /auth/login/code` returns `{refresh_token, profile}`
- [ ] `return_to` param on `GET /auth/login`
- [ ] `routes/token.py` and `routes/exchange.py` deleted
- [ ] `main.py` router registrations updated
- [ ] All tests updated for new paths and pass
- [ ] Full test suite green

---

## Step 4 — Python Consumer SDK

> Independent workstream. Can proceed in parallel with Step 3 if desired.

### 4a. Create `sdk/client_cache.py` — HTTPKeyCache

- Fetches public keys from `GET /auth/keys` via httpx
- Implements `KeyCacheLike` protocol
- TTL-based refresh

### 4b. Create `sdk/client.py` — DockmasterClient

- `verify_jwt(token)` — verify using HTTPKeyCache + ServiceRealm
- `has_permission(bearer_token, subject, target, permission)` — call `/auth/has`
- Permission result caching with configurable TTL

### 4c. Create `sdk/__init__.py`

- Thin re-export of `DockmasterClient`

### 4d. Import hygiene test

- Verify `from dockmaster.sdk import DockmasterClient` succeeds without
  service-only deps (no authlib, google-cloud-*, structlog, fastapi)

### 4e. SDK unit tests

- `tests/sdk/conftest.py`, `test_client.py`, `test_key_cache.py`
- Mock httpx responses for key cache, JWT verification, permission checks

### Definition of done
- [ ] `DockmasterClient.verify_jwt()` works against mock keys
- [ ] `DockmasterClient.has_permission()` works with bearer passthrough + caching
- [ ] Import hygiene test passes
- [ ] All SDK tests pass
- [ ] Full test suite green

---

## Step 5 — Close

- [ ] Full test suite pass (`uv run pytest`)
- [ ] Lint + format + types clean (`just check`)
- [ ] Manual browser test: login → dashboard → admin pages → logout
- [ ] Update `implementation-progress.md` with completion status
- [ ] Update `ROADMAP.md` Phase 11 status
- [ ] Update alignment report — mark edges as resolved
- [ ] Suggest commit

---

## Risk Register

| Risk | Mitigation |
|---|---|
| `allow_session` 401 breaks admin UI tests | Step 1c migrates admin_ui before tests run |
| Removing `allow_jwt_or_session` breaks token.py | Option B: keep it until Step 3 split |
| Refresh token body parsing in dependencies | FastAPI caches request body — test explicitly |
| Auth code profile claims change the store interface | Small change, backward-compatible (default `{}`) |
| ~80 test failures from route renames | Explicit mapping table in Step 3h, update systematically |
| `from __future__ import annotations` removal | May surface type annotation issues — fix inline |
