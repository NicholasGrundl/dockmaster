---
state: Finalized
changelog:
  "2026-03-16": "Created — test suite audit findings from coverage + pattern analysis"
---

# Phase 8d: Test Audit Findings

> Audit of test coverage, organization, patterns, and markers for the dockmaster test suite.

**Phase**: 8d
**Last updated**: 2026-03-16

---

## 1. Coverage Report

**Overall**: 86% (1858 statements, 265 missed)
**Test count**: 411 tests, all passing

### Coverage by Module

#### High Coverage (95%+) — 23 modules

| Module | Coverage | Notes |
|---|---|---|
| `auth/auth_code.py` | 100% | |
| `auth/jwt_signer.py` | 100% | |
| `auth/middleware.py` | 100% | |
| `auth/oauth.py` | 100% | |
| `auth/token_issuer.py` | 100% | |
| `cli/check.py` | 100% | |
| `cli/grants.py` | 98% | 1 line missed |
| `cli/main.py` | 100% | |
| `cli/roles.py` | 100% | |
| `config.py` | 96% | 2 lines missed (edge cases in `_parse_comma_separated`) |
| `logging.py` | 95% | 1 line: dev renderer branch |
| `rbac/admin_ops.py` | 100% | |
| `rbac/models.py` | 100% | |
| `routes/admin.py` | 100% | |
| `routes/claims.py` | 100% | |
| `routes/exchange.py` | 98% | |
| `routes/health.py` | 100% | |
| `routes/keys.py` | 100% | |
| `routes/permissions.py` | 100% | |
| `routes/refresh.py` | 95% | 4 lines missed |
| `routes/token.py` | 95% | 3 lines missed |
| `routes/ui.py` | 98% | |
| `sessions/memory.py` | 100% | |

#### Medium Coverage (75–94%) — 8 modules

| Module | Coverage | Missing | Notes |
|---|---|---|---|
| `auth/admin.py` | 75% | Lines 56-65 | `require_admin_ui` with session-based auth |
| `auth/jwt_verifier.py` | 93% | Lines 69-70, 85, 91 | Error branches in SA key fetch |
| `auth/key_cache.py` | 94% | 8 lines | Update/expiry edge cases |
| `cli/config.py` | 78% | Lines 18-19 | Credential path resolution |
| `cli/http.py` | 92% | Lines 39-40 | Error handling branch |
| `cli/token.py` | 89% | Lines 29-30 | Error handling branch |
| `main.py` | 87% | 18 lines | Lifespan branches (ADC fallback, admin SA loading) |
| `rbac/storage.py` | 84% | 11 lines | `_save_secret`, `_delete_secret` helper methods |
| `routes/login.py` | 91% | 14 lines | Various error/redirect branches |

#### Low Coverage (<75%) — 4 modules

| Module | Coverage | Missing | Notes |
|---|---|---|---|
| `cli/auth.py` | **51%** | 44 lines | Browser-based login flow — `_run_callback_server`, `login`, browser launch |
| `ui/config.py` | **62%** | 12 lines | `load_ui_config()` JSON parsing branches |
| `routes/admin_ui.py` | **25%** | 114 lines | All admin UI page handlers — deferred (Phase 10 scope) |
| `sessions/protocol.py` | **0%** | 3 lines | Protocol class — abstract definition, nothing to test |

### Coverage Gap Analysis

| Gap | Reason | Risk | Recommendation |
|---|---|---|---|
| `routes/admin_ui.py` (25%) | Intentionally deferred — UI still evolving (Phase 10) | Low | Keep deferred. UI tests should use browser-based testing. |
| `cli/auth.py` (51%) | Browser + localhost server flow is hard to unit test | Medium | The login flow involves spawning a server + opening a browser. Integration-level test with subprocess would be the right approach, but complex. |
| `ui/config.py` (62%) | Missing branches for JSON parsing edge cases | Low | Easy to add — just test `load_ui_config()` with various inputs. |
| `sessions/protocol.py` (0%) | It's a 3-line Protocol class | None | Nothing to test — this is correct. |
| `main.py` (87%) | Lifespan branches for ADC fallback, missing credentials | Low | These are infrastructure paths tested via integration. Safe gap. |
| `rbac/storage.py` (84%) | Write methods (`_save_secret`, `_delete_secret`) | Low | Already covered indirectly via `admin_ops` tests. |

---

## 2. Test Organization Review

### Current Structure

```
tests/                          # 34 test files (flat)
├── fixtures/                   # Test data files
│   ├── gcp/                    # GCP API response fixtures
│   │   ├── google_oauth/       # 4 OAuth fixtures
│   │   ├── google_oidc/        # OIDC certs
│   │   └── iam/                # IAM API fixtures
│   └── rbac/                   # RBAC model fixtures
│       ├── role_viewer.json
│       └── service_grants_example.json
├── conftest.py                 # Single shared conftest (~190 lines)
├── test_admin_auth.py
├── test_admin_endpoints.py
├── test_admin_ops.py
├── ... (31 more test files)
└── fake_sa_key.json
```

