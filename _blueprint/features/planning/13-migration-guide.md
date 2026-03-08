# Migration Guide: Flask to FastAPI

This document provides a comprehensive mapping from the current Flask-based implementation to a FastAPI recreation. It covers dependency changes, pattern-by-pattern migration, architectural decisions, and a recommended implementation order.

---

## Table of Contents

1. [Dependency Changes](#1-dependency-changes)
2. [Pattern Mapping Table](#2-pattern-mapping-table)
3. [Configuration: Pydantic BaseSettings](#3-configuration-pydantic-basesettings)
4. [Authentication: Dependency Injection](#4-authentication-dependency-injection)
5. [Dependency Factories: Replacing Flask g](#5-dependency-factories-replacing-flask-g)
6. [Routing: APIRouter Replacing Blueprint](#6-routing-apirouter-replacing-blueprint)
7. [Request/Response Handling](#7-requestresponse-handling)
8. [Session Management](#8-session-management)
9. [HTTP Client: httpx Replacing requests](#9-http-client-httpx-replacing-requests)
10. [API Documentation](#10-api-documentation)
11. [ASGI Server Configuration](#11-asgi-server-configuration)
12. [Deployment Changes](#12-deployment-changes)
13. [Client Library Refactoring](#13-client-library-refactoring)
14. [Known Issues to Fix During Migration](#14-known-issues-to-fix-during-migration)
15. [Recommended Implementation Order](#15-recommended-implementation-order)
16. [Testing Strategy](#16-testing-strategy)

---

## 1. Dependency Changes

### Remove

| Package | Reason |
|---|---|
| `flask` | Replaced by FastAPI |
| `watchtower` | FastAPI has built-in OpenAPI docs |
| `gevent` | Replaced by uvicorn's async I/O |

### Add

| Package | Replaces | Purpose |
|---|---|---|
| `fastapi` | `flask` | ASGI web framework |
| `uvicorn[standard]` | `gunicorn[gevent]` | ASGI server (or use as gunicorn worker) |
| `httpx` | `requests` (in async paths) | Async HTTP client |

### Keep (no changes)

| Package | Reason |
|---|---|
| `google-auth` | JWT signing/verification -- framework-independent |
| `google-api-python-client` | GCP IAM API -- framework-independent |
| `google-cloud-secret-manager` | RBAC storage -- framework-independent |
| `pydantic` | Already used for models; FastAPI is built on Pydantic |
| `click` | CLI tool -- framework-independent |
| `requests` | Keep for sync code paths (CLI, sync client library) |
| `redis` | Session storage (if sessions are needed) |

### Updated Dependency Lists

**Client library (`dockmaster/setup.cfg`):**
```
install_requires =
    google-auth
    google-api-python-client
    google-cloud-secret-manager
    click
    # flask removed -- see Client Library Refactoring section
    httpx          # for async HTTP client variants
    requests       # for sync HTTP client (CLI, backward compat)
```

**Service (`dockmaster_service/setup.cfg`):**
```
install_requires =
    dockmaster
    fastapi
    uvicorn[standard]
    httpx
    google-api-python-client
    google-cloud-secret-manager
    pydantic
```

---

## 2. Pattern Mapping Table

| Flask Pattern | FastAPI Equivalent | Notes |
|---|---|---|
| `Flask('XYZ')` | `FastAPI(title='Dockmaster')` | App creation |
| `Blueprint('auth', ...)` | `APIRouter(prefix='/auth')` | Route grouping |
| `@service.route('/path')` | `@app.get('/path')` | Route decoration |
| `@service.before_request` | `@app.middleware("http")` or `Depends()` | Request preprocessing |
| `flask.request` | `fastapi.Request` or parameter injection | Request access |
| `flask.request.args.get('x')` | `x: str = Query(None)` | Query parameters |
| `flask.request.json` | `body: Model` (Pydantic parameter) | Request body |
| `flask.g` | `request.state` + `Depends()` | Per-request state |
| `flask.session` | Custom middleware + Redis | Server-side sessions |
| `current_app.config` | `Settings()` via `Depends(get_settings)` | Configuration |
| `jsonify(data)` | `return data` (auto-serialized) | JSON responses |
| `jsonify(PydanticModel)` | `return PydanticModel` | Model responses |
| `abort(401)` | `raise HTTPException(status_code=401)` | Error responses |
| `redirect(url)` | `RedirectResponse(url)` | Redirects |
| `render_template('x.html')` | `Jinja2Templates.TemplateResponse()` | HTML templates |
| `send_from_directory(dir, path)` | `StaticFiles` mount | Static files |
| `service.config.from_object(Config())` | `Settings()` at import time | Config loading |
| `request.environ['REMOTE_USER']` | `request.state.user` or return from `Depends` | Authenticated user |
| `watchtower API + register()` | Built-in `/docs` and `/redoc` | API docs |

---

## 3. Configuration: Pydantic BaseSettings

Replace the `Config` class and `get_config()` pattern with Pydantic `BaseSettings`.

### Current Pattern (Flask)

```python
# config.py
class Config:
    APP_ROOT = '/console/'
    CLIENT_ID = '672345...'
    # ...

def get_config(name, default=None):
    return os.environ.get(name, current_app.config.get(name, default))

def get_authorized_issuers():
    if 'authorized_issuers' not in g:
        spec = get_config('AUTHORIZED_ISSUERS')
        g.authorized_issuers = set(s.strip() for s in spec.split(',')) if spec else set()
    return g.authorized_issuers
```

### FastAPI Equivalent

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Service configuration
    issuer: str | None = None
    secrets_project: str | None = None
    client_secret: str | None = None
    log_level: str = "info"

    # Authorization (comma-separated → parsed to sets)
    authorized_issuers: set[str] = set()
    authorized_domains: set[str] = set()
    authorized_audience: set[str] = set()

    # OAuth
    default_client_id: str | None = None
    client_id_suffix: str = ".apps.googleusercontent.com"

    # Google endpoints (with defaults)
    access_token_endpoint: str = "https://www.googleapis.com/oauth2/v1/tokeninfo"
    refresh_token_endpoint: str = "https://www.googleapis.com/oauth2/v4/token"
    userinfo_endpoint: str = "https://www.googleapis.com/oauth2/v3/userinfo"

    class Config:
        env_file = ".env"

    @field_validator("authorized_issuers", "authorized_domains", "authorized_audience",
                     mode="before")
    @classmethod
    def parse_comma_separated(cls, v):
        if isinstance(v, str):
            return {s.strip() for s in v.split(",") if s.strip()}
        return v

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Key advantages:**
- Environment variables are automatically loaded (Pydantic reads `AUTHORIZED_ISSUERS` env var into `authorized_issuers` field)
- Comma-separated strings are parsed via a validator at startup
- `@lru_cache` ensures Settings is created once (equivalent to a global singleton)
- No per-request caching needed (values don't change at runtime)
- Type validation at startup catches configuration errors early

---

## 4. Authentication: Dependency Injection

Replace `before_request` + `jwt_authenticate()` + `request.environ['REMOTE_USER']` with a FastAPI dependency.

### Current Pattern (Flask)

```python
@service.before_request
def before_request():
    if request.path.startswith('/exchange'):
        return
    # ... other skips ...
    realm = get_realm()
    return jwt_authenticate(realm)

# In jwt_authenticate():
request.environ['REMOTE_USER'] = claims

# In route handlers:
claims = request.environ['REMOTE_USER']
```

### FastAPI Equivalent

```python
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer_scheme = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    realm = get_realm(settings)
    try:
        claims = realm.verify(credentials.credentials)
        return claims
    except ValueError:
        raise HTTPException(status_code=401, detail="Not authenticated")

# In route handlers:
@app.get("/claims")
async def claims(user: dict = Depends(get_current_user)):
    return user

@app.get("/key/{kid}")
async def get_key(kid: str, user: dict = Depends(get_current_user)):
    # user is verified, proceed
    ...
```

**Key advantages:**
- No global `before_request` with path-based skip logic
- Auth is applied per-route via `Depends()` -- routes that don't need auth simply don't include it
- The dependency return value (`claims`) is directly available as a function parameter
- `HTTPBearer` adds the lock icon in Swagger UI for authenticated endpoints

### Selective Authentication

Routes that skip auth (like `/exchange` and `/refresh`) simply don't use the `get_current_user` dependency:

```python
@app.get("/exchange")
async def exchange(request: Request):
    # Does its own token handling
    ...

@app.post("/refresh")
async def refresh(body: RefreshTokenRequest):
    # No auth needed
    ...

@app.get("/has/{subject}/{target}/{permission:path}")
async def path_has(subject: str, target: str, permission: str,
                   user: dict = Depends(get_current_user)):
    # Requires auth
    ...
```

---

## 5. Dependency Factories: Replacing Flask `g`

Replace Flask's `g` object (per-request cache) with FastAPI's dependency injection.

### Current Pattern (Flask)

```python
def get_realm():
    if 'realm' not in g:
        g.realm = ServiceRealm(get_key_cache())
    return g.realm

def get_authority():
    if 'authority' not in g:
        g.authority = Authority(SecretsStorage(get_client(), get_project()))
    return g.authority
```

### FastAPI Equivalent

```python
# Global singleton (same as current _key_cache pattern)
_key_cache: ServiceAccountKeyCache | None = None

def get_key_cache(settings: Settings = Depends(get_settings)) -> ServiceAccountKeyCache:
    global _key_cache
    if _key_cache is None:
        _key_cache = ServiceAccountKeyCache(
            project=settings.secrets_project,
            credentials=settings.issuer,
        )
    return _key_cache

# Per-request dependency (equivalent to g.realm)
def get_realm(key_cache: ServiceAccountKeyCache = Depends(get_key_cache)) -> ServiceRealm:
    return ServiceRealm(key_cache)

# Per-request dependency (equivalent to g.authority)
def get_authority(settings: Settings = Depends(get_settings)) -> Authority:
    credentials = get_credentials(settings.issuer)
    client = secretmanager.SecretManagerServiceClient(credentials=credentials)
    return Authority(SecretsStorage(client, settings.secrets_project))
```

FastAPI's `Depends()` system calls the factory once per request and caches the result within that request (same behavior as Flask `g`). No manual `if 'x' not in g` checks needed.

### Lifespan Events (App Startup/Shutdown)

For initialization that currently happens at module import time:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize global singletons
    settings = get_settings()
    app.state.key_cache = ServiceAccountKeyCache(
        project=settings.secrets_project,
        credentials=settings.issuer,
    )
    yield
    # Shutdown: cleanup if needed

app = FastAPI(title="Dockmaster", lifespan=lifespan)
```

---

## 6. Routing: APIRouter Replacing Blueprint

### Current Pattern (Flask)

```python
auth_endpoint = Blueprint('auth', __name__, url_prefix='/auth')

@auth_endpoint.route('/authenticated', methods=['GET'])
def authenticated():
    ...

service.register_blueprint(auth_endpoint, url_prefix='/console/auth')
```

### FastAPI Equivalent

```python
auth_router = APIRouter(prefix="/auth", tags=["auth"])

@auth_router.get("/authenticated")
async def authenticated(request: Request):
    ...

app.include_router(auth_router)
```

### Path Parameters

Flask's `<path:permission>` converter maps directly:

```python
# Flask
@service.route('/has/<subject>/<target>/<path:permission>')

# FastAPI
@app.get("/has/{subject}/{target}/{permission:path}")
```

---

## 7. Request/Response Handling

### JSON Responses

```python
# Flask
return jsonify(Token(token=t, subject=e, service=s, expiry=x))
return jsonify({'error': 'Not authenticated'}), 401
return jsonify(StatusResponse(status=StatusCode.Error, message='...')), 403
return '', 204

# FastAPI
return Token(token=t, subject=e, service=s, expiry=x)                    # auto-serialized
raise HTTPException(status_code=401, detail="Not authenticated")
raise HTTPException(status_code=403, detail="...")
return Response(status_code=204)
```

### Non-JSON Responses

```python
# Flask (PEM key)
return key, 200, {'Content-Type': 'application/x-pem-file'}

# FastAPI
return Response(content=key, media_type="application/x-pem-file")
```

### Request Body

```python
# Flask
req = unmarshall(RefreshTokenRequest, request.json)

# FastAPI (automatic)
@app.post("/refresh")
async def refresh(req: RefreshTokenRequest):
    # req is already validated and typed
    ...
```

### Query Parameters

```python
# Flask
service = request.args.get('service', aud)
expiry = int(request.args.get('expiry', 3600))

# FastAPI
@app.get("/exchange")
async def exchange(
    service: str | None = Query(None),
    expiry: int = Query(3600),
):
    ...
```

### Error Response Standardization

Replace the mixed error formats (`{"error": "..."}` vs `StatusResponse`) with a consistent approach:

```python
# Option A: Use HTTPException everywhere (simplest)
raise HTTPException(status_code=403, detail="Issuer not allowed")

# Option B: Custom error model for structured errors
class ErrorResponse(BaseModel):
    status: str = "Error"
    message: str

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(message=exc.detail).model_dump(),
    )
```

---

## 8. Session Management

The current implementation uses `RedisSessionInterface` for server-side Flask sessions. This is only used by the console UI (currently disabled).

### Decision Point

If the console UI is not being recreated, session management can be omitted entirely. The API endpoints use JWT Bearer auth exclusively.

If sessions are needed:

### Option A: `starsessions` library

```python
from starsessions import SessionMiddleware
from starsessions.backends.redis import RedisBackend

app.add_middleware(
    SessionMiddleware,
    backend=RedisBackend("redis://localhost"),
    cookie_name="session",
    cookie_https_only=True,
)
```

### Option B: Custom middleware

```python
import json
from uuid import uuid4

class RedisSessionMiddleware:
    async def __call__(self, scope, receive, send):
        # Read session cookie → load from Redis
        # Set request.state.session
        # After response, save to Redis, set cookie
        ...
```

### Option C: JWT-based sessions

Replace session cookies with short-lived JWTs stored in HttpOnly cookies. Eliminates the Redis dependency for sessions.

### Recommendation

For a clean migration, skip sessions entirely. The service's API is JWT-authenticated, and the console UI (the only session consumer) is disabled. If browser-based auth is needed later, Option A (`starsessions`) is the simplest.

---

## 9. HTTP Client: httpx Replacing requests

### Sync Paths (Keep `requests`)

The client library's sync functions (`ServiceUser.get_token()`, `AuthorityClient.has_permission()`, CLI commands) should continue using `requests` for backward compatibility.

### Async Paths (Use `httpx`)

Service endpoints that make outbound HTTP calls should use `httpx.AsyncClient`:

```python
import httpx

# Current (sync, blocks the event loop)
response = requests.post(endpoint, params={...})

# FastAPI (async)
async with httpx.AsyncClient() as client:
    response = await client.post(endpoint, params={...})
```

### Retry Logic

Replace `requests_retry_session()` with `httpx` + `tenacity`:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result
import httpx

def is_server_error(response):
    return response.status_code in (500, 502, 504)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.3),
    retry=retry_if_result(is_server_error),
)
async def fetch_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs):
    response = await client.request(method, url, timeout=httpx.Timeout(5.0, read=30.0), **kwargs)
    return response
```

Or use the `httpx-retries` package if available.

### Shared Client

Create a shared `httpx.AsyncClient` at app startup to benefit from connection pooling:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=30.0))
    yield
    await app.state.http_client.aclose()
```

---

## 10. API Documentation

### Current: watchtower

```python
from watchtower import API, StatusCode, StatusResponse, unmarshaller

api = API(title='Dockmaster', version=__version__, description='...')
api.add_types(*[(cls.__name__, cls) for cls in [Token, RefreshTokenRequest]])
api.register(service, authenticator=None)
```

### FastAPI: Built-in

```python
app = FastAPI(
    title="Dockmaster",
    version="0.12.3",
    description="The dockmaster authentication service",
)

# Pydantic models are automatically included in the OpenAPI schema
# when used as route parameters or return types.

@app.get("/exchange", response_model=Token)
async def exchange(...):
    ...

@app.post("/refresh", response_model=Token)
async def refresh(req: RefreshTokenRequest):
    ...
```

**Endpoints automatically available:**
- `/docs` -- Swagger UI (replaces `/apidocs`)
- `/redoc` -- ReDoc alternative
- `/openapi.json` -- OpenAPI spec (replaces `/apispec`)

**Remove:** `watchtower` import, `API` instance, `add_types`, `register`, `StatusResponse`, `StatusCode`, `unmarshaller`. All replaced by FastAPI built-ins.

---

## 11. ASGI Server Configuration

### Current: Gunicorn + gevent

```bash
gunicorn dockmaster_service:service -b 0.0.0.0:9999 -w 4 -k gevent \
    --access-logfile - --error-logfile - --log-level debug --timeout 600
```

### Option A: Gunicorn + Uvicorn Workers (recommended for production)

```bash
gunicorn dockmaster_service:app -b 0.0.0.0:9999 -w 4 \
    -k uvicorn.workers.UvicornWorker \
    --access-logfile - --error-logfile - --log-level debug --timeout 600
```

- Multi-process with async I/O per worker
- Same gunicorn process management (worker recycling, graceful shutdown)
- The `.pyz` shiv entry point changes from `gunicorn.app.wsgiapp:run` to the same (gunicorn's entry point is unchanged)

### Option B: Standalone Uvicorn

```bash
uvicorn dockmaster_service:app --host 0.0.0.0 --port 9999 --workers 4 \
    --access-log --log-level debug --timeout-keep-alive 600
```

- Simpler, fewer dependencies
- Less mature process management compared to gunicorn

### Recommendation

Option A for production. The Kubernetes deployment already uses gunicorn, so changing only the worker class minimizes deployment changes.

### Shiv Build Command Change

```bash
# Current
python -m shiv -o ${ARCHIVE} -e gunicorn.app.wsgiapp:run . ./service gunicorn[gevent]

# New
python -m shiv -o ${ARCHIVE} -e gunicorn.app.wsgiapp:run . ./service gunicorn uvicorn[standard]
```

Replace `gunicorn[gevent]` with `gunicorn uvicorn[standard]`.

### Kubernetes Container Args Change

```yaml
# Current
args: ["/app/$(ARCHIVE)", "dockmaster_service:service", "-b", "0.0.0.0:9999",
       "-w", "4", "-k", "gevent", ...]

# New
args: ["/app/$(ARCHIVE)", "dockmaster_service:app", "-b", "0.0.0.0:9999",
       "-w", "4", "-k", "uvicorn.workers.UvicornWorker", ...]
```

Two changes:
1. WSGI app reference `dockmaster_service:service` → ASGI app reference `dockmaster_service:app`
2. Worker class `-k gevent` → `-k uvicorn.workers.UvicornWorker`

---

## 12. Deployment Changes

### Kubernetes Manifest Changes

Minimal changes needed:

| File | Change |
|---|---|
| `base/deployment.yaml` | Update container args (app name + worker class) |
| `service/deploy.yaml` | Update shiv build command (replace gevent with uvicorn) |

### Container Image

`python:3.10` continues to work. Consider upgrading to `python:3.11` or `python:3.12` for performance improvements and better async support.

### Health Checks

FastAPI makes it easy to add health/readiness probes:

```python
@app.get("/healthz")
async def health():
    return {"status": "ok"}
```

Add to Kubernetes deployment:
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 9999
  initialDelaySeconds: 10
  periodSeconds: 30
readinessProbe:
  httpGet:
    path: /healthz
    port: 9999
  initialDelaySeconds: 5
  periodSeconds: 10
```

The `/healthz` path should be added to the auth skip logic (or simply not require auth via the dependency injection approach).

---

## 13. Client Library Refactoring

The `dockmaster` client library currently has Flask as a hard dependency because of `flask_integration.py` and `sessions.py`. The migration should decouple the library.

### Proposed Package Structure

```
dockmaster/
├── __init__.py           # Core exports (no Flask imports)
├── client.py             # ServiceUser, AuthorityClient -- unchanged
├── target.py             # ServiceRealm, KeyCache hierarchy -- unchanged
├── rbac.py               # RBAC data model -- unchanged
├── __main__.py           # CLI -- unchanged
├── fastapi_integration.py  # NEW: FastAPI auth dependencies
└── flask_integration.py    # KEEP for backward compat (optional dependency)
    sessions.py             # KEEP for backward compat (optional dependency)
```

### Making Flask Optional

```python
# __init__.py
from .client import ServiceUser, AuthorityClient, requests_retry_session, check_access_token
from .target import ServiceRealm, KeyCache, RemoteKeyCache, ServiceAccountKeyCache, public_keys
from .rbac import Role, Grant, ServiceGrants, Authority, SecretsStorage

# Flask integration only if Flask is installed
try:
    from .flask_integration import (get_bearer_token, jwt_authenticate,
        auth_endpoint, login_authenticate, has_principal,
        get_principal_profile, logout_principal)
    from .sessions import RedisSessionInterface
except ImportError:
    pass

# FastAPI integration only if FastAPI is installed
try:
    from .fastapi_integration import get_bearer_token, verify_jwt, auth_router
except ImportError:
    pass
```

### `fastapi_integration.py` (New)

```python
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .target import ServiceRealm

bearer_scheme = HTTPBearer(auto_error=False)

def get_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth is None:
        return None
    kind, _, value = auth.partition(" ")
    if kind != "Bearer":
        return None
    value = value.strip()
    return value if value else None

def verify_jwt_factory(realm: ServiceRealm):
    """Creates a FastAPI dependency that verifies JWTs against the given realm."""
    async def verify_jwt(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> dict:
        if credentials is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        try:
            return realm.verify(credentials.credentials)
        except ValueError:
            raise HTTPException(status_code=401, detail="Not authenticated")
    return verify_jwt
```

---

## 14. Known Issues to Fix During Migration

Issues identified during analysis that should be addressed in the recreation:

| # | Issue | Location | Fix |
|---|---|---|---|
| 1 | `can_issue` flag not enforced in `/refresh` | `service.py:323-354` | Add `if not can_issue: raise HTTPException(403)` |
| 2 | Missing `subject` error says "status" instead of "subject" | `service.py:136` | Fix error message text |
| 3 | `load_google_keys` parameter ignored in `ServiceAccountKeyCache` | `target.py:102` | Use `self._load_google_keys = load_google_keys` |
| 4 | Mutable default `payload={}` in `ServiceUser.get_token()` | `client.py:47` | Use `payload=None` with `payload = payload or {}` |
| 5 | `logging.error(..., file=sys.stderr)` invalid parameter | `target.py:123-125` | Remove `file=sys.stderr` from logging calls |
| 6 | Revoke wildcard bug: `if found > 0` should be `>= 0` | `__main__.py:124` | Change to `if found >= 0` |
| 7 | `role remove` crashes if permission not present | `__main__.py:61` | Add check before `list.remove()` |
| 8 | No timeout on HTTP calls in `/refresh` endpoint | `service.py:315,339` | Add `timeout=(5, 30)` |
| 9 | No retry session for HTTP calls in `/refresh` | `service.py:315,339` | Use retry client |
| 10 | `ServiceUser` reads key file on every request | `service.py:261,353` | Cache parsed credentials |
| 11 | Pickle deserialization in `RedisSessionInterface` | `sessions.py:43` | Use JSON serialization if sessions are kept |
| 12 | OIDC nonce generated but never verified | `flask_integration.py:66-67` | Either verify or remove |
| 13 | `ServiceRealm` docstring references nonexistent parameters | `target.py:132-143` | Update docstring |
| 14 | `traceback` imported but unused in `target.py` | `target.py:6` | Remove import |
| 15 | Google refresh called with `params=` instead of `data=` | `service.py:315` | Use `data=` for form-encoded POST |

---

## 15. Recommended Implementation Order

A step-by-step migration order that ensures functionality is verified incrementally:

### Phase 1: Foundation

1. **Create FastAPI app shell with Settings**
   - `Settings` class with all env var bindings
   - Basic app creation with lifespan events
   - Global key cache initialization

2. **Port authentication dependency**
   - `get_current_user` dependency with `ServiceRealm`
   - `get_bearer_token` helper

3. **Port `/claims` endpoint**
   - Simplest endpoint -- validates that auth works end-to-end
   - Test: generate JWT with CLI, call `/claims`, verify response

### Phase 2: Core Endpoints

4. **Port `/key/{kid}` endpoint**
   - Tests key cache functionality
   - Non-JSON response (PEM)

5. **Port `/has` endpoints (both variants)**
   - Port path-based: `/has/{subject}/{target}/{permission:path}`
   - Port query-based: `/has?subject=...&target=...&permission=...`
   - Tests Authority + SecretsStorage chain

### Phase 3: Token Flows

6. **Port `/exchange` endpoint**
   - JWT verification + access token fallback
   - Issuer/audience/domain validation
   - Token signing

7. **Port `/refresh` endpoint**
   - Client secret lookup from Secret Manager
   - Google refresh token exchange
   - UserInfo enrichment
   - Fix `can_issue` bug during port

### Phase 4: Client Library

8. **Create `fastapi_integration.py` in client library**
   - Port `get_bearer_token`, `verify_jwt`
   - Optionally port auth router (OAuth login) if console is needed

9. **Make Flask an optional dependency**
   - Conditional imports in `__init__.py`
   - Update `setup.cfg` extras_require

### Phase 5: Deployment

10. **Update deployment artifacts**
    - Shiv build command (replace gevent with uvicorn)
    - Kubernetes container args (app name + worker class)
    - Add health check endpoint and K8s probes
    - Test full deployment pipeline

---

## 16. Testing Strategy

### FastAPI TestClient

```python
from fastapi.testclient import TestClient
from dockmaster_service import app

client = TestClient(app)

def test_claims_requires_auth():
    response = client.get("/claims")
    assert response.status_code == 401

def test_claims_with_valid_jwt():
    token = generate_test_jwt()
    response = client.get("/claims", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "email" in response.json()
```

### Async Tests

```python
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.anyio
async def test_exchange():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/exchange?service=test",
            headers={"Authorization": f"Bearer {google_jwt}"}
        )
        assert response.status_code == 200
```

### Mocking External Dependencies

```python
from unittest.mock import patch, MagicMock

def test_has_permission(mock_secret_manager):
    """Mock Secret Manager to avoid real API calls in tests."""
    with patch("dockmaster.rbac.SecretsStorage") as MockStorage:
        mock_storage = MockStorage.return_value
        mock_storage.load.return_value = Role("viewer", ["read"])
        # ... test permission check
```

### Test Matrix

| Endpoint | Test Cases |
|---|---|
| `/claims` | No auth (401), valid JWT (200), expired JWT (401) |
| `/key/{kid}` | Valid kid (200 + PEM), unknown kid (404), no auth (401) |
| `/has` (both) | Granted (204), denied (403), missing params (400), no auth (401) |
| `/exchange` | JWT path (200), access token path (200), bad issuer (403), bad domain (403), no token (401) |
| `/refresh` | Valid refresh (200), bad client_id (400), bad refresh token (401), unauthorized domain (should be 403) |
