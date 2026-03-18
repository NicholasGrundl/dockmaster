# Guide: Create the Admin Service Account for Phase 6

Sets up the `dockmaster-admin` service account with Secret Manager write access.
This SA is used by Phase 6 admin endpoints to create, update, and delete RBAC
roles and grants in Secret Manager.

**Why a separate SA?** The runtime `dockmaster` SA has read-only SM access
(`secretAccessor`). Admin write operations need `secretmanager.admin`. Splitting
these follows least-privilege: the runtime SA can never accidentally mutate RBAC
data.

**Prerequisites:**
- GCP project with Secret Manager API enabled
- `gcloud` CLI authenticated (see `appendix-gcp-multi-config.md` for multi-config setup)
- You need `roles/iam.serviceAccountAdmin` (or Owner) on the project

**Two paths:** [Option A (gcloud CLI)](#option-a-gcloud-cli) or
[Option B (Console UI)](#option-b-google-cloud-console). Both end at the same
[Seed Bootstrap RBAC Data](#5-seed-bootstrap-rbac-data) step.

---

# Option A: gcloud CLI

## 0. Set Variables

```bash
PROJECT="insilicostrategy-platform"
SA_NAME="dockmaster-admin"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
KEY_DIR="secrets"
KEY_FILE="${KEY_DIR}/service-account-dockmaster-admin.json"
```

Verify:

```bash
echo "SA_EMAIL=$SA_EMAIL"
echo "KEY_FILE=$KEY_FILE"
```

---

## 1. Create the Admin Service Account

Check if it already exists:

```bash
gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT" 2>&1
```

If `NOT_FOUND`, create it:

```bash
gcloud iam service-accounts create "$SA_NAME" \
  --project="$PROJECT" \
  --display-name="Dockmaster Admin" \
  --description="Admin SA for dockmaster RBAC management — Secret Manager write access"
```

Verify:

```bash
gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT"
```

---

## 2. Grant IAM Roles

The admin SA needs SM write access:

| Role | Purpose | Permissions granted |
|------|---------|---------------------|
| `roles/secretmanager.admin` | Create, update, delete secrets (RBAC roles + grants) | Full SM CRUD |

```bash
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.admin" \
  --condition=None \
  --quiet
```

Verify:

```bash
gcloud projects get-iam-policy "$PROJECT" \
  --flatten="bindings[].members" \
  --filter="bindings.members:${SA_EMAIL}" \
  --format="table(bindings.role)"
```

Should show `roles/secretmanager.admin`.

---

## 3. Download the Key File

```bash
mkdir -p "$KEY_DIR"
gcloud iam service-accounts keys create "$KEY_FILE" \
  --iam-account="$SA_EMAIL" \
  --project="$PROJECT" \
  --key-file-type=json
```

Verify:

```bash
jq '{type, project_id, client_email, private_key_id}' "$KEY_FILE"
```

Expected:

```json
{
  "type": "service_account",
  "project_id": "insilicostrategy-platform",
  "client_email": "dockmaster-admin@insilicostrategy-platform.iam.gserviceaccount.com",
  "private_key_id": "some-hex-key-id"
}
```

---

## 4. Update `.env`

Add the admin SA key path:

```bash
echo 'ADMIN_SA_KEY_FILE=secrets/service-account-dockmaster-admin.json' >> .env
```

Verify both SA key entries are present:

```bash
grep SA_KEY_FILE .env
```

Expected:

```
SA_KEY_FILE=secrets/service-account-dockmaster.json
ADMIN_SA_KEY_FILE=secrets/service-account-dockmaster-admin.json
```

---

---

# Option B: Google Cloud Console

## B1. Navigate to Service Accounts

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Select your project (`insilicostrategy-platform`) from the project dropdown
3. Navigate: **IAM & Admin** → **Service Accounts** (left sidebar)

---

## B2. Check if the Admin SA Exists

Look for `dockmaster-admin@insilicostrategy-platform.iam.gserviceaccount.com` in the list.

- **If it exists**: click on it and skip to B4.
- **If not**: continue to B3.

---

## B3. Create the Service Account

1. Click **+ CREATE SERVICE ACCOUNT** (top of page)
2. Fill in:
   - **Service account name**: `dockmaster-admin`
   - **Service account ID**: auto-fills to `dockmaster-admin` (verify)
   - **Description**: `Admin SA for dockmaster RBAC management — Secret Manager write access`
3. Click **CREATE AND CONTINUE**
4. **Grant this service account access to project** (step 2):
   - Click **Select a role** and search for `Secret Manager Admin`
   - Select `Secret Manager Admin` (`roles/secretmanager.admin`)
   - Click **CONTINUE**
5. **Grant users access to this service account** (step 3):
   - Skip — click **DONE**

---

## B4. Create a JSON Key

1. Click on the `dockmaster-admin` service account row to open its detail page
2. Click the **KEYS** tab
3. Click **ADD KEY** → **Create new key**
4. Select **JSON** format
5. Click **CREATE**
6. The browser downloads a file like `insilicostrategy-platform-XXXX.json`

Move and rename the downloaded file:

```bash
mkdir -p secrets
mv ~/Downloads/insilicostrategy-platform-*.json secrets/service-account-dockmaster-admin.json
```

Verify:

```bash
jq '{type, project_id, client_email, private_key_id}' secrets/service-account-dockmaster-admin.json
```

---

## B5. (Optional) Delete Old Keys via UI

Still on the **KEYS** tab:

1. Each key shows its **Key ID**, **Created date**, and **Expiry**
2. Click the **trash icon** next to any old keys you want to remove
3. Confirm deletion

> **Warning**: Deleting a key immediately invalidates any operations using it.

---

## B6. Verify IAM Role (if you skipped step 4 during creation)

1. Navigate: **IAM & Admin** → **IAM** (left sidebar)
2. Find the `dockmaster-admin@...` row
3. Click the **pencil icon** to edit
4. Verify `Secret Manager Admin` is listed. If not:
   - Click **+ ADD ANOTHER ROLE**
   - Search for and add `Secret Manager Admin`
5. Click **SAVE**

---

## B7. Update `.env`

```bash
echo 'ADMIN_SA_KEY_FILE=secrets/service-account-dockmaster-admin.json' >> .env
```

Verify:

```bash
grep SA_KEY_FILE .env
```

Expected:

```
SA_KEY_FILE=secrets/service-account-dockmaster.json
ADMIN_SA_KEY_FILE=secrets/service-account-dockmaster-admin.json
```

---

## B8. Seed Bootstrap RBAC Data via Console

You can create the bootstrap secrets in the Console UI instead of `gcloud`:

1. Navigate: **Security** → **Secret Manager** (left sidebar)
2. Click **+ CREATE SECRET**
3. Create `role-admin`:
   - **Name**: `role-admin`
   - **Secret value**: `{"name": "admin", "permissions": ["admin"]}`
   - **Replication**: Automatic
   - Click **CREATE SECRET**
4. Create `service-grants-dockmaster`:
   - **Name**: `service-grants-dockmaster`
   - **Secret value** (replace the email with yours):
     ```json
     {"service": "dockmaster", "grants": [{"subject": "you@insilicostrategy.com", "roles": ["admin"]}]}
     ```
   - **Replication**: Automatic
   - Click **CREATE SECRET**

Verify each secret by clicking on it → **VERSIONS** tab → click the version number → view the payload.

After completing Option B, skip to [Verify Admin SA Can Read and Write](#6-verify-admin-sa-can-read-and-write).

---

# Common Steps (both options)

## 5. Seed Bootstrap RBAC Data

> If you used **Option B** and already created secrets via the Console (step B8),
> skip to [step 5c](#5c-optional-also-add-dockmaster_admin_emails-as-bootstrap-fallback)
> or [step 6](#6-verify-admin-sa-can-read-and-write).

Before the admin UI can work, you need an `admin` role and a grant that gives
your email that role on the `dockmaster` service.

### 5a. Create the `admin` role

```bash
gcloud secrets create role-admin \
  --project="$PROJECT" \
  --replication-policy=automatic

echo '{"name": "admin", "permissions": ["admin"]}' | \
  gcloud secrets versions add role-admin \
  --project="$PROJECT" \
  --data-file=-
```

Verify:

```bash
gcloud secrets versions access latest \
  --secret=role-admin \
  --project="$PROJECT" | jq .
```

### 5b. Create the `dockmaster` service grants

Replace `YOUR_EMAIL` with your actual email:

```bash
YOUR_EMAIL="you@insilicostrategy.com"

gcloud secrets create service-grants-dockmaster \
  --project="$PROJECT" \
  --replication-policy=automatic

cat <<EOF | gcloud secrets versions add service-grants-dockmaster \
  --project="$PROJECT" \
  --data-file=-
{
  "service": "dockmaster",
  "grants": [
    {"subject": "$YOUR_EMAIL", "roles": ["admin"]}
  ]
}
EOF
```

Verify:

```bash
gcloud secrets versions access latest \
  --secret=service-grants-dockmaster \
  --project="$PROJECT" | jq .
```

### 5c. (Optional) Also add `DOCKMASTER_ADMIN_EMAILS` as bootstrap fallback

This is the emergency fallback in case RBAC data gets corrupted:

```bash
echo "DOCKMASTER_ADMIN_EMAILS=$YOUR_EMAIL" >> .env
```

Once RBAC is working and you've verified your admin role, you can remove this
line. The RBAC-first auth check will handle it.

---

## 6. Verify Admin SA Can Read and Write

These steps temporarily activate the admin SA for your gcloud session, run
verification commands, then switch back to your user account.

### 6a. Activate the admin SA

```bash
gcloud auth activate-service-account "$SA_EMAIL" --key-file="$KEY_FILE"
```

### 6b. List secrets (read)

```bash
gcloud secrets list \
  --project="$PROJECT" \
  --filter="name:role-" \
  --format="table(name)"
```

Should show `role-admin` (and any other roles).

### 6c. Write a test secret and clean up

```bash
# Create
echo '{"name": "test-delete-me", "permissions": ["test"]}' | \
  gcloud secrets create role-test-delete-me \
  --project="$PROJECT" \
  --replication-policy=automatic \
  --data-file=-

# Verify
gcloud secrets versions access latest \
  --secret=role-test-delete-me \
  --project="$PROJECT" | jq .

# Clean up
gcloud secrets delete role-test-delete-me \
  --project="$PROJECT" \
  --quiet
```

If all three commands succeed, the admin SA has full SM CRUD access.

### 6d. Switch back to your user account

```bash
gcloud config set account nicholasgrundl@insilicostrategy.com
```

Verify you're back:

```bash
gcloud auth list --filter="status:ACTIVE" --format="value(account)"
```

---

## 7. Verify End-to-End with Python

Quick smoke test that the admin SA key works with the GCP Python client:

```bash
uv run python -c "
import json
from google.oauth2 import service_account
from google.cloud.secretmanager_v1 import SecretManagerServiceClient

key_data = json.loads(open('$KEY_FILE').read())
creds = service_account.Credentials.from_service_account_info(
    key_data, scopes=['https://www.googleapis.com/auth/cloud-platform']
)
client = SecretManagerServiceClient(credentials=creds)

# List role secrets
parent = f'projects/$PROJECT'
secrets = list(client.list_secrets(request={'parent': parent, 'filter': 'name:role-'}))
print(f'Found {len(secrets)} role secret(s):')
for s in secrets:
    print(f'  {s.name.split(\"/\")[-1]}')
print('SUCCESS: admin SA can list secrets')
"
```

---

## Verification Checklist

- [ ] `dockmaster-admin` SA exists in GCP project
- [ ] SA has `roles/secretmanager.admin` on the project
- [ ] `secrets/service-account-dockmaster-admin.json` downloaded and gitignored
- [ ] `.env` has `ADMIN_SA_KEY_FILE=secrets/service-account-dockmaster-admin.json`
- [ ] `role-admin` secret exists in SM with `{"name": "admin", "permissions": ["admin"]}`
- [ ] `service-grants-dockmaster` secret exists with your email granted `admin` role
- [ ] Admin SA can list, read, create, and delete secrets (step 6)
- [ ] Python smoke test passes (step 7)

---

## Security Notes

- **Never commit** `secrets/` to git. Verify it's in `.gitignore`.
- The admin SA key grants full SM write access. Treat it like a production credential.
- `DOCKMASTER_ADMIN_EMAILS` is a bootstrap/emergency fallback. Remove it once
  RBAC is self-hosting (your email is granted admin via SM grants).

### SA Keys vs Workload Identity — when to use which

| Deployment | Recommended auth | Why |
|---|---|---|
| **Local dev** | SA key file | Simple, direct. No alternative for off-GCP dev. |
| **Self-hosted** (DO droplet, AWS, etc.) | SA key file (as Docker secret) | Host is outside GCP — no automatic identity. Key mounted at runtime, not baked into image. |
| **GCP-hosted** (Cloud Run, GKE, GCE) | Workload Identity | Service *is* the SA — no key to manage, rotate, or leak. GCP injects credentials automatically. |
| **CI/CD** (GitHub Actions, etc.) | Workload Identity Federation | Short-lived OIDC tokens exchanged for GCP access. No long-lived secrets in CI. |

Dockmaster deploys to a DO droplet via Docker, so SA key files are the right
approach. Details will be covered in the Phase 7 deployment guide.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `gcloud secrets create` → 403 | Admin SA lacks `secretmanager.admin` | Re-run step 2 |
| `activate-service-account` → error | Key file path wrong or SA email mismatch | Check `$SA_EMAIL` and `$KEY_FILE` values |
| Commands work under admin SA but fail after | Forgot to switch back to user account | Run `gcloud config set account YOUR_EMAIL` |
| Python client → `DefaultCredentialsError` | Key file path wrong or file missing | Check `KEY_FILE` path and `.env` |
| `role-admin` exists but admin UI shows 403 | `service-grants-dockmaster` missing or email mismatch | Re-run step 5b, check email exactly matches |
| Write endpoints return 503 | `ADMIN_SA_KEY_FILE` not set or file not found | Check `.env` and file exists |
