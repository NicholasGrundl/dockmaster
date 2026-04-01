---
state: Finalized
changelog:
  "2026-03-16 16h": "Pass 2 complete — interactive decisions, action plan appended"
  "2026-03-16": "Created — Pass 1 complete: FastAPI patterns, naming, docstrings, API surface"
---

# Phase 8b: Code Quality Findings

> Catalog of naming conventions, FastAPI patterns, docstrings, and API surface consistency.
> Pass 1 + Pass 2 (interactive decisions) complete.

**Last updated**: 2026-03-16
**Scope**: All source modules in `src/dockmaster/`

---

## 1. FastAPI Pattern Catalog

### 1.1 Dependency Injection

**Pattern**: Route-level `Depends()` for auth, `Depends(get_settings)` for config. App-level singletons via `request.app.state`.

| Pattern | Where Used | Assessment |
|---|---|---|
| `Depends(get_current_user)` | claims, permissions (has, grants) | Good — standard DI |
| `Depends(require_admin_api)` | admin CRUD | Good — composes with `get_current_user` |
| `Depends(require_admin_ui)` | admin UI | Good — composes with `require_ui_session` |
| `Depends(require_admin_writes)` | write operations | Good — capability gate |
| `Depends(get_settings)` | most routes | Good — testable via `dependency_overrides` |
| Manual `getattr(request.app.state, ...)` | exchange, token, login, refresh, permissions, admin, admin_ui, ui | **Mixed** — necessary for optional singletons, but ~30 instances |
| Manual Bearer extraction | exchange, token | **Divergent** — bypasses `get_current_user` for valid reasons (dual-auth, fallback to access tokens) |

**Finding Q-001**: The `getattr(request.app.state, "X", None)` pattern appears ~30 times across route modules. Each usage does its own None check and returns 503. This could be a set of thin DI dependencies (e.g., `def get_token_issuer(request: Request)`) that centralize the None→503 check. However, this is a minor consistency improvement — the current approach works and is explicit.

### 1.2 Middleware vs Route-Level Auth

| Layer | What | Assessment |
|---|---|---|
| App middleware | `CORSMiddleware`, `SessionMiddleware` | Correct — cross-cutting, all requests |
| Route-level DI | All auth checks | Correct — different routes need different auth |

**Assessment**: The split is clean and correct. No misplaced concerns.

### 1.3 Error Handling

| Pattern | Where | Assessment |
|---|---|---|
| `raise HTTPException(status_code=N, detail="...")` | All routes | Consistent |
| `except NotFound: raise HTTPException(404, ...)` | admin routes | Good — translates GCP errors to HTTP |
| `except Exception: logger.exception(...); raise HTTPException(500, ...)` | permissions | Good — catch-all with logging |
| `except ValueError as exc: raise HTTPException(401, detail=str(exc))` | middleware | **Leaky** — see S-002 from 8a |
| Bare `except Exception` in refresh (`client_secret_lookup_failed`) | refresh.py:81 | Swallows exception type — could mask unexpected errors |

### 1.4 Response Models

| Endpoint Group | Response Type | Assessment |
|---|---|---|
| Health, Exchange, Refresh, Token | `response_model=PydanticModel` | Good — typed, documented |
| Permissions `/auth/grants` | `response_model=GrantsResponse` | Good |
| Permissions `/auth/has` | Raw `Response(status_code=204)` / `JSONResponse(403)` | **Divergent** — no response_model, manual JSONResponse |
| Admin CRUD (roles, grants, sessions) | `model_dump()` → raw dict | **Missing** — no response_model on admin endpoints |
| Login (principal, sessions) | Raw dict | **Missing** — no response_model |
| Claims | `-> dict` return type | **Missing** — no response_model |

**Finding Q-002**: Admin CRUD endpoints return raw dicts from `model_dump()` without `response_model`. This means the OpenAPI docs (when enabled) don't show response schemas for admin endpoints. The fix is to add `response_model` to the decorator.

**Finding Q-003**: `/auth/has` endpoints return manually-constructed `Response`/`JSONResponse` objects, bypassing FastAPI's response model system. This is intentional (204 has no body, 403 uses a custom shape), but the 403 response uses `{"status": "Error", "message": "..."}` while every other endpoint uses FastAPI's default `{"detail": "..."}`. Inconsistent error envelope.

### 1.5 Route Organization

