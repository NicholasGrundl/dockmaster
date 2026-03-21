# Guide 03: Developer Howto

> Contributing to Dockmaster's codebase. Covers repo layout, running tests, code patterns, and development workflows.

**Audience**: Developers who want to modify or extend Dockmaster.
**Assumes**: Dev environment from [Guide 02](GUIDE-02-consumer-howto.md) is working.

---

## 1. Repo Layout

```
.
├── src/dockmaster/          Application source
│   ├── auth/                JWT signing/verification, OAuth, auth dependencies
│   ├── cli/                 Typer CLI (login, token, role, grant, check)
│   ├── rbac/                RBAC models, storage (Secret Manager), authority
│   ├── routes/              FastAPI route modules (health, login, exchange, admin, etc.)
│   ├── sessions/            SessionStore protocol + in-memory implementation
│   ├── templates/           Jinja2 HTML templates (login, dashboard, admin UI)
│   ├── ui/                  UIConfig loader
│   ├── config.py            Settings (pydantic-settings, env vars / .env)
│   ├── main.py              App factory (create_app), lifespan, middleware setup
│   ├── middleware.py         SecurityHeaders, RequireProxyHeaders middleware
│   ├── logging.py           structlog configuration
│   └── state.py             State type hints
├── tests/                   pytest test suite
│   ├── auth/                JWT, sessions, middleware, token validator tests
│   ├── cli/                 CLI command tests
│   ├── rbac/                RBAC models, storage, authority tests
│   ├── routes/              Endpoint tests (exchange, login, admin, permissions, etc.)
│   ├── ui/                  UI config and template tests
│   ├── fixtures/            Captured GCP responses, fake SA keys, RBAC fixture files
│   └── conftest.py          Shared fixtures (Settings, app, client, RSA keys, realm)
├── docs/                    Guides and learning docs
├── _blueprint/              Planning, specs, roadmap, and reference material
├── justfile                 Development commands (dev, test, check, fix, etc.)
└── pyproject.toml           Project metadata, dependencies, tool config
```

Key points:
- **`src/dockmaster/`** uses a `src/` layout — the package is `dockmaster`
- **`tests/`** mirrors the `src/dockmaster/` structure by domain
- Each test subdirectory has its own `conftest.py` with domain-specific fixtures
- The `_blueprint/` directory is for planning and specs, not runtime code

---

## 2. Development Commands

