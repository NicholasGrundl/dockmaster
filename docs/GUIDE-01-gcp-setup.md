# Guide 01: GCP Setup

> From zero to a fully configured GCP environment for Dockmaster. Covers project creation, service accounts, Secret Manager, and OAuth credentials.

**Audience**: Anyone setting up Dockmaster for the first time.
**Assumes**: A Google account with billing enabled. Nothing else.

> **Already have a GCP project?** Skip to [2. Enable APIs](#2-enable-apis).
> **Already have service accounts?** Skip to [4. Secret Manager Setup](#4-secret-manager-setup).
> **Already have OAuth credentials?** Skip to [5c. Verify](#5c-verify) and confirm your checklist.

---

## 1. Create a GCP Project

Every GCP resource lives inside a project. If you already have one you want to use for Dockmaster, skip ahead. Otherwise, create a dedicated project — this keeps IAM policies, billing, and audit logs isolated.

You'll reference this project ID throughout the rest of the guide. Pick something descriptive (e.g. `myorg-platform`, `mycompany-auth`).

### 1a. Console UI

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown (top-left, next to "Google Cloud") → **New Project**
3. Fill in:
   - **Project name**: e.g. `My Platform`
   - **Project ID**: e.g. `myorg-platform` (auto-generated, but you can customize — this cannot be changed later)
   - **Organization**: select your org if applicable, or "No organization"
   - **Billing account**: select your billing account
4. Click **Create**
5. Wait for the notification confirming project creation, then select the new project from the dropdown

### 1b. gcloud CLI

```bash
# Set your project ID — used throughout this guide
PROJECT="myorg-platform"

# Create the project (add --organization=ORG_ID if you have one)
gcloud projects create "$PROJECT" --name="My Platform"

# Link a billing account
gcloud billing accounts list
BILLING_ACCOUNT="XXXXXX-XXXXXX-XXXXXX"  # from the output above
gcloud billing projects link "$PROJECT" --billing-account="$BILLING_ACCOUNT"

# Set as your active project
gcloud config set project "$PROJECT"

# Verify
gcloud config get-value project
```

> **Tip**: If you work with multiple GCP projects, see [Appendix A](#appendix-a-gcloud-multi-config-with-direnv) for setting up per-repo automatic project switching with direnv.

---

## 2. Enable APIs

Dockmaster depends on three GCP APIs. They must be enabled before any service account or secret operations will work.

| API | Service name | Used for |
|-----|-------------|----------|
| **IAM** | `iam.googleapis.com` | Service account creation, key management |
| **IAM Credentials** | `iamcredentials.googleapis.com` | Public key enumeration for JWT verification |
| **Secret Manager** | `secretmanager.googleapis.com` | RBAC data storage (roles, grants) |

### 2a. Console UI

1. Navigate to **APIs & Services** → **Library** (left sidebar)
2. Search for and enable each:
   - "Identity and Access Management (IAM) API" → **Enable**
   - "IAM Service Account Credentials API" → **Enable**
   - "Secret Manager API" → **Enable**

### 2b. gcloud CLI

```bash
gcloud services enable iam.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  --project="$PROJECT"
```

Verify:

```bash
gcloud services list --enabled --project="$PROJECT" \
  --filter="name:(iam OR iamcredentials OR secretmanager)" \
  --format="table(name, title)"
```

All three should appear in the output.

---

## 3. Service Account Setup

Dockmaster uses **two** service accounts with different permission levels. This follows the principle of least privilege — the runtime SA can only read, while the admin SA can write.

| Service Account | Purpose | Secret Manager Access | When Used |
|---|---|---|---|
| `dockmaster` | Runtime operations — JWT signing, key enumeration, SM reads | Read-only (`secretAccessor`) | Every request |
| `dockmaster-admin` | Admin operations — RBAC role/grant CRUD | Full CRUD (`secretmanager.admin`) | Admin API only |

> **Why two SAs?** If the runtime SA is compromised, the attacker can read RBAC data but cannot modify it. Write access is isolated to the admin SA, which uses a separate key file and is only loaded when admin operations are configured.

### 3a. Runtime Service Account (`dockmaster`)

This SA is used for the core Dockmaster operations: signing JWTs with its private key, enumerating public keys across SAs in the project (for JWT verification), and reading secrets from Secret Manager (RBAC data).

The key file lives at `secrets/service-account-dockmaster.json` (gitignored) and is referenced by `SA_KEY_FILE` in `.env`.

#### Console UI

1. Navigate to **IAM & Admin** → **Service Accounts**
2. Click **+ Create Service Account**
3. Fill in:
   - **Name**: `dockmaster`
   - **ID**: auto-fills to `dockmaster`
   - **Description**: `Runtime SA for dockmaster — JWT signing, key enumeration, Secret Manager reads`
4. Click **Create and Continue**
5. Grant roles (click **+ Add Another Role** for each):
   - `Service Account Viewer` — lists SAs and their public keys for JWT verification
   - `Secret Manager Secret Accessor` — reads secret payloads (RBAC data)
6. Click **Continue** → **Done**
7. Click on the new `dockmaster` SA → **Keys** tab → **Add Key** → **Create new key** → **JSON** → **Create**
8. Move the downloaded file:

```bash
mkdir -p secrets
mv ~/Downloads/*-*.json secrets/service-account-dockmaster.json
```

#### gcloud CLI

```bash
SA_NAME="dockmaster"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
KEY_FILE="secrets/service-account-dockmaster.json"

# Create the service account
gcloud iam service-accounts create "$SA_NAME" \
  --project="$PROJECT" \
  --display-name="Dockmaster Runtime" \
  --description="Runtime SA for dockmaster — JWT signing, key enumeration, Secret Manager reads"

# Grant IAM roles
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountViewer" \
  --condition=None --quiet

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None --quiet

# Download the key file
mkdir -p secrets
gcloud iam service-accounts keys create "$KEY_FILE" \
  --iam-account="$SA_EMAIL" \
  --project="$PROJECT" \
  --key-file-type=json
```

Verify the key file:

```bash
jq '{type, project_id, client_email, private_key_id}' "$KEY_FILE"
```

Expected output:

```json
{
  "type": "service_account",
  "project_id": "myorg-platform",
  "client_email": "dockmaster@myorg-platform.iam.gserviceaccount.com",
  "private_key_id": "some-hex-key-id"
}
```

### 3b. Admin Service Account (`dockmaster-admin`)

This SA is used exclusively by the admin API for RBAC write operations: creating, updating, and deleting roles and grants in Secret Manager.

The key file lives at `secrets/service-account-dockmaster-admin.json` and is referenced by `ADMIN_SA_KEY_FILE` in `.env`.

#### Console UI

1. Navigate to **IAM & Admin** → **Service Accounts**
2. Click **+ Create Service Account**
3. Fill in:
   - **Name**: `dockmaster-admin`
   - **ID**: auto-fills to `dockmaster-admin`
   - **Description**: `Admin SA for dockmaster — Secret Manager write access for RBAC management`
4. Click **Create and Continue**
5. Grant role:
   - `Secret Manager Admin` — full CRUD on secrets
6. Click **Continue** → **Done**
7. Click on the new `dockmaster-admin` SA → **Keys** tab → **Add Key** → **Create new key** → **JSON** → **Create**
8. Move the downloaded file:

```bash
mv ~/Downloads/*-*.json secrets/service-account-dockmaster-admin.json
```

#### gcloud CLI

```bash
ADMIN_SA_NAME="dockmaster-admin"
ADMIN_SA_EMAIL="${ADMIN_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
ADMIN_KEY_FILE="secrets/service-account-dockmaster-admin.json"

# Create the service account
gcloud iam service-accounts create "$ADMIN_SA_NAME" \
  --project="$PROJECT" \
  --display-name="Dockmaster Admin" \
  --description="Admin SA for dockmaster — Secret Manager write access for RBAC management"

# Grant IAM role
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${ADMIN_SA_EMAIL}" \
  --role="roles/secretmanager.admin" \
  --condition=None --quiet

# Download the key file
gcloud iam service-accounts keys create "$ADMIN_KEY_FILE" \
  --iam-account="$ADMIN_SA_EMAIL" \
  --project="$PROJECT" \
  --key-file-type=json
```

Verify:

```bash
jq '{type, project_id, client_email, private_key_id}' "$ADMIN_KEY_FILE"
```

### 3c. Verify Service Accounts

Confirm both SAs exist and have the correct roles:

```bash
# List service accounts
gcloud iam service-accounts list --project="$PROJECT" \
  --filter="email:dockmaster" \
  --format="table(email, displayName)"
```

Should show both `dockmaster@...` and `dockmaster-admin@...`.

```bash
# Check IAM bindings for the runtime SA
gcloud projects get-iam-policy "$PROJECT" \
  --flatten="bindings[].members" \
  --filter="bindings.members:dockmaster@${PROJECT}.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

Expected: `roles/iam.serviceAccountViewer` and `roles/secretmanager.secretAccessor`.

```bash
# Check IAM bindings for the admin SA
gcloud projects get-iam-policy "$PROJECT" \
  --flatten="bindings[].members" \
  --filter="bindings.members:dockmaster-admin@${PROJECT}.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

Expected: `roles/secretmanager.admin`.

> **Security reminder**: Never commit the `secrets/` directory to git. Verify it's in `.gitignore`:
> ```bash
> grep secrets .gitignore
> ```

---

## 4. Secret Manager Setup

Dockmaster stores RBAC configuration as JSON secrets in GCP Secret Manager. Each role definition and each service's grant list is a separate secret. This section creates the minimum bootstrap data needed to get started.

### 4a. Secret Naming Conventions

| Entity | Secret ID Pattern | Example |
|---|---|---|
| Role | `role-{name}` | `role-viewer`, `role-admin` |
| Service Grants | `service-grants-{service}` | `service-grants-dockmaster`, `service-grants-data-pipeline` |
| OAuth Client Secret | `client_id-{numeric_prefix}` | `client_id-525956676695` |

### 4b. Seed Bootstrap RBAC Data

At minimum, you need an `admin` role and a grant that gives your email that role on the `dockmaster` service itself. This bootstraps admin access so you can manage everything else through the UI or CLI.

#### Console UI

1. Navigate to **Security** → **Secret Manager** (left sidebar)
2. Click **+ Create Secret**
3. Create the `admin` role:
   - **Name**: `role-admin`
   - **Secret value**: `{"name": "admin", "permissions": ["admin"]}`
   - **Replication**: Automatic
   - Click **Create Secret**
4. Create the `dockmaster` service grants:
   - **Name**: `service-grants-dockmaster`
   - **Secret value** (replace the email with yours):
     ```json
     {"service": "dockmaster", "grants": [{"subject": "you@yourcompany.com", "roles": ["admin"]}]}
     ```
   - **Replication**: Automatic
   - Click **Create Secret**

Verify each secret by clicking on it → **Versions** tab → click the version number to view the payload.

#### gcloud CLI

```bash
YOUR_EMAIL="you@yourcompany.com"

# Create the admin role
gcloud secrets create role-admin \
  --project="$PROJECT" \
  --replication-policy=automatic

echo '{"name": "admin", "permissions": ["admin"]}' | \
  gcloud secrets versions add role-admin \
  --project="$PROJECT" \
  --data-file=-

# Verify
gcloud secrets versions access latest \
  --secret=role-admin \
  --project="$PROJECT" | jq .

# Create the dockmaster service grants
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

# Verify
gcloud secrets versions access latest \
  --secret=service-grants-dockmaster \
  --project="$PROJECT" | jq .
```

> **Optional**: You can also create a `viewer` role for read-only access:
> ```bash
> gcloud secrets create role-viewer --project="$PROJECT" --replication-policy=automatic
> echo '{"name": "viewer", "permissions": ["read", "list"]}' | \
>   gcloud secrets versions add role-viewer --project="$PROJECT" --data-file=-
> ```

### 4c. Store OAuth Client Secret (Optional)

If you prefer to store the OAuth client secret in Secret Manager rather than the `.env` file, you can do so. This is optional — Dockmaster also accepts `CLIENT_SECRET` as an environment variable.

```bash
# The numeric prefix is the first segment of your OAuth client ID
# e.g. if CLIENT_ID=525956676695-abc.apps.googleusercontent.com → prefix is 525956676695
CLIENT_ID_PREFIX="525956676695"

gcloud secrets create "client_id-${CLIENT_ID_PREFIX}" \
  --project="$PROJECT" \
  --replication-policy=automatic

echo -n "GOCSPX-your-client-secret-here" | \
  gcloud secrets versions add "client_id-${CLIENT_ID_PREFIX}" \
  --project="$PROJECT" \
  --data-file=-
```

---

## 5. OAuth Client ID & Consent Screen

Google OAuth credentials enable browser login. Without these, the `/auth/login` endpoint won't work (Dockmaster logs a warning at startup: "CLIENT_ID not set — OAuth login will return 503").

> **Note**: OAuth client setup is Console-only — there is no gcloud CLI for creating OAuth credentials.

### 5a. Configure OAuth Consent Screen

1. Navigate to **APIs & Services** → **OAuth consent screen**
2. Select **External** (or **Internal** if you only want users from your Google Workspace org)
3. Fill in:
   - **App name**: `Dockmaster` (or your preferred name)
   - **User support email**: your email
   - **Authorized domains**: add your domain (e.g. `yourcompany.com`)
   - **Developer contact email**: your email
4. Click **Save and Continue**
5. **Scopes**: click **Add or Remove Scopes** and add:
   - `email`
   - `profile`
   - `openid`
6. Click **Save and Continue** through the remaining steps

### 5b. Create OAuth Client ID

1. Navigate to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. Fill in:
   - **Application type**: Web application
   - **Name**: `Dockmaster` (or your preferred name)
   - **Authorized redirect URIs**: add:
     - `http://localhost:8000/auth/callback` (for local development)
     - Your production URL when ready (e.g. `https://auth.yourcompany.com/auth/callback`)
4. Click **Create**
5. Note the **Client ID** and **Client Secret** — you'll need both for `.env` in [Guide 02](GUIDE-02-consumer-howto.md)

> **Important**: The Client ID looks like `123456789-abcdef.apps.googleusercontent.com`. The full string including `.apps.googleusercontent.com` is the Client ID. Don't truncate it.

### 5c. Verify

You should now have all the GCP artifacts Dockmaster needs. Use this checklist:

- [ ] **GCP project** exists with APIs enabled (IAM, IAM Credentials, Secret Manager)
- [ ] **Runtime SA** (`dockmaster@...`) with:
  - `roles/iam.serviceAccountViewer`
  - `roles/secretmanager.secretAccessor`
  - Key file at `secrets/service-account-dockmaster.json`
- [ ] **Admin SA** (`dockmaster-admin@...`) with:
  - `roles/secretmanager.admin`
  - Key file at `secrets/service-account-dockmaster-admin.json`
- [ ] **Secret Manager** seeded with:
  - `role-admin` — `{"name": "admin", "permissions": ["admin"]}`
  - `service-grants-dockmaster` — grants your email the `admin` role
- [ ] **OAuth Client ID** and **Client Secret** noted (from step 5b)
- [ ] `secrets/` directory is in `.gitignore`

These artifacts map to environment variables in [Guide 02: Consumer Howto](GUIDE-02-consumer-howto.md).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `gcloud projects create` → 403 | Insufficient org permissions | Ask org admin for `resourcemanager.projects.create`, or create under "No organization" |
| `gcloud services enable` → 403 | Not project owner | Ask project owner to enable APIs or grant you `serviceusage.services.enable` |
| `gcloud iam service-accounts create` → 403 | Lack `iam.serviceAccountAdmin` | Ask project owner to grant it, or use Owner role |
| `gcloud iam service-accounts keys create` → 403 | Need `iam.serviceAccountKeys.create` | Grant yourself `iam.serviceAccountKeyAdmin` temporarily |
| `gcloud secrets create` → 403 | Secret Manager API not enabled, or no SM permissions | Run step 2 (enable APIs), then check your IAM roles |
| Key file has wrong SA email | Downloaded key for wrong SA | Delete and re-download from the correct SA |
| OAuth consent screen shows "unverified app" warning | Normal for external apps in testing | Click "Continue" — or submit for Google verification for production |

---

## Appendix A: gcloud Multi-Config with direnv

If you work with multiple GCP projects, manually switching `gcloud` configurations is error-prone. This appendix sets up automatic per-repo project switching using named gcloud configurations and direnv.

**How it works**: each repo has a `.envrc` file that exports `CLOUDSDK_ACTIVE_CONFIG_NAME`. When you `cd` into the repo, direnv activates the correct GCP config. When you `cd` out, it's unloaded.

| Action | What happens |
|--------|-------------|
| `cd` into repo | direnv exports `CLOUDSDK_ACTIVE_CONFIG_NAME=myconfig` |
| `gcloud ...` | gcloud reads the env var, uses `myconfig` configuration |
| `cd` out of repo | direnv unloads, env var removed |
| Other terminals | Unaffected — use global default |

### A1. Install gcloud CLI

```bash
# macOS (Homebrew)
brew install --cask google-cloud-sdk

# Verify
gcloud version
```

For other platforms: https://cloud.google.com/sdk/docs/install

### A2. Create Named Configurations

Each GCP identity (personal Gmail, Workspace account, etc.) gets its own named configuration.

```bash
# Create a config for your org account
gcloud config configurations create myorg
gcloud config set account you@yourcompany.com
gcloud auth login                         # opens browser — sign in with this account
gcloud auth application-default login     # ADC for local tools (SDKs, etc.)

# Set the default project for this config
gcloud config set project myorg-platform
```

Repeat for other accounts if needed:

```bash
gcloud config configurations create personal
gcloud config set account you@gmail.com
gcloud auth login
gcloud auth application-default login
```

**Two auth commands, different purposes:**

| Command | What it does | Used by |
|---------|-------------|---------|
| `gcloud auth login` | Authenticates the CLI itself | `gcloud` commands |
| `gcloud auth application-default login` | Sets Application Default Credentials (ADC) | Python SDKs, other tools |

### A3. Per-Repo direnv Setup

Install direnv:

```bash
# macOS
brew install direnv

# Add to your shell (add to ~/.bashrc or ~/.zshrc)
eval "$(direnv hook bash)"   # or: eval "$(direnv hook zsh)"
```

Create `.envrc` in your dockmaster repo:

```bash
# .envrc (committed to git)
dotenv

# Activate GCP configuration for this repo
export CLOUDSDK_ACTIVE_CONFIG_NAME="${GCP_CONFIG:-default}"
```

Add GCP config to your `.env` (gitignored):

```bash
# .env
GCP_CONFIG=myorg
GCP_PROJECT=myorg-platform
```

Allow direnv:

```bash
direnv allow
```

### A4. Verify

```bash
# Inside the repo — should show your org config
echo $CLOUDSDK_ACTIVE_CONFIG_NAME    # → myorg
gcloud config get-value project      # → myorg-platform

# Outside the repo — should be unset
cd ~
echo $CLOUDSDK_ACTIVE_CONFIG_NAME    # → (empty)
```

**Quick reference:**

| Task | Command |
|------|---------|
| List configs | `gcloud config configurations list` |
| Switch config manually | `gcloud config configurations activate NAME` |
| Current project | `gcloud config get-value project` |
| List projects | `gcloud projects list` |
