# Feature Backlog

Ideas and deferred features not yet scheduled for implementation. When an item is
committed, create a spec in [`_blueprint/features/`](../features/) and link it from
[`ROADMAP.md`](./ROADMAP.md).

*Last updated: 2026-03-08*

---

## Deferred Items

### Redis Session Store
- **Context**: Phase 4 ships with in-memory `SessionStore`. Redis implementation uses the same `SessionStore` protocol.
- **When**: After Phase 4 in-memory is working, or when multi-instance deployment is needed.
- **Effort**: Small — implement `RedisSessionStore` against existing protocol.
- **Dependency**: `redis[hiredis]`

### FastHTML + MonsterUI Admin Dashboard Evaluation
- **Context**: Phase 6 ships with Jinja2+HTMX admin UI. FastHTML+MonsterUI could provide a richer SPA-like experience with Python-only components.
- **When**: After Phase 6 ships and we have real usage feedback on the admin UI.
- **Decision needed**: Whether the Jinja2+HTMX approach is sufficient or warrants replacement.

### SecretManagerAsyncClient Evaluation
- **Context**: Currently using sync client with `run_in_executor` + TTL cache. Google may stabilize an async client.
- **When**: When google-cloud-secret-manager ships a stable async API, or if blocking calls become a performance bottleneck.
- **Decision needed**: Whether the async client is stable enough for production use.

### Client Library / Python SDK
- **Context**: Other services (behind dockmaster auth) need to call dockmaster APIs to verify tokens and check permissions.
- **When**: After Phase 5 when the full API surface is stable.
- **Scope**: Python package with `DockMasterClient` class — token exchange, permission checks, middleware integration.

### Deployment Guides
- **Context**: Need operational guides for various deployment targets.
- **When**: After Phase 5+ when the service is feature-complete enough to deploy.
- **Scope**: Docker standalone, GCP Cloud Run, Kubernetes (Helm chart), Caddy reverse proxy integration.
