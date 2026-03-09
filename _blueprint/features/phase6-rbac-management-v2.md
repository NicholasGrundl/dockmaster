---
state: Finalized
changelog:
  "2026-03-09 v2": "Audit polish — add admin auth (admin key + admin emails), remove UI (defer to backlog), add cache invalidation on mutations, specify CLI auth modes"
  "2026-03-08 15h": "Initial spec created from planning sessions"
---

# Phase 6: RBAC Management + CLI

> CRUD endpoints for roles and grants, Typer CLI tool. Admin UI deferred.

**Status**: Planned
**Priority**: P1
**Phase**: 6
**Last updated**: 2026-03-09

---

## Problem

Operators need to manage RBAC roles and grants. The legacy codebase had no management API — all changes required direct Secret Manager edits. We need CRUD endpoints and a CLI for scripting.

## Solution

### Overview

Two management interfaces, both sharing the same backend (`SecretsStorage` + `Authority` from Phase 5):
1. **REST API** — CRUD endpoints at `/admin/*`
2. **CLI** — Typer-based command-line tool

Admin UI is deferred to backlog (the CLI handles 100% of management tasks).

### Implementation Details

#### Admin Authorization

Two-layer admin auth system, checked in order:

1. **Admin Key** (`DOCKMASTER_ADMIN_KEY` env var): A shared secret. If `Authorization: Bearer <key>` matches this env var, full admin access is granted. Works without any GCP/OAuth setup — ideal for local dev, CLI usage, and bootstrapping.

2. **Admin Emails** (`DOCKMASTER_ADMIN_EMAILS` env var): Comma-separated list of emails. If the request comes from an authenticated user (via Google SSO/JWT) whose email is in this list, they have full admin access. For production use once OAuth is configured.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `DOCKMASTER_ADMIN_KEY` | `str` | `""` (disabled) | Shared secret for admin API access. Empty string disables this auth mode. |
| `DOCKMASTER_ADMIN_EMAILS` | `list[str]` | `[]` | Emails that have admin access when authenticated via Google SSO. |

The admin auth check is a FastAPI dependency applied to all `/admin/*` routes.

#### CRUD REST Endpoints (admin.py)

All endpoints require admin authorization (see above).

**Roles:**
- `GET /admin/roles` — list all roles (no pagination for MVP)
- `GET /admin/roles/{name}` — get role details
- `POST /admin/roles` — create role
- `PUT /admin/roles/{name}` — update role
- `DELETE /admin/roles/{name}` — delete role (no referential integrity check for MVP)

**Grants:**
- `GET /admin/grants` — list all service grants (no pagination for MVP)
- `GET /admin/grants/{service}` — get grants for a service
- `POST /admin/grants/{service}` — create/update grants for a service
- `DELETE /admin/grants/{service}` — delete all grants for a service

#### Cache Invalidation

All write operations (POST, PUT, DELETE) on roles and grants **must clear the Authority's TTL cache** after the mutation succeeds. This ensures RBAC changes take effect immediately on the instance that handled the request, rather than waiting up to 300s for TTL expiry.

```python
# After any CRUD write operation:
authority.clear_cache()
```

> **Note**: In a multi-instance deployment, only the instance handling the admin request has its cache cleared. Other instances will see the change after their TTL expires. This is accepted for MVP. See backlog for distributed cache invalidation.

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

#### CLI Authentication

The CLI always communicates through the dockmaster API (not directly to Secret Manager). Two auth modes:

1. **Admin key** (default): Reads `DOCKMASTER_ADMIN_KEY` and `DOCKMASTER_URL` from env vars. Sends the admin key as `Authorization: Bearer <key>`.
2. **SA key file**: Reads a service account key file (via `--credentials` flag or `DOCKMASTER_CREDENTIALS` env var). Signs a JWT and sends it as `Authorization: Bearer <jwt>`. For legacy-style workflows.

```
# Admin key mode (default)
export DOCKMASTER_URL=http://localhost:8000
export DOCKMASTER_ADMIN_KEY=my-secret-key
dockmaster role get viewer

# SA key mode
dockmaster --credentials /path/to/sa-key.json role get viewer
```

#### Legacy Bug Fixes

1. **Revoke wildcard off-by-one**: Legacy `revoke` command had an off-by-one error when removing grants. New implementation uses direct dict/set operations.
2. **Role remove ValueError**: Legacy `role remove` raised `ValueError` when the grant didn't exist. New implementation checks existence first and returns a clear error message.

### File Structure

```
src/dockmaster/
    auth/
        admin.py            # Admin authorization dependency
    routes/
        admin.py            # RBAC CRUD endpoints at /admin/*
    cli/
        __init__.py
        main.py             # Typer app entry point
        roles.py            # role commands
        services.py         # service grant commands
        token.py            # token generation command
tests/
    test_admin_auth.py
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

- [ ] Admin auth works: admin key grants access, admin emails grant access after SSO
- [ ] `DOCKMASTER_ADMIN_KEY` and `DOCKMASTER_ADMIN_EMAILS` settings configured
- [ ] All CRUD endpoints work: create, read, update, delete for roles and grants
- [ ] CRUD endpoints require admin authorization (not just authentication)
- [ ] Write operations clear the Authority TTL cache
- [ ] CLI `role` commands: get, create, delete, add grant, remove grant
- [ ] CLI `service` commands: get, delete, grant role, revoke role
- [ ] CLI `test` command checks permissions via the API
- [ ] CLI `token` command generates a JWT
- [ ] CLI supports admin key auth (env vars) and SA key file auth (--credentials)
- [ ] Legacy bugs fixed: revoke off-by-one, role remove ValueError
- [ ] `dockmaster` CLI entry point registered in pyproject.toml
- [ ] All tests pass
- [ ] `uv run pytest tests/ -v` passes
- [ ] `just lint` and `just format` clean
