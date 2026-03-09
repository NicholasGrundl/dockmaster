---
state: Finalized
changelog:
  "2026-03-09": "Created from gap analysis of legacy vs phase5-rbac-v2.md"
---

# Phase 5: RBAC — Implementation Guide

> Concrete coding checklist and gap-analysis notes for implementing Phase 5.
> Reference alongside: `phase5-rbac-v2.md` (design spec).

**Status**: Ready to implement
**Phase**: 5
**Last updated**: 2026-03-09

---

## Decisions Locked In

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | No `kind` field in Pydantic models | Fresh deploy, no migration. `kind` was a legacy type-discriminator pattern — Pydantic + typed storage methods make it unnecessary |
| D2 | `SecretsStorage` list methods deferred to Phase 6 | Keep Phase 5 minimal; add when Phase 6 actually needs them |
| D3 | TTL cache on `Authority` (cross-request caching) | Major improvement over legacy (per-request SM calls). Default 300s, configurable via `RBAC_CACHE_TTL` |
| D4 | Add `Authority.clear_cache()` method now | Phase 6 needs it for cache invalidation after writes; cheap to add in Phase 5 |
| D5 | `run_in_executor` wrapping for sync SM client in async context | Phase 5 uses sync `SecretManagerServiceClient`; wrap calls to avoid blocking FastAPI event loop |

---

## Gaps vs Legacy (resolved)

### G1 — Legacy loaded ALL roles for ALL subjects on every cache miss
**Legacy**: `Authority.get_permissions()` iterated all grants for a target and resolved roles for every subject — not just the one being queried. 50 subjects = 50+ SM calls on first miss.
**New spec improvement**: TTL cache keyed by target. On cache miss, still loads all grants for the target, but results are cached for `RBAC_CACHE_TTL` seconds — subsequent calls for same target are free.
**Further optimization** (optional): Only resolve roles for the queried subject, not all subjects. Deferred — the TTL cache already makes this acceptable for MVP.

### G2 — Legacy had no cross-request caching
**Legacy**: Fresh `Authority` per request, empty caches each time. Every RBAC check = 1+ SM API calls.
**New**: `Authority` is a lifespan-scoped singleton with TTL cache. First check per target = SM calls; subsequent checks within TTL = in-memory.

### G3 — `kind` field in legacy secret JSON
**Legacy secret format**: `{"kind": "Role", "name": "viewer", "permissions": [...]}`
**New format**: `{"name": "viewer", "permissions": [...]}` — no `kind` field.
**Rationale**: `kind` was a generic deserialization discriminator. Typed storage methods (`get_role()`, `get_service_grants()`) make it redundant. Fresh deploy, no migration needed.

### G4 — Legacy `Authority` had no `clear_cache()` method
**Legacy**: Auth was per-request, so no explicit cache clearing was needed.
**New**: Singleton `Authority` needs `clear_cache()` for Phase 6 admin writes to take effect immediately on the handling instance.

---

## Data Model

### Pydantic models (`src/dockmaster/rbac/models.py`)

```python
class Role(BaseModel):
    name: str
    permissions: list[str]

class Grant(BaseModel):
    subject: str              # email or service account
    roles: list[str]          # multiple roles per subject supported

class ServiceGrants(BaseModel):
    service: str
    grants: list[Grant]
```

**Note**: No `kind` field. Extra fields from legacy secrets are silently ignored by Pydantic v2 (in case a secret was written by old code — forward compatibility).

### Secret naming conventions

| Entity | Secret ID pattern |
|--------|-------------------|
| Role | `role-{name}` |
| ServiceGrants | `service-grants-{service}` |

---

## Implementation Checklist

### `src/dockmaster/rbac/models.py`

- [ ] `Role(BaseModel)`: `name: str`, `permissions: list[str]`
- [ ] `Grant(BaseModel)`: `subject: str`, `roles: list[str]`
- [ ] `ServiceGrants(BaseModel)`: `service: str`, `grants: list[Grant]`
- [ ] All models: `model_config = ConfigDict(extra="ignore")` — silently ignore extra fields (handles legacy `kind` field gracefully)

### `src/dockmaster/rbac/storage.py` — SecretsStorage

- [ ] Constructor: `__init__(client: SecretManagerServiceClient, project: str)`
- [ ] `_secret_path(secret_id: str) -> str` — returns `projects/{project}/secrets/{secret_id}/versions/latest`
- [ ] `_load_secret(secret_id: str) -> dict` — access secret version, decode UTF-8, parse JSON
- [ ] `_save_secret(secret_id: str, data: dict) -> None`:
  - [ ] Create secret if not exists (`replication: {automatic: {}}`)
  - [ ] Add new version with JSON-serialized data
- [ ] `_delete_secret(secret_id: str) -> None` — delete secret + all versions; swallow NotFound

**Role methods:**
- [ ] `get_role(name: str) -> Role` — load `role-{name}`, parse as `Role`
- [ ] `put_role(name: str, role: Role) -> None` — save as `role-{name}`
- [ ] `delete_role(name: str) -> None` — delete `role-{name}`

**ServiceGrants methods:**
- [ ] `get_service_grants(service: str) -> ServiceGrants` — load `service-grants-{service}`, parse as `ServiceGrants`
- [ ] `put_service_grants(service: str, grants: ServiceGrants) -> None` — save as `service-grants-{service}`
- [ ] `delete_service_grants(service: str) -> None` — delete `service-grants-{service}`

**No list methods in Phase 5** — added in Phase 6.

### `src/dockmaster/rbac/authority.py` — Authority

- [ ] Constructor: `__init__(storage: SecretsStorage, cache_ttl: int = 300)`
  - [ ] `_cache: dict[str, tuple[Any, float]] = {}` — maps cache key to (value, expiry_timestamp)
  - [ ] `_cache_ttl: int` — from constructor arg or `RBAC_CACHE_TTL` setting
