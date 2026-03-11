# Guide: Capture Google OAuth Fixtures for Phase 4 Tests

Captures real Google OAuth API responses as JSON fixture files used by unit tests.
Run every command in order from the repo root. Do not skip steps.

**Prerequisites**: OAuth consent screen configured, OAuth client ID created,
test user added, `.env` populated. See implementation progress for GCP setup checklist.

---

## 0. Create fixture directory

```bash
mkdir -p tests/fixtures/gcp/google_oauth
```

---

## 1. Set shell variables

```bash
CLIENT_ID="525956676695-8o36ia4m8cvc4e00n4dhkjq2ko6ef4jk.apps.googleusercontent.com"
CLIENT_SECRET="$(grep CLIENT_SECRET .env | cut -d= -f2)"
REDIRECT_URI="http://localhost:8000/auth/callback"
FIXTURES="tests/fixtures/gcp/google_oauth"
```

Verify all four are set:

```bash
echo "CLIENT_ID=$CLIENT_ID"
echo "CLIENT_SECRET=$CLIENT_SECRET"
echo "REDIRECT_URI=$REDIRECT_URI"
echo "FIXTURES=$FIXTURES"
```

---

## 2. Build the authorization URL and open it in your browser

```bash
STATE=$(uuidgen | tr '[:upper:]' '[:lower:]')
AUTH_URL="https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}&scope=openid%20email%20profile&state=${STATE}&prompt=consent&access_type=offline"
echo "$AUTH_URL"
```

1. Copy the printed URL
2. Paste it into your browser
3. Sign in with your test user Google account
4. The browser will redirect to `http://localhost:8000/auth/callback?code=...&state=...`
5. **The server is NOT running** — you will see a "connection refused" error. That is expected.
6. Look at the URL bar. Find the `code=` parameter.

---

## 3. Copy the auth code and URL-decode it

The code in the URL bar will be URL-encoded. The `%2F` sequences must be replaced with `/`.

**Example**: if the URL bar shows:
```
http://localhost:8000/auth/callback?code=4%2F0AfrIepBHIF...Fx_Cg&state=...
```

Then the decoded code is:
```
4/0AfrIepBHIF...Fx_Cg
```

Paste the raw URL-encoded code into `RAW_CODE`, then decode it:

```bash
RAW_CODE="PASTE_RAW_CODE_HERE"
AUTH_CODE=$(python3 -c "import urllib.parse; print(urllib.parse.unquote('${RAW_CODE}'))")
echo "$AUTH_CODE"
```

Verify the code starts with `4/` (not `4%2F`):

```bash
echo "$AUTH_CODE"
```

> **IMPORTANT**: The auth code is **single-use** and expires in ~10 minutes.
> If any step below fails, you must redo from step 2 to get a fresh code.
> Do NOT re-run a curl command that already consumed the code.

---

## 4. Exchange code for tokens (save to variable FIRST)

This is the only command that uses the auth code. Run it exactly once.

```bash
TOKENS=$(curl -s -X POST "https://oauth2.googleapis.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "code=${AUTH_CODE}&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&redirect_uri=${REDIRECT_URI}&grant_type=authorization_code")
```

Check the response — it must contain `access_token`, NOT `error`:

```bash
echo "$TOKENS" | jq .
```

**If you see `"error": "invalid_grant"`**: the code was already used or expired.
Go back to step 2 and get a fresh code.

**If you see a JSON object with `access_token`, `refresh_token`, `id_token`**: success! Continue.

---

## 5. Extract tokens into shell variables

```bash
ACCESS_TOKEN=$(echo "$TOKENS" | jq -r '.access_token')
REFRESH_TOKEN=$(echo "$TOKENS" | jq -r '.refresh_token')
ID_TOKEN=$(echo "$TOKENS" | jq -r '.id_token')
```

Verify none of them are `null`:

```bash
echo "ACCESS_TOKEN=${ACCESS_TOKEN:0:20}..."
echo "REFRESH_TOKEN=${REFRESH_TOKEN:0:20}..."
echo "ID_TOKEN=${ID_TOKEN:0:20}..."
```

All three should show a truncated token string, not `null...`.

---

## 6. Save redacted token_exchange fixture

```bash
echo "$TOKENS" | jq '{
  request: {
    method: "POST",
    url: "https://oauth2.googleapis.com/token",
    headers: {"Content-Type": "application/x-www-form-urlencoded"},
    body: "grant_type=authorization_code&code=REDACTED&client_id=REDACTED&client_secret=REDACTED&redirect_uri=REDACTED"
  },
  response: {
    status: 200,
    headers: {"content-type": "application/json"},
    body: {
      access_token: "REDACTED_ACCESS_TOKEN",
      expires_in: .expires_in,
      refresh_token: "REDACTED_REFRESH_TOKEN",
      scope: .scope,
      token_type: .token_type,
      id_token: "REDACTED_ID_TOKEN"
    }
  }
}' > $FIXTURES/token_exchange.json
```

