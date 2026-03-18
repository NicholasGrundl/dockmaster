# Implementation Alignment Report

*Generated: 2026-03-16*
*Last updated: 2026-03-18*
*Purpose: Identify inconsistencies between blueprint docs and actual implementation state.*

---

## Resolved Items

1. ~~Routes had local `_get_*` helpers instead of using dependencies~~ — DONE (2026-03-18)
   - Created `state.py` with bridge dependencies (`get_admin_storage`, `get_authority`, `get_session_store`)
   - Migrated `admin.py` and `admin_ui.py` to `Annotated[X, Depends(...)]` params
   - Only `_admin_writes_enabled` remains as a local helper (template rendering hint, not a dependency)

## Established Pattern

```
allow_* gates are at the router level via dependencies=[...]

individual routes with permission or additional requirements use needs_* gates

routes that need information the allow or require gate returns should:
- add an information-only dependency to auth/dependencies.py (get_*)
- call it on the route specifically via Annotated[X, Depends(get_*)]
- this makes the Depends tree easy to follow (even if it duplicates some code from allow gates)

route modules should not make helpers for app.state access
- use state.py bridges as Annotated[X, Depends(...)] dependencies
- only use local helpers for route-specific logic (template rendering, form parsing, etc.)
```

## ToDo Items

None currently — all alignment items resolved.
