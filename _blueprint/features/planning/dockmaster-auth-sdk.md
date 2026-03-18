# Feature: dockmaster-auth SDK & Consumer Packages

> Core packages that let any service (Python, Node.js, browser SPA) integrate with Dockmaster for authentication and authorization.

**Status**: Planning
**Priority**: P1
**Phase**: TBD (post Phase 9b)
**Last updated**: 2026-03-18

---

## Problem

Dockmaster is an auth microservice — but consuming services have no turnkey way to integrate with it. Today, a developer would need to:
- Manually fetch public keys and verify JWTs with PyJWT
- Write their own HTTP client for permission checks
- Implement login redirect + token management from scratch
- Figure out cookie domain, CORS, and session sharing on their own

We need published packages that make integration a one-liner for each consumer type.

## Vision

Dockmaster is a **central auth microservice** for any domains the admin controls. With GCP project setup, it manages:
- Service-to-service auth (SA key → Type C JWT → call other services)
- Browser user sessions (SSO login → shared session cookie → call APIs)
- SPA-to-backend flows (session cookie for auth, Type C JWT for API calls)

The SDK packages make this easy to consume from any stack.

---

## Consumer Profiles

### Consumer B — Backend Service (Python / Node.js)

A service that has a Google SA key and needs to:
1. **Obtain** Type C JWTs by exchanging SA-signed JWTs via `/auth/exchange`
2. **Verify** incoming Type C JWTs on its own endpoints (fetch public keys from Dockmaster, verify locally with PyJWT)
3. **Check permissions** via `/auth/has/{subject}/{target}/{permission}` endpoint
4. **Enforce RBAC** using utilities that compose email + permissions into authorization decisions

The SA key and its RBAC grants are controlled by the Dockmaster admin. The admin creates the SA, assigns roles/permissions, and the service operates within those bounds.

**Token refresh**: Call `/auth/exchange` again with the SA key. SA keys don't expire (they're rotated by the admin), so this is always available.

### Consumer C — Browser App (SPA / SSR)

A browser-based application (e.g., Astro SPA) that needs to:
1. **Login** — redirect user to Dockmaster, handle callback, establish session
2. **Use session** — shared session cookie works across all apps under the admin's domain
3. **Obtain Type C JWTs** — call `/auth/token?service=X` with session cookie for API calls
4. **Call backend APIs** — attach Type C JWT to requests to Consumer B services
5. **Token management** — refresh before expiry, handle expiration gracefully

**Token refresh**: Call `/auth/token?service=X` with the session cookie. As long as the session is valid, new Type C JWTs can be obtained.

**Forced logout**: Admin revokes the session — user is logged out across all apps that share the session cookie. Type C JWTs already issued expire naturally (short TTL, default 15 min).

**Session lifecycle**:
- Created on successful OAuth login
- Shared across all apps under the same parent domain (via cookie domain setting)
- Expires after `SESSION_TTL` (default 1 hour) of inactivity
- Destroyed on explicit logout or admin revocation

### Note: No "Consumer A"

We originally considered a "Consumer A" profile — a backend service that only verifies Type C JWTs without an SA key. This doesn't stand on its own because calling Dockmaster's permission check endpoints requires authentication (Bearer JWT). Every backend service needs an SA key to interact with Dockmaster, making it Consumer B.

---

## Packaging Strategy

### Python: Single package with extras

One package on PyPI called `dockmaster`:

| Install | What you get | Use case |
|---|---|---|
| `pip install dockmaster` | Core SDK — JWT verification, permission checks, FastAPI dependencies, SA signer | Consumer B (backend service) |
| `pip install dockmaster[service]` | Core + full auth microservice (routes, CLI, admin UI, OAuth, GCP Secret Manager) | Running the Dockmaster service itself |

All source code ships in the wheel. The extras control which **dependencies** are installed. Service-only modules guard their imports via a capabilities singleton:

```python
# src/dockmaster/capabilities.py
def _has(module: str) -> bool:
    from importlib.util import find_spec
    return find_spec(module) is not None

HAS_SERVICE = _has("authlib") and _has("google.cloud.secretmanager")

def require_service(feature: str = "This feature") -> None:
    if not HAS_SERVICE:
        raise ImportError(
            f"{feature} requires the [service] extra. "
            "Install with: pip install dockmaster[service]"
        )
```

Service-only modules check this at import time:
```python
# src/dockmaster/routes/__init__.py
from dockmaster.capabilities import require_service
require_service("dockmaster.routes")
```

### JavaScript/Node.js: `@dockmaster/auth`

npm package for backend (Express/Koa/etc.) and browser (SPA) consumers:

