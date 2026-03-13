# Implementation Session Guide

This document defines how you run implementation sessions. Read it at the start of every session
before touching any code.

**Purpose**: Orient → Plan → Implement → Close. One phase (or sub-phase) per session.

**Composability**: Sections marked with `<!-- COMPOSABLE -->` contain project-specific content that
may change between phases or across alignment sessions. The surrounding workflow is generic and
stable. When updating composable sections, preserve the marker comments.

---

## Step 0 — Orient Yourself (every session, no exceptions)

### 0a. Explore the project structure

**Do this FIRST, before reading any files.** Use the `smart-tree` skill (or `tree` as fallback)
to scan the project layout. This builds a mental map of where things live and prevents wasting
context reading irrelevant files.

**Required scans** (run these before reading content):

1. **Blueprint scan** — understand planning state:
   - `smart-tree` or `tree _blueprint/ -L 2 --dirsfirst --noreport --gitignore`
   - Identifies: progress file, phase specs, feature docs, memory

2. **Source scan** — understand codebase structure:
   - `smart-tree` or `tree src/ -L 3 --dirsfirst --noreport --gitignore`
   - Identifies: modules, routes, templates, models — where code lives

3. **Test scan** — understand test coverage:
   - `smart-tree` or `tree tests/ -L 2 --dirsfirst --noreport --gitignore`
   - Identifies: which modules have tests, fixture directories

**Philosophy**: Explore structure and filenames FIRST. Only grep or read file contents after you
know WHERE to look. This limited-disclosure approach prevents wasting context on irrelevant files.

**Tool priority**:
1. **Primary**: `smart-tree` skill — intelligent, annotated, recommends read order
2. **Fallback**: `tree` command — fast, flexible, always available
3. **Last resort**: `find` with targeted flags if `tree` is unavailable

### 0b. Read the ground truth

Now that you know where things are, read the key files:

1. Read `_blueprint/roadmap/implementation-progress.md` — the canonical session-to-session state log. It
   tells you what phase we're on, what's done, what's in-progress, and any open decisions.
2. Read the implementation doc for the current phase. Find it by scanning
   `_blueprint/features/implementation-*.md` — there is one per phase or sub-phase.
3. Read `CLAUDE.md` for established patterns and conventions. Follow them exactly.

### 0c. Determine your situation

Based on the progress file, determine which situation applies:

**A) The progress file has incomplete sub-tasks for the current phase.**
Pick up where the last session left off. Confirm with the user: "The progress file shows sub-task
X is next — should I continue from there?" Then go to Step 2.

**B) A phase is complete, or sub-tasks haven't been written yet for the current phase.**
Go to Step 1 to plan and populate sub-tasks.

**C) The progress file is ambiguous.**
Ask the user before proceeding.

### 0d. Targeted exploration (as needed)

During planning or implementation, you may need to explore specific areas of the codebase in more depth. Use the `smart-tree` skill to start this to locate files by name before reading them.

If the exploration results are ambiguous or don't clearly point to the right files, ask the user
for guidance using the `AskUserQuestion` tool with multiple-choice options rather than guessing.

---

## Step 1 — Plan the Session (new phase or empty task list)

### 1a. Break the phase into sub-tasks

Based on the phase implementation doc, break the work into concrete, ordered sub-tasks.

### 1b. Propose to the user

**Propose the sub-task list to the user before writing any code.** Get sign-off.

### 1c. Persist immediately

Once approved, **write the sub-tasks into `_blueprint/roadmap/implementation-progress.md`** immediately
so they persist even if the session ends early.

### 1d. Choose the development approach per sub-task

| Situation | Approach |
|---|---|
| Module touches external services (APIs, databases, HTTP) | **Tracer Bullet** |
| Pure logic, no external dependencies | **TDD (Red / Green / Refactor)** |

<!-- COMPOSABLE: List modules that qualify for immediate TDD in the current phase.
     Example format:
     | Module | Why TDD works here |
     |---|---|
     | `Authority.has_permission()` | Pure Python permission resolution |
     | Pydantic models (`Role`, `Grant`) | Pure validation logic |
