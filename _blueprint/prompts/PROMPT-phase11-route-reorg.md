# Phase 11 Implementation Addendum

**Use with**: `PROMPT-orient-and-implement.md` (read that first, then this)
**Phase**: 11 — Route Reorg + Refresh Token
**Spec**: `_blueprint/features/implementation-phase11-route-reorg.md`

This addendum overrides the generic orient-and-implement guide with Phase 11-specific context.
It tells you what's already done, what's next, and how to approach each step.

---

## Orient Override (Step 0)

Skip the generic orientation. Read these files in this order:

1. `_blueprint/roadmap/implementation-progress.md` — current step status
2. `_blueprint/features/implementation-phase11-route-reorg.md` — **the single spec** (design,
   diagrams, steps, edges, route map — everything is here)
3. `CLAUDE.md` — coding conventions

Then read the key source files to understand current state:

4. `src/dockmaster/main.py` — lifespan + router registrations (old + new routes coexist)
5. `src/dockmaster/auth/dependencies.py` — auth gates and info deps
6. `src/dockmaster/routes/login.py` — the file being refactored
7. `src/dockmaster/routes/cli_routes.py` — new, needs CLI OAuth additions
8. `src/dockmaster/routes/session.py` — new, functional
9. `src/dockmaster/routes/service.py` — new, functional

**Do NOT read** `_blueprint/archive/` or `_blueprint/features/planning/` — all planning content
has been consolidated into the single spec.

---

## What's Already Done

Steps 0 and 1 from the original v1 plan are complete. Partial work from Step 2 exists:

| Item | Status | Where |
|---|---|---|
| `AuthResult` + `check_ui_session` | Done | `auth/dependencies.py` |
| `allow_session` returns 401 (not 307) | Done | `auth/dependencies.py` |
| UI routes use `check_ui_session` | Done | `routes/ui.py`, `routes/admin_ui.py` |
| `state.py` bridges | Done | `state.py` |
| `allow_session` accepts refresh_token body | Done | `auth/dependencies.py` |
| `get_session_user` accepts refresh_token body | Done | `auth/dependencies.py` |
| Logout changed to POST | Done | `routes/login.py` |
| `AuthCodeEntry.profile` field | Done | `auth/auth_code.py` |
| `POST /auth/login/code` endpoint | Done | `routes/login.py` (will be renamed in Step F) |
| `routes/session.py` created | Done | functional, registered in main.py |
| `routes/service.py` created | Done | functional, registered in main.py |
| `routes/cli_routes.py` created | Done | has `POST /auth/cli/token` only, needs OAuth |
| `from __future__ import annotations` sweep | Done | all source + test files |
| Old routes (token.py, exchange.py) still registered | **Active** | main.py — removed in Step G |

---

## Step Sequence

Implement in this order. Each step is independently committable and testable.

```
Step A — Extract CLI OAuth to cli_routes.py
Step B — Create OAuthFlowStore (pure addition, no consumers)
Step C — Wire OAuthFlowStore into app (replace old stores)
Step D — Rename callback → /auth/login/callback
Step E — Add return_to support
Step F — Rename /auth/login/code → /auth/login/exchange
Step G — Cleanup (delete old routes, dead code, lint)
Step H — Logout content negotiation
```

### Step dependencies

```
A ──┐
    ├── C (needs A for cli_routes consumers, needs B for OAuthFlowStore)
B ──┘
C ── D ── E ── F ── G ── H
```

Steps A and B are independent — they can be done in either order. Everything else is sequential.

---

## Development Approach Per Step

| Step | Approach | Why |
|---|---|---|
| A: CLI OAuth extraction | **TDD** | Pure route refactoring. Mock OAuth. No external services. |
| B: OAuthFlowStore | **TDD** | Pure logic. Pydantic models + TTLStore wrapper. |
| C: Wire OAuthFlowStore | **Careful migration** | Touch many files. Run full suite after each change. |
| D: Rename callback | **Mechanical** | Find-replace paths. Run tests. |
| E: return_to support | **TDD** | New feature with validation logic. |
| F: Rename login/code | **Mechanical** | Find-replace paths + model names. Run tests. |
| G: Cleanup | **Sweep** | Delete dead code, run lint + full suite. |
| H: Logout negotiation | **TDD** | Small feature. Test both JSON and redirect paths. |

---

## Key Patterns to Follow

### Router auth gates

```python
# API routes — hard gates at router level
router = APIRouter(tags=["session"], dependencies=[Depends(allow_session)])

# UI routes — NO router-level gate, soft auth per-route
router = APIRouter(tags=["ui"])
@router.get("/roles")
async def roles_page(auth: Annotated[AuthResult, Depends(check_ui_session("dockmaster", "admin"))]):
    if not auth.is_authenticated:
        return RedirectResponse("/ui/login", 307)
```

### OAuthFlowStore usage

```python
# In login.py (GET /auth/login):
flow_store = request.app.state.flow_store
state_key = flow_store.create_oauth_state(redirect_uri=validated, return_to=validated)

# In login.py (GET /auth/login/callback):
entry = flow_store.consume(state)
if not isinstance(entry, OAuthState):
    raise HTTPException(401, "Invalid OAuth state")

# In login.py (callback, external redirect branch):
code = flow_store.create_login_ticket(subject=email, redirect_uri=..., profile=..., return_to=...)

# In login.py (POST /auth/login/exchange):
ticket = flow_store.consume(body.code)
if not isinstance(ticket, LoginTicket) or ticket.redirect_uri != body.redirect_uri:
    raise HTTPException(400, "Invalid or expired code")
```

### CLI routes — no router-level JWT gate

```python
# cli_routes.py — allow_jwt moves to route-level, OAuth routes are public
router = APIRouter(tags=["cli"])

@router.get("/cli/login")     # public — entry point to GET a JWT
@router.get("/cli/callback")  # public — Google redirects here
@router.post("/cli/token", dependencies=[Depends(allow_jwt)])  # protected
```

---

## Known Edges to Watch For

These are documented in the spec but easy to forget during implementation:

1. **GCP OAuth config**: Steps A and D both change redirect URIs. `/auth/cli/callback` and
   `/auth/login/callback` must be added as authorized redirect URIs in Google OAuth client config.
   Don't block on this — build and test with mocks first, note it for manual GCP update.

2. **`PROFILE_CLAIM_KEYS` inconsistency**: login.py includes `"email"`, service.py/exchange.py
   don't. When cleaning up in Step G, decide: centralize the tuple or document the difference.

3. **Double body parsing**: `allow_session` and `get_session_user` both parse `request.json()`
   for refresh_token. FastAPI caches the body so it works. Don't try to fix this — it's a noted
   design smell, not a bug.

4. **Session renewal comment**: When creating the refresh token (in the exchange endpoint), add
   an inline comment noting that session renewal on use is a future enhancement (see backlog).

---

## Test Strategy

- **After each step**: run `uv run pytest` — all 461+ tests must stay green
- **After Step G**: run `just check` — lint + format + types must be clean
- **New test files**: `tests/auth/test_oauth_flow_store.py` (Step B),
  expand `tests/routes/test_cli_routes.py` (Step A)
- **Existing tests to update**: `tests/auth/test_auth_code_flow.py` (path changes),
  `tests/routes/test_login.py` (removed endpoints), `tests/routes/test_token_endpoint.py`
  (path changes)

---

## Session Close Override (Step 3)

After completing a step (or group of steps), update `implementation-progress.md`:
- Check off completed steps
- Note the test count
- If you stopped mid-step, note exactly where

Suggest a commit with conventional format. The user stages with `git add .`.
Do NOT commit without being asked. Do NOT push.
