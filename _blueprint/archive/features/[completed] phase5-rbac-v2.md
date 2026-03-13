---
state: Finalized
changelog:
  "2026-03-09 v2": "Audit polish — fix ServiceGrants to list[Grant] with multi-role, remove wildcards (exact match), match legacy 204/403, document SM tradeoffs, keep TTL cache"
  "2026-03-08 15h": "Initial spec created from planning sessions"
---

# Phase 5: RBAC

> Role-based access control with GCP Secret Manager storage and TTL-cached permission resolution.

**Status**: ✅ COMPLETE
**Priority**: P0
**Phase**: 5
**Last updated**: 2026-03-09

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
class Role(BaseModel):
    name: str
    permissions: list[str]  # e.g., ["read", "write", "execute"]

class Grant(BaseModel):
    subject: str            # e.g., "user@domain.com", "sa@project.iam.gserviceaccount.com"
    roles: list[str]        # e.g., ["viewer", "finance-admin"] — supports multiple roles per subject

class ServiceGrants(BaseModel):
    service: str            # e.g., "data-pipeline"
    grants: list[Grant]     # list of subject-to-roles mappings
```

This matches the legacy data model structure where each `Grant` maps a subject to a list of role names, allowing a subject to hold multiple roles for a single service.

#### Target Matching

Permission checks use **exact string matching** on targets for MVP. The target is the service name (e.g., `"data-pipeline"`).

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

**Why Secret Manager?** The legacy system uses GCP Secret Manager as the RBAC store. It's simple, GCP-native, and requires no additional infrastructure (no database to provision). Tradeoffs:
- **Pro**: Zero additional infrastructure, automatic encryption, versioning, IAM-based access control
- **Con**: Higher latency per access (~50-200ms), $0.03/10K access operations, 64KB secret size limit, no atomic compare-and-swap
- **Mitigation**: TTL caching (below) reduces SM calls to once per TTL interval instead of per-request

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
        # 1. Look up service grants for the target service
        # 2. Find the subject's grant entry
        # 3. Load each of the subject's roles
        # 4. Check if any role includes the requested permission
```

- **TTL caching**: `RBAC_CACHE_TTL` config var (default 300s)
- Cache miss → `run_in_executor` → Secret Manager fetch → cache update
- Cache hit → return immediately (no async overhead)
- This is an improvement over legacy, which re-read from SM on every request

#### Endpoints (permissions.py)

Two permission check endpoints (both require authentication — any authenticated user can check any subject, matching legacy):

```
GET /auth/has/{subject}/{target}/{permission}
GET /auth/has?subject=X&target=Y&permission=Z

Permission granted: 204 No Content (empty body)
Permission denied:  403 Forbidden
  {
    "status": "Error",
    "message": "{subject} does not have {permission} for {target}"
  }
```

Response codes match legacy behavior: 204 for granted, 403 for denied.

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
| `_blueprint/features/planning/04-rbac.md` | Role, Grant, ServiceGrants, Authority design |
| `_blueprint/features/planning/B-secrets-catalog.md` | Secret naming conventions, schemas |
| `_blueprint/features/planning/09-rbac-endpoints.md` | Authority lifecycle, caching strategy, 204/403 response pattern |
| `_blueprint/features/planning/07-service-endpoints.md` | Sections 4-5: /auth/has endpoint specs |
| `_blueprint/features/planning/E-confidence-notes.md` | "status" → "subject" typo bug |
| `_blueprint/features/planning/C-api-spec.md` | OpenAPI reference |

## Open Questions

None — all design decisions resolved in planning.

## Acceptance Criteria

- [ ] `Role`, `Grant`, `ServiceGrants` pydantic models validate correctly
- [ ] `Grant.roles` is `list[str]` supporting multiple roles per subject
- [ ] `SecretsStorage` reads/writes roles and grants to Secret Manager
- [ ] `Authority` resolves permissions with exact string matching on targets
- [ ] TTL cache works: first call fetches, subsequent calls use cache, cache expires after TTL
- [ ] `run_in_executor` wrapping works for async context
- [ ] `GET /auth/has/{subject}/{target}/{permission}` returns 204 (granted) or 403 (denied)
- [ ] `GET /auth/has` with query params returns correct permission check
- [ ] Both permission endpoints require authentication
- [ ] Error message uses "subject" not "status" (bug fix verified)
- [ ] `RBAC_CACHE_TTL` config var controls cache duration
- [ ] All tests pass with mocked Secret Manager (no real GCP calls)
- [ ] `uv run pytest tests/ -v` passes
- [ ] `just lint` and `just format` clean
- [ ] GCP Guide created: `docs/GUIDE-secret-manager.md`
