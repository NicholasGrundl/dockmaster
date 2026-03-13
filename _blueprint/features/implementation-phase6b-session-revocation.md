# Phase 6b: Session Revocation

> Admin session management — list, inspect, and revoke user sessions via API, admin UI, and shared service layer.

**Status**: Planned
**Priority**: P1
**Phase**: 6b
**Last updated**: 2026-03-12

---

## Problem

Admins cannot view or revoke user sessions. The dashboard currently shows all sessions to any
logged-in user (privacy issue). There's no way to remove a problematic user's sessions or clean
up stale sessions without restarting the service.

## Solution

### Overview

Add session management following the existing RBAC admin pattern:
1. Shared service layer (`admin_ops` session functions)
2. Admin API endpoints (`/admin/sessions/*`)
3. User-facing endpoint (`/auth/sessions`)
4. Admin UI page (`/ui/sessions`)
5. Fix dashboard to only show current user's session(s)

### API Surface

```
# Regular user (session cookie auth)
GET    /auth/sessions                      — current user's sessions only

# Admin (JWT or session auth + admin role)
GET    /admin/sessions                     — list all active sessions
GET    /admin/sessions/email/{email}       — list sessions for a specific user
DELETE /admin/sessions/id/{session_id}     — revoke one session
DELETE /admin/sessions/email/{email}       — revoke all sessions for a user
```

### Architecture

Mirrors the Phase 6 RBAC admin pattern exactly:

| Layer | RBAC (Phase 6) | Sessions (Phase 6b) |
|-------|----------------|---------------------|
| Storage | `SecretsStorage` / `AdminSecretsStorage` | `SessionStore` (existing protocol) |
| Service layer | `rbac/admin_ops.py` (role/grant functions) | `rbac/admin_ops.py` (add session functions) |
| Admin API | `routes/admin.py` (roles, grants) | `routes/admin.py` (add sessions) |
| User API | — | `routes/login.py` (add `/auth/sessions`) |
| Admin UI | `routes/admin_ui.py` (roles, grants pages) | `routes/admin_ui.py` (add sessions page) |
| Template | `roles.html`, `grants.html` | `sessions.html` (new) |

### Service Layer Functions (in `admin_ops.py`)

```python
# Sessions — these are async-native (no run_in_executor needed)
async def list_sessions(session_store: SessionStore) -> dict[str, dict]
async def list_sessions_by_email(session_store: SessionStore, email: str) -> dict[str, dict]
async def revoke_session(session_store: SessionStore, session_id: str) -> bool
async def revoke_sessions_by_email(session_store: SessionStore, email: str) -> int
```

Note: `revoke_sessions_by_email` uses the option B approach — calls `list_all()`, filters by
email, then calls `delete()` in a loop. No protocol changes needed. When Redis is added later,
this can be optimized with a native scan+delete. See backlog: "Redis Session Store."

### Dashboard Fix

Change `ui.py:dashboard()` to filter `list_all()` by the current user's email instead of
showing all sessions. The full sessions list moves to the admin-only `/ui/sessions` page.

---

## Dependencies

- **Requires**: Phase 6 complete (admin auth, admin_ops pattern, admin UI infrastructure)
- **Enables**: Phase 6c CLI (session revoke command wraps `/admin/sessions` endpoints)

## Implementation Sub-tasks

### TDD (all modules are pure logic with in-memory session store)

1. **Service layer functions + tests** — add session functions to `admin_ops.py`, tests in
   `test_admin_ops.py` (or new `test_session_ops.py` if cleaner)
   - `list_sessions` — delegates to `session_store.list_all()`
   - `list_sessions_by_email` — filters `list_all()` by email match
   - `revoke_session` — calls `session_store.delete()`, returns True/False
   - `revoke_sessions_by_email` — filters + deletes in loop, returns count

2. **Admin API endpoints + tests** — add session endpoints to `routes/admin.py`
   - `GET /admin/sessions` — list all (requires `require_admin_api`)
   - `GET /admin/sessions/email/{email}` — list by email (requires `require_admin_api`)
   - `DELETE /admin/sessions/id/{session_id}` — revoke one (requires `require_admin_api`)
   - `DELETE /admin/sessions/email/{email}` — revoke all for email (requires `require_admin_api`)
   - Tests in `test_admin_endpoints.py`

3. **User endpoint + tests** — add `GET /auth/sessions` to `routes/login.py`
   - Returns current user's sessions (filtered by session email)
   - Uses existing session cookie auth (same as `/auth/principal`)
   - Tests in `test_login.py`

4. **Dashboard fix** — modify `ui.py:dashboard()` to filter sessions by current user's email
   - Update `dashboard.html` to reflect "Your Sessions" (not "Active Sessions")
   - Update existing `test_ui.py` tests if they assert on session count

5. **Admin UI sessions page** — add `/ui/sessions` to `routes/admin_ui.py`
   - New template `sessions.html` — table of all sessions, revoke buttons (per-session and
     per-email), mirrors `roles.html` / `grants.html` layout
   - Form handlers: `POST /ui/sessions/{session_id}/revoke`, `POST /ui/sessions/email/{email}/revoke`
   - Add "Sessions" link to admin nav in `base.html`

6. **Lint + full suite green**

7. **Update progress file**

## Design Decisions

- **No protocol changes**: `SessionStore` protocol stays as-is. Email filtering is done in the
  service layer by iterating `list_all()`. This is fine for single-instance in-memory deployments.
  Redis optimization is a future backlog item.
- **Session functions in `admin_ops.py`**: Keeps the service layer in one place. If it gets too
  large, can be split into `admin_ops/sessions.py` later.
- **No `require_admin_writes` on session endpoints**: Session operations don't need the admin SA
  key (sessions are in-memory, not in Secret Manager). Only `require_admin_api` is needed.
- **Dashboard shows only current user's sessions**: Regular users see their own sessions. Full
  session management is admin-only at `/ui/sessions`.

## Open Questions

None — all decisions resolved during planning.

## Acceptance Criteria

- [ ] Admin can list all active sessions via API and UI
- [ ] Admin can revoke a single session by ID
- [ ] Admin can revoke all sessions for a user by email
- [ ] Regular user can see their own sessions via `GET /auth/sessions`
- [ ] Dashboard only shows current user's sessions (not all sessions)
- [ ] Admin nav includes "Sessions" link
- [ ] All new endpoints require appropriate auth (admin or session)
- [ ] All tests GREEN
