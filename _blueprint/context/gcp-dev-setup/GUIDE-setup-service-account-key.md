# Guide: Create a GCP Service Account Key for Dockmaster

Creates (or re-creates) the dockmaster service account and downloads a JSON key
file. This key is used for:

1. **JWT signing** — `ServiceUser` signs dockmaster JWTs with the SA private key
2. **IAM key enumeration** — `ServiceAccountKeyCache` uses the SA credentials to
   list public keys across all SAs in the project
3. **Secret Manager access** — the SA credential authorizes SM lookups for client
   secrets and RBAC data

The key file lives at `secrets/service-account-dockmaster.json` (gitignored) and
is referenced by `SA_KEY_FILE` in `.env`.

**Prerequisites**: A GCP project with IAM API enabled. You need `roles/iam.serviceAccountAdmin`
(or Owner) on the project.

---

## Option A: gcloud CLI

### A1. Set variables

```bash
PROJECT="insilicostrategy-platform"
SA_NAME="dockmaster"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
KEY_DIR="secrets"
KEY_FILE="${KEY_DIR}/service-account-dockmaster.json"
```

Verify:

```bash
echo "SA_EMAIL=$SA_EMAIL"
echo "KEY_FILE=$KEY_FILE"
```

---

### A2. Check if the SA already exists

```bash
gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT" 2>&1
```

- **If it exists**: skip to A4 (create a new key).
- **If `NOT_FOUND`**: continue to A3.

---

### A3. Create the service account

```bash
gcloud iam service-accounts create "$SA_NAME" \
  --project="$PROJECT" \
  --display-name="Dockmaster Auth Service" \
  --description="Service account for dockmaster auth microservice — JWT signing, IAM key enumeration, Secret Manager access"
```

Verify:

```bash
gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT"
```

Should show the SA email and display name.

---

### A4. (Optional) Delete old keys

List existing keys to see if there are stale ones:

```bash
gcloud iam service-accounts keys list \
  --iam-account="$SA_EMAIL" \
  --project="$PROJECT" \
  --managed-by=user
```

If you see old keys you want to remove:

```bash
KEY_ID="PASTE_KEY_ID_HERE"
gcloud iam service-accounts keys delete "$KEY_ID" \
  --iam-account="$SA_EMAIL" \
  --project="$PROJECT" \
  --quiet
```

Repeat for each old key. This invalidates any JWTs signed with those keys.

---

### A5. Create a new key and download

```bash
mkdir -p "$KEY_DIR"
gcloud iam service-accounts keys create "$KEY_FILE" \
  --iam-account="$SA_EMAIL" \
  --project="$PROJECT" \
  --key-file-type=json
```

Verify the file was created and has the expected fields:

```bash
jq '{type, project_id, client_email, private_key_id}' "$KEY_FILE"
```

Expected output:

```json
{
  "type": "service_account",
  "project_id": "insilicostrategy-platform",
  "client_email": "dockmaster@insilicostrategy-platform.iam.gserviceaccount.com",
  "private_key_id": "some-hex-key-id"
}
```

---

### A6. Grant required IAM roles

The SA needs these roles on the project — **both are read-only**:

| Role | Purpose | Phase | Permissions granted |
|------|---------|-------|---------------------|
| `roles/iam.serviceAccountViewer` | List SAs + enumerate public keys for JWT verification | 2 | `iam.serviceAccounts.list`, `iam.serviceAccountKeys.list`, `iam.serviceAccountKeys.get` |
| `roles/secretmanager.secretAccessor` | Read secret payloads (client secrets, RBAC data) | 4b, 5 | `secretmanager.versions.access` |

> **Note**: The runtime SA is strictly read-only. Write access to Secret Manager
> (for managing RBAC roles/grants) will use a separate `dockmaster-admin` SA in Phase 6.

```bash
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountViewer" \
  --condition=None \
  --quiet

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None \
  --quiet
```

Verify the bindings:

```bash
gcloud projects get-iam-policy "$PROJECT" \
  --flatten="bindings[].members" \
  --filter="bindings.members:${SA_EMAIL}" \
  --format="table(bindings.role)"
```

Should show both roles. If you see `iam.serviceAccountKeyAdmin` from a previous setup,
remove it — it grants write access (create/delete keys) which the runtime SA doesn't need:

```bash
gcloud projects remove-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountKeyAdmin" \
  --quiet
```

---

### A7. Update .env

Make sure `.env` points to the new key file:

```bash
grep SA_KEY_FILE .env
```

Should show:

```
SA_KEY_FILE=secrets/service-account-dockmaster.json
```

If not, update it:

```bash
sed -i '' 's|^SA_KEY_FILE=.*|SA_KEY_FILE=secrets/service-account-dockmaster.json|' .env
```

---

### A8. Verify end to end

```bash
uv run python -c "
from dockmaster.auth.jwt_signer import ServiceUser
su = ServiceUser('$KEY_FILE')
token = su.get_token(subject='test@example.com', service_name='test')
print(f'SUCCESS: signed JWT with kid={su.private_key_id}')
print(f'token starts with: {token[:30]}...')
"
```

