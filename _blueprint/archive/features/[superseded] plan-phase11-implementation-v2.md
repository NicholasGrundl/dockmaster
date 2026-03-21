# Phase 11 Implementation Plan — v2

> Second revision of the Phase 11 plan. Steps 0 and 1 are complete (auth gate cleanup).
> Steps 2+ are revised based on design review during implementation: CLI gets its own
> OAuth route, login callback is simplified, `return_to` is unified across flows, and
> TTL stores are consolidated.

**Created**: 2026-03-20
**Status**: Ready to implement (Steps 0-1 complete)
**Supersedes**: `plan-phase11-implementation.md` (v1)
**Reference**: `_blueprint/features/planning/proposal-auth-gates.md` (auth taxonomy)
**Reference**: `_blueprint/features/planning/oauth-sequence-diagrams.md` (flow diagrams)

---

## What Changed From v1

1. **CLI OAuth gets its own route pair** (`/auth/cli/login`, `/auth/cli/callback`) instead
   of sharing the main callback with branching logic. Simplifies the main login flow.
2. **`return_to` is unified** across cookie and refresh token flows. Both flows accept it
   on `GET /auth/login`. Cookie flow uses it directly for the post-login redirect. Refresh
   token flow stores it in the auth code entry and returns it in the exchange response.
3. **TTL stores consolidated** into a single `TTLStore` with typed wrappers. One store,
   tagged entries, no cross-use risk.
4. **`POST /auth/login/exchange`** replaces both `POST /auth/code/exchange` (old) and
   `POST /auth/login/code` (v1). Returns `{refresh_token, profile, return_to}`.
5. **`_handle_external_callback` and `_handle_cli_callback` removed** from login.py.
   CLI logic moves to `cli_routes.py`. External callback logic inlines cleanly in the
   simplified callback.

---

## Completed Steps (from v1)

### Step 0 — Foundations ✓

- `AuthResult` model + `check_ui_session` closure in `auth/dependencies.py`
- `get_ui_config` + `get_token_issuer` state bridges in `state.py`
- Test stubs in `tests/auth/test_ui_auth.py`

### Step 1 — Auth Gate Cleanup ✓

- `allow_session` returns 401 (not 307)
- `allow_session_admin` + `get_session_or_jwt_email` removed (commented, delete at close)
- `admin_ui.py` migrated to `check_ui_session` per-route
- `ui.py` collapsed to single router + `check_ui_session`
- `token.py` gate changed to `allow_session` (JWT path removed, CLI route pending)
- `from __future__ import annotations` removed from all route files
- Tests updated and passing (425 green)

### Partially Complete (from v1, being revised)

- `resolve_session` renamed param to `handle` ✓
- `allow_session` + `get_session_user` accept refresh_token from body ✓
- Logout changed to POST, template updated ✓
- `AuthCodeEntry.profile` field added ✓
- `_handle_external_callback` passes profile claims ✓
- `POST /auth/login/code` created ✓ (will be renamed to `/auth/login/exchange`)
- `routes/session.py`, `routes/service.py`, `routes/cli_routes.py` created ✓ (cli_routes needs OAuth additions)

---

## Step 2 — Consolidate TTL Store

> Replace separate `oauth_state_store` and `auth_code_store` with a single `OAuthFlowStore`.
> Two internal `TTLStore` instances (per-type TTL), one unified `consume()` method.

### Design Decisions

- **Name**: `OAuthFlowStore`
- **Internal**: two `TTLStore` instances — one for OAuth state (600s), one for login tickets (300s)
- **External API**: typed `create_*` methods, single `consume(key)` that searches both stores
- **Return types**: Pydantic models (`OAuthState`, `LoginTicket`) — not raw dicts
- **Naming**: "login ticket" replaces "auth code" to avoid confusion with Google's auth code
- **Keys are globally unique** (`secrets.token_urlsafe`), so `consume(key)` is unambiguous

### 2a. Create `OAuthFlowStore` in `auth/oauth_flow_store.py`

