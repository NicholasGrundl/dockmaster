---
state: Finalized
changelog:
  "2026-03-20 06h": "Created from v2 plan discussion — micro-step breakdown for login reorg"
---

# Phase 11 Login Reorg — Implementation Checklist

> Step-by-step implementation guide for the login route simplification and flow store
> consolidation. Each step is isolated, committable, and testable independently.
>
> **Prerequisite**: Steps 0 and 1 (auth gate cleanup) are complete. Partial work from
> Steps 2/2.5 is in place (refresh token body support, POST logout, profile claims).

**Reference docs**:
- `plan-phase11-implementation-v2.md` — full design rationale and architecture decisions
- `oauth-sequence-diagrams.md` — cookie and refresh token flow diagrams
- `proposal-auth-gates.md` — auth gate taxonomy

**Current state of key files**:
- `src/dockmaster/routes/login.py` — still has all three flows (cookie, refresh token, CLI)
  in one callback, plus old endpoints (`principal`, `sessions`, `code/exchange`). New
  `POST /auth/login/code` added at bottom.
- `src/dockmaster/routes/cli_routes.py` — has `POST /auth/cli/token` only. Needs OAuth
  login/callback added.
- `src/dockmaster/routes/session.py` — created, has `principal`, `token`, `list` endpoints.
- `src/dockmaster/routes/service.py` — created, has `POST /auth/service/token`.
- `src/dockmaster/main.py` — registers all routers including old `token_router` and
  `exchange_router`. Has separate `oauth_state_store` and `auth_code_store` on app.state.
- `src/dockmaster/auth/auth_code.py` — `AuthCodeStore` wrapping `TTLStore`, `AuthCodeEntry`
  model with `profile` field.
- `src/dockmaster/auth/ttl_store.py` — generic `TTLStore[V]` with create/consume/prune.

---

## Step A — Extract CLI OAuth to `cli_routes.py`

> Move CLI OAuth login/callback out of login.py into cli_routes.py. This removes one
> branch from the main callback and isolates the CLI flow completely.

### What to do

1. **Move constants to `cli_routes.py`**:
   - `_LOCALHOST_RE` regex (login.py line 25)
   - `CLI_TOKEN_TTL = 900` (login.py line 153)

2. **Add `GET /auth/cli/login`** to `cli_routes.py`:
   - Accept `redirect_uri` param (required, must be localhost)
   - Validate with `_LOCALHOST_RE`
   - Create OAuth state: `oauth_state_store.create({"redirect_uri": redirect_uri})`
   - Redirect to Google with callback URI = `/auth/cli/callback`
   - **Note**: this route must NOT be behind the `allow_jwt` router gate. Either:
     - Create a separate `cli_oauth_router` without auth gates, or
     - Move the `allow_jwt` dep from router-level to route-level on `POST /auth/cli/token`

3. **Add `GET /auth/cli/callback`** to `cli_routes.py`:
   - Consume OAuth state, verify state is valid
   - Exchange Google code via `oauth.google.authorize_access_token(request)`
   - Verify email + domain (same logic as main callback)
   - Mint short-lived Type C JWT (15 min)
   - Redirect to localhost: `{redirect_uri}?token={jwt}`

4. **Remove from `login.py`**:
   - Delete `_LOCALHOST_RE`
   - Delete `CLI_TOKEN_TTL`
   - Delete `_handle_cli_callback` function (lines 174-188)
   - Remove CLI branch from callback (lines 120-121):
     ```python
     # DELETE THIS:
     if _LOCALHOST_RE.match(redirect_target):
         return _handle_cli_callback(request, email, redirect_target)
     ```

5. **Update `_validate_redirect_uri`** in login.py:
   - Remove localhost acceptance (CLI no longer goes through this path)
   - Only validates against `allowed_redirect_uris` allowlist
   - Or: remove entirely if we want to inline the check

6. **Tests**:
   - `tests/auth/test_auth_code_flow.py::TestCallbackExternalRedirect::test_localhost_redirect_still_returns_jwt`
     — this test hits the CLI branch via the main callback. Move to a CLI-specific test file
     or update to use `/auth/cli/login` + `/auth/cli/callback`.
   - Add basic tests for `GET /auth/cli/login` and `GET /auth/cli/callback`

### Router structure decision

`cli_routes.py` currently has `dependencies=[Depends(allow_jwt)]` at the router level.
CLI OAuth routes (`/auth/cli/login`, `/auth/cli/callback`) must NOT require JWT auth —
they're the entry point to *get* a JWT.

**Option 1**: Two routers in `cli_routes.py`:
```python
# Public — no auth gate
cli_oauth_router = APIRouter(tags=["cli"])

# Protected — requires JWT
cli_token_router = APIRouter(tags=["cli"], dependencies=[Depends(allow_jwt)])
```
Register both in `main.py`.

