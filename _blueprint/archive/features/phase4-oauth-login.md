---
state: Finalized
changelog:
  "2026-03-08 15h": "Initial spec created from planning sessions"
---

# Phase 4: OAuth Login + Session

> Browser-based Google OAuth2 login via Authlib, pluggable session management, and test UI.

**Status**: Planned
**Priority**: P0
**Phase**: 4
**Last updated**: 2026-03-08

---

## Problem

Users need to log in via their browser using Google SSO. After login, the system needs session management to maintain auth state. The refresh endpoint must exchange refresh tokens for new dockmaster JWTs.

## Solution

### Overview

Integrate Authlib for the full OAuth2/OIDC authorization code flow with Google. Implement a pluggable session store (in-memory first, Redis later). Add a minimal test UI for browser-based login testing.

### Implementation Details

#### OAuth Client (oauth.py)

Configure Authlib's OAuth2 client for Google:
- OpenID Connect discovery (`https://accounts.google.com/.well-known/openid-configuration`)
- PKCE support for authorization code flow
- Scopes: `openid email profile`
- Client credentials from Settings (`client_id`, `client_secret`)

#### Login Flow (login.py)

Three endpoints:

- `GET /auth/login` — redirect to Google authorization URL
  - Generates state parameter, stores in session
  - Redirects to Google's authorization endpoint
- `GET /auth/callback` — handle Google's redirect
  - Validates state parameter
  - Exchanges authorization code for tokens
  - Extracts id_token claims (email, name, picture)
  - Creates session, issues dockmaster JWT
  - Redirects to test UI or returns JSON
- `GET /auth/logout` — clear session
  - Destroys session
  - Redirects to login page

#### Refresh Endpoint (refresh.py)

```
POST /auth/refresh
Body: { "refresh_token": "<google-refresh-token>" }

Response 200:
{
  "token": "<new-dockmaster-jwt>",
  "claims": { ... }
}
```

- Loads client secret from Secret Manager (or config for dev)
- Calls Google refresh endpoint with `data=` (not `params=` — legacy bug fix)
- Verifies returned id_token
- **Checks `can_issue` flag before issuing** (legacy bug fix)
- Signs new dockmaster JWT with ServiceUser

#### Session Management (sessions/)

Pluggable `SessionStore` protocol:

```python
class SessionStore(Protocol):
    async def get(self, session_id: str) -> dict | None: ...
    async def set(self, session_id: str, data: dict, ttl: int = 3600) -> None: ...
    async def delete(self, session_id: str) -> None: ...
```

**InMemorySessionStore** — dict-based implementation:
- `dict[str, tuple[dict, float]]` — maps session_id to (data, expiry_timestamp)
- Lazy cleanup on access (check expiry before returning)
- Suitable for single-instance development

#### Test UI (templates/login_test.html)

Minimal Jinja2+HTMX page:
- Login button → redirects to `/auth/login`
- Shows current session state (logged in user, JWT claims)
- Logout button → calls `/auth/logout`
- Refresh button → calls `/auth/refresh`

#### Legacy Bug Fixes

1. **`data=` vs `params=`**: Google's token endpoint requires form-encoded body (`data=`), not query params. Legacy code used `params=`.
2. **`can_issue` enforcement**: Refresh endpoint now checks the flag before issuing a new JWT.

### File Structure

```
src/dockmaster/
    auth/
        oauth.py            # Authlib OAuth2 client setup
    sessions/
        __init__.py
        protocol.py         # SessionStore protocol/ABC
        memory.py           # InMemorySessionStore
    routes/
        login.py            # /auth/login, /auth/callback, /auth/logout
        refresh.py          # /auth/refresh
    templates/
        login_test.html     # Jinja2+HTMX test UI
tests/
    test_oauth.py
    test_sessions.py
    test_login.py
    test_refresh.py
docs/
    GUIDE-oauth-consent-screen.md
```

## Dependencies

- **Requires**: Phase 3 (token exchange, ServiceUser signing)
- **Enables**: Phase 5 (RBAC can protect endpoints via session auth)
- **New packages**: `authlib>=1.0`, `jinja2`, `itsdangerous` (session signing)

## Source References

| Planning Doc | Relevant Sections |
|---|---|
| `_blueprint/features/planning/05-flask-integration.md` | Auth Blueprint (OAuth flow), session management patterns |
| `_blueprint/features/planning/07-service-endpoints.md` | Section 3: /auth/refresh endpoint spec |
| `_blueprint/features/planning/08-token-flows.md` | OAuth code flow details |
| `_blueprint/features/planning/E-confidence-notes.md` | `data=` vs `params=` bug, `can_issue` bug |
| `_blueprint/features/planning/C-api-spec.md` | OpenAPI reference |

## Open Questions

None — all design decisions resolved in planning.

## Acceptance Criteria

- [ ] `GET /auth/login` redirects to Google authorization URL with correct params
- [ ] `GET /auth/callback` exchanges code for tokens and creates session
- [ ] `GET /auth/logout` clears session and redirects
- [ ] `POST /auth/refresh` exchanges refresh token for new dockmaster JWT
- [ ] `InMemorySessionStore` stores/retrieves/deletes sessions with TTL
- [ ] `SessionStore` protocol allows drop-in replacement
- [ ] Test UI renders and allows login/logout/refresh cycle
- [ ] Legacy bugs fixed: `data=` for token endpoint, `can_issue` checked
- [ ] All tests pass (OAuth flow mocked, no real Google calls)
- [ ] `uv run pytest tests/ -v` passes
- [ ] `just lint` and `just format` clean
- [ ] GCP Guide created: `docs/GUIDE-oauth-consent-screen.md`
