# Appendix B: Secret Manager Secrets Catalog

This appendix documents every secret stored in GCP Secret Manager by the dockmaster system, including naming conventions, JSON schemas, and how each secret is accessed.

---

## Project

All secrets are stored in the GCP project specified by `SECRETS_PROJECT` (default: `shipyard-auth-2022`).

---

## 1. RBAC Secrets

### 1.1 Role Secrets

**Secret ID pattern:** `role-{name}`

**Examples:** `role-admin`, `role-operator`, `role-viewer`

**Created by:** CLI `python -m dockmaster role create`

**Read by:** `Authority.get_role()` via `SecretsStorage.load(Role, name)`

**JSON Schema:**

```json
{
  "kind": "Role",
  "name": "<role-name>",
  "permissions": ["<permission-1>", "<permission-2>"]
}
```

| Field | Type | Description |
|---|---|---|
| `kind` | string | Always `"Role"` |
| `name` | string | Role identifier, matches the `{name}` in the secret ID |
| `permissions` | string[] | Permission strings granted by this role |

**Example payload:**

```json
{
  "kind": "Role",
  "name": "operator",
  "permissions": ["execute", "status", "monitor"]
}
```

**Versioning:** Each update (add/remove permissions) creates a new secret version. Only the `latest` version is read.

---

### 1.2 ServiceGrants Secrets

**Secret ID pattern:** `service-grants-{service}`

**Examples:** `service-grants-data-pipeline`, `service-grants-api-gateway`

**Created by:** CLI `python -m dockmaster service grant`

**Read by:** `Authority.get_permissions()` via `SecretsStorage.load(ServiceGrants, target)`

**JSON Schema:**

```json
{
  "kind": "ServiceGrants",
  "service": "<service-name>",
  "grants": [
    {
      "kind": "Grant",
      "subject": "<email-or-identity>",
      "roles": ["<role-1>", "<role-2>"]
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `kind` | string | Always `"ServiceGrants"` |
| `service` | string | Target service identifier, matches `{service}` in the secret ID |
| `grants` | Grant[] | List of subject-to-role mappings |
| `grants[].kind` | string | Always `"Grant"` |
| `grants[].subject` | string | Principal identifier (typically an email address) |
| `grants[].roles` | string[] | List of role names granted to this subject |

**Example payload:**

```json
{
  "kind": "ServiceGrants",
  "service": "data-pipeline",
  "grants": [
    {
      "kind": "Grant",
      "subject": "worker@my-project.iam.gserviceaccount.com",
      "roles": ["operator"]
    },
    {
      "kind": "Grant",
      "subject": "admin@shipyard.com",
      "roles": ["operator", "viewer"]
    }
  ]
}
```

**Versioning:** Each grant/revoke operation creates a new secret version.

---

### 1.3 Client ID Secrets

**Secret ID pattern:** `client_id-{client_id_name}`

Where `{client_id_name}` is the client ID prefix before the first `.`.

**Example:** For client ID `109370504310-p2e82hp5cvubrub37jjrbpgabj0ivlnv.apps.googleusercontent.com`, the secret ID is `client_id-109370504310-p2e82hp5cvubrub37jjrbpgabj0ivlnv`.

**Created by:** Manual (not managed by CLI)

**Read by:** `/refresh` endpoint in `service.py:302-305`

**Payload format:** Raw UTF-8 string (NOT JSON) containing the Google OAuth2 client secret.

```
GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 2. Kubernetes Secrets

These are Kubernetes secrets (not Secret Manager secrets) used by the deployment.

### 2.1 Issuer Key

**K8s Secret name:** `issuer-dockmaster`

**Mounted at:** `/etc/issuer/identity.json`

**Content:** GCP service account JSON key file

**Used by:** The `ISSUER` env var points to this mount path. The service uses this key to:
- Sign JWTs issued by dockmaster
- Authenticate to Secret Manager for RBAC operations

**Key file structure (standard GCP format):**

```json
{
  "type": "service_account",
  "project_id": "shipyard-auth-2022",
  "private_key_id": "<kid>",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n",
  "client_email": "dock-master@shipyard-auth-2022.iam.gserviceaccount.com",
  "client_id": "<numeric-id>",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/..."
}
```

### 2.2 OAuth Login Secret

**K8s Secret name:** `oauth-login`

**Key:** `client_secret`

**Content:** Google OAuth2 client secret string

**Used by:** `CLIENT_SECRET` env var for the `/refresh` endpoint

---

## 3. Secret Access Patterns

### 3.1 Secret ID Construction

```python
# SecretsStorage.load()
secret_id = f'{entity_class.category}-{name}'
# Role.category = 'role'         → 'role-{name}'
# ServiceGrants.category = 'service-grants' → 'service-grants-{name}'
```

### 3.2 Secret Version Path

```python
secret_name = sm_client.secret_version_path(project, secret_id, 'latest')
# → 'projects/{project}/secrets/{secret_id}/versions/latest'
```

### 3.3 Access Flow

```
SecretsStorage.load(entity_class, name)
  → secret_id = '{category}-{name}'
  → secret_name = 'projects/{project}/secrets/{secret_id}/versions/latest'
  → sm_client.access_secret_version(request={"name": secret_name})
  → json.loads(response.payload.data.decode('utf-8'))
  → entity_class.from_data(data)
```

### 3.4 Save Flow

```
SecretsStorage.save(instance)
  → name = getattr(instance, instance.__class__.name)  # class attr 'name' or 'service'
  → secret_id = '{category}-{name}'
  → _ensure_secret_exists(secret_id)  # creates if needed
  → sm_client.add_secret_version(parent, payload=json.dumps(instance.data))
```

---

## 4. IAM Permissions Required

| Operation | IAM Permission | Used By |
|---|---|---|
| Read secret | `secretmanager.versions.access` | `SecretsStorage.load()` |
| Check existence | `secretmanager.versions.list` | `SecretsStorage._secret_exists()` |
| Create secret | `secretmanager.secrets.create` | `SecretsStorage._ensure_secret_exists()` |
| Add version | `secretmanager.versions.add` | `SecretsStorage.save()` |
| Delete secret | `secretmanager.secrets.delete` | `SecretsStorage.delete()` |
| Get secret metadata | `secretmanager.secrets.get` | `SecretsStorage._secret_exists()` |

### Minimum Roles

| Use Case | Suggested IAM Role |
|---|---|
| Service (read-only RBAC checks) | `roles/secretmanager.secretAccessor` |
| CLI (full RBAC management) | `roles/secretmanager.admin` |

---

## 5. Replication Configuration

When `SecretsStorage._ensure_secret_exists()` creates a new secret, it uses automatic replication:

```python
'secret': {'replication': {'automatic': {}}}
```

This means the secret data is replicated across all GCP regions automatically. For a migration, consider whether region-specific replication (`user_managed`) is needed for compliance or latency reasons.
