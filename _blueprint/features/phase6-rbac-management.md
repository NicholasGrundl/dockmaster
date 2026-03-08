---
state: Finalized
changelog:
  "2026-03-08 15h": "Initial spec created from planning sessions"
---

# Phase 6: RBAC Management + CLI

> CRUD endpoints for roles and grants, Typer CLI tool, and minimal admin UI.

**Status**: Planned
**Priority**: P1
**Phase**: 6
**Last updated**: 2026-03-08

---

## Problem

Operators need to manage RBAC roles and grants. The legacy codebase had no management API — all changes required direct Secret Manager edits. We need CRUD endpoints, a CLI for scripting, and a simple admin UI for visual management.

## Solution

### Overview

Three management interfaces, all sharing the same backend (`SecretsStorage` + `Authority` from Phase 5):
1. **REST API** — CRUD endpoints at `/admin/*` (new — not in legacy)
2. **CLI** — Typer-based command-line tool
3. **Admin UI** — Minimal Jinja2+HTMX dashboard at `/admin/*`

### Implementation Details

#### CRUD REST Endpoints (admin.py)

All endpoints require authentication (auth middleware from Phase 2).

**Roles:**
- `GET /admin/roles` — list all roles
- `GET /admin/roles/{name}` — get role details
- `POST /admin/roles` — create role
- `PUT /admin/roles/{name}` — update role
- `DELETE /admin/roles/{name}` — delete role

**Grants:**
- `GET /admin/grants` — list all service grants
- `GET /admin/grants/{service}` — get grants for a service
- `POST /admin/grants/{service}` — create/update grants for a service
- `DELETE /admin/grants/{service}` — delete all grants for a service

#### CLI Tool (cli/)

Typer-based CLI with subcommands:

```
dockmaster role get <name>
dockmaster role create <name> --grant <target>:<permissions>
dockmaster role delete <name>
dockmaster role add <name> --grant <target>:<permissions>
dockmaster role remove <name> --grant <target>:<permissions>

dockmaster service get <service>
dockmaster service delete <service>
dockmaster service grant <service> <subject> <role>
dockmaster service revoke <service> <subject>

dockmaster test <subject> <target> <permission>
dockmaster token <subject> [--audience <aud>] [--lifetime <seconds>]
```

Entry point registered in `pyproject.toml`:
```toml
[project.scripts]
dockmaster = "dockmaster.cli.main:app"
```

#### Legacy Bug Fixes

1. **Revoke wildcard off-by-one**: Legacy `revoke` command had an off-by-one error when removing wildcard grants. New implementation uses direct dict/set operations.
2. **Role remove ValueError**: Legacy `role remove` raised `ValueError` when the grant didn't exist. New implementation checks existence first and returns a clear error message.

#### Admin UI (templates/admin/)

Minimal Jinja2+HTMX pages:
- **Layout** (`layout.html`) — nav bar, auth check
- **Roles page** (`roles.html`) — table of roles with create/edit/delete
- **Grants page** (`grants.html`) — table of service grants with create/edit/delete
- HTMX for inline editing and deletion without full page reloads
- Protected by auth middleware (session or JWT required)

### File Structure

```
src/dockmaster/
    routes/
        admin.py            # RBAC CRUD endpoints at /admin/*
    cli/
        __init__.py
        main.py             # Typer app entry point
        roles.py            # role commands
        services.py         # service grant commands
        token.py            # token generation command
    templates/
        admin/
            layout.html
            roles.html
            grants.html
tests/
    test_admin_endpoints.py
    test_cli_roles.py
    test_cli_services.py
    test_cli_token.py
```

## Dependencies

- **Requires**: Phase 5 (RBAC models, storage, authority)
- **Enables**: Full operational management of the auth system
- **New packages**: `typer>=0.9`

## Source References

| Planning Doc | Relevant Sections |
|---|---|
| `_blueprint/features/planning/10-admin-panel.md` | CRUD endpoint table, admin UI design |
| `_blueprint/features/planning/11-cli-tool.md` | CLI commands, argument patterns |
| `_blueprint/features/planning/E-confidence-notes.md` | Revoke off-by-one, role remove ValueError bugs |
| `_blueprint/features/planning/C-api-spec.md` | OpenAPI reference |

## Open Questions

None — all design decisions resolved in planning.

## Acceptance Criteria

- [ ] All CRUD endpoints work: create, read, update, delete for roles and grants
- [ ] CRUD endpoints require authentication
- [ ] CLI `role` commands: get, create, delete, add grant, remove grant
- [ ] CLI `service` commands: get, delete, grant role, revoke role
- [ ] CLI `test` command checks permissions
- [ ] CLI `token` command generates a JWT
- [ ] Admin UI renders roles and grants tables
- [ ] Admin UI supports inline CRUD via HTMX
- [ ] Legacy bugs fixed: revoke wildcard off-by-one, role remove ValueError
- [ ] `dockmaster` CLI entry point registered in pyproject.toml
- [ ] All tests pass
- [ ] `uv run pytest tests/ -v` passes
- [ ] `just lint` and `just format` clean
