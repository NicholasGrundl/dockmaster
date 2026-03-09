---
state: Finalized
changelog:
  "2026-03-09": "Created from gap analysis of legacy vs phase4-oauth-login-v2.md"
---

# Phase 4: OAuth Login + Session — Implementation Guide

> Concrete coding checklist and gap-analysis notes for implementing Phase 4.
> Reference alongside: `phase4-oauth-login-v2.md` (design spec).

**Status**: Ready to implement
**Phase**: 4
**Last updated**: 2026-03-09

---

## Decisions Locked In

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Add `GET /auth/principal` endpoint | Needed for SPAs/test UI to check session status; low effort |
| D2 | Refresh request field: `refresh_token` (not legacy's `token`) | More explicit; matches OAuth2 spec terminology. **Document the difference from legacy.** |
| D3 | `DEFAULT_CLIENT_ID` setting as fallback when `client_id` not in refresh request | Matches legacy; single-app deploys won't need to send client_id on every call |
| D4 | Client secret loaded from Secret Manager at runtime | Matches legacy `client_id-{name}` secret naming; keeps secrets out of env vars |
| D5 | `/auth/refresh` calls UserInfo API for richer profile claims | Matches legacy; id_token from refresh may have fewer fields than UserInfo response |
| D6 | `/auth/refresh` returns `id_token` + `access_token` in response | Clients may need Google tokens to call other Google APIs |
| D7 | `/auth/refresh` request body includes `service` + `expiry` | Matches legacy; without `service`, issued JWT audience defaults to Google client ID (not useful) |
| D8 | Post-login redirect hardcoded to `/ui/test` (MVP) | Conscious simplification; original-path restoration deferred to backlog |
| D9 | No email whitelist (`AUTHORIZED`) | Domain-level control (`AUTHORIZED_DOMAINS`) is sufficient for LLC use case |

---

## Gaps vs Legacy (resolved)

### G1 — `/auth/refresh` request body was incomplete in v2 spec
**Legacy body**: `{token, client_id?, service?, expiry?}` — note field name is `token` not `refresh_token`
**New body**: `{refresh_token, client_id?, service?, expiry?}` — renamed for clarity
**API difference note**: Document in `docs/` or API spec that legacy used `"token"` for the refresh token field. Any clients migrating from the old service must update this field name.

### G2 — `/auth/refresh` response was incomplete in v2 spec
**Legacy response**: included `id_token`, `access_token`, and `claims` dict alongside the dockmaster `token`
**New response** must include all of: `{token, subject, service, expiry, claims, id_token, access_token}`

### G3 — Client secret storage not detailed in v2 spec
**Legacy**: Secret Manager secret named `client_id-{part_before_first_dot}`
Example: client_id `109370504310.apps.googleusercontent.com` → secret `client_id-109370504310`
**New**: Same naming convention. Phase 5's `SecretsStorage` can be used for this lookup, or direct SM client call.

### G4 — Missing `GET /auth/principal` endpoint
**Legacy**: Part of Flask Blueprint. Returns session profile or `{}`.
**New**: Add to Phase 4 implementation.

### G5 — Callback route name changed
**Legacy**: `GET /auth/authenticated`
**New**: `GET /auth/callback` (cleaner name, no compatibility concern — internal route)

### G6 — Post-login redirect simplified
**Legacy**: Stored original path + args in session; redirected back after callback.
**New MVP**: Hardcodes redirect to `/ui/test`. Backlog item: configurable redirect with allowlist.

---

## Settings Additions for Phase 4

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `GOOGLE_CLIENT_ID` | `str` | required | Google OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | `str` | `""` | Google OAuth2 client secret (dev only; prod uses SM) |
| `DEFAULT_CLIENT_ID` | `str` | `""` | Default Google OAuth client ID for /auth/refresh when not in request body |
| `CLIENT_ID_SUFFIX` | `str` | `.apps.googleusercontent.com` | Suffix appended to short-form client IDs |
| `SESSION_SECRET_KEY` | `str` | required | Secret key for `itsdangerous` session cookie signing |
| `SESSION_TTL` | `int` | `3600` | Session lifetime in seconds |

---

## Implementation Checklist

### `src/dockmaster/auth/oauth.py` — Authlib OAuth2 client

- [ ] Configure Authlib `OAuth` with Google:
  - [ ] Discovery URL: `https://accounts.google.com/.well-known/openid-configuration`
  - [ ] Scopes: `openid email profile`
  - [ ] PKCE: enabled
  - [ ] Client credentials from `Settings.GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`

### `src/dockmaster/sessions/protocol.py` — SessionStore protocol

```python
class SessionStore(Protocol):
    async def get(self, session_id: str) -> dict | None: ...
    async def set(self, session_id: str, data: dict, ttl: int = 3600) -> None: ...
    async def delete(self, session_id: str) -> None: ...
```

### `src/dockmaster/sessions/memory.py` — InMemorySessionStore

- [ ] `dict[str, tuple[dict, float]]` — maps session_id → (data, expiry_timestamp)
- [ ] Lazy TTL check on `get()` — return None if expired, delete entry
- [ ] `set()` — store with `time.time() + ttl` as expiry
- [ ] `delete()` — remove entry, idempotent

### `src/dockmaster/routes/login.py` — OAuth login routes

#### `GET /auth/login`
- [ ] Generate UUID4 state, store in in-memory dict (keyed by state) for CSRF
- [ ] Build Google authorization URL via Authlib
- [ ] Set `prompt=select_account`, `response_type=code`, `scope=openid email profile`
- [ ] Redirect to Google

#### `GET /auth/callback`
- [ ] Extract `code` and `state` from query params
- [ ] Validate `state` against stored value → 401 if mismatch
- [ ] Exchange code for tokens via Authlib
- [ ] Extract `id_token` claims (email, name, picture, etc.)
- [ ] Check `can_issue` on email domain (`AUTHORIZED_DOMAINS`) → 403 if not allowed
- [ ] Create session ID (UUID4), sign with `itsdangerous`
- [ ] Store session data in `SessionStore`: `{email, name, picture, given_name, family_name, locale, token_expiry}`
- [ ] Set signed `session_id` cookie: `HttpOnly=True, Secure=True, SameSite=Lax, Path=/`
- [ ] Redirect to `/ui/test`

#### `GET /auth/logout`
- [ ] Read `session_id` cookie, verify signature
- [ ] Delete session from `SessionStore`
- [ ] Clear `session_id` cookie
- [ ] Redirect to `/ui/test`

### `src/dockmaster/routes/login.py` — GET /auth/principal (NEW)

- [ ] Read `session_id` cookie
- [ ] Look up session in `SessionStore`
- [ ] If found and not expired: return `{email, name, picture, given_name, family_name, locale}`
- [ ] If not found or expired: return `{}`
- [ ] **No auth requirement** — endpoint is the auth check mechanism itself

### `src/dockmaster/routes/refresh.py` — POST /auth/refresh

#### Request body (Pydantic model)

```python
class RefreshTokenRequest(BaseModel):
    refresh_token: str          # NOTE: legacy used field name "token" — this is intentionally renamed
    client_id: str | None = None
    service: str | None = None
    expiry: int = 3600
```

> **API migration note**: The legacy `/refresh` endpoint used `"token"` as the field name for the refresh token.
> The new endpoint uses `"refresh_token"` for clarity. Clients migrating from legacy must update this field name.

#### Response body

```python
class RefreshResponse(BaseModel):
    token: str              # dockmaster JWT
    subject: str
    service: str
    expiry: int
    claims: dict            # profile claims (name, picture, etc.)
    id_token: str           # Google id_token from refresh
    access_token: str       # Google access_token from refresh
```

#### Implementation flow

- [ ] **Step 1: Resolve client_id**
  - [ ] Use `request.client_id` if provided, else `settings.DEFAULT_CLIENT_ID`
  - [ ] If still None → 400 "No client_id was specified and there is no default"
  - [ ] Normalize: if no `.` in client_id, append `settings.CLIENT_ID_SUFFIX`

- [ ] **Step 2: Load client secret from Secret Manager**
  - [ ] Extract name: `client_id.partition(".")[0]` (part before first dot)
  - [ ] Secret ID: `client_id-{name}` (e.g., `client_id-109370504310`)
  - [ ] Load via `SecretsStorage` (Phase 5) or direct SM call
  - [ ] On failure → 400 "Invalid client_id value"

- [ ] **Step 3: Exchange refresh token with Google**
  - [ ] `POST https://oauth2.googleapis.com/token`
  - [ ] Body (form-encoded `data=`): `{grant_type: refresh_token, refresh_token, client_id, client_secret}`
  - [ ] **Must use `data=` (form body), NOT `params=` (query string)** — this was a legacy bug, now fixed
  - [ ] Use `httpx.AsyncClient` with timeout (5s connect, 30s read)
  - [ ] On non-200 → 401 "Not authenticated"

- [ ] **Step 4: Verify returned id_token**
  - [ ] `ServiceRealm.verify(id_token)` — verify signature against cached keys

- [ ] **Step 5: Check can_issue** (ENFORCED — not just logged)
  - [ ] Check `claims["iss"]` in `AUTHORIZED_ISSUERS` → 403 if not
  - [ ] Check `claims["aud"]` in `AUTHORIZED_AUDIENCE` → 403 if not
  - [ ] Check email domain in `AUTHORIZED_DOMAINS` → 403 if not

- [ ] **Step 6: Call Google UserInfo API for profile**
  - [ ] `GET https://www.googleapis.com/oauth2/v3/userinfo`
  - [ ] `Authorization: Bearer {access_token}` (fresh access token from step 3)
  - [ ] On success: copy `name, picture, given_name, family_name, locale` into payload
  - [ ] On failure: log warning, continue with empty profile (non-fatal)

- [ ] **Step 7: Resolve service audience**
  - [ ] Use `request.service` if provided, else fall back to id_token's `aud`

- [ ] **Step 8: Sign dockmaster JWT**
  - [ ] `service_user.get_token(subject=email, service_name=service, expiry=request.expiry, payload=profile_claims)`

- [ ] **Return 200** with full `RefreshResponse`

### `src/dockmaster/routes/ui.py` — /ui/test

- [ ] `GET /ui/test` — serve Jinja2 template
- [ ] Inject session state (email, JWT claims) from `SessionStore` into template context

### `src/dockmaster/templates/login_test.html`

- [ ] Login button → `GET /auth/login`
- [ ] Logout button → `GET /auth/logout`
- [ ] Refresh button → `POST /auth/refresh` (HTMX or JS)
- [ ] Show current session state (logged-in user, JWT claims)
- [ ] Show result of refresh

### Tests

- [ ] `tests/test_sessions.py` — InMemorySessionStore: set/get/delete/TTL expiry
- [ ] `tests/test_login.py`:
  - [ ] `/auth/login` redirects to Google with correct params and CSRF state
  - [ ] `/auth/callback` exchanges code, creates session, sets cookie, redirects to `/ui/test`
  - [ ] `/auth/callback` with wrong state → 401
  - [ ] `/auth/logout` clears session and cookie
  - [ ] `/auth/principal` returns profile when session active; `{}` when not
  - [ ] All OAuth flows mocked (no real Google calls)
- [ ] `tests/test_refresh.py`:
  - [ ] Valid refresh token → 200 with dockmaster JWT + Google tokens
  - [ ] Missing client_id + no default → 400
  - [ ] SM lookup failure → 400
  - [ ] Google refresh non-200 → 401
  - [ ] can_issue failures → 403
  - [ ] `data=` form body used (not `params=`) — verify mock call args
  - [ ] UserInfo failure is non-fatal (warning logged, empty profile)
  - [ ] `service` and `expiry` body fields work correctly

### Acceptance gates

- [ ] `GET /auth/login` → redirects to Google with state + PKCE params
- [ ] `GET /auth/callback` → creates session, sets HttpOnly signed cookie, redirects to `/ui/test`
- [ ] `GET /auth/logout` → destroys session, clears cookie
- [ ] `GET /auth/principal` → `{email, name, ...}` or `{}`
- [ ] `POST /auth/refresh` → dockmaster JWT + Google tokens in response
- [ ] Session cookie: `HttpOnly=True, Secure=True, SameSite=Lax`
- [ ] Refresh uses `data=` form body (not query params) — legacy bug fixed
- [ ] `can_issue` enforced in refresh (not just logged) — legacy bug fixed
- [ ] `InMemorySessionStore` TTL works correctly
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] `just lint` and `just format` clean
- [ ] GCP Guide created: `docs/GUIDE-oauth-consent-screen.md`