- JWT verification middleware (Consumer B)
- Permission check client (Consumer B)
- Login redirect + callback handler (Consumer C)
- Token management + fetch wrapper (Consumer C)

### Open Questions — Package Boundaries

- [ ] Where does `google-auth` land? Core needs it for `ServiceAccountSigner` and `ServiceAccountKeyCache`. It's ~2MB. If it's in core, Consumer B gets it automatically. If it's a separate extra (`dockmaster[google]`), core stays lighter but Consumer B always needs it.
- [ ] Should `rbac/authority.py` be core? It's pure logic (no GCP imports) but Consumer B would typically check permissions over HTTP, not run the Authority engine locally.
- [ ] Should `itsdangerous` be core? Needed for session cookie verification, which Consumer B might do if it receives session cookies (shared domain scenario).

---

## Core/Service Module Split

| Core (always available) | Service (requires `[service]`) |
|---|---|
| `auth/jwt_verifier.py` — ServiceRealm, JWT verification | `routes/*` — all FastAPI route modules |
| `auth/key_cache.py` — EphemeralKeyCache, ServiceAccountKeyCache | `cli/*` — Typer CLI |
| `auth/jwt_signers.py` — ServiceAccountSigner, EphemeralKeypairSigner | `sessions/*` — SessionStore, InMemorySessionStore |
| `auth/dependencies.py` — gates, check_permission, utilities | `templates/*` — Jinja2 HTML templates |
| `auth/token_validator.py` — Google access token validation | `auth/oauth.py` — Authlib OAuth client |
| `rbac/models.py` — Role, Grant, ServiceGrants | `rbac/storage.py` — SecretsStorage (GCP SM) |
| `config.py` — Settings | `rbac/admin_ops.py` — admin CRUD operations |
| `middleware.py` — SecurityHeaders, RequireProxyHeaders | `main.py` — app factory, lifespan |
| `capabilities.py` — import guards (new) | `ui/*` — UIConfig |

**Gray areas to resolve:**
- `auth/oauth.py` — depends on authlib (service), but Consumer C's Node.js client might reference its patterns
- `rbac/authority.py` — pure logic, no GCP imports, but is it useful outside the service?
- `auth/ttl_store.py` — generic utility, could be core
- `auth/auth_code.py` — auth code store, only used by service routes

---

## Critical Design Review: Cross-Domain Session & Cookie Architecture

> **This section requires a dedicated planning session before implementation.**

The original design assumed Dockmaster would serve its own UI and consumers would use the auth code flow. The revised vision is that Dockmaster acts as a **central auth service for all domains the admin controls**, with shared sessions across apps.

### What this means

```
auth.example.com      ← Dockmaster
app.example.com       ← Astro SPA (Consumer C)
api.example.com       ← FastAPI backend (Consumer B)
billing.example.com   ← Another service (Consumer B)
```

A user logs in once at `auth.example.com`. The session cookie is shared across all `*.example.com` subdomains. The SPA at `app.example.com` can call `/auth/token?service=api` with the session cookie to get a Type C JWT, then call `api.example.com` with that JWT.

### What needs review

**1. Cookie domain & scope**
- New setting: `SESSION_COOKIE_DOMAIN` (e.g., `.example.com`)
- Cookie flags: `HttpOnly`, `Secure`, `SameSite=Lax` (or `None` for cross-subdomain?)
- What happens when apps are NOT on the same parent domain? Fall back to auth code flow?
- Current implementation: `itsdangerous` signed cookie — does cookie domain affect signature verification?

**2. CORS policy**
- Current: `ALLOWED_ORIGINS` controls which origins can make cross-origin requests
- With shared sessions: SPAs on different subdomains need CORS with `credentials: true`
- Need to ensure `Access-Control-Allow-Origin` is NOT `*` when `credentials: true` (browser rejects this)
- Per-origin CORS headers (already supported — Starlette CORSMiddleware does this)

**3. Session validation for external apps**
- Current: only Dockmaster's own routes verify sessions (via `allow_session` dependency)
- External apps receive the session cookie but can't validate it themselves
- Options:
  - **Validation endpoint**: `GET /auth/session/validate` — external app forwards cookie, Dockmaster returns user info or 401
  - **Middleware proxy**: consumer SDK middleware that calls Dockmaster on each request to validate the session
  - **Session token introspection**: external app verifies the signed cookie locally (needs shared secret — security concern)
- Recommendation: validation endpoint is simplest and most secure. Consumer SDK middleware calls it with caching.

