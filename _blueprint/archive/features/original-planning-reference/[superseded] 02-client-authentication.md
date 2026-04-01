# Client Library: Authentication

**Source file**: `dockmaster/client.py`

This module provides the core authentication primitives for dockmaster: JWT token generation from GCP service account credentials, a remote RBAC client, Google access token validation, and an HTTP client with retry logic.

---

## Table of Contents

1. [requests_retry_session()](#1-requests_retry_session)
2. [ServiceUser](#2-serviceuser)
3. [AuthorityClient](#3-authorityclient)
4. [check_access_token()](#4-check_access_token)
5. [Dependencies](#5-dependencies)

---

## 1. `requests_retry_session()`

**Signature:**
```python
def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
    session=None
) -> requests.Session
```

Creates a `requests.Session` configured with automatic retry on transient failures. This is used throughout the codebase as the standard HTTP client factory.

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `retries` | int | 3 | Number of retry attempts for `total`, `read`, and `connect` retries |
| `backoff_factor` | float | 0.3 | Multiplier for exponential backoff between retries. Delay = `backoff_factor * (2 ** (retry_number - 1))` |
| `status_forcelist` | tuple[int] | (500, 502, 504) | HTTP status codes that trigger a retry |
| `session` | requests.Session | None | Optional existing session to configure. If None, a new session is created |

### Implementation Details

- Uses `urllib3.util.retry.Retry` for retry configuration
- Mounts the retry adapter on both `http://` and `https://` schemes via `HTTPAdapter`
- The retry applies to connect errors, read errors, and responses with status codes in `status_forcelist`

### Return Value

A configured `requests.Session` instance with retry logic mounted.

### Usage Pattern

```python
# Default retry session
session = requests_retry_session()
response = session.get('https://api.example.com/resource', timeout=(5, 30))

# Custom retry configuration
session = requests_retry_session(retries=5, backoff_factor=0.5, status_forcelist=(500, 502, 503, 504))
```

### Where Used

- `AuthorityClient.has_permission()` -- permission check HTTP calls
- `check_access_token()` -- Google tokeninfo validation
- `RemoteKeyCache.__getitem__()` (in `target.py`) -- fetching public keys from dockmaster service
- `ServiceAccountKeyCache.update()` (in `target.py`) -- fetching Google OIDC certs
- `exchange_code()` (in `flask_integration.py`) -- OAuth2 code exchange
- Service endpoints (in `service.py`) -- refresh token flow, userinfo calls

---

## 2. `ServiceUser`

**Signature:**
```python
class ServiceUser:
    def __init__(self, credentials, email=None)
```

The primary class for generating signed JWT tokens using GCP service account credentials. Used by services that need to authenticate to other services (service-to-service auth) or to the dockmaster service itself.

### Constructor

| Parameter | Type | Required | Description |
|---|---|---|---|
| `credentials` | str or dict | Yes | Either a file path to a JSON service account key file, or a dict of the parsed credentials |
| `email` | str | No | Override for the client principal email. Defaults to `client_email` from credentials |

**Behavior:**
1. If `credentials` is a string, it is treated as a file path -- the file is opened and parsed as JSON
2. The parsed dict is stored as `self.credentials`
3. `email` is resolved in order: explicit `email` parameter -> `credentials['client_email']` -> `ValueError`

**Raises:** `ValueError` if email cannot be determined from either the parameter or the credentials.

### `get_token()`

**Signature:**
```python
def get_token(
    self,
    subject=None,
    service_name=None,
    expiry=3600,
    payload={}
) -> bytes
```

Generates a signed JWT token.

#### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `subject` | str | None | JWT `sub` and `email` claims. If None, defaults to `self.email` (the service account email) |
| `service_name` | str | None | Sets the JWT `aud` (audience) claim. Typically the target service URL. Omitted from claims if None |
| `expiry` | int | 3600 | Token lifetime in seconds from current time |
| `payload` | dict | {} | Additional claims to include in the JWT. **Warning: this dict is mutated in-place** |

#### JWT Claims Produced

| Claim | Value | Description |
|---|---|---|
| `iat` | `int(time.time())` | Issued-at timestamp (seconds since epoch) |
| `exp` | `iat + expiry` | Expiration timestamp |
| `iss` | `self.email` | Issuer -- always the service account email |
| `sub` | `subject` or `self.email` | Subject -- the principal the token represents |
| `email` | `subject` or `self.email` | Email claim -- same as `sub` |
| `aud` | `service_name` | Audience -- only set if `service_name` is not None |

Plus any additional claims passed via `payload`.

#### Signing Mechanism

1. Creates an `RSASigner` from the service account credentials:
   - If credentials is a dict: `google.auth.crypt.RSASigner.from_service_account_info(credentials)`
   - Otherwise: `google.auth.crypt.RSASigner.from_service_account_file(credentials)`
2. Signs the JWT using `google.auth.jwt.encode(signer, payload)`
3. The signer extracts the private key from the credentials and the `private_key_id` is set as the JWT header `kid`

#### Return Value

`bytes` -- The encoded JWT token. Call `.decode('utf-8')` to get a string.

#### Important Behavior: Mutable Default Argument

The `payload={}` default is a **mutable default argument**. This means:
- The same dict object is reused across calls if no explicit payload is provided
- Since `get_token()` mutates the payload in-place (setting `iat`, `exp`, `iss`, `sub`, `email`, `aud`), calling `get_token()` multiple times without passing a payload will accumulate claims in the shared dict
- In practice this works because the standard claims are overwritten each call, but any custom claims from a previous call would persist
- A recreated implementation should use `payload=None` with `payload = payload or {}` inside the method

### `get_authorization()`

**Signature:**
```python
def get_authorization(
    self,
    subject=None,
    service_name=None,
    expiry=3600,
    payload={}
) -> str
```

Convenience wrapper around `get_token()` that returns a formatted Bearer token header value.

#### Return Value

`str` -- `"Bearer <jwt_token_string>"`

#### Usage

```python
user = ServiceUser('/path/to/service-account-key.json')

# Generate Authorization header
auth_header = user.get_authorization(
    subject='user@example.com',
    service_name='https://my-service.example.com/'
)
# auth_header = "Bearer eyJhbG..."

# Use in HTTP request
response = requests.get(
    'https://my-service.example.com/api/resource',
    headers={'Authorization': auth_header}
)
```

### Full Usage Example

```python
from dockmaster import ServiceUser

# From file path
user = ServiceUser('/path/to/service-account-key.json')

# From dict (e.g., loaded from environment or secret manager)
import json
creds = json.loads(os.environ['SERVICE_ACCOUNT_KEY'])
user = ServiceUser(creds)

# With explicit email override
user = ServiceUser(creds, email='custom@example.com')

# Generate token for service-to-service auth
token = user.get_token(
    subject='target-user@example.com',
    service_name='https://target-service/',
    expiry=1800,  # 30 minutes
    payload={'custom_claim': 'value'}
)

# Generate Authorization header
auth = user.get_authorization(service_name='https://target-service/')
```

---

## 3. `AuthorityClient`

**Signature:**
```python
class AuthorityClient:
    def __init__(self, service, user)
```

HTTP client for checking RBAC permissions against the dockmaster service's `/has` endpoint. This is the client-side counterpart to the service's permission check endpoints.

### Constructor

| Parameter | Type | Description |
|---|---|---|
| `service` | str | Base URL of the dockmaster service (trailing `/` is stripped) |
| `user` | ServiceUser | ServiceUser instance used to generate Bearer tokens for authentication |

### `has_permission()`

**Signature:**
```python
def has_permission(self, subject, target, permission) -> bool
```

Checks whether a subject has a specific permission on a target by calling the dockmaster service.

#### Parameters

| Parameter | Type | Description |
|---|---|---|
| `subject` | str | The principal to check (e.g., service account email) |
| `target` | str | The service/resource identifier |
| `permission` | str | The permission string to check |

#### Implementation

1. Creates a new retry session via `requests_retry_session()`
2. Makes a GET request to `{service}/has/{subject}/{target}/{permission}`
3. Includes `Authorization: Bearer <jwt>` header from `self._user.get_authorization()`
4. Timeout: 5 seconds connect, 30 seconds read
5. Returns `True` if status code is 2xx (200-299), `False` otherwise

#### Usage

```python
user = ServiceUser('/path/to/key.json')
client = AuthorityClient('https://dockmaster.service.example.net', user)

if client.has_permission('worker@project.iam.gserviceaccount.com', 'data-pipeline', 'execute'):
    # proceed with operation
    pass
```

#### Design Notes

- A new `requests_retry_session()` is created on every call (no session reuse)
- The ServiceUser generates a fresh JWT on every call via `get_authorization()`
- No caching of permission results -- every call hits the network
- The permission path parameter supports `/` in the permission string (uses Flask's `<path:permission>` converter on the server side)

---

## 4. `check_access_token()`

**Signature:**
```python
def check_access_token(
    endpoint,
    token,
    audiences,
    headers=None
) -> tuple[bool, str, dict | None]
```

Validates a Google OAuth2 access token by calling a token info endpoint (typically Google's tokeninfo API). Used by the service's `/exchange` endpoint as a fallback when the incoming token is not a JWT.

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `endpoint` | str | Token info URL (e.g., `https://www.googleapis.com/oauth2/v1/tokeninfo`) |
| `token` | str | The access token to validate |
| `audiences` | list[str] or set[str] | Collection of allowed audience values |
| `headers` | dict | Optional HTTP headers to include in the request |

### Return Value

A 3-tuple `(valid, message, info)`:

| Element | Type | Description |
|---|---|---|
| `valid` | bool | Whether the token is valid and has an allowed audience |
| `message` | str | Human-readable status message |
| `info` | dict or None | The parsed tokeninfo response (None if HTTP call failed) |

### Validation Logic

1. Makes GET request to `{endpoint}?access_token={token}` with 5s connect / 30s read timeout
2. If response is not 2xx: returns `(False, "Invalid token, status {code}", None)`
3. If response is 2xx, parses JSON:
   - If no `audience` field in response: returns `(False, "No audience was provided", info)`
   - If `audience` is in the allowed `audiences`: returns `(True, "Audience {aud} allowed", info)`
   - Otherwise: returns `(False, "Audience {aud} is not allowed", info)`

### Usage in the Service

```python
# In service.py /exchange endpoint
valid, message, info = check_access_token(
    get_access_token_endpoint(),       # https://www.googleapis.com/oauth2/v1/tokeninfo
    token,                              # the bearer token from the request
    get_authorized_audience()           # set of allowed client IDs
)
if not valid:
    return jsonify({'error': message}), 401
# info contains the token claims (email, audience, scope, etc.)
```

### Important Details

- The `info` dict returned on success contains Google-specific fields like `audience`, `email`, `email_verified`, `scope`, `expires_in`, `access_type`
- The function checks `audience` (singular) from the tokeninfo response against the `audiences` collection using `in` operator
- A new retry session is created per call (no session reuse)

---

## 5. Dependencies

### Direct Imports

| Import | Package | Purpose |
|---|---|---|
| `time` | stdlib | Current timestamp for JWT `iat`/`exp` claims |
| `json` | stdlib | Parse service account JSON key file |
| `google.auth.crypt` | `google-auth` | `RSASigner` for JWT signing with RSA private keys |
| `google.auth.jwt` | `google-auth` | `encode()` for JWT creation |
| `requests` | `requests` | HTTP client |
| `requests.adapters.HTTPAdapter` | `requests` | Mount retry adapter on session |
| `requests.packages.urllib3.util.retry.Retry` | `urllib3` (via requests) | Retry configuration |

### Key Dependency: `google-auth`

The `google.auth.crypt.RSASigner` and `google.auth.jwt.encode()` functions are the core signing mechanism:

- `RSASigner.from_service_account_info(info_dict)` -- extracts `private_key` and `private_key_id` from a credentials dict
- `RSASigner.from_service_account_file(filename)` -- loads from a JSON file directly
- `google.auth.jwt.encode(signer, payload)` -- creates a JWT with:
  - Header: `{"alg": "RS256", "typ": "JWT", "kid": "<private_key_id>"}`
  - Payload: the provided claims dict
  - Signature: RSA-SHA256 using the private key

### Service Account Key File Format

The credentials JSON file (or dict) is expected to be a standard GCP service account key with at minimum:

```json
{
  "type": "service_account",
  "project_id": "my-project",
  "private_key_id": "key-id-used-as-jwt-kid",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n",
  "client_email": "my-sa@my-project.iam.gserviceaccount.com",
  "client_id": "123456789",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

Key fields used by `ServiceUser`:
- `client_email` -- used as default `self.email` (JWT issuer)
- `private_key` + `private_key_id` -- used by `RSASigner` for signing (the `kid` in JWT header comes from `private_key_id`)
