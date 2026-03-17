---
state: Draft
changelog:
  "2026-03-17 v2": "Rewritten — expanded scope: auth conventions + middleware consolidation + settings DI bridge. Senior review of Layer 2 naming, allow_* vocabulary, middleware module structure."
  "2026-03-17": "Created — auth dependency conventions, router-level gates, permission factory"
---

# Phase 8e: App Architecture Conventions

> Standardize three cross-cutting concerns: auth dependency conventions,
> middleware organization, and settings injection. Make the codebase
> self-documenting so a new developer adding a route knows exactly what to
> reach for.

**Status**: Planned
**Priority**: P1
**Phase**: 8e
**Last updated**: 2026-03-17

---

## Problem

Three problems for a developer adding or reading a route:

1. **Auth is inconsistent** — some routes use `Depends(get_current_user)`, some
   roll their own `HTTPBearer` instance (exchange, token endpoints). Admin
   routes repeat `Depends(require_admin_api)` on every endpoint (~13 times in
   `admin.py`, ~12 in `admin_ui.py`). One missed `Depends` silently leaves a
   route unprotected. No "door" on the router itself.

2. **Middleware is scattered** — `SecurityHeadersMiddleware` lives in
   `middleware.py`, but CORS and Session middleware are configured inline in
   `create_app()`. No single place answers "what middleware runs?"

3. **Settings injection is manual** — every route does
   `settings: Settings = request.app.state.settings` as an inline assignment.
   Not idiomatic FastAPI, not visible in the dependency graph, not
   self-documenting.

---

## Solution Overview

Three pillars, one coherent theme: "how does the app wire its cross-cutting
concerns?"

### Pillar 1: Auth Conventions

Three-layer auth model with consistent `allow_*` / `require_*` / `needs_*`
vocabulary.

### Pillar 2: Middleware Consolidation

All middleware classes in `middleware.py`, all wiring in a `setup_middleware()`
helper in `main.py`.

### Pillar 3: Settings DI Bridge

`Depends(get_settings)` reads from `app.state.settings`. Routes declare
settings as a dependency via `Annotated[Settings, Depends(get_settings)]`.

---

## Pillar 1: Auth Conventions

### Three-Layer Auth Model

```
Layer 0 — Auth mechanism gate (allow_*)
    How does the caller prove their identity?
    Applied at the router level via dependencies=[Depends(allow_*)].
    FastAPI enforces on every route automatically.

Layer 1 — RBAC permission check (require_permission)
    Is this authenticated user authorized for this specific action?
    Applied per-route for actions needing RBAC beyond the gate.

Layer 2 — System capability check (needs_*)
    Can the system perform this operation right now?
    Applied per-route for operations requiring optional infrastructure.
```

**Naming rationale**:
- `allow_*` = auth mechanism gates (who is allowed in)
- `require_*` = user permission checks (what the user is required to have)
- `needs_*` = system prerequisites (what the system needs to function)

**The rule**: a new dev adds a route and asks three questions in order:
1. Which router? → inherit its auth gate for free.
2. Does this action require a specific RBAC permission? → add `require_permission`.
3. Does this action require optional infrastructure? → add `needs_*`.

### Layer 0 — Auth Mechanism Gates

All live in `auth/dependencies.py`. Naming pattern: `allow_{mechanism}[_{level}]`.

| Dependency | Returns | What it does |
|---|---|---|
| `allow_jwt` | user claims `dict` | Verify dockmaster Bearer JWT. Raises 401. |
| `allow_session` | user session `dict` | Verify session cookie. Redirects to `/ui/login`. |
| `allow_jwt_or_session` | `str` (email) | Try session first, then Bearer JWT. Raises 401. |
| `allow_google_credential` | Google claims `dict` | Verify Google JWT or access token. Raises 401. |

**Composed gates (Layer 0 + Layer 1):**

| Dependency | Composition | Used by |
|---|---|---|
| `allow_jwt_admin` | `allow_jwt` + `require_permission("dockmaster", "admin")` | Admin API router |
| `allow_session_admin` | `allow_session` + `require_permission("dockmaster", "admin")` | Admin UI router |

The composed names read as a namespace hierarchy: `allow_jwt_admin` = "allow
JWT → further: must be admin."