| Prefix | Router Module | Endpoints | Assessment |
|---|---|---|---|
| `/auth` | health, keys, claims, exchange, login, refresh, permissions, token | 18 endpoints | **Overloaded** — OAuth flow, JWT ops, RBAC checks, sessions all under `/auth` |
| `/admin` | admin | 13 endpoints | Clean — CRUD only |
| `/ui` | ui (public + protected), admin_ui | 13 endpoints | Clean — pages only |
| `/` | root (in main.py) | 1 endpoint | Fine |

**Finding Q-004**: The `/auth` prefix hosts 18 endpoints spanning four different concerns: OAuth flow (login/callback/logout), JWT operations (claims/exchange/token/refresh), RBAC checks (has/grants), and user session management (principal/sessions). This makes the API hard to navigate. A possible reorganization: `/auth/oauth/*`, `/auth/jwt/*`, `/auth/rbac/*`. However, this is a breaking change and the current flat structure works fine for the current consumer set.

### 1.6 Lifespan Function

`main.py:lifespan()` is ~110 lines and creates ~10 singletons. Well-commented with section markers.

**Assessment**: Approaching the point where extraction would help readability (e.g., `_init_auth(settings, log)`, `_init_rbac(settings, log)`), but not yet a problem. The TODO on line 57 (`# TODO(phase5)`) is stale.

---

## 2. Naming & Vocab Audit

### 2.1 Auth Class Naming

| Class | Purpose | Naming Convention |
|---|---|---|
| `ServiceUser` | Signs JWTs with GCP SA private key (Type B) | Describes WHO |
| `JWTTokenIssuer` | Signs JWTs with ephemeral RSA key (Type C) | Describes WHAT |
| `ServiceRealm` | Verifies JWTs against cached public keys | Describes WHERE |
| `ServiceAccountKeyCache` | Caches GCP SA + Google OIDC public keys | Describes SOURCE |
| `EphemeralKeyCache` | Caches ephemeral public keys with file persistence | Describes SOURCE |
| `AuthCodeStore` | In-memory authorization code store | Describes WHAT |

**Finding Q-005**: `ServiceUser` and `JWTTokenIssuer` do the same thing (sign JWTs) but use different naming conventions. `ServiceUser` describes the actor ("who signs"), while `JWTTokenIssuer` describes the function ("what it does"). If both used functional naming, they'd be something like `ServiceAccountSigner` and `EphemeralSigner`. If both used actor naming, they'd be `ServiceUser` and `DockTokenUser`. The inconsistency is manageable but worth noting — already flagged as D29 vocab unification.

### 2.2 Method Naming

| Class | Method | What It Does |
|---|---|---|
| `ServiceUser` | `get_token()` | Signs a JWT |
| `ServiceUser` | `get_authorization()` | Returns `Bearer <token>` |
| `JWTTokenIssuer` | `sign()` | Signs a JWT |
| `ServiceRealm` | `verify()` | Verifies a JWT |
| `KeyCache` | `get_key()` | Returns a public key PEM |
| `KeyCache` | `update()` | Refreshes cached keys |

**Finding Q-006**: `get_token()` vs `sign()` — same operation, different verb. `get_token()` implies retrieval, `sign()` implies creation. `sign()` is more accurate. Already noted in D29.

### 2.3 The `subject` / `email` / `user` Problem

These three terms are used for the same concept (the authenticated identity) across the codebase:

| Term | Where Used | Meaning |
|---|---|---|
| `subject` | RBAC models, admin_ops params, permission endpoints, exchange endpoint, JWT `sub` claim | The identity being checked/authorized |
| `email` | Session data, login routes, admin session ops, `get_current_user` dict key, JWT `email` claim | The user's email address |
| `user` | Route dependency return values (`user: dict`), template context | The full user/session dict |

**Finding Q-007**: `subject` and `email` are used interchangeably when the value is an email address. In JWT claims, `sub` and `email` are set to the same value (the email). In RBAC, `subject` is the email. This works because dockmaster's identity model is email-based, but the terminology inconsistency could confuse new developers. Consider establishing: `subject` for RBAC/permissions context, `email` for session/identity context, `user` for the full claims/session dict.

### 2.4 The `service` / `target` / `audience` Problem

