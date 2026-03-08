I want to plan and implement the FastAPI auth service for dockmaster in phased milestones. Each phase
  should end with working tests and a deployable checkpoint.

 ## Project Context

 Dockmaster is an auth microservice for fine-grained RBAC via Google services. The repo was just
 modernized to use uv + hatchling + justfile. The `src/dockmaster/` package is currently empty (just
 `__init__.py` with v0.1.0). All planning docs are in `_blueprint/features/planning/`.

 ## Key Decisions Already Made

 - **Framework**: FastAPI + Uvicorn
 - **OAuth library**: Authlib (supports Google now, extensible to other providers later)
 - **Session storage**: Pluggable interface (Protocol/ABC), start with in-memory dict, design for easy
  Redis swap later
 - **JWT signing**: python-jose with RS256 (GCP service account keys)
 - **Config**: pydantic-settings (loads from .env and env vars)
 - **Login UI**: Pure JSON API by default + a minimal built-in test UI (Jinja2 or FastHTML+HTMX —
 decide during planning) so we can test without a frontend
 - **No legacy code reuse**: Clean-room build from the planning docs only
 - **Test approach**: Red-green TDD per CLAUDE.md. Fixtures in conftest.py. `uv run pytest`.

 ## Phased Milestones

 The implementation should be broken into phases. Each phase ends with:
 - All tests passing
 - The service runnable via `just dev`
 - A natural commit point

 Suggested phasing (refine during planning):

 ### Phase 1: Configuration + Health + App Skeleton
 - pydantic-settings config models (Google OAuth2, Dockmaster service settings)
 - FastAPI app factory or module with lifespan
 - `/auth/health` endpoint
 - Logging setup
 - Tests for config loading and health endpoint

 ### Phase 2: Google OAuth2 Login Flow
 - Authlib-based Google OAuth2 client
 - Session interface (Protocol) + MemorySession implementation
 - Endpoints: `/auth/login/google`, `/auth/callback/google`, `/auth/logout`, `/auth/principal`
 - CSRF state validation
 - Tests with mocked Google responses
 - Minimal HTML test UI (login button + profile display)

 ### Phase 3: Token Exchange (stretch goal for later)
 - `/exchange` endpoint: accept Google JWT or access token, return Dockmaster JWT
 - JWT signing with ServiceUser (GCP SA key)
 - JWT verification with key cache
 - Issuer/audience/domain validation

 ## Files to Read FIRST (skip exploration)

 Read these files before planning. They contain the full spec:

 ### Planning Docs (primary source — read in order)
 1. `_blueprint/features/planning/01-overview.md` — Full architecture, all flows, component design,
 migration notes
 2. `_blueprint/features/planning/02-client-authentication.md` — ServiceUser, JWT signing,
 AuthorityClient
 3. `_blueprint/features/planning/06-service-configuration.md` — Config patterns, env vars, lazy init
 4. `_blueprint/features/planning/07-service-endpoints.md` — All endpoint specs with request/response
 schemas
 5. `_blueprint/features/planning/08-token-flows.md` — Exchange and refresh flow deep dives
 6. `_blueprint/features/planning/A-env-vars.md` — Complete env var reference
 7. `_blueprint/features/planning/00-reintroduction.md` — Executive summary, architecture diagrams,
 deployment (sections 5a-5c)

 ### Current Repo State
 8. `pyproject.toml` — Current dependencies and tool config
 9. `src/dockmaster/__init__.py` — Package root (currently just version)
 10. `CLAUDE.md` — Project conventions (testing, git, dependencies, etc.)
 11. `DEPLOY.md` — Deployment guide, Docker, env vars, compose

 ### Reference (only if needed for Authlib patterns)
 12. `_blueprint/features/planning/05-flask-integration.md` — Legacy Flask OAuth flow (for
 understanding the flow, NOT for porting code)

 ## Constraints

 - Follow CLAUDE.md conventions exactly (uv run, pytest fixtures, pydantic, conventional commits)
 - Use red-green TDD: write failing tests first, then implement
 - Use conftest.py for fixtures (mock Google responses, test config, etc.)
 - Do NOT look at `_blueprint/context/legacy-src/` — this is a clean-room build
 - Ask before adding any new dependency
 - Each phase should be independently deployable and testable
