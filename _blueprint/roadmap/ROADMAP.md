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
Phase 9b: Documentation Overhaul ..................... 🔄 IN PROGRESS (GUIDEs done, LEARNINGs planned)
Phase 11: Route Reorg + Refresh Token ................ 🔄 IN PROGRESS (Steps 0-F done, G-H remain)
Phase 11b: Node.js Browser Auth SDK .................. 📋 PLANNED
Phase 12: Python Consumer SDK ........................ 📋 PLANNED
Phase 9c: Production Deployment ...................... 📋 PLANNED
Phase 10: UI Tests ................................... 📋 PLANNED (low priority)
```

**Test count**: 474 tests (as of Phase 11, 2026-03-21)

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

See [`phase-history.md`](./phase-history.md) for full narratives, decisions, and detours.

---

## Active Phases

### Phase 11: Route Reorg + Refresh Token — IN PROGRESS

> Route reorganization into clean namespaces (session/service/cli/login) and refresh token
> support for cross-domain browser users. SDK split to Phase 12.

**Spec**: [`features/implementation-phase11-route-reorg.md`](../features/implementation-phase11-route-reorg.md)
**Progress**: [`implementation-progress.md`](./implementation-progress.md)

Steps 0–F complete. Remaining: Step G (cleanup) and Step H (logout content negotiation).

---

### Phase 9b: Documentation Overhaul — IN PROGRESS

> Comprehensive documentation rewrite — GUIDEs and LEARNINGs.

GUIDEs 01–03 complete. LEARNINGs 01–04 planned but not yet written.
See [`implementation-progress.md`](./implementation-progress.md) for details.

---

## Planned Phases

Plans for these phases live in [`feature-backlog.md`](./feature-backlog.md) until pulled
into `implementation-progress.md` for active work.

### Phase 11b: Node.js Browser Auth SDK

> TypeScript browser client (`@dockmaster/auth`) for Astro and React SPAs.

**Spec**: [`features/implementation-phase11b-js-sdk.md`](../features/implementation-phase11b-js-sdk.md)
**Dependencies**: Phase 11 complete

### Phase 12: Python Consumer SDK

> Lightweight Python SDK for backend services — JWT verification + permission checks, no GCP deps.

**Spec**: To be created during Phase 12 planning
**Dependencies**: Phase 11 complete

### Phase 9c: Production Deployment

> Docker, Caddy, GCP credential rotation, .env templates, monitoring.

**Spec**: To be created during Phase 9c planning
**Dependencies**: Phase 11 + 11b + 12 complete

### Phase 10: UI Tests (low priority)

> Comprehensive UI test coverage for all admin pages.

**Spec**: To be created during Phase 10 planning
**Dependencies**: All UI-affecting phases complete
