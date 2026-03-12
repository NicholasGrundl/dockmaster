---
state: Finalized
changelog:
  "2026-03-12": "Alignment session — split CLI into Phase 6b, redesign admin auth (RBAC-first, no API key), add capability gate, add admin UI pages"
  "2026-03-09 v2": "Audit polish — add admin auth (admin key + admin emails), remove UI (defer to backlog), add cache invalidation on mutations, specify CLI auth modes"
  "2026-03-08 15h": "Initial spec created from planning sessions"
---

# Phase 6: RBAC Management

> Admin CRUD endpoints for roles/grants and RBAC management pages in the existing admin dashboard.

**Status**: Planned
**Priority**: P1
**Phase**: 6
**Last updated**: 2026-03-12

---

## Problem

Operators need to manage RBAC roles and grants. The legacy codebase had no management API — all changes required direct Secret Manager edits. We need CRUD endpoints and an admin UI for managing roles and grants.

## Solution

### Overview

Two management interfaces sharing the same backend (`SecretsStorage` + `Authority` from Phase 5):
1. **REST API** — CRUD endpoints at `/admin/*`
2. **Admin UI** — RBAC management pages added to the existing `/ui/` dashboard (built in Phase 4c)

CLI moved to Phase 6b (separate scope with its own OAuth login flow).

### Implementation Details

#### Capability Gate — Admin SA Key

Write operations to Secret Manager require a separate admin SA (`dockmaster-admin`) with SM write permissions. The admin SA key presence is a **capability gate**:

- **Admin SA key present** (`ADMIN_SA_KEY_FILE` configured): write endpoints (`POST`, `PUT`, `DELETE`) are enabled
- **Admin SA key absent**: write endpoints return **503 Service Unavailable**. Read-only admin endpoints (`GET`) still work using the runtime SA.

This cleanly separates "can the server do this?" (503) from "are you allowed to?" (403).

#### Admin Authorization

Two-layer admin auth, checked in order:

1. **RBAC role check**: `authority.has_permission(email, "dockmaster", "admin")` — primary check once RBAC is bootstrapped.

2. **Settings fallback** (`DOCKMASTER_ADMIN_EMAILS` env var): Comma-separated list of admin emails. Used for bootstrapping (can't create admin role via RBAC if you need admin to access RBAC) and emergency access.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `ADMIN_SA_KEY_FILE` | `str` | `""` (disabled) | Path to admin SA key file for SM write operations. Empty = writes disabled (503). |
| `DOCKMASTER_ADMIN_EMAILS` | `str \| set[str]` | `set()` | Bootstrap/emergency admin emails. Comma-delimited, parsed like other set fields. |

The admin auth check is a FastAPI dependency applied to all `/admin/*` routes.

**Bootstrap flow**: First deploy sets `DOCKMASTER_ADMIN_EMAILS` with admin's email → login via UI → create "admin" role in RBAC → grant to self → optionally remove env whitelist.

#### CRUD REST Endpoints (admin.py)

All endpoints require admin authorization. Write endpoints additionally require the capability gate (`require_admin_writes`).

**Roles:**
- `GET /admin/roles` — list all roles (no pagination for MVP)
- `GET /admin/roles/{name}` — get role details
- `POST /admin/roles` — create role (503 if no admin SA)
- `PUT /admin/roles/{name}` — update role (503 if no admin SA)
- `DELETE /admin/roles/{name}` — delete role (503 if no admin SA, no referential integrity check for MVP)

**Grants:**
- `GET /admin/grants` — list all service grants (no pagination for MVP)
- `GET /admin/grants/{service}` — get grants for a service
- `POST /admin/grants/{service}` — create/update grants for a service (503 if no admin SA)
- `DELETE /admin/grants/{service}` — delete all grants for a service (503 if no admin SA)

#### Admin UI Pages

Extend the existing dashboard at `/ui/` (Phase 4c) with RBAC management pages:

- **Roles page** (`/ui/roles`) — list roles, create/edit/delete
- **Grants page** (`/ui/grants`) — list services, view/edit grants per service
- **Admin nav items** — only visible when user has admin role
- **Read-only mode** — if admin SA not configured, show roles/grants but disable create/edit/delete buttons

UI admin routes use `require_ui_session` (session cookie auth) combined with `require_admin` (RBAC role check).

#### Cache Invalidation

All write operations (POST, PUT, DELETE) on roles and grants **must clear the Authority's TTL cache** after the mutation succeeds.

```python
# After any CRUD write operation:
authority.clear_cache()
```

> **Note**: In a multi-instance deployment, only the instance handling the admin request has its cache cleared. Other instances will see the change after their TTL expires. This is accepted for MVP. See backlog for distributed cache invalidation.

#### Legacy Bug Fixes

1. **Revoke wildcard off-by-one**: Legacy `revoke` command had an off-by-one error when removing grants. New implementation uses direct dict/set operations.
2. **Role remove ValueError**: Legacy `role remove` raised `ValueError` when the grant didn't exist. New implementation checks existence first and returns a clear error message.

### File Structure

```
src/dockmaster/
    auth/
        admin.py            # Admin authorization + capability gate dependencies
    routes/
        admin.py            # RBAC CRUD endpoints at /admin/*
    templates/
        roles.html          # Roles management page
        grants.html         # Grants management page
tests/
    test_admin_auth.py
    test_admin_capability.py
    test_admin_endpoints.py
```

## Dependencies

- **Requires**: Phase 5 (RBAC models, storage, authority)
- **Enables**: Full operational management of the auth system via UI
- **New packages**: None (all deps already installed)

## Source References

| Planning Doc | Relevant Sections |
|---|---|
| `_blueprint/features/planning/10-admin-panel.md` | CRUD endpoint table, admin UI design |
| `_blueprint/features/planning/E-confidence-notes.md` | Revoke off-by-one, role remove ValueError bugs |
| `_blueprint/features/planning/C-api-spec.md` | OpenAPI reference |

## Open Questions

None — all design decisions resolved during alignment session (2026-03-12).

## Acceptance Criteria

- [ ] Admin auth works: RBAC admin role grants access; `DOCKMASTER_ADMIN_EMAILS` grants access as fallback
- [ ] Capability gate: write endpoints return 503 when admin SA not configured
- [ ] Read-only admin endpoints work without admin SA
- [ ] All CRUD endpoints work: create, read, update, delete for roles and grants
- [ ] CRUD endpoints require admin authorization (not just authentication)
- [ ] Write operations clear the Authority TTL cache
- [ ] Admin UI pages show roles/grants with create/edit/delete (when write-capable)
- [ ] Admin UI shows read-only view when admin SA missing
- [ ] Bootstrap flow works: set env whitelist → login → create admin role → grant to self
- [ ] Legacy bugs fixed: revoke off-by-one, role remove ValueError
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] `just lint` and `just format` clean