### Assessment

**Flat structure: KEEP.** At 34 files, the flat layout is still scannable. The naming convention
(`test_{module}.py`) makes it easy to find tests for any source module. Nested directories
(`tests/auth/`, `tests/cli/`, etc.) would add navigation overhead without real benefit at this
scale. Revisit if the test count exceeds ~50 files.

**Conftest: HEALTHY.** At ~190 lines with clear section comments, the single conftest is manageable.
Fixtures are well-scoped:
- RSA keys: session-scoped (generated once, reused)
- Settings/app/client: function-scoped (fresh per test)
- GCP fixture loaders: function-scoped with `pytest.skip` if file missing

**Fixture files: GOOD.** Well-organized by service (`gcp/google_oauth/`, `gcp/iam/`, `rbac/`).

**One issue**: `tests/fake_sa_key.json` sits at the root level outside `fixtures/`. Should be
in `fixtures/` or removed if it's a duplicate of the conftest-generated fake key.

### Finding: T-001 — Stray fixture file (Severity: Low)

`tests/fake_sa_key.json` exists at the root of `tests/` outside the `fixtures/` directory.
The conftest already generates fake SA keys dynamically via the `fake_sa_key_data` fixture.

**Recommendation**: Check if any test imports this file directly. If not, delete it. If yes,
move it to `tests/fixtures/` and update the import.

---

## 3. Test Pattern Review

### Class-based grouping: CONSISTENT

All 34 test files use `class Test*` grouping — 133 test classes total. This is a valid pytest
pattern (pytest discovers methods on plain classes without `TestCase` inheritance). The grouping
aids readability by clustering related tests.

**Verdict**: Consistent. No change needed.

### Mocking approach: MIXED — `unittest.mock` dominant

| Approach | Files |
|---|---|
| `from unittest.mock import ...` | 18 files |
| `mocker` fixture (pytest-mock) | 1 file (`test_key_cache.py`) |

Despite `pytest-mock` being a dev dependency, nearly all tests use `unittest.mock` directly.
This isn't a bug — `unittest.mock` is perfectly fine with pytest — but the inconsistency
with `test_key_cache.py` using `mocker` is notable.

### Finding: T-002 — Mixed mocking approaches (Severity: Low)

18 test files use `unittest.mock.patch`/`MagicMock` directly. 1 file uses the `mocker` fixture
from `pytest-mock`. Both work fine, but the inconsistency is a minor DX issue.

**Recommendation**: Standardize on one approach. `unittest.mock` is already dominant and doesn't
require an extra dependency — consider making it the standard and removing `pytest-mock` from dev
deps. Or migrate everything to `mocker` if the team prefers the fixture-based API.

**Effort**: Small (cleanup) — not urgent.

### Parameterization: ZERO usage

Zero `@pytest.mark.parametrize` decorators across the entire suite. Several test files have
repetitive setup patterns that could benefit from parameterization.

### Finding: T-003 — No parametrize usage (Severity: Low)

Some test classes repeat nearly identical tests with different inputs. For example, config
tests for different comma-separated fields, CLI command tests for different subcommands with
similar mock patterns, and admin endpoint tests for similar CRUD operations.

**Recommendation**: Not urgent — readability matters more than DRY in tests. But consider
parametrize for cases where 5+ tests differ only by input/expected values (e.g., config
parsing edge cases).

**Effort**: Small per instance, medium overall.

### Test isolation: GOOD

Tests use fresh `app` and `client` fixtures per test (function-scoped). No shared mutable
state. The `auth_client` fixture properly yields within a `TestClient` context manager.

Some test files build their own mini `FastAPI()` apps (e.g., `test_admin_endpoints.py` with
`_admin_app()`, `test_admin_auth.py` with `_authed_app()`). This is intentional — these tests
need specific state configurations that differ from the base conftest `app`.

**Verdict**: Good isolation. No hidden ordering dependencies.

### Assertion style: CONSISTENT

- Plain `assert` for value checks
- `pytest.raises` for exception checks
- No use of `pytest.approx` (not needed — no floating-point comparisons)
- Consistent pattern: `assert result.status_code == 200` for HTTP tests

### Finding: T-004 — Some test files build custom mini-apps (Severity: Low / Intentional)

Files like `test_admin_endpoints.py`, `test_admin_auth.py`, `test_permissions.py`, and
`test_auth_code_flow.py` construct standalone `FastAPI()` apps with manually wired state
instead of using the conftest `app` fixture.

This is intentional — these tests need precisely controlled mock configurations. But it creates
a parallel wiring pattern that doesn't go through `create_app()`, so middleware/startup behavior
differs from the real app.

