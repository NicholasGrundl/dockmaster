# Authentication and Protectred Routes Taxonomy

## Ui Routes

UI routers return HTML. When an auth check fails we need to convert the Exception or failure into a Redirect to another HTML route/page
- Redirect to the login page
- Redirect to the 403.error html page
- Redirect or paramterize conditionally the page (i.e. user versus admin roles, etc)

So for the UI case, there are really multiple outcomes per route depending on the condition:
┌───────────────────────┬────────────────────────────────────────────────────────────┐
│       Condition       │                          Response                          │
├───────────────────────┼────────────────────────────────────────────────────────────┤
│ No session            │ Redirect to /ui/login                                      │
├───────────────────────┼────────────────────────────────────────────────────────────┤
│ Session but not admin │ Render an "access denied" HTML page (or redirect to login) │
├───────────────────────┼────────────────────────────────────────────────────────────┤
│ Session + admin       │ Render the actual admin page                               │
└───────────────────────┴────────────────────────────────────────────────────────────┘

(optional) In the future, potentially a fourth: session + non-admin → render a limited/public view (your conditional rendering idea).   

This means the UI route really needs to control the response type at every decision point
- it can't delegate to a router level dependecy gate that raises HTTPException because that returns JSON, not HTML.
- it needs to check and return the auth state to the route so the route can decide how to delegate

### UI Route Auth pattern

The pattern is to use a "check_*" gate that returns a common auth result we can reason over

```python
class AuthResult(BaseModel):
    is_authenticated: bool
    has_permission: bool | None  # None = not checked, True/False = checked
    user: dict                   # session data, {} if not authenticated


def check_ui_session(service: str | None = None, permission: str | None = None)->AuthResult:
    ...
```

The actual Code structure is a closure allowing us to parameterize the check per route based on the permission
- Note we should put the Depends DI inside the closure for fastAPI to track it
- note in practice we should use our DI bridge states in the closure args not extract from request.app.state

```python
def check_ui_session(service: str | None = None, permission: str | None = None)->Callable[,AuthResult]:
    """Soft auth check for UI routes. Returns AuthResult, never raises.

    With no args: checks session only (has_permission = None).
    With service + permission: also checks RBAC (has_permission = True/False).

    Also returns user session data if available
    """
    async def _check(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        session_cookie: Annotated[str | None, Cookie(alias="session_id")] = None,
    ) -> AuthResult:
        store = getattr(request.app.state, "session_store", None)
        
        # Check is user in session
        data = await resolve_session(session_cookie, store, settings.session_secret_key)
        if not data:
            return AuthResult(is_authenticated=False, has_permission=None, user={})
        # Check permissions if passed
        if service is not None and permission is not None:
            authority = getattr(request.app.state, "authority", None)
            permitted = await check_permission(
                data.get("email", ""), service, permission, authority,
                whitelist_emails=settings.dockmaster_admin_emails or None,
            )
            return AuthResult(is_authenticated=True, has_permission=permitted, user=data)
        
        return AuthResult(is_authenticated=True, has_permission=None, user=data)
    
    return _check
```

An then an example route that uses this check looks like this

```python
@router.get("/roles")
async def roles_page(
    request: Request,
    auth : Annotated[AuthResult, Depends(check_ui_session("dockmaster", "admin"))],
    settings: Annotated[Settings, Depends(get_settings)],
):
    # No session → redirect to login (HTML-appropriate response)
    if not auth.is_authenticated:
        return RedirectResponse("/ui/login", 307)
    
    # No permission (i.e. not dockmaster admin)
    if not auth.has_permission:
        # Example: render "access denied" template
        # Option B: redirect to login
        # Option C: render limited view (future)
        return templates.TemplateResponse(request, "403.html", {"user": auth.user}, status_code=403)
    # Full admin view
    user = auth.user
    # ... html render logic
    html_context = {"email" : user['email']}
    return templates.TemplateResponse(request, "roles.html", {...})
```

