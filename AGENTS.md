# AGENTS.md

## Project Overview

Dockmaster is an auth microservice that provides fine-grained RBAC control via Google services.

Includes:
- Browser-based SSO login via OAuth code flow
- Service-to-service auth via JWT exchange
- Session and token based auth
- CLI for admin operations

## Where to Start

1. `_blueprint/roadmap/ROADMAP.md` — master task list, phase statuses, what to work on
2. `_blueprint/AGENTS.md` — how the blueprint directory is organized
3. `_blueprint/roadmap/implementation-progress.md` — session-to-session implementation state

## Repository Layout

```
.
├── _blueprint/         Planning, specs, and reference material
│   ├── roadmap/        ROADMAP, backlog, decisions
│   ├── features/       Active specs + planning/ subfolder
│   ├── archive/        Completed/superseded specs ([completed] or [discarded] prefix)
│   ├── context/        Reference docs by topic
│   ├── prompts/        Session prompt templates
│   ├── memory/         Agent memory (MEMORY.md index)
│   └── skills/         Custom skills
├── src/dockmaster/     Application source
│   ├── auth/           JWT, OAuth, admin auth dependencies
│   ├── cli/            Typer CLI (login, role, grant, check commands)
│   ├── rbac/           Models, storage, authority, admin_ops
│   ├── routes/         FastAPI route modules
│   ├── sessions/       SessionStore protocol + in-memory impl
│   ├── templates/      Jinja2 HTML templates
│   ├── ui/             UIConfig
│   ├── config.py       Settings (pydantic-settings)
│   └── main.py         App factory + lifespan
├── tests/              pytest test suite
│   ├── fixtures/       GCP + RBAC fixture files
│   └── conftest.py     Shared test fixtures
└── docs/               Guides (GCP setup, CLI E2E, etc.)
```

## Conventions

- **Documentation**: Markdown everywhere. Feature specs in `_blueprint/features/`.
- **Planning**: Start high level and ask user many questions to find blindspots. Save planning docs to `_blueprint/features/planning/`.

## Python & uv

- Always invoke Python through `uv run`. This applies to everything:
  `uv run python`, `uv run pytest`, `uv run <script>`. Never use bare `python`,
  `python3`, or `pytest`.
- Always use `ruff` and `ty` for formatting, linting, and type checking.
- When sensible prefer `pydantic` to `dataclasses` for JSON-like objects. Pydantic gives us validation and serialization out the box.

## Testing

- **Framework**: pytest. Use pytest-family packages (e.g. `pytest-mock`) instead of `unittest` equivalents.
- **Approach**: Tracer bullet + selective TDD. Use tracer bullet (e.g. real GCP or service calls with curl, then capture request/response via jq and piping to fixtures) for integration-heavy modules. Use Red-Green TDD for pure-logic modules with no external dependencies.
- **Fixtures**: Always start test writing by considering lifecycles and fixtures. Always use conftest and pytest ecosystem patterns. Capture real responses as fixture files during Pass 1.
- **When to run**: Run existing tests after code changes. If a package has no tests, surface this and ask whether tests should be added.
- **When to write**: Suggest tests for new functionality but wait for approval before writing them.
- **Scope**: Run relevant tests first. If they pass, run the full suite to catch regressions.
- **Invocation**: Always `uv run pytest` (never bare `pytest`).
- **Markers**: Use `@pytest.mark.integration` for tests requiring real external services. Default `uv run pytest` runs everything except integration tests.

## Git

- Use conventional commit format (`feat:`, `fix:`, `chore:`, etc.).
- Do NOT add `Co-Authored-By: Claude` to commit messages.
- Do NOT make commits unless explicitly instructed. Instead, suggest when a commit makes sense and provide the commit message for the user to run.
- Always ask before pushing, creating PRs, or any action visible to others.
- User stages with `git add .` (not surgical staging).
- Always start with a descriptive commit subject line. Then a 3-4 sentence paragraph summarizing the commit content and motivation.
- After the paragraph put a bulleted list of the key items, files, etc that were completed.

## Dependencies

- Ask before adding any new dependency to a package.
- Updating existing dependencies to compatible versions is fine without asking.

## Design Philosophy

- Prefer idempotent tooling with clear error messages over silent failures.

## Established Patterns

### Settings (`src/dockmaster/config.py`)

- All config lives in `Settings(BaseSettings)` — env vars or `.env` file.
- Comma-separated fields are typed `str | set[str]` and parsed to `set[str]` in `model_validator(mode="after")` via `_parse_comma_separated()`.
- Settings are stored on `app.state.settings` at app creation time. Route handlers read `request.app.state.settings`.
- `create_app(settings=None)` accepts an optional `Settings` parameter (falls back to `get_settings()` if not provided).
- Never use `Depends(get_settings)` in route handlers — always read from `app.state.settings`.
- In tests, pass settings to `create_app(settings)` or set `app.state.settings = Settings(...)` directly.

### Lifespan singletons (`src/dockmaster/main.py`)

- Expensive objects (GCP clients, key caches, `ServiceUser`, `Authority`) are created once in the `lifespan()` context manager and attached to `app.state`.
- Settings are also on `app.state.settings` — lifespan reads from there (not `get_settings()`).
- In tests, if a singleton needs overriding, set `app.state.X = FakeX()` before the `with TestClient(app)` block.

### Routes

- Route modules live in `src/dockmaster/routes/`, each with `router = APIRouter()`.
- Registered in `create_app()` with a prefix: `app.include_router(router, prefix="/auth")`.
- Two auth patterns: JWT/Bearer for API routes, session/cookie for UI routes.

### Test fixtures

Tests are organized by domain: `tests/auth/`, `tests/cli/`, `tests/rbac/`, `tests/routes/`, `tests/ui/`.

Root `tests/conftest.py` provides shared fixtures — extend, don't replace:

- `fixtures_dir` — `Path` to `tests/fixtures/` (use instead of relative paths)
- `test_settings` — `Settings` with safe defaults, no real GCP credentials
- `test_app_factory` — callable that accepts optional `Settings`, returns `TestClient`
- `app` — `FastAPI` created via `create_app(TEST_SETTINGS)`
- `client` — `TestClient` wrapping `app`

Domain-specific fixtures go in `tests/<domain>/conftest.py`. Each domain conftest has a header documenting what it provides and what it inherits.

Always use `pytest-mock` (`mocker` fixture) for mocking — not `unittest.mock` directly.

### Run commands

```bash
just test-core                    # unit tests (fast, no GCP)
just test-integration             # integration tests (requires GCP)
just test                         # all tests
just check                        # lint + format + types + core tests
just fix                          # auto-fix lint + format
```

## Tech Stack

| Concern | Choice | Notes |
|---|---|---|
| JWT signing/verification | `PyJWT` + `cryptography` | Not `google-auth` |
| HTTP client (async) | `httpx` | All Google API calls |
| Settings | `pydantic-settings` `BaseSettings` | Env vars → Pydantic |
| Logging | `structlog` | Wired in lifespan |
| CLI | `typer` | With `platformdirs` for token storage |
| Session signing | `itsdangerous` | Via Starlette SessionMiddleware |
| OAuth client | `authlib` | Google OAuth2/OIDC |
| Templates | `jinja2` + Tailwind CSS (CDN) | Admin UI |
| Test framework | `pytest` + `pytest-mock` | Always `uv run pytest` |
