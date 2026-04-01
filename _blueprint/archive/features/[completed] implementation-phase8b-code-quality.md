---
state: Finalized
changelog:
  "2026-03-16": "Created — code quality review spec with two-pass approach"
---

# Phase 8b: Code Quality Review

> Audit naming conventions, FastAPI patterns, docstrings, and API surface consistency.
> Two-pass approach: catalog + recommendations first, then optional interactive refactoring planning.

**Status**: Planned
**Priority**: P1
**Phase**: 8b
**Last updated**: 2026-03-16
**Depends on**: Phase 8a complete (security findings inform quality recommendations)
**Output**: `_blueprint/features/audit-8b-code-quality-findings.md`

---

## Problem

The codebase has been built across multiple phases by different sessions. Before deployment and
before other developers interact with it, we need to ensure:
1. Naming is consistent and self-documenting across modules
2. FastAPI patterns follow best practices (DI, middleware, error handling)
3. The API surface is consistent and well-structured
4. Docstrings are useful and present where needed

## Approach: Two Passes

### Pass 1: Catalog + Recommendations (always done)

Read every module, catalog current patterns, compare against best practices, produce findings doc.
This is a documentation-only pass.

### Pass 2: Interactive Refactoring Planning (optional, same session)

After Pass 1 is complete, ask the user if they want to do a second pass where we work together to:
- Review each finding interactively
- Discuss tradeoffs for different refactoring approaches
- Produce concrete refactoring plans for approved changes

Pass 2 uses the interview format (AskUserQuestion with options) to walk through findings one by
one and let the user decide on the approach for each.

## Deliverables (Pass 1)

### 1. FastAPI Pattern Catalog

Document every pattern currently used and compare against best practices:

- **Dependency injection**: Where is `Depends()` used? Where should it be used but isn't?
  Are dependencies composed correctly (deps that depend on other deps)?
- **Middleware vs route-level auth**: Current mix of `SessionMiddleware`, `CORSMiddleware`
  (app-level) vs `Depends(get_current_user)`, `Depends(require_admin_api)` (route-level).
  Is the split correct? Are there cases where middleware would be better than Depends or vice versa?
- **Error handling**: How are errors raised and caught? Are we using `HTTPException` consistently?
  Do we have any bare `raise` that leaks details? Are status codes consistent?
- **Response models**: Are we using Pydantic response models for type safety and documentation?
  Or are we returning raw dicts?
- **Route organization**: Are routes logically grouped? Do router prefixes make sense?
  Is the `admin.py` / `admin_ui.py` / `login.py` / `ui.py` split clean?
- **Lifespan pattern**: Is the lifespan function getting too large? Should singletons be
  organized differently?

### 2. Naming & Vocab Audit

Review consistency across the codebase:

- **Auth module naming**: `ServiceUser` (signs GCP SA JWTs), `JWTTokenIssuer` (signs ephemeral JWTs),
  `ServiceRealm` (verifies JWTs), `ServiceAccountKeyCache` (GCP keys), `EphemeralKeyCache` (ephemeral keys).
  Do these names tell a coherent story? Is there a naming scheme that would be clearer?
- **Method naming**: `get_token()` vs `sign()` vs `exchange()` — are verb choices consistent?
- **Route naming**: `/auth/*` vs `/admin/*` vs `/ui/*` — do prefixes accurately describe what's behind them?
- **Variable naming**: Are parameter names consistent across similar functions?
  (e.g., `subject` vs `email` vs `user`, `service` vs `target` vs `audience`)
- **Module naming**: Do file names match what's inside? Any misleading names?

### 3. Docstring Audit

For each module and public function/class:

- **Present?** Does it have a docstring?
- **Useful?** Does it explain *why*, not just *what*?
- **Accurate?** Does it match the current implementation?
- **Concise?** Is it the right length — not too verbose, not missing key info?

Produce a summary: which modules are well-documented, which need work, which are over-documented.

### 4. API Surface Consistency

Review the HTTP API as a consumer would see it:

- **Response format consistency**: Do all endpoints use the same envelope? Same error format?
- **Parameter conventions**: Query params vs path params vs body — is usage consistent?
- **Status code usage**: Are we using the right codes? (200 vs 201 vs 204, 401 vs 403, etc.)
- **Content types**: JSON everywhere? Any HTML responses from API routes?
- **Pagination**: Any list endpoints that might need pagination?

### 5. Findings Summary

Each finding with:

| Field | Description |
|---|---|
| ID | Sequential (Q-001, Q-002, ...) |
| What | Description of the inconsistency or anti-pattern |
| Impact | High / Medium / Low (developer experience impact) |
| Category | Naming / Pattern / Docstring / API Surface |
| Recommendation | Suggested improvement |

## Deliverables (Pass 2 — optional)

For each finding the user chooses to address:
- Concrete refactoring plan (files to change, approach)
- Alternative approaches with tradeoffs (presented as interview questions)
- Estimated scope (how many files/lines affected)

Pass 2 output appended to the same findings doc or saved as a separate refactoring plan.

## Implementation Sub-tasks

### Pass 1
- [ ] 1. Read all route modules, catalog FastAPI patterns (DI, middleware, error handling, response models)
- [ ] 2. Read all auth modules, catalog naming and vocab
- [ ] 3. Read all models, storage, and service modules
- [ ] 4. Audit docstrings across public interfaces
- [ ] 5. Review API surface from consumer perspective
- [ ] 6. Write findings doc with categorized recommendations
- [ ] 7. Review Pass 1 findings with user

### Pass 2 (optional)
- [ ] 8. Ask user which findings to plan refactoring for
- [ ] 9. For each selected finding, interview user on approach preferences
- [ ] 10. Produce concrete refactoring plans

## Acceptance Criteria

- [ ] Every route module, auth module, and model reviewed
- [ ] FastAPI patterns cataloged with best-practice comparison
- [ ] Naming inconsistencies documented with recommendations
- [ ] Docstring coverage summarized
- [ ] API surface reviewed for consumer experience
- [ ] No code changes — documentation only (Pass 1)
