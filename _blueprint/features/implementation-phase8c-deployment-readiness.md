---
state: Draft
changelog:
  "2026-03-16": "Created — deployment readiness audit spec, interview-driven Caddy/Docker planning"
---

# Phase 8c: Deployment Readiness

> Audit the application for deployment blockers and plan integration into the user's existing
> DigitalOcean + Docker Compose + Caddy stack.

**Status**: Planned
**Priority**: P1
**Phase**: 8c
**Last updated**: 2026-03-16
**Depends on**: Phase 8a (security findings), Phase 8b (code quality findings)
**Output**: `_blueprint/features/audit-8c-deployment-readiness-findings.md`

---

## Problem

Dockmaster needs to be deployed alongside the user's existing Astro-based personal website on a
DigitalOcean droplet running Docker Compose with Caddy as reverse proxy. Before deployment (Phase 9),
we need to:

1. Identify anything in the app that would break behind a reverse proxy
2. Plan how dockmaster integrates into the existing Docker Compose stack
3. Ensure production settings, secrets, and env vars are properly handled
4. Flag deployment-blocking issues for Phase 9 to fix

## Approach

This phase starts with an **interview** to gather details about the existing deployment setup.
The user has an Astro site on a DO droplet with Docker Compose + Caddy — we need to understand
that stack before planning dockmaster's integration.

## Deliverables

### 1. Deployment Context Interview

Gather from the user:

- **Current stack**: Docker Compose services, Caddy config (Caddyfile), networking setup
- **Domain/DNS**: What domain(s) will dockmaster run on? Subdomain? Same domain different path?
- **TLS**: Caddy auto-TLS? Custom certs? What domains are covered?
- **Secrets management**: How are secrets currently handled? `.env` files? Docker secrets?
  Does the DO droplet have access to GCP credentials?
- **Deployment process**: How do you currently deploy? git pull + docker compose up?
  CI/CD? Manual?
- **Resource constraints**: Droplet size, memory, disk. Can it handle another service?

### 2. Application Readiness Audit

Check the dockmaster app for production readiness:

- **Hardcoded values**: Any localhost URLs, debug flags, or dev-only settings that would
  break in production?
- **Environment variables**: Complete list of required env vars for production. Which have
  safe defaults, which must be set?
- **Trusted proxy headers**: Does the app respect `X-Forwarded-For`, `X-Forwarded-Proto`?
  FastAPI/Starlette's `--proxy-headers` flag. Does `ALLOWED_REDIRECT_URIS` need the
  external hostname?
- **OAuth redirect URIs**: Callback URL must match the production domain. GCP OAuth consent
  screen needs the production redirect URI added.
- **Session cookies**: `Secure` flag requires HTTPS. `Domain` scoping if using subdomains.
  `SameSite` policy for cross-origin flows.
- **CORS**: `ALLOWED_ORIGINS` must include the production origin if UI and API are cross-origin.
- **Logging**: Is structlog configured for production (JSON output, appropriate log level)?
- **Health check**: Does `/auth/health` return meaningful status for Docker health checks?

### 3. Caddy Integration Plan

Based on the interview, document:

- **Routing**: How Caddy routes requests to dockmaster vs the Astro site
  (subdomain-based? path-based?)
- **Headers**: Which headers Caddy must forward (`X-Forwarded-For`, `X-Forwarded-Proto`,
  `Host`, `X-Real-IP`)
- **TLS termination**: Caddy handles TLS, app sees HTTP. Implications for cookie Secure flag,
  OAuth redirect URIs, HSTS
- **WebSocket**: Not currently needed, but note if any future features would require it
- **Rate limiting**: Should Caddy rate-limit auth endpoints? (login, exchange, token)
- **Draft Caddyfile snippet**: Example config block for the dockmaster service

### 4. Docker Compose Integration Plan

- **Service definition**: dockmaster service with image, ports, env, health check, restart policy
- **Networking**: How dockmaster connects to Caddy (shared Docker network, internal port exposure)
- **Volumes**: GCP credential files, JWKS registry, any persistent state
- **Environment**: `.env` file structure, secret injection approach
- **Build vs image**: Build from source on droplet vs pre-built image from registry?
- **Draft docker-compose.yml snippet**: Example service block

### 5. GCP Credentials in Production

- **Service account keys**: How to securely get SA key files onto the droplet
- **OAuth client secret**: Currently in GCP Secret Manager — does the droplet have SM access,
  or should it be injected as env var?
- **Admin SA**: Needed for RBAC writes — same key file question
- **Rotation plan**: How to rotate keys without downtime

### 6. Deployment Blockers

Issues that must be fixed before going live:

| Field | Description |
|---|---|
| ID | Sequential (D-001, D-002, ...) |
| What | Description of the blocker |
| Severity | Blocker / Warning / Nice-to-have |
| Category | App Config / Infrastructure / Security / GCP |
| Fix in | Phase 9 task reference |

## Implementation Sub-tasks

- [ ] 1. Interview user about existing deployment stack
- [ ] 2. Audit app for production readiness (env vars, hardcoded values, proxy headers)
- [ ] 3. Document Caddy integration plan (routing, headers, TLS, rate limiting)
- [ ] 4. Document Docker Compose integration plan (service, networking, volumes)
- [ ] 5. Document GCP credential handling for production
- [ ] 6. Write deployment blockers list
- [ ] 7. Review findings with user

## Acceptance Criteria

- [ ] User's existing deployment stack is documented and understood
- [ ] All required env vars for production are listed
- [ ] Caddy integration plan covers routing, headers, TLS, cookies
- [ ] Docker Compose plan covers service definition, networking, secrets
- [ ] GCP credential strategy for production is documented
- [ ] Deployment blockers are listed with severity ratings
- [ ] No code changes — planning and documentation only
