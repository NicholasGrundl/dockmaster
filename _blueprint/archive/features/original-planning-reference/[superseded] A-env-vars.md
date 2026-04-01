# Appendix A: Environment Variable Reference

This appendix catalogs every environment variable used by the dockmaster system, including the service, client library, CLI, and Kubernetes deployment.

---

## Service Environment Variables

These are consumed by the dockmaster service at runtime.

| Variable | Required | Default | Source (K8s) | Description |
|---|---|---|---|---|
| `ISSUER` | Yes | None | K8s Secret `issuer-dockmaster` mounted at `/etc/issuer/identity.json` | Path to a GCP service account JSON key file. Used to sign JWTs and authenticate to Secret Manager. |
| `SECRETS_PROJECT` | Yes | None | ConfigMap `config` key `project` | GCP project ID for Secret Manager (RBAC storage). Production value: `shipyard-auth-2022`. |
| `AUTHORIZED_ISSUERS` | Yes | None (empty set) | ConfigMap `config` key `authorized_issuers` | Comma-separated list of trusted JWT issuers. Used in `/exchange` and `/refresh` to validate incoming tokens. Example: `https://accounts.google.com,dock-master@shipyard-auth-2022.iam.gserviceaccount.com` |
| `AUTHORIZED_DOMAINS` | Yes | None (empty set) | ConfigMap `config` key `authorized_domains` | Comma-separated list of allowed email domains. Emails outside these domains are rejected. Example: `shipyard.com` |
| `AUTHORIZED_AUDIENCE` | Yes | None (empty set) | ConfigMap `config` key `authorized_audience` | Comma-separated list of allowed JWT audience values. Used in both `/exchange` (JWT aud check) and access token validation. |
| `DEFAULT_CLIENT_ID` | No | None | ConfigMap `config` key `default_client_id` | Default Google OAuth2 client ID for the `/refresh` endpoint when the request doesn't specify one. |
| `CLIENT_SECRET` | Yes (for `/refresh`) | None | K8s Secret `oauth-login` key `client_secret` | Google OAuth2 client secret. Used by the `/refresh` endpoint to call Google's token endpoint. |
| `LOG_LEVEL` | No | None | ConfigMap `dockmaster-log` key `log_level` | Python logging level (`debug`, `info`, `warning`, `error`, `critical`). Also passed to gunicorn `--log-level`. |
| `SERVICE_CONFIG` | No | None | Not set in K8s | Dotted Python class path (e.g., `mymodule.MyConfig`) to load Flask config from a Python class at startup. Used by `__init__.py` dynamic config loading. |
| `ACCESS_TOKEN_ENDPOINT` | No | `https://www.googleapis.com/oauth2/v1/tokeninfo` | Not set in K8s | Google token info endpoint for access token validation in `/exchange`. |
| `REFRESH_TOKEN_ENDPOINT` | No | `https://www.googleapis.com/oauth2/v4/token` | Not set in K8s | Google token endpoint for refresh token exchange in `/refresh`. |
| `USERINFO_ENDPOINT` | No | `https://www.googleapis.com/oauth2/v3/userinfo` | Not set in K8s | Google userinfo endpoint. Called during `/refresh` to populate profile claims (name, picture, etc.). |
| `CLIENT_ID_SUFFIX` | No | `.apps.googleusercontent.com` | Not set in K8s | Suffix appended to short-form client IDs in `/refresh` when the provided client_id doesn't contain a dot. |

### Config Resolution Order

The service uses two different resolution patterns:

**`get_config()` in `service/dockmaster_service/config.py`:**
```
env var → Flask config → default
```

**`get_project()` in `service/dockmaster_service/config.py`:**
```
Flask config → env var  (reversed order — likely a bug)
```

**`get_config()` in `dockmaster/flask_integration.py`:**
```
Flask config → env var → default  (reversed order from service)
```

---

## Client Library / Flask Integration Variables

These are consumed by the dockmaster client library when used by a Flask application (not the dockmaster service itself).