Verify — `scope` should show `"openid ... email profile"`, not `null`:

```bash
cat $FIXTURES/token_exchange.json | jq .response.body.scope
```

---

## 7. Call UserInfo API and save fixture

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://www.googleapis.com/oauth2/v3/userinfo" \
  | jq '{
    request: {
      method: "GET",
      url: "https://www.googleapis.com/oauth2/v3/userinfo",
      headers: {"Authorization": "Bearer REDACTED_ACCESS_TOKEN"}
    },
    response: {
      status: 200,
      headers: {"content-type": "application/json"},
      body: (. | .sub = "REDACTED_SUB" | .picture = "REDACTED_PICTURE_URL")
    }
  }' > $FIXTURES/userinfo.json
```

Verify — should show your name and email (sub and picture redacted):

```bash
cat $FIXTURES/userinfo.json | jq .response.body
```

**If you see `"error": "invalid_request"`**: the access token is bad. Go back to step 2.

---

## 8. Refresh the token and save fixture

```bash
REFRESH_RESPONSE=$(curl -s -X POST "https://oauth2.googleapis.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token&refresh_token=${REFRESH_TOKEN}&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}")
```

Check — must contain `access_token`, NOT `error`:

```bash
echo "$REFRESH_RESPONSE" | jq .
```

Save redacted fixture:

```bash
echo "$REFRESH_RESPONSE" | jq '{
  request: {
    method: "POST",
    url: "https://oauth2.googleapis.com/token",
    headers: {"Content-Type": "application/x-www-form-urlencoded"},
    body: "grant_type=refresh_token&refresh_token=REDACTED&client_id=REDACTED&client_secret=REDACTED"
  },
  response: {
    status: 200,
    headers: {"content-type": "application/json"},
    body: {
      access_token: "REDACTED_ACCESS_TOKEN",
      expires_in: .expires_in,
      scope: .scope,
      token_type: .token_type,
      id_token: "REDACTED_ID_TOKEN"
    }
  }
}' > $FIXTURES/token_refresh.json
```

Verify:

```bash
cat $FIXTURES/token_refresh.json | jq .response.body.expires_in
```

Should print `3600` (or similar number), not `null`.

---

## 9. Tokeninfo and save fixture

```bash
curl -s "https://oauth2.googleapis.com/tokeninfo?access_token=$ACCESS_TOKEN" \
  | jq '{
    request: {
      method: "GET",
      url: "https://oauth2.googleapis.com/tokeninfo?access_token=REDACTED",
      headers: {}
    },
    response: {
      status: 200,
      headers: {"content-type": "application/json"},
      body: (. | .azp = "REDACTED_CLIENT_ID" | .aud = "REDACTED_CLIENT_ID" | .sub = "REDACTED_SUB")
    }
  }' > $FIXTURES/tokeninfo.json
```

Verify:

```bash
cat $FIXTURES/tokeninfo.json | jq .response.body.scope
```

---

## 10. Verify all fixtures

```bash
ls -la $FIXTURES/
```

Expected files:
- `token_exchange.json`
- `userinfo.json`
- `token_refresh.json`
- `tokeninfo.json`

Check each has valid `request` and `response` keys:

```bash
for f in $FIXTURES/*.json; do
  echo "=== $(basename $f) ==="
  jq 'keys' "$f"
  echo ""
done
```

Every file should print:

```json
[
  "request",
  "response"
]
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `"error": "invalid_grant"` in step 4 | Code was already used or expired | Redo from step 2 |
| `"error": "invalid_request"` in step 7 | Access token is null or expired | Check step 5 variables; redo from step 2 if null |
| `AUTH_CODE` contains `%2F` | URL encoding not decoded | Use the python3 decode command in step 3 |
| `scope` is `null` in fixtures | Token exchange failed silently | Check `echo "$TOKENS" \| jq .` — if it has `error`, redo from step 2 |
| `REFRESH_TOKEN` is `null` | Auth URL missing `access_type=offline` | Redo step 2 with `&access_type=offline&prompt=consent` in the URL |
| Browser shows "Access blocked" | Test user not added to consent screen | Add your email at Console → OAuth consent screen → Test users |

---

## Notes

- Auth codes are **single-use**. Every failed attempt requires a new browser login.
- Access tokens expire in ~1 hour. If later steps fail with 401, redo from step 2.
- Refresh tokens are long-lived but will be rotated post-Phase 4b.
- All fixture files redact secrets. The response **shapes** and non-sensitive fields
  (`expires_in`, `scope`, `token_type`) are what tests use.
- These fixtures and all GCP credentials will be rotated after Phase 4b is complete.
