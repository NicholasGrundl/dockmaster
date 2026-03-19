# Code Review Notes

Personal notes collected while reading through the dockmaster codebase.

---

## auth

<!-- src/dockmaster/auth/ — JWT, OAuth, admin auth dependencies -->

### dependencies.py — `object` type annotations

The utility functions use `object` as the type for `realm`, `session_store`, and `authority` parameters instead of their actual classes. This kills IDE autocompletion and type checking.

Locations:
- `verify_jwt` (line 57): `realm: object` — should be the actual realm class (e.g. `ServiceRealm`)
- `resolve_session` (line 68): `session_store: object | None` — should be the `SessionStore` protocol
- `check_permission` (line 93): `authority: object | None` — should be `Authority`
- `verify_google_credential` (line 118): `realm: object | None` — same as `verify_jwt`

**Action**: Replace `object` with the real class/protocol types so IDEs can provide autocomplete.


### dependencies.py — dependency function design intent

The module has three categories of FastAPI dependencies:

#### `allow_*` — Router auth gates
- Purpose: authenticate/authorize the request. They are **guards**.
- On failure: **must raise an HTTPException** (401 unauthenticated, 403 forbidden, 5xx service error). FastAPI handles these exceptions at the framework level.
- Must **never redirect** — redirects conflate the "is this allowed?" check with "what do we do about it?" behavior. The route or error handler decides what to do with the rejection, not the gate.
- Return value on success: whatever is useful to the caller (claims dict, email string, typed credential, etc.).

**Current violation**: `allow_session` returns a 307 redirect to `/ui/login` instead of a 401. Needs to be changed to raise 401; the UI layer should handle the redirect separately.

#### `get_*` — Information retrieval dependencies
- Purpose: extract and return data for the route to use. They are **data providers**, not enforcers.
- Should **not raise auth exceptions** — return None / empty dict on failure. Pair with a router-level `allow_*` gate for enforcement.
- Should use the `state.py` DI bridges (`get_realm`, `get_session_store`, `get_authority`, etc.) with `Annotated[..., Depends(...)]` syntax to make their state dependencies explicit and visible in the function signature.

**Current issue**: `get_*` functions use raw `getattr(request.app.state, ...)` instead of the state module DI bridges. Also need a `get_realm` bridge added to `state.py` (currently missing).

#### `needs_*` — System capability checks
- Purpose: assert that a required system resource is available. They check **what the system can do**, not what the user is allowed to do.
- On failure: raise 503 (service unavailable).
- Examples: `needs_admin_storage`, `needs_session_store`.

#### DI bridge usage
Both `allow_*` and `get_*` functions should use the `state.py` DI bridges with `Annotated` notation instead of raw `getattr(request.app.state, ...)`. This makes dependencies explicit in function signatures and consistent with the rest of the DI design.


## cli

<!-- src/dockmaster/cli/ — Typer CLI (login, role, grant, check commands) -->


## rbac

<!-- src/dockmaster/rbac/ — Models, storage, authority, admin_ops -->


## routes

<!-- src/dockmaster/routes/ — FastAPI route modules -->

### State objects used across routes

All state singletons set in `main.py` lifespan. Current `state.py` DI bridges: `get_admin_storage`, `get_authority`, `get_session_store`. Missing bridges noted below.

| State object | Type | Bridge exists? |
|---|---|---|
| `realm` | `ServiceRealm` | **No** — needs `get_realm` |
| `session_store` | `SessionStore` | Yes |
| `authority` | `Authority` | Yes |
| `admin_storage` | `AdminSecretsStorage` | Yes |
| `token_issuer` | `EphemeralKeypairSigner` | **No** — needs `get_token_issuer` |
| `oauth` | authlib OAuth client | **No** — needs `get_oauth` |
| `oauth_state_store` | `TTLStore[dict]` | **No** — needs `get_oauth_state_store` |
| `auth_code_store` | `AuthCodeStore` | **No** — needs `get_auth_code_store` |
| `signer` | `ServiceAccountSigner \| None` | **No** — needs `get_signer` |
| `secrets_storage` | `SecretsStorage` | **No** — needs `get_secrets_storage` (read-only counterpart to admin_storage) |
| `ui_config` | `UIConfig` | **No** — needs `get_ui_config` |


