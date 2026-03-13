# Development Approach Guide

This document defines how you implement features in this project. Read it at the start of every
session before touching any code.

---

## Step 0 — Orient Yourself (every session, no exceptions)

1. Read `_blueprint/implementation-progress.md` — the canonical session-to-session state log. It tells you what phase we're on what's done, what's in-progress, and any open decisions.
2. Read the implementation doc for the current phase: `_blueprint/features/implementation-phase{N}-<name>.md`
These are the authoritative specs. Do NOT read `_blueprint/features/planning/` — those are legacy Flask reference docs and will conflict with the v2 design.

3. Determine which situation you're in:

**A) The progress file has incomplete sub-tasks for the current phase.**
Pick up where the last session left off. Confirm with the user: "The progress file shows sub-task X is next — should I continue from there?" Then go to Step 2.

**B) A phase is complete, or sub-tasks haven't been written yet for the current phase.**
Go to Step 1 to plan and populate sub-tasks.

**C) The progress file is ambiguous.** 
Ask the user before proceeding.

<note>
If you need to do some deeper exploration of the source code to verify the state attempt to do so with the `smart tree` skill
- if `smart tree` skil is not available try to explore using the `tree` command line bash tool (if you are unfamiliar run its `tree --help` command first)
- if the `tree` package is unavailable or uninstalled, use the `find` bash function with its advanced args to listing dirs only, certain files only, etc.
- the goal is to use concise file tree like outputs to rapidly gist the source code, whats in it, etc. assuming our filenames are sensible.
</note>
---

## Step 1 — Plan the Session (new phase or empty task list)

1. Based on the phase implementation doc, break the phase into concrete, ordered sub-tasks.
2. **Propose the sub-task list to the user before writing any code.** Get sign-off.
3. Once approved, **write the sub-tasks into `_blueprint/implementation-progress.md`** immediately
   so they persist even if the session ends early.
4. For each sub-task, decide the development approach:

| Situation | Approach |
|---|---|
| Module touches external services (GCP, Google APIs, HTTP) | **Tracer Bullet** |
| Pure logic, no external dependencies | **TDD (Red / Green / Refactor)** |

Some examples of modules that qualify for immediate TDD (no external deps needed):

| Module | Why |
|---|---|
| `ServiceUser` (JWT signing) | Generate RSA key pair in-test |
| `ServiceRealm` (JWT verification) | Sign with test key, verify round-trip |
| `Authority.has_permission()` | Pure Python permission resolution |
| Pydantic models (`Role`, `Grant`, etc.) | Pure validation logic |
| `InMemorySessionStore` | No external deps |

See the Reference: Development Approaches section at the bottom for full definitions of each
approach.

---

## Step 2 — Implement

### Tracer Bullet modules: three passes

**Pass 1 — Prove end-to-end (real GCP)**

- Build the thinnest path through the sub-task that satisfies the acceptance criteria.
- Write **one integration test** per phase using FastAPI `TestClient` — the golden source of
  "it works end to end."
- Run against real GCP (real IAM API, real Secret Manager, real Google OAuth).
- **Capture every GCP/Google API request+response as a fixture file** immediately after the call succeeds — don't defer this. See Fixture Capture Strategy below.
- Tag integration tests `@pytest.mark.integration`.
- **Phase gate**: integration test is GREEN before moving to Pass 2.

**Pass 2 — Freeze internals (unit tests with captured fixtures)**

- Write unit tests for every module, using the captured fixture files as mock data.
- Fixtures represent real GCP behavior — not guessed shapes.
- Code does NOT change in this pass — tests lock in what's working.
- Unit tests must run without any GCP access.

**Pass 3 — Build fake classes**

- Build `FakeSecretManagerClient`, `FakeIAMClient`, `FakeGoogleOAuth`, etc. using the captured
  fixtures.
- Replace raw mock patches with these reusable fake classes.
- Document which tests still require real GCP vs which use fakes.

### TDD modules: standard cycle

1. Write a failing test (RED) — it must fail because the behavior isn't implemented, not because
   the test is broken.
2. Write the minimum code to make it GREEN.
3. Refactor while GREEN.
4. Repeat.

### During implementation (both approaches)

- Implement one sub-task at a time.
- Run `uv run pytest` after each sub-task; surface failures immediately.
- **When a test fails unexpectedly**: diagnose whether the test or the code is wrong. Tell the
  user: "This test is RED but I think [the test / the code] is wrong — here's why." Then ask
  whether to fix the test, skip it, or adjust the code.