```python
# auth/dependencies.py

async def allow_jwt(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Verify Bearer JWT. Returns decoded claims.

    Use as a router-level gate for API zones requiring a valid
    dockmaster JWT. Raises 401 if no token or invalid/expired.
    """
    ...

async def allow_session(request: Request) -> dict:
    """Verify session cookie. Returns session data dict.

    Use as a router-level gate for UI zones. Redirects to
    /ui/login if no valid session.
    """
    ...

async def allow_jwt_or_session(request: Request) -> str:
    """Session cookie OR Bearer JWT. Returns email.

    Tries session first (browser clients), Bearer second (CLI/API).
    Use per-route for endpoints that accept either auth method.
    Raises 401 if neither succeeds.
    """
    ...

async def allow_google_credential(request: Request) -> dict:
    """Verify Google JWT or access token. Returns Google claims.

    Use as router-level gate for the exchange router. This is NOT
    dockmaster auth — it verifies external Google credentials.
    """
    ...

async def allow_jwt_admin(
    request: Request,
    user: dict = Depends(allow_jwt),
) -> dict:
    """Bearer JWT + dockmaster admin permission.

    Wraps allow_jwt, then checks require_permission("dockmaster", "admin").
    Use as router-level gate for admin API zones. Raises 403 if not admin.
    """
    ...

async def allow_session_admin(request: Request) -> dict:
    """Session cookie + dockmaster admin permission.

    Session-based counterpart to allow_jwt_admin. For HTML/form-based
    admin pages. Redirects to /ui/login if no session, raises 403 if
    authenticated but not admin.
    """
    ...
```

Applied at the router:
```python
# routes/admin.py
router = APIRouter(
    tags=["admin-api"],
    dependencies=[Depends(allow_jwt_admin)],
)
# Every route is admin-gated automatically. No per-route Depends needed.
```

For **public** routes, the absence of a gate is the signal:
```python
# routes/health.py
router = APIRouter(tags=["public"])
# No dependencies= — intentionally public, documented by tag.
```

### Layer 1 — RBAC Permission Factory

A parameterized dependency factory. Lives in `auth/dependencies.py`.

```python
def require_permission(service: str, permission: str):
    """Dependency factory — asserts the current user has permission on service.

    Returns a FastAPI dependency that raises 403 if the check fails.
    Resolves via Authority.has_permission(), falls back to
    DOCKMASTER_ADMIN_EMAILS whitelist for ("dockmaster", "admin").

    Usage:
        # On a router (gate for the whole zone):
        dependencies=[Depends(require_permission("dockmaster", "admin"))]

        # On a single route (additional RBAC gate):
        _: None = Depends(require_permission("billing", "write"))
    """
    async def _check(
        user: dict = Depends(allow_jwt),
        request: Request = None,
    ) -> None:
        email = user.get("email", "")
        authority = getattr(request.app.state, "authority", None)
        settings: Settings = request.app.state.settings
        granted = await _resolve_permission(email, service, permission, authority, settings)
        if not granted:
            logger.warning("permission_denied", email=email, service=service, permission=permission)
            raise HTTPException(status_code=403, detail="Access denied")
    return _check
```

The `allow_jwt_admin` and `allow_session_admin` gates are built on this factory:
```python
async def allow_jwt_admin(user: dict = Depends(allow_jwt), ...) -> dict:
    await require_permission("dockmaster", "admin")(user=user, request=request)
    return user
```

### Layer 2 — System Capability Checks

Not RBAC — these check what the **system** can do, not what the user is
allowed to do. Named `needs_*` to clearly distinguish from `require_*` (user
permissions).

```python
async def needs_admin_storage(request: Request) -> None:
    """Assert admin SM client is configured for write operations.

    Raises 503 if admin_storage is not on app.state.
    This is a system capability check — it asks 'can the system do this?'
    rather than 'is this user allowed to do this?'
    """
    ...
```

### Router → Gate Mapping

| Router | Tag | Gate | Notes |
|---|---|---|---|
| `health.py` | `"public"` | *(none)* | Intentionally open |
| `keys.py` | `"public"` | *(none)* | Public key distribution |
| `login.py` | `"oauth"` | *(none)* | Semi-public OAuth flow |
| `claims.py` | `"authenticated"` | `allow_jwt` | JWT introspection |
| `permissions.py` | `"authenticated"` | `allow_jwt` | Permission checks |
| `exchange.py` | `"exchange"` | `allow_google_credential` | Google credential exchange |
| `token.py` | `"authenticated"` | *(per-route)* | Uses `allow_jwt_or_session` per-route |
| `admin.py` | `"admin-api"` | `allow_jwt_admin` | Admin CRUD |
| `admin_ui.py` | `"admin-ui"` | `allow_session_admin` | Admin pages |
| `ui.py` (public) | `"ui"` | *(none)* | Login page |
| `ui.py` (protected) | `"ui"` | `allow_session` | Dashboard |

