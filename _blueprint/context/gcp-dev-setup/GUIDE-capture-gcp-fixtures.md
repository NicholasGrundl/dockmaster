# Guide: Capture GCP Fixtures for Phase 2 Tests

Captures real GCP API responses as JSON fixture files used by unit tests.
Run commands in order from the repo root.

---

## 0. Setup

```
mkdir -p tests/fixtures/gcp/iam tests/fixtures/gcp/google_oidc
```

```
PROJECT="insilicostrategy-platform"
SA="dockmaster@insilicostrategy-platform.iam.gserviceaccount.com"
TOKEN=$(gcloud auth print-access-token)
FIXTURES="tests/fixtures/gcp"
```

---

## 1. Google OIDC Certs (no auth required)

```
curl -s https://www.googleapis.com/oauth2/v1/certs | jq '{request: {method: "GET", url: "https://www.googleapis.com/oauth2/v1/certs", headers: {}}, response: {status: 200, headers: {"content-type": "application/json"}, body: .}}' > $FIXTURES/google_oidc/v1_certs.json
```

---

## 2. IAM — List Service Accounts

```
curl -s -H "Authorization: Bearer $TOKEN" "https://iam.googleapis.com/v1/projects/$PROJECT/serviceAccounts?pageSize=50" | jq '{request: {method: "GET", url: "https://iam.googleapis.com/v1/projects/REDACTED_PROJECT/serviceAccounts?pageSize=50", headers: {}}, response: {status: 200, headers: {"content-type": "application/json"}, body: (. | walk(if type == "string" then gsub("insilicostrategy-platform"; "REDACTED_PROJECT") | gsub("dockmaster@insilicostrategy-platform.iam.gserviceaccount.com"; "REDACTED_SA_EMAIL") else . end))}}' > $FIXTURES/iam/list_service_accounts.json
```

---

## 3. IAM — List Keys for Dockmaster SA

```
curl -s -H "Authorization: Bearer $TOKEN" "https://iam.googleapis.com/v1/projects/$PROJECT/serviceAccounts/$SA/keys?keyTypes=USER_MANAGED" | jq '{request: {method: "GET", url: "https://iam.googleapis.com/v1/projects/REDACTED_PROJECT/serviceAccounts/REDACTED_SA_EMAIL/keys?keyTypes=USER_MANAGED", headers: {}}, response: {status: 200, headers: {"content-type": "application/json"}, body: (. | walk(if type == "string" then gsub("insilicostrategy-platform"; "REDACTED_PROJECT") | gsub("dockmaster@insilicostrategy-platform.iam.gserviceaccount.com"; "REDACTED_SA_EMAIL") else . end))}}' > $FIXTURES/iam/list_keys__sa0.json
```

---

## 4. Extract the Key Name

Run this to pull the first key's full resource name into a shell variable:

```
KEY_NAME=$(cat $FIXTURES/iam/list_keys__sa0.json | jq -r '.response.body.keys[0].name' | sed 's/REDACTED_PROJECT/insilicostrategy-platform/g' | sed 's/REDACTED_SA_EMAIL/dockmaster@insilicostrategy-platform.iam.gserviceaccount.com/g')
```

Verify:

```
echo $KEY_NAME
```

Expected format: `projects/insilicostrategy-platform/serviceAccounts/dockmaster@.../keys/KEY_ID`

If there are multiple keys, repeat step 5 for each, changing `key0` to `key1`, `key2`, etc.
Use `jq -r '.response.body.keys[N].name'` to get each one.

---

## 5. IAM — Get Public Key

```
curl -s -H "Authorization: Bearer $TOKEN" "https://iam.googleapis.com/v1/${KEY_NAME}?publicKeyType=TYPE_X509_PEM_FILE" | jq '{request: {method: "GET", url: "https://iam.googleapis.com/v1/REDACTED_PROJECT/serviceAccounts/REDACTED_SA_EMAIL/keys/REDACTED_KEY_ID?publicKeyType=TYPE_X509_PEM_FILE", headers: {}}, response: {status: 200, headers: {"content-type": "application/json"}, body: (. | walk(if type == "string" then gsub("insilicostrategy-platform"; "REDACTED_PROJECT") | gsub("dockmaster@insilicostrategy-platform.iam.gserviceaccount.com"; "REDACTED_SA_EMAIL") else . end))}}' > $FIXTURES/iam/get_public_key__sa0_key0.json
```

---

## 6. Verify

```
ls -la $FIXTURES/iam/ $FIXTURES/google_oidc/
```

Expected files:
- `tests/fixtures/gcp/google_oidc/v1_certs.json`
- `tests/fixtures/gcp/iam/list_service_accounts.json`
- `tests/fixtures/gcp/iam/list_keys__sa0.json`
- `tests/fixtures/gcp/iam/get_public_key__sa0_key0.json`

---

## Notes

- `sa0` = dockmaster SA (the only user-managed SA we target)
- `key0` = first user-managed key; add `key1` etc. if the SA has multiple keys
- The `privateKeyId` field in public key responses is NOT sensitive (it's a public key ID) but is redacted anyway for consistency
- Re-run step 0 setup vars if your shell session resets (token expires after ~1 hour)
