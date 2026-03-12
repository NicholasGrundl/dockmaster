# Phase 4c: UI Polish + Admin Prep

## Context

Phase 4b is complete — the test UI at `/ui/test` works functionally (login, logout, refresh all verified) but has rendering bugs (raw Jinja2 tags visible) and is visually rough. The user wants to:
1. Fix the template rendering
2. Polish the visual design
3. Prepare the UI as a foundation for an admin dashboard (show sessions, JWT state, etc.)
4. Add Playwright as a dev tool so Claude can screenshot pages during iteration

## Approach

### 1. Add Playwright dev dependency
- `uv add --dev pytest-playwright`
- `uv run playwright install chromium`
- Create a small helper script (`scripts/screenshot.py`) to capture a page and save as PNG
- Claude can then use `Read` tool to view screenshots during polish iterations

### 2. Fix template rendering — switch to Jinja2
The manual `_keep_block()` renderer is buggy (nested conditionals don't work). Rather than patching it, add `jinja2` as a dependency (FastAPI already supports it) and use proper template rendering. Jinja2 is lightweight and we'll need it long-term for the admin UI anyway.

- `uv add jinja2` (FastAPI's `Jinja2Templates` needs it)
- Rewrite `routes/ui.py` to use `Jinja2Templates`
- Keep `templates/login_test.html` but clean up the template syntax

### 3. Visual polish
- Clean monospace layout with proper spacing
- Status banner (logged in / not logged in) styled clearly
- Buttons instead of raw links for Login/Logout
- Refresh form with better layout
- Response display area with formatted JSON

### 4. Admin UI prep — show more state
- **Session info**: current user email, name, session expiry
- **Last refresh result**: JWT claims decoded, token expiry countdown
- **Service status panel**: show which singletons are configured (signer, realm, oauth, secrets_storage)
- **Active sessions list**: add `list_all()` to `SessionStore` protocol + `InMemorySessionStore`, display in UI
- Full dashboard (RBAC status, key cache state, health metrics) deferred to Phase 5

## Files to modify
- `pyproject.toml` — add `jinja2`, `pytest-playwright` (dev)
- `src/dockmaster/routes/ui.py` — rewrite with Jinja2Templates
- `src/dockmaster/templates/login_test.html` — proper Jinja2 template + CSS polish
- `src/dockmaster/sessions/protocol.py` — add `list_all()` to protocol
- `src/dockmaster/sessions/memory.py` — implement `list_all()`
- `scripts/screenshot.py` — Playwright screenshot helper (new)

## Sub-tasks (ordered)
1. Add dependencies (jinja2 + pytest-playwright), install Playwright chromium
2. Create screenshot helper, verify it works
3. Rewrite ui.py with Jinja2Templates, fix rendering bugs
4. Visual polish pass (CSS, layout, buttons)
5. Add session list + service status to UI
6. Lint + full test suite green
7. Update implementation-progress.md

## Verification
- `uv run pytest` — 117+ tests GREEN
- `uv run python scripts/screenshot.py` — captures page screenshot
- Visual inspection via screenshot: no raw template tags, clean layout
- Login → session displayed → refresh → JWT claims shown → logout flow works
- `uv run ruff check src/ tests/` — clean
