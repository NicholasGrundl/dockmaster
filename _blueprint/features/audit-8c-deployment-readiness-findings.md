---
state: Draft
changelog:
  "2026-03-16": "Created — deployment readiness audit findings from interview + app audit"
---

# Phase 8c: Deployment Readiness Findings

> Audit of dockmaster's production readiness and integration plan for the existing
> DigitalOcean + Docker Compose + Caddy stack.

**Phase**: 8c
**Last updated**: 2026-03-16

---

## 1. Deployment Context (from interview)

### Existing Stack

| Component | Details |
|---|---|
| Provider | DigitalOcean (single droplet) |
| OS | Ubuntu 24.04 LTS |
| Droplet size | 1 GB RAM / 1 vCPU |
| Reverse proxy | Caddy (system service, not containerized) |
| Container runtime | Docker + Docker Compose |
| Existing services | 1 service: Astro site (`web`, port 4321) |
| TLS | Caddy auto-TLS via Let's Encrypt, behind Cloudflare proxy (Full Strict) |
| DNS | Cloudflare — `insilicostrategy.com` + `www` |
| Access | Tailscale for SSH, DO firewall for HTTP/HTTPS |
| Deploy process | Local build → `docker save` → SSH transfer → `docker compose up` (via `just deploy`) |
| Future CI/CD | GitHub Actions → GCP Artifact Registry → `docker pull` on droplet |

### Existing Files (reference)

- **Caddyfile**: `insilicostrategy.com, www.insilicostrategy.com { encode zstd gzip; reverse_proxy 127.0.0.1:4321 }`
- **docker-compose.yml**: Single `web` service, binds `127.0.0.1:4321:4321`, healthcheck via wget
- **Dockerfile**: Multi-stage Node.js build, runs as `node` user

### Decisions Made

- **D-001**: Dockmaster domain: `auth.insilicostrategy.com` (subdomain-based routing)
- **D-002**: Build strategy: local build + transfer now, GCP Artifact Registry via GitHub Actions later
- **D-003**: GCP credentials: SCP key files to droplet, mount as Docker volumes
- **D-004**: Secrets/env vars: decide in Phase 9 (likely `.env` file on droplet)
- **D-005**: Multiple services will eventually use dockmaster for auth (not just Astro site)

---

## 2. Application Readiness Audit

### Environment Variables — Production Checklist

| Variable | Required | Default | Production Notes |
|---|---|---|---|
| `SA_KEY_FILE` | Yes | None | Path to dockmaster SA key file (JWT signing, SM reads) |
| `SECRETS_PROJECT` | Yes | None | GCP project ID for Secret Manager |
| `CLIENT_ID` | Yes | None | Google OAuth client ID |
| `CLIENT_SECRET` | Yes | None | Google OAuth client secret (or stored in SM) |
| `DEFAULT_CLIENT_ID` | No | None | OAuth client ID suffix matching |
| `SESSION_SECRET_KEY` | **Required** | ~~None~~ (was `"change-me-in-production"`) | Remove default — app won't start without it |
| `REQUIRE_PROXY_HEADERS` | No | `True` | Set `false` in local dev only. Middleware checks `X-Forwarded-Proto` present. |
| `LOG_LEVEL` | No | `"INFO"` | `INFO` is correct for production |
| `ADMIN_SA_KEY_FILE` | Yes (for writes) | None | Path to admin SA key file (RBAC writes) |
| `DOCKMASTER_ADMIN_EMAILS` | Yes | `""` | Comma-separated admin email allowlist |
| `ALLOWED_REDIRECT_URIS` | Yes | `""` | Must include CLI + any external service redirect URIs |
| `ALLOWED_ORIGINS` | Conditional | `""` | Required if UI/API are cross-origin |
| `JWKS_REGISTRY_PATH` | No | platformdirs path | Override to a persistent Docker volume path |
| `RBAC_CACHE_TTL` | No | `300` | Fine as default |
| `DOCKMASTER_TOKEN_TTL` | No | `900` | Fine as default |
| `AUTHORIZED_ISSUERS` | Yes | `""` | Must include `accounts.google.com` + `"dockmaster"` |
| `AUTHORIZED_DOMAINS` | Yes | `""` | Must include allowed email domains |
| `AUTHORIZED_AUDIENCE` | Recommended | `""` | Should validate audience in production |
| `UI_CONFIG_PATH` | No | None | Optional branding config |
| `REDIS_URL` | No | None | Not used yet (in-memory sessions) |
| `SESSION_TTL` | No | `3600` | Fine as default |

