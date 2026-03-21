---
state: Finalized
changelog:
  "2026-03-21 00h": "Created from Phase 11 route reorg completion. Covers GCP reconfig + manual testing."
---

# Phase 11 Post-Deploy: GCP Reconfiguration & Manual Verification

> Checklist for reconfiguring GCP OAuth credentials and manually verifying all
> route changes from Phase 11 (Steps A-G). Run this before starting Step H.

**Status**: TODO — run after deploying Phase 11 route reorg
**Prerequisite**: Steps A-G committed and deployed

---

## 1. Update GCP OAuth Redirect URIs

In **Google Cloud Console** → **APIs & Services** → **Credentials** → your OAuth client:

**Remove** (old):
- `http://localhost:8000/auth/callback`
- Any production `/auth/callback` entries

**Add** (new):
- `http://localhost:8000/auth/login/callback` (local dev)
- `http://localhost:8000/auth/cli/callback` (CLI local dev)
- `https://<your-prod-domain>/auth/login/callback` (production)
- `https://<your-prod-domain>/auth/cli/callback` (production)

- [ ] Old redirect URIs removed
- [ ] New redirect URIs added
- [ ] Changes saved in GCP console

---

## 2. Verify Browser Login (Cookie Flow)

```bash
# Start the server
uv run uvicorn dockmaster.main:app --reload

# Open in browser — should redirect to Google, then back to /ui/
open http://localhost:8000/auth/login
```

- [ ] Redirects to Google consent screen
- [ ] After auth, redirects to /ui/ with session_id cookie
- [ ] /ui/ dashboard shows user email

---

## 3. Verify Browser Login with return_to

```bash
# Should redirect to /ui/roles after login instead of /ui/
open "http://localhost:8000/auth/login?return_to=/ui/roles"
```

- [ ] Redirects to /ui/roles after login (not /ui/)
- [ ] Absolute URL return_to is ignored (falls back to /ui/)

---

## 4. Verify CLI Login Flow

```bash
# CLI login — should open browser, redirect to Google, then back to localhost
uv run dockmaster login
```

- [ ] Browser opens to /auth/cli/login?redirect_uri=http://localhost:PORT/callback
- [ ] After Google auth, redirects to localhost with ?token=JWT
- [ ] CLI captures and stores the token
- [ ] Token has 15-min TTL, aud=dockmaster

---

## 5. Verify External App Flow (Refresh Token)

```bash
BASE=http://localhost:8000

# Step 1: Start login with redirect_uri (must be in ALLOWED_REDIRECT_URIS)
open "$BASE/auth/login?redirect_uri=http://localhost:3000/callback&return_to=/dashboard"

# Step 2: After Google auth, browser redirects to:
#   http://localhost:3000/callback?code=TICKET_CODE&state=STATE
# Capture the code from the URL

# Step 3: Exchange the ticket for refresh_token + profile
curl -s -X POST "$BASE/auth/login/exchange" \
  -H "Content-Type: application/json" \
  -d '{"code": "TICKET_CODE", "redirect_uri": "http://localhost:3000/callback"}' | jq .

# Step 4: Use refresh_token to get a service JWT
curl -s -X POST "$BASE/auth/session/token?service=billing" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "THE_REFRESH_TOKEN"}' | jq .
```

- [ ] Login redirects to Google, then to redirect_uri with ?code=...&state=...
- [ ] Exchange returns { refresh_token, profile, return_to: "/dashboard" }
- [ ] refresh_token works with /auth/session/token to get a service JWT

---

## 6. Verify Logout

```bash
# Cookie logout (browser)
curl -s -X POST "$BASE/auth/logout" -b "session_id=SIGNED_COOKIE" -v
# Expected: 302 redirect to /ui/, cookie cleared

# Refresh token logout (API)
curl -s -X POST "$BASE/auth/logout" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "THE_REFRESH_TOKEN"}'
# Expected: 302 redirect (will become JSON response in Step H)
```

- [ ] Cookie logout: 302 to /ui/, cookie cleared, session destroyed
- [ ] Refresh token logout: session destroyed (redirect for now, JSON after Step H)

---

## 7. Verify Old Routes Are Gone

```bash
curl -s "$BASE/auth/callback" | jq .                    # 404
curl -s -X POST "$BASE/auth/token" | jq .               # 404
curl -s -X POST "$BASE/auth/exchange" | jq .             # 404
curl -s -X POST "$BASE/auth/code/exchange" | jq .        # 404
curl -s -X POST "$BASE/auth/login/code" | jq .           # 404
```

- [ ] /auth/callback → 404 (moved to /auth/login/callback)
- [ ] /auth/token → 404 (moved to /auth/session/token)
- [ ] /auth/exchange → 404 (moved to /auth/service/token)
- [ ] /auth/code/exchange → 404 (deleted, replaced by /auth/login/exchange)
- [ ] /auth/login/code → 404 (renamed to /auth/login/exchange)

---

## 8. Run Full Suite

```bash
just check   # lint + format + types + tests
```

- [ ] All tests pass
- [ ] Lint clean
- [ ] Format clean

---

## Final Route Map (for reference)

```
# Login flow (cookie + refresh token)
GET  /auth/login              — start OAuth (accepts redirect_uri, return_to)
GET  /auth/login/callback     — Google OAuth callback
POST /auth/login/exchange     — exchange login ticket for {refresh_token, profile, return_to}
POST /auth/logout             — destroy session (cookie or refresh_token body)

# CLI flow
GET  /auth/cli/login          — start CLI OAuth (localhost redirect_uri)
GET  /auth/cli/callback       — Google OAuth callback → JWT → redirect to localhost
POST /auth/cli/token          — issue Type C JWT from Bearer JWT

# Session-gated (cookie or refresh_token)
GET  /auth/session/principal  — session user profile
POST /auth/session/token      — issue Type C JWT for a service
GET  /auth/session/list       — user's active sessions

# Service-to-service
POST /auth/service/token      — exchange Google credential for Type C JWT

# API (JWT-gated)
GET  /auth/has                — permission check (query params)
GET  /auth/has/{s}/{t}/{p}    — permission check (path params)
GET  /auth/grants             — resolved permissions
GET  /auth/claims             — decoded JWT claims
GET  /auth/keys               — public JWKS
GET  /auth/health             — health check

# Admin API (JWT + admin permission)
/admin/*                      — CRUD for roles, grants, sessions

# Admin UI (session + soft auth via check_ui_session)
/ui/*                         — dashboard, login, roles, grants, sessions
```
