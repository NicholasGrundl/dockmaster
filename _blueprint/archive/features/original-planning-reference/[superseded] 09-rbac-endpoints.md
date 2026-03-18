# Service: RBAC Endpoints (Deep Dive)

**Source file**: `service/dockmaster_service/service.py` (lines 68-149), `service/dockmaster_service/config.py` (lines 39-42)

This document provides a detailed analysis of the RBAC permission check endpoints, the per-request Authority lifecycle, and the data flow from HTTP request to Secret Manager and back.

---

## Table of Contents

1. [RBAC Endpoint Architecture](#1-rbac-endpoint-architecture)
2. [Path-Based Endpoint](#2-path-based-endpoint)
3. [Query-Based Endpoint](#3-query-based-endpoint)
4. [Authority Per-Request Lifecycle](#4-authority-per-request-lifecycle)
5. [End-to-End Permission Check Trace](#5-end-to-end-permission-check-trace)
6. [RBAC Data Model in Secret Manager](#6-rbac-data-model-in-secret-manager)
7. [Caching Behavior](#7-caching-behavior)
8. [Error Handling](#8-error-handling)

---

## 1. RBAC Endpoint Architecture

The RBAC system has three layers at runtime:

```
HTTP Request
  ↓
service.py endpoint (path_has or has)
  ↓
config.py: get_authority() → Authority instance (cached in Flask g)
  ↓
rbac.py: Authority.has_permission() → get_permissions() → get_role()
  ↓
rbac.py: SecretsStorage.load() → SecretManagerServiceClient
  ↓
GCP Secret Manager
```

Both endpoints share identical permission check logic -- they differ only in how they receive the `subject`, `target`, and `permission` parameters.

---

## 2. Path-Based Endpoint

**Route:** `GET /has/<subject>/<target>/<path:permission>`
**Source:** `service.py:68-103`

### Route Definition

```python
@service.route('/has/<subject>/<target>/<path:permission>')
def path_has(subject, target, permission):
```

**Flask URL converters:**
- `<subject>` -- standard string converter (matches a single path segment, no `/`)
- `<target>` -- standard string converter (single path segment)
- `<path:permission>` -- path converter (matches one or more segments, **allows `/` characters**)

This means:
- `GET /has/user@example.com/my-service/read` → subject=`user@example.com`, target=`my-service`, permission=`read`
- `GET /has/user@example.com/my-service/data/read` → subject=`user@example.com`, target=`my-service`, permission=`data/read`

The `<path:permission>` converter enables hierarchical permission strings like `data/read`, `admin/users/manage`, etc.

### Implementation

```python
try:
    logging.debug(f'Checking {subject} for {permission} on  {target}')
    if get_authority().has_permission(subject, target, permission):
        return '', 204
    else:
        return jsonify(StatusResponse(
            status=StatusCode.Error,
            message=f'{subject} does not have {permission} for {target}'
        )), 403
except Exception as ex:
    logging.exception(ex)
    logging.error(f'Exception while checking {subject} for {permission} on {target}: {ex}')
    return jsonify(StatusResponse(
        status=StatusCode.Error,
        message=f'Exception during processing request.'
    )), 500
```

**Response logic:**
- Permission granted: empty body, 204 No Content
- Permission denied: JSON error body, 403 Forbidden
- Exception: JSON error body, 500 Internal Server Error (generic message, details only in logs)

**Note:** The debug log has a double space (`on  {target}`) -- cosmetic typo in original code.

---

## 3. Query-Based Endpoint

**Route:** `GET /has`
**Source:** `service.py:105-149`

### Parameter Extraction

```python
subject = request.args.get('subject')
target = request.args.get('target')
permission = request.args.get('permission')

if subject is None:
    return jsonify(StatusResponse(
        status=StatusCode.Error,
        message='The status query parameter is missing'
    )), 400
if target is None:
    return jsonify(StatusResponse(
        status=StatusCode.Error,
        message='The target query parameter is missing'
    )), 400
if permission is None:
    return jsonify(StatusResponse(
        status=StatusCode.Error,
        message='The permission query parameter is missing'
    )), 400
```

**Known bug:** The error message for missing `subject` says `"The status query parameter is missing"` instead of `"The subject query parameter is missing"`. This should be fixed in a recreation.

After parameter validation, the permission check logic is identical to the path-based endpoint.

### Usage

```
GET /has?subject=user@example.com&target=my-service&permission=read
Authorization: Bearer <jwt>
```

Unlike the path-based endpoint, the permission string here cannot contain `/` characters unless URL-encoded (query parameters are single values).

---

## 4. Authority Per-Request Lifecycle

### Creation

```python
# config.py:39-42
def get_authority():
    if 'authority' not in g:
        g.authority = Authority(SecretsStorage(get_client(), get_project()))
    return g.authority
```

**Per-request creation chain:**

```
get_authority()
  → get_client()
      → get_credentials()
          → get_issuer() → ISSUER env var (file path)
          → service_account.Credentials.from_service_account_file(issuer)
      → secretmanager.SecretManagerServiceClient(credentials=credentials)
  → get_project() → SECRETS_PROJECT config/env var
  → SecretsStorage(sm_client, project)
  → Authority(storage)
  → cached in g.authority
```

**Objects created per request** (when RBAC is needed):
1. `service_account.Credentials` -- loaded from ISSUER key file
2. `SecretManagerServiceClient` -- new client with those credentials
3. `SecretsStorage` -- wraps the client
4. `Authority` -- wraps the storage, with empty caches

### Lifecycle Scope

| Object | Scope | Notes |
|---|---|---|
| `Authority` | Single request | Fresh caches each request |
| `SecretsStorage` | Single request | Created with Authority |
| `SecretManagerServiceClient` | Single request | New connection per request |
| `Credentials` | Single request | Key file re-read each request |
| `Authority._roles` cache | Single request | Populated during permission resolution |
| `Authority._permissions` cache | Single request | Populated during permission resolution |

### Within-Request Caching

If multiple permission checks happen in the same request (e.g., calling both `/has` endpoints, or a hypothetical batch check), the Authority's internal caches provide optimization:

- **First check for target "my-service":** Loads `ServiceGrants` from Secret Manager, loads all referenced `Role` objects, caches everything
- **Second check for same target, different subject:** Uses cached `ServiceGrants` and roles, no Secret Manager calls
- **Check for different target:** Loads that target's `ServiceGrants` (cache miss), but any shared roles may be cached

In practice, each HTTP request typically involves only a single permission check, so the within-request caching provides minimal benefit. The primary effect is that cross-request caching does NOT happen -- every request pays the full Secret Manager latency.

---

## 5. End-to-End Permission Check Trace

**Scenario:** Check if `worker@project.iam.gserviceaccount.com` has `execute` on `data-pipeline`.

```
1. HTTP Request
   GET /has/worker@project.iam.gserviceaccount.com/data-pipeline/execute
   Authorization: Bearer eyJhbG...

2. before_request handler
   → Path does not match skip list (/exchange, /refresh, /apidocs, /apispec)
   → jwt_authenticate(get_realm())
   → Verifies Bearer JWT, stores claims in request.environ['REMOTE_USER']
   → Returns None (success)

3. path_has() route handler
   → subject = "worker@project.iam.gserviceaccount.com"
   → target = "data-pipeline"
   → permission = "execute"

4. get_authority()
   → Creates Credentials from ISSUER file
   → Creates SecretManagerServiceClient
   → Creates SecretsStorage(client, "shipyard-auth-2022")
   → Creates Authority(storage)
   → Caches in g.authority

5. authority.has_permission("worker@...", "data-pipeline", "execute")
   → Calls get_permissions("data-pipeline", "worker@...")

6. authority.get_permissions("data-pipeline", "worker@...")
   → _permissions cache miss for "data-pipeline"
   → ServiceGrants.load(storage, "data-pipeline")

7. storage.load(ServiceGrants, "data-pipeline")
   → secret_id = "service-grants-data-pipeline"
   → secret_name = "projects/shipyard-auth-2022/secrets/service-grants-data-pipeline/versions/latest"
   → sm_client.access_secret_version(...)
   → Parses JSON payload
   → Returns ServiceGrants(service="data-pipeline", grants=[
       Grant(subject="worker@...", roles=["operator"]),
       Grant(subject="reader@...", roles=["viewer"])
     ])

8. For Grant(subject="worker@...", roles=["operator"]):
   → authority.get_role("operator")
   → _roles cache miss for "operator"
   → Role.load(storage, "operator")

9. storage.load(Role, "operator")
   → secret_id = "role-operator"
   → sm_client.access_secret_version(...)
   → Returns Role(name="operator", permissions=["execute", "status"])

10. Accumulate permissions:
    → permissions["worker@..."] = {"execute", "status"}

11. For Grant(subject="reader@...", roles=["viewer"]):
    → authority.get_role("viewer")
    → Role.load(storage, "viewer")
    → Returns Role(name="viewer", permissions=["read", "list"])
    → permissions["reader@..."] = {"read", "list"}

12. Cache: _permissions["data-pipeline"] = {
      "worker@...": {"execute", "status"},
      "reader@...": {"read", "list"}
    }

13. Return permissions.get("worker@...") → {"execute", "status"}

14. has_permission checks: "execute" in {"execute", "status"} → True

15. HTTP Response: 204 No Content (empty body)
```

### Secret Manager Calls for This Request

| Call # | Secret | Purpose |
|---|---|---|
| 1 | `service-grants-data-pipeline` | Load grants for target |
| 2 | `role-operator` | Load role for first grant's role |
| 3 | `role-viewer` | Load role for second grant's role |

Total: 3 Secret Manager API calls per request (for this configuration).

### General Call Count Formula

For a single permission check:
- 1 call to load `ServiceGrants` for the target
- N calls to load `Role` for each unique role name across all grants (not just the matching subject's roles -- all subjects' roles are resolved)
- Total: `1 + N` Secret Manager calls

---

## 6. RBAC Data Model in Secret Manager

### Role Secret

**Secret ID:** `role-{name}`

```json
{
  "kind": "Role",
  "name": "operator",
  "permissions": ["execute", "status", "monitor"]
}
```

| Field | Type | Description |
|---|---|---|
| `kind` | string | Always `"Role"` |
| `name` | string | Role identifier (matches secret suffix) |
| `permissions` | string[] | List of permission strings this role grants |

### ServiceGrants Secret

**Secret ID:** `service-grants-{service}`

```json
{
  "kind": "ServiceGrants",
  "service": "data-pipeline",
  "grants": [
    {
      "kind": "Grant",
      "subject": "worker@project.iam.gserviceaccount.com",
      "roles": ["operator"]
    },
    {
      "kind": "Grant",
      "subject": "reader@project.iam.gserviceaccount.com",
      "roles": ["viewer"]
    },
    {
      "kind": "Grant",
      "subject": "admin@shipyard.com",
      "roles": ["operator", "viewer"]
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `kind` | string | Always `"ServiceGrants"` |
| `service` | string | Target service identifier (matches secret suffix) |
| `grants` | Grant[] | List of subject-to-role mappings |
| `grants[].kind` | string | Always `"Grant"` |
| `grants[].subject` | string | Principal identifier (email) |
| `grants[].roles` | string[] | Role names granted to this subject |

### Relationship Diagram

```
Secret Manager
├── role-admin          → {"permissions": ["read", "write", "delete", "manage"]}
├── role-operator       → {"permissions": ["execute", "status", "monitor"]}
├── role-viewer         → {"permissions": ["read", "list"]}
├── service-grants-data-pipeline → {
│     "grants": [
│       {"subject": "worker@...", "roles": ["operator"]},
│       {"subject": "admin@...",  "roles": ["operator", "viewer"]}
│     ]
│   }
└── service-grants-api-gateway → {
      "grants": [
        {"subject": "frontend@...", "roles": ["viewer"]},
        {"subject": "admin@...",    "roles": ["admin"]}
      ]
    }
```

Roles are shared across services. A role like `viewer` can appear in grants for multiple services.

---

## 7. Caching Behavior

### No Cross-Request Cache

The Authority is created fresh per request (via Flask `g`). This means:

- **Consistency:** Changes to roles or grants in Secret Manager take effect on the next request
- **Latency:** Every request incurs Secret Manager API calls (typically 2-5 calls depending on grant/role count)
- **No stale data:** There is no TTL or cache invalidation concern

### Comparison with Key Cache

| Aspect | Authority (RBAC) | ServiceAccountKeyCache (JWT verification) |
|---|---|---|
| Scope | Per-request | Process-global singleton |
| Refresh | Every request | Every 300 seconds (default) |
| Persistence | Discarded after request | Lives for process lifetime |
| Rationale | Permissions may change frequently, need fresh reads | Public keys change rarely, expensive to fetch |

### Performance Implications

For a service handling 100 requests/second, each needing a permission check with 3 roles:
- 400 Secret Manager API calls/second (1 ServiceGrants + 3 Roles per request)
- Each call has ~50-100ms latency
- This adds 200-400ms to each request

A recreation should consider:
- TTL-based caching of roles and grants (e.g., 60 seconds)
- Application-scoped Authority with periodic refresh
- An in-memory cache with explicit invalidation

---

## 8. Error Handling

### Exception Handling Strategy

Both endpoints wrap the entire permission check in a `try/except Exception`:

```python
try:
    if get_authority().has_permission(subject, target, permission):
        return '', 204
    else:
        return ..., 403
except Exception as ex:
    logging.exception(ex)
    logging.error(f'Exception while checking ...: {ex}')
    return ..., 500
```

**Caught exceptions include:**
- Secret Manager connection errors
- Authentication failures (ISSUER not valid)
- JSON deserialization errors in secret payloads
- Any unexpected errors in the Authority/SecretsStorage chain

**Not caught by endpoints** (caught by `before_request`):
- JWT verification failures (handled by middleware, returns 401)

### Error Response Consistency

Both endpoints use `StatusResponse` from watchtower for error bodies:

```json
{"status": "Error", "message": "..."}
```

The 500 error always uses a generic message (`"Exception during processing request."`) rather than exposing internal details. Specific error information is only in the server logs.

### Missing Error Cases

The following scenarios produce 500 errors but could have dedicated handling:

| Scenario | Current Behavior | Better Handling |
|---|---|---|
| SECRETS_PROJECT not configured | 500 (NoneType error) | 503 with clear message |
| ISSUER not configured | 500 (Credentials error) | 503 with clear message |
| Secret Manager permissions denied | 500 (PermissionDenied) | 503 with configuration hint |
| Malformed JSON in secret | 500 (JSON/KeyError) | 500 with specific secret ID |
