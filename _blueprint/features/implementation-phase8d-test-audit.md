---
state: Draft
changelog:
  "2026-03-16": "Created — test suite audit spec"
---

# Phase 8d: Test Audit

> Audit test coverage, organization, patterns, and markers against pytest best practices.
> Produces findings doc only — no code changes.

**Status**: Planned
**Priority**: P2
**Phase**: 8d
**Last updated**: 2026-03-16
**Depends on**: Phase 8a–8c complete (full codebase context needed)
**Output**: `_blueprint/features/audit-8d-test-findings.md`

---

## Problem

The test suite has grown to 411+ tests across multiple phases. Each phase added tests with
slightly different conventions. Before the codebase matures further, we should audit the test
suite for:

1. Coverage gaps (what's untested?)
2. Organizational consistency (flat files vs packages, conftest structure)
3. Pattern consistency (functions vs classes, fixture usage, mocking approaches)
4. Marker strategy (integration, slow, smoke — what's tagged, what should be?)

## Deliverables

### 1. Coverage Audit

- **Run coverage report**: `uv run pytest --cov=src/dockmaster --cov-report=term-missing`
- **Identify gaps**: Which modules/functions have no test coverage?
- **Categorize gaps**: Is this untested because it's hard to test (GCP calls), low risk
  (simple config), or just missed?
- **Coverage by module**: Table showing coverage % per source module

### 2. Test Organization Review

Current structure: all test files in flat `tests/` directory with a single `tests/conftest.py`
and `tests/fixtures/` for data files.

Evaluate and recommend on:

- **Flat vs nested**: Should tests mirror the source structure?
  (e.g., `tests/auth/test_token_issuer.py` vs `tests/test_token_issuer.py`)
- **Conftest hierarchy**: Single `conftest.py` vs nested conftest files per subdirectory.
  Current conftest has fixtures for all phases — is it getting unwieldy?
- **Fixture files**: `tests/fixtures/` currently has GCP and RBAC fixtures. Is the structure
  scaling well?
- **Test file naming**: Are names descriptive and consistent?
  (e.g., `test_admin_endpoints.py` vs `test_admin_auth.py` vs `test_admin_ops.py`)

### 3. Test Pattern Review

Evaluate current patterns against pytest best practices:

- **Functions vs classes**: Are tests using bare functions (recommended by pytest) or
  TestCase-style classes? Is the choice consistent?
- **Fixture usage**: Are fixtures properly scoped (function/module/session)?
  Any fixtures that should be shared but aren't? Any over-shared fixtures?
- **Mocking approach**: `pytest-mock` (mocker fixture) vs `unittest.mock.patch`?
  Are mocks properly scoped and cleaned up?
- **Assertion style**: Plain `assert` vs pytest helpers (`pytest.raises`, `pytest.approx`)?
  Consistent assertion patterns?
- **Test isolation**: Do tests have hidden dependencies on execution order?
  Any shared mutable state between tests?
- **Parameterization**: Are there tests with repetitive setup that could use `@pytest.mark.parametrize`?
- **DRY vs readable**: Are test helpers/factories used where helpful, or are tests
  copy-pasted? Is there over-abstraction making tests hard to read?

### 4. Marker & Tagging Review

Current markers:
- `@pytest.mark.integration` — tests requiring real GCP services

Evaluate:

- **Missing markers**: Should there be `slow`, `smoke`, `e2e`, `ui` markers?
- **Default test run**: `uv run pytest` runs everything except `integration`.
  Should there be a `smoke` subset for quick CI checks?
- **Marker discipline**: Are all integration-dependent tests properly marked?
  Are any tests accidentally hitting external services without the marker?
- **Custom markers**: Should markers be registered in `pyproject.toml` or `conftest.py`
  to avoid typo warnings?

### 5. Findings Summary

Each finding with:

| Field | Description |
|---|---|
| ID | Sequential (T-001, T-002, ...) |
| What | Description of the issue or improvement opportunity |
| Impact | High / Medium / Low (test reliability and DX impact) |
| Category | Coverage / Organization / Pattern / Markers |
| Recommendation | Suggested improvement |
| Effort | Small / Medium / Large (estimated refactoring effort) |

## Implementation Sub-tasks

- [ ] 1. Run coverage report and analyze gaps
- [ ] 2. Review test file organization and conftest structure
- [ ] 3. Read representative test files from each phase, catalog patterns
- [ ] 4. Audit marker usage and test categorization
- [ ] 5. Write findings doc with categorized recommendations
- [ ] 6. Review findings with user

## Acceptance Criteria

- [ ] Coverage report generated with per-module breakdown
- [ ] Test organization reviewed with recommendation (flat vs nested, conftest strategy)
- [ ] Test patterns audited against pytest best practices
- [ ] Marker strategy reviewed with recommendations
- [ ] Each finding has impact rating and effort estimate
- [ ] No code changes — audit and documentation only