### admin.py — `/admin/*`

**Non-route helpers**: None (only pydantic request/response models: `CreateRoleRequest`, `UpdateRoleRequest`, `PutGrantsRequest`, `RevokeSessionResponse`, `RevokeByEmailResponse`).

**DI bridge usage**: Good — uses `get_admin_storage`, `get_authority`, `get_session_store` from `state.py` with `Annotated` syntax. Also uses `needs_admin_storage`, `needs_session_store` capability checks.

**`get_*` info deps used**: None needed — routes get data directly from `admin_ops` functions.


### admin_ui.py — `/ui/roles`, `/ui/grants`, `/ui/sessions`

**Non-route helpers**:
- `_admin_writes_enabled(request)` (line 31): checks if `admin_storage` is on `app.state`. Returns bool for template rendering. Uses raw `getattr`.
  - Could use existing `get_admin_storage` bridge — just check `is not None`.

**DI bridge usage**: Good — uses `get_admin_storage`, `get_authority`, `get_session_store` from `state.py`.

**`get_*` info deps used**: `get_session_user` from `auth/dependencies.py`.

**Other notes**:
- `roles_page` and `grants_page` fall back to `request.app.state.secrets_storage` (read-only storage) via raw `getattr` when `admin_storage` is None. Needs a `get_secrets_storage` bridge.
- `grants_detail_page` also does the same `secrets_storage` fallback.


### claims.py — `/auth/claims`

**Non-route helpers**: None.

**DI bridge usage**: N/A — no state accessed directly.

**`get_*` info deps used**: `get_jwt_claims` from `auth/dependencies.py`. Clean usage.


### exchange.py — `/auth/exchange`

**Non-route helpers**: None (only pydantic `ExchangeResponse` model).

**DI bridge usage**: `token_issuer` accessed via raw `getattr(request.app.state, "token_issuer", None)` in `exchange_token`. Needs `get_token_issuer` bridge.

**`get_*` info deps used**: `get_google_claims` from `auth/dependencies.py`. Clean usage.


### health.py — `/auth/health`

**Non-route helpers**:
- `root_info(request)` (line 29): returns `ServiceInfo` with docs URL. Not mounted on the health router — registered separately in `main.py`. Uses `request.app.docs_url` (not state).

**DI bridge usage**: None needed.

**`get_*` info deps used**: None needed.


### keys.py — `/auth/key/{kid}`

**Non-route helpers**: None.

**DI bridge usage**: `realm` accessed via raw `getattr(request.app.state, "realm", None)`. Needs `get_realm` bridge.

**`get_*` info deps used**: None — but could benefit from a `get_realm` info dep or just use the state bridge directly since it only calls `realm.get_key(kid)`.


### login.py — `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/principal`, `/auth/sessions`, `/auth/code/exchange`

**Non-route helpers**:
- `_get_signer(settings)` (line 33): creates `URLSafeSerializer` from `settings.session_secret_key`. Pure function, no state access.
- `_validate_redirect_uri(uri, allowed_redirect_uris)` (line 37): validates redirect URI against localhost regex and allowlist. Pure function, raises HTTPException on invalid.
- `_handle_external_callback(request, email, redirect_uri, state)` (line 157): generates auth code and redirects. Uses `auth_code_store` via raw `getattr`.
- `_handle_cli_callback(request, email, redirect_uri)` (line 174): mints CLI JWT and redirects. Uses `token_issuer` via raw `getattr`.

**DI bridge usage**: Heavy raw `getattr` usage throughout:
- `oauth` — login, callback (needs `get_oauth`)
- `oauth_state_store` — login, callback (needs `get_oauth_state_store`; currently accessed via direct `request.app.state.oauth_state_store` without `getattr` — would crash if missing)
- `session_store` — callback, logout, principal, sessions (has bridge `get_session_store`, not used)
- `auth_code_store` — `_handle_external_callback` (needs `get_auth_code_store`)
- `token_issuer` — `_handle_cli_callback`, code_exchange (needs `get_token_issuer`)