**Option 2**: Single router, no router-level gate. Move `allow_jwt` to route-level dep
on `POST /auth/cli/token` only.

Recommend **Option 2** — simpler, one router, explicit about which routes need auth.

### GCP note

`/auth/cli/callback` must be added as an authorized redirect URI in the Google OAuth
client config. This is a manual step in the GCP console. Document it but don't block on it
— the route can be built and tested with mocks first.

### Definition of done
- [ ] `GET /auth/cli/login` exists in `cli_routes.py`
- [ ] `GET /auth/cli/callback` exists in `cli_routes.py`
- [ ] `_LOCALHOST_RE`, `CLI_TOKEN_TTL`, `_handle_cli_callback` removed from `login.py`
- [ ] CLI branch removed from `login.py` callback
- [ ] `cli_routes.py` router no longer has `allow_jwt` at router level
- [ ] `POST /auth/cli/token` has `allow_jwt` as route-level dep
- [ ] Tests pass

---

## Step B — Create `OAuthFlowStore` (pure addition)

> New file, new models, new tests. No consumers wired yet. Zero risk to existing code.

### What to do

1. **Create `src/dockmaster/auth/oauth_flow_store.py`**:

   ```python
   from pydantic import BaseModel
   from dockmaster.auth.ttl_store import TTLStore

   class OAuthState(BaseModel):
       """CSRF state for an in-progress OAuth round-trip."""
       redirect_uri: str | None = None
       return_to: str | None = None

   class LoginTicket(BaseModel):
       """Pending login for an external app to claim via code exchange."""
       subject: str
       redirect_uri: str
       profile: dict = {}
       return_to: str | None = None

   class OAuthFlowStore:
       """Unified single-use store for OAuth login flow entries.

       Two internal TTLStores with independent TTLs. One consume() method
       searches both — keys are cryptographically unique so there's no ambiguity.
       """

       def __init__(self, oauth_state_ttl: int = 600, login_ticket_ttl: int = 300):
           self._oauth_states = TTLStore[OAuthState](ttl=oauth_state_ttl)
           self._login_tickets = TTLStore[LoginTicket](ttl=login_ticket_ttl)

       def create_oauth_state(self, redirect_uri: str | None = None, return_to: str | None = None) -> str:
           return self._oauth_states.create(OAuthState(redirect_uri=redirect_uri, return_to=return_to))

       def create_login_ticket(self, subject: str, redirect_uri: str, profile: dict = {}, return_to: str | None = None) -> str:
           return self._login_tickets.create(LoginTicket(subject=subject, redirect_uri=redirect_uri, profile=profile, return_to=return_to))

       def consume(self, key: str) -> OAuthState | LoginTicket | None:
           entry = self._oauth_states.consume(key)
           if entry is not None:
               return entry
           return self._login_tickets.consume(key)
   ```

2. **Create `tests/auth/test_oauth_flow_store.py`** with tests:
   - `create_oauth_state` → `consume` returns `OAuthState`
   - `create_login_ticket` → `consume` returns `LoginTicket`
   - `consume` with unknown key → `None`
   - `consume` is single-use (second consume → `None`)
   - TTL expiry works independently per type
   - Keys don't collide across internal stores
   - `LoginTicket` with profile data round-trips correctly

### Definition of done
- [ ] `auth/oauth_flow_store.py` exists with `OAuthFlowStore`, `OAuthState`, `LoginTicket`
- [ ] Unit tests pass
- [ ] No existing code changed

---

## Step C — Wire `OAuthFlowStore` into app

> Replace `oauth_state_store` + `auth_code_store` with `OAuthFlowStore` on app.state.
> Update all consumers.

### What to do

1. **Update `main.py` lifespan**:
   - Remove: `app.state.auth_code_store = AuthCodeStore(ttl=300)`
   - Remove: `app.state.oauth_state_store = TTLStore[dict](ttl=OAUTH_STATE_TTL)`
   - Remove: `from dockmaster.routes.login import OAUTH_STATE_TTL`
   - Add: `from dockmaster.auth.oauth_flow_store import OAuthFlowStore`
   - Add: `app.state.flow_store = OAuthFlowStore(oauth_state_ttl=600, login_ticket_ttl=300)`

2. **Update `login.py`**:
   - `GET /auth/login`: `oauth_state_store.create({...})` → `flow_store.create_oauth_state(...)`
   - `GET /auth/callback`: `oauth_state_store.consume(state)` → `flow_store.consume(state)`,
     check `isinstance(entry, OAuthState)`
   - Callback external branch: `auth_code_store.create(...)` → `flow_store.create_login_ticket(...)`
   - `POST /auth/login/code`: `auth_code_store.consume(...)` → `flow_store.consume(code)`,
     check `isinstance(ticket, LoginTicket) and ticket.redirect_uri == body.redirect_uri`
   - Remove `OAUTH_STATE_TTL` constant
   - Remove `from dockmaster.auth.ttl_store import TTLStore`

