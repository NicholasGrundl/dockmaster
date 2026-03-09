---
state: Finalized
changelog:
  "2026-03-09": "Created from gap analysis of legacy vs phase6-rbac-management-v2.md"
---

# Phase 6: RBAC Management + CLI — Implementation Guide

> Concrete coding checklist and gap-analysis notes for implementing Phase 6.
> Reference alongside: `phase6-rbac-management-v2.md` (design spec).

**Status**: Ready to implement
**Phase**: 6
**Last updated**: 2026-03-09

---

## Decisions Locked In

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | CLI goes through API (not direct SM access) | Architectural decision; legacy direct-SM access is backlog item |
| D2 | `service grant` supports multiple roles in one call (space-separated) | Matches legacy power-user behavior; see CLI UX backlog note |
| D3 | `service revoke <service> <subject>` with no role arg = revoke all | Cleaner than legacy's `:*` wildcard syntax |
| D4 | CLI output: JSON | Machine-friendly; no extra dependency; consistent with API |
| D5 | `SecretsStorage` list methods added in Phase 6 | Natural place — first needed here |
| D6 | Cache invalidated after every write operation | Ensures RBAC changes take effect immediately on the handling instance |

---

## CLI UX Backlog Note

The positional argument ordering (`dockmaster service grant <service> <subject> <role1> [role2...]`) is functional but the order may not be intuitive. Consider a future UX pass before the CLI is widely adopted:
- Option: named flags instead of positionals (`--service`, `--subject`, `--role`)
- Option: interactive prompting for required args
- Option: a config file approach for bulk operations
Add to `_blueprint/roadmap/feature-backlog.md` when this implementation doc is complete.

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

## SecretsStorage Additions (Phase 6)

Add to `src/dockmaster/rbac/storage.py`:

- [ ] `list_roles() -> list[str]` — list all role names
  - [ ] `sm_client.list_secrets(request={"parent": f"projects/{project}", "filter": "name:role-"})`
  - [ ] Extract name after `role-` prefix from each secret resource name
  - [ ] Return list of role name strings
- [ ] `list_service_grants() -> list[str]` — list all service names
  - [ ] Filter: `"name:service-grants-"`
  - [ ] Extract service name after `service-grants-` prefix

---

## Implementation Checklist

### `src/dockmaster/auth/admin.py` — Admin authorization dependency

- [ ] FastAPI dependency `require_admin`:
  - [ ] **Mode 1 — Admin key**: Check `Authorization: Bearer <key>` matches `settings.DOCKMASTER_ADMIN_KEY` (if key is set)
  - [ ] **Mode 2 — Admin email**: If Mode 1 fails, check request has a valid JWT (via `get_current_user`) and `claims["email"]` is in `settings.DOCKMASTER_ADMIN_EMAILS`
  - [ ] If neither passes → 403 Forbidden
  - [ ] If `DOCKMASTER_ADMIN_KEY` is `""` (disabled) AND `DOCKMASTER_ADMIN_EMAILS` is empty → 403 (no admin configured — fail safe)

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

### `src/dockmaster/cli/` — Typer CLI

Entry point: `dockmaster.cli.main:app` registered in `pyproject.toml`.

#### CLI Authentication (in `cli/main.py`)

```python
# Admin key mode (default)
DOCKMASTER_URL = os.getenv("DOCKMASTER_URL", "http://localhost:8000")
DOCKMASTER_ADMIN_KEY = os.getenv("DOCKMASTER_ADMIN_KEY", "")

def get_headers() -> dict:
    if DOCKMASTER_ADMIN_KEY:
        return {"Authorization": f"Bearer {DOCKMASTER_ADMIN_KEY}"}
    # SA key mode (--credentials flag)
    ...
```

#### `cli/roles.py` — role commands