---

## Option B: Google Cloud Console (UI)

### B1. Navigate to Service Accounts

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Select your project (`insilicostrategy-platform`) from the project dropdown
3. Navigate: **IAM & Admin** → **Service Accounts** (left sidebar)

---

### B2. Check if the SA exists

Look for `dockmaster@insilicostrategy-platform.iam.gserviceaccount.com` in the list.

- **If it exists**: click on it and skip to B4.
- **If not**: continue to B3.

---

### B3. Create the service account

1. Click **+ CREATE SERVICE ACCOUNT** (top of page)
2. Fill in:
   - **Service account name**: `dockmaster`
   - **Service account ID**: auto-fills to `dockmaster` (verify)
   - **Description**: `Service account for dockmaster auth microservice`
3. Click **CREATE AND CONTINUE**
4. **Grant this service account access to project** (step 2):
   - Click **+ ADD ANOTHER ROLE** and add each:
     - `Service Account Viewer` (under IAM)
     - `Secret Manager Secret Accessor` (under Secret Manager)
   - Click **CONTINUE**
5. **Grant users access to this service account** (step 3):
   - Skip — click **DONE**

---

### B4. Create a new JSON key

1. Click on the `dockmaster` service account row to open its detail page
2. Click the **KEYS** tab
3. Click **ADD KEY** → **Create new key**
4. Select **JSON** format
5. Click **CREATE**
6. The browser downloads a file like `insilicostrategy-platform-XXXX.json`

Move and rename the downloaded file:

```bash
mkdir -p secrets
mv ~/Downloads/insilicostrategy-platform-*.json secrets/service-account-dockmaster.json
```

Verify:

```bash
jq '{type, project_id, client_email, private_key_id}' secrets/service-account-dockmaster.json
```

---

### B5. (Optional) Delete old keys via UI

Still on the **KEYS** tab:

1. Each key shows its **Key ID**, **Created date**, and **Expiry**
2. Click the **trash icon** (🗑) next to any old keys you want to remove
3. Confirm deletion

> **Warning**: Deleting a key immediately invalidates any JWTs signed with it.
> Only delete keys you know are not in use.

---

### B6. Grant IAM roles (if you skipped step 3 during creation)

1. Navigate: **IAM & Admin** → **IAM** (left sidebar)
2. Find the `dockmaster@...` row
3. Click the **pencil icon** (✏️) to edit
4. Click **+ ADD ANOTHER ROLE**
5. Add:
   - `Service Account Viewer`
   - `Secret Manager Secret Accessor`
6. Click **SAVE**

---

### B7. Update .env and verify

Same as CLI steps A7 and A8:

```bash
grep SA_KEY_FILE .env
# Should show: SA_KEY_FILE=secrets/service-account-dockmaster.json

uv run python -c "
from dockmaster.auth.jwt_signer import ServiceUser
su = ServiceUser('secrets/service-account-dockmaster.json')
token = su.get_token(subject='test@example.com', service_name='test')
print(f'SUCCESS: signed JWT with kid={su.private_key_id}')
print(f'token starts with: {token[:30]}...')
"
```

---

## Verification Checklist

After completing either Option A or B:

- [ ] `secrets/service-account-dockmaster.json` exists with valid `private_key`, `client_email`, `private_key_id`
- [ ] `.env` has `SA_KEY_FILE=secrets/service-account-dockmaster.json`
- [ ] SA has `roles/secretmanager.secretAccessor` (verify: `gcloud projects get-iam-policy ...`)
- [ ] SA has `roles/iam.serviceAccountKeyAdmin` (verify same command)
- [ ] `ServiceUser` can sign a JWT with the key (A8/B7 verification script)
- [ ] Old keys deleted (if rotating)

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `gcloud iam service-accounts create` → 403 | You lack `iam.serviceAccountAdmin` | Ask project owner to grant it, or use Owner role |
| `gcloud iam service-accounts keys create` → 403 | `iam.serviceAccountKeys.create` permission needed | Grant yourself `iam.serviceAccountKeyAdmin` on the project |
| Key file has `"type": "service_account"` but JWT signing fails | Private key is corrupted or key was disabled | Delete and recreate the key |
| `ServiceAccountKeyCache` can't list SA keys | SA lacks `iam.serviceAccountViewer` | Grant the role (A6 / B6) |
| `SecretsStorage` returns `PERMISSION_DENIED` | SA lacks `secretmanager.secretAccessor` | Grant the role (A6 / B6) |
| Downloaded key file is named `<project>-XXXX.json` | Normal — GCP names downloads by project | Rename per B4 instructions |

---

## Security Notes

- **Never commit** `secrets/` to git. Verify it's in `.gitignore`:
  ```bash
  grep secrets .gitignore
  ```
- SA keys don't expire by default. Rotate periodically (delete old, create new).
- In production, use Workload Identity Federation instead of downloaded keys.
- After rotation, re-run the Phase 2 fixture capture guide (`GUIDE-capture-gcp-fixtures.md`)
  to update the IAM fixtures with the new key ID.