---

## Pillar 2: Middleware Consolidation

### Current State

- `middleware.py` — defines `SecurityHeadersMiddleware` class + `DEFAULT_CSP`
- `main.py:create_app()` — configures all three middlewares inline (~15 lines)

### Target State

**`middleware.py`** — class definitions and constants only:
- `SecurityHeadersMiddleware` class
- `DEFAULT_CSP` constant

**`main.py`** — new top-level `setup_middleware(app, settings)` helper:
```python
def setup_middleware(app: FastAPI, settings: Settings) -> None:
    """Configure all application middleware.

    Order matters — Starlette executes middleware in reverse-add order
    (last added runs first on the request path).
    """
    if settings.security_headers:
        app.add_middleware(SecurityHeadersMiddleware)
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=sorted(settings.allowed_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization"],
            allow_credentials=True,
        )
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)


def create_app(settings=None) -> FastAPI:
    ...
    setup_middleware(application, settings)
    application.include_router(...)
```

The wiring logic stays visible in `main.py` so a developer can see exactly
what settings feed into what middleware. Class definitions and constants live
in `middleware.py`.

### SessionMiddleware

Starlette's `SessionMiddleware` stays as-is. It was originally added for
Authlib's OAuth state management. OAuth CSRF state is now managed by `TTLStore`
(S-005), but Authlib's `authorize_redirect()` and `authorize_access_token()`
may still use `request.session` internally.

**Backlog item**: Investigate whether Authlib can operate without
`SessionMiddleware` when we pass `state=` explicitly. Not blocking for 8e.

---

## Pillar 3: Settings DI Bridge

### Current State

Routes read settings via manual assignment:
```python
settings: Settings = request.app.state.settings
```

This works but isn't idiomatic FastAPI — settings aren't visible in the
dependency graph, and every route repeats the same line.

### Target State

Bridge function in `config.py` that reads from `app.state`:
```python
# config.py
def get_settings(request: Request) -> Settings:
    """Read settings from app.state.

    Bridge between app.state (source of truth) and FastAPI's DI system.
    In tests, set app.state.settings = Settings(...) — no lru_cache,
    no dependency_overrides needed.
    """
    return request.app.state.settings
```

Routes declare settings as an explicit dependency:
```python
# routes/exchange.py
from typing import Annotated
from dockmaster.config import Settings, get_settings

@router.post("/exchange")
async def exchange_token(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
):
    ...
```

**No type alias** — use `Annotated[Settings, Depends(get_settings)]` explicitly
in each route signature. The few extra characters keep each route
self-documenting without chasing an alias.

**Test behavior**: unchanged. Tests set `app.state.settings = test_settings`
before creating a `TestClient`. The bridge reads from there automatically.
No `lru_cache`, no `dependency_overrides`.

---

## Migration Plan

### Ordering

1. **Pillar 3 first** (settings bridge) — changes `config.py` + all route
   files. Foundation for Pillar 1 since auth deps will use `get_settings`.
2. **Pillar 1 second** (auth conventions) — changes `auth/dependencies.py`,
   `auth/admin.py`, all route files. Biggest change.
3. **Pillar 2 last** (middleware) — changes `middleware.py` + `main.py`.
   Independent, lowest risk.

### Files to Change

**Pillar 3 — Settings DI Bridge:**
- `src/dockmaster/config.py` — add `get_settings(request)` bridge function
- All route files that read `request.app.state.settings` — migrate to
  `Annotated[Settings, Depends(get_settings)]`:
  - `routes/login.py` (5 occurrences)
  - `routes/ui.py` (2)
  - `routes/exchange.py` (1)
  - `routes/token.py` (1)
- `auth/admin.py` (2) — though this file is removed in Pillar 1

**Pillar 1 — Auth Conventions:**
- `src/dockmaster/auth/dependencies.py`:
  - Rename `get_current_user` → `allow_jwt` (keep `get_current_user` as alias
    during migration, remove in follow-up)
  - Add `allow_session`, `allow_jwt_or_session`, `allow_google_credential`
  - Add `allow_jwt_admin`, `allow_session_admin` (composed gates)
  - Add `require_permission(service, permission)` factory
  - Add `needs_admin_storage` (from `auth/admin.py`)
  - Move `_email_from_session`, `_email_from_bearer` helpers here (from `token.py`)
