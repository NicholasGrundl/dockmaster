---
state: Finalized
changelog:
  "2026-03-12": "Alignment session: split CLI into Phase 6b, redesign admin auth (RBAC-first, no API key), add capability gate, update settings"
  "2026-03-09": "Created from gap analysis of legacy vs phase6-rbac-management-v2.md"
---

# Phase 6: RBAC Management — Implementation Guide

> Concrete coding checklist for implementing Phase 6 (admin endpoints + admin UI).
> CLI moved to Phase 6b. Reference alongside: `phase6-rbac-management-v2.md` (design spec).

**Status**: ✅ COMPLETE
**Phase**: 6
**Last updated**: 2026-03-12

---

## Decisions Locked In

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | CLI moved to Phase 6b | Phase 6 delivers admin endpoints + UI. CLI (with OAuth login flow) is a follow-up. |
| D2 | No DOCKMASTER_ADMIN_KEY (shared API key) | Dropped. Auth uses RBAC role + env whitelist fallback. SA keys stay server-side only. |
| D3 | Admin SA key = capability gate for writes | If `ADMIN_SA_KEY_FILE` is not set, write endpoints return 503. Read-only admin endpoints still work. |
| D4 | Admin auth: RBAC-first + env whitelist fallback | `has_permission(email, 'dockmaster', 'admin')` first. `DOCKMASTER_ADMIN_EMAILS` for bootstrap/emergency. |
| D5 | `SecretsStorage` list methods added in Phase 6 | Natural place — first needed here |
| D6 | Cache invalidated after every write operation | Ensures RBAC changes take effect immediately on the handling instance |
| D7 | Write endpoints return 503 when admin SA missing | 503 (Service Unavailable) signals config issue, not auth issue. Distinct from 403. |

---

## Gaps vs Legacy (resolved)

### G1 — CLI accessed SM directly
**Legacy**: `python -m dockmaster` with ADC → direct SM operations.
**New**: `dockmaster` CLI → dockmaster API → SM. Adds the API as a required intermediary. Documented in backlog as "Direct Secret Manager CLI Access" (emergency/migration use case).

### G2 — Legacy `service grant` used `subject:role1,role2` format
**Legacy**: Single argument with embedded colon/comma syntax was cryptic.
**New**: Space-separated positionals: `dockmaster service grant lims sarah@co.com pi lab-tech`.
Multiple roles supported. See CLI UX backlog note above.

### G3 — Legacy `service revoke` had a wildcard `:*` syntax (and an off-by-one bug)
**Legacy bug**: `if found > 0` — grants at position 0 (first grant) were never deleted.
**New**: `dockmaster service revoke <service> <subject>` — no role arg means "delete entire grant for subject". Clean fix.

### G4 — No CRUD API in legacy
**Legacy**: No `/admin/*` endpoints existed. All CRUD was CLI → direct SM.
**New**: Full REST CRUD at `/admin/*`. This is entirely new — no legacy gap, just new capability.

### G5 — Cache invalidation after writes
**Legacy**: Per-request Authority (no cache) — no invalidation needed.
**New**: Singleton Authority with TTL cache. Phase 6 writes must call `authority.clear_cache()` after mutations so changes are visible immediately on the handling instance.

---

## Already Exists (from earlier phases)

> These items are already implemented and should NOT be rebuilt in Phase 6.

- **`SecretsStorage` base class** — `src/dockmaster/rbac/storage.py` (Phase 4b): constructor, `_load_secret`, `_load_secret_raw`, `get_client_secret`
- **RBAC read methods** — Added in Phase 5: `get_role`, `get_service_grants`
- **`Authority` singleton** — `src/dockmaster/rbac/authority.py` (Phase 5): `has_permission`, TTL cache, `clear_cache()`
- **`SecretManagerServiceClient` + `SecretsStorage` singletons in lifespan** — `src/dockmaster/main.py` (Phase 4b)
- **`secrets_project` setting** — `src/dockmaster/config.py` (Phase 4b)
- **Admin dashboard UI at `/ui/`** — `src/dockmaster/routes/ui.py` (Phase 4c): Jinja2 + Tailwind CSS, `UIConfig`, auth guard (`require_ui_session`), sessions table
- **Session-based auth for UI** — `require_ui_session` dependency (Phase 4c)

## GCP SA Key Split — Admin Write Access

Phase 6 adds **write operations** to Secret Manager (`_save_secret`, `_delete_secret`, `put_role`, etc.).
These require a separate admin SA (`dockmaster-admin`) with SM write permissions
(`roles/secretmanager.admin` or `roles/secretmanager.secretVersionAdder`).