| Term | Where Used | Meaning |
|---|---|---|
| `service` | Exchange `?service=` param, Token `?service=` param, admin grants paths, CLI token command | The target service |
| `target` | RBAC authority methods, permission endpoint params, `GrantsResponse` field | The target service |
| `audience` | JWT `aud` claim, config `authorized_audience`, `ServiceUser.get_token(service_name=)` | The target service |
| `service_name` | `ServiceUser.get_token()` parameter | The target service |

**Finding Q-008**: Four terms for the same concept. `service` (user-facing), `target` (RBAC internals), `audience` (JWT standard), `service_name` (ServiceUser param). Consumer confusion is likely. The HTTP API uses `service` consistently (good), but the internal code uses all four.

### 2.5 Module Naming

| File | Contains | Assessment |
|---|---|---|
| `auth/middleware.py` | `get_current_user` dependency | **Misleading** — it's a DI dependency, not middleware. Name suggests app-level middleware. |
| `auth/jwt_signer.py` | `ServiceUser` class | **Misleading** — file says "signer", class says "user" |
| `auth/jwt_verifier.py` | `ServiceRealm`, `KeyCacheLike` | **OK** — verifier is accurate for ServiceRealm |
| `auth/token_validator.py` | `validate_access_token()` | **OK** — single-function module for access token validation |
| `auth/token_issuer.py` | `JWTTokenIssuer` | **OK** — matches class name |
| `routes/permissions.py` | Has permission + grants endpoints | **Slightly misleading** — "permissions" but also contains grants resolution |

**Finding Q-009**: `auth/middleware.py` contains a DI dependency function (`get_current_user`), not actual middleware. Renaming to `auth/dependencies.py` would be more accurate and conventional for FastAPI projects.

**Finding Q-010**: `auth/jwt_signer.py` contains `ServiceUser`, not a class called "JWTSigner". The file name and class name don't match.

---

## 3. Docstring Audit

### 3.1 Module-Level Docstrings

| Module | Has Docstring? | Quality |
|---|---|---|
| `config.py` | Yes | Good — clear purpose |
| `main.py` | Yes (minimal) | OK |
| `logging.py` | Yes | Good |
| `auth/middleware.py` | Yes | Good |
| `auth/admin.py` | Yes | Good |
| `auth/jwt_signer.py` | Yes | Good |
| `auth/jwt_verifier.py` | Yes | Good |
| `auth/key_cache.py` | Yes | Good — explains all 3 classes |
| `auth/token_issuer.py` | Yes | Good |
| `auth/token_validator.py` | Yes | Good |
| `auth/oauth.py` | Yes | Good |
| `auth/auth_code.py` | Yes | Good |
| `rbac/models.py` | Yes | Good |
| `rbac/storage.py` | Yes | Good |
| `rbac/authority.py` | Yes | Good |
| `rbac/admin_ops.py` | Yes | **Excellent** — explains service layer pattern and executor usage |
| `sessions/protocol.py` | Yes | Good |
| `sessions/memory.py` | Yes | Good |
| All route modules | Yes | Good |

**Assessment**: Module-level docstrings are comprehensive. No gaps.

### 3.2 Public Function/Class Docstrings

| Category | Coverage | Quality |
|---|---|---|
| Auth classes | 100% | Good — explain construction, usage, lifecycle |
| RBAC models | 0% (Pydantic — fields are self-documenting) | Acceptable |
| Storage methods | 100% | Good — explain SM conventions |
| Authority methods | 100% | Good — explain caching behavior |
| Admin ops | 100% | Good — short and accurate |
| Route handlers | ~90% | Most have docstrings; a few one-liners |
| Config | 50% | `Settings` class undocumented, `get_settings` has docstring |

**Assessment**: Docstring coverage is strong. The few gaps are in places where the code is self-documenting (Pydantic models, simple route handlers).

### 3.3 Stale or Inaccurate Docstrings

**Finding Q-011**: `main.py:57` has `# TODO(phase5)` — Phase 5 is complete. This TODO is stale.

**Finding Q-012**: `refresh.py` docstring (line 51-62) describes an "8-step flow" that matches the implementation. Accurate. However, `RefreshTokenRequest` docstring mentions "Legacy used field name `token`" — this is historical context that doesn't help future developers.

---

## 4. API Surface Consistency

### 4.1 Response Format