- [ ] `_is_cached(key: str) -> bool` — check `time.time() < cache[key][1]`
- [ ] `_cache_get(key: str) -> Any` — return `_cache[key][0]`
- [ ] `_cache_set(key: str, value: Any) -> None` — store `(value, time.time() + _cache_ttl)`
- [ ] `clear_cache() -> None` — `self._cache = {}` (used by Phase 6 admin writes)

- [ ] `async has_permission(subject: str, target: str, permission: str) -> bool`:
  - [ ] Check cache for `f"grants:{target}"`
  - [ ] On cache miss: `await asyncio.get_event_loop().run_in_executor(None, storage.get_service_grants, target)` → cache result
  - [ ] Find `grant` where `grant.subject == subject` → return `False` if not found
  - [ ] For each `role_name` in `grant.roles`:
    - [ ] Check cache for `f"role:{role_name}"`
    - [ ] On cache miss: `run_in_executor` → load role → cache result
  - [ ] Collect union of all permissions from all roles
  - [ ] Return `permission in permissions_set`

**Note on loading strategy**: Unlike legacy (which loaded all subjects' roles), load only the roles for the matched subject's grants. This is more efficient and the TTL cache makes the target-level data fast on subsequent calls.

### `src/dockmaster/routes/permissions.py` — /auth/has endpoints

- [ ] `GET /auth/has/{subject}/{target}/{permission}` — requires authentication
  - [ ] FastAPI path params: `subject: str`, `target: str`, `permission: str`
  - [ ] Note: `permission` may contain `:` characters (e.g., `experiment:approve`) — standard path param handles this
  - [ ] `await authority.has_permission(subject, target, permission)`
  - [ ] `True` → `Response(status_code=204)` (empty body)
  - [ ] `False` → `JSONResponse(status_code=403, content={"status": "Error", "message": f"{subject} does not have {permission} for {target}"})`
  - [ ] Wrap in `try/except Exception` → 500 with generic message (details in logs only)

- [ ] `GET /auth/has` — requires authentication (query params variant)
  - [ ] Query params: `subject: str`, `target: str`, `permission: str` (all required)
  - [ ] FastAPI auto-validates presence; missing params → 422 (acceptable — better than the legacy 400 with wrong error message)
  - [ ] Same permission check logic as path-based
  - [ ] Bug fix: legacy returned "The **status** query parameter is missing" — new version won't have this typo (FastAPI handles missing param errors automatically)

### App lifespan wiring (`src/dockmaster/main.py`)

- [ ] Create `SecretManagerServiceClient` singleton (uses ISSUER credentials or ADC)
- [ ] Create `SecretsStorage` singleton
- [ ] Create `Authority` singleton with `RBAC_CACHE_TTL` from settings
- [ ] Attach to `app.state`
- [ ] Register `/auth/has` routes

### Settings additions (`src/dockmaster/config.py`)

- [ ] `SECRETS_PROJECT: str` — GCP project for Secret Manager (required)
- [ ] `RBAC_CACHE_TTL: int = 300` — Authority cache TTL in seconds

### Tests

- [ ] `tests/test_rbac_models.py`:
  - [ ] `Role` validates correctly; extra fields ignored
  - [ ] `Grant.roles` is list; supports multiple roles per subject
  - [ ] `ServiceGrants` serializes/deserializes correctly
- [ ] `tests/test_storage.py`:
  - [ ] `get_role()` / `put_role()` / `delete_role()` with mocked SM client
  - [ ] `get_service_grants()` / `put_service_grants()` / `delete_service_grants()`
  - [ ] Legacy-format secret (with `kind` field) is loaded without error
- [ ] `tests/test_authority.py`:
  - [ ] Permission granted (subject has role with permission) → True
  - [ ] Permission denied (subject has role, but not that permission) → False
  - [ ] Subject not in grants → False
  - [ ] TTL cache: first call hits SM, second call within TTL uses cache
  - [ ] TTL expiry: after TTL, SM is called again
  - [ ] `clear_cache()` forces fresh SM load
  - [ ] `run_in_executor` wrapping works in async context
- [ ] `tests/test_permissions.py`:
  - [ ] `GET /auth/has/{s}/{t}/{p}` → 204 when granted
  - [ ] `GET /auth/has/{s}/{t}/{p}` → 403 when denied (with correct message)
  - [ ] `GET /auth/has` (query params) → same results
  - [ ] Both endpoints require authentication
  - [ ] Permission string with `:` characters works (e.g., `experiment:approve`)
- [ ] `tests/fixtures/role_viewer.json` — sample role JSON
- [ ] `tests/fixtures/service_grants_example.json` — sample service grants JSON

### Acceptance gates

- [ ] `Role`, `Grant`, `ServiceGrants` validate correctly; extra fields ignored
- [ ] `Grant.roles` supports multiple roles per subject
- [ ] `SecretsStorage` reads/writes roles and grants
- [ ] `Authority.has_permission()` resolves correctly with exact string matching
- [ ] TTL cache: SM called once per TTL interval, not per request
- [ ] `Authority.clear_cache()` exists and resets cache
- [ ] `GET /auth/has/{s}/{t}/{p}` → 204 (granted) or 403 (denied)
- [ ] `GET /auth/has` (query) → same behavior
- [ ] Both endpoints require authentication
- [ ] Error message uses "subject" (not "status") — legacy typo fixed
- [ ] All tests pass with mocked SM (no real GCP calls)
- [ ] `uv run pytest tests/ -v`
- [ ] `just lint` and `just format` clean
- [ ] GCP Guide created: `docs/GUIDE-secret-manager.md`