```
dockmaster role get <name>                  → GET /admin/roles/{name}
dockmaster role list                         → GET /admin/roles
dockmaster role create <name> [perm...]      → POST /admin/roles
dockmaster role delete <name>               → DELETE /admin/roles/{name}
dockmaster role add <name> [perm...]        → GET then PUT /admin/roles/{name}
dockmaster role remove <name> [perm...]     → GET then PUT /admin/roles/{name}
```

- [ ] All commands use `httpx` to call the API with admin headers
- [ ] Output: JSON (pretty-printed via `json.dumps(data, indent=2)`)
- [ ] Exit code 1 on error (non-2xx response)

#### `cli/services.py` — service grant commands

```
dockmaster service get <service>                          → GET /admin/grants/{service}
dockmaster service delete <service>                       → DELETE /admin/grants/{service}
dockmaster service grant <service> <subject> [role...]    → GET then POST /admin/grants/{service}
dockmaster service revoke <service> <subject>             → GET then POST /admin/grants/{service}
```

**`service grant` implementation:**
- [ ] Load current ServiceGrants for service (or create empty if not found)
- [ ] Find or create `Grant` for subject
- [ ] Append new roles (deduplicated)
- [ ] PUT updated ServiceGrants

**`service revoke` implementation:**
- [ ] Load current ServiceGrants
- [ ] Remove the entire Grant for subject (not individual roles)
- [ ] Bug fix from legacy: use `grants = [g for g in grants if g.subject != subject]` — no off-by-one possible
- [ ] PUT updated ServiceGrants

#### `cli/token.py` — token command

```
dockmaster token <keyfile> [--subject <s>] [--audience <a>] [--lifetime <n>]
```

- [ ] Load `ServiceUser` from keyfile
- [ ] Call `service_user.get_token(subject, service_name, expiry)`
- [ ] Print token to stdout

#### `cli/test.py` — test command (permission check)

```
dockmaster test <subject> <target> <permission>    → GET /auth/has/{subject}/{target}/{permission}
```

- [ ] Returns `Oui!` (exit 0) or `Non!` (exit 1) — preserve legacy output strings

### Settings additions (`src/dockmaster/config.py`)

- [ ] `DOCKMASTER_ADMIN_KEY: str = ""` — shared secret for admin API access; empty = disabled
- [ ] `DOCKMASTER_ADMIN_EMAILS: list[str] = []` — emails with admin access via SSO

### `pyproject.toml` additions

- [ ] Entry point: `[project.scripts]` → `dockmaster = "dockmaster.cli.main:app"`
- [ ] New dependency: `typer>=0.9`

### Tests

- [ ] `tests/test_admin_auth.py`:
  - [ ] Admin key in header → passes
  - [ ] Admin email in JWT → passes
  - [ ] No auth → 403
  - [ ] Empty admin config → 403
- [ ] `tests/test_admin_endpoints.py`:
  - [ ] Full CRUD cycle: create → get → update → delete for roles
  - [ ] Full CRUD cycle for grants
  - [ ] `authority.clear_cache()` called after each write
  - [ ] List endpoints return all items
- [ ] `tests/test_cli_roles.py` — mock httpx calls, verify correct API calls and output
- [ ] `tests/test_cli_services.py` — verify grant/revoke logic (especially off-by-one fix)
- [ ] `tests/test_cli_token.py` — token generated from keyfile

### Acceptance gates

- [ ] Admin auth: admin key grants access; admin emails grant access after SSO
- [ ] All CRUD endpoints work for roles and grants
- [ ] Write operations clear `Authority` TTL cache
- [ ] CLI `role` commands: get, list, create, delete, add, remove
- [ ] CLI `service` commands: get, delete, grant (multi-role), revoke
- [ ] CLI `test` command: returns Oui!/Non!, exit codes 0/1
- [ ] CLI `token` command: generates JWT from keyfile
- [ ] CLI supports admin key (env vars) and SA key file (`--credentials`)
- [ ] Revoke off-by-one bug fixed (no index-based deletion)
- [ ] Role remove raises no uncaught ValueError
- [ ] `dockmaster` entry point registered in `pyproject.toml`
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] `just lint` and `just format` clean