-->

---

## Step 2 — Implement

### Tracer Bullet modules: three passes

**Pass 1 — Prove end-to-end (real external services)**

- Build the thinnest path through the sub-task that satisfies the acceptance criteria.
- Write **one integration test** per phase using the app's test client — the golden source of
  "it works end to end."
- Run against real external services (real APIs, real databases, real auth providers).
- **Capture every external API request+response as a fixture file** immediately after the call
  succeeds — don't defer this. See Fixture Capture Strategy below.
- Tag integration tests with an appropriate marker (e.g. `@pytest.mark.integration`).
- **Phase gate**: integration test is GREEN before moving to Pass 2.

**Pass 2 — Freeze internals (unit tests with captured fixtures)**

- Write unit tests for every module, using the captured fixture files as mock data.
- Fixtures represent real external behavior — not guessed shapes.
- Code does NOT change in this pass — tests lock in what's working.
- Unit tests must run without any external service access.

**Pass 3 — Build fake classes**

- Build fake/stub implementations of external clients using the captured fixtures.
- Replace raw mock patches with these reusable fake classes.
- Document which tests still require real services vs which use fakes.

### TDD modules: standard cycle

1. Write a failing test (RED) — it must fail because the behavior isn't implemented, not because
   the test is broken.
2. Write the minimum code to make it GREEN.
3. Refactor while GREEN.
4. Repeat.

### During implementation (both approaches)

- Implement one sub-task at a time.
- Run tests after each sub-task; surface failures immediately.
- **When a test fails unexpectedly**: diagnose whether the test or the code is wrong. Tell the
  user: "This test is RED but I think [the test / the code] is wrong — here's why." Then ask
  whether to fix the test, skip it, or adjust the code.
- **When a sub-task reveals that a future sub-task's interface needs to change**: stop, surface it
  to the user, and get a decision before continuing. Don't silently adjust.
- Never move to the next phase until the current phase's integration test is GREEN.

---

## Fixture Capture Strategy

For every external API call during Pass 1, capture the real HTTP interaction immediately after it
succeeds.

Each fixture file should contain both the request and response:

```json
{
  "request": { "method": "GET", "url": "...", "headers": {}, "body": null },
  "response": { "status": 200, "headers": {}, "body": { ... } }
}
```

These captured fixtures become the mock data for Pass 2 unit tests and the backing data for
Pass 3 fake classes. Mocks built from real responses don't lie.

<!-- COMPOSABLE: Define the fixture directory structure for the current project.
     Example:
     ```
     tests/fixtures/gcp/
       iam/
         list_service_accounts.json
         get_public_key.json
       secret_manager/
         get_role.json
         put_role.json
       google_oauth/
         tokeninfo.json
         userinfo.json
         token_exchange.json
     ```
-->

---

## Step 3 — Close the Session

Update `_blueprint/roadmap/implementation-progress.md` before ending. Use this format:

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
- `tests/fixtures/<service>/<endpoint>.json` done
- `tests/fixtures/<service>/<endpoint>.json` not yet

## Test status
- `tests/test_<module>.py` GREEN
- `tests/test_<module>.py` RED — not started
- `tests/integration/test_phase<N>.py` RED — WIP

## Decisions log
- YYYY-MM-DD: <decision made and why>

## Open decisions / blockers
- None

## Next session: pick up at
"<specific sub-task description>"
```

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
   Real services, real tokens, real HTTP. It doesn't have to be clean. It has to work.
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

When interface design is already done (from specs with clear interfaces, data models, and
acceptance criteria), the bigger risk is "do external services actually behave like we think they
do?" — mocks can't answer that. We answer it by running against real services first and capturing
the actual responses as fixtures. Those real-response fixtures then become the basis for unit test
mocks, so the mocks reflect reality rather than assumptions.

Pure-logic modules don't have this problem. Their inputs and outputs are fully known, so TDD
gives fast feedback without integration overhead.

</reference_content>