### Findings

#### D-010: No trusted proxy header configuration (Severity: Blocker)

**What**: The app has zero `X-Forwarded-For` / `X-Forwarded-Proto` handling. Behind Caddy,
`request.url` will show `http://` instead of `https://`, and `request.client.host` will be
`127.0.0.1` instead of the real client IP.

**Impact**:
- OAuth callback URL generation may use `http://` scheme → Google rejects it
- Session cookies with `Secure` flag won't be set correctly
- Access logs show `127.0.0.1` for all requests

**Fix** (two layers):
1. **Uvicorn flag**: `--proxy-headers --forwarded-allow-ips 127.0.0.1` in Dockerfile CMD
2. **App middleware**: New `REQUIRE_PROXY_HEADERS` setting (default `True`). When enabled,
   middleware checks every request for `X-Forwarded-Proto` header — returns 502 if missing.
   Set `REQUIRE_PROXY_HEADERS=false` in local dev `.env` only. This catches the "forgot the
   uvicorn flag" scenario in production.

#### D-011: Session secret key has insecure default (Severity: Blocker)

**What**: `session_secret_key` defaults to `"change-me-in-production"` in `config.py:73`.

**Impact**: Session cookies can be forged if the default isn't overridden.

**Fix**: Remove the default entirely — make `SESSION_SECRET_KEY` a required setting with no
default. App fails to start without it (pydantic-settings validation error). In local dev,
add `SESSION_SECRET_KEY=dev-secret` to `.env`.

#### D-012: OpenAPI docs exposed by default (Severity: Warning)

**What**: FastAPI serves `/docs` and `/openapi.json` by default. The `ServiceInfo` root endpoint
explicitly links to `/docs`.

**Impact**: Exposes full API schema to unauthenticated users. Already flagged in Phase 8a
security audit (S-001).

**Fix**: Set `docs_url=None, redoc_url=None, openapi_url=None` in `create_app()` for production.
Consider an env var toggle (`ENABLE_DOCS=true`) for dev.

#### D-013: In-memory session store doesn't survive restarts (Severity: Warning)

**What**: `InMemorySessionStore` loses all sessions on container restart.

**Impact**: All users logged out on every deploy. Acceptable for early production — annoying but
not broken. Users just re-login.

**Future fix**: Redis-backed session store (already has `REDIS_URL` setting placeholder).

#### D-014: JWKS registry path needs persistence (Severity: Warning)

**What**: `EphemeralKeyCache` writes a JWKS registry file to `platformdirs.user_data_dir()`.
Inside a Docker container, this path is ephemeral by default.

**Impact**: On container restart, old ephemeral keys are lost → tokens issued before the restart
can't be verified until they expire. The registry file is specifically designed to survive restarts
so old keys remain verifiable.

**Fix**: Set `JWKS_REGISTRY_PATH` to a path on a mounted Docker volume
(e.g., `/data/jwks-registry.json`).

#### D-015: Health endpoint is too simple for Docker healthcheck (Severity: Nice-to-have)

**What**: `/auth/health` returns `{"service": "dockmaster", "status": "ok"}` unconditionally.
It doesn't check if GCP credentials are loaded, OAuth is configured, or SM is reachable.

**Impact**: Docker healthcheck will report healthy even if the service is broken.

**Fix**: Optionally add a "deep health" that checks `app.state` singletons are initialized.
For now, a simple HTTP 200 check is sufficient for Docker.

#### D-016: No `HOST`/`PORT` settings for uvicorn bind (Severity: Warning)

**What**: The app doesn't have configurable host/port settings. The `app = create_app()` module
variable works with `uvicorn dockmaster.main:app` but the bind address is only configured via
uvicorn CLI flags.

**Impact**: Need to pass `--host 0.0.0.0 --port 8000` via Docker CMD. Not a code issue, just a
Dockerfile concern.

**Fix**: Document in Dockerfile CMD.

---

## 3. Caddy Integration Plan

### Routing

Subdomain-based: `auth.insilicostrategy.com` routes to dockmaster, existing domain routes to Astro.

### Draft Caddyfile

