# GCP CLI Setup: Multi-Config with direnv

**Problem:** Working across multiple GCP projects (personal, org, client) with a single `gcloud` CLI leads to accidental deployments to the wrong project. `gcloud config configurations` helps, but switching manually is error-prone.

**Solution:** Named gcloud configurations + `CLOUDSDK_ACTIVE_CONFIG_NAME` exported via direnv per-repo. `cd` into a project → correct GCP config activates. `cd` out → global default restored. No manual switching.

---

## 1. Install gcloud CLI (one-time)

```bash
# macOS (Homebrew)
brew install --cask google-cloud-sdk

# Verify
gcloud version
```

For other platforms see https://cloud.google.com/sdk/docs/install.

## 2. Create Named Configurations (one-time per account)

Each GCP identity (personal Gmail, Workspace account, etc.) gets its own named configuration.

```bash
# Create a config for your org account
gcloud config configurations create insilico
gcloud config set account you@insilicostrategy.com
gcloud auth login                         # opens browser — sign in with this account
gcloud auth application-default login     # ADC for local tools (keyring, SDKs, etc.)

# Verify
gcloud config configurations list
```

Repeat for other accounts:

```bash
gcloud config configurations create personal
gcloud config set account you@gmail.com
gcloud auth login
gcloud auth application-default login
```

**Two auth commands, different purposes:**

| Command | What it does | Used by |
|---------|-------------|---------|
| `gcloud auth login` | Authenticates the CLI | `gcloud` commands |
| `gcloud auth application-default login` | Sets Application Default Credentials | SDKs, keyring, twine, etc. |

## 3. Set a Global Default

```bash
gcloud config configurations activate default
```

This is what `gcloud` uses when no override is set. Pick whichever account you use most.

## 4. Create a GCP Project (per-project, once)

From the CLI (using the org config):

```bash
gcloud config configurations activate insilico

# List org ID
gcloud organizations list

# Create project under org
gcloud projects create PROJECT_ID \
  --name="Project Display Name" \
  --organization=ORG_ID

# Link billing
gcloud billing accounts list
gcloud billing projects link PROJECT_ID \
  --billing-account=BILLING_ACCOUNT_ID

# Set as default project in this config
gcloud config set project PROJECT_ID
```

Or use the console: https://console.cloud.google.com/projectcreate — select the correct organization.

## 5. Per-Repo direnv Setup

### How it works

| Action | What happens |
|--------|-------------|
| `cd` into repo | direnv exports `CLOUDSDK_ACTIVE_CONFIG_NAME=insilico` |
| `gcloud ...` | gcloud reads the env var, uses `insilico` config |
| `cd` out of repo | direnv unloads, env var removed |
| Other terminals | Unaffected — use global default |

### .env (project-specific values, gitignored)

```bash
# GCP
GCP_CONFIG=insilico
GCP_PROJECT=your-project-id
```

### .env.example (committed template)

```bash
# GCP Configuration
# GCP_CONFIG: Name of gcloud configuration (see: gcloud config configurations list)
# GCP_PROJECT: GCP project ID (see: gcloud projects list)
GCP_CONFIG=insilico
GCP_PROJECT=your-project-id-here
```

### .envrc (committed)

```bash
# Load project-specific env vars
dotenv

# Activate GCP configuration for this repo (session-scoped)
export CLOUDSDK_ACTIVE_CONFIG_NAME="${GCP_CONFIG:-default}"
```

Then allow it:

```bash
direnv allow
```

### .gitignore

```
.env
```

## 6. Justfile Recipes (optional)

```just
set dotenv-load

GCP_PROJECT := env_var_or_default('GCP_PROJECT', '')
GCP_CONFIG := env_var_or_default('GCP_CONFIG', 'default')

# Show current GCP configuration
gcp-info:
    @echo "Config:  {{GCP_CONFIG}}"
    @echo "Project: {{GCP_PROJECT}}"
    @echo ""
    @gcloud config configurations list

# Manually activate GCP config (fallback if direnv not loaded)
gcp-activate:
    gcloud config configurations activate {{GCP_CONFIG}}

# Set project in current config
gcp-set-project:
    gcloud config set project {{GCP_PROJECT}}
```

## 7. Enable APIs (per-project, as needed)

```bash
# Verify correct project
gcloud config get-value project

# Common APIs
gcloud services enable artifactregistry.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable iap.googleapis.com
```

## 8. Verification

```bash
# In a repo with .envrc configured:
cd /path/to/project
echo $CLOUDSDK_ACTIVE_CONFIG_NAME    # → insilico
gcloud config get-value project      # → your-project-id
gcloud projects list                 # should succeed with org projects

# Outside the repo:
cd ~
echo $CLOUDSDK_ACTIVE_CONFIG_NAME    # → (empty)
gcloud config configurations list    # → default is active
```

---

## Quick Reference

| Task | Command |
|------|---------|
| List configs | `gcloud config configurations list` |
| Switch config | `gcloud config configurations activate NAME` |
| Current project | `gcloud config get-value project` |
| List projects | `gcloud projects list` |
| List orgs | `gcloud organizations list` |
| List billing | `gcloud billing accounts list` |
| Revoke auth | `gcloud auth revoke ACCOUNT` |
