---
state: Finalized
changelog:
  "2026-03-12": "Created during alignment session — split from phase6-rbac-management-v2.md"
---

# Phase 6b: CLI + OAuth Login Flow

> Typer CLI with browser-based OAuth login for RBAC management from the terminal.

**Status**: Planned
**Priority**: P1
**Phase**: 6b
**Last updated**: 2026-03-12

---

## Problem

Admins need a command-line interface for managing RBAC roles and grants, testing permissions, and generating tokens. The CLI must authenticate as the user (not as a service account) so the server can check their admin RBAC role.

## Solution

### Overview

Typer-based CLI that communicates through the dockmaster API. Authenticates via a localhost-callback OAuth flow (same pattern as `gcloud`, `gh`, `firebase` CLIs). Short-lived JWT persisted to disk for the duration of an admin session.

### Implementation Details

#### CLI OAuth Login Flow

**Localhost callback pattern:**
1. CLI starts a temporary local HTTP server (e.g., `localhost:9876`)
2. Opens the user's browser to `{DOCKMASTER_URL}/auth/login?redirect_uri=http://localhost:9876/callback`
3. User authenticates with Google in the browser
4. Dockmaster completes OAuth flow and redirects to `localhost:9876/callback` with a token
5. CLI captures the token, stores it, and shuts down the local server
6. Control returns to the terminal

**Note**: The dockmaster server needs a small change to support a `redirect_uri` parameter on `/auth/login` for this flow. The redirect URI must be validated against an allowlist to prevent open redirect attacks.

#### Token Storage

- **Location**: `platformdirs.user_data_dir("dockmaster")` (cross-platform)
- **Contents**: JWT + expiry timestamp (no refresh token)
- **TTL**: 15 minutes
- **Behavior**: Before each API call, CLI checks expiry. If expired → prompt re-login. If valid → use stored token.
- **Format**: Simple JSON file (e.g., `~/.local/share/dockmaster/credentials.json`)

```json
{
  "token": "eyJhbG...",
  "expires_at": 1741234567
}
```

#### CLI Commands

```
dockmaster login                                         # OAuth login flow
dockmaster logout                                        # Delete stored credentials

dockmaster role get <name>                               # GET /admin/roles/{name}
dockmaster role list                                     # GET /admin/roles
dockmaster role create <name> [perm...]                  # POST /admin/roles
dockmaster role delete <name>                            # DELETE /admin/roles/{name}
dockmaster role add <name> [perm...]                     # GET then PUT /admin/roles/{name}
dockmaster role remove <name> [perm...]                  # GET then PUT /admin/roles/{name}

dockmaster service get <service>                         # GET /admin/grants/{service}
dockmaster service delete <service>                      # DELETE /admin/grants/{service}
dockmaster service grant <service> <subject> [role...]   # GET then POST /admin/grants/{service}
dockmaster service revoke <service> <subject>            # GET then POST /admin/grants/{service}

dockmaster test <subject> <target> <permission>          # GET /auth/has/{s}/{t}/{p}
dockmaster token <keyfile> [--subject <s>] [--audience <a>] [--lifetime <n>]  # Generate JWT from SA key
```

Entry point registered in `pyproject.toml`:
```toml
[project.scripts]
dockmaster = "dockmaster.cli.main:app"
```

#### CLI Authentication

All commands (except `login`, `logout`, `token`) require a valid stored JWT:
1. Check for stored credentials at `platformdirs.user_data_dir("dockmaster")/credentials.json`
2. If missing or expired → prompt: "Not logged in. Run `dockmaster login` first." (exit 1)
3. If valid → send as `Authorization: Bearer <jwt>` header

The server validates the JWT and checks the user's admin RBAC role (same auth flow as the UI).

#### CLI Output

- All commands output JSON (pretty-printed via `json.dumps(data, indent=2)`)
- Exit code 0 on success, 1 on error
- `dockmaster test` preserves legacy output: `Oui!` (exit 0) or `Non!` (exit 1)

#### Legacy Bug Fixes

1. **Revoke wildcard off-by-one**: Legacy `if found > 0` skipped grants at position 0. New implementation uses `grants = [g for g in grants if g.subject != subject]`.
2. **Role remove ValueError**: Legacy raised `ValueError` when grant didn't exist. New implementation checks existence first and returns a clear error message.

### File Structure

```
src/dockmaster/
    cli/
        __init__.py
        main.py             # Typer app entry point + login/logout commands
        auth.py             # OAuth login flow (localhost callback + token storage)
        roles.py            # role commands
        services.py         # service grant commands
        token.py            # token generation command (SA key → JWT)
tests/
    test_cli_auth.py        # login flow, token storage, expiry
    test_cli_roles.py       # role commands (mock httpx)
    test_cli_services.py    # service commands (mock httpx)
    test_cli_token.py       # token generation
```

## Dependencies

- **Requires**: Phase 6 (admin CRUD endpoints must exist)
- **Enables**: Terminal-based RBAC management
- **New packages**: `typer>=0.9`, `platformdirs`

## Source References

| Planning Doc | Relevant Sections |
|---|---|
| `_blueprint/features/planning/11-cli-tool.md` | CLI commands, argument patterns |
| `_blueprint/features/planning/E-confidence-notes.md` | Revoke off-by-one, role remove ValueError bugs |

## Open Questions

1. **Localhost callback port**: Fixed port (9876) or dynamic (find available port)? Dynamic is more robust.
2. **`/auth/login` redirect_uri support**: Needs server-side change. Should redirect URI allowlist be in Settings or hardcoded to `localhost:*`?
3. **CLI UX**: Positional args vs named flags — see CLI UX Redesign in feature-backlog.md.

## Acceptance Criteria

- [ ] `dockmaster login` opens browser, completes OAuth, stores JWT
- [ ] `dockmaster logout` deletes stored credentials
- [ ] Stored JWT expires after 15 minutes; CLI prompts re-login
- [ ] Token stored via `platformdirs` (cross-platform path)
- [ ] CLI `role` commands: get, list, create, delete, add, remove
- [ ] CLI `service` commands: get, delete, grant (multi-role), revoke
- [ ] CLI `test` command: returns Oui!/Non!, exit codes 0/1
- [ ] CLI `token` command: generates JWT from keyfile
- [ ] Legacy bugs fixed: revoke off-by-one, role remove ValueError
- [ ] `dockmaster` entry point registered in pyproject.toml
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] `just lint` and `just format` clean