3. **Update `cli_routes.py`** (from Step A):
   - `GET /auth/cli/login`: use `flow_store.create_oauth_state(...)`
   - `GET /auth/cli/callback`: use `flow_store.consume(state)`

4. **Update `main.py` imports**:
   - Remove `from dockmaster.auth.auth_code import AuthCodeStore`
   - Remove `from dockmaster.auth.ttl_store import TTLStore`

5. **Tests**: Update any tests that mock or reference `oauth_state_store` / `auth_code_store`
   on app.state to use `flow_store`.

### Definition of done
- [ ] `app.state.flow_store` replaces `app.state.oauth_state_store` + `app.state.auth_code_store`
- [ ] All consumers use `OAuthFlowStore` API
- [ ] Old store references removed from lifespan
- [ ] Tests pass

---

## Step D — Rename callback to `/auth/login/callback`

> Mechanical rename. All login-related routes grouped under `/auth/login/`.

### What to do

1. **In `login.py`**: rename `@router.get("/callback")` → `@router.get("/login/callback")`
2. **In `login.py`**: update `request.url_for("callback")` → `request.url_for("login_callback")`
   (FastAPI derives the name from the function name)
3. **Rename function**: `async def callback(...)` → `async def login_callback(...)`
4. **Update tests**: any test hitting `/auth/callback` → `/auth/login/callback`
5. **GCP**: note that the authorized redirect URI in Google OAuth config must be updated
   from `/auth/callback` to `/auth/login/callback`

### Route map after this step

```
GET  /auth/login              — start OAuth
GET  /auth/login/callback     — Google redirects here (cookie + refresh token flows)
POST /auth/login/code         — exchange ticket for refresh token (renamed in Step F)
POST /auth/logout             — destroy session
GET  /auth/cli/login          — start CLI OAuth
GET  /auth/cli/callback       — Google redirects here (CLI flow)
POST /auth/cli/token          — issue JWT from Bearer JWT
```

### Definition of done
- [ ] Callback route is `GET /auth/login/callback`
- [ ] Function named `login_callback`
- [ ] `url_for` reference updated
- [ ] Tests updated
- [ ] Tests pass

---

## Step E — Add `return_to` support

> New feature: both flows accept `return_to` on `GET /auth/login`. Cookie flow uses it
> directly. Refresh token flow stores it in the login ticket and returns it in the
> exchange response.

### What to do

1. **Add `_validate_return_to` helper** in `login.py`:
   ```python
   def _validate_return_to(uri: str | None) -> str | None:
       """Validate return_to — reject absolute URLs, allow relative paths only."""
       if not uri:
           return None
       if uri.startswith(("http://", "https://", "//")):
           raise HTTPException(400, "return_to must be a relative path")
       if not uri.startswith("/"):
           raise HTTPException(400, "return_to must start with /")
       return uri
   ```

2. **Update `GET /auth/login`**:
   - Add `return_to: str | None = None` param
   - Validate with `_validate_return_to`
   - Pass to `flow_store.create_oauth_state(redirect_uri=..., return_to=validated_return_to)`

3. **Update `GET /auth/login/callback`**:
   - Cookie flow: `RedirectResponse(state_entry.return_to or "/ui/", 302)` (instead of
     hardcoded `/ui/`)
   - Refresh token flow: pass `return_to=state_entry.return_to` to
     `flow_store.create_login_ticket(...)`

4. **Update `POST /auth/login/code` response** (will be renamed in Step F):
   - Add `return_to: str | None` to `LoginCodeResponse`
   - Return `ticket.return_to` in the response

5. **Tests**:
   - `GET /auth/login?return_to=/dashboard` → stored in state
   - Cookie flow callback → redirects to `/dashboard` instead of `/ui/`
   - Cookie flow without return_to → redirects to `/ui/`
   - Refresh token flow → `return_to` appears in exchange response
   - `return_to=https://evil.com` → 400
   - `return_to=relative-no-slash` → 400

### Definition of done
- [ ] `return_to` param on `GET /auth/login`
- [ ] Validation rejects absolute URLs
- [ ] Cookie flow redirects to `return_to` (default `/ui/`)
- [ ] Refresh token flow includes `return_to` in exchange response
- [ ] Tests pass

---

## Step F — Rename `/auth/login/code` → `/auth/login/exchange`

> Mechanical rename. "Exchange" better describes what's happening.

### What to do