- **When a sub-task reveals that a future sub-task's interface needs to change**: stop, surface it
  to the user, and get a decision before continuing. Don't silently adjust.
- Never move to the next phase until the current phase's integration test is GREEN.

---

## Step 3 — Close the Session

Update `_blueprint/implementation-progress.md` before ending. Use this format:

```markdown
# Implementation Progress

*Last updated: YYYY-MM-DD*

## Current Phase: Phase N — <name>
**Pass**: 1 (Tracer Bullet) | 2 (Unit Tests) | 3 (Fake Classes)
**Status**: IN PROGRESS | COMPLETE

## Sub-tasks
- [x] Completed sub-task
- [ ] In-progress sub-task  <- where we stopped
- [ ] Not started

## Fixtures captured
- `tests/fixtures/gcp/iam/list_service_accounts.json` done
- `tests/fixtures/gcp/iam/get_public_key.json` not yet

## Test status
- `tests/test_jwt_signer.py` GREEN
- `tests/test_key_cache.py` RED — not started
- `tests/integration/test_phase2.py` RED — WIP

## Decisions log
- YYYY-MM-DD: <decision made and why>

## Open decisions / blockers
- None

## Next session: pick up at
"<specific sub-task description>"
```

---

## Fixture Capture Strategy

For every GCP or Google API call during Pass 1, capture the real HTTP interaction immediately
after it succeeds.

