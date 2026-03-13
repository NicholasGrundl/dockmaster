---
state: Draft
changelog:
  "2026-03-12 16h": "Added Phase 6 findings: 503 info leak concern, authority type annotation audit"
  "2026-03-12": "Created — auth surface audit phase, unified Mermaid DAG"
---

# Phase 8a: Auth + API Surface Audit — Endpoint Inventory + Mermaid DAG

> Comprehensive audit of all HTTP endpoints and auth boundaries, producing a unified Mermaid DAG
> showing every possible request path through the system with pass/fail decision nodes.

**Status**: Planned
**Priority**: P1
**Phase**: 8a (after Phase 7 Redirect+Keypair, before Phase 9 Deployment)
**Last updated**: 2026-03-13

---

## Problem

Before deploying behind a Caddy reverse proxy, we need confidence that:
1. Every endpoint that should require auth actually does
2. Unauthenticated users can only access intentionally-public endpoints
3. The auth decision chain is correct (no bypass paths)
4. The system behaves correctly behind a reverse proxy (headers, cookies, redirects)

## Scope

**Audit + document only.** Flag gaps but don't fix them — fixes go into Phase 7 or a dedicated
hardening phase if warranted.

## Deliverables

### 1. Endpoint Inventory Table

Markdown table in the audit doc listing every endpoint with:

| Endpoint | Method | Auth Mechanism | Public? | Notes |
|---|---|---|---|---|
| `/` | GET | None | Yes | Service info |
| `/auth/health` | GET | None | Yes | Health check |
| `/auth/key/{kid}` | GET | None | Yes | Public key distribution (intentionally open) |
| `/auth/login` | GET | None | Yes | OAuth redirect initiation |
| `/auth/callback` | GET | None | Yes | OAuth callback (state validated internally) |
| `/auth/logout` | GET | None | Yes | Session destruction |
| `/auth/principal` | GET | None (session) | Semi | Returns `{}` if no session, profile if session exists |
| `/auth/claims` | GET | Bearer JWT | No | Returns decoded JWT claims |
| `/auth/exchange` | POST | Bearer JWT/access token | No | Token exchange |
| `/auth/refresh` | POST | None (body params) | Semi | Requires valid refresh_token in body |
| `/auth/has/{s}/{t}/{p}` | GET | Bearer JWT | No | RBAC permission check |
| `/auth/has` | GET | Bearer JWT | No | RBAC permission check (query variant) |
| `/ui/login` | GET | None | Yes | Login page HTML |
| `/ui/` | GET | Session cookie | No | Admin dashboard |

*Phase 6 and 6b will add more endpoints — update this table when those phases complete.*

### 2. Unified Auth DAG (Mermaid)

A single Mermaid flowchart showing:

- **Entry nodes**: Each endpoint (or endpoint group) as a starting point
- **Decision nodes**: Auth checks (has Bearer token? → token valid? → has session cookie? → session valid? → has RBAC permission?)
- **Outcome nodes**: Success responses (200/204) and failure responses (401/403/422/503)
- **Edge labels**: What triggers each transition (pass/fail, redirect, error)

The DAG should make it visually obvious:
- Which endpoints skip auth entirely
- Where unauthenticated requests get stopped
- The difference between API auth (JWT) and UI auth (session cookie)
- What an attacker with no credentials can reach

#### DAG Structure (draft)

```
Request arrives
  → Route matched?
    → No → 404
    → Yes → Which endpoint group?
      → Public (health, key, login page, OAuth flow) → Response directly
      → API-protected (claims, exchange, has) → Bearer token present?
        → No → 401
        → Yes → JWT valid (signature, expiry, issuer)?
          → No → 401
          → Yes → Endpoint-specific logic → 200/204/403/500
      → Session-protected (dashboard) → Session cookie present?
        → No → Redirect to /ui/login
        → Yes → Session valid (exists in store, not expired)?
          → No → Redirect to /ui/login
          → Yes → Render page
      → Semi-protected (principal, refresh) → [endpoint-specific checks]
```

### 3. Reverse Proxy Considerations

Document for Caddy deployment:
- Which headers Caddy must forward (`X-Forwarded-For`, `X-Forwarded-Proto`, etc.)
- Cookie behavior: `Secure` flag, `SameSite`, domain scoping
- Redirect URLs: do `/auth/callback` and `/auth/login` use absolute URLs that need to match the external hostname?
- HTTPS termination: does the app need to know it's behind TLS? (session cookies, OAuth redirect URIs)
- CORS: any cross-origin concerns if UI and API are on same domain?

### 4. Gap Analysis

For each finding:
- **What**: Description of the gap or concern
- **Risk**: Low / Medium / High
- **Recommendation**: What to fix and when (Phase 7 or separate)

Example findings to investigate:
- Is `/auth/refresh` too open? (anyone with a valid Google refresh token can get a dockmaster JWT)
- Are session cookies `HttpOnly` and `Secure`?
- Does `/auth/principal` leak info to unauthenticated users? (currently returns `{}`, which is fine)
- Are error responses consistent (no stack traces in production)?
- Does the `require_admin_writes` 503 message ("admin SA key not set") leak infrastructure details to callers? Should it be a generic "service unavailable" instead?
- Type annotations across auth modules — `auth/admin.py` uses `object | None` for `authority` parameter. Audit all auth module signatures for proper typing (Protocol or ABC for Authority).
- Grants allow referencing nonexistent role names — no validation that role names in a grant actually exist in SM. Typos silently fail (Authority skips missing roles with a warning). Consider: validate on write (hard-fail or warn?), validate on UI form submission, or surface warnings in the grants detail page.
- Admin self-revocation returns raw 403 JSON instead of graceful redirect — when an admin removes their own grant via the UI, the POST redirect hits `require_admin_ui` which returns a JSON 403. Should redirect to dashboard or logout with a message instead. Decide: should self-revocation be allowed? If yes, catch 403 and redirect gracefully.

## Output Files

- `_blueprint/features/audit-auth-surface.md` — full audit document with table, gaps, proxy notes
- `_blueprint/features/auth-dag.md` — the Mermaid DAG (separate file so it renders cleanly on GitHub)

## Implementation Sub-tasks

- [ ] 1. Read every route module and document the auth mechanism used
- [ ] 2. Read middleware, session, and RBAC auth code paths
- [ ] 3. Build the endpoint inventory table
- [ ] 4. Build the unified Mermaid DAG
- [ ] 5. Document reverse proxy considerations for Caddy
- [ ] 6. Write gap analysis with risk ratings
- [ ] 7. Review with user

## Acceptance Criteria

- [ ] Every HTTP endpoint is listed in the inventory table
- [ ] The Mermaid DAG renders correctly and shows all auth decision paths
- [ ] Reverse proxy section covers headers, cookies, redirects, TLS
- [ ] Gap analysis flags any endpoints with surprising auth behavior
- [ ] No code changes — audit and documentation only