## Auth Patterns

UI has no router-level gate at all, its always conditional (no auth means redirect condition)
- The route owns the full decision tree because every branch produces HTML even for "fail" modes.

API routes use router AND route level gates, they always return JSON (errors are JSON and handled on requester side)


### Dependency Prefix Convention(s)
┌───────────┬───────────────┬──────────────────────────────┬───────────────┬───────────────────────────┐
│ Prefix    │   Category    │           Behavior           │     Scope     │           Example         │
├───────────┼───────────────┼──────────────────────────────┼───────────────┼───────────────────────────┤
│ allow_*   │ Hard auth     │ Pass or raise 401/403        │ Router-level  │ allow_jwt, allow_session  │
├───────────┼───────────────┼──────────────────────────────┼───────────────┼───────────────────────────┤
│ needs_*.  │ Hard          │ Pass or raise 503            │ Router or     │ needs_admin_storage       │
│           │ capability    │                              │ route-level   │                           │
├───────────┼───────────────┼──────────────────────────────┼───────────────┼───────────────────────────┤
│ require_* │ Hard          │ Pass or raise 401/403.       │ Router or     │ require_admin             │
│           │ permission    │                              │ Route-level   │                           │
├───────────┼───────────────┼──────────────────────────────┼───────────────┼───────────────────────────┤
│ check_*   │ Soft auth     │ Returns AuthResult.          │ Route-level   │ check_ui_session          │
│           │               │ never raises.                │               │                           │
├───────────┼───────────────┼──────────────────────────────┼───────────────┼───────────────────────────┤
│ get_*     │ Info / data   │ Returns data or empty,       │ Route-level   │ get_session_user,         │
│           │               │ never raises                 │               │ get_jwt_claims            │
└───────────┴───────────────┴──────────────────────────────┴───────────────┴───────────────────────────┘

Hard = pass or fail, exception controls the response (JSON error).
Soft = evaluate, route controls the response (redirect, template, conditional).

### Prefix taxonomy

We use a taxonomy of function prefixes to illustrate cleraly what the auth is doing

```
HARD (raise on failure — route never executes)
├── allow_*      → auth enforcement (401/403)
│   ├── allow_jwt
│   ├── allow_session
│   ├── allow_google_credential
│   └── allow_jwt_admin   
├── needs_*      → capability check (503)
│   ├── needs_session_store
│   └── needs_admin_storage   
├── requires_*   → permission check (403)
│   ├── requires_admin
│   └── requires_viewer  
│
SOFT (never raise — route decides what to do)
├── check_*      → auth evaluation → AuthResult
│   ├── check_ui_session("dockmaster", "admin")
│   └── check_ui_session()  
└── get_*        → data/info → value or empty or None
│   ├── get_session_user()
│   ├── get_jwt_claims()
│   ├── get_authority()
│   ├── get_session_store()
|   ...
│   └── get_ui_config()
```

---

## Route Module Audit — Current vs New

Per-module audit of every route: current auth patterns, issues found, and proposed changes
under the new taxonomy.

### `health.py` — `/auth/health`, `/` (root_info)

**Type**: API (public)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `GET /auth/health` | None | None | Clean ✅ |
| `GET /` | None | None | Clean ✅ |

**New**: No changes needed.

---

### `keys.py` — `/auth/key/{kid}`

**Type**: API (public)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `GET /auth/key/{kid}` | None | None | Uses `request.app.state.realm` directly, returns JSONResponse manually for errors instead of raising HTTPException |

**New**: Add `get_realm` state bridge or leave as-is (single public endpoint, low priority).

---

### `claims.py` — `/auth/claims`

**Type**: API (Hard auth)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `GET /auth/claims` | `allow_jwt` ✅ | `get_jwt_claims` ✅ | Clean ✅ |

**New**: No changes needed. Textbook example of the pattern.

---

### `permissions.py` — `/auth/has`, `/auth/grants`

