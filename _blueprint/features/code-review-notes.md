# Code Review Notes

Personal notes collected while reading through the dockmaster codebase.

---

## auth

<!-- src/dockmaster/auth/ — JWT, OAuth, admin auth dependencies -->

### dependencies.py — `object` type annotations

The utility functions use `object` as the type for `realm`, `session_store`, and `authority` parameters instead of their actual classes. This kills IDE autocompletion and type checking.

Locations:
- `verify_jwt` (line 57): `realm: object` — should be the actual realm class (e.g. `ServiceRealm`)
- `resolve_session` (line 68): `session_store: object | None` — should be the `SessionStore` protocol
- `check_permission` (line 93): `authority: object | None` — should be `Authority`
- `verify_google_credential` (line 118): `realm: object | None` — same as `verify_jwt`

**Action**: Replace `object` with the real class/protocol types so IDEs can provide autocomplete.


## cli

<!-- src/dockmaster/cli/ — Typer CLI (login, role, grant, check commands) -->


## rbac

<!-- src/dockmaster/rbac/ — Models, storage, authority, admin_ops -->


## routes

<!-- src/dockmaster/routes/ — FastAPI route modules -->


## sessions

<!-- src/dockmaster/sessions/ — SessionStore protocol + in-memory impl -->


## templates

<!-- src/dockmaster/templates/ — Jinja2 HTML templates -->


## ui

<!-- src/dockmaster/ui/ — UIConfig -->


## config

<!-- src/dockmaster/config.py — Settings (pydantic-settings) -->


## main

<!-- src/dockmaster/main.py — App factory + lifespan -->


## tests

<!-- tests/ — pytest test suite -->


## general

<!-- Cross-cutting observations, patterns, questions -->

