# Auth Code Flow — Manual E2E Test Guide

This guide walks through testing the OAuth auth code flow end-to-end against a
live dev server. The auth code flow allows external services to authenticate
users through dockmaster and receive a JWT.

## Prerequisites

1. Dev server running: `uv run uvicorn dockmaster.main:app --reload`
2. `.env` configured with valid Google OAuth credentials
3. `ALLOWED_REDIRECT_URIS` set in `.env` (see Setup below)
4. `jq` installed (`brew install jq`)

## Setup

Add the test redirect URI and CORS origin to your `.env`:

```bash
ALLOWED_REDIRECT_URIS=http://localhost:3000/callback
ALLOWED_ORIGINS=http://localhost:3000
```

This simulates an external SPA at `localhost:3000` that uses dockmaster for auth.

Restart the dev server after changing `.env`.

## Test 1: Auth Code Flow (full round-trip)

**What we're testing:** Login → Google → auth code → exchange → JWT.

### Step 1: Open in browser

```
http://localhost:8000/auth/login?redirect_uri=http://localhost:3000/callback
```

### Step 2: Complete Google sign-in

Sign in with a Google account in your `AUTHORIZED_DOMAINS`.

### Step 3: Capture the redirect URL

Copy the full URL from your browser address bar and paste it:

```bash
REDIRECT_URL="<paste full URL here>"
CODE=$(echo "$REDIRECT_URL" | sed 's/.*[?&]code=\([^&]*\).*/\1/')
echo "Code: $CODE"
```

### Step 4: Exchange code for JWT and decode claims

```bash
RESPONSE=$(curl -s -X POST http://localhost:8000/auth/code/exchange \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"$CODE\", \"redirect_uri\": \"http://localhost:3000/callback\"}")

echo "$RESPONSE" | jq .

TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')
echo "$TOKEN" | cut -d. -f2 | tr '_-' '/+' | awk '{while(length%4)$0=$0"=";print}' | base64 -d | jq .
```

Expected: `access_token` present, `token_type: "bearer"`, `expires_in: 900`,
claims show your email as `sub`, `iss: "dockmaster"`.

---

## Test 2: Code is single-use

Re-run the exchange with the same code (don't get a new one):

```bash
curl -s -X POST http://localhost:8000/auth/code/exchange \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"$CODE\", \"redirect_uri\": \"http://localhost:3000/callback\"}" | jq .
```

Expected: `{"detail": "Invalid or expired authorization code"}` (HTTP 400)

---

## Test 3: Wrong redirect_uri is rejected

Get a fresh code (repeat Test 1 steps 1–3), then exchange with wrong URI:

```bash
REDIRECT_URL="<paste fresh URL here>"
CODE=$(echo "$REDIRECT_URL" | sed 's/.*[?&]code=\([^&]*\).*/\1/')

curl -s -X POST http://localhost:8000/auth/code/exchange \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"$CODE\", \"redirect_uri\": \"http://localhost:9999/wrong\"}" | jq .
```

Expected: HTTP 400

---

## Test 4: Non-allowlisted redirect_uri is rejected

Open in browser:

```
http://localhost:8000/auth/login?redirect_uri=https://evil.com/callback
```

Expected: HTTP 400 — "Invalid redirect_uri: not in allowlist"

---

## Test 5: CLI flow still works

```bash
uv run dockmaster login
uv run dockmaster token billing
```

The CLI should still use direct JWT delivery (not auth codes). Verify the token:

```bash
uv run dockmaster token billing | cut -d. -f2 | tr '_-' '/+' | awk '{while(length%4)$0=$0"=";print}' | base64 -d | jq .
```

---

## Test 6: CORS headers

```bash
curl -s -D - -o /dev/null -X OPTIONS http://localhost:8000/auth/code/exchange \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type"
```

Expected headers in output:

```
access-control-allow-origin: http://localhost:3000
access-control-allow-credentials: true
```

Verify a disallowed origin gets no CORS headers:

```bash
curl -s -D - -o /dev/null -X OPTIONS http://localhost:8000/auth/code/exchange \
  -H "Origin: https://evil.com" \
  -H "Access-Control-Request-Method: POST"
```

Expected: no `access-control-allow-origin` header.

---

## Checklist

- [ ] Test 1: Auth code flow produces a valid JWT with correct claims
- [ ] Test 2: Code is single-use (replay returns 400)
- [ ] Test 3: Wrong redirect_uri returns 400
- [ ] Test 4: Non-allowlisted redirect_uri rejected at login
- [ ] Test 5: CLI login + token still works
- [ ] Test 6: CORS headers present for allowed origins, absent for others