```
tests/fixtures/gcp/
  iam/
    list_service_accounts.json
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

Each file contains both request and response:

```json
{
  "request": { "method": "GET", "url": "...", "headers": {}, "body": null },
  "response": { "status": 200, "headers": {}, "body": { ... } }
}
```

These captured fixtures become the mock data for Pass 2 unit tests and the backing data for
Pass 3 fake classes. Mocks built from real responses don't lie.

---

## Phase Order

Phases are strictly sequential. Each builds on the previous.

```
Phase 2: JWT Infrastructure        <- start here
Phase 3: Token Exchange
Phase 4: OAuth Login + Session
Phase 5: RBAC
Phase 6: RBAC Management + CLI
```

Implementation docs:
- `_blueprint/features/implementation-phase2-jwt-infrastructure.md`
- `_blueprint/features/implementation-phase3-token-exchange.md`
- `_blueprint/features/implementation-phase4-oauth-login.md`
- `_blueprint/features/implementation-phase5-rbac.md`
- `_blueprint/features/implementation-phase6-rbac-management.md`

Design specs: `_blueprint/features/phase{N}-*-v2.md`

---

## Established Patterns — Follow Exactly

### Settings (`src/dockmaster/config.py`)

- All config lives in `Settings(BaseSettings)` — env vars or `.env` file.
- Comma-separated fields are typed `str | set[str]` and parsed to `set[str]` in
  `model_validator(mode="after")` via `_parse_comma_separated()`.
- Tests override settings via `app.dependency_overrides[get_settings] = lambda: test_settings`.
  Never patch `get_settings` directly.

### Lifespan singletons (`src/dockmaster/main.py`)

- Expensive objects (GCP clients, key caches, `ServiceUser`, `Authority`) are created once in the
  `lifespan()` context manager and attached to `app.state`.
- In tests, if a singleton needs overriding, set `app.state.X = FakeX()` before the
  `with TestClient(app)` block.

### Routes

- Route modules live in `src/dockmaster/routes/`, each with `router = APIRouter()`.
- Registered in `create_app()` with a prefix: `app.include_router(router, prefix="/auth")`.
- Follow `src/dockmaster/routes/health.py` as the reference pattern.

### Test fixtures (`tests/conftest.py`)

Three base fixtures exist — extend, don't replace:

- `test_settings` — `Settings` with safe defaults, no real GCP credentials
- `app` — `FastAPI` wired with `test_settings` via `dependency_overrides`
- `client` — `TestClient` wrapping `app`

Phase-specific fixtures go in `tests/conftest.py` if shared, or a phase-local `conftest.py` if
isolated.

### RSA key fixtures (foundation for all JWT tests)

```python
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
```

A static version lives in `tests/fixtures/fake_sa_key.json` — a complete GCP SA JSON structure
with the test private key embedded.

### pytest markers

```toml
[tool.pytest.ini_options]
markers = [
    "integration: requires real GCP credentials (deselect with '-m not integration')",
    "unit: pure unit tests, no external deps",
]
```

### Run commands

```bash
uv run pytest                     # all unit tests (fast, no GCP)
uv run pytest -m integration      # integration tests (requires GCP)
just lint                         # ruff check + ty
just format                       # ruff format
```

---

## Tech Stack (decisions already made)

| Concern | Choice | Notes |
|---|---|---|
| JWT signing/verification | `PyJWT` + `cryptography` | Not `google-auth` |
| HTTP client (async) | `httpx` | All Google API calls |
| Settings | `pydantic-settings` `BaseSettings` | Env vars -> Pydantic |
| Logging | `structlog` | Already wired in lifespan |
| CLI | `typer` | Phase 6 only |
| Session signing | `itsdangerous` | Phase 4 |
| OAuth client | `authlib` | Phase 4 |
| Test framework | `pytest` + `pytest-mock` | Always `uv run pytest` |

### GCP services by phase

| GCP Service | Phase | Purpose |
|---|---|---|
| GCP IAM API (`google-api-python-client`) | 2 | Enumerate SA public keys |
| GCP Secret Manager (`google-cloud-secret-manager`) | 4, 5, 6 | OAuth secrets + RBAC storage |
| Google OAuth2 / OIDC certs | 2 | Google's public signing keys |
| Google tokeninfo API | 3 | Validate access tokens |
| Google UserInfo API | 4 | Profile claims during refresh |
| Google OAuth token endpoint | 4 | Code exchange + refresh |

---

<reference_content>

## Reference: Development Approaches

These definitions are included for completeness. The operational instructions above tell you
*when* to use each approach — this section defines *what* each approach means in full detail.

### Test-Driven Development (TDD)

TDD means the test defines the behavior before the implementation exists. The cycle is:

1. **Assess** what tests are needed (unit, integration, edge cases). Think about what real
   behavior needs to be proven — not just code coverage.
2. **Plan fixtures first.** Before writing any test, think about the lifecycle of dependencies:
   what needs a client, what needs a database, what needs a mock. Define `conftest.py` fixtures
   that cover these. Reuse fixtures from previous phases where they fit. Extend elegantly rather
   than duplicating. Keep fixtures concise but powerful.
3. **Write RED tests.** Each test should fail initially — but fail for the right reason (the
   behavior isn't implemented yet, not because the test is broken). A RED test that passes
   trivially is not a RED test.
4. **Write code to make tests GREEN.** Implement the minimum code needed to satisfy each test.
   Don't over-implement. The test defines the contract.
5. **Handle imperfect tests.** If a RED test turns out to be wrong — the spec was ambiguous, the
   assumption was bad, the approach changed — surface it explicitly. Decide: change the test,
   skip it, or make the code match it. Log the decision.
6. **Repeat across sessions.** Each session picks up the RED/GREEN log and continues.

### Tracer Bullet Development

Tracer bullet means proving end-to-end flow first, then hardening the internals.

1. **Build the thinnest working path.** For each phase, build just enough code to make the full
   flow work — input to processing to output — against real dependencies. No stubs, no fakes.
   Real GCP, real tokens, real HTTP. It doesn't have to be clean. It has to work.
2. **Write one integration test.** A single end-to-end integration test that captures the full
   flow. This is the golden source — "if this passes, the phase works." It doesn't test internals.
   It tests outcomes.
3. **Refine while the integration test stays GREEN.** Once the tracer bullet works, improve the
   implementation: clean up code, extract modules, add error handling. The integration test tells
   you if you broke anything.
4. **Freeze the internals with unit tests.** As a second pass, add unit and detailed integration
   tests to lock in the internal behavior. By now the code is stable — these tests document and
   protect what's already working.

### Why we combine them

Interface design is already done — the implementation docs have clear interfaces, data models,
and acceptance criteria. The bigger risk is "does GCP actually behave like we think it does?" —
mocks can't answer that. We answer it by running against real GCP first and capturing the actual
responses as fixtures. Those real-response fixtures then become the basis for unit test mocks, so
the mocks reflect reality rather than assumptions.

Pure-logic modules don't have this problem. Their inputs and outputs are fully known, so TDD
gives fast feedback without integration overhead.

</reference_content>