```caddy
# Existing site
insilicostrategy.com, www.insilicostrategy.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:4321
}

# Dockmaster auth service
auth.insilicostrategy.com {
    encode zstd gzip

    # Forward proxy headers so the app knows the real client IP and protocol
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Real-IP {remote_host}
    }

    # Security headers
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }

    # Rate limit auth endpoints (optional, Caddy rate_limit plugin required)
    # rate_limit /auth/login* 10r/m
    # rate_limit /auth/exchange* 30r/m
    # rate_limit /auth/token* 30r/m
}
```

**Notes**:
- Caddy automatically handles TLS for new subdomains via Let's Encrypt
- Cloudflare DNS needs an `A` record for `auth` pointing to the droplet IP (DNS only initially,
  then proxied after cert is obtained — same flow as the main site)
- Caddy sends `X-Forwarded-For` and `X-Forwarded-Proto` by default in `reverse_proxy` — the
  explicit `header_up` lines above are for clarity, but Caddy does this automatically
- The `header` block adds security headers at the proxy level (defense in depth)

### TLS Implications

- Caddy terminates TLS → app sees HTTP on `127.0.0.1:8000`
- Session cookies need `Secure` flag → requires the app to trust `X-Forwarded-Proto: https`
  (uvicorn `--proxy-headers` flag)
- OAuth redirect URIs must use `https://auth.insilicostrategy.com/auth/callback`
- GCP OAuth console needs this redirect URI added

---

## 4. Docker Compose Integration Plan

### Draft docker-compose.yml

```yaml
services:
  # Existing Astro site
  web:
    image: ${DOCKER_IMAGE:-insilicostrategy}:${DOCKER_TAG:-latest}
    environment:
      - HOST=0.0.0.0
      - PORT=4321
    ports:
      - "127.0.0.1:4321:4321"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:4321/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # Dockmaster auth service
  dockmaster:
    image: dockmaster:${DOCKMASTER_TAG:-latest}
    env_file:
      - .env.dockmaster
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      # GCP credential files (SCP'd to droplet)
      - /opt/insilicostrategy/secrets/sa-key.json:/secrets/sa-key.json:ro
      - /opt/insilicostrategy/secrets/admin-sa-key.json:/secrets/admin-sa-key.json:ro
      # Persistent JWKS registry (survives container restarts)
      - dockmaster-data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/auth/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

volumes:
  dockmaster-data:
```

### Networking

- Both services bind to `127.0.0.1` — only Caddy can reach them
- No Docker network needed — Caddy is a system service accessing localhost ports
- Dockmaster on port 8000, Astro on port 4321 — no conflict

### Environment File (`.env.dockmaster`)

```bash
# GCP
SA_KEY_FILE=/secrets/sa-key.json
ADMIN_SA_KEY_FILE=/secrets/admin-sa-key.json
SECRETS_PROJECT=your-gcp-project-id

# OAuth
CLIENT_ID=your-oauth-client-id.apps.googleusercontent.com
CLIENT_SECRET=your-oauth-client-secret

# Session (REQUIRED — no default, app won't start without it)
SESSION_SECRET_KEY=generate-a-random-64-char-string-here

# Proxy (default is true — only set false for local dev without reverse proxy)
# REQUIRE_PROXY_HEADERS=false

# Auth
AUTHORIZED_ISSUERS=accounts.google.com,dockmaster
AUTHORIZED_DOMAINS=insilicostrategy.com
DOCKMASTER_ADMIN_EMAILS=nicholasgrundl@gmail.com

# Redirect URIs (CLI localhost + any external services)
ALLOWED_REDIRECT_URIS=http://localhost:9876/callback

# CORS (if Astro site calls dockmaster API cross-origin)
ALLOWED_ORIGINS=https://insilicostrategy.com

# Persistence
JWKS_REGISTRY_PATH=/data/jwks-registry.json

# Logging
LOG_LEVEL=INFO
```

---

## 5. Dockerfile Plan (dockmaster)

### Draft Dockerfile

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install production dependencies only
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ ./src/

# Run as non-root user
RUN useradd --create-home appuser
USER appuser

# Create data directory for JWKS registry
RUN mkdir -p /home/appuser/data

EXPOSE 8000