**`get_*` info deps used**: `resolve_session` utility (not a `get_*` dep, called directly). `get_principal` and `get_sessions` could use `get_session_user` instead of manually calling `resolve_session`.

**Other notes**:
- `get_sessions` has redundant `session_store` lookup — fetches it once in `resolve_session` call, then again on line 243.
- `_handle_external_callback` and `_handle_cli_callback` take `request: Request` and do raw `getattr` — these helpers could take their dependencies as parameters instead (or the calling route could inject via DI and pass them).


### permissions.py — `/auth/has`, `/auth/grants`

**Non-route helpers**:
- `_check_permission(request, subject, target, permission)` (line 20): shared permission check for both path and query param variants. Uses `authority` via raw `getattr`.
  - Could take `Authority | None` as a parameter instead of `request`, or the routes could inject `authority` via `get_authority` bridge and pass it in.

**DI bridge usage**: `authority` accessed via raw `getattr` in `_check_permission` and `get_grants`. Needs to use `get_authority` bridge.

**`get_*` info deps used**: None — but `_check_permission` is effectively a shared helper that could be refactored to accept `authority` as a DI-injected parameter.

**Response models**: `GrantsResponse` (pydantic).


### token.py — `/auth/token`

**Non-route helpers**: None (only pydantic `TokenResponse` model).

**DI bridge usage**: `token_issuer` accessed via raw `getattr(request.app.state, "token_issuer", None)`. Needs `get_token_issuer` bridge.

**`get_*` info deps used**: `get_session_or_jwt_email` from `auth/dependencies.py`. Clean usage.


### ui.py — `/ui/login`, `/ui/` (dashboard)

**Non-route helpers**:
- `_timestamp_to_datetime(ts)` (line 21): Jinja2 filter. Pure function.
- `_get_session_user(request)` (line 35): extracts user from session cookie. Uses `session_store` and `settings` via raw `request.app.state`. **Duplicates** `get_session_user` from `auth/dependencies.py` — should use that instead.
- `require_ui_session(request)` (line 43): dependency that ensures active session. **Redirects** (307) on failure via `_redirect_to_login()` — same redirect-in-gate issue as `allow_session`. Should raise 401 and let the UI layer handle redirects.
- `_redirect_to_login()` (line 54): creates HTTPException with 307. Part of the redirect-in-gate anti-pattern.
- `_ui_config(request)` (line 61): reads `ui_config` from `app.state` via `getattr`. Needs `get_ui_config` bridge.

**DI bridge usage**: All raw `getattr`:
- `session_store` — `_get_session_user`, dashboard (has bridge, not used)
- `authority` — dashboard (has bridge, not used)
- `signer` — dashboard status check (needs `get_signer`)
- `realm` — dashboard status check (needs `get_realm`)
- `oauth` — dashboard status check (needs `get_oauth`)
- `secrets_storage` — dashboard status check (needs `get_secrets_storage`)
- `ui_config` — `_ui_config` helper (needs `get_ui_config`)

**`get_*` info deps used**: `resolve_session` and `check_permission` called directly as utilities. `_get_session_user` duplicates `get_session_user`.

**Other notes**:
- `require_ui_session` is a local equivalent of `allow_session` — both do session validation + redirect. After fixing `allow_session` to raise 401, `require_ui_session` should either be replaced by `allow_session` or kept as a UI-specific variant that does the redirect (if we decide the UI layer *is* the right place for that redirect logic).
- Dashboard has inline `from dockmaster.rbac.admin_ops import list_sessions_by_email` — should be a top-level import.


## sessions

<!-- src/dockmaster/sessions/ — SessionStore protocol + in-memory impl -->


## templates

<!-- src/dockmaster/templates/ — Jinja2 HTML templates -->


## ui

<!-- src/dockmaster/ui/ — UIConfig -->


## config

<!-- src/dockmaster/config.py — Settings (pydantic-settings) -->


## main

<!-- src/dockmaster/main.py — App factory + lifespan -->


## tests

<!-- tests/ — pytest test suite -->


## general

<!-- Cross-cutting observations, patterns, questions -->