| Pattern | Endpoints | Format |
|---|---|---|
| Pydantic response model | health, exchange, refresh, token, grants | `{"field": "value", ...}` |
| Raw dict | claims, principal, sessions, admin CRUD | `{"field": "value", ...}` |
| No body (204) | permission check (granted), role/grants delete | Empty |
| Custom error JSON | permission check (denied) | `{"status": "Error", "message": "..."}` |
| FastAPI error JSON | Everything else | `{"detail": "..."}` |

**Finding Q-013**: Two different error response formats: FastAPI's default `{"detail": "..."}` (used everywhere) vs a custom `{"status": "Error", "message": "..."}` (used only by `/auth/has` 403 responses in `permissions.py:32-37`). Consumers must handle both shapes.

### 4.2 Parameter Conventions

| Convention | Where | Assessment |
|---|---|---|
| Path params | `/auth/key/{kid}`, `/auth/has/{s}/{t}/{p}`, admin CRUD | Appropriate for resource identification |
| Query params | `/auth/has?subject=&target=&permission=`, `/auth/token?service=`, `/auth/exchange?service=&expiry=` | Appropriate for filtering/options |
| Body (JSON) | `/auth/refresh`, `/auth/code/exchange`, admin POST/PUT | Appropriate for create/update |
| Form data | Admin UI POST endpoints | Appropriate for HTML forms |

**Finding Q-014**: `/auth/has` exists as BOTH path params (`/auth/has/{s}/{t}/{p}`) AND query params (`/auth/has?subject=&target=&permission=`). Two routes for the same operation. The query param version is more standard for GET requests. The path param version is convenient for curl but creates long URLs. Consider deprecating one.

### 4.3 Status Code Usage

| Code | Usage | Assessment |
|---|---|---|
| 200 | Data responses | Correct |
| 201 | `POST /admin/roles` | Correct |
| 204 | Permission granted, DELETE operations | Correct |
| 302 | OAuth redirects, logout | Correct |
| 303 | Admin UI form submissions (POST→redirect) | Correct (PRG pattern) |
| 307 | UI auth guard redirect | Correct (preserves method) |
| 400 | Missing params, invalid input | Correct |
| 401 | Missing/invalid auth | Correct |
| 403 | Unauthorized (domain, admin, permission) | Correct |
| 404 | Resource not found | Correct |
| 409 | Role conflict | Correct |
| 500 | Unhandled errors (with catch) | Correct |
| 503 | Missing capability (signer, oauth, storage) | Correct |

**Assessment**: Status codes are used correctly and consistently. Good.

### 4.4 Content Types

All API endpoints return JSON. All UI endpoints return HTML. No mixing.

### 4.5 Pagination

**Finding Q-015**: List endpoints (`/admin/roles`, `/admin/grants`, `/admin/sessions`) return full lists with no pagination. For the expected scale (tens of roles, tens of services, tens of sessions), this is fine. If scale increases, these will need pagination. Low priority.

---

## 5. Code Pattern Observations

### 5.1 Duplicated Constants

**Finding Q-016**: `PROFILE_CLAIM_KEYS` is defined in three places:
- `exchange.py:18` — `("name", "picture", "given_name", "family_name", "locale")`
- `refresh.py:18` — same tuple
- `login.py:21` — `("email", "name", "picture", "given_name", "family_name", "locale")` — **includes `email`**

The login version includes `email` because it's building session data, not profile claims. The other two exclude it because `email` is a core JWT claim, not a profile claim. This distinction is correct but the shared constant name suggests they should be the same.

### 5.2 Duplicated Session-Reading Logic

**Finding Q-017**: The pattern "read session cookie → unsign → look up session → extract email" appears in four places with slight variations:
- `token.py:_email_from_session()` — returns email or None
- `login.py:get_principal()` — returns session data or `{}`
- `login.py:get_sessions()` — returns sessions or `{}`
- `ui.py:_get_session_user()` — returns user dict or None

These could share a common `_get_session_data(request, settings)` helper, but the variations are small enough that extraction might over-abstract.

### 5.3 Deprecated API Usage

**Finding Q-018**: `asyncio.get_event_loop()` is used in `authority.py` (4 times) and `admin_ops.py` (7 times). This is deprecated since Python 3.10 in favor of `asyncio.get_running_loop()`. Since these are called from within async route handlers, `get_running_loop()` is correct and will always work.

### 5.4 Logger Inconsistency

