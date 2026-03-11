# Guide: Capture Google OAuth Fixtures for Phase 4 Tests

Captures real Google OAuth API responses as JSON fixture files used by unit tests.
Run commands in order from the repo root.

**Prerequisites**: OAuth consent screen configured, OAuth client ID created,
test user added, `.env` populated. See implementation progress for GCP setup checklist.

---

## 0. Setup

```bash
mkdir -p tests/fixtures/gcp/google_oauth
```

```bash
CLIENT_ID="525956676695-8o36ia4m8cvc4e00n4dhkjq2ko6ef4jk.apps.googleusercontent.com"
CLIENT_SECRET="$(grep CLIENT_SECRET .env | cut -d= -f2)"
REDIRECT_URI="http://localhost:8000/auth/callback"
FIXTURES="tests/fixtures/gcp/google_oauth"
```

Verify:

```bash
echo "CLIENT_ID=$CLIENT_ID"
echo "CLIENT_SECRET=$CLIENT_SECRET"
echo "REDIRECT_URI=$REDIRECT_URI"
```

---

## 1. Get an Authorization Code (browser required)

Build the authorization URL and open it in your browser:

```bash
STATE=$(uuidgen | tr '[:upper:]' '[:lower:]')
AUTH_URL="https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}&scope=openid%20email%20profile&state=${STATE}&prompt=select_account"
echo "$AUTH_URL"
```

1. Copy the URL and paste it into your browser
2. Sign in with your test user Google account
3. The browser will redirect to `http://localhost:8000/auth/callback?code=...&state=...`
4. **The server is NOT running**, so you'll see a connection error — that's fine
5. Copy the `code` value from the URL bar (everything after `code=` and before `&`)

```bash
AUTH_CODE="<paste-the-code-here>"
```

> **Note**: The auth code expires in ~10 minutes. Move quickly through the next steps.

---

## 2. Exchange Code for Tokens

```bash
curl -s -X POST "https://oauth2.googleapis.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "code=${AUTH_CODE}&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&redirect_uri=${REDIRECT_URI}&grant_type=authorization_code" \
  | jq '{
    request: {
      method: "POST",
      url: "https://oauth2.googleapis.com/token",
      headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body: "grant_type=authorization_code&code=REDACTED&client_id=REDACTED&client_secret=REDACTED&redirect_uri=REDACTED"
    },
    response: {
      status: 200,
      headers: {"content-type": "application/json"},
      body: (. | {
        access_token: "REDACTED_ACCESS_TOKEN",
        expires_in: .expires_in,
        refresh_token: "REDACTED_REFRESH_TOKEN",
        scope: .scope,
        token_type: .token_type,
        id_token: "REDACTED_ID_TOKEN"
      })
    }
  }' > $FIXTURES/token_exchange.json
```

**Before redacting, save the real tokens for the next steps:**

```bash
TOKENS=$(curl -s -X POST "https://oauth2.googleapis.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "code=${AUTH_CODE}&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&redirect_uri=${REDIRECT_URI}&grant_type=authorization_code")
echo "$TOKENS" | jq .

ACCESS_TOKEN=$(echo "$TOKENS" | jq -r '.access_token')
REFRESH_TOKEN=$(echo "$TOKENS" | jq -r '.refresh_token')
ID_TOKEN=$(echo "$TOKENS" | jq -r '.id_token')
```

**Now save the redacted fixture:**

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

Verify:

```bash
cat $FIXTURES/token_exchange.json | jq .response.body.scope
```

---

## 3. Call UserInfo API

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
      body: (. | walk(
        if type == "string" and test("^[0-9]+$") then "REDACTED_SUB"
        else . end
      ) | .sub = "REDACTED_SUB" | .picture = "REDACTED_PICTURE_URL")
    }
  }' > $FIXTURES/userinfo.json
```

Verify — should show name, email, etc. (with sub/picture redacted):

```bash
cat $FIXTURES/userinfo.json | jq .response.body
```

---

## 4. Refresh Token

```bash
REFRESH_RESPONSE=$(curl -s -X POST "https://oauth2.googleapis.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token&refresh_token=${REFRESH_TOKEN}&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}")
echo "$REFRESH_RESPONSE" | jq .

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

---

## 5. Tokeninfo (bonus — validates access tokens)

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

---

## 6. Verify All Fixtures

```bash
ls -la $FIXTURES/
```

Expected files:
- `tests/fixtures/gcp/google_oauth/token_exchange.json`
- `tests/fixtures/gcp/google_oauth/userinfo.json`
- `tests/fixtures/gcp/google_oauth/token_refresh.json`
- `tests/fixtures/gcp/google_oauth/tokeninfo.json`

Each file should have `request` and `response` keys:

```bash
for f in $FIXTURES/*.json; do echo "=== $(basename $f) ==="; jq 'keys' "$f"; done
```

---

## Notes

- The auth code is single-use — if step 2 fails, redo step 1
- Access tokens expire in ~1 hour. If step 3/4/5 fails with 401, redo from step 1
- Refresh tokens are long-lived but can be revoked; keep the real value safe
- All fixture files redact secrets (tokens, client_secret, sub). The response *shapes* and
  non-sensitive fields (expires_in, scope, token_type) are the valuable part
- These fixtures will be rotated post-Phase 4b (new client secret, new SA key)
