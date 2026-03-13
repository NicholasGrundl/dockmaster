---
state: Finalized
changelog:
  "2026-03-08 15h": "Initial spec created from planning sessions"
---

# Phase 5: RBAC

> Role-based access control with GCP Secret Manager storage and TTL-cached permission resolution.

**Status**: Planned
**Priority**: P0
**Phase**: 5
**Last updated**: 2026-03-08

---

## Problem

Dockmaster needs fine-grained permission checking: "Can subject X perform action Y on target Z?" Roles and grants are stored in GCP Secret Manager. Permission checks must be fast (cached) but eventually consistent.

## Solution

### Overview

Three layers:
1. **Data model** — Pydantic models for Role, Grant, ServiceGrants
2. **Storage** — GCP Secret Manager backend with secret naming conventions
3. **Authority** — Permission resolution engine with TTL-based in-memory caching

### Implementation Details

#### RBAC Data Model (models.py)

```python
class Grant(BaseModel):
    target: str          # e.g., "projects/*", "users/alice"
    permissions: set[str]  # e.g., {"read", "write", "admin"}

class Role(BaseModel):
    name: str
    grants: list[Grant]

class ServiceGrants(BaseModel):
    service: str
    roles: dict[str, str]  # subject_email → role_name
```

#### SecretsStorage (storage.py)

GCP Secret Manager backend:
- Secret naming convention: `role-{name}` for roles, `service-grants-{service}` for grants
- `get_role(name) → Role`
- `put_role(name, role) → None`
- `delete_role(name) → None`
- `get_service_grants(service) → ServiceGrants`
- `put_service_grants(service, grants) → None`
- `delete_service_grants(service) → None`
- Uses `google-cloud-secret-manager` sync client
- Wrapped with `run_in_executor` when called from async context

#### Authority (authority.py)

Permission resolution engine:

```python
class Authority:
    def __init__(self, storage: SecretsStorage, cache_ttl: int = 300):
        self._storage = storage
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[Any, float]] = {}

    async def has_permission(
        self, subject: str, target: str, permission: str
    ) -> bool:
        # 1. Look up service grants for subject's service
        # 2. Find subject's role
        # 3. Check if role grants permission on target
        # 4. Support wildcard targets (e.g., "projects/*")
```

- **TTL caching**: `RBAC_CACHE_TTL` config var (default 300s)
- Cache miss → `run_in_executor` → Secret Manager fetch → cache update
- Cache hit → return immediately (no async overhead)

#### Endpoints (permissions.py)

Two permission check endpoints:

```
GET /auth/has/{subject}/{target}/{permission}
GET /auth/has?subject=X&target=Y&permission=Z

Response 200:
{
  "has_permission": true,
  "subject": "user@example.com",
  "target": "projects/foo",
  "permission": "read"
}

Response 403:
{
  "has_permission": false,
  ...
}
```

#### Legacy Bug Fix

Error message typo: "status" → "subject" in missing parameter error responses.

### File Structure

```
src/dockmaster/
    rbac/
        __init__.py
        models.py           # Role, Grant, ServiceGrants
        storage.py          # SecretsStorage
        authority.py        # Authority (with TTL cache)
    routes/
        permissions.py      # /auth/has endpoints
tests/
    test_rbac_models.py
    test_storage.py
    test_authority.py
    test_permissions.py
    fixtures/
        role_viewer.json
        service_grants_example.json
docs/
    GUIDE-secret-manager.md
```

## Dependencies

- **Requires**: Phase 2 (auth middleware for protecting endpoints)
- **Enables**: Phase 6 (CRUD management of roles/grants)
- **New packages**: `google-cloud-secret-manager`

## Source References

| Planning Doc | Relevant Sections |
|---|---|
| `_blueprint/features/planning/04-rbac.md` | Role, Grant, Authority design |
| `_blueprint/features/planning/B-secrets-catalog.md` | Secret naming conventions, schemas |
| `_blueprint/features/planning/09-rbac-endpoints.md` | Authority lifecycle, caching strategy |
| `_blueprint/features/planning/07-service-endpoints.md` | Sections 4-5: /auth/has endpoint specs |
| `_blueprint/features/planning/E-confidence-notes.md` | "status" → "subject" typo bug |
| `_blueprint/features/planning/C-api-spec.md` | OpenAPI reference |

## Open Questions

None — all design decisions resolved in planning.

## Acceptance Criteria

- [ ] `Role`, `Grant`, `ServiceGrants` pydantic models validate correctly
- [ ] `SecretsStorage` reads/writes roles and grants to Secret Manager
- [ ] `Authority` resolves permissions with wildcard target support
- [ ] TTL cache works: first call fetches, subsequent calls use cache, cache expires after TTL
- [ ] `run_in_executor` wrapping works for async context
- [ ] `GET /auth/has/{subject}/{target}/{permission}` returns correct permission check
- [ ] `GET /auth/has` with query params returns correct permission check
- [ ] Error message uses "subject" not "status" (bug fix verified)
- [ ] `RBAC_CACHE_TTL` config var controls cache duration
- [ ] All tests pass with mocked Secret Manager (no real GCP calls)
- [ ] `uv run pytest tests/ -v` passes
- [ ] `just lint` and `just format` clean
- [ ] GCP Guide created: `docs/GUIDE-secret-manager.md`
