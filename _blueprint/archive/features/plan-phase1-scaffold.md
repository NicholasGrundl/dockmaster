# Phase 1: Configuration + Health + App Skeleton

## Context

Dockmaster is being rebuilt as a FastAPI auth microservice from scratch. The repo has an empty `src/dockmaster/` package (just `__init__.py` with v0.1.0) and empty test scaffolding. Phase 1 establishes the foundation: config loading, app creation, health endpoint, logging, and test infrastructure. Every subsequent phase builds on this skeleton.

## Decisions (from 6 rounds of Q&A)

| Decision | Choice |
|---|---|
| Phase 1 scope | Config + health + app skeleton only |
| Config model | Single `Settings` class with pydantic-settings |
| URL structure | `/auth/*` for API, `/admin/*` for dashboard (later), `/` for service info |
| Logging | structlog (new dependency — stdlib-compatible, JSON prod, pretty dev) |
| UI framework | Jinja2+HTMX for Phase 2 test UI, evaluate FastHTML+MonsterUI later |
| Test strategy | Unit tests + mock infrastructure scaffold, `tests/fixtures/` with JSON files |
| .env pattern | `.env.example` in repo |
| GCP guides | Per-phase, code first then guide, `docs/GUIDE-*.md` format |
| Dev mode | Real SA key for dev; tests use mocked fixtures |
| Justfile | Verify/update recipes for new structure |

---

## File Structure

```
src/dockmaster/
    __init__.py          # EXISTING — no changes needed
    config.py            # NEW — pydantic-settings Settings model
    main.py              # NEW — FastAPI app, lifespan, router mounting
    logging.py           # NEW — structlog configuration
    routes/
        __init__.py      # NEW — empty package init
        health.py        # NEW — /auth/health and / endpoints

tests/
    __init__.py          # EXISTING — no changes
    conftest.py          # MODIFY — add fixtures (test_settings, app, client)
    test_config.py       # NEW — config loading and validation tests
    test_health.py       # NEW — health + root endpoint tests
    fixtures/            # NEW — directory for JSON fixture files
        .gitkeep         # placeholder so directory is tracked

.env.example             # NEW — documented env var template
```

---

## Implementation Details

### 1. `src/dockmaster/config.py` — Settings Model

Single `Settings` class using pydantic-settings `BaseSettings`.

**Fields:**

```
# Service
issuer: str | None = None                    # ISSUER — path to GCP SA JSON key
secrets_project: str | None = None           # SECRETS_PROJECT
log_level: str = "INFO"                      # LOG_LEVEL

# Authorization (comma-separated env vars → set[str])
authorized_issuers: set[str] = set()         # AUTHORIZED_ISSUERS
authorized_domains: set[str] = set()         # AUTHORIZED_DOMAINS
authorized_audience: set[str] = set()        # AUTHORIZED_AUDIENCE

# OAuth
client_id: str | None = None                 # CLIENT_ID
client_secret: SecretStr | None = None       # CLIENT_SECRET
default_client_id: str | None = None         # DEFAULT_CLIENT_ID
client_id_suffix: str = ".apps.googleusercontent.com"

# Google Endpoints (with defaults)
access_token_endpoint: str = "https://www.googleapis.com/oauth2/v1/tokeninfo"
refresh_token_endpoint: str = "https://www.googleapis.com/oauth2/v4/token"
userinfo_endpoint: str = "https://www.googleapis.com/oauth2/v3/userinfo"

# Session
redis_url: str | None = None                 # REDIS_URL
session_secret_key: str = "change-me-in-production"
```

**Key implementation details:**
- `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`
- `@field_validator("authorized_issuers", "authorized_domains", "authorized_audience", mode="before")` to parse comma-separated strings into sets, handling str/set/list/None
- `@field_validator("log_level", mode="before")` to normalize to uppercase
- `SecretStr` for `client_secret` to prevent accidental logging
- Module-level `get_settings()` with `@lru_cache` for singleton pattern — tests override via `app.dependency_overrides[get_settings]`

### 2. `src/dockmaster/logging.py` — structlog Setup

**New dependency: `structlog`** (must add to pyproject.toml dependencies)

```python
def setup_logging(log_level: str = "INFO") -> None:
```

- Configure structlog with stdlib logging integration
- Dev mode: colored, human-readable console output (ConsoleRenderer)
- Prod mode: JSON output (JSONRenderer) — detect via `LOG_LEVEL != "DEBUG"` or a separate flag
- Intercept uvicorn and httpx loggers to route through structlog
- Use `structlog.stdlib.ProcessorChain` for timestamp, log level, logger name

### 3. `src/dockmaster/main.py` — App Creation

**Pattern:** `create_app()` function called at module level to produce `app`.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: configure logging, log startup message
    settings = get_settings()
    setup_logging(settings.log_level)
    log = structlog.get_logger("dockmaster")
    log.info("starting up", log_level=settings.log_level)
    yield
    # Shutdown: log shutdown
    log.info("shutting down")

def create_app() -> FastAPI:
    application = FastAPI(
        title="Dockmaster",
        version="0.1.0",
        description="Auth microservice for fine-grained RBAC via Google services",
        lifespan=lifespan,
    )
    application.include_router(health_router, prefix="/auth")
    application.add_api_route("/", root_info, methods=["GET"])
    return application

