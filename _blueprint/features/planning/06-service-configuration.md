# Service: Configuration and Startup

**Source files**: `service/dockmaster_service/__init__.py`, `service/dockmaster_service/config.py`, `service/dockmaster_service/service.py` (initialization section), `service/dockmaster_service/__main__.py`, `service/dockmaster_service/message.py`

This document covers how the dockmaster service initializes, loads configuration, constructs dependencies, and registers API documentation.

---

## Table of Contents

1. [Startup Sequence](#1-startup-sequence)
2. [Config Class](#2-config-class)
3. [get_config() Pattern](#3-get_config-pattern)
4. [Dependency Factories](#4-dependency-factories)
5. [Dynamic Config Loading](#5-dynamic-config-loading)
6. [Flask App Initialization](#6-flask-app-initialization)
7. [Pydantic Models](#7-pydantic-models)
8. [API Documentation (watchtower)](#8-api-documentation-watchtower)
9. [Entry Points](#9-entry-points)

---

## 1. Startup Sequence

The service startup involves module-level initialization across three files, executed in import order:

```
1. service/dockmaster_service/service.py (imported by __init__.py)
   ├── Creates Flask app: Flask('XYZ')
   ├── Applies Config defaults: service.config.from_object(Config())
   ├── Creates watchtower API instance
   ├── Registers Pydantic models with API
   ├── Sets secret_key from Config.SESSION_KEY
   ├── Registers before_request handler
   └── Calls api.register(service) for OpenAPI docs

2. service/dockmaster_service/__init__.py
   ├── Imports Config and service from service.py (triggers step 1)
   ├── Checks SERVICE_CONFIG env var
   │   ├── If set: dynamically imports config class, applies to service.config
   │   └── If not set: reads LOG_LEVEL from config, sets logging level
   └── Exports: Config, service, get_config

3. Gunicorn / __main__.py
   └── Imports service from __init__.py (triggers step 2)
   └── Starts WSGI server
```

**Import note:** Because `__init__.py` imports from `service.py`, the Flask app and all route registrations happen at import time, before `SERVICE_CONFIG` is applied. This means the `Config` defaults are always applied first, and `SERVICE_CONFIG` can override them afterward.

---

## 2. `Config` Class

**Source**: `config.py:11-20`

```python
class Config:
    APP_ROOT = '/console/'
    AUTH_PREFIX = '/console/auth'
    NOAUTH = []
    NOAUTH_PREFIXES = ['/console/assets']
    AUTH_PROVIDER = 'https://accounts.google.com/o/oauth2/auth'
    TOKEN_PROVIDER = 'https://oauth2.googleapis.com/token'
    CLIENT_ID = '672345219866-cgt501gfbghclukdehvhlfnja5d7nqgc.apps.googleusercontent.com'
    REDIRECT_URI = 'http://auth.dev.example.net:9999/console/auth/'
    SESSION_KEY = b'zwdGbWiyDfhj2p1NdC61UOEiR+rLZ30t'
```

All attributes are class-level static values. Applied to Flask via `service.config.from_object(Config())`.

| Attribute | Value | Purpose |
|---|---|---|
| `APP_ROOT` | `'/console/'` | Root path for the console UI (currently disabled) |
| `AUTH_PREFIX` | `'/console/auth'` | Auth endpoint prefix for console OAuth (currently disabled) |
| `NOAUTH` | `[]` | Paths exempt from authentication (empty -- all paths require auth) |
| `NOAUTH_PREFIXES` | `['/console/assets']` | Path prefixes exempt from auth (for static assets) |
| `AUTH_PROVIDER` | Google OAuth2 auth URL | Google authorization endpoint |
| `TOKEN_PROVIDER` | Google token URL | Google token exchange endpoint |
| `CLIENT_ID` | `672345219866-...` | Google OAuth client ID (for console UI login) |
| `REDIRECT_URI` | `http://auth.dev.example.net:9999/console/auth/` | OAuth callback URL (dev default) |
| `SESSION_KEY` | base64 bytes | Secret key for Flask session signing |

**Note:** These defaults are oriented toward the console UI and local development. In production, most values are overridden via environment variables (not via `SERVICE_CONFIG`). The API endpoints (`/exchange`, `/refresh`, `/has`, etc.) don't use most of these config values -- they rely on environment variables directly.

---

## 3. `get_config()` Pattern

**Source**: `config.py:22-23`

```python
def get_config(name, default=None):
    return os.environ.get(name, current_app.config.get(name, default))
```

**Lookup order:** Environment variable -> Flask app config -> default

This is the service's configuration accessor. **Important:** This lookup order (env first) is the **opposite** of the `get_config()` in `flask_integration.py` (Flask config first, then env). The service prioritizes environment variables because production configuration comes from Kubernetes ConfigMaps and Secrets mounted as env vars.

### All Configuration Accessors

Each accessor wraps `get_config()` with a specific config key and default:

| Function | Config Key | Default | Return Type | Description |
|---|---|---|---|---|
| `get_issuer()` | `ISSUER` | `None` | `str \| None` | File path to service account JSON key |
| `get_project()` | `SECRETS_PROJECT` | `None` | `str \| None` | GCP project for Secret Manager |
| `get_access_token_endpoint()` | `ACCESS_TOKEN_ENDPOINT` | `https://www.googleapis.com/oauth2/v1/tokeninfo` | `str` | Google token validation endpoint |
| `get_refresh_token_endpoint()` | `REFRESH_TOKEN_ENDPOINT` | `https://www.googleapis.com/oauth2/v4/token` | `str` | Google refresh token endpoint |
| `get_userinfo_endpoint()` | `USERINFO_ENDPOINT` | `https://www.googleapis.com/oauth2/v3/userinfo` | `str` | Google user profile endpoint |
| `get_default_client_id()` | `DEFAULT_CLIENT_ID` | `None` | `str \| None` | Default OAuth client ID for refresh flow |
| `get_client_id_suffix()` | `CLIENT_ID_SUFFIX` | `.apps.googleusercontent.com` | `str` | Suffix appended to short client IDs |

### Comma-Separated Set Accessors

These parse comma-separated strings into sets. They use Flask `g` for per-request caching.

| Function | Config Key | Default | Description |
|---|---|---|---|
| `get_authorized_issuers()` | `AUTHORIZED_ISSUERS` | `set()` | Trusted JWT issuers (e.g., `https://accounts.google.com,sa@project.iam...`) |
| `get_authorized_domains()` | `AUTHORIZED_DOMAINS` | `set()` | Allowed email domains (e.g., `shipyard.com`) |
| `get_authorized_audience()` | `AUTHORIZED_AUDIENCE` | `set()` | Allowed JWT audiences (e.g., Google client IDs) |

**Parsing logic** (identical for all three):
```python
spec = get_config('AUTHORIZED_ISSUERS')
if spec is None:
    g.authorized_issuers = set([])
else:
    g.authorized_issuers = set([s.strip() for s in spec.split(',')])
```

### `get_project()` -- Special Case

```python
def get_project():
    return current_app.config.get('SECRETS_PROJECT', os.environ.get('SECRETS_PROJECT'))
```

This does **not** use `get_config()`. The lookup order is reversed: Flask config first, then env var. No default is provided. This is likely inconsistent with the other accessors.

---

## 4. Dependency Factories

### GCP Credential Chain

```
get_issuer()          → returns file path string (ISSUER env var)
    ↓
get_credentials()     → loads service_account.Credentials from file
    ↓
get_client()          → creates SecretManagerServiceClient with credentials
```

#### `get_credentials()`

```python
def get_credentials():
    issuer = get_issuer()
    return service_account.Credentials.from_service_account_file(issuer) if issuer is not None else None
```

Loads GCP service account credentials from the `ISSUER` file path. Returns `None` if `ISSUER` is not configured.

**In production:** `ISSUER` is set to `/etc/issuer/identity.json` (mounted from a Kubernetes secret).

#### `get_client()`

```python
def get_client():
    credentials = get_credentials()
    client = secretmanager.SecretManagerServiceClient(credentials=credentials)
    return client
```

Creates a new Secret Manager client on every call. **Not cached** -- a new client is created per invocation.

### Cached Dependencies (Flask `g`)

These are created once per request and cached in Flask's `g` object:

#### `get_authority()`

```python
def get_authority():
    if 'authority' not in g:
        g.authority = Authority(SecretsStorage(get_client(), get_project()))
    return g.authority
```

Creates `Authority` with a fresh `SecretsStorage` and `SecretManagerServiceClient`. Cached per request, so:
- Multiple permission checks in the same request share one Authority (and its role/permission caches)
- Each new request gets a fresh Authority
- A new `SecretManagerServiceClient` is created per request

#### `get_realm()`

```python
def get_realm():
    if 'realm' not in g:
        g.realm = ServiceRealm(get_key_cache())
    return g.realm
```

Creates `ServiceRealm` wrapping the global key cache. Cached per request. The `ServiceRealm` itself is lightweight -- the expensive part (the key cache) is shared globally.

### Global Singleton

#### `get_key_cache()`

```python
_key_cache = None

def get_key_cache():
    global _key_cache
    if _key_cache is None:
        _key_cache = ServiceAccountKeyCache(
            project=os.environ.get('SECRETS_PROJECT'),
            credentials=get_issuer()
        )
    return _key_cache
```

Module-level singleton -- created once for the entire process lifetime. The `ServiceAccountKeyCache` handles its own time-based refresh internally (default 300s expiry).

**Note:** Uses `os.environ.get('SECRETS_PROJECT')` directly instead of `get_config()` because this runs outside a Flask request context (at first access time).

### Dependency Lifecycle Summary

| Dependency | Scope | Created When |
|---|---|---|
| `_key_cache` (ServiceAccountKeyCache) | Process-global singleton | First request |
| `g.realm` (ServiceRealm) | Per-request | Each request |
| `g.authority` (Authority) | Per-request | Each request needing RBAC |
| `g.authorized_issuers` (set) | Per-request | Each request needing issuer check |
| `g.authorized_domains` (set) | Per-request | Each request needing domain check |
| `g.authorized_audience` (set) | Per-request | Each request needing audience check |
| `SecretManagerServiceClient` | Per-request (via get_authority) | Each request needing RBAC |
| `Credentials` | Per-call (not cached) | Each call to get_credentials() |

---

## 5. Dynamic Config Loading

**Source**: `__init__.py:18-46`

The `SERVICE_CONFIG` environment variable enables dynamic configuration class loading.

```python
if 'SERVICE_CONFIG' in os.environ and __configured__ is None:
    config_value = os.environ['SERVICE_CONFIG']
    modulename, _, classname = config_value.rpartition('.')
    m = __import__(modulename)
    config = getattr(m, classname)()
    service.config.from_object(config)
```

**Format:** `module.ClassName` (e.g., `myapp.config.ProductionConfig`)

**Behavior:**
1. Splits on last `.` to get module name and class name
2. Imports the module via `__import__()`
3. Gets the class from the module, instantiates it
4. Applies to Flask via `service.config.from_object(config)`
5. Stores in `__configured__` dict to prevent re-application

**Error handling:**
- `ModuleNotFoundError`: prints error to stderr, calls `sys.exit(1)`
- Missing class attribute: prints error to stderr, calls `sys.exit(1)`

**If `SERVICE_CONFIG` is not set:** Reads `LOG_LEVEL` from config and sets Python logging level.

```python
else:
    with service.app_context():
        log_level = get_config('LOG_LEVEL')
        if log_level is not None:
            set_loglevel(log_level)
```

The `set_loglevel()` function converts the string level (e.g., `'debug'`) to a logging constant and calls `logging.basicConfig(level=n_log_level)`.

---

## 6. Flask App Initialization

**Source**: `service.py:19-57`

### App Creation

```python
assets_dir = str(importlib.resources.path(dockmaster_service, 'assets'))
templates_dir = str(importlib.resources.path(dockmaster_service, 'templates'))

service = Flask('XYZ', template_folder=templates_dir)
service.config.from_object(Config())
```

- Flask app name: `'XYZ'` (micro symbol, for the-project)
- Template folder and assets directory resolved via `importlib.resources` for package-relative paths
- Config defaults applied immediately

### Secret Key

```python
service.secret_key = base64.b64decode(Config.SESSION_KEY)
```

Base64-decodes the `SESSION_KEY` bytes to produce the Flask secret key used for session cookie signing.

### Before Request Handler

```python
@service.before_request
def before_request():
    if request.path.startswith('/exchange'):
        return
    if request.path.startswith('/refresh'):
        return
    if request.path.startswith('/apidocs') or request.path.startswith('/apispec'):
        return
    realm = get_realm()
    return jwt_authenticate(realm)
```

**Skip list** (no JWT auth required):

| Path Prefix | Reason |
|---|---|
| `/exchange` | Does its own token validation (JWT or access token) |
| `/refresh` | Accepts refresh tokens, not JWTs |
| `/apidocs`, `/apispec` | API documentation endpoints (public) |

**All other paths:** Requires valid JWT Bearer token via `jwt_authenticate(realm)`.

**Commented-out console logic** (lines 50-55): Previously, paths under `APP_ROOT` used `login_authenticate()` (browser OAuth) while API paths used `jwt_authenticate()`. This was removed when the console was disabled.

---

## 7. Pydantic Models

**Source**: `message.py`

### `Token`

```python
class Token(BaseModel):
    token: str
    subject: str
    service: str
    expiry: int
    claims: Optional[Dict] = {}
    access_token: Optional[str] = None
    id_token: Optional[str] = None
```

Response model for token issuance endpoints (`/exchange`, `/refresh`).

| Field | Type | Required | Description |
|---|---|---|---|
| `token` | str | yes | The dockmaster-signed JWT |
| `subject` | str | yes | Email/principal the token represents |
| `service` | str | yes | Service audience the token is for |
| `expiry` | int | yes | Token lifetime in seconds |
| `claims` | dict | no | Extra profile claims (name, picture, etc.). Default `{}` |
| `access_token` | str | no | Google access token (only in `/refresh` response) |
| `id_token` | str | no | Google ID token (only in `/refresh` response) |

### `RefreshTokenRequest`

```python
class RefreshTokenRequest(BaseModel):
    token: str
    client_id: str = None
    service: str = None
    expiry: int = 3600
```

Request body model for `POST /refresh`.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `token` | str | yes | -- | Google refresh token |
| `client_id` | str | no | `None` | Google OAuth client ID. If omitted, uses `DEFAULT_CLIENT_ID` from config |
| `service` | str | no | `None` | Target service audience. If omitted, uses the audience from the refreshed Google token |
| `expiry` | int | no | `3600` | Desired token lifetime in seconds |

### Unmarshalling

```python
from watchtower import unmarshaller
unmarshall = unmarshaller(RefreshTokenRequest)
```

The `unmarshall` function (from `watchtower`) is used to deserialize request JSON into Pydantic models:
```python
req = unmarshall(RefreshTokenRequest, request.json)
```

---

## 8. API Documentation (watchtower)

**Source**: `service.py:25-31, 391`

The `watchtower` library provides OpenAPI/Swagger documentation generation for Flask.

### Setup

```python
from watchtower import API, StatusCode, StatusResponse, get_config, unmarshaller

api = API(
    title='Dockmaster',
    version=__version__,       # (0, 12, 3)
    description='The dockmaster authentication service',
    libraries=['dockmaster']
)
```

### Model Registration

```python
api.add_types(*[(cls.__name__, cls) for cls in [
    Token,
    RefreshTokenRequest
]])
```

Registers Pydantic models as OpenAPI schemas referenced by route docstrings (`$ref: '#/components/schemas/Token'`).

### Route Documentation

Routes use YAML docstrings (OpenAPI spec fragments) parsed by watchtower:
```python
@service.route('/exchange', methods=['GET'])
def exchange():
    """
    ---
    get:
      description: Exchanges a Google Login JWT...
      responses:
        200:
          content:
            'application/json':
              schema:
                $ref: '#/components/schemas/Token'
    """
```

### Registration

```python
api.register(service, authenticator=None)
```

Attaches the API documentation to the Flask app. This adds `/apidocs` and `/apispec` routes for the Swagger UI and OpenAPI JSON spec respectively.

### `StatusResponse` and `StatusCode`

From `watchtower`, used for error responses:
```python
StatusResponse(status=StatusCode.Error, message='...')
```

Serialized as:
```json
{"status": "Error", "message": "..."}
```

---

## 9. Entry Points

### Development: `__main__.py`

```python
python -m dockmaster_service [host:port]
```

- Default: `0.0.0.0:9999`
- Parses `host:port` from first command-line argument
- If no port separator found, defaults port to `9999`
- Runs Flask development server: `service.run(host=host, port=port)`

### Production: Gunicorn

The service is packaged as a `.pyz` archive and run via gunicorn:

```bash
gunicorn dockmaster_service:service -b 0.0.0.0:9999 -w 4 -k gevent \
    --access-logfile - --error-logfile - \
    --log-level ${LOG_LEVEL} --timeout 600
```

| Gunicorn Parameter | Value | Purpose |
|---|---|---|
| `dockmaster_service:service` | -- | WSGI app: imports `service` from `dockmaster_service` package |
| `-b 0.0.0.0:9999` | -- | Bind to all interfaces, port 9999 |
| `-w 4` | -- | 4 worker processes |
| `-k gevent` | -- | Async worker class (greenlet-based concurrency) |
| `--access-logfile -` | -- | Access logs to stdout |
| `--error-logfile -` | -- | Error logs to stderr |
| `--log-level` | from env | Logging verbosity |
| `--timeout 600` | -- | Worker timeout (10 minutes) |

**Note on gevent:** The gevent worker class enables cooperative multitasking within each worker process. This is important because the service makes blocking HTTP calls to Google APIs and GCP Secret Manager. With gevent, these blocking calls are monkey-patched to yield to other greenlets, allowing a single worker to handle multiple concurrent requests.