# Start uvicorn with proxy headers enabled
CMD ["uv", "run", "uvicorn", "dockmaster.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "127.0.0.1"]
```

**Notes**:
- Uses `uv` for fast, reproducible installs
- `--proxy-headers` + `--forwarded-allow-ips` trust only Caddy (localhost)
- Non-root user for security
- Slim base image (~150MB vs ~1GB full)
- `uv.lock` doesn't exist yet — need `uv lock` before first build

---

## 6. GCP Credentials in Production

### Credential Files Needed

| File | Purpose | Source |
|---|---|---|
| `sa-key.json` | JWT signing, Secret Manager reads | GCP Console → IAM → Service Accounts |
| `admin-sa-key.json` | RBAC write operations (SM writes) | GCP Console → IAM → Service Accounts |

### Transfer Process

```bash
# From local machine
scp ~/.dockmaster/sa-key.json root@DROPLET_TAILSCALE_IP:/opt/insilicostrategy/secrets/sa-key.json
scp ~/.dockmaster/admin-sa-key.json root@DROPLET_TAILSCALE_IP:/opt/insilicostrategy/secrets/admin-sa-key.json

# Lock permissions on droplet
ssh root@DROPLET_TAILSCALE_IP "chmod 600 /opt/insilicostrategy/secrets/*.json"
```

### OAuth Redirect URI

Add to GCP OAuth consent screen → Authorized redirect URIs:
- `https://auth.insilicostrategy.com/auth/callback`
- Keep `http://localhost:8000/auth/callback` for local dev

### Rotation Plan

1. Generate new SA key in GCP Console
2. SCP new key to droplet (same path)
3. `docker compose restart dockmaster`
4. Delete old key in GCP Console
5. No downtime — key is loaded at container startup

---

## 7. Deployment Blockers Summary

| ID | What | Severity | Category | Fix in |
|---|---|---|---|---|
| D-010 | No trusted proxy header config — fix: uvicorn `--proxy-headers` flag + `REQUIRE_PROXY_HEADERS` middleware (default `True`) | **Blocker** | App Config | Phase 9 |
| D-011 | Session secret key defaults to insecure value — fix: remove default, make required | **Blocker** | Security | Phase 9 |
| D-012 | OpenAPI docs (`/docs`, `/openapi.json`) exposed by default | Warning | Security | Phase 9 |
| D-013 | In-memory session store — all sessions lost on restart | Warning | App Config | Backlog (Redis) |
| D-014 | JWKS registry path needs Docker volume for persistence | Warning | App Config | Phase 9 |
| D-015 | Health endpoint doesn't check service dependencies | Nice-to-have | App Config | Backlog |
| D-016 | No configurable host/port — managed via uvicorn CLI flags | Nice-to-have | App Config | Phase 9 (Dockerfile) |

### Pre-deployment Checklist (Phase 9 scope)

- [ ] Add `--proxy-headers --forwarded-allow-ips 127.0.0.1` to uvicorn startup (D-010)
- [ ] Add startup validation for session secret key (D-011)
- [ ] Disable OpenAPI docs in production (D-012)
- [ ] Create Dockerfile for dockmaster (D-016)
- [ ] Create `.env.dockmaster` template
- [ ] Add `auth.insilicostrategy.com` block to Caddyfile
- [ ] Add dockmaster service to docker-compose.yml
- [ ] Create `/opt/insilicostrategy/secrets/` directory on droplet
- [ ] SCP GCP credential files to droplet
- [ ] Add `https://auth.insilicostrategy.com/auth/callback` to GCP OAuth redirect URIs
- [ ] Add Cloudflare DNS `A` record for `auth` subdomain
- [ ] Generate a strong `SESSION_SECRET_KEY`
- [ ] Set `JWKS_REGISTRY_PATH=/data/jwks-registry.json` (D-014)
- [ ] Run `uv lock` to create lockfile for Docker build
- [ ] Test full flow: login → session → token issuance → RBAC check

### Resource Assessment

The 1 GB / 1 vCPU droplet is tight but workable:
- Astro (Node.js): ~80-120 MB RAM
- Dockmaster (Python/uvicorn): ~60-100 MB RAM
- Caddy: ~20 MB RAM
- Docker overhead: ~100 MB
- **Total estimated**: ~360-440 MB, leaving ~560-640 MB free

This should work for low-traffic use. If you see memory pressure, the cheapest upgrade is the
2 GB / 1 vCPU tier. Watch for GCP SDK memory usage — the google-cloud libraries can be
memory-hungry on first load.
