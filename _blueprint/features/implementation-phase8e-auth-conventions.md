---
state: Draft
changelog:
  "2026-03-17": "Created — auth dependency conventions, router-level gates, permission factory"
---

# Phase 8e: Auth Dependency Conventions

> Standardise how routes declare their auth requirements so the codebase is
> self-documenting and a new developer adding a route knows exactly what to
> reach for.

**Status**: Planned
**Priority**: P1
**Phase**: 8e
**Last updated**: 2026-03-17

---

## Problem

The current codebase has three problems for a developer adding a new route:

1. **Inconsistent patterns** — some routes use `Depends(get_current_user)` as a
   route param, others roll their own `HTTPBearer` instance (exchange, token
   endpoints). No single answer to "how do I protect a route with a JWT?"

2. **No router-level protection** — admin routes repeat `Depends(require_admin_api)`
   on every single endpoint. One missed `Depends` silently leaves a route
   unprotected. There is no "door" on the router itself.

3. **Naming conflates concerns** — `require_admin_api` does two things: checks
   the JWT (`get_current_user`) AND checks the admin role. There's no
   consistent vocabulary for "who can enter" vs "what can they do."

---

## Solution

### Three-Layer Auth Model

```
Layer 0 — Router gate (allow_*)
    Who is allowed into this zone at all?
    Applied once at the router via dependencies=[Depends(allow_*)].
    FastAPI enforces it on every route in the router automatically.

Layer 1 — RBAC permission check (require_permission)
    Is this authenticated user authorised to perform this specific action?
    Applied per-route for actions that need an RBAC lookup beyond the gate.

Layer 2 — Infrastructure capability check (require_writes, future require_config)
    Is the system currently capable of performing this operation?
    Applied per-route for operations that need optional infrastructure
    (e.g. admin SA key configured, system not in read-only mode).
```

**The rule**: a new dev adds a route and asks three questions in order:
1. Which router does this belong to? → inherit its gate for free.
2. Does this action require a specific RBAC permission? → add `require_permission`.
3. Does this action require optional infrastructure? → add `require_writes` etc.

---

### Layer 0 — Router-level gates (`allow_*`)

Four zones, four dependencies. All live in `auth/dependencies.py`.

| Zone | Dependency | What it does |
|---|---|---|
| **Public** | *(none — explicit by tag only)* | No auth. Intentionally open. |
| **Authenticated** | `allow_authenticated` | Valid dockmaster-issued JWT required. Returns user dict. |
| **Admin API** | `allow_admin` | JWT + `require_permission("dockmaster", "admin")`. Returns user dict. |
| **Admin UI** | `allow_admin_ui` | Session cookie + `require_permission("dockmaster", "admin")`. Returns user dict. |

```python
# auth/dependencies.py

async def allow_authenticated(request: Request, ...) -> dict:
    """Verify Bearer JWT. Returns user claims dict.

    Use as a router-level gate for any zone requiring a valid dockmaster
    JWT. Raises 401 if no token, 401 if invalid/expired.
    """
    ...

async def allow_admin(
    user: dict = Depends(allow_authenticated),
    request: Request = None,
) -> dict:
    """Bearer JWT + dockmaster admin permission.

    Wraps allow_authenticated, then checks require_permission("dockmaster", "admin").
    Use as router-level gate for admin API zones. Raises 403 if not admin.
    """
    ...

async def allow_admin_ui(request: Request) -> dict:
    """Session cookie + dockmaster admin permission.

    Session-based counterpart to allow_admin. For HTML/form-based admin
    pages. Redirects to /ui/login if no session, raises 403 if not admin.
    """
    ...
```

Applied at the router:
```python
# routes/admin.py
router = APIRouter(
    tags=["admin-api"],
    dependencies=[Depends(allow_admin)],
)
# Every route in this router is now admin-gated automatically.
# No per-route Depends(allow_admin) needed.
```

For **public** routes, the absence of a gate is the signal. Reinforce with the tag:
```python
# routes/health.py
router = APIRouter(tags=["public"])
# No dependencies= — intentionally public, documented by tag.
```

---

### Layer 1 — RBAC permission factory (`require_permission`)

A parameterised dependency factory. Lives in `auth/dependencies.py`.

```python
def require_permission(service: str, permission: str):
    """Dependency factory — asserts the current user has permission on service.

    Args:
        service:    The target service/resource (e.g. "dockmaster", "billing").
        permission: The required permission (e.g. "admin", "read", "write").

    Returns a FastAPI dependency that raises 403 if the check fails.

    Usage:
        # On a router (gate for the whole zone):
        dependencies=[Depends(require_permission("dockmaster", "admin"))]

        # On a single route (additional RBAC gate):
        _: None = Depends(require_permission("billing", "write"))

    How it resolves:
        1. Checks RBAC via Authority.has_permission(email, service, permission)
        2. Falls back to DOCKMASTER_ADMIN_EMAILS whitelist for ("dockmaster", "admin")
    """
    async def _check(
        user: dict = Depends(allow_authenticated),
        request: Request = None,
    ) -> None:
        email = user.get("email", "")
        authority = getattr(request.app.state, "authority", None)
        settings: Settings = request.app.state.settings
        granted = await _resolve_permission(email, service, permission, authority, settings)
        if not granted:
            logger.warning(
                "permission_denied",
                email=email,
                service=service,
                permission=permission,
            )
            raise HTTPException(status_code=403, detail="Access denied")
    return _check
```

