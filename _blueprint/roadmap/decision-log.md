# Architecture Decision Log

Record key decisions here so future-you remembers why.

*Last updated: 2026-03-08*

---

## 2026-03-08: Returning to this project to get auth behind my public domains

**Decision**: First get dockmaster running for my LLC domain to host projects behind SSO.
**Rationale**: Need to be able to access stuff from outside my home network.

---

## 2026-03-08: Phase ordering — Exchange before OAuth

**Decision**: Build JWT infrastructure (Phase 2) and token exchange (Phase 3) before OAuth login (Phase 4).
**Rationale**: Simpler, testable increments. JWT core → /exchange → OAuth login. Each phase builds on the previous without requiring browser flows or external OAuth setup until Phase 4.

## 2026-03-08: Legacy bugs — Fix during rebuild

**Decision**: Fix known legacy bugs during the clean-room rebuild rather than porting them.
**Rationale**: Clean-room implementation. Document what changed vs legacy in each phase spec.

## 2026-03-08: RBAC management — CLI + API + simple UI

**Decision**: Provide RBAC management through CRUD REST endpoints, a Typer CLI, and a minimal Jinja2+HTMX admin dashboard at `/admin/*`.
**Rationale**: API-first for automation, CLI for operators, UI for visual management. All three share the same backend logic.

## 2026-03-08: Async + Secret Manager — run_in_executor + TTL cache

**Decision**: Wrap synchronous Secret Manager calls with `run_in_executor`. Use TTL-based in-memory cache to minimize blocking calls.
**Rationale**: Secret Manager Python client is sync-only. TTL cache (RBAC_CACHE_TTL) makes the sync overhead acceptable. Document `AsyncClient` as a future optimization path.

## 2026-03-08: RBAC caching — TTL-based in-memory

**Decision**: Use TTL-based in-memory cache for RBAC data. Config var `RBAC_CACHE_TTL` with default 300s.
**Rationale**: Simple, no external dependencies. Cache miss triggers Secret Manager fetch. Acceptable staleness for permission data that changes infrequently.

## 2026-03-08: JWT library — PyJWT + google-auth

**Decision**: Use PyJWT for JWT encode/decode and google-auth for GCP SA credentials and IAM key fetching.
**Rationale**: PyJWT is the standard Python JWT library. google-auth handles GCP-specific credential management, SA key loading, and IAM API integration.

## 2026-03-08: OAuth library — Authlib

**Decision**: Use Authlib for OAuth2/OIDC client integration.
**Rationale**: Full OAuth2/OIDC client with FastAPI integration, handles PKCE + discovery. More complete than rolling our own.

## 2026-03-08: Doc structure — ROADMAP.md + per-phase feature specs

**Decision**: Master roadmap with phase summaries, detailed specs in `_blueprint/features/` (one per phase).
**Rationale**: Overview stays scannable; implementation details live in dedicated specs. New sessions can read ROADMAP.md → find current phase → read its spec.

## 2026-03-08: Sessions — In-memory first → Redis later

**Decision**: Implement a pluggable `SessionStore` protocol. Ship in-memory dict implementation first, Redis as follow-up.
**Rationale**: Unblocks development without infrastructure dependency. Protocol ensures drop-in replacement when Redis is needed.

## 2026-03-08: /exchange mode — Keep dual-mode

**Decision**: `/auth/exchange` accepts both Google JWTs and access tokens. Try JWT verification first, fall back to access token validation via tokeninfo API.
**Rationale**: Matches legacy behavior for backwards compatibility. Services with JWTs get fast local verification; browser contexts with access tokens still work.

## 2026-03-08: CLI framework — Typer

**Decision**: Use Typer for the CLI tool.
**Rationale**: Modern Click wrapper, type-hint driven, auto-completion support. Minimal boilerplate for CRUD-style commands.

## 2026-03-08: GCP guides — Separate per-phase

**Decision**: Create GCP setup guides as separate docs, one per phase that needs GCP configuration.
**Rationale**: Each guide is self-contained and only relevant when that phase is being deployed. Guides: `GUIDE-gcp-project-setup.md` (done), `GUIDE-oauth-consent-screen.md` (P4), `GUIDE-secret-manager.md` (P5).