All commands are run via [just](https://github.com/casey/just). Run `just` with no arguments to see the full list.

> **Rule**: Always use `uv run` to invoke Python. Never use bare `python`, `python3`, or `pytest`. The justfile handles this for you.

### Dev Server

```bash
just dev
# → uv run fastapi dev src/dockmaster/main.py --port 8001
```

Starts uvicorn with `--reload` on port 8001. Hot-reloads on file changes.

### Testing

| Command | What it runs | When to use |
|---------|-------------|-------------|
| `just test-core` | `uv run pytest tests/ -v -m "not integration"` | After any code change — fast, no GCP needed |
| `just test-integration` | `uv run pytest tests/ -v -m "integration"` | When testing real GCP calls (requires credentials) |
| `just test` | `test-core` + `test-integration` | Full suite before a release |

Integration tests are excluded by default via `addopts = "-m 'not integration'"` in `pyproject.toml`. You only run them explicitly with `just test-integration` or `just test`.

### Code Quality

| Command | What it runs | When to use |
|---------|-------------|-------------|
| `just check` | `check-lint` + `check-format` + `check-types` + `test-core` | Pre-commit / CI gate |
| `just check-lint` | `uv run ruff check src/ tests/` | Lint only (read-only) |
| `just check-format` | `uv run ruff format --check src/ tests/` | Format check only |
| `just check-types` | `uv run ty check src/` | Type check (informational, non-blocking) |
| `just fix` | `fix-lint` + `fix-format` | Auto-fix lint + formatting issues |
| `just fix-lint` | `uv run ruff check --fix src/ tests/` | Auto-fix lint |
| `just fix-format` | `uv run ruff format src/ tests/` | Auto-fix formatting |

### Build & Install

| Command | What it does |
|---------|-------------|
| `just install` | `uv sync --extra dev` — install all deps including dev tools |
| `just build` | `uv build --wheel` — build a distributable wheel |

---

## 3. Code Patterns

### 3a. Settings & Configuration

All configuration lives in `Settings(BaseSettings)` in `src/dockmaster/config.py`. Values come from environment variables or a `.env` file.

**Key patterns:**

```python
from dockmaster.config import Settings

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Simple fields — env var name matches field name (case-insensitive)
    log_level: str = "INFO"
    enable_docs: bool = False

    # Comma-separated fields — accept "a,b,c" from env, parse to set[str]
    authorized_domains: CommaSeparatedSet = set()

    # Secret with auto-generation fallback
    session_secret_key: str = Field(default_factory=_generate_session_secret)
```

**`CommaSeparatedSet`** is a custom type (`Annotated[str | set[str], BeforeValidator(...)]`) that parses comma-separated strings like `"example.com,corp.com"` into `{"example.com", "corp.com"}`. Used for `authorized_issuers`, `authorized_domains`, `authorized_audience`, `allowed_redirect_uris`, `allowed_origins`, and `dockmaster_admin_emails`.

**How settings flow through the app:**

1. `create_app(settings)` stores settings on `app.state.settings`
2. Route handlers access settings via the dependency bridge:
   ```python
   from dockmaster.config import Settings, get_settings

   @router.get("/example")
   async def example(settings: Annotated[Settings, Depends(get_settings)]):
       # settings is read from request.app.state.settings
       ...
   ```
3. **Never** import settings directly or use `lru_cache` — always go through `app.state`

**In tests**, pass settings to `create_app(settings)` or set `app.state.settings` directly:

```python
settings = Settings(log_level="DEBUG", authorized_domains={"test.com"})
app = create_app(settings)
```

### 3b. App Factory & Lifespan

The app is created by `create_app(settings)` in `src/dockmaster/main.py`. It accepts an optional `Settings` parameter (falls back to `create_settings()` which reads from env/.env).

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="Dockmaster", lifespan=lifespan, ...)
    application.state.settings = settings
    setup_middleware(application, settings)
    # Register all routers with prefixes
    application.include_router(health_router, prefix="/auth")
    application.include_router(admin_router, prefix="/admin")
    ...
    return application
```

**Lifespan singletons** — the `lifespan()` async context manager runs at startup and creates all expensive objects on `app.state`:

| `app.state.*` | Type | Depends On | Purpose |
|---|---|---|---|
| `signer` | `ServiceAccountSigner` or `None` | `SA_KEY_FILE` | Signs JWTs with the runtime SA private key |
| `token_issuer` | `EphemeralKeypairSigner` | Always created | Signs Type C JWTs with an in-memory RSA keypair |
| `realm` | `ServiceRealm` | Always created | Verifies JWTs (ephemeral + SA key caches) |
| `auth_code_store` | `AuthCodeStore` | Always created | TTL store for auth codes (5 min expiry) |
| `oauth_state_store` | `TTLStore[dict]` | Always created | CSRF state tokens for OAuth login flow |
| `session_store` | `InMemorySessionStore` | Always created | Server-side session storage |
| `oauth` | Authlib OAuth client or `None` | `CLIENT_ID` | Google OAuth client for browser login |
| `secrets_storage` | `SecretsStorage` or `None` | `SECRETS_PROJECT` | Read-only GCP Secret Manager client |
| `authority` | `Authority` or `None` | `SECRETS_PROJECT` | RBAC permission resolution with caching |
| `admin_storage` | `AdminSecretsStorage` or `None` | `ADMIN_SA_KEY_FILE` | Read-write SM client for admin CRUD |
| `ui_config` | `UIConfig` | Optional config file | UI branding/customization |

When a required setting is missing, the corresponding singleton is set to `None` and a warning is logged. Route handlers check for `None` and return 503 if the capability isn't available.

**In tests**, override singletons by setting `app.state.X = FakeX()` before entering the `TestClient` context:

```python
app = create_app(test_settings)
app.state.realm = fake_realm
app.state.signer = signer
with TestClient(app) as client:
    ...