**Capability gate**: If `ADMIN_SA_KEY_FILE` is not configured:
- Read-only admin endpoints (`GET /admin/roles`, `GET /admin/grants/{service}`, etc.) still work using the runtime SA
- Write endpoints (`POST`, `PUT`, `DELETE`) return **503 Service Unavailable** with a message indicating admin SA is not configured

**Implementation needs:**
- New setting: `ADMIN_SA_KEY_FILE: str = ""` (path to admin SA key file; empty = writes disabled)
- If set: second `SecretManagerServiceClient` initialized with admin credentials in lifespan
- `SecretsStorage` write methods use the admin client
- Decision: single `SecretsStorage` with two clients, or separate read/write storage instances — resolve during Phase 6 planning

See decision log: "GCP SA key split — Read-only vs Admin" and "Admin authorization — RBAC-first with settings fallback".

## SecretsStorage Additions (Phase 6)

Add to `src/dockmaster/rbac/storage.py` (write methods require admin SA):

- [ ] `list_roles() -> list[str]` — list all role names
  - [ ] `sm_client.list_secrets(request={"parent": f"projects/{project}", "filter": "name:role-"})`
  - [ ] Extract name after `role-` prefix from each secret resource name
  - [ ] Return list of role name strings
- [ ] `list_service_grants() -> list[str]` — list all service names
  - [ ] Filter: `"name:service-grants-"`
  - [ ] Extract service name after `service-grants-` prefix

---

## Implementation Checklist

### `src/dockmaster/auth/admin.py` — Admin authorization + capability dependencies

**`require_admin` — authorization dependency:**
- [ ] Extract user identity from the request (session cookie for UI, JWT Bearer for API)
- [ ] **Check 1 — RBAC**: `authority.has_permission(email, "dockmaster", "admin")` → pass if True
- [ ] **Check 2 — Bootstrap fallback**: If RBAC check fails, check `email in settings.DOCKMASTER_ADMIN_EMAILS` → pass if True
- [ ] If both fail → 403 Forbidden
- [ ] If RBAC has no admin grants AND `DOCKMASTER_ADMIN_EMAILS` is empty → 403 (fail safe)
- [ ] **For UI admin routes**: Combine with `require_ui_session` (session cookie auth + admin role check)

**`require_admin_writes` — capability gate dependency:**
- [ ] Check if admin SM client is available on `app.state` (i.e., `ADMIN_SA_KEY_FILE` was configured)
- [ ] If not available → 503 Service Unavailable with message: "RBAC write operations not configured (admin SA key missing)"
- [ ] Use on all write endpoints (`POST`, `PUT`, `DELETE`). Read endpoints (`GET`) skip this check.

### `src/dockmaster/routes/admin.py` — CRUD endpoints

All endpoints use `Depends(require_admin)`.

#### Role endpoints

- [ ] `GET /admin/roles` — list all roles
  - [ ] `storage.list_roles()` in executor
  - [ ] For each name, optionally load full `Role` or return names only (names-only is faster)
  - [ ] Return `[{"name": "viewer", "permissions": [...]}]`
  - [ ] After: **no** cache invalidation (read-only)

- [ ] `GET /admin/roles/{name}` — get one role
  - [ ] `storage.get_role(name)` in executor
  - [ ] 404 if not found

- [ ] `POST /admin/roles` — create role
  - [ ] Body: `{"name": str, "permissions": list[str]}`
  - [ ] Check doesn't already exist → 409 Conflict if it does
  - [ ] `storage.put_role(name, role)` in executor
  - [ ] `authority.clear_cache()`
  - [ ] Return 201 with created role

- [ ] `PUT /admin/roles/{name}` — update role
  - [ ] Body: `{"permissions": list[str]}`
  - [ ] `storage.put_role(name, updated_role)` in executor
  - [ ] `authority.clear_cache()`
  - [ ] Return 200 with updated role

- [ ] `DELETE /admin/roles/{name}` — delete role
  - [ ] `storage.delete_role(name)` in executor
  - [ ] `authority.clear_cache()`
  - [ ] Return 204 No Content
  - [ ] **No referential integrity check** (deferred to backlog: "Role Deletion Referential Integrity")

#### Grant endpoints

- [ ] `GET /admin/grants` — list all service grants
  - [ ] `storage.list_service_grants()` in executor
  - [ ] Return list of service names (or full `ServiceGrants` objects)

