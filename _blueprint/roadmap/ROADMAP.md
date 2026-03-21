# Roadmap

Master plan and status for the dockmaster project. Scannable index — detailed history
lives in [`phase-history.md`](./phase-history.md).

**Goal**: Get dockmaster running for LLC domain to host projects behind SSO.

- Active specs: [`_blueprint/features/`](../features/)
- Archived specs: [`_blueprint/archive/features/`](../archive/features/)
- Upcoming plans + backlog ideas: [`feature-backlog.md`](./feature-backlog.md)
- Active decisions: [`decision-log.md`](./decision-log.md)
- Full phase narratives: [`phase-history.md`](./phase-history.md)
- Current phase details: [`implementation-progress.md`](./implementation-progress.md)

*Last updated: 2026-03-21*

---

## Overview

```
Phase 1: Config + Health + App Skeleton ............... ✅ COMPLETE
Phase 2: JWT Infrastructure .......................... ✅ COMPLETE
Phase 3: Token Exchange .............................. ✅ COMPLETE
Phase 4: OAuth Login + Session ....................... ✅ COMPLETE (4a, 4b, 4c)
Phase 5: RBAC ........................................ ✅ COMPLETE
Phase 6: RBAC Management (endpoints + admin UI) ...... ✅ COMPLETE
Phase 6b: Session Revocation ......................... ✅ COMPLETE
Phase 6c: CLI + OAuth Login Flow ..................... ✅ COMPLETE
Phase 7: Redirect URI + Ephemeral Keypair ............ ✅ COMPLETE
Phase 8a: Security Audit ............................. ✅ COMPLETE
Phase 8b: Code Quality Review ........................ ✅ COMPLETE
Phase 8c: Deployment Readiness ....................... ✅ COMPLETE
Phase 8d: Test Audit ................................. ✅ COMPLETE
Phase 8e: Auth Dependency Conventions ................ ✅ COMPLETE
Phase 9a: Deployment Readiness Cherry-Picks .......... ✅ COMPLETE
Phase 11: Route Reorg + Refresh Token ................ ✅ COMPLETE
Phase 11b: Node.js Browser Auth SDK .................. 📋 NEXT
Phase 12: Python Consumer SDK ........................ 📋 PLANNED
Phase 9c: Production Deployment ...................... 📋 PLANNED
Phase 9b: Documentation Overhaul ..................... ⏸️  DEFERRED (post-deploy)
Phase 10: Test Coverage + Refactor ................... ⏸️  BACKLOG
```

**Test count**: 476 tests (as of Phase 11 close, 2026-03-21)

---

## Completed Phases

| Phase | Summary | Spec |
|---|---|---|
| 1 | Config, health endpoint, app factory, test infra | [archive](../archive/features/[completed]%20plan-phase1-scaffold.md) |
| 2 | JWT signing/verification, key cache, auth middleware | [archive](../archive/features/[completed]%20phase2-jwt-infrastructure-v2.md) |
| 3 | Token exchange (Google JWT/access token → dockmaster JWT) | [archive](../archive/features/[completed]%20phase3-token-exchange-v2.md) |
| 4 | OAuth login, sessions, refresh, SecretsStorage, admin UI | [archive](../archive/features/[completed]%20phase4-oauth-login-v2.md) |
| 5 | RBAC data model, Authority engine, permission endpoints | [archive](../archive/features/[completed]%20phase5-rbac-v2.md) |
| 6 | Admin CRUD endpoints, RBAC management UI pages | [archive](../archive/features/[completed]%20phase6-rbac-management-v2.md) |
| 6b | Session revocation (admin endpoints + UI) | [archive](../archive/features/[completed]%20implementation-phase6b-session-revocation.md) |
| 6c | Typer CLI with browser-based OAuth login | [archive](../archive/features/[completed]%20phase6c-cli-v2.md) |
| 7 | Redirect URI system, ephemeral RS256 keypair, token issuance | [archive](../archive/features/[completed]%20implementation-phase7-ephemeral-keypair-redirect.md) |
| 8a | Security audit + fix all 14 findings | [archive](../archive/features/[completed]%20implementation-phase8a-security-audit.md) |
| 8b | Code quality review (20 findings, 12 actioned) | [archive](../archive/features/[completed]%20implementation-phase8b-code-quality.md) |
| 8c | Deployment readiness audit (7 findings) | [archive](../archive/features/[completed]%20implementation-phase8c-deployment-readiness.md) |
| 8d | Test audit | [archive](../archive/features/[completed]%20implementation-phase8d-test-audit.md) |
| 8e | Auth conventions, middleware consolidation, settings DI | [archive](../archive/features/[completed]%20implementation-phase8e-auth-conventions.md) |
| 9a | Deployment-critical cherry-picks from 8c findings | See [phase-history.md](./phase-history.md#phase-9a) |
| 11 | Route reorg (session/service/cli/login namespaces), refresh token, logout content negotiation | [spec](../features/implementation-phase11-route-reorg.md) |

See [`phase-history.md`](./phase-history.md) for full narratives, decisions, and detours.

---

## Execution Order

```
11 (finish) → 11b (JS SDK) → 12 (Python SDK) → 9c (deploy)
     ↑              ↑               ↑                ↑
  stable       Astro app can   backend can      ship the
  endpoints    do login +      verify JWTs +    whole stack
               protected pages check perms      together
```

**Rationale**: Build all integration pieces locally (JS SDK for Astro frontend, Python SDK
for backend API), test the full flow, then deploy everything together. After 12, focus shifts
to building the actual consumer apps — dockmaster work pauses until deploy time.

### Phase 11b: Node.js Browser Auth SDK — NEXT

> TypeScript browser client (`@dockmaster/auth`) for Astro and React SPAs.

**Spec**: [`features/implementation-phase11b-js-sdk.md`](../features/implementation-phase11b-js-sdk.md)
**Dependencies**: Phase 11 complete

### Phase 12: Python Consumer SDK

> Lightweight Python SDK for backend services — JWT verification + permission checks, no GCP deps.

**Spec**: To be created during Phase 12 planning
**Dependencies**: Phase 11 complete (11b not required)

### Phase 9c: Production Deployment

> Docker, Caddy, GCP credential rotation, .env templates, monitoring.

**Spec**: To be created during Phase 9c planning
**Dependencies**: Phase 11 + 11b + 12 complete

---

## Deferred

### Phase 9b: Documentation Overhaul — DEFERRED (post-deploy)

> LEARNINGs (conceptual architecture docs). GUIDEs 01–03 already complete.

Docs are most valuable when the system is stable and deployed. Resume after 9c.

### Phase 10: Test Coverage + Refactor — BACKLOG

> General test coverage improvements and code polish. Not a blocking phase.

Moved to [`feature-backlog.md`](./feature-backlog.md). Pull into active work when needed.
