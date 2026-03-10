# Development Approach

Read the full guide at `_blueprint/prompts/PROMPT-development-approaches.md` at the start of
every implementation session.

## Summary: Tracer Bullet + Selective TDD

We use **tracer bullet** as the primary approach, with **TDD for pure-logic modules** that have
no external dependencies.

### Three passes per phase

1. **Pass 1 — Tracer Bullet**: Build the thinnest end-to-end path against real GCP. Write one
   integration test (`@pytest.mark.integration`). Capture every GCP API request+response as a
   fixture file in `tests/fixtures/gcp/`.
2. **Pass 2 — Freeze Internals**: Write unit tests using captured fixtures as mock data. Code
   does NOT change — tests lock in what's working.
3. **Pass 3 — Build Fake Classes**: Build `FakeSecretManagerClient`, `FakeIAMClient`, etc. from
   captured fixtures. Replace raw mocks with reusable fakes.

### TDD from Pass 1 for pure-logic modules

These modules have no external deps — use Red-Green TDD immediately:
- `ServiceUser` (JWT signing), `ServiceRealm` (JWT verification)
- `Authority.has_permission()`, Pydantic models, `InMemorySessionStore`

### Session workflow

1. Read `_blueprint/implementation-progress.md`
2. Read the current phase implementation doc
3. Propose sub-tasks to the user before writing code
4. Implement one sub-task at a time, run `uv run pytest` after each
5. Update `_blueprint/implementation-progress.md` at session end

### Phase order (strictly sequential)

Phase 2: JWT Infrastructure → Phase 3: Token Exchange → Phase 4: OAuth Login + Session →
Phase 5: RBAC → Phase 6: RBAC Management + CLI