**Type**: API (Hard auth)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `GET /auth/has/{s}/{t}/{p}` | `allow_jwt` ✅ | None | ⚠️ Uses `request.app.state.authority` directly via `_check_permission` local helper |
| `GET /auth/has` | `allow_jwt` ✅ | None | Same issue |
| `GET /auth/grants` | `allow_jwt` ✅ | None | Same issue — `request.app.state.authority` directly |

**Issues**:
- `_check_permission` is a **local helper** that accesses `request.app.state.authority` directly — should use `get_authority` state bridge
- No `needs_*` check for authority being None — the local helper does it inline (503)

**New**:
```
Router gate:   allow_jwt (unchanged)
Route-level:   get_authority state bridge (replace local app.state access)
               Consider: needs_authority system check (503 if RBAC not configured)
```

---

### `exchange.py` — `/auth/exchange`

**Type**: API (Hard auth)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `POST /auth/exchange` | `allow_google_credential` ✅ | `get_google_claims` ✅, `get_settings` ✅ | ⚠️ Uses `request.app.state.token_issuer` directly |

**New** (becomes `service.py` → `POST /auth/service/token`):
```
Router gate:   allow_google_credential (unchanged)
Route-level:   get_google_claims (unchanged)
               get_token_issuer state bridge (replace app.state access)
```

---

### `token.py` — `/auth/token`

**Type**: API (Hard auth)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `POST /auth/token` | `allow_jwt_or_session` ⚠️ | `get_session_or_jwt_email` ⚠️ | Both are **mixed-mode deps** that combine JWT + session. These get split in Phase 11. Uses `request.app.state.token_issuer` directly. |

**New** (splits into two modules):

**`session.py`** — `POST /auth/session/token`, `GET /auth/session/principal`, `GET /auth/session/list`
```
Router gate:   allow_session (cookie OR refresh_token → 401)
Route-level:   get_session_user (cookie OR refresh_token → dict | {})
               get_token_issuer state bridge
               get_session_store state bridge (for /session/list)
```

**`cli_routes.py`** — `POST /auth/cli/token`
```
Router gate:   allow_jwt (Bearer JWT with aud=dockmaster)
Route-level:   get_jwt_claims
               get_token_issuer state bridge
```

**Removed deps**: `allow_jwt_or_session`, `get_session_or_jwt_email` — no longer needed.

---

### `login.py` — `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/principal`, `/auth/sessions`, `/auth/code/exchange`

**Type**: API (public OAuth flow + mixed session endpoints)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `GET /auth/login` | None | None | ⚠️ `request.app.state.oauth` directly. Needs `return_to` param (Phase 11) |
| `GET /auth/callback` | None | None | ⚠️ Multiple `request.app.state.*` accesses. `_handle_external_callback` missing profile claims on auth code |
| `GET /auth/logout` | None | None | ⚠️ Should be POST. Manual cookie/signer/session_store access. |
| `GET /auth/principal` | None | None | ⚠️ **Wrong module** — session-dependent, belongs in session.py. Manual cookie parsing via `resolve_session` directly. |
| `GET /auth/sessions` | None | None | ⚠️ **Wrong module** — session-dependent, belongs in session.py. Manual cookie parsing. Inline import. |
| `POST /auth/code/exchange` | None | None | ⚠️ Becomes `POST /auth/login/code` — needs to create session + return refresh_token + profile |

**Issues summary**:
- `get_principal` and `get_sessions` are session-dependent endpoints incorrectly living in the OAuth module — they have no auth gate at all (return `{}` if no session)
- Multiple local helpers: `_get_signer`, `_validate_redirect_uri`, `_handle_external_callback`, `_handle_cli_callback`
- All use `request.app.state.*` directly

**New**:
```
login.py (stays — public OAuth lifecycle):
  GET  /auth/login       — public, no gate. Add return_to param.
  GET  /auth/callback     — public, no gate. Add profile claims to auth code.
  POST /auth/logout       — public (best-effort). Change from GET to POST.
                            Accept cookie OR refresh_token body.
  POST /auth/login/code   — public (auth code validated in route). NEW.
                            Creates session, returns {refresh_token, profile}.

MOVED to session.py:
  GET /auth/principal → GET /auth/session/principal
  GET /auth/sessions  → GET /auth/session/list
```

