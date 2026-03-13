---
state: Finalized
changelog:
  "2026-03-13": "Alignment session — updated to match implementation reality (commands, files, resolved questions, status COMPLETE)"
  "2026-03-12": "Created during alignment session — split from phase6-rbac-management-v2.md"
---

# Phase 6c: CLI + OAuth Login Flow

> Typer CLI with browser-based OAuth login for RBAC management from the terminal.

**Status**: ✅ COMPLETE
**Priority**: P1
**Phase**: 6c
**Last updated**: 2026-03-13

---

## Problem

Admins need a command-line interface for managing RBAC roles and grants, testing permissions, and revoking sessions. The CLI must authenticate as the user (not as a service account) so the server can check their admin RBAC role.

## Solution

### Overview

Typer-based CLI that communicates through the dockmaster API. Authenticates via a localhost-callback OAuth flow (same pattern as `gcloud`, `gh`, `firebase` CLIs). Short-lived JWT persisted to disk for the duration of an admin session.

### Implementation Details

#### CLI OAuth Login Flow

**Localhost callback pattern:**
1. CLI starts a temporary local HTTP server on a dynamic port
2. Opens the user's browser to `{DOCKMASTER_URL}/auth/login?redirect_uri=http://localhost:{port}/callback`
3. User authenticates with Google in the browser
4. Dockmaster completes OAuth flow and redirects to `localhost:{port}/callback` with a short-lived JWT (15 min)
5. CLI captures the token, stores it, and shuts down the local server
6. Control returns to the terminal

**Server-side support**: `/auth/login` accepts a `redirect_uri` parameter, validated to localhost-only. The callback mints a short-lived JWT instead of setting a session cookie. `_pending_states` stores `dict[str, dict]` (with redirect_uri metadata) instead of `dict[str, bool]`.

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

#### CLI Commands (as implemented)

```
dockmaster login                                         # OAuth login flow
dockmaster logout                                        # Delete stored credentials

dockmaster role get <name>                               # GET /admin/roles/{name}
dockmaster role list                                     # GET /admin/roles
dockmaster role create <name> -p <perm> [-p <perm>...]   # POST /admin/roles
dockmaster role delete <name>                            # DELETE /admin/roles/{name}
dockmaster role add <name> -p <perm> [-p <perm>...]      # GET then PUT /admin/roles/{name}
dockmaster role remove <name> -p <perm> [-p <perm>...]   # GET then PUT /admin/roles/{name}

dockmaster grant get <service>                           # GET /admin/grants/{service}
dockmaster grant list                                    # GET /admin/grants
dockmaster grant delete <service>                        # DELETE /admin/grants/{service}
dockmaster grant add <service> <subject> -r <role> [-r <role>...]    # GET (allow_404) then POST
dockmaster grant remove <service> <subject> [-r <role>...]           # GET then POST (no -r = remove all)

dockmaster check <subject> <target> -p <permission>      # GET /auth/has/{s}/{t}/{p} → Oui!/Non!
```

**Design decisions:**
- D12: `grant` group (not `service`) to avoid grant/grant verb collision
- D13: `check` command (not `test`) for clarity
- D14: `--permission`/`-p` for role commands, `--role`/`-r` for grant commands
- D15: `token` command deferred until unified JWT issuer design
- D16: `grant remove` without `-r` flags removes all roles for that subject
- D19: `grant add` uses `allow_404=True` on GET (pragmatic read-modify-write for new services)

Entry point registered in `pyproject.toml`:
```toml
[project.scripts]
dockmaster = "dockmaster.cli.main:app"
```

#### CLI Authentication

All commands (except `login`, `logout`) require a valid stored JWT:
1. Check for stored credentials at `platformdirs.user_data_dir("dockmaster")/credentials.json`
2. If missing or expired → prompt: "Not logged in. Run `dockmaster login` first." (exit 1)
3. If valid → send as `Authorization: Bearer <jwt>` header

The server validates the JWT and checks the user's admin RBAC role (same auth flow as the UI).

#### CLI Output

- All commands output JSON (pretty-printed via `json.dumps(data, indent=2)`)
- Exit code 0 on success, 1 on error
- `dockmaster check` outputs `Oui!` (exit 0) or `Non!` (exit 1) — preserves legacy style

### File Structure (as implemented)

```
src/dockmaster/
    cli/
        __init__.py
        main.py             # Typer app entry point, command registration
        auth.py             # OAuth login flow (localhost callback + token storage)
        config.py           # Server URL + credential path config
        http.py             # Shared authenticated HTTP client
        roles.py            # role commands (-p/--permission flags)
        grants.py           # grant commands (-r/--role flags)
        check.py            # check command (subject + target positional, -p flag)
tests/
    test_cli_auth.py        # 12 tests — token storage, loading, expiry, delete
    test_cli_roles.py       # 12 tests — list, get, create, delete, add, remove
    test_cli_grants.py      # 12 tests — list, get, add, add-on-404, merge, remove, delete
    test_cli_check.py       # 4 tests — granted, denied, error, flag required
    test_cli_login_redirect.py  # 9 tests — redirect_uri validation, state storage
```

## Dependencies

- **Requires**: Phase 6 + 6b (admin CRUD + session endpoints must exist)
- **Enables**: Terminal-based RBAC management
- **New packages**: `typer>=0.9`, `platformdirs`

## Server-Side Changes

- `routes/login.py` — `redirect_uri` param on `/auth/login`, CLI JWT minting on callback, `_pending_states` changed from `dict[str, bool]` to `dict[str, dict]`
- `pyproject.toml` — added `typer`, `platformdirs`, `[project.scripts]` entry point, consolidated `[dependency-groups]` (D20)

## Resolved Questions (from original spec)

1. **Localhost callback port** → Dynamic (find available port). Resolved during implementation.
2. **redirect_uri allowlist** → Hardcoded to localhost-only validation. Full external redirect URI system deferred (D17).
3. **CLI UX** → Named flags: `-p/--permission` for roles, `-r/--role` for grants. Positional for subject/target. (D14)

## Deferred Items

1. **`token` command** — Deferred until dockmaster issues its own RS256 JWTs (unified token issuer design). Likely Phase 7+ scope. (D15)
2. **External service redirect URIs** — `/auth/login` accepts `redirect_uri` but only validates localhost. Future: allowlisted per-service redirect URIs. (D17)
3. **Server-side grant merge endpoint** — CLI does read-modify-write for `grant add/remove`. A `PATCH /admin/grants/{service}` would be atomic. Low priority. (D19)

## Acceptance Criteria

- [x] `dockmaster login` opens browser, completes OAuth, stores JWT
- [x] `dockmaster logout` deletes stored credentials
- [x] Stored JWT expires after 15 minutes; CLI prompts re-login
- [x] Token stored via `platformdirs` (cross-platform path)
- [x] CLI `role` commands: get, list, create, delete, add, remove (with `-p`)
- [x] CLI `grant` commands: get, list, delete, add, remove (with `-r`)
- [x] CLI `check` command: returns Oui!/Non!, exit codes 0/1
- [x] `dockmaster` entry point registered in pyproject.toml
- [x] 301 tests pass, ruff clean
