# Guide: Capture Phase 4b Fixtures — Secret Manager + Refresh E2E

Validates the Phase 4b refresh flow end-to-end against real GCP and captures
the Secret Manager fixture. Run every command in order from the repo root.

**Prerequisites**:
- Phase 4a fixtures already captured (you have a working `REFRESH_TOKEN`)
- `.env` populated with `SECRETS_PROJECT`, `CLIENT_ID`, `CLIENT_SECRET`, `SA_KEY_FILE`
- Dockmaster SA has `roles/secretmanager.secretAccessor` on the project
- OAuth client secret stored in Secret Manager (see GCP setup checklist)

---

## Part A: Capture Secret Manager Fixture

### A1. Set shell variables

```bash
SECRETS_PROJECT="$(grep SECRETS_PROJECT .env | cut -d= -f2)"
CLIENT_ID="$(grep CLIENT_ID .env | head -1 | cut -d= -f2)"
FIXTURES="tests/fixtures/gcp/secret_manager"
```

Derive the secret name from the client ID (part before first dot):

```bash
CLIENT_NAME="${CLIENT_ID%%.*}"
SECRET_ID="client_id-${CLIENT_NAME}"
echo "PROJECT=$SECRETS_PROJECT"
echo "SECRET_ID=$SECRET_ID"
```

Verify both are set and the secret ID looks like `client_id-525956676695` (numbers match
your OAuth client ID).

---

### A2. Create fixture directory

```bash
mkdir -p $FIXTURES
```

---

### A3. Access the secret via gcloud

```bash
SM_RESPONSE=$(gcloud secrets versions access latest \
  --secret="$SECRET_ID" \
  --project="$SECRETS_PROJECT" 2>&1)
```

Check the output — it should be the raw client secret string (not an error):

```bash
echo "${SM_RESPONSE:0:10}..."
```

**If you see `NOT_FOUND`**: the secret doesn't exist yet. Create it:

```bash
CLIENT_SECRET="$(grep CLIENT_SECRET .env | cut -d= -f2)"
gcloud secrets create "$SECRET_ID" \
  --project="$SECRETS_PROJECT" \
  --replication-policy="automatic"
echo -n "$CLIENT_SECRET" | gcloud secrets versions add "$SECRET_ID" \
  --project="$SECRETS_PROJECT" \
  --data-file=-
```

Then re-run A3.

**If you see `PERMISSION_DENIED`**: the SA needs `secretmanager.secretAccessor`. Fix IAM
and retry.

---

### A4. Save redacted Secret Manager fixture

```bash
cat > $FIXTURES/get_client_secret.json << 'FIXTURE'
{
  "request": {
    "method": "gRPC",
    "service": "google.cloud.secretmanager.v1.SecretManagerService",
    "rpc": "AccessSecretVersion",
    "resource": "projects/PROJECT/secrets/SECRET_ID/versions/latest"
  },
  "response": {
    "status": "OK",
    "payload": {
      "data": "REDACTED_CLIENT_SECRET"
    },
    "notes": "Secret value is the raw OAuth client_secret string (not JSON)"
  }
}
FIXTURE
```

Edit the fixture to fill in your actual project and secret ID (but keep the value redacted):

```bash
sed -i '' "s|PROJECT|$SECRETS_PROJECT|g; s|SECRET_ID|$SECRET_ID|g" $FIXTURES/get_client_secret.json
```

Verify:

```bash
cat $FIXTURES/get_client_secret.json | jq .
```

---

### A5. Verify SecretsStorage works in Python

This proves the `SecretsStorage` class can actually load the secret from real SM:

```bash
uv run python -c "
from google.cloud.secretmanager_v1 import SecretManagerServiceClient
from dockmaster.rbac.storage import SecretsStorage

client = SecretManagerServiceClient()
storage = SecretsStorage(client=client, project='$SECRETS_PROJECT')

secret = storage.get_client_secret('$CLIENT_ID')
print(f'SUCCESS: got secret, length={len(secret)}, starts_with={secret[:4]}...')
"
```

**Expected**: `SUCCESS: got secret, length=XX, starts_with=GOCSP...` (or similar).

**If you see `NotFound`**: the secret name doesn't match. Check the naming convention —
`client_id-{part_before_first_dot}`. Verify with:

```bash
gcloud secrets list --project="$SECRETS_PROJECT" --filter="name:client_id"
```

---

## Part B: End-to-End Refresh Flow

This proves the full 8-step refresh chain works against real services.

### B1. Get a fresh refresh token (if needed)

If you still have a valid `REFRESH_TOKEN` from the Phase 4a capture guide, reuse it:

```bash
REFRESH_TOKEN="PASTE_YOUR_REFRESH_TOKEN_HERE"
echo "REFRESH_TOKEN=${REFRESH_TOKEN:0:20}..."
```

