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