```python
from pydantic import BaseModel

class OAuthState(BaseModel):
    """CSRF state for an in-progress OAuth round-trip."""
    redirect_uri: str | None  # external app callback, or None for cookie flow
    return_to: str | None     # where to send user after auth completes

class LoginTicket(BaseModel):
    """Pending login for an external app to claim via code exchange."""
    subject: str              # authenticated email
    redirect_uri: str         # external app callback (must match on consume)
    profile: dict = {}        # OAuth profile claims (name, picture, etc.)
    return_to: str | None     # forwarded from OAuth state

class OAuthFlowStore:
    """Unified single-use store for OAuth login flow entries.

    Two internal TTLStores with independent TTLs. One consume() method
    searches both — keys are cryptographically unique so there's no
    ambiguity.
    """

    def __init__(self, oauth_state_ttl: int = 600, login_ticket_ttl: int = 300):
        self._oauth_states = TTLStore[OAuthState](ttl=oauth_state_ttl)
        self._login_tickets = TTLStore[LoginTicket](ttl=login_ticket_ttl)

    def create_oauth_state(self, redirect_uri: str | None = None, return_to: str | None = None) -> str:
        return self._oauth_states.create(OAuthState(redirect_uri=redirect_uri, return_to=return_to))

    def create_login_ticket(
        self, subject: str, redirect_uri: str, profile: dict, return_to: str | None = None,
    ) -> str:
        return self._login_tickets.create(
            LoginTicket(subject=subject, redirect_uri=redirect_uri, profile=profile, return_to=return_to)
        )

    def consume(self, key: str) -> OAuthState | LoginTicket | None:
        """Consume an entry by key. Returns the typed model or None."""
        entry = self._oauth_states.consume(key)
        if entry is not None:
            return entry
        return self._login_tickets.consume(key)
```

Callers use `isinstance()` or just know what they expect based on context:
- `GET /auth/callback` always consumes an `OAuthState`
- `POST /auth/login/exchange` always consumes a `LoginTicket`

For `LoginTicket` consumption, the caller must also verify `redirect_uri` matches:
```python
ticket = flow_store.consume(body.code)
if not isinstance(ticket, LoginTicket) or ticket.redirect_uri != body.redirect_uri:
    raise HTTPException(400, "Invalid or expired code")
```

### 2b. Update `main.py` lifespan

```python
# Before
app.state.oauth_state_store = TTLStore[dict](ttl=600)
app.state.auth_code_store = AuthCodeStore(ttl=300)

# After
app.state.flow_store = OAuthFlowStore(oauth_state_ttl=600, login_ticket_ttl=300)
```

### 2c. Update all consumers

- `login.py`: `GET /auth/login` → `flow_store.create_oauth_state(...)`
- `login.py`: `GET /auth/callback` → `flow_store.consume(state)` → expect `OAuthState`
- `login.py`: callback refresh token path → `flow_store.create_login_ticket(...)`
- `login.py`: `POST /auth/login/exchange` → `flow_store.consume(code)` → expect `LoginTicket`
- `cli_routes.py`: `GET /auth/cli/login` → `flow_store.create_oauth_state(...)`
- `cli_routes.py`: `GET /auth/cli/callback` → `flow_store.consume(state)` → expect `OAuthState`

### 2d. Delete old stores

- Delete `AuthCodeStore` class from `auth/auth_code.py`
- Keep `auth/auth_code.py` file if `AuthCodeEntry` is still referenced in tests — or migrate
  tests to use `LoginTicket`
- Remove `oauth_state_store` and `auth_code_store` from lifespan
- Update tests that reference old stores

### 2e. Tests

- Test `OAuthFlowStore.create_oauth_state` → `consume` returns `OAuthState`
- Test `OAuthFlowStore.create_login_ticket` → `consume` returns `LoginTicket`
- Test `consume` with unknown key → `None`
- Test `consume` is single-use (second consume returns `None`)
- Test TTL expiry for each type independently
- Test keys don't collide across stores (create state + create ticket, consume each)

### Definition of done
- [ ] `OAuthFlowStore` exists in `auth/oauth_flow_store.py`
- [ ] `OAuthState` and `LoginTicket` Pydantic models defined
- [ ] Per-type TTL (600s state, 300s tickets)
- [ ] Single `consume()` method searches both internal stores
- [ ] Single store instance on `app.state.flow_store`
- [ ] All consumers updated
- [ ] Old `AuthCodeStore` and `oauth_state_store` removed
- [ ] Tests pass

---

## Step 3 — Simplify Login Routes

> Clean up login.py: extract CLI to its own route, unify `return_to`, simplify callback.

### 3a. Extract CLI OAuth to `cli_routes.py`