**Admin pattern** using this:
```python
# allow_admin (router gate) is built on require_permission:
async def allow_admin(user: dict = Depends(allow_authenticated), ...) -> dict:
    await require_permission("dockmaster", "admin")(user=user, request=request)
    return user
```

**Future downstream use** (e.g. in a billing service SDK):
```python
# billing service route that calls dockmaster to gate access:
@router.get("/invoices")
async def list_invoices(
    _: None = Depends(require_permission("billing", "read")),
):
    ...
```

---

### Layer 2 — Infrastructure capability checks (`require_*`)

Not RBAC — these check what the **system** can do right now, not what the user is allowed to do.

```python
async def require_writes(request: Request) -> None:
    """Assert admin SM client is configured for write operations.

    Raises 503 if admin_storage is not on app.state.
    This is an infrastructure check, not an RBAC check — it asks
    'can we do this?' rather than 'is this user allowed to do this?'
    """
    ...
```

Future additions follow the same pattern:
```python
async def require_config(key: str, expected_value: Any) -> ...:
    """Assert a runtime config condition is met (e.g. not in read-only mode)."""
    ...
```

---

### FastAPI Tags for self-documentation

Every router gets a tag that makes its auth zone visible in the OpenAPI spec
and in code search:

| Router | Tag | Gate |
|---|---|---|
| `health.py`, `keys.py` | `"public"` | *(none)* |
| `login.py` | `"oauth"` | *(none — semi-public by design)* |
| `claims.py`, `exchange.py`, `token.py`, `permissions.py` | `"authenticated"` | `allow_authenticated` |
| `admin.py` | `"admin-api"` | `allow_admin` |
| `admin_ui.py` | `"admin-ui"` | `allow_admin_ui` |
| `ui.py` (protected) | `"ui"` | `allow_ui_session` (existing) |

---

## Migration Plan

### Files to change

**`src/dockmaster/auth/dependencies.py`**
- Add `allow_authenticated` (rename/wrap `get_current_user` — keep `get_current_user` as alias for backward compat during migration)
- Add `allow_admin` (wraps `allow_authenticated` + `require_permission("dockmaster", "admin")`)
- Add `allow_admin_ui` (migrate from `auth/admin.py`)
- Add `require_permission(service, permission)` factory
- Keep `require_writes` here or in `auth/admin.py` (TBD — both are reasonable)

**`src/dockmaster/auth/admin.py`**
- `require_admin_api` → replaced by `allow_admin` in `dependencies.py`
- `require_admin_ui` → replaced by `allow_admin_ui` in `dependencies.py`
- `require_admin_writes` → keep as `require_writes`, move to `dependencies.py` or keep here
- File may become empty; remove or repurpose

**`src/dockmaster/routes/admin.py`**
- Add `dependencies=[Depends(allow_admin)]` to `APIRouter(...)`
- Remove per-route `Depends(require_admin_api)` from every endpoint
- Keep per-route `Depends(require_writes)` on write endpoints

**`src/dockmaster/routes/admin_ui.py`**
- Add `dependencies=[Depends(allow_admin_ui)]` to `APIRouter(...)`
- Remove per-route `Depends(require_admin_ui)` from every endpoint

**`src/dockmaster/routes/claims.py`, `permissions.py`**
- Add `dependencies=[Depends(allow_authenticated)]` to `APIRouter(...)`
- Remove per-route `Depends(get_current_user)` where it's only used for auth (keep where the return value is used)

**`src/dockmaster/routes/exchange.py`, `token.py`**
- Migrate custom `HTTPBearer` + manual extraction to use `allow_authenticated`
  (these have custom auth logic — needs careful handling, see Open Questions)

**All route files** — add or update `tags=[...]` on `APIRouter(...)`.

**`tests/`** — update imports from `require_admin_api` → `allow_admin` etc.

---

## Open Questions

1. **`exchange.py` and `token.py`** have custom auth logic (exchange: JWT-then-access-token fallback; token: dual session+JWT auth). These can't be trivially migrated to `allow_authenticated`. Options:
   - Keep custom logic, just document it clearly
   - Extract custom logic into named dependencies (`allow_exchange_token`, `allow_dual_auth`) that follow the `allow_*` naming but live in their respective route files
   - Decision needed before implementation

2. **`get_current_user` backward compat** — tests import it directly. Keep as an alias during migration, remove in a follow-up pass.

3. **`auth/admin.py` fate** — if all functions move to `dependencies.py`, the file becomes empty. Remove or repurpose as a thin re-export for a version?

---

## Acceptance Criteria

- [ ] `allow_authenticated`, `allow_admin`, `allow_admin_ui` defined in `auth/dependencies.py`
- [ ] `require_permission(service, permission)` factory defined in `auth/dependencies.py`
- [ ] `require_writes` consolidated into `auth/dependencies.py`
- [ ] All admin routers use `dependencies=[Depends(allow_admin)]` — no per-route `Depends(allow_admin)` repetition
- [ ] All authenticated routers use `dependencies=[Depends(allow_authenticated)]`
- [ ] All routers have a `tags=[...]` entry reflecting their auth zone
- [ ] `exchange.py` and `token.py` custom auth decisions resolved and documented
- [ ] All existing tests pass, no new test failures
- [ ] A new developer can determine the auth zone of any route in under 30 seconds