**Finding Q-019**: `key_cache.py` uses stdlib `logging` (`_log = logging.getLogger(__name__)`) while every other module uses `structlog` (`logger = structlog.get_logger("dockmaster.X")`). This means key cache log messages bypass structlog's processors (timestamps, JSON formatting, etc.).

### 5.5 Dataclass vs Pydantic

**Finding Q-020**: `AuthCodeEntry` in `auth/auth_code.py` is a `@dataclass`. CLAUDE.md says "prefer pydantic to dataclasses for JSON-like objects." However, `AuthCodeEntry` is an internal data structure, not serialized to JSON — so dataclass is arguably appropriate here. Borderline finding.

---

## 6. Findings Summary

| ID | What | Impact | Category | Recommendation |
|---|---|---|---|---|
| Q-001 | `getattr(request.app.state, ...)` repeated ~30 times with individual None→503 checks | Low | Pattern | Could extract to DI dependencies, but current approach is explicit and works |
| Q-002 | Admin CRUD endpoints missing `response_model` | Medium | Pattern | Add response models for OpenAPI documentation |
| Q-003 | `/auth/has` 403 uses `{"status", "message"}` instead of `{"detail"}` | Medium | API Surface | Standardize on FastAPI's `{"detail": "..."}` format |
| Q-004 | `/auth` prefix hosts 18 endpoints across 4 concerns | Low | Pattern | Document the grouping; defer reorganization unless consumers request it |
| Q-005 | `ServiceUser` (actor naming) vs `JWTTokenIssuer` (functional naming) | Low | Naming | Unify naming convention during D29 vocab pass |
| Q-006 | `get_token()` vs `sign()` — same operation, different verb | Medium | Naming | Standardize on `sign()` — already noted as D29 |
| Q-007 | `subject` / `email` / `user` used interchangeably for identity | Low | Naming | Establish terminology guide: subject=RBAC, email=identity, user=dict |
| Q-008 | `service` / `target` / `audience` / `service_name` for same concept | Medium | Naming | Standardize internal code on `target` (RBAC) and `audience` (JWT); keep `service` for HTTP API |
| Q-009 | `auth/middleware.py` is a DI dependency, not middleware | Low | Naming | Rename to `auth/dependencies.py` |
| Q-010 | `auth/jwt_signer.py` contains `ServiceUser` — name mismatch | Low | Naming | Rename file or class during D29 pass |
| Q-011 | Stale `# TODO(phase5)` in `main.py:57` | Low | Docstring | Remove |
| Q-012 | Legacy comment in `RefreshTokenRequest` docstring | Low | Docstring | Remove "Legacy used field name" note |
| Q-013 | Two error response formats (`{"detail"}` vs `{"status", "message"}`) | Medium | API Surface | Standardize on `{"detail"}` |
| Q-014 | `/auth/has` exists as both path-param and query-param variants | Low | API Surface | Keep both for now; deprecate path-param version if API surface is formalized |
| Q-015 | List endpoints have no pagination | Low | API Surface | Acceptable at current scale; add when needed |
| Q-016 | `PROFILE_CLAIM_KEYS` defined in 3 places (one different) | Low | Pattern | Extract to shared constant in `config.py` or `auth/__init__.py` |
| Q-017 | Session-reading logic duplicated in 4 places | Low | Pattern | Could share a helper; variations are small enough to be tolerable |
| Q-018 | `asyncio.get_event_loop()` deprecated — 11 occurrences | Medium | Pattern | Replace with `asyncio.get_running_loop()` |
| Q-019 | `key_cache.py` uses stdlib `logging` instead of `structlog` | Medium | Pattern | Switch to `structlog` for consistent log formatting |
| Q-020 | `AuthCodeEntry` is a dataclass (CLAUDE.md prefers pydantic) | Low | Pattern | Borderline — internal-only, not serialized. Acceptable. |

### Impact Summary

| Impact | Count | IDs |
|---|---|---|
| **Medium** | 6 | Q-002, Q-003, Q-006, Q-008, Q-013, Q-018, Q-019 |
| **Low** | 14 | Q-001, Q-004, Q-005, Q-007, Q-009, Q-010, Q-011, Q-012, Q-014, Q-015, Q-016, Q-017, Q-020 |

### Quick Wins (< 5 min each, no API changes)
1. **Q-011** — Delete stale TODO comment
2. **Q-012** — Remove legacy docstring note
3. **Q-018** — `get_event_loop()` → `get_running_loop()` (11 replacements)
4. **Q-019** — `key_cache.py` switch to structlog

