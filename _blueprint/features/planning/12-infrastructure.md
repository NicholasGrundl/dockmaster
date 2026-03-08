# Infrastructure and Deployment

**Source files**: `k8s/service/**`, `service/deploy.yaml`, `service/cloudbuild.yaml`, `build.yaml`

This document covers the complete deployment infrastructure: Kubernetes manifests with Kustomize overlays, the Cloud Build CI/CD pipeline, artifact packaging, and environment-specific configuration.

---

## Table of Contents

1. [Kustomize Overlay Structure](#1-kustomize-overlay-structure)
2. [Base Manifests](#2-base-manifests)
3. [Config Overlay](#3-config-overlay)
4. [Staging Overlay](#4-staging-overlay)
5. [Production Overlay](#5-production-overlay)
6. [Environment Comparison](#6-environment-comparison)
7. [Pod Architecture](#7-pod-architecture)
8. [Cloud Build: Library Package](#8-cloud-build-library-package)
9. [Cloud Build: Service Deploy Pipeline](#9-cloud-build-service-deploy-pipeline)
10. [Artifact Packaging (shiv)](#10-artifact-packaging-shiv)
11. [Secrets Management](#11-secrets-management)
12. [Network Architecture](#12-network-architecture)

---

## 1. Kustomize Overlay Structure

The Kubernetes manifests use a four-level Kustomize hierarchy:

```
k8s/service/
├── base/                        Layer 1: Core Kubernetes resources
│   ├── kustomization.yaml       namespace: auth
│   ├── deployment.yaml          Deployment (2 replicas, init containers, main container)
│   ├── service.yaml             ClusterIP Service (80 → 9999)
│   └── account.yaml             ServiceAccount (empty annotations)
│
├── config/                      Layer 2: Shared configuration
│   ├── kustomization.yaml       inherits base, adds ConfigMap + limits + WI annotation
│   ├── config.properties        ConfigMap data (bucket, project, auth settings)
│   └── limits.yaml              Resource limits patch
│
├── staging/                     Layer 3a: Staging environment
│   ├── kustomization.yaml       namespace: auth-staging, inherits config
│   ├── ingress.yaml             Ingress (dockmaster.service.staging.example.net)
│   ├── scale.yaml               Replica count override (1)
│   ├── oauth.properties         Secret: client_secret
│   ├── log.properties           ConfigMap: log_level=debug
│   └── identity.json            Secret: issuer key (injected at build time)
│
├── prod/                        Layer 3b: Production environment
│   ├── kustomization.yaml       namespace: auth, inherits config
│   ├── ingress.yaml             Ingress (dockmaster.service.example.net)
│   ├── oauth.properties         Secret: client_secret
│   ├── log.properties           ConfigMap: log_level=info
│   └── identity.json            Secret: issuer key (injected at build time)
│
└── deployment/                  Layer 4: Generated at build time
    └── kustomization.yaml       inherits staging or prod, adds release annotations
```

**Build-time flow:** `base → config → staging|prod → deployment`

The `deployment/` directory is created dynamically during Cloud Build. It adds release labels/annotations and is the final layer used by `kubectl kustomize` to produce the deployment manifest.

---

## 2. Base Manifests

### Deployment (`base/deployment.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dockmaster
  labels:
    app: dockmaster
spec:
  revisionHistoryLimit: 2
  replicas: 2
  selector:
    matchLabels:
      app: dockmaster
  template:
    spec:
      serviceAccountName: dockmaster
      initContainers: [...]   # see Pod Architecture section
      containers: [...]        # see Pod Architecture section
      volumes:
      - name: app
        emptyDir: {}
      - name: issuer
        secret:
          secretName: issuer-dockmaster
```

Key settings:
- `revisionHistoryLimit: 2` -- keeps only the 2 most recent ReplicaSets
- `replicas: 2` -- default (overridden to 1 in staging)
- `serviceAccountName: dockmaster` -- binds to the ServiceAccount for Workload Identity

### Service (`base/service.yaml`)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: dockmaster
spec:
  selector:
    app: dockmaster
  ports:
  - protocol: TCP
    port: 80
    targetPort: 9999
```

ClusterIP service (default type). Maps external port 80 to container port 9999.

### ServiceAccount (`base/account.yaml`)

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: dockmaster
  annotations: {}
```

Empty annotations in base -- the Workload Identity annotation is added by the config overlay.

### Kustomization (`base/kustomization.yaml`)

```yaml
namespace: auth
resources:
- deployment.yaml
- account.yaml
- service.yaml
```

Sets default namespace to `auth` (overridden by staging).

---

## 3. Config Overlay

**Source**: `k8s/service/config/kustomization.yaml`

Inherits from `base/` and adds:

### ConfigMap from Properties

```yaml
configMapGenerator:
- name: config
  env: config.properties
```

Generates ConfigMap `config` from `config.properties`:

| Key | Value | Used By |
|---|---|---|
| `bucket` | `example-artifacts` | Init container: GCS bucket for archive |
| `path` | `dockmaster_service` | Init container: path within bucket |
| `archive` | `dockmaster_service-0.6.4-x86_64.pyz` | Init container + main container: archive filename |
| `project` | `shipyard-auth-2022` | SECRETS_PROJECT env var |
| `authorized_issuers` | `https://accounts.google.com,dock-master@...` | AUTHORIZED_ISSUERS env var |
| `authorized_domains` | `shipyard.com` | AUTHORIZED_DOMAINS env var |
| `authorized_audience` | `109370504310-...` | AUTHORIZED_AUDIENCE env var |
| `default_client_id` | `109370504310-...` | DEFAULT_CLIENT_ID env var |

**Note:** The `archive` value in the checked-in file (`0.6.4`) is a placeholder. It is updated at build time by `deploy.yaml` to match the actual built archive name.

### Resource Limits Patch (`limits.yaml`)

Strategic merge patch overriding container resources:

| Container | CPU Request/Limit | Memory Request/Limit |
|---|---|---|
| `google-toaster-warmer` | (unchanged from base: 0.5) | (unchanged: 0.5Gi) |
| `download` | 0.25 | 0.5Gi |
| `service` | 0.5 | 0.75Gi |

### Workload Identity Annotation

JSON patch on the ServiceAccount:

```yaml
patchesJson6902:
- target:
    version: v1
    kind: ServiceAccount
    name: dockmaster
  patch: |-
    - op: add
      path: /metadata/annotations
      value:
        iam.gke.io/gcp-service-account: dock-master@shipyard-auth-2022.iam.gserviceaccount.com
```

This binds the Kubernetes ServiceAccount to the GCP service account `dock-master@shipyard-auth-2022.iam.gserviceaccount.com` via GKE Workload Identity, allowing pods to authenticate as this GCP identity without explicit key files.

### Generator Options

```yaml
generatorOptions:
  disableNameSuffixHash: true
  labels:
    app: dockmaster
```

`disableNameSuffixHash: true` prevents Kustomize from appending a hash suffix to generated ConfigMap/Secret names. This is important because the Deployment references these by exact name (e.g., `configMapKeyRef: name: config`).

---

## 4. Staging Overlay

**Source**: `k8s/service/staging/kustomization.yaml`

```yaml
namespace: auth-staging

resources:
- ../config
- ingress.yaml

patchesStrategicMerge:
- scale.yaml

secretGenerator:
- name: oauth-login
  env: oauth.properties
- name: issuer-dockmaster
  files:
  - identity.json

configMapGenerator:
- name: dockmaster-log
  env: log.properties
```

### Staging-Specific Resources

| Resource | Content |
|---|---|
| `ingress.yaml` | Host: `dockmaster.service.staging.example.net`, NGINX ingress class |
| `scale.yaml` | `replicas: 1` (overrides base's 2) |
| `oauth.properties` | `client_secret=GOCSPX-...` → Secret `oauth-login` |
| `log.properties` | `log_level=debug` → ConfigMap `dockmaster-log` |
| `identity.json` | Service account key file → Secret `issuer-dockmaster` (injected at build time) |

### Namespace

All resources are placed in `auth-staging` namespace (overrides base's `auth`).

---

## 5. Production Overlay

**Source**: `k8s/service/prod/kustomization.yaml`

```yaml
namespace: auth

resources:
- ../config
- ingress.yaml

secretGenerator:
- name: oauth-login
  env: oauth.properties
- name: issuer-dockmaster
  files:
  - identity.json

configMapGenerator:
- name: dockmaster-log
  env: log.properties
```

### Production-Specific Resources

| Resource | Content |
|---|---|
| `ingress.yaml` | Host: `dockmaster.service.example.net`, NGINX ingress class |
| `oauth.properties` | `client_secret=GOCSPX-...` → Secret `oauth-login` |
| `log.properties` | `log_level=info` → ConfigMap `dockmaster-log` |
| `identity.json` | Service account key file → Secret `issuer-dockmaster` (injected at build time) |

**Note:** No `scale.yaml` -- production uses the base replica count of 2.

---

## 6. Environment Comparison

| Aspect | Staging | Production |
|---|---|---|
| Namespace | `auth-staging` | `auth` |
| Replicas | 1 | 2 |
| FQDN | `dockmaster.service.staging.example.net` | `dockmaster.service.example.net` |
| Log Level | `debug` | `info` |
| OAuth Client Secret | Same value | Same value |
| Total CPU | 1.25 (1 pod) | 2.5 (2 pods) |
| Total Memory | 1.75Gi (1 pod) | 3.5Gi (2 pods) |

---

## 7. Pod Architecture

Each pod has 2 init containers and 1 main container, sharing an `emptyDir` volume at `/app`.

### Init Container 1: `google-toaster-warmer`

**Image:** `gcr.io/google.com/cloudsdktool/cloud-sdk:alpine`
**Purpose:** Wait for the GKE metadata server to become available (required for Workload Identity).

```bash
curl -sS -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token' \
  --retry 30 --retry-connrefused --retry-max-time 60 --connect-timeout 3 \
  --fail --retry-all-errors > /dev/null && exit 0 || \
  echo 'Retry limit exceeded...' >&2; exit 1
```

Retries up to 30 times over 60 seconds with 3-second connection timeout. This ensures the metadata server (and Workload Identity token endpoint) is ready before the download container tries to authenticate.

**Resources:** 0.5 CPU, 0.5Gi memory

### Init Container 2: `download`

**Image:** `google/cloud-sdk:latest`
**Purpose:** Download the `.pyz` archive from GCS and create a run script.

**Environment variables** (from ConfigMap `config`):
- `BUCKET` → `example-artifacts`
- `BUCKET_PATH` → `dockmaster_service`
- `ARCHIVE` → `dockmaster_service-{version}-{arch}.pyz`
- `SOURCE` → `gs://$(BUCKET)/$(BUCKET_PATH)/$(ARCHIVE)` (composed via Kubernetes variable expansion)

**Script:**
```bash
set -e
echo "Downloading ${SOURCE} to /app/${ARCHIVE}"
gsutil -D cp ${SOURCE} /app/${ARCHIVE}
echo '#!/bin/bash -l' >> /app/run.sh
echo 'cd /app' >> /app/run.sh
echo '/usr/local/bin/python $*' >> /app/run.sh
chmod +x /app/run.sh
```

The generated `/app/run.sh` is a wrapper that runs Python with all passed arguments:
```bash
#!/bin/bash -l
cd /app
/usr/local/bin/python $*
```

**Resources:** 0.25 CPU, 0.5Gi memory
**Volume:** Mounts `/app` (emptyDir, shared with main container)

### Main Container: `service`

**Image:** `python:3.10`
**Command:** `/app/run.sh`
**Args:** The .pyz archive path followed by gunicorn arguments:

```
/app/{ARCHIVE}
dockmaster_service:service
-b 0.0.0.0:9999
-w 4
-k gevent
--access-logfile -
--error-logfile -
--log-level {LOG_LEVEL}
--timeout 600
```

This effectively runs:
```bash
python /app/dockmaster_service-{version}-{arch}.pyz \
    dockmaster_service:service \
    -b 0.0.0.0:9999 -w 4 -k gevent \
    --access-logfile - --error-logfile - \
    --log-level debug --timeout 600
```

The `.pyz` archive is a shiv-built zipapp with `gunicorn.app.wsgiapp:run` as its entry point, so it starts gunicorn which loads the `dockmaster_service:service` Flask app.

**Environment Variables:**

| Env Var | Source | Value/Key |
|---|---|---|
| `SECRETS_PROJECT` | ConfigMap `config` | `project` |
| `ARCHIVE` | ConfigMap `config` | `archive` |
| `CLIENT_SECRET` | Secret `oauth-login` | `client_secret` |
| `LOG_LEVEL` | ConfigMap `dockmaster-log` | `log_level` |
| `ISSUER` | Hardcoded | `/etc/issuer/identity.json` |
| `AUTHORIZED_ISSUERS` | ConfigMap `config` | `authorized_issuers` |
| `AUTHORIZED_DOMAINS` | ConfigMap `config` | `authorized_domains` |
| `AUTHORIZED_AUDIENCE` | ConfigMap `config` | `authorized_audience` |
| `DEFAULT_CLIENT_ID` | ConfigMap `config` | `default_client_id` |

**Volume Mounts:**
- `/app` -- emptyDir (contains downloaded archive and run.sh)
- `/etc/issuer` -- Secret `issuer-dockmaster` (read-only, contains `identity.json`)

**Resources:** 0.5 CPU, 0.75Gi memory

---

## 8. Cloud Build: Library Package

**Source**: `build.yaml`

Builds and publishes the `dockmaster` Python library package to the private artifact registry.

### Steps

| Step | Image | Action |
|---|---|---|
| Install build requirements | `python:3.10` | `pip install -r build-requirements.txt --user` |
| Build package | `python:3.10` | `python -m build -n` (creates sdist + wheel in `dist/`) |
| Upload to repo | `python:3.10` | `twine upload --repository-url {_REPO} dist/*` |
| Notify | `python:3.10` | Slack webhook with package name and version |

### Substitutions

| Variable | Value |
|---|---|
| `_REPO` | `https://us-west1-python.pkg.dev/example-artifact-registries-prod/example-python/` |
| `_NOTIFY_URL` | Slack webhook URL |

---

## 9. Cloud Build: Service Deploy Pipeline

**Source**: `service/deploy.yaml`

The main deployment pipeline that builds the service archive, configures secrets, generates Kubernetes manifests, and queues the deployment.

### Pipeline Steps

#### Step 1: Install Build Requirements

```yaml
- id: 'Install build requirements'
  name: python:3.10
  entrypoint: pip
  args: ["install", "-r", "service/build-requirements.txt", "--user"]
```

Installs `shiv`, `build`, `twine`, and artifact registry auth.

#### Step 2: Build Shiv Archive

```bash
VERSION=$(python3 -c '...read from service/setup.cfg...')
if [ -z "${TAG_NAME}" ]; then
  ARCHIVE=${_SERVICE}-v${VERSION}-${COMMIT_SHA}-$(arch).pyz
else
  ARCHIVE=${_SERVICE}-${TAG_NAME}-$(arch).pyz
fi
python -m shiv -o ${ARCHIVE} -e gunicorn.app.wsgiapp:run . ./service gunicorn[gevent]
```

- Archive naming: `dockmaster_service-{tag_or_version-commit}-{arch}.pyz`
- Entry point: `gunicorn.app.wsgiapp:run`
- Packages included: root package (`.`), service package (`./service`), and `gunicorn[gevent]`

#### Step 3: Upload Archive to GCS

```bash
gsutil cp ${ARCHIVE} ${_BUCKET}${ARCHIVE}
```

Uploads to `gs://example-artifacts/dockmaster_service/`.

#### Step 4: Configure Secrets

Uses `secretEnv` to access Secret Manager values, then:

1. Updates `config.properties` with the actual archive filename:
   ```bash
   sed "s/archive=.*/archive=${ARCHIVE}/g" k8s/service/config/config.properties
   ```

2. Updates `oauth.properties` with the client secret:
   ```bash
   sed "s/client_secret=.*/client_secret=${CLIENT_SECRET}/g" k8s/service/${_K8S_TARGET}/oauth.properties
   ```

3. Writes the issuer identity JSON:
   ```bash
   echo ${ISSUER} > k8s/service/${_K8S_TARGET}/identity.json
   ```

#### Step 5: Create Deployment Metadata

Creates `k8s/service/deployment/kustomization.yaml` dynamically:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- ../{_K8S_TARGET}           # staging or prod
commonAnnotations:
  example.net/release: '{LABEL}'
generatorOptions:
  labels:
    example.net/release: '{LABEL}'
```

This adds a release label to all generated resources for tracking.

#### Step 6: Generate Final Manifest

```bash
kubectl kustomize -o service_deploy.yaml k8s/service/deployment
```

Produces a single YAML file with all Kubernetes resources fully resolved.

#### Step 7: Upload Manifest to GCS

```bash
gsutil cp service_deploy.yaml ${_K8S_BUCKET}service_deploy-${LABEL}.yaml
```

Uploads to `gs://example-{target}-artifacts/dockmaster_service/`.

#### Step 8: Queue Deployment via Redis

```python
import redis, os
client = redis.Redis(
    host=os.environ['REDIS_DEPLOY_HOST'],
    port=int(os.environ['REDIS_DEPLOY_PORT']),
    username=os.environ['REDIS_DEPLOY_USERNAME'],
    password=os.environ['REDIS_DEPLOY_PASSWORD']
)
client.xadd('deploy-' + os.environ['TARGET'], {
    'deploy': os.environ['DEPLOY'],
    'archive': os.environ['ARCHIVE']
})
```

Adds an entry to a Redis stream (`deploy-staging` or `deploy-prod`). An external deployment agent reads this stream and applies the manifest to the target cluster.

#### Step 9: Slack Notification

Posts a build completion message to Slack with the archive and deployment YAML paths.

### Substitutions

| Variable | Default | Description |
|---|---|---|
| `_K8S_TARGET` | `staging` | Target environment (`staging` or `prod`) |
| `_SERVICE` | `dockmaster_service` | Service name |
| `_BUCKET` | `gs://example-artifacts/${_SERVICE}/` | GCS bucket for archives |
| `_K8S_BUCKET` | `gs://example-${_K8S_TARGET}-artifacts/${_SERVICE}/` | GCS bucket for deployment manifests |
| `_NOTIFY_URL` | Slack webhook URL | Notification endpoint |

### Secrets from Secret Manager

| Secret | Env Var | Purpose |
|---|---|---|
| `catteldog-oauth-client-secret` | `CLIENT_SECRET` | OAuth client secret for K8s Secret |
| `dockmaster-service-key-prod` | `ISSUER` | Service account key JSON for K8s Secret |
| `redis-deploy-host` | `REDIS_DEPLOY_HOST` | Redis deployment queue connection |
| `redis-deploy-port` | `REDIS_DEPLOY_PORT` | Redis deployment queue connection |
| `redis-deploy-username` | `REDIS_DEPLOY_USERNAME` | Redis deployment queue connection |
| `redis-deploy-password` | `REDIS_DEPLOY_PASSWORD` | Redis deployment queue connection |

**Note:** The secret name `catteldog-oauth-client-secret` has a typo (double `t` in `catteldog`). This is in the actual GCP Secret Manager and must be referenced exactly as-is.

---

## 10. Artifact Packaging (shiv)

The service is packaged as a `.pyz` zipapp using [shiv](https://github.com/linkedin/shiv).

### What shiv produces

A `.pyz` file is a self-contained Python zipapp that:
1. Contains the application code and all dependencies in a single file
2. Has an entry point that bootstraps the environment
3. Can be executed directly: `python archive.pyz [args]`

### Build command

```bash
python -m shiv -o ${ARCHIVE} -e gunicorn.app.wsgiapp:run . ./service gunicorn[gevent]
```

| Flag | Value | Purpose |
|---|---|---|
| `-o` | `dockmaster_service-{label}-{arch}.pyz` | Output file |
| `-e` | `gunicorn.app.wsgiapp:run` | Entry point function |
| `.` | -- | Install root package (dockmaster library) |
| `./service` | -- | Install service package (dockmaster_service) |
| `gunicorn[gevent]` | -- | Install gunicorn with gevent extra |

The `.pyz` includes the dockmaster library, the service, gunicorn, gevent, and all their transitive dependencies.

### Runtime execution

When run as `python archive.pyz dockmaster_service:service -b 0.0.0.0:9999 ...`:
1. shiv extracts dependencies to a cache directory
2. The entry point (`gunicorn.app.wsgiapp:run`) is invoked
3. Gunicorn starts with the WSGI app `dockmaster_service:service`

---

## 11. Secrets Management

### Kubernetes Secrets

| Secret Name | Type | Source | Mount/Env |
|---|---|---|---|
| `oauth-login` | Opaque (env) | `oauth.properties` | Env: `CLIENT_SECRET` |
| `issuer-dockmaster` | Opaque (file) | `identity.json` | Volume: `/etc/issuer/identity.json` |

### GCP Secret Manager (Runtime)

Used by the service at runtime for RBAC data and OAuth client secrets:

| Secret Pattern | Purpose | Accessed By |
|---|---|---|
| `role-{name}` | RBAC role definitions | Authority via SecretsStorage |
| `service-grants-{service}` | RBAC service grants | Authority via SecretsStorage |
| `client_id-{name}` | OAuth client secrets for refresh flow | `/refresh` endpoint |

### GCP Secret Manager (Build Time)

Used by Cloud Build to inject values into Kubernetes manifests:

| Secret | Purpose |
|---|---|
| `catteldog-oauth-client-secret` | Injected into `oauth.properties` |
| `dockmaster-service-key-prod` | Written to `identity.json` |
| `redis-deploy-*` | Redis deployment queue credentials |

---

## 12. Network Architecture

### Request Flow

```
Internet
  ↓
NGINX Ingress Controller
  ↓ (Host: dockmaster.service.example.net)
Kubernetes Service: dockmaster (ClusterIP, port 80)
  ↓ (targetPort: 9999)
Pod: gunicorn on 0.0.0.0:9999 (4 workers, gevent)
```

### DNS

| FQDN | Environment | Resolves To |
|---|---|---|
| `dockmaster.service.example.net` | Production | NGINX Ingress external IP |
| `dockmaster.service.staging.example.net` | Staging | NGINX Ingress external IP |

### TLS

No TLS configuration is present in the ingress manifests. TLS termination is likely handled at the NGINX ingress controller level via a default certificate or cert-manager, but this is not configured within the dockmaster manifests.

### Cluster Details (from deploy.yaml)

| Setting | Value |
|---|---|
| Region | `us-west1` |
| Cluster | `apps-k8s-prod` |
| Project | `example-shared-k8s-prod-000000` |

These are referenced in the `kubectl kustomize` step's environment variables.
