# Development Approach Guide

This document defines how we implement features in this project. Read it at the start of every
implementation session before touching any code.

---

## Background: Development Approaches

### Test-Driven Development (TDD)

TDD means the test defines the behavior before the implementation exists. The cycle is:

1. **Assess** what tests are needed for the phase (unit, integration, edge cases). Think about what
   real behavior needs to be proven — not just code coverage.
2. **Plan fixtures first.** Before writing any test, think about the lifecycle of dependencies:
   what needs a client, what needs a database, what needs a mock. Define `conftest.py` fixtures
   that cover these. Reuse fixtures from previous phases where they fit. Extend them elegantly
   rather than duplicating. Keep fixtures concise but powerful.
3. **Write RED tests.** Each test should fail initially — but fail for the right reason (the
   behavior isn't implemented yet, not because the test is broken). A RED test that passes
   trivially is not a RED test.
4. **Write code to make tests GREEN.** Implement the minimum code needed to satisfy each test.
   Don't over-implement. The test defines the contract.
5. **Handle imperfect tests.** Planning is imperfect. If a RED test turns out to be wrong — the
   spec was ambiguous, the assumption was bad, the approach changed — surface it explicitly.
   Decide: change the test, skip it, or make the code match it. Log the decision.
6. **Repeat across sessions.** Each session picks up the RED/GREEN log and continues. Progress
   is tracked so context can be rebuilt cheaply at the start of the next session.

**When TDD works best**: pure-logic modules with no external dependencies. The test and the code
are in the same world. Fast feedback, no mocks lying to you.

---

### Tracer Bullet Development

Tracer bullet means proving end-to-end flow first, then hardening the internals.

1. **Build the thinnest working path.** For each phase, build just enough code to make the full
   flow work — input → processing → output — against real dependencies. No stubs, no fakes. Real
   GCP, real tokens, real HTTP. It doesn't have to be clean. It has to work.
2. **Write one integration test.** As you build, write a single end-to-end integration test that
   captures the full flow. This test becomes the **golden source** — "if this passes, the phase
   works." It doesn't test internals. It tests outcomes.
3. **Refine while the integration test stays GREEN.** Once the tracer bullet works, improve the
   implementation: clean up the code, extract modules, add error handling. The integration test
   tells you if you broke anything.
4. **Freeze the internals with unit tests.** As a second pass, add unit and detailed integration
   tests to lock in the internal behavior. By now the code is stable — these tests document and
   protect what's already working rather than discovering it. They should not need to change much.

**When tracer bullet works best**: when the biggest unknown is integration behavior, not design.
When you need to learn how external systems actually respond before you can write good mocks.
When interface design is already settled (from specs) and the question is just "does it work?"

---

## Our Approach: Tracer Bullet + Selective TDD

We use tracer bullet as the primary approach, with TDD for pure-logic modules that have no
external dependencies.

### Why not pure TDD for this project

Interface design is already done — the implementation docs have clear interfaces, data models,
and acceptance criteria. Writing Red tests before code would just transcribe the spec into test
form, which is overhead without payoff.

The bigger risk is "does GCP actually behave like we think it does?" — mocks can't answer that.
We answer it by running against real GCP first and capturing the actual responses as fixtures.
Those real-response fixtures then become the basis for unit test mocks, so the mocks reflect
reality rather than assumptions.

---

### Pass 1 — Tracer Bullet (real GCP)

Goal: prove the end-to-end flow works with real infrastructure.

- Build the thinnest path through the phase that satisfies the acceptance criteria
- Write **one integration test** per phase using FastAPI `TestClient` — this is the golden source
  of "it works end to end"
- Run against **real GCP** (real IAM API, real Secret Manager, real Google OAuth)
- **Capture every GCP/Google API request+response as a fixture file** — see Fixture Capture below
- Tag integration tests `@pytest.mark.integration` — these are skipped in CI by default

Phase gate: integration test is GREEN before moving to Pass 2.

---

### Pass 2 — Freeze Internals (unit tests with captured fixtures)

Goal: lock down the implementation using the real responses we just captured.

- Write unit tests for every module, using captured fixture files as mock data
- Fixtures represent real GCP behavior — not guessed shapes
- Code does NOT change in this pass — tests lock in what's working
- Unit tests must run without any GCP access

---

### Pass 3 — Build Fake Classes

Goal: make the test suite fully self-contained for contributors without GCP access.

- Build `FakeSecretManagerClient`, `FakeIAMClient`, `FakeGoogleOAuth`, etc. using the captured
  fixtures
- Replace raw mock patches with these reusable fake classes
- Document which tests still require real GCP vs which use fakes

---

### TDD for pure-logic modules (use this from Pass 1, no GCP needed)

Some modules have no external dependencies and benefit from Red-Green TDD immediately:

| Module | Why TDD works here |
|---|---|
| `ServiceUser` (JWT signing) | Generate a real RSA key pair in-test |
| `ServiceRealm` (JWT verification) | Sign with test key, verify round-trip |
| `Authority.has_permission()` | Pure Python permission resolution |
| Pydantic models (`Role`, `Grant`, etc.) | Pure validation logic |
| `InMemorySessionStore` | No external deps |

For these modules: write failing test → write minimal code → make it pass → refactor.

---

## Fixture Capture Strategy

For every GCP or Google API call during Pass 1, capture the real HTTP interaction:

```
tests/fixtures/gcp/
  iam/
    list_service_accounts.json    # real IAM list response
    list_keys.json
    get_public_key.json
  secret_manager/
    get_role.json
    put_role.json
    list_secrets.json
  google_oauth/
    tokeninfo.json
    userinfo.json
    token_exchange.json
    token_refresh.json
```

Each file should contain both the request and response:
```json
{
  "request": { "method": "GET", "url": "...", "headers": {}, "body": null },
  "response": { "status": 200, "headers": {}, "body": { ... } }
}
```

Tools:
- `curl -v` piped to file for one-off captures
- `httpx` with a custom logging transport during a dev run
- Later: `pytest-recording` to record cassettes automatically

---

## Step 0 — Orient yourself before every session

1. Read `_blueprint/implementation-progress.md` — this is the canonical session-to-session state
   log. It tells you what phase we're on, what's done, what's in-progress, and any open decisions.
2. Read the implementation doc for the current phase:
   `_blueprint/features/implementation-phase{N}-<name>.md`
   These are the authoritative specs. Do NOT read `_blueprint/features/planning/` — those are
   legacy Flask reference docs and will conflict with the v2 design.
3. Ask the user which specific task within the phase to start on if the progress file is ambiguous.

---

## Session workflow

### At the start of a session

1. Read `_blueprint/implementation-progress.md`
2. Read the current phase implementation doc
3. **Propose a concrete list of sub-tasks to the user before writing any code.** Break the phase
   doc into small, ordered, completable units. Get user sign-off before starting.
4. Start with Pass 1 (tracer bullet) or resume where the progress file says

### During a session

- Implement one sub-task at a time
- Run `uv run pytest` after each sub-task; surface failures immediately
- If a RED test turns out to be wrong, surface it explicitly: "This test is RED but I think the
  test itself is wrong — here's why. Should I change the test, skip it, or make the code match it?"
- Never move to the next phase until the current phase's integration test is GREEN

### At the end of every session

Update `_blueprint/implementation-progress.md` before ending:

```markdown
# Implementation Progress

*Last updated: YYYY-MM-DD*

## Current Phase: Phase N — <name>
**Pass**: 1 (Tracer Bullet) | 2 (Unit Tests) | 3 (Fake Classes)
**Status**: IN PROGRESS | COMPLETE

## Sub-tasks for current session
- [x] Completed sub-task
- [ ] In-progress sub-task  ← where we stopped
- [ ] Not started

## Fixtures captured
- `tests/fixtures/gcp/iam/list_service_accounts.json` ✅
- `tests/fixtures/gcp/iam/get_public_key.json` ❌ not yet

## Test status
- `tests/test_jwt_signer.py` GREEN ✅
- `tests/test_key_cache.py` RED — not started
- `tests/integration/test_phase2.py` RED — WIP

## Open decisions / blockers
- None

## Next session: pick up at
"Implement ServiceAccountKeyCache.update() — GCP IAM key enumeration"
```

---

## Phase order

Phases are strictly sequential. Each phase builds on the previous.

```
Phase 2: JWT Infrastructure        ← start here
Phase 3: Token Exchange
Phase 4: OAuth Login + Session
Phase 5: RBAC
Phase 6: RBAC Management + CLI
```

Implementation docs for each phase:
- `_blueprint/features/implementation-phase2-jwt-infrastructure.md`
- `_blueprint/features/implementation-phase3-token-exchange.md`
- `_blueprint/features/implementation-phase4-oauth-login.md`
- `_blueprint/features/implementation-phase5-rbac.md`
- `_blueprint/features/implementation-phase6-rbac-management.md`

The v2 design specs are in `_blueprint/features/phase{N}-*-v2.md`.
Do not read `_blueprint/features/planning/` — those are legacy reference docs, not the plan we follow.

---

## Project-Specific Guidance

### What this project is

Dockmaster is a FastAPI auth microservice. It handles:
- Service-to-service JWT auth via GCP service account keys
- Browser SSO via Google OAuth2 (authorization code flow)
- RBAC with roles and grants stored in GCP Secret Manager

**Phase 1 is complete.** The scaffold is live: `Settings`, `create_app()`, lifespan, health
endpoint, conftest fixtures, structlog. Every subsequent phase extends this foundation.

---

### Tech stack decisions already made

| Concern | Choice | Notes |
|---|---|---|
| JWT signing/verification | `PyJWT` + `cryptography` | Not `google-auth` — different library, same RS256 wire format |
| HTTP client (async) | `httpx` | Used for all Google API calls |
| Settings | `pydantic-settings` `BaseSettings` | Env vars → Pydantic; comma-separated sets via `model_validator` |
| Logging | `structlog` | Already wired in lifespan |
| CLI | `typer` | Phase 6 only |
| Session signing | `itsdangerous` | Phase 4 |
| OAuth client | `authlib` | Phase 4 |
| Test framework | `pytest` + `pytest-mock` | Always `uv run pytest`, never bare `pytest` |

---

### GCP services used and when

| GCP Service | Used in | What for |
|---|---|---|
| GCP IAM API (`google-api-python-client`) | Phase 2 | Enumerate all SA public keys in the project |
| GCP Secret Manager (`google-cloud-secret-manager`) | Phases 4, 5, 6 | Store OAuth client secrets + RBAC roles/grants |
| Google OAuth2 / OIDC certs | Phase 2 | Fetch Google's public signing keys |
| Google tokeninfo API | Phase 3 | Validate access tokens |
| Google UserInfo API | Phase 4 | Fetch profile claims during token refresh |
| Google OAuth token endpoint | Phase 4 | Code exchange + refresh token exchange |

During **Pass 1 (tracer bullet)** for each phase, run against the real GCP service and capture
its responses. This is the only time you need live GCP access.

---

### Established patterns — follow these exactly

#### Settings (`src/dockmaster/config.py`)
- All config lives in `Settings(BaseSettings)` — env vars or `.env` file
- Comma-separated fields (issuers, domains, audience) are typed `str | set[str]` and parsed to
  `set[str]` in `model_validator(mode="after")` via `_parse_comma_separated()`
- New settings fields follow this same pattern
- Tests override settings via `app.dependency_overrides[get_settings] = lambda: test_settings`
- Never patch `get_settings` directly — always use `dependency_overrides`

#### Lifespan singletons (`src/dockmaster/main.py`)
- Expensive objects (GCP clients, key caches, `ServiceUser`, `Authority`) are created **once** in
  the `lifespan()` context manager and attached to `app.state`
- Example pattern to follow:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
      settings = get_settings()
      app.state.service_user = ServiceUser(settings.issuer)
      app.state.key_cache = ServiceAccountKeyCache(...)
      yield
      # cleanup if needed
  ```
- In tests, the `TestClient` context manager triggers lifespan automatically. If a singleton needs
  overriding in tests, set `app.state.X = FakeX()` before the `with TestClient(app)` block.

#### Adding routes
- Route modules live in `src/dockmaster/routes/`
- Each module defines a `router = APIRouter()` and its handlers
- Routers are registered in `create_app()` with a prefix: `app.include_router(router, prefix="/auth")`
- Follow `src/dockmaster/routes/health.py` as the reference pattern

#### Tests (`tests/conftest.py`)
Three base fixtures already exist — extend from these, don't replace them:
- `test_settings` — `Settings` with safe defaults, no real GCP credentials
- `app` — `FastAPI` wired with `test_settings` via `dependency_overrides`
- `client` — `TestClient` wrapping `app`

For phase-specific fixtures (e.g., RSA key pair, fake SM client), add them to `tests/conftest.py`
if shared across phases, or a phase-local `conftest.py` if isolated.

#### Run commands
```bash
uv run pytest              # all unit tests (fast, no GCP)
uv run pytest -m integration  # integration tests (requires GCP)
just lint                  # ruff check + ty
just format                # ruff format
```

---

### Phase 2 specific: RSA key fixtures

Phase 2 is the first phase. Before writing any test for `ServiceUser` or `ServiceRealm`, generate
a test RSA key pair. This is the foundation for all JWT tests across every phase.

```python
# Suggested conftest.py fixture
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

@pytest.fixture(scope="session")
def rsa_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)

@pytest.fixture(scope="session")
def rsa_private_key_pem(rsa_private_key):
    return rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

@pytest.fixture(scope="session")
def rsa_public_key_pem(rsa_private_key):
    return rsa_private_key.public_key().private_bytes(...)  # PEM SPKI format
```

Store a static version in `tests/fixtures/fake_sa_key.json` — a complete GCP SA JSON structure
with the test private key embedded. This file is used by `ServiceUser` loading tests.

---

### pytest markers

Add to `pyproject.toml` to distinguish test categories:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: requires real GCP credentials (deselect with '-m not integration')",
    "unit: pure unit tests, no external deps",
]
```

Default `uv run pytest` runs everything except `integration`. CI always runs with
`-m "not integration"`.
