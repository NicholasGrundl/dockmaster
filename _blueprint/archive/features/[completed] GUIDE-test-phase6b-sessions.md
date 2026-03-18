# Guide: Manual Testing — Phase 6b Session Revocation

Tests session management end-to-end with two user accounts (one in incognito).

**Prerequisites**:
- `.env` fully populated (OAuth, SA keys, admin emails)
- Both test user emails added to OAuth consent screen test users
- At least one test email in `DOCKMASTER_ADMIN_EMAILS`
- Dev server not running yet

---

## Setup

### 1. Verify admin email is configured

```bash
grep DOCKMASTER_ADMIN_EMAILS .env
```

Should include your primary test email. The second test email should NOT be an admin
(so you can test the non-admin dashboard view).

### 2. Start the dev server

```bash
uv run uvicorn dockmaster.main:app --reload --port 8000
```

Watch for all singletons initializing (signer, realm, oauth, secrets, authority, admin_storage).

---

## Test 1: Dashboard — User sees only their own sessions

### 1a. Login as User A (primary browser)

1. Open http://localhost:8000/ui/login
2. Click "Sign in with Google" → authenticate as User A (admin email)
3. You should land on the dashboard at `/ui/`
4. **Check**: "Your Sessions" section shows 1 session (yours)
5. **Check**: Admin nav shows Dashboard, Roles, Grants, Sessions links

### 1b. Login as User B (incognito window)

1. Open an incognito/private window
2. Go to http://localhost:8000/ui/login
3. Click "Sign in with Google" → authenticate as User B (non-admin email)
4. You should land on the dashboard at `/ui/`
5. **Check**: "Your Sessions" shows 1 session (User B's only — NOT User A's)
6. **Check**: Admin nav should NOT show Roles, Grants, Sessions links (User B is not admin)

### 1c. Verify User A's dashboard updated

1. Go back to the primary browser
2. Refresh http://localhost:8000/ui/
3. **Check**: "Your Sessions" still shows only User A's session(s), not User B's

---

## Test 2: Admin Sessions Page

### 2a. Navigate to sessions page (as User A / admin)

1. In the primary browser (User A, admin), click "Sessions" in the nav
2. **Check**: URL is `/ui/sessions`
3. **Check**: Table shows ALL active sessions (both User A and User B)
4. **Check**: Each row shows email, name, expiry, truncated session ID, and a "Revoke" button
5. **Check**: "Revoke by Email" form is visible at the top

---

## Test 3: Revoke a single session via UI

### 3a. Revoke User B's session

1. On the sessions page, find User B's session row
2. Click "Revoke" → confirm the dialog
3. **Check**: Success message appears ("Session revoked")
4. **Check**: User B's session is gone from the table
5. **Check**: User A's session is still there

### 3b. Verify User B is logged out

1. Go to the incognito window (User B)
2. Refresh http://localhost:8000/ui/
3. **Check**: User B is redirected to `/ui/login` (session was revoked)

---

## Test 4: Revoke by email via UI

### 4a. Re-login User B

1. In incognito, log in again as User B
2. Optionally, open another incognito window and log in as User B again (to create 2 sessions)

### 4b. Revoke all sessions for User B's email

1. In primary browser (User A, admin), go to `/ui/sessions`
2. In the "Revoke by Email" form, enter User B's email
3. Click "Revoke All" → confirm
4. **Check**: Success message shows count (e.g., "2 session(s) revoked for user-b@...")
5. **Check**: All User B sessions gone from table

### 4c. Verify User B is logged out

1. Refresh User B's incognito windows
2. **Check**: Both redirect to `/ui/login`

---

## Test 5: Admin API endpoints (curl)

You need a dockmaster JWT (Bearer token) for API calls. Sign one locally using your SA key —
no exchange or Google auth needed:

```bash
ADMIN_EMAIL="YOUR_ADMIN_EMAIL_HERE"
TOKEN=$(uv run python -c "
from dockmaster.config import Settings
from dockmaster.auth.jwt_signer import ServiceUser
settings = Settings()
signer = ServiceUser(settings.sa_key_file)
print(signer.get_token(subject='$ADMIN_EMAIL', service_name='dockmaster', expiry=900))
")
echo "TOKEN=${TOKEN:0:30}..."
```

**Note**: The email must be in `DOCKMASTER_ADMIN_EMAILS` or have the `admin` RBAC role.

### Verify the token works

```bash
curl -s http://localhost:8000/auth/claims \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected**: Your claims with `sub`, `iss`, `aud`, `exp` etc.

### 5a. List all sessions

```bash
curl -s http://localhost:8000/admin/sessions \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected**: JSON object with session IDs as keys.

### 5b. List sessions by email

```bash
curl -s http://localhost:8000/admin/sessions/email/USER_A_EMAIL \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected**: Only sessions for that email.

### 5c. Revoke a session by ID

Pick a session ID from the list response:

```bash
curl -s -X DELETE http://localhost:8000/admin/sessions/id/SESSION_ID \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected**: `{"revoked": true, "session_id": "SESSION_ID"}`

### 5d. Revoke by email

```bash
curl -s -X DELETE http://localhost:8000/admin/sessions/email/USER_B_EMAIL \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected**: `{"revoked": N, "email": "USER_B_EMAIL"}`

### 5e. Revoke nonexistent session (expect 404)

```bash
curl -s -X DELETE http://localhost:8000/admin/sessions/id/nonexistent \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected**: 404 with `"Session 'nonexistent' not found"`

---

## Test 6: User endpoint — GET /auth/sessions

### 6a. As logged-in user (browser)

1. In the primary browser (User A), open the browser dev tools → Console
2. Run:

```javascript
fetch('/auth/sessions').then(r => r.json()).then(d => console.log(d))
```

3. **Check**: Returns only User A's sessions (not all sessions)

### 6b. Without session (expect empty)

```bash
curl -s http://localhost:8000/auth/sessions | jq .
```

**Expected**: `{}` (no session cookie)

---

## Verification Checklist

- [ ] Dashboard shows only current user's sessions ("Your Sessions")
- [ ] Non-admin user cannot see Sessions nav link
- [ ] Admin sessions page shows all sessions
- [ ] Single session revoke works (UI + API)
- [ ] Revoke by email works (UI + API)
- [ ] Revoked user is redirected to login on next request
- [ ] `GET /auth/sessions` returns only current user's sessions
- [ ] 404 returned for revoking nonexistent session
- [ ] Revoke by email returns 0 count for unknown email (not an error)