If you don't have one, follow steps 2–5 of `GUIDE-capture-oauth-fixtures.md` to get a
fresh one. Make sure the auth URL includes `access_type=offline&prompt=consent` to get
a refresh token.

---

### B2. Start the dev server

In a separate terminal:

```bash
uv run uvicorn dockmaster.main:app --reload --port 8000
```

Watch the startup logs — you should see:
- `auth singletons initialized`
- `session store initialized`
- `oauth client initialized`
- `secrets storage initialized`

If `secrets storage initialized` is missing, check that `SECRETS_PROJECT` is in your `.env`.

---

### B3. Hit the refresh endpoint with curl

```bash
curl -s -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{
    \"refresh_token\": \"$REFRESH_TOKEN\",
    \"service\": \"test-service\",
    \"expiry\": 3600
  }" | jq .
```

**Expected response** (200 OK):

```json
{
  "token": "eyJhbGciOiJSUzI1NiI...",
  "subject": "you@yourdomain.com",
  "service": "test-service",
  "expiry": 3600,
  "claims": {
    "name": "Your Name",
    "picture": "https://...",
    "given_name": "...",
    "family_name": "...",
    "locale": "en"
  },
  "id_token": "eyJhbGciOiJSUzI1NiI...",
  "access_token": "ya29..."
}
```

### B3 checklist — verify each step worked

| Check | How to verify |
|-------|--------------|
| Step 1: client_id resolved | No `400 No client_id` error |
| Step 2: SM lookup | No `400 Invalid client_id` error |
| Step 3: Google refresh | No `401 Not authenticated` error |
| Step 4: id_token verified | No `401` with verification error |
| Step 5: can_issue passed | No `403` errors |
| Step 6: UserInfo fetched | `claims` object has `name`, `picture`, etc. (non-empty) |
| Step 7: service resolved | `"service": "test-service"` (matches what you sent) |
| Step 8: JWT signed | `"token"` field is a long JWT string starting with `eyJ` |

---

### B4. Verify the dockmaster JWT

Decode the returned JWT to check its claims:

```bash
TOKEN="PASTE_TOKEN_FROM_RESPONSE"
uv run python -c "
import jwt
decoded = jwt.decode('$TOKEN', options={'verify_signature': False})
import json
print(json.dumps(decoded, indent=2))
"
```

Expected claims: `iss` (your SA email), `sub` (your email), `aud` (test-service),
`iat`/`exp` timestamps, plus profile claims.

---

### B5. Test error cases

**Missing refresh token (expect 422)**:

```bash
curl -s -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
```

**Bad refresh token (expect 401)**:

```bash
curl -s -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "bad-token"}' | jq .
```

**No default client_id — only works if DEFAULT_CLIENT_ID is unset in .env**:

```bash
curl -s -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "any", "client_id": "nonexistent"}' | jq .
```

Expected: `400 Invalid client_id value` (SM lookup fails).

---

## Part C: Verification Checklist

Before moving on, confirm all of these:

- [ ] `tests/fixtures/gcp/secret_manager/get_client_secret.json` exists and looks correct
- [ ] `SecretsStorage.get_client_secret()` works against real SM (A5 passed)
- [ ] `POST /auth/refresh` returned 200 with valid dockmaster JWT (B3 passed)
- [ ] JWT claims contain correct `iss`, `sub`, `aud`, `exp` (B4 passed)
- [ ] `claims` in response has profile data from UserInfo (non-empty)
- [ ] Error cases return expected status codes (B5 passed)

Once all checks pass, Phase 4b tracer bullet is validated.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `503 Secrets storage not configured` | `SECRETS_PROJECT` missing from `.env` | Add it and restart server |
| `400 Invalid client_id value` | SM secret name mismatch | Check `gcloud secrets list` vs naming convention |
| `401 Not authenticated` (step 3) | Refresh token expired or revoked | Get fresh token via OAuth guide steps 2-5 |
| `401` after step 3 (verification) | Key cache can't fetch public keys | Check SA_KEY_FILE is set and SA has `iam.serviceAccountViewer` role |
| `403 Issuer not allowed` | `AUTHORIZED_ISSUERS` doesn't include Google | Add `https://accounts.google.com` to `.env` |
| `403 Audience not allowed` | `AUTHORIZED_AUDIENCE` doesn't include your client ID | Add your full client ID to `AUTHORIZED_AUDIENCE` |
| `403 Domain not allowed` | Your email domain not in `AUTHORIZED_DOMAINS` | Add your domain to `.env` |
| `claims` is `{}` | UserInfo call failed (non-fatal) | Check server logs for `userinfo_fetch_failed` |
| SM `PERMISSION_DENIED` | SA lacks `secretmanager.secretAccessor` | Grant role via IAM console or gcloud |
