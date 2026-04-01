# Secret Manager Guide for Dockmaster RBAC

How Dockmaster uses GCP Secret Manager to store RBAC roles and service grants.

## Overview

Dockmaster stores RBAC configuration as JSON secrets in GCP Secret Manager. Each role and each service's grant list is a separate secret. The `Authority` engine resolves permissions by loading these secrets with TTL-based caching.

## Secret Naming Conventions

| Entity | Secret ID Pattern | Example |
|---|---|---|
| Role | `role-{name}` | `role-viewer`, `role-finance-admin` |
| Service Grants | `service-grants-{service}` | `service-grants-data-pipeline` |
| OAuth Client Secret | `client_id-{numeric_prefix}` | `client_id-525956676695` |

## Secret Schemas

### Role

```json
{
  "name": "viewer",
  "permissions": ["read", "list"]
}
```

- `name` — role identifier (must match the `{name}` in the secret ID)
- `permissions` — list of permission strings (exact match, e.g. `"read"`, `"experiment:approve"`)

### Service Grants

```json
{
  "service": "data-pipeline",
  "grants": [
    {
      "subject": "alice@example.com",
      "roles": ["viewer", "editor"]
    },
    {
      "subject": "pipeline-sa@project.iam.gserviceaccount.com",
      "roles": ["admin"]
    }
  ]
}
```

- `service` — the target service name (must match the `{service}` in the secret ID)
- `grants[].subject` — email or service account identifier
- `grants[].roles` — list of role names that this subject holds for this service

## How Permission Resolution Works

When `Authority.has_permission(subject, target, permission)` is called:

1. Load `service-grants-{target}` from cache or Secret Manager
2. Find the grant entry where `grant.subject == subject`
3. For each role in the subject's `grant.roles`, load `role-{name}` from cache or SM
4. Collect the union of all permissions from all roles
5. Return `True` if the requested permission is in that set

## Caching

- `Authority` is a lifespan-scoped singleton with TTL cache (default 300s, configurable via `RBAC_CACHE_TTL`)
- Cache keys: `grants:{target}` for service grants, `role:{name}` for roles
- First request for a target loads from SM; subsequent requests within TTL use cached data
- `Authority.clear_cache()` forces fresh loads (used by admin write operations)

## GCP IAM Requirements

| Phase | Operation | Required IAM Role |
|---|---|---|
| 5 (RBAC reads) | `AccessSecretVersion` | `roles/secretmanager.secretAccessor` |
| 6 (RBAC writes) | `CreateSecret`, `AddSecretVersion`, `DeleteSecret` | `roles/secretmanager.admin` |

The runtime service account needs at minimum `secretAccessor` for read-only RBAC. Admin operations (Phase 6) require `secretmanager.admin`.

## Creating Secrets via gcloud

### Create a role

```bash
# Create the secret
gcloud secrets create role-viewer \
  --project=YOUR_PROJECT \
  --replication-policy=automatic

# Add the JSON payload as a version
echo '{"name": "viewer", "permissions": ["read", "list"]}' | \
  gcloud secrets versions add role-viewer \
  --project=YOUR_PROJECT \
  --data-file=-
```

### Create service grants

```bash
gcloud secrets create service-grants-data-pipeline \
  --project=YOUR_PROJECT \
  --replication-policy=automatic

cat <<'EOF' | gcloud secrets versions add service-grants-data-pipeline \
  --project=YOUR_PROJECT \
  --data-file=-
{
  "service": "data-pipeline",
  "grants": [
    {"subject": "alice@example.com", "roles": ["viewer", "editor"]},
    {"subject": "bob@example.com", "roles": ["viewer"]}
  ]
}
EOF
```

### Verify a secret

```bash
gcloud secrets versions access latest \
  --secret=role-viewer \
  --project=YOUR_PROJECT
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRETS_PROJECT` | Yes (for RBAC) | None | GCP project ID for Secret Manager |
| `RBAC_CACHE_TTL` | No | `300` | Cache TTL in seconds |
| `SA_KEY_FILE` | No | None | Path to SA key JSON (falls back to ADC) |

## Troubleshooting

**503 "RBAC service not configured"** — `SECRETS_PROJECT` is not set. The Authority singleton was not created.

**Permission denied on SM access** — The runtime SA lacks `roles/secretmanager.secretAccessor`. Grant it:
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="serviceAccount:SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor"
```

**Stale permissions after updating a secret** — The TTL cache may still be serving old data. Wait for `RBAC_CACHE_TTL` seconds, or restart the service. Phase 6 admin endpoints call `clear_cache()` automatically after writes.
