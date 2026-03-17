---
state: Draft
changelog:
  "2026-03-16": "Created — restructured from original 8a spec, expanded scope for Phase 7 completeness"
---

# Phase 8a: Security Audit

> Comprehensive security audit of all HTTP endpoints, auth boundaries, and information leakage.
> Produces findings doc only — no code changes.

**Status**: Planned
**Priority**: P0
**Phase**: 8a
**Last updated**: 2026-03-16
**Depends on**: Phase 7 complete
**Output**: `_blueprint/features/audit-8a-security-findings.md`

---

## Problem

Dockmaster is approaching deployment. Before going live we need confidence that:
1. Every endpoint that should require auth actually does
2. No information leaks to unauthenticated users (API docs, error messages, headers)
3. Auth decision paths have no bypass routes
4. Session and token handling follows security best practices

## Deliverables

### 1. Complete Endpoint Inventory

Markdown table listing **every** HTTP endpoint with:

| Column | Description |
|---|---|
| Endpoint | Route pattern |
| Method | HTTP method(s) |
| Auth Mechanism | None / Bearer JWT / Session cookie / Admin (RBAC + email whitelist) / Dual (session or JWT) |
| Public? | Yes / No / Semi (conditional) |
| Notes | Auth nuances, edge cases |

Must include all endpoints from Phases 1–7:
- Health, info, key distribution
- OAuth flow (login, callback, logout, principal)
- JWT operations (claims, exchange, token, code/exchange)
- RBAC checks (has permission)
- RBAC grants (get permissions)
- Admin CRUD (roles, grants, sessions)
- Admin UI pages (dashboard, roles, grants, sessions, login)
- Refresh endpoint

### 2. Auth Decision DAG (Mermaid)

Single Mermaid flowchart showing every possible request path:

- **Entry nodes**: Request arrives at each endpoint group
- **Decision nodes**: Auth checks (Bearer present? → JWT valid? → Session present? → Session valid? → Is admin? → Has RBAC permission?)
- **Outcome nodes**: Success (200/204), redirect (302 → /ui/login), and error (401/403/404/422/503)
- **Edge labels**: Pass/fail conditions

The DAG should make visually obvious:
- Which endpoints skip auth entirely
- Where unauthenticated requests get stopped
- The difference between API auth (JWT) and UI auth (session cookie)
- Admin auth chain (RBAC-first + email whitelist fallback)
- Dual-auth paths (token endpoint accepts session or JWT)

### 3. Information Leakage Audit

Check and document:

- **OpenAPI docs**: Are `/docs` and `/redoc` publicly accessible? They expose the full API surface including protected endpoints, request/response schemas, and parameter names. **This is a known issue.**
- **Error responses**: Do 401/403/500 responses include stack traces, internal paths, or implementation details?
- **503 capability gate**: Does the "admin SA key not set" message in `require_admin_writes` leak infrastructure details?
- **Response headers**: Does the server expose `Server`, `X-Powered-By`, or other fingerprinting headers?
- **Session data**: Is anything sensitive stored in the session cookie vs server-side? Is the cookie HttpOnly + Secure + SameSite?
- **OAuth state**: Is the CSRF state parameter properly validated? Are tokens ever exposed in URLs or logs?
- **CORS configuration**: Is `ALLOWED_ORIGINS` properly restrictive? Are credentials allowed?

### 4. Auth Boundary Analysis

For each protected endpoint, verify:

- **JWT endpoints**: What happens with no token? Expired token? Valid token for wrong audience? Malformed token?
- **Session endpoints**: What happens with no cookie? Expired session? Tampered cookie?
- **Admin endpoints**: What happens with valid JWT but no admin role? With admin role but no write capability?
- **Auth code flow**: Is the code single-use? Does it expire? Can it be replayed?
- **Token delivery**: Are tokens ever passed in query parameters (visible in logs/history)?
- **Refresh endpoint**: Can anyone with a valid Google refresh token mint a dockmaster JWT? Is this intentional?

### 5. Gap Analysis

For each finding:

| Field | Description |
|---|---|
| ID | Sequential (S-001, S-002, ...) |
| What | Description of the gap |
| Risk | High / Medium / Low |
| Category | Info Leakage / Auth Bypass / Session Security / Token Security / Config |
| Recommendation | What to fix and when |

## Implementation Sub-tasks

- [ ] 1. Read every route module, catalog endpoints and their auth dependencies
- [ ] 2. Read auth middleware, session, admin auth, and RBAC code paths
- [ ] 3. Build the complete endpoint inventory table
- [ ] 4. Build the Mermaid auth decision DAG
- [ ] 5. Audit information leakage (docs, errors, headers, cookies)
- [ ] 6. Audit auth boundaries (each endpoint with various credential states)
- [ ] 7. Write gap analysis with risk ratings
- [ ] 8. Review findings with user

## Acceptance Criteria

- [ ] Every HTTP endpoint from Phases 1–7 is in the inventory
- [ ] Mermaid DAG renders correctly and covers all auth paths
- [ ] Information leakage section addresses OpenAPI docs, error responses, headers, cookies
- [ ] Gap analysis has risk-rated findings with actionable recommendations
- [ ] No code changes — audit and documentation only