**Recommendation**: Document this as a known pattern. For future tests, prefer using the conftest
`app` fixture and overriding specific `app.state.*` attributes where possible.

**Effort**: None (documentation only).

---

## 4. Marker & Tagging Review

### Registered markers (pyproject.toml)

```toml
markers = [
    "integration: requires real GCP credentials (deselect with '-m not integration')",
    "unit: pure unit tests, no external deps",
]
```

### Actual marker usage

| Marker | Usage |
|---|---|
| `@pytest.mark.integration` | 0 tests currently marked (integration tests run manually via curl/scripts) |
| `@pytest.mark.unit` | 0 tests currently marked |

### Finding: T-005 — Markers registered but unused (Severity: Medium)

Both `integration` and `unit` markers are registered in `pyproject.toml` but no tests actually
use them. The default `uv run pytest` runs all 411 tests without marker filtering.

**Impact**: No way to run a quick "smoke" subset. The full suite takes ~42 seconds, which is
reasonable for now but will grow.

**Recommendation**:
1. Remove the unused `unit` marker — all tests are unit tests by default. The convention should
   be: unmarked = unit (runs by default), `@pytest.mark.integration` = requires external services.
2. When integration tests are added (Phase 9+), mark them properly.
3. Consider adding a `slow` marker for tests that take >1s (currently none).

**Effort**: Small.

### Finding: T-006 — No filterconfig for integration tests (Severity: Low)

`pyproject.toml` doesn't have a `filterwarnings` or `addopts` entry to exclude integration tests
by default. If someone adds `@pytest.mark.integration` tests, they'll run with every
`uv run pytest` unless the developer remembers `-m "not integration"`.

**Recommendation**: Add to `pyproject.toml`:
```toml
addopts = "-m 'not integration'"
```

This makes `uv run pytest` skip integration tests by default. Run them explicitly with
`uv run pytest -m integration`.

**Effort**: Tiny (one line in pyproject.toml).

---

## 5. Additional Findings

### Finding: T-007 — `pytest-playwright` is a dev dependency but unused in tests (Severity: Low)

`pytest-playwright` is listed in dev dependencies but no test file imports from it. Playwright
was used for screenshot scripts (`scripts/screenshot.py`) during Phase 4c UI development, not
for automated tests.

**Recommendation**: Move `pytest-playwright` to an optional dependency group or remove it until
Phase 10 (UI tests). It pulls in a large dependency tree.

**Effort**: Tiny.

### Finding: T-008 — Test suite speed is healthy (Severity: None — informational)

Full suite: 411 tests in ~42 seconds. Average ~100ms per test. No individual test appears to
be a bottleneck. This is well within acceptable CI time.

---

## 6. Findings Summary

| ID | What | Impact | Category | Recommendation | Effort |
|---|---|---|---|---|---|
| T-001 | Stray `fake_sa_key.json` at `tests/` root | Low | Organization | Move to `fixtures/` or delete if unused | Tiny |
| T-002 | Mixed mocking: 18 files `unittest.mock`, 1 file `mocker` | Low | Pattern | Standardize on `unittest.mock`, consider dropping `pytest-mock` dep | Small |
| T-003 | Zero `@pytest.mark.parametrize` usage | Low | Pattern | Add where 5+ tests differ only by input. Not urgent. | Medium |
| T-004 | Some tests build mini-apps instead of using conftest `app` | Low | Pattern | Intentional — document as known pattern | None |
| T-005 | Markers registered but unused (0 tests marked) | Medium | Markers | Remove `unit` marker, keep `integration` for future use | Small |
| T-006 | No `addopts` to exclude integration tests by default | Low | Markers | Add `addopts = "-m 'not integration'"` to pyproject.toml | Tiny |
| T-007 | `pytest-playwright` unused in test suite | Low | Organization | Remove or move to optional dep group until Phase 10 | Tiny |
| T-008 | Suite speed: 411 tests in 42s — healthy | None | Info | No action | None |

### Coverage Gaps Worth Addressing

| Module | Current | Gap Reason | Action |
|---|---|---|---|
| `routes/admin_ui.py` (25%) | Deferred to Phase 10 | UI still evolving | No action now |
| `cli/auth.py` (51%) | Hard to unit test (browser + server) | Complex integration flow | Backlog |
| `ui/config.py` (62%) | Missing edge case tests | Easy to add | Small task |

### Overall Assessment

The test suite is in **good shape** for a project at this stage:
- 86% coverage with explainable gaps
- Consistent patterns (class-based, plain assert, function-scoped fixtures)
- Clean conftest with proper scoping
- No test isolation issues
- Reasonable speed

The main opportunities are hygiene items (T-001, T-002, T-006, T-007) rather than structural
issues. No urgent action required before deployment.