```

### 3c. Route Modules

Each route module lives in `src/dockmaster/routes/` and exports a `router = APIRouter()`. Routers are registered in `create_app()` with a prefix:

```python
# In create_app():
app.include_router(health_router, prefix="/auth")
app.include_router(admin_router, prefix="/admin")
app.include_router(ui_public_router, prefix="/ui")
```

**Current route modules and their prefixes:**

| Module | Prefix | Auth Pattern | Purpose |
|--------|--------|-------------|---------|
| `health.py` | `/auth` | None | Health check, root info |
| `keys.py` | `/auth` | None | Public key retrieval (PEM, JWKS) |
| `login.py` | `/auth` | None / Session | OAuth login, callback, logout |
| `claims.py` | `/auth` | Bearer JWT | Decode and return JWT claims |
| `exchange.py` | `/auth` | Google credential | Exchange Google JWT/token for Type C |
| `token.py` | `/auth` | Session or Bearer | Issue Type C JWTs |
| `permissions.py` | `/auth` | Bearer (Type A) | RBAC permission checks |
| `admin.py` | `/admin` | JWT Admin | Admin CRUD API (roles, grants, sessions) |
| `ui.py` | `/ui` | None / Session | Login page, dashboard |
| `admin_ui.py` | `/ui` | Session Admin | Admin UI pages (roles, grants, sessions) |

**Two auth patterns:**

- **Bearer JWT** — API routes for programmatic access. Use `allow_jwt` or `allow_jwt_admin` as a dependency.
- **Session cookie** — UI routes for browser users. Use `allow_session` or `allow_session_admin` as a dependency.

Routes that accept either (e.g., `/auth/session/token`) use `allow_jwt_or_session`.

### 3d. Middleware Stack

Middleware is configured in `setup_middleware()` in `main.py`. Starlette executes middleware in **reverse-add order** — the last added runs first on the request path.

The add order and resulting execution order:

```
Add order (in setup_middleware):        Request execution order:
1. RequireProxyHeaders (if enabled)     4. RequireProxyHeaders  ← outermost
2. SecurityHeaders (if enabled)         3. SecurityHeaders
3. CORSMiddleware (if origins set)      2. CORSMiddleware
4. SessionMiddleware (always)           1. SessionMiddleware    ← innermost
```

| Middleware | Setting | Default | Purpose |
|---|---|---|---|
| `RequireProxyHeadersMiddleware` | `REQUIRE_PROXY_HEADERS` | `true` | Returns 502 if `X-Forwarded-Proto` is missing. Safety net for production behind a reverse proxy. **Set to `false` for local dev.** |
| `SecurityHeadersMiddleware` | `SECURITY_HEADERS` | `true` | Adds `X-Content-Type-Options`, `X-Frame-Options`, CSP, `Referrer-Policy` to every response. |
| `CORSMiddleware` | `ALLOWED_ORIGINS` | _(empty)_ | Allows cross-origin requests from configured origins. Only added when `ALLOWED_ORIGINS` is non-empty. |
| `SessionMiddleware` | Always on | — | Starlette session cookie for Authlib's OAuth flow. Signed with `SESSION_SECRET_KEY`. Distinct from the application's own `session_id` cookie. |

**Note**: HSTS is intentionally **not** set at the app level — it's handled by the reverse proxy (e.g., Caddy) at the infrastructure layer.

### 3e. Auth Dependencies

Auth enforcement lives in `src/dockmaster/auth/dependencies.py`. It follows a two-layer design:

1. **Utility functions** — pure logic, explicit typed args, no `Depends`, no `app.state`. Testable in isolation.
2. **FastAPI dependencies** — inject via `Depends`, call the utilities. Used in route signatures.

**Gate dependencies** (enforce auth — raise 401/403 on failure):

| Dependency | Returns | Use for |
|---|---|---|
| `allow_jwt` | `dict` (decoded claims) | API routes requiring a valid dockmaster JWT |
| `allow_session` | `dict` (session data) | UI routes requiring a valid session cookie |
| `allow_jwt_or_session` | `str` (email) | Routes accepting either auth method (e.g., `/auth/session/token`) |
| `allow_google_credential` | `GoogleJWTCredential \| GoogleAccessTokenCredential` | Exchange endpoint — verifies Google-issued credentials |
| `allow_jwt_admin` | `dict` (claims) | Admin API — JWT + admin permission check |
| `allow_session_admin` | `dict` (session data) | Admin UI — session + admin permission check |

**System capability checks** (return 503 if infrastructure is missing):

| Dependency | Purpose |
|---|---|
| `needs_admin_storage` | Ensures admin SM client is configured for write operations |
| `needs_session_store` | Ensures session store is available |

**Usage in a route:**

```python
from dockmaster.auth.dependencies import allow_jwt_admin