Add CLI-specific OAuth endpoints to the existing `cli_routes.py`:

```
GET  /auth/cli/login     — redirect to Google with localhost callback URI
GET  /auth/cli/callback  — exchange Google code, mint JWT, redirect to localhost
POST /auth/cli/token     — issue Type C JWT from Bearer JWT (already exists)
```

- `GET /auth/cli/login` accepts `redirect_uri` (localhost only, validated by `_LOCALHOST_RE`)
- Stores state via `flow_store.create_oauth_state(redirect_uri=localhost_uri, return_to=None)`
- Passes `/auth/cli/callback` as the Google callback URI
- **GCP note**: `/auth/cli/callback` must be registered as an authorized redirect URI in
  the Google OAuth client config

`GET /auth/cli/callback`:
- Consumes OAuth state via `flow_store.consume(state)` → expect `OAuthState`
- Exchanges Google code, verifies email/domain
- Mints a short-lived Type C JWT (15 min)
- Redirects to localhost: `{redirect_uri}?token={jwt}`

### 3b. Move callback to `/auth/login/callback`

Rename `GET /auth/callback` → `GET /auth/login/callback`. All login-related routes
are now grouped under `/auth/login/`:

```
GET  /auth/login              — start OAuth (cookie or refresh token flow)
GET  /auth/login/callback     — Google redirects here after OAuth
POST /auth/login/exchange     — exchange login ticket for refresh token
POST /auth/logout             — destroy session
```

**GCP note**: Update the authorized redirect URI from `/auth/callback` to
`/auth/login/callback` in Google OAuth client config.

### 3c. Add `return_to` to `GET /auth/login`

Accept `return_to` as an optional query param alongside `redirect_uri`:

```python
@router.get("/login")
async def login(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    redirect_uri: str | None = None,
    return_to: str | None = None,
):
```

Validation:
- `return_to` for cookie flow (no `redirect_uri`): reject absolute URLs, allow relative paths only
- `return_to` for refresh token flow (with `redirect_uri`): same validation — reject absolute
  URLs. Even though the external app consumes it, we still validate to prevent abuse.
- Both use a shared `_validate_return_to(uri)` helper

Store in OAuth state:
```python
flow_store.create_oauth_state(redirect_uri=validated_redirect, return_to=validated_return_to)
```

### 3d. Simplify `GET /auth/login/callback`

With CLI extracted, the callback only handles two cases:

```python
@router.get("/login/callback")
async def login_callback(request, settings):
    # 1. Validate CSRF state
    state_entry = flow_store.consume(state)  # → OAuthState
    if not isinstance(state_entry, OAuthState):
        raise HTTPException(401, "Invalid OAuth state")

    # 2. Exchange Google code, verify email/domain
    ...

    if state_entry.redirect_uri:
        # REFRESH TOKEN FLOW — create login ticket, redirect to external app
        code = flow_store.create_login_ticket(
            subject=email,
            redirect_uri=state_entry.redirect_uri,
            profile=profile_claims,
            return_to=state_entry.return_to,
        )
        return RedirectResponse(f"{state_entry.redirect_uri}?code={code}&state={state}")

    # COOKIE FLOW — create session, set cookie, redirect
    session_id = create_session(...)
    response = RedirectResponse(state_entry.return_to or "/ui/", 302)
    response.set_cookie(...)
    return response
```

No more `_handle_external_callback` or `_handle_cli_callback` helpers. Two clean branches.

### 3e. Rename `POST /auth/login/code` → `POST /auth/login/exchange`

Update the endpoint and add `return_to` to the response:

```python
class LoginExchangeRequest(BaseModel):
    code: str
    redirect_uri: str

class LoginExchangeResponse(BaseModel):
    refresh_token: str
    profile: dict
    return_to: str | None

@router.post("/login/exchange", response_model=LoginExchangeResponse)
async def login_exchange(body: LoginExchangeRequest, request, settings):
    ticket = flow_store.consume(body.code)
    if not isinstance(ticket, LoginTicket) or ticket.redirect_uri != body.redirect_uri:
        raise HTTPException(400, "Invalid or expired code")

    # Create session + sign refresh token
    session_id = str(uuid4())
    session_data = {"email": ticket.subject, **ticket.profile}
    await session_store.set(session_id, session_data, ttl=settings.session_ttl)
    refresh_token = signer.dumps(session_id)

    return LoginExchangeResponse(
        refresh_token=refresh_token,
        profile=ticket.profile,
        return_to=ticket.return_to,
    )
```