app = create_app()
```

- `just dev` runs `uv run fastapi dev src/dockmaster/main.py --port 8001` — works with module-level `app`
- Dockerfile uses `dockmaster.main:app`
- Tests use `create_app()` or import `app` directly

### 4. `src/dockmaster/routes/health.py` — Endpoints

**Two endpoints:**

`GET /auth/health` — Health check
```json
{"service": "dockmaster", "status": "ok"}
```
- Response model: `HealthResponse(BaseModel)` with `service: str = "dockmaster"`, `status: str = "ok"`
- No auth required

`GET /` — Root service info
```json
{
  "service": "dockmaster",
  "version": "0.1.0",
  "health": "/auth/health",
  "docs": "/docs"
}
```
- Response model: `ServiceInfo(BaseModel)`
- Reads version from `dockmaster.__version__`

### 5. `tests/conftest.py` — Test Fixtures

```python
@pytest.fixture
def test_settings() -> Settings:
    """Settings with safe test defaults — no real GCP credentials."""
    return Settings(
        log_level="DEBUG",
        authorized_issuers={"https://accounts.google.com"},
        authorized_domains={"example.com"},
        authorized_audience={"test-audience"},
        client_id="test-client-id",
        client_secret="test-client-secret",
        session_secret_key="test-secret-key",
    )

@pytest.fixture
def app(test_settings) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: test_settings
    return application

@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as c:
        yield c
```

### 6. `tests/test_config.py` — Config Tests

1. `test_defaults` — construct Settings() with no env, verify all defaults
2. `test_comma_separated_parsing` — AUTHORIZED_ISSUERS="a,b,c" → {"a","b","c"}
3. `test_comma_separated_with_whitespace` — " a , b " → {"a","b"}
4. `test_comma_separated_empty_string` — "" → set()
5. `test_comma_separated_none` — omit var → set()
6. `test_log_level_normalized` — "debug" → "DEBUG"
7. `test_client_secret_is_secret_str` — value not in str(settings.client_secret)
8. `test_get_settings_caching` — two calls return same object

Use `monkeypatch.setenv`/`monkeypatch.delenv` for env var tests. Construct Settings directly (with keyword args) for unit tests.

### 7. `tests/test_health.py` — Endpoint Tests

1. `test_health_returns_200` — GET /auth/health → 200
2. `test_health_response_body` — response JSON matches expected schema
3. `test_root_returns_service_info` — GET / → 200 with service, version, health, docs
4. `test_openapi_available` — GET /openapi.json → 200

### 8. `.env.example`

```env
# === Dockmaster Configuration ===

# --- Service ---
# ISSUER=/path/to/service-account-key.json
# SECRETS_PROJECT=your-gcp-project-id
LOG_LEVEL=INFO

# --- Authorization (comma-separated) ---
# AUTHORIZED_ISSUERS=https://accounts.google.com
# AUTHORIZED_DOMAINS=yourdomain.com
# AUTHORIZED_AUDIENCE=your-client-id.apps.googleusercontent.com

# --- OAuth ---
# CLIENT_ID=your-client-id.apps.googleusercontent.com
# CLIENT_SECRET=your-client-secret
# DEFAULT_CLIENT_ID=

# --- Session ---
# REDIS_URL=redis://localhost:6379
SESSION_SECRET_KEY=change-me-in-production
```

### 9. Justfile Updates

Verify these recipes work with the new structure:
- `just dev` — already points to `src/dockmaster/main.py`, should work as-is
- `just test` — already runs `uv run pytest tests/ -v`, should work as-is
- `just lint` / `just format` — already target `src/` and `tests/`, should work
- No changes expected, but verify after implementation

### 10. pyproject.toml Update

Add `structlog` to dependencies:
```toml
dependencies = [
    ...existing...,
    "structlog>=24.0",
]
```

Then run `uv sync --extra dev` to update lockfile.

---

## TDD Order (Red-Green Cycles)

1. **Config defaults** — Write `test_defaults`, create `config.py` with Settings class
2. **Comma-separated validators** — Write parsing tests, add `@field_validator`
3. **Log level + SecretStr** — Write validation tests, add validators
4. **get_settings caching** — Write caching test, add `@lru_cache` function
5. **Health endpoint** — Write `test_health_*`, create `logging.py`, `routes/health.py`, `main.py`
6. **Root info endpoint** — Write `test_root_*`, add root route to `main.py`
7. **Smoke test** — `just dev`, curl /auth/health and /, check /docs loads

---

## Verification

1. `uv run pytest tests/ -v` — all tests pass
2. `just dev` — server starts on port 8001
3. `curl http://localhost:8001/auth/health` → `{"service":"dockmaster","status":"ok"}`
4. `curl http://localhost:8001/` → service info with version and links
5. Browser: `http://localhost:8001/docs` → Swagger UI loads with /auth/health documented
6. `just lint` and `just format` — no issues
7. `just check` — full suite passes

---

## What Comes Next (Not In Scope)

- **Phase 1 follow-up**: `docs/GUIDE-gcp-project-setup.md` — GCP project + SA key setup guide with educational callouts
- **Phase 2**: Google OAuth2 login flow, session interface, Authlib integration, Jinja2+HTMX test UI
- **Phase 3**: Token exchange (/exchange, /refresh), JWT signing with ServiceUser
- **Future**: FastHTML+MonsterUI admin dashboard evaluation, RBAC endpoints