@router.get("/admin/roles")
async def list_roles(user: Annotated[dict, Depends(allow_jwt_admin)]):
    email = user.get("email", "")
    # user is authenticated and has admin permission
    ...
```

**Composition**: `allow_jwt_admin` wraps `allow_jwt` (validates the JWT first) then checks admin permission via RBAC with an email whitelist fallback. `allow_session_admin` does the same for session-based auth.

---

## 4. Adding a New Endpoint

Step-by-step recipe for adding a new endpoint to Dockmaster.

### Step 1: Understand the Three-Layer Protection Model

Every endpoint in Dockmaster is protected by up to three composable layers. Each layer answers a different question, and they run in order:

```
Request
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Allow  (router-level)                         │
│  "Are you authenticated?"                               │
│  → allow_jwt, allow_session, allow_jwt_or_session, etc. │
│  → 401 if not authenticated                             │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Requires  (per-route)                         │
│  "Do you have permission to do THIS specific action?"   │
│  → RBAC check: authority.has_permission(email, svc, p)  │
│  → 403 if permission denied                             │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Needs  (per-route)                            │
│  "Can the system actually fulfill this request?"        │
│  → needs_admin_storage, needs_session_store              │
│  → 503 if infrastructure not configured                 │
└─────────────────────────────────────────────────────────┘
  │
  ▼
Route handler runs
```

**Layer 1 — Allow** (authentication): Applied at the **router level** so every endpoint in the module gets it automatically. Answers "who is this caller?"

| Gate | When to use | Returns |
|------|------------|---------|
| `allow_jwt` | API endpoint, caller has a dockmaster JWT | `dict` — decoded claims |
| `allow_session` | UI endpoint, caller has a browser session | `dict` — session data |
| `allow_jwt_or_session` | Endpoint used by both browser and CLI/API | `str` — email |
| `allow_google_credential` | Caller presents a Google JWT or access token | Typed credential model |
| _(none)_ | Public endpoint (health, public keys, login page) | — |

**Layer 2 — Requires** (authorization): Applied **per-route** for fine-grained RBAC permission checks. Answers "does this caller have permission to do this specific action?"

This is the mechanism downstream services will use most heavily when consuming Dockmaster. A billing service, for example, would use `allow_jwt` at the router (Layer 1), then check `billing:read` or `billing:write` on individual routes (Layer 2).

Today, Dockmaster collapses Layer 1+2 into composed gates for its own admin access:

```python
# allow_jwt_admin = Layer 1 (allow_jwt) + Layer 2 (check "dockmaster:admin")
async def allow_jwt_admin(...):
    user = ...  # Layer 1: verify JWT
    if not await check_permission(email, "dockmaster", "admin", ...):  # Layer 2
        raise HTTPException(status_code=403)
```

But you could also decompose them for more granular control — e.g., `dockmaster:admin.read` vs `dockmaster:admin.write` on individual routes while sharing the same Layer 1 gate.

**Layer 3 — Needs** (capability): Applied **per-route** for infrastructure availability checks. Answers "even though the caller is allowed, can we actually do this?"

| Check | When to use | Failure |
|-------|------------|---------|
| `needs_admin_storage` | Endpoint writes to Secret Manager | 503 |
| `needs_session_store` | Endpoint reads/writes sessions | 503 |

### Step 2: Decide Where to Apply Each Layer

Each layer has a natural home:

**Router-level** (`dependencies=[...]` on `APIRouter`) — **Layer 1 only**. Every endpoint in the module shares the same authentication gate:

```python
# Layer 1: every endpoint requires a valid dockmaster JWT
router = APIRouter(
    tags=["authenticated"],
    dependencies=[Depends(allow_jwt)],
)
```

**Per-route** (in the function signature or route `dependencies`) — **Layers 2 and 3**. Individual endpoints declare what permissions and capabilities they need:

```python
@router.post("/roles", status_code=201)
async def create_role(
    body: CreateRoleRequest,
    # Layer 3 — capability check: fail 503 if admin_storage is None
    _writes: Annotated[None, Depends(needs_admin_storage)],
    # State bridges — inject typed objects from app.state
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
):
    ...
