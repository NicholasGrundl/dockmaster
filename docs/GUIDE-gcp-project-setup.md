# Guide: GCP Project and Service Account Setup

> **Phase 1 prerequisite.** This guide sets up the GCP project and service account
> that dockmaster uses to sign JWTs. Later guides will add Secret Manager (RBAC
> storage) and OAuth consent screen (browser login).

**Time:** ~15 minutes
**Cost:** Free (GCP free tier covers everything here)
**You will have at the end:** A `.env` file pointing to a service account key that
dockmaster can use to sign tokens.

---

## Table of Contents

1. [Create a GCP Project](#1-create-a-gcp-project)
2. [Enable the IAM API](#2-enable-the-iam-api)
3. [Create a Service Account](#3-create-a-service-account)
4. [Create and Download a Key](#4-create-and-download-a-key)
5. [Configure Dockmaster](#5-configure-dockmaster)
6. [Verify the Setup](#6-verify-the-setup)

---

## 1. Create a GCP Project

> **Why a dedicated project?**
>
> GCP organizes resources (APIs, service accounts, secrets) inside projects.
> Dockmaster needs its own project because it manages auth for your entire
> system — keeping it separate means auth credentials, RBAC secrets, and
> billing are isolated from your application workloads. If someone has access
> to your app project, they don't automatically get access to your auth
> infrastructure.

### Steps

1. Go to the [GCP Console](https://console.cloud.google.com/)
2. Click the project selector dropdown at the top of the page
3. Click **New Project**
4. Fill in:
   - **Project name:** Something like `myorg-auth` or `dockmaster-prod`
   - **Organization:** Select your org if you have one, or leave as "No organization"
   - **Location:** Your org folder, or leave default
5. Click **Create**
6. Wait for the project to be created (notification bell will confirm)
7. Switch to the new project using the project selector

> **What is a GCP project ID?**
>
> Every project gets a globally unique **project ID** (e.g., `myorg-auth-2024`).
> This is different from the display name. You cannot change the project ID
> after creation. This ID is what you will set as `SECRETS_PROJECT` in
> dockmaster config (used in Phase 2 for Secret Manager).

**Note your project ID** — you will need it later. Find it on the project
dashboard or in the project selector dropdown.

---

## 2. Enable the IAM API

> **Why the IAM API?**
>
> The Identity and Access Management (IAM) API lets dockmaster programmatically
> list service account public keys. When another service receives a JWT signed
> by dockmaster, it needs to verify the signature. It does this by fetching the
> public key that matches the JWT's `kid` (key ID) header. The IAM API is how
> those public keys are discovered and cached.
>
> In short: IAM API = other services can verify tokens that dockmaster signs.

### Steps

1. Make sure you are in the correct project (check the project selector)
2. Go to **APIs & Services > Library** (or [direct link](https://console.cloud.google.com/apis/library))
3. Search for **"Identity and Access Management (IAM) API"**
4. Click on it, then click **Enable**

> **What does "enabling an API" mean?**
>
> GCP disables most APIs by default. Enabling an API tells GCP that this
> project is allowed to make calls to that service. It does not cost anything
> to enable — you only pay for actual API usage, and IAM API calls for key
> listing are free within generous quotas.

---

## 3. Create a Service Account

> **What is a service account?**
>
> A service account is a non-human identity in GCP. While your Google account
> (`you@gmail.com`) represents you, a service account (`dockmaster@myorg-auth.iam...`)
> represents a service. It has its own email address, its own RSA key pair, and
> its own permissions.
>
> Dockmaster uses a service account for two things:
> 1. **JWT signing** — the service account's private key signs JWTs that dockmaster
>    issues. The `kid` in the JWT header maps to this key.
> 2. **GCP API access** — the service account's credentials authenticate dockmaster
>    to GCP services like Secret Manager (Phase 2) and IAM.

### Steps

1. Go to **IAM & Admin > Service Accounts** (or [direct link](https://console.cloud.google.com/iam-admin/serviceaccounts))
2. Click **+ Create Service Account**
3. Fill in:
   - **Service account name:** `dockmaster` (or `dock-master` to match legacy naming)
   - **Service account ID:** auto-generated from the name (e.g., `dockmaster@myorg-auth.iam.gserviceaccount.com`)
   - **Description:** "Dockmaster auth service — signs JWTs and accesses Secret Manager"
4. Click **Create and Continue**
5. **Grant this service account access to the project** (roles):
   - Click **Add Another Role** and add: **Secret Manager Secret Accessor** (`roles/secretmanager.secretAccessor`)

   > **Why Secret Manager Secret Accessor?**
   >
   > This role lets dockmaster read secrets (RBAC roles and grants) from
   > Secret Manager. It cannot create, delete, or modify secrets — only read
   > the latest version. This follows the principle of least privilege.
   > You won't use Secret Manager until Phase 2, but adding the role now
   > saves a trip back to the console.

6. Click **Continue**
7. **Grant users access to this service account** — skip this, click **Done**

**Note the service account email** — it looks like
`dockmaster@myorg-auth.iam.gserviceaccount.com`. This email becomes the `iss`
(issuer) claim in every JWT that dockmaster signs.

---

## 4. Create and Download a Key

> **What is a service account key?**
>
> A service account key is a JSON file containing an RSA private key and
> metadata (project ID, client email, key ID). When dockmaster loads this file,
> it uses the private key to sign JWTs. The corresponding public key is
> available via the IAM API, so any service can verify the signature.
>
> **Security note:** This key file is essentially a password. Anyone who has
> it can sign JWTs as dockmaster and access Secret Manager. Treat it like a
> private SSH key:
> - Never commit it to git
> - Store it in a secure location
> - Rotate it periodically (GCP recommends every 90 days)

### Steps

1. In the Service Accounts list, click on the service account you just created
2. Go to the **Keys** tab
3. Click **Add Key > Create new key**
4. Select **JSON** format
5. Click **Create**
6. The key file downloads automatically. It looks like:

```json
{
  "type": "service_account",
  "project_id": "myorg-auth",
  "private_key_id": "abc123...",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n",
  "client_email": "dockmaster@myorg-auth.iam.gserviceaccount.com",
  "client_id": "123456789",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  ...
}
```

7. Move the downloaded file to a secure location in your project:

```bash
# Create a secrets directory (already in .gitignore via the Dockerfile pattern)
mkdir -p secrets

# Move the downloaded key (filename varies)
mv ~/Downloads/myorg-auth-*.json secrets/identity.json
```

8. **Make sure `secrets/` is in your `.gitignore`:**

```bash
echo "secrets/" >> .gitignore
```

> **Key fields dockmaster uses from this file:**
>
> | Field | Used For |
> |---|---|
> | `private_key` + `private_key_id` | Signing JWTs (RSA-SHA256). The `private_key_id` becomes the `kid` in JWT headers. |
> | `client_email` | The `iss` (issuer) claim in signed JWTs. Also used as the identity for GCP API calls. |
> | `project_id` | Implicitly used when authenticating to GCP services. |
> | `token_uri` | Used by Google auth libraries to exchange credentials for access tokens. |

---

## 5. Configure Dockmaster

1. Copy the example env file if you haven't already:

```bash
cp .env.example .env
```

2. Edit `.env` and set the `ISSUER` variable to point to your key file:

```env
ISSUER=secrets/identity.json
```

> **What does ISSUER mean?**
>
> In the context of dockmaster, `ISSUER` is the path to the service account
> key file. Dockmaster reads this file to:
> 1. Create an RSA signer for JWT token issuance
> 2. Extract the `client_email` to use as the JWT `iss` claim
> 3. Authenticate to GCP APIs (Secret Manager, IAM) using the embedded credentials
>
> The name "ISSUER" comes from JWT terminology — the issuer is the entity
> that creates and signs the token.

3. Optionally set `SECRETS_PROJECT` to your project ID (not used until Phase 2,
   but good to have ready):

```env
SECRETS_PROJECT=myorg-auth
```

---

## 6. Verify the Setup

### Verify the service starts

```bash
just dev
```

You should see structlog output indicating startup. The health endpoint should work:

```bash
curl http://localhost:8001/auth/health
# {"service":"dockmaster","status":"ok"}
```

### Verify GCP credentials load (Python REPL)

This confirms the key file is valid and readable:

```bash
uv run python -c "
from dockmaster.config import Settings
s = Settings()
print(f'ISSUER: {s.issuer}')
if s.issuer:
    import json
    from pathlib import Path
    key = json.loads(Path(s.issuer).read_text())
    print(f'Service account email: {key[\"client_email\"]}')
    print(f'Project ID: {key[\"project_id\"]}')
    print(f'Key ID: {key[\"private_key_id\"][:12]}...')
    print('Key file is valid.')
else:
    print('ISSUER not set - key file not configured yet.')
"
```

### Verify IAM API access (optional, requires network)

This confirms the service account can call the IAM API to list public keys:

```bash
uv run python -c "
from google.oauth2 import service_account
from googleapiclient.discovery import build

KEYFILE = 'secrets/identity.json'
creds = service_account.Credentials.from_service_account_file(KEYFILE)
iam = build('iam', 'v1', credentials=creds)

# List keys for this service account
sa_email = creds.service_account_email
project_id = creds.project_id
name = f'projects/{project_id}/serviceAccounts/{sa_email}'
keys = iam.projects().serviceAccounts().keys().list(name=name).execute()
print(f'Found {len(keys.get(\"keys\", []))} keys for {sa_email}')
for k in keys.get('keys', []):
    print(f'  - {k[\"name\"].split(\"/\")[-1][:12]}... ({k[\"keyType\"]})')
print('IAM API access works.')
"
```

---

## What This Unlocks

With a GCP project, service account, and key file in place, dockmaster can:

- **Now (Phase 1):** Start and serve health checks. The key file is loaded by
  `Settings.issuer` but not yet used by any endpoint.
- **Phase 2:** Sign JWTs during the OAuth login flow. The service account's
  private key signs tokens; the `client_email` becomes the `iss` claim.
- **Phase 2+:** Access Secret Manager to load RBAC roles and grants (requires
  `SECRETS_PROJECT` and the Secret Manager Secret Accessor role we added in step 3).

## Next Guide

**Phase 2 will add:** `docs/GUIDE-oauth-consent-screen.md` — setting up the
Google OAuth consent screen and creating OAuth2 client credentials (CLIENT_ID
and CLIENT_SECRET) for the browser login flow.