---

### `admin.py` — `/admin/*`

**Type**: API (Hard auth)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `GET /admin/roles` | `allow_jwt_admin` ✅ | `get_admin_storage` ✅ | Clean ✅ |
| `GET /admin/roles/{name}` | `allow_jwt_admin` ✅ | `get_admin_storage` ✅ | Clean ✅ |
| `POST /admin/roles` | `allow_jwt_admin` ✅ | `needs_admin_storage` ✅, `get_admin_storage` ✅, `get_authority` ✅ | Clean ✅ |
| `PUT /admin/roles/{name}` | `allow_jwt_admin` ✅ | Same as above | Clean ✅ |
| `DELETE /admin/roles/{name}` | `allow_jwt_admin` ✅ | Same as above | Clean ✅ |
| `GET /admin/grants` | `allow_jwt_admin` ✅ | `get_admin_storage` ✅ | Clean ✅ |
| `GET /admin/grants/{svc}` | `allow_jwt_admin` ✅ | `get_admin_storage` ✅ | Clean ✅ |
| `POST /admin/grants/{svc}` | `allow_jwt_admin` ✅ | Full DI ✅ | Clean ✅ |
| `DELETE /admin/grants/{svc}` | `allow_jwt_admin` ✅ | Full DI ✅ | Clean ✅ |
| `GET /admin/sessions` | `allow_jwt_admin` ✅ | `needs_session_store` ✅, `get_session_store` ✅ | Clean ✅ |
| `GET /admin/sessions/email/{e}` | `allow_jwt_admin` ✅ | Same | Clean ✅ |
| `DELETE /admin/sessions/id/{id}` | `allow_jwt_admin` ✅ | Same | Clean ✅ |
| `DELETE /admin/sessions/email/{e}` | `allow_jwt_admin` ✅ | Same | Clean ✅ |

**New**: No changes needed. This module is the gold standard for the pattern. ✅

---

### `ui.py` — `/ui/login`, `/ui/` (dashboard)

**Type**: UI (Soft auth)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `GET /ui/login` | None (public_router) | None | ⚠️ Uses `_get_session_user` local helper (duplicates `resolve_session`). Uses `_ui_config` local helper. |
| `GET /ui/` (dashboard) | None (protected_router, but gate is per-route) | `require_ui_session` ⚠️ | ⚠️ `require_ui_session` is a local dep that throws 307. Multiple `request.app.state.*` accesses. Inline import. `check_permission` called directly for `is_admin` flag. |

**Issues**:
- Two routers (`public_router`, `protected_router`) — but `protected_router` has no router-level gate, protection is per-route via `require_ui_session`
- Local helpers: `_get_session_user`, `require_ui_session`, `_redirect_to_login`, `_ui_config`
- Dashboard directly accesses `request.app.state` for session_store, signer, realm, oauth, secrets_storage, authority
- `_redirect_to_login` is a function that raises (never returns) — confusing

**New**:
```
Single router (no public/protected split — login is public by not having check_*):
  GET /ui/login    — public. Use get_ui_config state bridge. Optionally check_ui_session()
                     to redirect to dashboard if already logged in.
  GET /ui/         — Soft auth: check_ui_session("dockmaster", "admin")
                     if not auth.is_authenticated → redirect to /ui/login
                     Render with auth.user, auth.has_permission for conditional content
                     Use state bridges for service status checks

REMOVED:
  _get_session_user, require_ui_session, _redirect_to_login, _ui_config (all local helpers)

ADDED state bridges:
  get_ui_config (new in state.py)
```

---

### `admin_ui.py` — `/ui/roles`, `/ui/grants`, `/ui/sessions`

**Type**: UI (Soft auth)

