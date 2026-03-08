# Deployment Guide

## Docker Build & Run

### Build

```bash
docker build -t dockmaster:latest .
```

The Dockerfile uses a multi-stage build:
1. **Builder** (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`): installs dependencies via `uv sync` and builds the package
2. **Runtime** (`python:3.12-slim-bookworm`): copies only the virtualenv, runs as non-root user

### Run Locally

```bash
docker run --rm -p 8001:8001 --env-file .env dockmaster:latest
```

### Health Check

```
GET /auth/health → {"service": "dockmaster", "status": "ok"}
```

---

## Environment Variables

### Required (Service)

| Variable | Description | Example |
|---|---|---|
| `CLIENT_ID` | Google OAuth2 client ID | `109370...-p2e82hp5cv....apps.googleusercontent.com` |
| `CLIENT_SECRET` | Google OAuth2 client secret | `GOCSPX-...` |
| `ISSUER` | Path to GCP service account JSON key file (signs JWTs) | `/etc/secrets/identity.json` |
| `SECRETS_PROJECT` | GCP project ID for Secret Manager (RBAC storage) | `shipyard-auth-2022` |
| `AUTHORIZED_ISSUERS` | Comma-separated trusted JWT issuers | `https://accounts.google.com,dock-master@project.iam.gserviceaccount.com` |
| `AUTHORIZED_DOMAINS` | Comma-separated allowed email domains | `shipyard.com` |
| `AUTHORIZED_AUDIENCE` | Comma-separated allowed JWT audience values | `109370...-p2e82hp5cv....apps.googleusercontent.com` |

### Optional (Service)

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_CLIENT_ID` | None | Default Google OAuth2 client ID for `/refresh` when not specified in request |
| `CLIENT_ID_SUFFIX` | `.apps.googleusercontent.com` | Suffix appended to short-form client IDs |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `REDIS_URL` | None | Redis connection URL for session storage (e.g., `redis://redis:6379`) |
| `ACCESS_TOKEN_ENDPOINT` | `https://www.googleapis.com/oauth2/v1/tokeninfo` | Google token info endpoint |
| `REFRESH_TOKEN_ENDPOINT` | `https://www.googleapis.com/oauth2/v4/token` | Google token refresh endpoint |
| `USERINFO_ENDPOINT` | `https://www.googleapis.com/oauth2/v3/userinfo` | Google userinfo endpoint |

### GCP Authentication

| Variable | Description |
|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | Standard GCP env var pointing to a service account key file. Used by Application Default Credentials. |

---

## Target Architecture

DigitalOcean droplet running Docker Compose with Caddy for automatic TLS:

```
Internet ──HTTPS──▶ Caddy (auto TLS)
                      ├── /auth/* ──▶ dockmaster (FastAPI + Uvicorn)
                      ├── /api/*  ──▶ your-api (FastAPI)
                      └── /*      ──▶ your-frontend (Astro SSR)

dockmaster ──▶ GCP Secret Manager (RBAC storage)
           ──▶ GCP IAM (key verification)
           ──▶ Google OAuth2 (token exchange)
           ──▶ Redis (sessions)
```

The dockmaster service still uses GCP backend services (Secret Manager, IAM) even when running outside GCP. Authentication to GCP is via a mounted service account key file.

---

## Docker Compose

### `compose.yml`

```yaml
services:
  caddy:
    image: caddy:2
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    depends_on:
      - auth

  auth:
    build: .
    environment:
      - ISSUER=/etc/secrets/identity.json
      - SECRETS_PROJECT=shipyard-auth-2022
      - AUTHORIZED_ISSUERS=https://accounts.google.com
      - AUTHORIZED_DOMAINS=shipyard.com
      - AUTHORIZED_AUDIENCE=${AUTHORIZED_AUDIENCE}
      - DEFAULT_CLIENT_ID=${DEFAULT_CLIENT_ID}
      - CLIENT_ID=${CLIENT_ID}
      - CLIENT_SECRET=${CLIENT_SECRET}
      - REDIS_URL=redis://redis:6379
      - LOG_LEVEL=INFO
    volumes:
      - ./secrets/identity.json:/etc/secrets/identity.json:ro
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  caddy_data:
  redis_data:
```

### `Caddyfile`

```
auth.your-domain.com {
    reverse_proxy auth:8001
}
```

---

## GCP Authentication from Outside GCP

Two options for authenticating to GCP services (Secret Manager, IAM) from a non-GCP host:

### Option 1: Mounted SA Key File (simpler)

Download a service account JSON key, mount it into the container via Docker volume. Set `GOOGLE_APPLICATION_CREDENTIALS` and `ISSUER` to point to the mounted file.

```yaml
volumes:
  - ./secrets/identity.json:/etc/secrets/identity.json:ro
environment:
  - GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/identity.json
  - ISSUER=/etc/secrets/identity.json
```

**Downside:** Key needs manual rotation.

### Option 2: Workload Identity Federation (keyless)

Configure GCP to trust an external identity provider. More complex setup but no key file to manage. Best if you want to avoid storing keys on disk.

---

## Service Endpoints Reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/auth/health` | None | Health check |
| `GET` | `/exchange?service=X&expiry=N` | Bearer (Google token) | Exchange Google token for Dockmaster JWT |
| `POST` | `/refresh` | None | Exchange Google refresh token for Dockmaster JWT |
| `GET` | `/has/{subject}/{target}/{permission}` | Bearer (Dockmaster JWT) | RBAC permission check (204=allowed, 403=denied) |
| `GET` | `/key/{kid}` | None | Fetch public key by key ID (PEM format) |
| `GET` | `/claims` | Bearer (Dockmaster JWT) | Return verified JWT claims |

---

## Auth Middleware for Consuming Services

Every consuming service needs middleware that handles three auth modes (in order):

1. **Bearer token** — JWT in `Authorization: Bearer <jwt>` header. Verify directly using public key from `/key/{kid}`.
2. **Session cookie** — Session ID in httpOnly cookie, JWT stored server-side. Look up JWT from session store and verify.
3. **OAuth redirect** — No token found. Redirect to Dockmaster's OAuth endpoint. On return, store JWT in session.

### FastAPI Dependency Example

```python
from fastapi import Depends, HTTPException, Request

async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        claims = await verify_jwt(token)  # fetch key from /key/{kid}
        return claims
    raise HTTPException(status_code=401, detail="Not authenticated")

@app.get("/api/protected")
async def protected(user: dict = Depends(get_current_user)):
    return {"email": user["email"]}
```

---

## RBAC Model

Roles and grants are stored as JSON secrets in GCP Secret Manager:

- **Roles**: `role-{name}` — e.g., `role-lab-technician` with a list of permissions
- **Service grants**: `service-grants-{service}` — maps subjects to role lists

Permission check: load grants for the target service, find the subject's roles, union all role permissions, check if the requested permission is in the set.

### CLI Management

```bash
uv run python -m dockmaster role create admin read:all write:all delete:all
uv run python -m dockmaster service grant myapp "user@domain.com:admin"
uv run python -m dockmaster test user@domain.com myapp read:all
```