### 3f. Delete `POST /auth/code/exchange`

Old endpoint fully replaced by `POST /auth/login/exchange`.

### 3g. Remove old code from `login.py`

- Delete `_handle_external_callback`
- Delete `_handle_cli_callback`
- Delete `CLI_TOKEN_TTL` constant
- Delete `_LOCALHOST_RE` (moves to `cli_routes.py`)
- Delete `_validate_redirect_uri` (replaced by simpler validation — external URIs validated
  against allowlist inline, localhost validation moves to CLI routes)
- Remove `GET /auth/principal` and `GET /auth/sessions` (already moved to `session.py`)
- Remove old `CodeExchangeRequest` / `code_exchange` endpoint

### 3h. Update `main.py`

- Replace `app.state.oauth_state_store` + `app.state.auth_code_store` with `app.state.flow_store`
- Ensure CLI callback route is registered
- Update GCP OAuth redirect URIs: `/auth/login/callback` and `/auth/cli/callback`

### 3i. Update tests

Route rename mapping:

| Old path | New path | Notes |
|---|---|---|
| `GET /auth/callback` | `GET /auth/login/callback` | Renamed |
| `POST /auth/code/exchange` | `POST /auth/login/exchange` | Returns `{refresh_token, profile, return_to}` |
| `POST /auth/login/code` (v1) | `POST /auth/login/exchange` | Rename |
| Callback CLI branch | `GET /auth/cli/callback` | Separate route |

### Definition of done
- [ ] CLI OAuth has own route pair in `cli_routes.py`
- [ ] Callback moved to `GET /auth/login/callback`
- [ ] `return_to` accepted on `GET /auth/login`, validated, stored in flow state
- [ ] Cookie flow: redirects to `return_to` (default `/ui/`)
- [ ] Refresh token flow: `return_to` stored in login ticket, returned in exchange response
- [ ] `POST /auth/login/exchange` replaces `POST /auth/code/exchange` and `POST /auth/login/code`
- [ ] Old helpers and dead code removed from `login.py`
- [ ] `OAuthFlowStore` used everywhere, old stores removed
- [ ] All tests updated and passing

---

## Step 4 — Python Consumer SDK

> Independent workstream. Can proceed after Step 3.

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

## Step 5 — Cleanup & Close

- [ ] Delete commented-out code (`allow_session_admin`, `get_session_or_jwt_email`, etc.)
- [ ] Delete `routes/token.py` and `routes/exchange.py` (if not already)
- [ ] Revisit storage DI bridges (read-only vs admin naming confusion)
- [ ] Revisit `permissions.py` `_check_permission` helper (use `get_authority` bridge)
- [ ] Extract `get_session_handle` utility (DRY up cookie/refresh_token resolution)
- [ ] Full test suite pass (`uv run pytest`)
- [ ] Lint + format + types clean (`just check`)
- [ ] Manual browser test: login → dashboard → admin pages → logout
- [ ] Update `implementation-progress.md` with completion status
- [ ] Update `ROADMAP.md` Phase 11 status
- [ ] Suggest commit

---

## Risk Register

| Risk | Mitigation |
|---|---|
| GCP needs `/auth/cli/callback` as authorized redirect URI | Document in guide, flag during implementation |
| `FlowStore` TTL mismatch (OAuth state 600s vs auth code 300s) | Use 600s for all, or per-type TTL — decide in Step 2 |
| `return_to` open redirect | Validate: reject absolute URLs, relative paths only |
| Removing `_handle_cli_callback` breaks CLI tests | CLI tests move to `cli_routes.py` test module |
| `POST /auth/login/exchange` rename breaks external consumers | No external consumers yet — safe to rename |

---

## Resolved Questions

1. **Store naming**: `OAuthFlowStore` with `OAuthState` + `LoginTicket` models
2. **Return types**: Pydantic models for both (`OAuthState`, `LoginTicket`)
3. **TTL strategy**: Per-type TTL — two internal `TTLStore` instances (600s state, 300s tickets)
4. **`redirect_uri` validation**: Keep allowlist in Settings for now
5. **Single consume**: One `consume(key)` searches both stores — keys are globally unique