| Route | Current Gate | Current Route-level | Issues |
|---|---|---|---|
| `GET /ui/roles` | `allow_session_admin` ⚠️ (307 redirect) | `get_session_user`, `get_admin_storage` ✅ | Router gate throws 307 |
| `POST /ui/roles` | Same | `needs_admin_storage`, `get_admin_storage`, `get_authority` ✅ | Same |
| `POST /ui/roles/{n}/update` | Same | `needs_admin_storage`, `get_admin_storage`, `get_authority` ✅ | Same |
| `POST /ui/roles/{n}/delete` | Same | Same ✅ | Same |
| `GET /ui/grants` | Same | `get_session_user`, `get_admin_storage` | ⚠️ Manual fallback to `request.app.state.secrets_storage` |
| `POST /ui/grants/new` | Same | `needs_admin_storage`, `get_admin_storage`, `get_authority` ✅ | Same gate issue |
| `GET /ui/grants/{svc}` | Same | `get_session_user`, `get_admin_storage` | ⚠️ Same fallback |
| `POST /ui/grants/{svc}` | Same | `needs_admin_storage`, `get_admin_storage`, `get_authority` ✅ | Same gate issue |
| `POST /ui/grants/{svc}/delete` | Same | Same ✅ | Same gate issue |
| `GET /ui/sessions` | Same | `get_session_user`, `get_session_store` ✅ | Same gate issue |
| `POST /ui/sessions/{id}/revoke` | Same | `get_session_store` ✅ | Same gate issue |
| `POST /ui/sessions/revoke-by-email` | Same | `get_session_store` ✅ | Same gate issue |

**Issues**:
- Router gate `allow_session_admin` throws 307 — the core problem
- GET routes for grants have manual fallback from `admin_storage` to `secrets_storage` via `request.app.state`
- Imports `templates` and `_ui_config` from `ui.py` (cross-module dependency)

**New**:
```
Router gate:   NONE (removed — UI uses soft auth)
Route-level:   check_ui_session("dockmaster", "admin") on every route
               if not auth.is_authenticated → RedirectResponse("/ui/login")
               if not auth.has_permission → 403 template
               user = auth.user

               State bridges: get_admin_storage, get_authority, get_session_store,
                              get_ui_config (all from state.py)

               needs_admin_storage on POST routes (unchanged — 503 is fine for
               form submissions since the UI should hide the form when can_write=False)

REMOVED:
  allow_session_admin (from dependencies.py — no longer needed)
  Cross-module import of _ui_config from ui.py (replaced by get_ui_config state bridge)
  Manual secrets_storage fallback (use a get_read_storage bridge or handle in route)
```

---

### Summary: What Changes

```
REMOVED DEPS (from dependencies.py):
  allow_jwt_or_session      → split into allow_session + allow_jwt
  allow_session_admin        → replaced by check_ui_session
  get_session_or_jwt_email  → no longer needed

MODIFIED DEPS:
  allow_session             → returns 401 (not 307), supports refresh_token
  get_session_user          → supports refresh_token

NEW DEPS:
  check_ui_session(service?, permission?)  → AuthResult (closure pattern)

NEW STATE BRIDGES (state.py):
  get_ui_config             → UIConfig
  get_token_issuer          → EphemeralKeypairSigner

MODULES CLEAN (no changes):
  health.py    ✅
  claims.py    ✅
  admin.py     ✅

MODULES WITH MINOR FIXES:
  keys.py         — optional state bridge
  permissions.py  — replace local helper with state bridge

MODULES WITH MAJOR CHANGES:
  login.py     — logout GET→POST, add login/code, add return_to, move principal+sessions out
  token.py     → REMOVED, split into session.py + cli_routes.py
  exchange.py  → RENAMED to service.py, path change
  ui.py        — collapse to single router, remove local helpers, use check_ui_session + state bridges
  admin_ui.py  — remove router gate, add check_ui_session per-route, remove cross-module imports
```
