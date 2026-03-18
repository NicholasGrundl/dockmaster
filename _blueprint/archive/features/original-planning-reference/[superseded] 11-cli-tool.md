# CLI Tool

**Source file**: `dockmaster/__main__.py`

The dockmaster CLI provides command-line management of RBAC roles and grants in GCP Secret Manager, permission testing, and JWT token generation. It uses the Click framework and is invoked as `python -m dockmaster`.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Authentication](#2-authentication)
3. [role Command](#3-role-command)
4. [service Command](#4-service-command)
5. [test Command](#5-test-command)
6. [token Command](#6-token-command)
7. [Commented-Out: keys Command](#7-commented-out-keys-command)
8. [Dependencies](#8-dependencies)

---

## 1. Overview

```
python -m dockmaster <command> [options] [arguments]

Commands:
  role      Manage RBAC roles (get, create, delete, add, remove permissions)
  service   Manage service grants (get, delete, grant, revoke roles)
  test      Test whether a subject has a permission on a target
  token     Generate a JWT from a service account key file
```

### Shared Infrastructure

```python
def get_client():
    client = secretmanager.SecretManagerServiceClient()
    return client

def get_storage(project):
    client = get_client()
    return SecretsStorage(client, project)
```

- `get_client()` creates a `SecretManagerServiceClient` with **no explicit credentials** -- uses Application Default Credentials (ADC). This means the CLI uses whatever credentials are configured in the local environment (e.g., `gcloud auth application-default login` or `GOOGLE_APPLICATION_CREDENTIALS` env var).
- `get_storage()` wraps the client in a `SecretsStorage` instance for the given project.
- The default project for all commands is `shipyard-auth-2022`.

---

## 2. Authentication

Unlike the service (which uses an explicit ISSUER key file), the CLI relies on Application Default Credentials:

| Method | How to Set Up |
|---|---|
| `gcloud auth application-default login` | Interactive login, stores credentials in `~/.config/gcloud/` |
| `GOOGLE_APPLICATION_CREDENTIALS` env var | Points to a service account key file |
| Compute Engine / GKE metadata | Automatic on GCP infrastructure |

The authenticated identity must have the following IAM permissions on the target project:

| Permission | Used By |
|---|---|
| `secretmanager.secrets.get` | All read operations |
| `secretmanager.versions.access` | `load()` operations |
| `secretmanager.versions.list` | `exists()` checks |
| `secretmanager.secrets.create` | `create` and `grant` operations |
| `secretmanager.versions.add` | All write operations |
| `secretmanager.secrets.delete` | `delete` operations |

---

## 3. `role` Command

```
python -m dockmaster role [--project PROJECT] OPERATION ROLE [PERMISSIONS...]
```

Manages RBAC `Role` entities in Secret Manager.

### Options

| Option | Default | Description |
|---|---|---|
| `--project` | `shipyard-auth-2022` | GCP project ID |

### Arguments

| Argument | Type | Description |
|---|---|---|
| `OPERATION` | Choice: get, create, delete, add, remove | Operation to perform |
| `ROLE` | string | Role name |
| `PERMISSIONS` | string (variadic) | Zero or more permission strings |

### Operations

#### `get` -- Display a role

```bash
python -m dockmaster role get viewer
```

Output (YAML):
```yaml
kind: Role
name: viewer
permissions:
- read
- list
```

Exits with code 1 if the role is not found.

#### `create` -- Create a new role

```bash
python -m dockmaster role create operator execute status monitor
```

- Checks if the role already exists -- exits with code 1 if it does
- Creates secret `role-operator` with the given permissions
- Permissions are converted to strings via `str(x)`

#### `delete` -- Delete a role

```bash
python -m dockmaster role delete operator
```

- Deletes the secret `role-operator` and all its versions
- Idempotent via `SecretsStorage.delete()` (swallows NotFound)
- **Does NOT check or update ServiceGrants that reference this role** -- grants may reference a deleted role, which would cause `get_role()` to return `None` and the role's permissions to be silently ignored

#### `add` -- Add permissions to an existing role

```bash
python -m dockmaster role add operator restart
```

- Loads the existing role (exits 1 if not found)
- Appends each permission only if not already present (deduplication)
- Saves as a new secret version

#### `remove` -- Remove permissions from an existing role

```bash
python -m dockmaster role remove operator monitor
```

- Loads the existing role (exits 1 if not found)
- Calls `list.remove()` for each permission
- **Raises `ValueError` if a permission is not in the list** -- the code does not check before removing
- Saves as a new secret version

---

## 4. `service` Command

```
python -m dockmaster service [--project PROJECT] OPERATION NAME [TARGETS...]
```

Manages `ServiceGrants` entities in Secret Manager.

### Options

| Option | Default | Description |
|---|---|---|
| `--project` | `shipyard-auth-2022` | GCP project ID |

### Arguments

| Argument | Type | Description |
|---|---|---|
| `OPERATION` | Choice: get, delete, grant, revoke | Operation to perform |
| `NAME` | string | Service name (target identifier) |
| `TARGETS` | string (variadic) | Zero or more grant targets in format `subject:role1,role2` |

### Target Format

Targets are parsed by `convert_target()`:

```python
def convert_target(target):
    target = target.strip()
    subject, _, roles = target.partition(':')
    roles = roles.strip().split(',') if len(roles) > 0 else []
    return Grant(subject, roles)
```

**Format:** `subject:role1,role2,role3`

**Examples:**
- `worker@project.iam.gserviceaccount.com:operator` → Grant(subject="worker@...", roles=["operator"])
- `admin@shipyard.com:operator,viewer` → Grant(subject="admin@...", roles=["operator", "viewer"])
- `user@example.com:` → Grant(subject="user@...", roles=[]) -- empty roles
- `user@example.com` → Grant(subject="user@example.com", roles=[]) -- no colon, empty roles

### Operations

#### `get` -- Display service grants

```bash
python -m dockmaster service get data-pipeline
```

Output (YAML, sorted keys disabled):
```yaml
kind: ServiceGrants
service: data-pipeline
grants:
- kind: Grant
  subject: worker@project.iam.gserviceaccount.com
  roles:
  - operator
- kind: Grant
  subject: reader@project.iam.gserviceaccount.com
  roles:
  - viewer
```

Exits with code 1 if the service doesn't exist.

#### `delete` -- Delete service grants

```bash
python -m dockmaster service delete data-pipeline
```

- Deletes secret `service-grants-data-pipeline`
- Idempotent

#### `grant` -- Grant roles to subjects

```bash
python -m dockmaster service grant data-pipeline \
    "worker@project.iam.gserviceaccount.com:operator" \
    "reader@project.iam.gserviceaccount.com:viewer"
```

**Behavior:**
1. Loads existing `ServiceGrants` or creates a new empty one
2. For each target:
   - If target has empty roles: skips (no-op)
   - If subject already exists in grants: merges roles (adds only new ones, no duplicates)
   - If subject is new: appends the entire Grant
3. Saves the updated ServiceGrants

**Merge logic for existing subjects:**
```python
for role in target.roles:
    if role not in existing.roles:
        existing.roles.append(role)
```

This is additive only -- `grant` never removes existing roles.

#### `revoke` -- Revoke roles from subjects

```bash
# Revoke specific roles
python -m dockmaster service revoke data-pipeline \
    "worker@project.iam.gserviceaccount.com:operator"

# Revoke all roles (wildcard)
python -m dockmaster service revoke data-pipeline \
    "worker@project.iam.gserviceaccount.com:*"

# Revoke all roles (empty roles)
python -m dockmaster service revoke data-pipeline \
    "worker@project.iam.gserviceaccount.com"
```

Exits with code 1 if the service doesn't exist.

**Wildcard/empty revocation behavior:**

When `'*'` is in `target.roles` or roles list is empty:
1. Iterates through grants to find the matching subject
2. Stores the position index
3. Deletes the grant at that position via `del s.grants[found]`

**Bug in wildcard revocation:** The code sets `found = -1` initially and checks `if found > 0` before deleting. This means:
- If the matching subject is at position 0 (first grant): `found = 0`, `0 > 0` is False, **grant is NOT deleted**
- If at position 1+: works correctly
- The initial value `-1` is correct for "not found", but position 0 is incorrectly treated as "not found"

**Specific role revocation:**

After the wildcard check (even if wildcard was triggered), the code continues to a second loop that removes specific roles:
```python
for existing in s.grants:
    if target.subject == existing.subject:
        for role in target.roles:
            if role in existing.roles:
                existing.roles.remove(role)
        break
```

This means for wildcard revocation, if the grant at position 0 wasn't deleted (due to the bug), the second loop would try to remove `'*'` from the roles list -- which would fail silently since `'*'` is not a real role name.

After processing all targets, the updated ServiceGrants is saved.

---

## 5. `test` Command

```
python -m dockmaster test [--project PROJECT] SUBJECT TARGET PERMISSION
```

Tests whether a subject has a specific permission on a target.

### Arguments

| Argument | Type | Description |
|---|---|---|
| `SUBJECT` | string | Principal to check |
| `TARGET` | string | Service/resource identifier |
| `PERMISSION` | string | Permission string to test |

### Behavior

```python
authority = Authority(storage)
if authority.has_permission(subject, target, permission):
    print('Oui!')
else:
    print('Non!')
    sys.exit(1)
```

- Creates a fresh Authority (same as the service does per-request)
- Prints `Oui!` and exits 0 on success
- Prints `Non!` and exits 1 on failure
- Exit code can be used in shell scripts: `python -m dockmaster test ... && echo allowed || echo denied`

### Example

```bash
$ python -m dockmaster test worker@project.iam.gserviceaccount.com data-pipeline execute
Oui!

$ python -m dockmaster test reader@project.iam.gserviceaccount.com data-pipeline execute
Non!
$ echo $?
1
```

---

## 6. `token` Command

```
python -m dockmaster token [--subject SUBJECT] [--service SERVICE] KEYFILE
```

Generates a JWT token from a service account key file.

### Options

| Option | Default | Description |
|---|---|---|
| `--subject` | None | JWT `sub` claim. If omitted, defaults to the service account's `client_email` |
| `--service` | None | JWT `aud` claim. If omitted, no audience is set |

### Arguments

| Argument | Type | Description |
|---|---|---|
| `KEYFILE` | string | Path to a GCP service account JSON key file |

### Behavior

```python
user = ServiceUser(keyfile)
token = user.get_token(subject=subject, service_name=service)
print(token.decode('utf-8'))
```

- Creates a `ServiceUser` from the key file
- Generates a JWT with default 3600s expiry
- Prints the JWT string to stdout

### Example

```bash
# Basic token (issuer = subject = service account email)
$ python -m dockmaster token /path/to/key.json
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IjEyMzQ...

# Token with custom subject and audience
$ python -m dockmaster token \
    --subject user@example.com \
    --service https://my-api.example.com/ \
    /path/to/key.json
eyJhbGciOiJSUzI1NiIs...

# Use in a curl command
$ TOKEN=$(python -m dockmaster token /path/to/key.json)
$ curl -H "Authorization: Bearer $TOKEN" https://dockmaster.service.example.net/claims
```

---

## 7. Commented-Out: `keys` Command

**Source:** `service.py:161-192` (commented out)

A `keys` command was planned but marked as broken (`# TODO: this is broken`). It would have:

- Listed all public keys from service accounts in a project
- Used `public_keys()` generator from `target.py`
- Supported JSON output (`--as-json`) or human-readable output
- Used `--identity` option or `GOOGLE_APPLICATION_CREDENTIALS` env var for credentials

This command is not functional and should be reimplemented if key listing is needed.

---

## 8. Dependencies

| Import | Package | Purpose |
|---|---|---|
| `sys` | stdlib | Exit codes, stderr output |
| `os` | stdlib | Imported but only used in commented-out `keys` command |
| `json` | stdlib | Imported but only used in commented-out `keys` command |
| `yaml` | `PyYAML` | YAML output for `get` operations |
| `click` | `click` | CLI framework (command groups, options, arguments) |
| `google.cloud.secretmanager` | `google-cloud-secret-manager` | Secret Manager client (uses ADC) |
| `dockmaster.client.ServiceUser` | dockmaster | JWT token generation |
| `dockmaster.Role, Grant, ServiceGrants, Authority, SecretsStorage, public_keys` | dockmaster | RBAC data model and storage |

### Migration Note

The CLI is entirely framework-independent -- it does not import Flask or any web framework. No changes are needed for the Flask-to-FastAPI migration. The only consideration is whether `PyYAML` should remain a dependency or if JSON output is preferred.