- `src/dockmaster/auth/admin.py` — **remove entirely**. All logic moves to
  `dependencies.py`. `_is_admin` logic folded into `require_permission`.
- `src/dockmaster/routes/admin.py` — add `dependencies=[Depends(allow_jwt_admin)]`,
  remove per-route `Depends(require_admin_api)` (~13 endpoints).
  Rename `Depends(require_admin_writes)` → `Depends(needs_admin_storage)`.
- `src/dockmaster/routes/admin_ui.py` — add `dependencies=[Depends(allow_session_admin)]`,
  remove per-route `Depends(require_admin_ui)` (~12 endpoints).
  Rename `require_admin_writes` → `needs_admin_storage`.
- `src/dockmaster/routes/claims.py` — add `dependencies=[Depends(allow_jwt)]`,
  remove per-route `Depends(get_current_user)` where only used for auth gate
  (keep where return value is used for claims data).
- `src/dockmaster/routes/permissions.py` — add `dependencies=[Depends(allow_jwt)]`,
  remove per-route auth deps.
- `src/dockmaster/routes/exchange.py` — add `dependencies=[Depends(allow_google_credential)]`.
  Extract Google credential verification from inline code into the dependency.
  Remove local `_bearer` instance.
- `src/dockmaster/routes/token.py` — add `Depends(allow_jwt_or_session)` as
  per-route dependency. Remove inline `_email_from_session`/`_email_from_bearer`.
  Remove local `_bearer` instance.
- Test files — update imports: `require_admin_api` → `allow_jwt_admin`,
  `require_admin_ui` → `allow_session_admin`,
  `require_admin_writes` → `needs_admin_storage`,
  `get_current_user` → `allow_jwt` (or use alias).

**Pillar 2 — Middleware Consolidation:**
- `src/dockmaster/main.py` — extract inline middleware config into
  `setup_middleware(app, settings)` helper at module top level. Remove inline
  `add_middleware` calls from `create_app`.
- `src/dockmaster/middleware.py` — no changes needed (already has class +
  constants only).

### Backward Compatibility

- `get_current_user` — keep as alias for `allow_jwt` during migration. Tests
  import it directly. Remove the alias in a follow-up pass.
- `get_session_data` — keep in `dependencies.py`. Used internally by
  `allow_session` and `allow_jwt_or_session`.

---

## Testing Approach

- **No new test files** — this is a refactor, not new functionality.
- **All existing tests must pass** (412+) after migration.
- **Mechanical import updates** in test files — rename imports to match new
  dependency names.
- Test fixture patterns stay as-is (fixture audit is separate scope).

---

## Acceptance Criteria

### Pillar 1 — Auth Conventions
- [ ] `allow_jwt`, `allow_session`, `allow_jwt_or_session`, `allow_google_credential` defined in `auth/dependencies.py`
- [ ] `allow_jwt_admin`, `allow_session_admin` defined as composed gates
- [ ] `require_permission(service, permission)` factory defined
- [ ] `needs_admin_storage` defined with `needs_*` naming
- [ ] Admin routers use `dependencies=[Depends(allow_jwt_admin)]` / `dependencies=[Depends(allow_session_admin)]` — no per-route auth repetition
- [ ] Authenticated API routers use `dependencies=[Depends(allow_jwt)]`
- [ ] Exchange router uses `dependencies=[Depends(allow_google_credential)]`
- [ ] Token route uses `Depends(allow_jwt_or_session)` per-route
- [ ] `auth/admin.py` removed — all logic in `auth/dependencies.py`
- [ ] All routers have `tags=[...]` reflecting their auth zone

### Pillar 2 — Middleware Consolidation
- [ ] `setup_middleware(app, settings)` helper in `main.py`
- [ ] No inline `add_middleware` calls in `create_app`
- [ ] `middleware.py` contains only class definitions and constants

### Pillar 3 — Settings DI Bridge
- [ ] `get_settings(request)` bridge function in `config.py`
- [ ] All routes use `Annotated[Settings, Depends(get_settings)]` instead of manual `request.app.state.settings`
- [ ] No `SettingsDep` alias — explicit `Annotated` in each route

### General
- [ ] All existing tests pass (412+)
- [ ] A new developer can determine the auth zone of any route in under 30 seconds