**4. Audience and service mapping**
- Type C JWTs have an `aud` claim set to the target service name (e.g., `billing`)
- How does this map to actual service domains? Is `billing` → `billing.example.com` implicit, or configured?
- Should Dockmaster maintain a service registry mapping service names to domains/URLs?
- How does the SPA know which service name to request when calling `/auth/token?service=X`?

**5. Multi-domain support**
- The vision is Dockmaster manages auth for "any domains the admin controls"
- Single parent domain (*.example.com) — shared cookie works naturally
- Multiple parent domains (example.com + otherdomain.com) — cookies can't cross, need auth code flow
- Should Dockmaster support both patterns? Shared cookie for same-domain, auth code for cross-domain?

**6. Security implications**
- Shared cookie across subdomains: if ANY subdomain is compromised, the session is compromised
- Subdomain takeover risk: unused DNS records could be hijacked to steal cookies
- CSRF: `SameSite=Lax` mitigates, but cross-subdomain POST requests need review
- Cookie theft via XSS on any subdomain: `HttpOnly` prevents JS access, but HTTP response splitting or other attacks could leak it

**7. Existing Starlette SessionMiddleware interaction**
- Dockmaster currently has TWO cookies: `session_id` (application) and `session` (Starlette/Authlib)
- The Starlette `session` cookie is used during OAuth flow only
- For cross-domain sharing, only `session_id` should be shared — the Starlette cookie should stay scoped to Dockmaster's host
- Need to verify both cookies can have different domain scopes

### Decisions needed before implementation

- [ ] Shared cookie domain as the primary Consumer C pattern, auth code flow as fallback for third-party domains?
- [ ] Session validation endpoint design (path, response shape, caching strategy)
- [ ] Service name → domain mapping strategy (convention, config, or registry?)
- [ ] Multi-domain story — support both shared cookie and auth code, or pick one?
- [ ] Cookie security review (SameSite, Secure, domain scope, subdomain takeover mitigation)

---

## CI/CD Plan

### GitHub Actions

**Python package (PyPI)**:
- Trigger: git tag matching `dockmaster-v*`
- Steps: `just check` → `uv build --wheel` → publish to PyPI
- Uses trusted publisher (OIDC) — no API tokens stored in secrets
- Optional: publish to GCP Artifact Registry for private forks

**JavaScript package (npm)**:
- Trigger: git tag matching `dockmaster-auth-js-v*`
- Steps: lint → test → `npm publish`
- Scoped package: `@dockmaster/auth`

**GCP Artifact Registry (optional, for private forks)**:
- Same build steps, different publish target
- Configurable via repository secret (`GCP_ARTIFACT_REGISTRY`)
- Users who fork and want private hosting just set the secret and push a tag

### Monorepo structure

```
.
├── src/dockmaster/          Python package (core + service)
├── packages/
│   └── auth-js/             @dockmaster/auth npm package
│       ├── src/
│       ├── package.json
│       └── tsconfig.json
├── tests/                   Python tests
├── pyproject.toml           Python project config
├── justfile                 Dev commands
└── .github/
    └── workflows/
        ├── ci.yml           Lint + test on PR
        ├── publish-py.yml   Publish Python to PyPI on tag
        └── publish-js.yml   Publish JS to npm on tag
```

---

## Dependencies

- **Requires**: Phase 9b (documentation) complete — consumer docs reference SDK packages
- **Requires**: Cross-domain session design review (this doc, section above)
- **Enables**: Consumer B and C integration guides (GUIDE-04, GUIDE-05)
- **Enables**: First consuming services (Astro SPA + backend)

## Open Questions

1. **`google-auth` in core or extra?** — affects Consumer B install experience
2. **Service name → domain mapping** — convention vs configuration vs registry
3. **Consumer A eliminated?** — confirm every backend service needs an SA key
4. **Session validation endpoint** — needed for shared cookie model, design TBD
5. **Cookie domain configuration** — single parent domain only, or multi-domain support?
6. **Auth code flow** — keep as fallback for cross-domain, or deprecate in favor of shared cookies?

## Acceptance Criteria

- [ ] `pip install dockmaster` provides working JWT verification + permission check client
- [ ] `pip install dockmaster[service]` runs the full auth microservice (no regressions)
- [ ] `capabilities.py` singleton guards service-only imports with clear error messages
- [ ] `@dockmaster/auth` npm package provides JWT verification + login flow for Node.js/SPA
- [ ] GitHub Actions publish Python to PyPI and JS to npm on tag push
- [ ] Cross-domain session design reviewed and decided (separate planning session)
- [ ] Consumer integration guide (GUIDE-04) covers both Consumer B and C patterns