| Variable | Required | Default | Description |
|---|---|---|---|
| `CLIENT_SECRET` | Yes (for OAuth2 login) | None | Google OAuth2 client secret for the authorization code exchange flow. |
| `DOCKMASTER_EXPIRY` | No | Token's `expires_in` | Session expiry override in seconds. Checked in `flask_integration.py` when `EXPIRY` is not in Flask config. |
| `HOST_URL` | No | `request.host_url` | Base URL for constructing the OAuth2 redirect URI. |
| `REDIRECT_URI` | No | Constructed from `HOST_URL` + `AUTH_PREFIX` | Full redirect URI base for OAuth2 callbacks. |
| `REDIRECT_PREFIX` | No | `''` | Path prefix prepended to `/authenticated` in the redirect URI construction. |

### Flask Config Keys (not env vars)

These are set via `app.config` (e.g., from a Config class), not environment variables:

| Key | Default | Description |
|---|---|---|
| `AUTH_PROVIDER` | `https://accounts.google.com/o/oauth2/auth` | Google OAuth2 authorization endpoint |
| `TOKEN_PROVIDER` | `https://oauth2.googleapis.com/token` | Google OAuth2 token endpoint |
| `CLIENT_ID` | (from Config class) | Google OAuth2 client ID for the login flow |
| `APP_ROOT` | `/console/` (service) or `/` (library) | Application root path |
| `AUTH_PREFIX` | `/console/auth` (service) or `/auth` (library) | Blueprint URL prefix |
| `NOAUTH` | `[]` | List of exact paths that skip authentication |
| `NOAUTH_PREFIXES` | `['/console/assets']` | List of path prefixes that skip authentication |
| `SESSION_KEY` | (from Config class) | Base64-encoded Flask secret key for session signing |
| `AUTHORIZED` | None | Optional whitelist of allowed email addresses |
| `EXPIRY` | None | Session expiry in seconds (overrides token-provided expiry) |
| `PREFIX` | `''` | URL prefix for post-login redirect |

---

## CLI Variables

The CLI (`python -m dockmaster`) uses Application Default Credentials, not explicit environment variables.

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | No | Standard GCP env var pointing to a service account key file. Used by ADC if set. |

---

## Kubernetes Init Container Variables

These are used by the init containers in the deployment, not by the Python application.

| Variable | Source | Description |
|---|---|---|
| `BUCKET` | ConfigMap `config` key `bucket` | GCS bucket name for artifact storage. Value: `example-artifacts` |
| `BUCKET_PATH` | ConfigMap `config` key `path` | Path within the bucket. Value: `dockmaster_service` |
| `ARCHIVE` | ConfigMap `config` key `archive` | Shiv `.pyz` filename. Value: `dockmaster_service-{version}-x86_64.pyz` |
| `SOURCE` | Constructed: `gs://$(BUCKET)/$(BUCKET_PATH)/$(ARCHIVE)` | Full GCS URI for the application archive |

---

## Cloud Build Variables

These are used in the Cloud Build pipeline (`service/deploy.yaml`) via substitutions.

| Variable | Default | Description |
|---|---|---|
| `_TAG` | `latest` | Docker image tag / version label |
| `_DEPLOY_TO` | `staging` | Target environment (`staging` or `prod`) |
| `_BUCKET` | `example-artifacts` | GCS bucket for artifact upload |
| `_PROJECT` | `shipyard-auth-2022` | GCP project ID |
| `_PLATFORM` | `x86_64` | Platform label for the shiv archive filename |
| `_DEPLOY_QUEUE` | `deploy-staging` | Redis stream name for deployment notifications |
| `_REDIS_HOST` | `redis.infra.svc.cluster.local` | Redis host for the deployment queue |

---

## Example Script Variables

Used by the example scripts in the `examples/` directory.

| Variable | Script | Description |
|---|---|---|
| `ISSUER` | `get_token_dockmaster.py`, `get_token_jwt.py` | Default value for `--keyfile` option |
| `LOG_LEVEL` | `get_token_google.py` | Default log level for the example script |

The `google_refresh.py` script supports environment variable indirection: if a CLI option value starts with `env:`, it reads the actual value from the named environment variable (e.g., `--client-id env:MY_CLIENT_ID`).