1. **In `login.py`**:
   - `@router.post("/login/code")` → `@router.post("/login/exchange")`
   - `LoginCodeRequest` → `LoginExchangeRequest`
   - `LoginCodeResponse` → `LoginExchangeResponse`
   - `async def login_code(...)` → `async def login_exchange(...)`

2. **Delete `POST /auth/code/exchange`** (old endpoint, lines 267-303):
   - Remove `CodeExchangeRequest` model
   - Remove `code_exchange` function

3. **Update tests**: any test hitting `/auth/login/code` → `/auth/login/exchange`,
   and `/auth/code/exchange` → deleted

### Definition of done
- [ ] Endpoint is `POST /auth/login/exchange`
- [ ] Old `POST /auth/code/exchange` deleted
- [ ] Models renamed
- [ ] Tests updated and pass

---

## Step G — Cleanup

> Delete all dead code, commented-out deps, and old modules. Final test pass.

### What to do

1. **Delete from `login.py`**:
   - `_handle_external_callback` function (if not already removed in Step A — the refresh
     token path may have been inlined in Step C)
   - `GET /auth/principal` endpoint (moved to `session.py`)
   - `GET /auth/sessions` endpoint (moved to `session.py`)
   - `_validate_redirect_uri` function (if no longer needed — check if still used for
     allowlist validation in `GET /auth/login`)
   - `from dockmaster.auth.dependencies import resolve_session` (if no longer used)

2. **Delete from `auth/dependencies.py`**:
   - Uncomment/delete `allow_session_admin` (commented out in Step 1b)
   - Uncomment/delete `get_session_or_jwt_email` (commented out in Step 1b)
   - Uncomment/delete `allow_jwt_or_session` (no longer used after token.py changed)
   - Move `from typing import Callable` to top of file if still needed

3. **Delete old route modules** (if not already):
   - `routes/token.py` — split into `session.py` + `cli_routes.py`
   - `routes/exchange.py` — moved to `service.py`

4. **Update `main.py`**:
   - Remove `from dockmaster.routes.token import router as token_router`
   - Remove `from dockmaster.routes.exchange import router as exchange_router`
   - Remove `application.include_router(token_router, prefix="/auth")`
   - Remove `application.include_router(exchange_router, prefix="/auth")`

5. **Delete old store class** (if not done in Step C):
   - `AuthCodeStore` from `auth/auth_code.py` (keep file if `AuthCodeEntry` is still
     used — or delete entirely if `LoginTicket` replaced it)

6. **Cleanup notes from earlier sessions**:
   - Dead `user = auth.user` lines in POST routes in `admin_ui.py`
   - `from pathlib import Path` unused import check across touched files

7. **Run full suite**: `uv run pytest` — all green
8. **Run checks**: `just check` — lint + format + types clean

### Definition of done
- [ ] No commented-out code in `dependencies.py`
- [ ] No dead endpoints in `login.py`
- [ ] `routes/token.py` and `routes/exchange.py` deleted
- [ ] `main.py` only registers active routers
- [ ] `uv run pytest` — all pass
- [ ] `just check` — clean

---

## Final Route Map

After all steps complete:

```
# Login flow (cookie + refresh token)
GET  /auth/login              — start OAuth (accepts redirect_uri, return_to)
GET  /auth/login/callback     — Google OAuth callback (cookie or login ticket)
POST /auth/login/exchange     — exchange login ticket for {refresh_token, profile, return_to}
POST /auth/logout             — destroy session (cookie or refresh_token body)

# CLI flow
GET  /auth/cli/login          — start CLI OAuth (localhost redirect_uri)
GET  /auth/cli/callback       — Google OAuth callback → JWT → redirect to localhost
POST /auth/cli/token          — issue Type C JWT from Bearer JWT

# Session-gated (cookie or refresh_token)
GET  /auth/session/principal  — session user profile
POST /auth/session/token      — issue Type C JWT for a service
GET  /auth/session/list       — user's active sessions

# Service-to-service
POST /auth/service/token      — exchange Google credential for Type C JWT

# API (JWT-gated)
GET  /auth/has                — permission check (query params)
GET  /auth/has/{s}/{t}/{p}    — permission check (path params)
GET  /auth/grants             — resolved permissions for subject+target
GET  /auth/claims             — decoded JWT claims
GET  /auth/keys               — public JWKS
GET  /auth/health             — health check

# Admin API (JWT + admin permission)
GET  /admin/roles             — list roles
POST /admin/roles             — create role
...

# Admin UI (session + admin permission via check_ui_session)
GET  /ui/                     — dashboard
GET  /ui/login                — login page
GET  /ui/roles                — roles admin
GET  /ui/grants               — grants admin
GET  /ui/sessions             — sessions admin
```
