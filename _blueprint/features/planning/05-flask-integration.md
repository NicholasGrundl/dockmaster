# Client Library: Flask Integration

**Source files**: `dockmaster/flask_integration.py`, `dockmaster/sessions.py`

These modules provide Flask-specific functionality: JWT Bearer token authentication middleware, a complete Google OAuth2 SSO login flow via a Flask Blueprint, session management helpers, and a Redis-backed server-side session interface.

---

## Table of Contents

1. [JWT Authentication Middleware](#1-jwt-authentication-middleware)
2. [OAuth2 Configuration](#2-oauth2-configuration)
3. [OAuth2 Helper Functions](#3-oauth2-helper-functions)
4. [Auth Blueprint Routes](#4-auth-blueprint-routes)
5. [Session Management Helpers](#5-session-management-helpers)
6. [RedisSessionInterface](#6-redissessioninterface)
7. [Dependencies](#7-dependencies)

---

## 1. JWT Authentication Middleware

These functions are used by the dockmaster service for API endpoint authentication (not browser-based login).

### `get_bearer_token()`

```python
def get_bearer_token() -> str | None
```

Extracts the Bearer token from the current Flask request's `Authorization` header.

**Logic:**
1. Reads `request.headers.get('Authorization')`
2. If missing: returns `None`
3. Splits on first space: `kind, _, value = auth.partition(' ')`
4. If `kind != 'Bearer'`: returns `None`
5. Strips whitespace from value
6. If empty after strip: returns `None`
7. Returns the token string

### `jwt_authenticate(realm)`

```python
def jwt_authenticate(realm: ServiceRealm) -> tuple | None
```

Flask `before_request` handler for JWT Bearer token verification. Verifies the token against a `ServiceRealm` and stores the decoded claims for downstream handlers.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `realm` | ServiceRealm | The verification realm with key cache |

**Flow:**
1. Calls `get_bearer_token()`
2. If no token: returns `(jsonify({'error': 'Not authenticated'}), 401)`
3. Calls `realm.verify(token)`
4. On success: sets `request.environ['REMOTE_USER'] = claims`, returns `None` (Flask proceeds to route handler)
5. On `ValueError`: logs error, returns `(jsonify({'error': 'Not authenticated'}), 401)`

**How claims are accessed downstream:**
```python
# In a route handler
claims = request.environ['REMOTE_USER']
email = claims.get('email')
```

**Usage in service:**
```python
@service.before_request
def before_request():
    if request.path.startswith('/exchange'):
        return  # skip JWT auth
    # ... other skips ...
    return jwt_authenticate(get_realm())
```

---

## 2. OAuth2 Configuration

The OAuth2 login flow reads configuration from Flask `app.config` and environment variables. The `get_config()` helper (local to this module, separate from the service's `get_config`) checks Flask config first, then environment variables.

```python
def get_config(name, default):
    return current_app.config.get(name, os.environ.get(name, default))
```

**Note:** This lookup order is Flask config -> env var -> default. This is the **opposite** order from the service's `config.py` which checks env var -> Flask config -> default.

### Required Configuration

| Key | Source | Description |
|---|---|---|
| `CLIENT_ID` | `app.config` | Google OAuth2 client ID |
| `AUTH_PROVIDER` | `app.config` | Google authorization endpoint (e.g., `https://accounts.google.com/o/oauth2/auth`) |
| `TOKEN_PROVIDER` | `app.config` | Google token exchange endpoint (e.g., `https://oauth2.googleapis.com/token`) |

### Optional Configuration

| Key | Source | Default | Description |
|---|---|---|---|
| `CLIENT_SECRET` | `app.config` or env var | None | OAuth2 client secret |
| `HOST_URL` | `app.config` or env var | `request.host_url` | Application base URL |
| `REDIRECT_URI` | `app.config` or env var | `{HOST_URL}{AUTH_PREFIX}` | OAuth2 redirect base URI |
| `REDIRECT_PREFIX` | `app.config` or env var | `''` | Additional path segment before `authenticated` |
| `AUTH_PREFIX` | `app.config` | `'auth/'` | URL prefix for auth endpoints |
| `APP_ROOT` | `app.config` | `'/'` | Application root path for redirects |
| `PREFIX` | `app.config` | `''` | URL prefix prepended to redirect paths after login |
| `AUTHORIZED` | `app.config` | *(not set)* | List of allowed email addresses (whitelist). If not set, all authenticated users are allowed |
| `EXPIRY` | `app.config` | *(not set)* | Session token lifetime in seconds |
| `DOCKMASTER_EXPIRY` | env var | *(not set)* | Fallback for EXPIRY (env var only) |
| `NOAUTH` | `app.config` | `[]` | List of exact paths that skip authentication |
| `NOAUTH_PREFIXES` | `app.config` | `[]` | List of path prefixes that skip authentication |

### Expiry Resolution Order

1. `EXPIRY` in `app.config` -> use that value
2. `DOCKMASTER_EXPIRY` in environment -> use that value
3. Neither set -> use `expires_in` from the Google token response

---

## 3. OAuth2 Helper Functions

### `host_url()`

```python
def host_url() -> str
```
Returns `HOST_URL` config or falls back to `request.host_url` (the current request's scheme + host).

### `redirect_uri()`

```python
def redirect_uri() -> str
```
Constructs the full OAuth2 callback URL.

**Formula:**
```
{REDIRECT_URI or (host_url() + AUTH_PREFIX)} + {REDIRECT_PREFIX} + "authenticated"
```

**Example:** `https://app.example.com/console/auth/authenticated`

### `set_state()`

```python
def set_state() -> str
```
Generates a UUID4 string, stores it in `session['state']`, and returns it. Used for CSRF protection -- the state is verified when Google redirects back.

### `set_nonce()`

```python
def set_nonce() -> str
```
Generates a UUID4 string and returns it. **Does NOT store it in the session** -- the nonce is sent to Google but never verified on callback. This is an incomplete OIDC nonce implementation.

### `auth_uri()`

```python
def auth_uri() -> str
```

Builds the full Google OAuth2 authorization URL.

**Side effects:**
1. Calls `set_state()` -- stores CSRF state in session
2. Stores original request path in `session['state.path']`
3. Pickles and stores original request args in `session['state.args']`

**If the original path is the login page itself** (`{AUTH_PREFIX}/login`), the return path is set to `APP_ROOT` instead.

**Constructed URL:**
```
{AUTH_PROVIDER}?
  client_id={CLIENT_ID}
  &prompt=select_account
  &response_type=code
  &scope=openid%20email%20profile
  &redirect_uri={redirect_uri()}
  &state={state}
  &nonce={nonce}
```

**OAuth2 parameters:**

| Parameter | Value | Purpose |
|---|---|---|
| `client_id` | from config | Identifies the application |
| `prompt` | `select_account` | Forces Google account chooser on every login |
| `response_type` | `code` | Authorization code flow |
| `scope` | `openid email profile` | Requests OIDC identity, email, and profile |
| `redirect_uri` | computed | Where Google redirects after auth |
| `state` | UUID4 | CSRF protection token |
| `nonce` | UUID4 | OIDC replay protection (not verified) |

### `exchange_code(code)`

```python
def exchange_code(code) -> dict
```

Exchanges an authorization code for tokens by POSTing to the token endpoint.

**POST body (form-encoded):**

| Field | Value |
|---|---|
| `code` | The authorization code from Google's redirect |
| `client_id` | From `app.config['CLIENT_ID']` |
| `client_secret` | From `get_client_secret()` |
| `redirect_uri` | From `redirect_uri()` |
| `grant_type` | `authorization_code` |

**On success (200):** Returns parsed JSON response containing:
```json
{
  "access_token": "ya29...",
  "id_token": "eyJ...",
  "expires_in": 3600,
  "token_type": "Bearer",
  "scope": "openid email profile",
  "refresh_token": "1//0g..."
}
```

**On failure:** Prints error to stderr and calls `abort(401)`.

**Uses** `requests_retry_session()` with 5s connect / 30s read timeout.

### `get_principal(token)`

```python
def get_principal(token) -> tuple[str, dict]
```

Decodes a JWT token's payload to extract the user's email and full claims. **Does NOT verify the signature** -- this is a simple base64 decode of the payload segment.

**Logic:**
1. Splits token on `.`
2. Base64-decodes the second segment (payload) with padding fix
3. Parses as JSON

**Returns:** `(email_string, claims_dict)`

The `claims_dict` typically contains:
```json
{
  "iss": "https://accounts.google.com",
  "sub": "1234567890",
  "email": "user@example.com",
  "name": "Jane Doe",
  "picture": "https://...",
  "given_name": "Jane",
  "family_name": "Doe",
  "locale": "en",
  "iat": 1234567890,
  "exp": 1234571490
}
```

### `logout_principal()`

```python
def logout_principal()
```

Clears the entire Flask session via `session.clear()`.

---

## 4. Auth Blueprint Routes

```python
auth_endpoint = Blueprint('auth', __name__, url_prefix='/auth')
```

The blueprint is registered by consuming applications with a chosen prefix:
```python
# Example (currently commented out in the service):
# service.register_blueprint(auth_endpoint, url_prefix='/console/auth')
```

### `GET /auth/authenticated` -- OAuth2 Callback

The OAuth2 redirect callback. This is where Google sends the user after authentication.

**Query parameters from Google:**
- `code` -- Authorization code
- `state` -- CSRF state (must match session)

**Flow:**

1. **CSRF verification:**
   - Compares `request.args['state']` with `session['state']`
   - If mismatch: logs warning, calls `abort(401)`
   - Removes `state` from session

2. **Code exchange:**
   - Calls `exchange_code(code)` to get tokens from Google

3. **Token extraction:**
   - Extracts `id_token` from the exchange response

4. **Principal extraction:**
   - Calls `get_principal(id_token)` to decode email and profile (no signature verification)

5. **Whitelist check:**
   - If `AUTHORIZED` is in app config, checks if `principal` (email) is in the list
   - If not in list: logs warning, calls `abort(401)`

6. **Session expiry:**
   - Uses `EXPIRY` config, `DOCKMASTER_EXPIRY` env var, or `expires_in` from token response
   - Sets `session['expiry'] = datetime.now() + timedelta(seconds=expiry_value)`
   - **Note:** Uses naive `datetime.now()` (no timezone), but `has_principal()` uses timezone-aware comparison. This timezone mismatch is handled by `has_principal()` adding timezone info to the stored expiry.

7. **Session population:**
   - Sets `session['token']` = id_token
   - Sets `session['expiry']` = expiry datetime
   - Copies profile properties into session: `name`, `email`, `picture`, `given_name`, `family_name`, `locale`

8. **Redirect reconstruction:**
   - Pops `session['state.path']` (the original request path, default `'/'`)
   - Pops and unpickles `session['state.args']` (the original query parameters)
   - Prepends `PREFIX` config if set
   - Reconstructs URL: `{prefix}{path}?arg1=val1&arg2=val2`
   - Redirects to the reconstructed URL

### `GET /auth/logout` -- Logout

1. Calls `logout_principal()` (clears session)
2. Redirects to `APP_ROOT` (default `'/'`)

### `GET /auth/login` -- Login

Identical behavior to logout:
1. Calls `logout_principal()` (clears session)
2. Redirects to `APP_ROOT`

The actual login redirect happens via `login_authenticate()` when the user hits a protected page after session is cleared.

### `GET /auth/principal` -- Current User Info

Returns the authenticated user's profile as JSON.

```python
def principal():
    info = get_principal_profile() if has_principal() else {}
    return jsonify(info)
```

**Response when authenticated:**
```json
{
  "name": "Jane Doe",
  "email": "user@example.com",
  "picture": "https://...",
  "given_name": "Jane",
  "family_name": "Doe",
  "locale": "en"
}
```

**Response when not authenticated:**
```json
{}
```

---

## 5. Session Management Helpers

### `has_principal()`

```python
def has_principal() -> bool
```

Checks whether the current session contains a valid, non-expired authentication token.

**Logic:**
1. Checks `session` has `token` key with non-None value
2. If `expiry` key exists in session:
   - Gets current time with timezone: `datetime.now().astimezone()`
   - Adds timezone info to stored expiry (which was stored as naive datetime): `session['expiry'].replace(tzinfo=tz)`
   - Calculates elapsed time: `expiry - now`
   - If elapsed seconds < 0 (expired): pops `token` and `expiry`, returns `False`
3. If no `expiry` key: pops `token`, returns `False`
4. Returns `True` only if token exists and has not expired

### `login_authenticate()`

```python
def login_authenticate() -> Response | tuple | None
```

Flask `before_request` handler for browser-based OAuth2 login protection.

**Decision flow:**

```
request.path in NOAUTH?           → return None (skip auth)
request.path starts with NOAUTH_PREFIXES? → return None (skip auth)
request.path is {prefix}/logout?  → return None (skip auth)
request.path starts with {prefix}/principal? → return None (skip auth)
has_principal() is True?          → return None (authenticated)
request.path ends with /authenticated? → return None (callback route)
request.path not under APP_ROOT?  → return 401 JSON error
else                              → return redirect to auth_uri()
```

**Key behaviors:**
- Paths in `NOAUTH` list are exact matches
- Paths in `NOAUTH_PREFIXES` are prefix matches via `startswith()`
- The `/authenticated` callback route is always allowed through (so the OAuth2 callback can complete)
- Requests outside `APP_ROOT` that are unauthenticated get a 401 JSON error (API-style), not a redirect
- Requests under `APP_ROOT` that are unauthenticated get redirected to Google login

### `get_principal_profile()`

```python
def get_principal_profile(properties=default_profile_properties) -> dict
```

Extracts user profile properties from the session.

**Default properties:** `['name', 'email', 'picture', 'given_name', 'family_name', 'locale']`

Returns a dict of `{property: value}` where missing properties default to empty string `''`.

---

## 6. `RedisSessionInterface`

**Source file**: `dockmaster/sessions.py`

Replaces Flask's default client-side cookie sessions with server-side Redis-backed sessions. The session cookie contains only a session ID; the actual session data is stored in Redis.

### `total_seconds(td)`

```python
def total_seconds(td) -> int
```

Helper to convert a `timedelta` to total seconds: `td.days * 86400 + td.seconds`.

**Note:** This ignores microseconds. Python's `timedelta.total_seconds()` method exists and returns a float, but this custom implementation returns an int.

### `ServerSideSession`

```python
class ServerSideSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid=None, permanent=None)
```

A Flask-compatible session object that tracks modifications.

**Inheritance:**
- `CallbackDict` (from werkzeug): a dict that calls a callback when modified
- `SessionMixin` (from Flask): adds `modified` and `permanent` session properties

**Constructor:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `initial` | dict | None | Initial session data (loaded from Redis) |
| `sid` | str | None | Session ID (UUID4) |
| `permanent` | bool | None | If truthy, marks session as permanent (uses `PERMANENT_SESSION_LIFETIME` for expiry) |

**Behavior:**
- The `on_update` callback sets `self.modified = True` whenever the dict is changed
- `modified` starts as `False`
- `sid` is the session identifier stored in the cookie

### `RedisSessionInterface`

```python
class RedisSessionInterface(SessionInterface):
    def __init__(self, get_redis, key_prefix='session:')
```

**Constructor:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `get_redis` | callable | required | Factory function that returns a `redis.Redis` connection |
| `key_prefix` | str | `'session:'` | Prefix for Redis keys |

**Note:** `get_redis` is a callable (not a connection) to support lazy initialization and connection pooling. It is called on every `open_session()` and `save_session()`.

The constructor also checks `has_same_site_capability` -- whether the Flask `SessionInterface` base class supports the `SameSite` cookie attribute (version-dependent).

#### `open_session(app, request) -> ServerSideSession`

Called by Flask at the start of each request to load the session.

**Flow:**
1. Reads session cookie: `request.cookies.get(app.config['SESSION_COOKIE_NAME'])`
2. If no cookie:
   - Generates new SID via `_generate_sid()` (UUID4)
   - Returns empty `ServerSideSession(sid=new_sid)`
3. If cookie exists:
   - Calls `get_redis()` to get Redis connection
   - Reads `{key_prefix}{sid}` from Redis
   - If Redis value exists: unpickles the data, returns `ServerSideSession(data, sid=sid)`
   - If unpickle fails (bare `except`): returns empty `ServerSideSession(sid=sid)`
   - If Redis value is None (expired/missing): returns empty `ServerSideSession(sid=sid)`

#### `save_session(app, session, response)`

Called by Flask at the end of each request to persist the session.

**Flow:**
1. Gets cookie domain and path from Flask app config
2. Gets Redis connection via `get_redis()`
3. **If session is empty (falsy):**
   - If session was modified: deletes `{key_prefix}{sid}` from Redis and removes the cookie
   - Returns (no cookie set)
4. **If session has data:**
   - Pickles `dict(session)` -- converts CallbackDict to plain dict first
   - Stores in Redis with `setex()`: key=`{key_prefix}{sid}`, TTL=`app.permanent_session_lifetime` (converted to seconds)
   - Sets cookie on response:
     - Name: `SESSION_COOKIE_NAME`
     - Value: `session.sid`
     - Expires: from Flask's `get_expiration_time()`
     - HttpOnly: from Flask config
     - Secure: from Flask config
     - Domain: from Flask config
     - SameSite: from Flask config (if supported)

### Redis Key Structure

```
session:{uuid4}  →  pickled dict of session data
```

**TTL:** Set to `app.permanent_session_lifetime` (a `timedelta`). Default Flask value is 31 days.

### Security Considerations

- **Pickle deserialization:** Session data is serialized with `pickle`. If Redis is compromised, malicious pickle payloads could achieve remote code execution. JSON serialization would be safer but cannot serialize all Python types (e.g., `datetime` objects stored in session).
- **Session ID in cookie:** The SID is a UUID4 -- 122 bits of randomness, which is sufficient for session identifiers.
- **HttpOnly flag:** Set based on Flask config (default True), preventing JavaScript access to the session cookie.

### Usage

```python
import redis
from dockmaster import RedisSessionInterface

app = Flask(__name__)

def get_redis():
    return redis.Redis(host='localhost', port=6379, db=0)

app.session_interface = RedisSessionInterface(get_redis)
```

---

## 7. Dependencies

### `flask_integration.py` Imports

| Import | Package | Purpose |
|---|---|---|
| `sys` | stdlib | `sys.stderr` for error output in `exchange_code()` |
| `os` | stdlib | Read environment variables |
| `logging` | stdlib | Debug/warning logging throughout |
| `datetime`, `timedelta`, `timezone` | stdlib | Session expiry calculations |
| `uuid4` | stdlib | Generate CSRF state and nonce |
| `pickle` | stdlib | Serialize/deserialize request args for session storage |
| `urllib.parse.quote` (as `uriencode`) | stdlib | URL-encode redirect URI and query parameters |
| `urllib.parse.unquote_plus` | stdlib | Imported but **not used** |
| `json` | stdlib | Parse JWT payload in `get_principal()` |
| `base64` | stdlib | Decode JWT payload in `get_principal()` |
| `flask.Blueprint` | `flask` | Auth endpoint blueprint |
| `flask.request` | `flask` | Current request context |
| `flask.session` | `flask` | Session proxy |
| `flask.current_app` | `flask` | Application config access |
| `flask.redirect` | `flask` | HTTP redirect responses |
| `flask.abort` | `flask` | Abort with HTTP status |
| `flask.jsonify` | `flask` | JSON response helper |
| `.client.requests_retry_session` | dockmaster | HTTP client for code exchange |
| `.target.ServiceRealm` | dockmaster | Type annotation for `jwt_authenticate()` |

### `sessions.py` Imports

| Import | Package | Purpose |
|---|---|---|
| `pickle` | stdlib | Serialize/deserialize session data |
| `uuid4` | stdlib | Generate session IDs |
| `flask.sessions.SessionInterface` | `flask` | Base class for custom session interfaces |
| `flask.sessions.SessionMixin` | `flask` | Session behavior mixin |
| `werkzeug.datastructures.CallbackDict` | `werkzeug` | Dict with modification tracking |

### External Runtime Dependencies

| Dependency | Used For |
|---|---|
| `flask` | All request handling, session management, Blueprint routing |
| `werkzeug` | `CallbackDict` for session modification tracking |
| `redis` | Session storage backend (not imported directly -- accessed via `get_redis()` callable) |
| `requests` | HTTP calls for OAuth2 code exchange (via `requests_retry_session()`) |