```

**How existing routes use the layers:**

| Route module | L1: Allow (router) | L2: Requires (per-route) | L3: Needs (per-route) |
|---|---|---|---|
| `health.py` | _(public)_ | — | — |
| `permissions.py` | `allow_jwt` | — | — |
| `token.py` | `allow_jwt_or_session` | — | — |
| `exchange.py` | `allow_google_credential` | — | — |
| `admin.py` | `allow_jwt_admin` (L1+L2 collapsed) | — | `needs_admin_storage`, `needs_session_store` |
| `admin_ui.py` | `allow_session_admin` (L1+L2 collapsed) | — | `needs_admin_storage` |

Notice that `admin.py` and `admin_ui.py` collapse L1+L2 into a single composed gate (`allow_jwt_admin` = `allow_jwt` + `check_permission("dockmaster", "admin")`). This is a convenience for Dockmaster's own admin routes. For more fine-grained control, you would separate them — see the example below.

**Example: separating L1 and L2 for granular admin control**

Instead of one `allow_jwt_admin` gate, you could have `allow_jwt` at the router and explicit RBAC checks per route:

```python
router = APIRouter(
    tags=["admin-api"],
    dependencies=[Depends(allow_jwt)],    # L1: authenticated
)

@router.get("/roles")
async def list_roles(
    claims: Annotated[dict, Depends(allow_jwt)],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
):
    # L2: requires "dockmaster:admin.read"
    email = claims.get("email", "")
    authority = getattr(request.app.state, "authority", None)
    if not await check_permission(email, "dockmaster", "admin.read", authority, settings.dockmaster_admin_emails):
        raise HTTPException(status_code=403, detail="Access denied")
    ...

@router.post("/roles")
async def create_role(
    claims: Annotated[dict, Depends(allow_jwt)],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    _writes: Annotated[None, Depends(needs_admin_storage)],    # L3: capability
):
    # L2: requires "dockmaster:admin.write"
    email = claims.get("email", "")
    authority = getattr(request.app.state, "authority", None)
    if not await check_permission(email, "dockmaster", "admin.write", authority, settings.dockmaster_admin_emails):
        raise HTTPException(status_code=403, detail="Access denied")
    ...
```

This pattern — Layer 1 at the router, Layer 2 per-route — is how downstream services consuming Dockmaster would structure their own auth. A billing service would `allow_jwt` at the router, then check `billing:read`, `billing:write`, `billing:refund`, etc. on individual routes.

### Step 3: Create the Route Module

Putting it together — here's a complete example for a JWT-protected endpoint:

```python
# src/dockmaster/routes/whoami.py
"""Whoami endpoint — returns the authenticated user's identity."""

from typing import Annotated

from fastapi import APIRouter, Depends

from dockmaster.auth.dependencies import allow_jwt

router = APIRouter(
    tags=["authenticated"],
    dependencies=[Depends(allow_jwt)],    # Layer 1: auth gate
)


@router.get("/whoami")
async def whoami(
    claims: Annotated[dict, Depends(allow_jwt)],    # also injects the claims data
):
    """Return the authenticated user's email and subject."""
    return {
        "email": claims.get("email"),
        "sub": claims.get("sub"),
        "iss": claims.get("iss"),
    }