### Worth Planning (need discussion)
1. **Q-003 + Q-013** — Error format standardization
2. **Q-006 + Q-005 + Q-010** — D29 vocab unification (rename `get_token()` → `sign()`, align class/file names)
3. **Q-008** — `service`/`target`/`audience` terminology guide
4. **Q-002** — Add response models to admin endpoints

---

## 7. Pass 2 — Action Plan (Interactive Decisions)

All 20 findings reviewed with user. Decisions below.

### Do Now (implementation tasks)

| ID | Action | Scope | Files |
|---|---|---|---|
| Q-011 | Delete stale `# TODO(phase5)` comment | 1 line | `main.py:57` |
| Q-012 | Delete legacy docstring note | 1 line | `refresh.py:25` |
| Q-018 | Replace `get_event_loop()` → `get_running_loop()` | 11 replacements | `authority.py`, `admin_ops.py` |
| Q-019 | Switch `key_cache.py` to structlog + standardize ALL logger names to `__name__` | ~15 files | All modules with `structlog.get_logger("dockmaster.X")` |
| Q-003/Q-013 | Standardize permission denied response to `{"detail": "..."}` | 1 file | `permissions.py:32-37` |
| Q-005/Q-006/Q-010 | Rename `ServiceUser` → `ServiceAccountSigner`, `get_token()` → `sign()`, align param names, rename file `jwt_signer.py` → `sa_signer.py` | ~20 files | Source: `sa_signer.py`, `main.py`, `refresh.py`. Tests: `conftest.py`, `test_jwt_signer.py`, `test_jwt_verifier.py`, `test_realm_e2e.py`, `test_exchange.py`, `test_token_endpoint.py`, `test_claims_endpoint.py`, `test_refresh.py` |
| Q-005/S-010 | Migrate `refresh.py` from `signer.get_token()` (Type B) to `token_issuer.sign()` (Type C). Remove `app.state.signer` from lifespan. Keep `ServiceAccountSigner` for test utility use. | 3 files | `refresh.py`, `main.py`, `test_refresh.py` |
| Q-009 | Rename `auth/middleware.py` → `auth/dependencies.py` | 7 files | `auth/dependencies.py`, `auth/admin.py`, `routes/permissions.py`, `routes/claims.py`, `test_admin_auth.py`, `test_admin_endpoints.py` |
| Q-017 | Extract shared session-reading helper into `auth/dependencies.py` | 5 files | `auth/dependencies.py` (new function), `token.py`, `login.py`, `ui.py` |
| Q-020 | Convert `AuthCodeEntry` from dataclass to Pydantic BaseModel | 1 file | `auth/auth_code.py` |
| Q-002 | Add `response_model` to all endpoints that return untyped dicts | ~6 files | `routes/admin.py`, `routes/login.py`, `routes/claims.py`, `routes/permissions.py` — create response models where needed |
| Q-004 | Add OpenAPI tags to group `/auth` endpoints by concern | ~5 files | Route modules (add `tags=["oauth"]`, `tags=["jwt"]`, etc.) |

### Document Only (no code changes, add to CLAUDE.md or backlog)

| ID | Action | Where |
|---|---|---|
| Q-007 | Add terminology guide: subject=RBAC context, email=identity value, user=full claims dict | CLAUDE.md |
| Q-008 | Add terminology guide: API=service, RBAC=target, JWT=audience (aud claim) | CLAUDE.md |
| Q-008 | Note: eventual full rename to `target` everywhere is desired but deferred (SM secret naming complicates) | Backlog |
| Q-004 | Note: endpoint reorganization + modular activation as future backlog item | Backlog |
| Q-009 | Note: consider default-deny auth middleware (whitelist public paths) as future architecture decision | Backlog |
| Q-015 | Note: add pagination when list endpoints return 100+ items | Backlog |
| Q-016 | Note: PROFILE_CLAIM_KEYS duplication deferred — login version includes email, complicates extraction | Backlog |
| Q-002 | Note: consider centralizing response models to a schemas module if cross-route imports grow | Backlog |

### No Action

| ID | Decision | Reason |
|---|---|---|
| Q-001 | Keep inline `getattr(app.state)` pattern | Explicit, works, not worth DI indirection |
| Q-014 | Keep both `/auth/has` route variants | Both work, both tested, convenient for different use cases |
