# Client Library: Token Verification

**Source file**: `dockmaster/target.py`

This module provides the receiving side of JWT authentication: verifying incoming JWT tokens against cached public keys. It includes a key cache hierarchy for different deployment scenarios and a `ServiceRealm` class that ties verification and optional RBAC authorization together.

---

## Table of Contents

1. [KeyCache (Base Class)](#1-keycache-base-class)
2. [RemoteKeyCache](#2-remotekeycache)
3. [public_keys() Generator](#3-public_keys-generator)
4. [ServiceAccountKeyCache](#4-serviceaccountkeycache)
5. [ServiceRealm](#5-servicerealm)
6. [Dependencies](#6-dependencies)

---

## 1. `KeyCache` (Base Class)

**Signature:**
```python
class KeyCache:
    def __init__(self, expiry=300)
```

Base class for all key caches. Stores public keys in an in-memory dictionary with time-based expiry. Subclasses override `update()` to define how keys are refreshed.

### Constructor

| Parameter | Type | Default | Description |
|---|---|---|---|
| `expiry` | int | 300 | Cache lifetime in seconds before `update()` is triggered |

### Internal State

| Attribute | Type | Initial Value | Description |
|---|---|---|---|
| `_keys` | dict | `{}` | Maps key ID (`kid`) to key material (PEM string) |
| `expiry` | int | 300 | Cache lifetime in seconds |
| `updated_at` | int | 0 | Timestamp of last `update()` call. Starts at 0, so the first `__getitem__` call always triggers an update |

### Methods

#### `update()`
```python
def update(self):
    pass
```
Template method -- no-op in the base class. Subclasses override this to populate `self._keys`.

#### `keys` (property)
```python
@property
def keys(self) -> dict
```
Returns the full `_keys` dictionary. Used by `ServiceRealm.verify()` when no `kid` is present in the JWT header (falls back to trying all cached keys).

#### `__getitem__(kid)`
```python
def __getitem__(self, kid) -> str | None
```
Retrieves a key by ID. If the cache has expired (current time - `updated_at` >= `expiry`), calls `update()` first and resets `updated_at`. Returns `None` if the key ID is not found.

**Expiry check logic:**
```
if (time.time() - self.updated_at) >= self.expiry:
    self.update()
    self.updated_at = time.time()
return self._keys.get(kid)
```

Since `updated_at` starts at 0, the first access always triggers an update.

#### `__setitem__(kid, key)`
```python
def __setitem__(self, kid, key)
```
Directly sets a key in the cache. Does not affect `updated_at`.

---

## 2. `RemoteKeyCache`

**Signature:**
```python
class RemoteKeyCache(KeyCache):
    def __init__(self, service, user, expiry=300)
```

Fetches individual public keys on-demand from the dockmaster service's `/key/{kid}` endpoint. Keys are cached locally once fetched. This is used when a service verifies JWTs but doesn't have direct access to GCP IAM -- it delegates key fetching to the dockmaster service.

### Constructor

| Parameter | Type | Required | Description |
|---|---|---|---|
| `service` | str | Yes | Base URL of the dockmaster service (trailing `/` is stripped) |
| `user` | ServiceUser | Yes | ServiceUser instance for authenticating requests to the dockmaster service |
| `expiry` | int | No | Cache lifetime in seconds (default 300). Controls when `update()` clears the cache |

**Raises:** `ValueError` if `service` is None.

### Overridden Methods

#### `update()`
```python
def update(self):
    self._keys = {}
```
Clears the entire local key cache. After `update()`, subsequent `__getitem__` calls will re-fetch keys from the remote service.

#### `__getitem__(kid)`
```python
def __getitem__(self, kid) -> str | None
```

**Overrides the base class entirely** -- does NOT call `super().__getitem__()` and does NOT check expiry. Instead:

1. Checks if `kid` exists in local `_keys` dict
2. If not found, fetches from `{service}/key/{kid}` with Bearer auth header
3. On HTTP 200, caches the response text (PEM key) and returns it
4. On any other status, returns `None` (key not found)

**Important behavioral difference from base class:**
- The base class `__getitem__` checks cache expiry and triggers `update()`. The `RemoteKeyCache` override does neither -- it never expires individual keys and never calls `update()` from `__getitem__`.
- The `update()` method (which clears the cache) is only triggered externally, not by key lookups.
- In practice, the expiry-based `update()` mechanism from the base class is **not used** by `RemoteKeyCache` since `__getitem__` is fully overridden.

### Usage

```python
from dockmaster import ServiceUser, RemoteKeyCache, ServiceRealm

user = ServiceUser('/path/to/key.json')
cache = RemoteKeyCache('https://dockmaster.service.example.net', user)
realm = ServiceRealm(cache)

# When realm.verify() looks up a kid, RemoteKeyCache fetches it from the service
claims = realm.verify(jwt_token)
```

---

## 3. `public_keys()` Generator

**Signature:**
```python
def public_keys(credentials=None, project=None) -> Generator[tuple[str, str, str], None, None]
```

Generator function that yields all user-managed public keys for all service accounts in a GCP project. This is the mechanism by which `ServiceAccountKeyCache` populates itself with verification keys.

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `credentials` | str, dict, or None | None | Service account credentials -- file path, parsed dict, or None for default credentials |
| `project` | str | None | GCP project ID. If credentials is a dict, `project_id` is extracted from it |

### Yields

`tuple[str, str, str]` -- `(email, kid, pem_key)` for each user-managed key:

| Element | Description |
|---|---|
| `email` | Service account email (e.g., `my-sa@project.iam.gserviceaccount.com`) |
| `kid` | Key ID (the last segment of the key resource name) |
| `pem_key` | X.509 PEM-formatted public key (base64-decoded from the API response) |

### Implementation Details

1. **Credential resolution:**
   - `None`: uses default credentials (Application Default Credentials)
   - `dict`: calls `service_account.Credentials.from_service_account_info()` with `cloud-platform` scope; extracts `project_id`
   - `str`: calls `service_account.Credentials.from_service_account_file()` with `cloud-platform` scope

2. **Service account enumeration:**
   - Builds IAM v1 API client: `googleapiclient.discovery.build('iam', 'v1', credentials=service_creds)`
   - Lists service accounts: `projects.serviceAccounts.list(name='projects/{project}', pageSize=50)`
   - Handles pagination via `list_next()` -- iterates all pages

3. **Key enumeration per account:**
   - Lists user-managed keys: `projects.serviceAccounts.keys.list(name='.../{email}', keyTypes='USER_MANAGED')`
   - For each key, fetches the public key in X.509 PEM format: `keys.get(name=key_name, publicKeyType='TYPE_X509_PEM_FILE')`
   - Extracts `kid` from the key resource name (everything after the last `/`)
   - Base64-decodes `publicKeyData` from the response

### Key Resource Name Format

```
projects/{project}/serviceAccounts/{email}/keys/{kid}
```

The `kid` is extracted via:
```python
rest, _, kid = key.get('name').rpartition('/')
```

### GCP API Calls Made

| API | Method | Purpose |
|---|---|---|
| IAM v1 | `projects.serviceAccounts.list` | Enumerate all service accounts in project |
| IAM v1 | `projects.serviceAccounts.keys.list` | List user-managed keys per service account |
| IAM v1 | `projects.serviceAccounts.keys.get` | Fetch public key data in PEM format |

---

## 4. `ServiceAccountKeyCache`

**Signature:**
```python
class ServiceAccountKeyCache(KeyCache):
    def __init__(self, credentials=None, project=None, expiry=300, load_google_keys=True)
```

The primary key cache for production use. Loads public keys from two sources:
1. All user-managed service account keys in a GCP project (via `public_keys()`)
2. Google's OAuth2 public OIDC signing keys (from `googleapis.com/oauth2/v1/certs`)

### Constructor

| Parameter | Type | Default | Description |
|---|---|---|---|
| `credentials` | str or dict | None | Service account credentials (file path or parsed dict). If str, the file is loaded and parsed |
| `project` | str | None | GCP project ID. Defaults to `project_id` from credentials |
| `expiry` | int | 300 | Cache refresh interval in seconds |
| `load_google_keys` | bool | True | Whether to load Google's public OIDC certs |

**Note:** The constructor always sets `self._load_google_keys = True` regardless of the `load_google_keys` parameter value. This appears to be a bug -- the parameter is accepted but ignored.

### `update(retry=True)`

```python
def update(self, retry=True)
```

Refreshes the entire key cache by fetching keys from all sources.

**Flow:**

1. Creates a new empty dict `new_keys`
2. If `_load_google_keys` is True:
   - Fetches `https://www.googleapis.com/oauth2/v1/certs` (no retry session -- uses plain `requests.get()`)
   - Parses JSON response as `{kid: pem_cert}` pairs
   - Adds all to `new_keys`
   - Exceptions are caught, logged, and swallowed (non-fatal)
3. Iterates `public_keys(credentials, project)`:
   - For each `(email, kid, key)`, adds `kid: key` to `new_keys`
4. Atomically replaces `self._keys` with `new_keys`

**Error handling:**
- `RefreshError` (from `google.auth`): logged, then retried once if `retry=True`
- The retry call passes `retry=False` to prevent infinite recursion
- Note: the error log calls use `logging.error(..., file=sys.stderr)` which is incorrect -- `logging.error` doesn't accept a `file` parameter. The `file=sys.stderr` is silently ignored.
- Google key fetch failures are non-fatal (caught and logged independently)

**Atomicity:** The key replacement `self._keys = new_keys` is a single reference assignment, so readers will always see either the old or new complete dict, never a partial update.

### Usage

```python
from dockmaster import ServiceAccountKeyCache, ServiceRealm

cache = ServiceAccountKeyCache(
    credentials='/path/to/service-account-key.json',
    project='my-project',
    expiry=300,
    load_google_keys=True
)

realm = ServiceRealm(cache)
claims = realm.verify(jwt_token)
```

### Cache Lifecycle

```
Time 0:        KeyCache.__getitem__() called
               → (time.time() - 0) >= 300 → True
               → update() called
               → Keys fetched from GCP IAM + Google certs
               → updated_at = time.time()
               → Key returned

Time 0-300:    Keys served from memory
               → No API calls

Time 300+:     Next __getitem__() call
               → (time.time() - updated_at) >= 300 → True
               → update() called again
               → Full refresh from GCP IAM + Google certs
```

---

## 5. `ServiceRealm`

**Signature:**
```python
class ServiceRealm:
    def __init__(self, key_cache, authority=None)
```

The central JWT verification class. Verifies incoming JWT tokens against cached public keys and optionally delegates RBAC permission checks to an `Authority` instance.

### Constructor

| Parameter | Type | Required | Description |
|---|---|---|---|
| `key_cache` | KeyCache | Yes | Any KeyCache subclass for public key lookup |
| `authority` | Authority | No | Optional RBAC Authority for permission checks |

**Raises:** `ValueError` if `key_cache` is None.

**Note:** The docstring on the constructor references parameters (`credentials`, `audience`, `project`, `load_json`) that don't exist -- it appears to be a leftover from an earlier version of the class.

### `key_cache` (property)

```python
@property
def key_cache(self) -> KeyCache
```
Read-only access to the underlying key cache. Used by the service's `/key/{kid}` endpoint to serve public keys.

### `verify()`

**Signature:**
```python
def verify(self, jwt_value, audience=None) -> dict
```

Verifies a JWT token and returns its decoded claims.

#### Parameters

| Parameter | Type | Description |
|---|---|---|
| `jwt_value` | str | The JWT token string to verify |
| `audience` | str | Expected audience claim (optional). Passed to `google.auth.jwt.decode()` |

#### Return Value

`dict` -- The decoded JWT claims (payload). Contains fields like `iss`, `sub`, `email`, `aud`, `iat`, `exp`, plus any custom claims.

#### Verification Steps

1. **Structural validation:**
   - Splits token on `.` -- must have exactly 3 parts (header.payload.signature)
   - Raises `ValueError('Not a JWT value')` if not 3 parts

2. **Header decoding:**
   - Fixes base64 padding on the header (adds `=` padding if `len % 4 != 0`)
   - Base64-decodes the header
   - Parses as JSON
   - Raises `ValueError('Invalid base64 value')` on base64 decode failure
   - Raises `ValueError('Invalid JSON header in JWT')` on JSON parse failure

3. **Key lookup:**
   - Extracts `kid` from the decoded header
   - **If `kid` is present:** looks up the specific key via `self._key_cache[kid]`
     - If key is None (not found): raises `ValueError(f'Unknown key {kid}')`
     - The `certs` variable is set to the single key value (a PEM string)
   - **If `kid` is absent:** uses `self._key_cache.keys` (the full dict of all cached keys)
     - The `certs` variable is set to the entire `{kid: pem}` dict

4. **Signature verification:**
   - Calls `google.auth.jwt.decode(jwt_value, certs=certs, audience=audience)`
   - This verifies the RSA-SHA256 signature, checks expiry (`exp`), and validates audience if provided
   - On success, returns the decoded claims dict
   - On failure, `google.auth.jwt.decode()` raises exceptions (which propagate to the caller)

#### Important Detail: `certs` Parameter Shape

The `google.auth.jwt.decode()` function accepts `certs` as either:
- A `dict` of `{kid: key}` pairs (tries each key until one works)
- A single key string/cert

When `kid` is present in the JWT header, `ServiceRealm` passes the single key value directly (not wrapped in a dict). When `kid` is absent, it passes the full dict. Both formats are accepted by `google.auth.jwt.decode()`.

### `has_permission()`

**Signature:**
```python
def has_permission(self, subject, target, permission) -> bool
```

Delegates to the Authority instance if one was provided at construction.

| Parameter | Type | Description |
|---|---|---|
| `subject` | str | The principal to check |
| `target` | str | The service/resource identifier |
| `permission` | str | The permission string |

**Returns:**
- If no authority configured: always returns `False`
- Otherwise: returns `self._authority.has_permission(subject, target, permission)`

### Usage

```python
from dockmaster import ServiceAccountKeyCache, ServiceRealm, Authority, SecretsStorage

# Basic verification (no RBAC)
cache = ServiceAccountKeyCache(credentials='key.json', project='my-project')
realm = ServiceRealm(cache)

try:
    claims = realm.verify(jwt_token)
    print(f"Authenticated as: {claims['email']}")
except ValueError as e:
    print(f"JWT verification failed: {e}")

# With RBAC
authority = Authority(SecretsStorage(sm_client, 'my-project'))
realm = ServiceRealm(cache, authority=authority)

claims = realm.verify(jwt_token)
if realm.has_permission(claims['email'], 'my-service', 'read'):
    # authorized
    pass
```

---

## 6. Dependencies

### Direct Imports

| Import | Package | Purpose |
|---|---|---|
| `sys` | stdlib | Referenced in error logging (though incorrectly as `file=sys.stderr`) |
| `base64` | stdlib | Decode JWT header, decode public key data from GCP API |
| `binascii` | stdlib | Catch `binascii.Error` on base64 decode failure |
| `json` | stdlib | Parse JWT header JSON, parse credentials file |
| `time` | stdlib | Cache expiry timestamp tracking |
| `traceback` | stdlib | Imported but not used |
| `logging` | stdlib | Log cache update events and errors |
| `google.auth.jwt` | `google-auth` | `jwt.decode()` for JWT verification |
| `google.auth.exceptions.RefreshError` | `google-auth` | Catch credential refresh failures |
| `google.oauth2.service_account` | `google-auth` | Create credentials for IAM API access |
| `googleapiclient.discovery` | `google-api-python-client` | Build IAM v1 API client |
| `requests` | `requests` | Fetch Google OIDC certs |
| `.client.requests_retry_session` | dockmaster | HTTP client with retry (used by RemoteKeyCache) |

### Key Dependency: `google.auth.jwt.decode()`

This is the core verification function. It:
- Decodes the JWT header and payload
- Verifies the RSA-SHA256 signature against the provided certificate(s)
- Validates standard claims: `exp` (not expired), `iat` (not in future)
- Optionally validates `audience` if provided
- Returns the decoded claims dict on success
- Raises on any verification failure

### Key Dependency: Google IAM v1 API

Used by `public_keys()` to enumerate service accounts and their keys. Requires:
- Service account credentials with `cloud-platform` scope
- IAM API enabled on the GCP project
- `iam.serviceAccounts.list` and `iam.serviceAccountKeys.list`/`get` permissions

### Google OIDC Certs Endpoint

`https://www.googleapis.com/oauth2/v1/certs` returns a JSON object mapping key IDs to X.509 PEM certificates. These are Google's public signing keys for OIDC tokens (used when verifying Google-issued JWTs like those from Google Sign-In).