```

And a write endpoint that also needs a capability check:

```python
# src/dockmaster/routes/settings_admin.py
"""Admin settings endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from dockmaster.auth.dependencies import allow_jwt_admin, needs_admin_storage
from dockmaster.rbac.storage import AdminSecretsStorage
from dockmaster.state import get_admin_storage

router = APIRouter(
    tags=["admin-api"],
    dependencies=[Depends(allow_jwt_admin)],          # Layer 1: auth gate
)


@router.post("/config")
async def update_config(
    _writes: Annotated[None, Depends(needs_admin_storage)],      # Layer 2: capability check
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],  # Layer 3: state bridge
):
    ...
```

### Step 4: Register in `create_app()`

In `src/dockmaster/main.py`, import the router and register it with the appropriate prefix:

```python
from dockmaster.routes.whoami import router as whoami_router

# Inside create_app():
application.include_router(whoami_router, prefix="/auth")
```

### Step 5: Write Tests

Create a test file mirroring the route module:

```python
# tests/routes/test_whoami.py

def test_whoami_returns_identity(client, app, fake_realm, signer):
    app.state.realm = fake_realm
    token = signer.sign(subject="alice@example.com", audience="test")
    resp = client.get("/auth/whoami", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@example.com"


def test_whoami_rejects_unauthenticated(client):
    resp = client.get("/auth/whoami")
    assert resp.status_code == 401
```

### Step 6: Verify

```bash
just test-core    # run tests
just check        # lint + format + types + tests
```

---

## 5. Test Patterns

### 5a. Test Organization

Tests mirror the source layout by domain:

```
tests/
├── auth/          JWT, sessions, middleware, token validator
├── cli/           CLI command tests
├── rbac/          RBAC models, storage, authority
├── routes/        Endpoint tests (exchange, login, admin, etc.)
├── ui/            UI config and template tests
├── fixtures/      Captured GCP responses, fake SA keys, RBAC data
│   ├── gcp/       Real GCP API responses (for mocking)
│   └── rbac/      Role and grant fixture files
└── conftest.py    Shared fixtures (inherited by all subdirectories)
```

Each subdirectory has its own `conftest.py` for domain-specific fixtures. These inherit from the root `conftest.py` automatically via pytest's fixture discovery.

### 5b. Shared Fixtures

The root `tests/conftest.py` provides these fixtures to all tests:

**Settings & App:**

| Fixture | Scope | Returns | Use for |
|---------|-------|---------|---------|
| `test_settings` | function | `Settings` with safe defaults | Accessing the default test settings |
| `app` | function | `FastAPI` via `create_app(TEST_SETTINGS)` | Customizing `app.state` before creating a client |
| `client` | function | `TestClient` wrapping `app` | Making HTTP requests in tests |
| `test_app_factory` | function | `Callable[Settings] → TestClient` | Creating a client with custom settings |
| `fixtures_dir` | session | `Path` to `tests/fixtures/` | Loading fixture files (use instead of relative paths) |

**Crypto & Auth:**

| Fixture | Scope | Returns | Use for |
|---------|-------|---------|---------|
| `rsa_private_key` | session | RSA private key object | Low-level crypto tests |
| `rsa_private_key_pem` | session | PEM string | Constructing fake SA keys |
| `rsa_public_key_pem` | session | PEM string | Key cache / verification tests |
| `fake_sa_key_data` | session | `dict` (SA JSON structure) | Building signers and realms |
| `fake_sa_key_path` | session | `Path` to temp SA key file | Tests that need a file path |
| `fake_realm` | function | `ServiceRealm` with test keys | Verifying JWTs in route tests |
| `signer` | function | `ServiceAccountSigner` | Signing test JWTs |
| `valid_token` | function | Signed JWT string | Quick auth header for requests |

**`TEST_SETTINGS`** is a module-level constant with safe defaults: no real GCP credentials, `REQUIRE_PROXY_HEADERS=false`, test OAuth client ID, and a fixed session secret.

### 5c. Mocking Patterns

**Always use `pytest-mock`** (the `mocker` fixture) — never `unittest.mock` directly.

**Override `app.state` singletons** by assigning before the `TestClient` context:

```python
def test_exchange_with_mocked_authority(app, fake_realm, signer, mocker):
    # Wire up the real fake_realm for JWT verification
    app.state.realm = fake_realm

    # Mock the authority for permission checks
    mock_authority = mocker.AsyncMock()
    mock_authority.has_permission.return_value = True
    app.state.authority = mock_authority

    with TestClient(app) as client:
        token = signer.sign(subject="alice@example.com", audience="test")
        resp = client.get("/auth/has/alice@example.com/billing/read",
                         headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 204
```

**Custom Settings for a specific test** — construct explicitly, don't monkeypatch:

```python
def test_docs_enabled(test_app_factory):
    client = test_app_factory(Settings(
        enable_docs=True,
        session_secret_key="test-secret",
        require_proxy_headers=False,
    ))
    resp = client.get("/docs")
    assert resp.status_code == 200
```

### 5d. Integration vs Unit Tests

**Unit tests** (default) — run fast, no external dependencies. Mock GCP clients and use fake SA keys. These run with `just test-core`.

**Integration tests** — hit real GCP services. Mark with `@pytest.mark.integration`:

```python
import pytest

@pytest.mark.integration
def test_real_secret_manager_read(live_settings):
    """Requires real GCP credentials and network access."""
    ...
```

Integration tests are **excluded by default** via `addopts = "-m 'not integration'"` in `pyproject.toml`. Run them explicitly:

```bash
just test-integration   # only integration tests
just test               # all tests (unit + integration)
```

**When to write each type:**

- **Unit tests**: All pure logic, route handlers (with mocked singletons), CLI commands, models, validators
- **Integration tests**: Real GCP Secret Manager reads/writes, real OAuth flows, real IAM key lookups

---

## 6. Linting, Formatting & Type Checking

| Tool | Purpose | Config Location |
|------|---------|----------------|
| **ruff** | Linting + formatting | `[tool.ruff]` in `pyproject.toml` |
| **ty** | Type checking | — |

### Ruff Configuration

Key settings from `pyproject.toml`:

- **Line length**: 120 characters
- **Target**: Python 3.12
- **Quote style**: preserve (don't change existing quotes)
- **Fixable**: all rules — `just fix` can auto-fix most issues
- **Excluded**: `__init__.py` files (allows unused imports for re-exports)

### Workflow

```bash
# Check for issues (read-only)
just check-lint       # ruff lint check
just check-format     # ruff format check
just check-types      # ty type check (informational, non-blocking)

# Auto-fix
just fix-lint         # ruff auto-fix lint issues
just fix-format       # ruff auto-format

# Everything at once
just check            # all checks + core tests
just fix              # all auto-fixes
```

### Type Checking

`ty` is the type checker. It runs via `just check-types` and is currently **informational** — the `|| true` in the justfile means type errors don't fail the build. This lets you see type issues without blocking development.

```bash
uv run ty check src/    # check source code types
```

---

## Appendix A: Security Model

Dockmaster is an auth service — security is the product. This appendix covers the security concerns you need to understand when modifying the codebase.

### A1. The Three-Layer Protection Model

Every endpoint is protected by up to three composable layers. They run in order and answer progressively narrower questions:

```
Request
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Allow  (router-level)                         │
│  "Are you authenticated?"                               │
│  → allow_jwt, allow_session, allow_jwt_or_session       │
│  → 401 if not                                           │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Requires  (per-route)                         │
│  "Do you have permission for THIS action?"              │
│  → RBAC check via authority.has_permission              │
│  → 403 if denied                                        │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Needs  (per-route)                            │
│  "Can the system fulfill this request?"                 │
│  → needs_admin_storage, needs_session_store              │
│  → 503 if not configured                                │
└─────────────────────────────────────────────────────────┘
  │
  ▼
Route handler
```

**Layer 1 (Allow)** is about identity: "I know who you are." Applied at the router level so it's impossible to accidentally leave an endpoint unprotected. Returns 401 on failure.

**Layer 2 (Requires)** is about authorization: "You're authenticated, but do you have the specific RBAC permission this action requires?" Applied per-route because different endpoints in the same router may require different permissions (e.g., `admin.read` vs `admin.write`). Returns 403 on failure.

Today, Dockmaster collapses L1+L2 into composed gates for its own admin access (`allow_jwt_admin` = `allow_jwt` + `check_permission("dockmaster", "admin")`). But the separated pattern is how **downstream services** will consume Dockmaster: `allow_jwt` on the router, then per-route RBAC checks like `billing:read`, `billing:refund`, etc.

**Layer 3 (Needs)** is about capability: "You're allowed, but can we actually do it?" Applied per-route because not every endpoint requires the same infrastructure (read endpoints don't need `needs_admin_storage`). Returns 503 on failure.

### A2. JWT Security

**Signature verification**: All JWTs are verified via `ServiceRealm`, which checks signatures against known public keys from two caches (ephemeral keys + GCP IAM/OIDC keys). Unknown `kid` values are rejected.

**Token types**:
- **Type A** — Google-signed JWTs from service accounts. Verified against Google's public OIDC keys or IAM-published keys.
- **Type C** — Dockmaster-signed JWTs issued via `/auth/service/token` or `/auth/session/token`. Signed with an ephemeral RSA keypair generated at startup.

**Audience validation**: Dockmaster endpoints do **not** validate the `aud` claim on Type C JWTs. Audience validation is the responsibility of downstream services. This is by design — Dockmaster issues tokens scoped to target services, but it's the target service that should verify `aud` matches its own identity.

**Ephemeral keys**: The token issuer generates a new RSA keypair on every startup. This means:
- Type C JWTs cannot be verified after a restart unless the verifier fetches the new public key
- The JWKS registry file persists key history for cross-restart verification
- In production, key rotation is driven by service restarts

### A3. Session Security

**Server-side sessions**: Session data is stored server-side in `InMemorySessionStore`. The browser only holds a signed `session_id` cookie.

**Cookie signing**: The `session_id` cookie value is signed with `itsdangerous.URLSafeSerializer` using `SESSION_SECRET_KEY`. Tampering is detected server-side (signature mismatch → session rejected).

**Two cookies**: Dockmaster sets two cookies:
- `session_id` — the application session (signed, HttpOnly)
- `session` — Starlette's SessionMiddleware cookie (used by Authlib during OAuth flow)

**Session lifetime**: Sessions expire after `SESSION_TTL` seconds (default 3600). The session store enforces expiry — even if the cookie is still valid, an expired server-side session is rejected.

**Auto-generated secrets**: If `SESSION_SECRET_KEY` is not set, a random key is generated at startup. This means sessions don't survive restarts — acceptable for dev, not for production.

### A4. OAuth & CSRF

**State parameter**: The OAuth login flow uses a `TTLStore`-backed state parameter for CSRF protection. A random state token is generated before redirecting to Google, stored server-side with a TTL, and verified on callback. Replay or forged callbacks are rejected.

**Redirect URI validation**: The `redirect_uri` parameter on `/auth/login` is validated against `ALLOWED_REDIRECT_URIS`. Unrecognized URIs are rejected with 400, preventing open redirect attacks.

**Login ticket single-use**: Login ticket codes issued by `/auth/login/callback` are stored in `OAuthFlowStore` (TTL-based, 5 min expiry). Each code can only be exchanged once — replay attempts return 400.

### A5. Domain & Issuer Allowlists

**Authorized domains**: The `AUTHORIZED_DOMAINS` setting restricts which email domains can authenticate. During token exchange, the caller's email domain is checked against this allowlist. Unrecognized domains are rejected with 403.

**Authorized issuers**: The `AUTHORIZED_ISSUERS` setting restricts which JWT issuers are trusted for Google credential verification. Only JWTs from listed issuers (e.g., `https://accounts.google.com`) are accepted.

**Authorized audience**: The `AUTHORIZED_AUDIENCE` setting restricts which JWT audience values are accepted during Google credential verification.

### A6. Response Hardening

**Security headers** (via `SecurityHeadersMiddleware`):
- `X-Content-Type-Options: nosniff` — prevents MIME-type sniffing
- `X-Frame-Options: DENY` — prevents clickjacking via iframes
- `Content-Security-Policy` — restricts script/style/image sources
- `Referrer-Policy: strict-origin-when-cross-origin` — limits URL leakage in referrer headers

**CORS**: Only origins listed in `ALLOWED_ORIGINS` can make cross-origin requests. The allowlist is empty by default (no cross-origin access).

**Proxy header enforcement**: In production (`REQUIRE_PROXY_HEADERS=true`), requests without `X-Forwarded-Proto` are rejected with 502. This catches misconfigured reverse proxies that would break OAuth callbacks and secure cookie handling.

### A7. Security Checklist for New Endpoints

When adding a new endpoint, walk the three layers:

**Layer 1 — Allow:**
- [ ] Is there a router-level `dependencies=[Depends(allow_*)]`?
- [ ] If the endpoint is intentionally public (no auth), is that documented in the module docstring?

**Layer 2 — Requires:**
- [ ] If the endpoint performs a privileged action, does it check RBAC permissions per-route?
- [ ] If the endpoint issues tokens or grants access based on email, is the email domain validated against `AUTHORIZED_DOMAINS`?

**Layer 3 — Needs:**
- [ ] If the endpoint reads/writes to Secret Manager, does it declare `needs_admin_storage`?
- [ ] If the endpoint accesses sessions, does it declare `needs_session_store`?

**General:**
- [ ] **No secrets in responses** — don't leak SA keys, session secrets, or internal error details to callers
- [ ] **Input validation** — path/query params from untrusted callers should be validated before use in GCP API calls or string formatting
- [ ] **Logging** — log auth failures with enough context to investigate (but never log tokens or secrets — use token fingerprints instead)