- [ ] `GET /admin/grants/{service}` — get grants for a service
  - [ ] 404 if not found

- [ ] `POST /admin/grants/{service}` — create/update grants for a service
  - [ ] Body: `{"grants": [{"subject": str, "roles": list[str]}]}`
  - [ ] Upsert semantics: replace entire `ServiceGrants` for this service
  - [ ] `storage.put_service_grants(service, grants)` in executor
  - [ ] `authority.clear_cache()`
  - [ ] Return 200 or 201

- [ ] `DELETE /admin/grants/{service}` — delete all grants for a service
  - [ ] `storage.delete_service_grants(service)` in executor
  - [ ] `authority.clear_cache()`
  - [ ] Return 204

### Admin UI pages (extend existing `/ui/` dashboard)

> The dashboard at `/ui/` already exists (Phase 4c). Phase 6 adds RBAC management pages.

- [ ] RBAC roles page (`/ui/roles`) — list roles, create/edit/delete (requires admin + write capability)
- [ ] RBAC grants page (`/ui/grants`) — list services, view/edit grants per service
- [ ] Admin nav items — only visible when user has admin role
- [ ] Read-only mode — if admin SA not configured, show roles/grants but disable create/edit/delete buttons

### Settings additions (`src/dockmaster/config.py`)

- [ ] `ADMIN_SA_KEY_FILE: str = ""` — path to admin SA key file for SM write operations; empty = writes disabled (503)
- [ ] `DOCKMASTER_ADMIN_EMAILS: str | set[str] = set()` — bootstrap/emergency admin emails (comma-delimited, parsed like other set fields)

### App lifespan additions (`src/dockmaster/main.py`)

- [ ] If `ADMIN_SA_KEY_FILE` is set:
  - [ ] Create admin `SecretManagerServiceClient` with admin SA credentials
  - [ ] Attach to `app.state.admin_sm_client` (or create a write-capable `SecretsStorage` instance)
- [ ] If not set: `app.state.admin_sm_client = None` (capability gate checks this)

### Tests

- [ ] `tests/test_admin_auth.py`:
  - [ ] User with RBAC admin role → passes
  - [ ] User in DOCKMASTER_ADMIN_EMAILS → passes (bootstrap fallback)
  - [ ] User without admin role or whitelist → 403
  - [ ] Empty admin config (no RBAC admin, no whitelist) → 403
- [ ] `tests/test_admin_capability.py`:
  - [ ] Write endpoint with admin SA configured → works
  - [ ] Write endpoint without admin SA → 503
  - [ ] Read endpoint without admin SA → works (uses runtime SA)
- [ ] `tests/test_admin_endpoints.py`:
  - [ ] Full CRUD cycle: create → get → update → delete for roles
  - [ ] Full CRUD cycle for grants
  - [ ] `authority.clear_cache()` called after each write
  - [ ] List endpoints return all items

### Acceptance gates

- [ ] Admin auth: RBAC admin role grants access; DOCKMASTER_ADMIN_EMAILS grants access as fallback
- [ ] Capability gate: write endpoints return 503 when admin SA not configured
- [ ] Read-only admin endpoints work without admin SA
- [ ] All CRUD endpoints work for roles and grants (when admin SA present)
- [ ] Write operations clear `Authority` TTL cache
- [ ] Admin UI pages show roles/grants with create/edit/delete (when write-capable)
- [ ] Admin UI shows read-only view when admin SA missing
- [ ] Bootstrap flow: set DOCKMASTER_ADMIN_EMAILS → login → create admin role → grant to self → remove env whitelist
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] `just lint` and `just format` clean

---

## Phase 6b: CLI (separate scope)

> CLI implementation with OAuth login flow. See `implementation-phase6b-cli.md` (to be created during Phase 6b planning).

**Scope summary:**
- Typer CLI with localhost-callback OAuth login flow
- 15-minute JWT persisted to disk via `platformdirs` (no refresh token)
- CLI checks token expiry before each call; prompts re-login if expired
- Role commands: get, list, create, delete, add, remove
- Service commands: get, delete, grant (multi-role), revoke
- Token command: generate JWT from SA keyfile
- Test command: permission check (Oui!/Non!)
- New deps: `typer>=0.9`, `platformdirs`

**Decisions for Phase 6b planning:**
- Localhost callback vs device code flow (leaning localhost callback)
- CLI UX: positional args vs named flags (see CLI UX backlog note)
- Legacy bug fixes: revoke off-by-one, role remove ValueError
