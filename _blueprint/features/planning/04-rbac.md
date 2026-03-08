# Client Library: RBAC

**Source file**: `dockmaster/rbac.py`

This module implements role-based access control (RBAC) backed by GCP Secret Manager. Roles and grants are stored as JSON secrets, and the `Authority` class resolves whether a subject has a given permission on a target service.

---

## Table of Contents

1. [Data Model Overview](#1-data-model-overview)
2. [SecretsStorage](#2-secretsstorage)
3. [Entity Base Class](#3-entity-base-class)
4. [Role](#4-role)
5. [Grant](#5-grant)
6. [ServiceGrants](#6-servicegrants)
7. [Authority](#7-authority)
8. [Permission Resolution Walkthrough](#8-permission-resolution-walkthrough)
9. [Dependencies](#9-dependencies)

---

## 1. Data Model Overview

The RBAC system has three data types and two layers:

```
ServiceGrants (per target service)
  └── Grant[] (per subject/principal)
        └── role name[] (references)
              └── Role (standalone entity)
                    └── permission[]
```

**Entities stored in Secret Manager:**
- `Role` -- a named set of permissions (e.g., `viewer` with `[read, list]`)
- `ServiceGrants` -- a list of grants for a target service, where each grant maps a subject to a set of roles

**Not stored independently:**
- `Grant` -- nested within `ServiceGrants`, maps a subject to role names

**Secret naming convention:**

| Entity | Secret ID Pattern | Example |
|---|---|---|
| Role | `role-{name}` | `role-admin`, `role-viewer` |
| ServiceGrants | `service-grants-{service}` | `service-grants-data-pipeline` |

---

## 2. `SecretsStorage`

**Signature:**
```python
class SecretsStorage:
    def __init__(self, sm_client, project)
```

CRUD backend that stores RBAC entities as JSON secrets in GCP Secret Manager. Each entity becomes a secret with versioned JSON payloads.

### Constructor

| Parameter | Type | Description |
|---|---|---|
| `sm_client` | `SecretManagerServiceClient` | Google Cloud Secret Manager client instance |
| `project` | str | GCP project ID where secrets are stored |

### Public Methods

#### `exists(entity_class, name) -> bool`

Checks whether an entity exists and has at least one version.

```python
def exists(self, entity_class, name) -> bool
```

- Constructs secret ID: `{entity_class.category}-{name}`
- Returns `True` only if the secret exists AND has at least one version
- Returns `False` if the secret doesn't exist or exists but has no versions

#### `load(entity_class, name) -> Entity | None`

Loads the latest version of an entity from Secret Manager.

```python
def load(self, entity_class, name) -> Entity | None
```

- Constructs secret ID: `{entity_class.category}-{name}`
- Accesses the `latest` version: `secret_version_path(project, secret_id, 'latest')`
- Decodes the payload as UTF-8 JSON
- Calls `entity_class.from_data(data)` to deserialize
- Returns `None` if the secret is not found (`NotFound` exception)

#### `save(instance) -> str`

Saves an entity as a new secret version.

```python
def save(self, instance) -> str
```

- Extracts the entity name dynamically: `getattr(instance, instance.__class__.name)`
  - For `Role`: reads `instance.name` (the role name field)
  - For `ServiceGrants`: reads `instance.service` (the service name field)
- Constructs secret ID: `{category}-{name}`
- Ensures the secret exists (creates if needed with automatic replication)
- Adds a new version with JSON-encoded `instance.data`
- Returns the secret version resource name (e.g., `projects/123/secrets/role-admin/versions/3`)

#### `delete(entity_class, name)`

Deletes an entire secret (all versions).

```python
def delete(self, entity_class, name)
```

- Constructs secret ID: `{entity_class.category}-{name}`
- Deletes the secret via `delete_secret()`
- Idempotent: swallows `NotFound` exceptions

### Private Methods

#### `_secret_exists(name) -> int`

Low-level existence check with version awareness.

| Return Value | Meaning |
|---|---|
| `1` | Secret exists and has at least one version |
| `0` | Secret exists but has no versions |
| `-1` | Secret does not exist |

Implementation: Lists secret versions and returns `1` on first result, `0` if no versions exist, `-1` on `NotFound`.

#### `_ensure_secret_exists(name)`

Creates the secret if `_secret_exists()` returns `-1`. Uses automatic replication.

```python
self._sm_client.create_secret(request={
    'parent': f'projects/{self._project}',
    'secret_id': name,
    'secret': {'replication': {'automatic': {}}}
})
```

---

## 3. `Entity` Base Class

```python
class Entity:
```

Provides a common interface for storable entities. Not a dataclass itself -- serves as a mixin for dataclass subclasses.

### Class Protocol

Subclasses must define two **class-level** attributes:

| Attribute | Type | Purpose | Example |
|---|---|---|---|
| `category` | str | Secret name prefix | `'role'`, `'service-grants'` |
| `name` | str | Name of the instance field that holds the entity's identifier | `'name'`, `'service'` |

**Important:** The `name` class attribute is a string containing the *field name* to look up dynamically (via `getattr`), not the entity's name itself. This creates a naming collision with the dataclass `name` field in `Role` -- the dataclass field shadows the class attribute. This works because `SecretsStorage.save()` uses `instance.__class__.name` (gets the class attribute from the class, not the instance) while `instance.name` (on an instance) gets the dataclass field value.

### Class Methods

```python
@classmethod
def exists(entity_class, storage, name) -> bool
    # Delegates to storage.exists(entity_class, name)

@classmethod
def delete(entity_class, storage, name)
    # Delegates to storage.delete(entity_class, name)

@classmethod
def load(entity_class, storage, name) -> Entity | None
    # Delegates to storage.load(entity_class, name)
```

### Instance Methods

```python
def save(self, storage) -> str
    # Delegates to storage.save(self)
```

### Usage Pattern

```python
# Load via class method
role = Role.load(storage, 'admin')

# Save via instance method
role.permissions.append('delete')
role.save(storage)

# Check existence
if Role.exists(storage, 'admin'):
    Role.delete(storage, 'admin')
```

---

## 4. `Role`

**Signature:**
```python
@dataclass
class Role(Entity):
    category = 'role'
    name = 'name'
    name: str
    permissions: list[str] = field(default_factory=list)
```

A named role with a list of permission strings.

### Class Attributes

| Attribute | Value | Purpose |
|---|---|---|
| `category` | `'role'` | Secret prefix: secrets are named `role-{name}` |
| `name` | `'name'` | Points to the `name` field as the entity identifier |

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | str | required | Role identifier (e.g., `'admin'`, `'viewer'`) |
| `permissions` | list[str] | `[]` | Permission strings (e.g., `['read', 'write', 'delete']`) |

### `from_data(data)` (static factory)

```python
def from_data(data) -> Role
```

Creates a `Role` from a dict (as loaded from Secret Manager JSON).

| Key | Default | Description |
|---|---|---|
| `data['name']` | -- | Role name |
| `data['permissions']` | `[]` | Permission list |

Note: This is defined as a plain function (no `@staticmethod` or `@classmethod` decorator), but works when called as `Role.from_data(data)` because it doesn't reference `self` or `cls`.

### `data` (property)

```python
@property
def data(self) -> dict
```

Returns the JSON-serializable representation:

```json
{
  "kind": "Role",
  "name": "admin",
  "permissions": ["read", "write", "delete"]
}
```

### Secret Manager JSON Example

Secret: `role-admin`
```json
{
  "kind": "Role",
  "name": "admin",
  "permissions": ["read", "write", "delete", "manage"]
}
```

---

## 5. `Grant`

**Signature:**
```python
@dataclass
class Grant:
    subject: str
    roles: list[str]
```

Maps a subject (principal) to a list of role names. Not an `Entity` subclass -- `Grant` objects are always nested within a `ServiceGrants` instance and are never stored independently.

### Fields

| Field | Type | Description |
|---|---|---|
| `subject` | str | Principal identifier (e.g., service account email, user email) |
| `roles` | list[str] | List of role names granted to this subject |

### `from_data(data)` (static factory)

```python
def from_data(data) -> Grant
```

| Key | Default | Description |
|---|---|---|
| `data['subject']` | -- | Subject identifier |
| `data['roles']` | `[]` | Role name list |

### `data` (property)

```json
{
  "kind": "Grant",
  "subject": "worker@project.iam.gserviceaccount.com",
  "roles": ["admin", "viewer"]
}
```

---

## 6. `ServiceGrants`

**Signature:**
```python
@dataclass
class ServiceGrants(Entity):
    category = "service-grants"
    name = 'service'
    service: str
    grants: list[Grant] = field(default_factory=list)
```

A collection of grants for a specific target service. Each grant maps a subject to its roles on this service.

### Class Attributes

| Attribute | Value | Purpose |
|---|---|---|
| `category` | `'service-grants'` | Secret prefix: secrets are named `service-grants-{service}` |
| `name` | `'service'` | Points to the `service` field as the entity identifier |

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `service` | str | required | Target service identifier (e.g., `'data-pipeline'`) |
| `grants` | list[Grant] | `[]` | List of subject-to-roles mappings |

### `from_data(data)` (static factory)

```python
def from_data(data) -> ServiceGrants
```

Deserializes nested grants:
```python
ServiceGrants(
    data.get('service'),
    [Grant.from_data(grant) for grant in data.get('grants', [])]
)
```

### `data` (property)

```json
{
  "kind": "ServiceGrants",
  "service": "data-pipeline",
  "grants": [
    {
      "kind": "Grant",
      "subject": "worker@project.iam.gserviceaccount.com",
      "roles": ["admin"]
    },
    {
      "kind": "Grant",
      "subject": "reader@project.iam.gserviceaccount.com",
      "roles": ["viewer"]
    }
  ]
}
```

---

## 7. `Authority`

**Signature:**
```python
class Authority:
    def __init__(self, storage)
```

The RBAC permission engine. Loads roles and service grants from `SecretsStorage`, resolves permissions for subjects, and caches results for the lifetime of the instance.

### Constructor

| Parameter | Type | Description |
|---|---|---|
| `storage` | SecretsStorage | Backend for loading Role and ServiceGrants entities |

### Internal State

| Attribute | Type | Description |
|---|---|---|
| `_storage` | SecretsStorage | The storage backend |
| `_roles` | dict[str, Role] | Cache of loaded roles, keyed by role name |
| `_permissions` | dict[str, dict[str, set[str]]] | Cache of resolved permissions: `{target: {subject: set(permissions)}}` |

### Methods

#### `get_role(name) -> Role | None`

Loads a role, caching the result.

```python
def get_role(self, name) -> Role | None
```

1. Check `_roles` cache for `name`
2. If not cached, load from storage: `Role.load(self._storage, name)`
3. Cache the result if found
4. Return `Role` or `None`

#### `get_permissions(target, subject) -> set[str] | None`

Resolves all permissions a subject has on a target service.

```python
def get_permissions(self, target, subject) -> set[str] | None
```

1. Check `_permissions` cache for `target`
2. If not cached, load `ServiceGrants` for the target
3. For each `Grant` in the service grants:
   - Get or create a permission set for `grant.subject`
   - For each role name in `grant.roles`:
     - Load the `Role` via `get_role(name)` (uses role cache)
     - Add all `role.permissions` to the subject's permission set
4. Cache the entire `{subject: set(permissions)}` dict for the target
5. Return `permissions.get(subject)` -- the set for the requested subject, or `None` if subject has no grants

#### `has_permission(subject, target, permission) -> bool`

Top-level permission check.

```python
def has_permission(self, subject, target, permission) -> bool
```

1. Calls `get_permissions(target, subject)`
2. If result is `None` (subject not found in grants): returns `False`
3. Otherwise: returns `permission in permissions`

### Caching Behavior

The `Authority` instance caches both roles and resolved permissions for its entire lifetime:

- **In the service**: Authority is created per-request via `get_authority()` cached in Flask `g`. This means:
  - Each HTTP request gets a fresh Authority with empty caches
  - Multiple permission checks within the same request share cached data
  - No cross-request caching -- every request re-reads from Secret Manager

- **Cache invalidation**: There is no explicit invalidation. Changes to roles or grants in Secret Manager take effect on the next request (since Authority is re-created).

- **Cache scope**: If `has_permission` is called for the same target with different subjects in the same request, the second call uses the already-loaded `ServiceGrants` (all subjects for that target are resolved in one pass).

---

## 8. Permission Resolution Walkthrough

**Scenario:** Check if `worker@project.iam.gserviceaccount.com` has `execute` permission on `data-pipeline`.

### Step 1: Data in Secret Manager

Secret `role-operator`:
```json
{"kind": "Role", "name": "operator", "permissions": ["execute", "status"]}
```

Secret `role-viewer`:
```json
{"kind": "Role", "name": "viewer", "permissions": ["read", "list"]}
```

Secret `service-grants-data-pipeline`:
```json
{
  "kind": "ServiceGrants",
  "service": "data-pipeline",
  "grants": [
    {"subject": "worker@project.iam.gserviceaccount.com", "roles": ["operator"]},
    {"subject": "reader@project.iam.gserviceaccount.com", "roles": ["viewer"]}
  ]
}
```

### Step 2: `has_permission('worker@...', 'data-pipeline', 'execute')`

1. Calls `get_permissions('data-pipeline', 'worker@...')`
2. `_permissions` cache miss for `'data-pipeline'`
3. Loads `ServiceGrants.load(storage, 'data-pipeline')` from Secret Manager
4. Iterates grants:
   - **Grant 1**: subject=`worker@...`, roles=`['operator']`
     - Creates empty set for `worker@...`
     - Loads `Role('operator')` -> permissions=`['execute', 'status']`
     - Adds to set: `{'execute', 'status'}`
   - **Grant 2**: subject=`reader@...`, roles=`['viewer']`
     - Creates empty set for `reader@...`
     - Loads `Role('viewer')` -> permissions=`['read', 'list']`
     - Adds to set: `{'read', 'list'}`
5. Caches: `_permissions['data-pipeline'] = {'worker@...': {'execute', 'status'}, 'reader@...': {'read', 'list'}}`
6. Returns `{'execute', 'status'}` for `worker@...`
7. `has_permission` checks: `'execute' in {'execute', 'status'}` -> `True`

### Step 3: Subsequent call in same request

If `has_permission('reader@...', 'data-pipeline', 'read')` is called:
1. `_permissions` cache hit for `'data-pipeline'`
2. Returns `{'read', 'list'}` for `reader@...`
3. `'read' in {'read', 'list'}` -> `True`
4. **No Secret Manager calls** -- fully served from cache

---

## 9. Dependencies

### Direct Imports

| Import | Package | Purpose |
|---|---|---|
| `dataclasses.dataclass` | stdlib | Dataclass decorator for Role, Grant, ServiceGrants |
| `dataclasses.field` | stdlib | Default factory for list fields |
| `json` | stdlib | Serialize/deserialize entity data |
| `logging` | stdlib | Debug logging for secret load operations |
| `google.api_core.exceptions.NotFound` | `google-api-core` | Catch missing secrets |
| `google.api_core.exceptions.ClientError` | `google-api-core` | Imported but not directly caught (base class of NotFound) |

### Key Dependency: `google-cloud-secret-manager`

The `SecretsStorage` class uses the Secret Manager client's methods:

| Method | Purpose |
|---|---|
| `secret_path(project, secret_id)` | Build secret resource name |
| `secret_version_path(project, secret_id, version)` | Build version resource name |
| `create_secret(request)` | Create a new secret |
| `delete_secret(request)` | Delete a secret and all versions |
| `list_secret_versions(request)` | Check for existing versions |
| `access_secret_version(request)` | Read secret payload |
| `add_secret_version(request)` | Write new secret version |

### Secret Manager Resource Paths

```
projects/{project}/secrets/{secret_id}                          # secret
projects/{project}/secrets/{secret_id}/versions/{version}       # version
projects/{project}/secrets/{secret_id}/versions/latest          # latest version
```
