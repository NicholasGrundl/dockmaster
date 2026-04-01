---
state: Finalized
changelog:
  "2026-03-09": "Created from gap analysis of legacy vs phase3-token-exchange-v2.md"
---

# Phase 3: Token Exchange — Implementation Guide

> Concrete coding checklist and gap-analysis notes for implementing Phase 3.
> Reference alongside: `phase3-token-exchange-v2.md` (design spec).

**Status**: ✅ COMPLETE
**Phase**: 3
**Last updated**: 2026-03-09

---

## Decisions Locked In

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | `POST /auth/exchange` (not GET) | Better REST design for an action endpoint; token still in Authorization header |
| D2 | Tokeninfo URL: `https://oauth2.googleapis.com/tokeninfo` | Updated endpoint (legacy used v1 URL); v2 spec already reflected this |
| D3 | Dual-mode: try JWT verification first, fall back to tokeninfo | Matches legacy behavior exactly |
| D4 | `can_issue` checks are enforced (return 403 on failure) | Fixes legacy bug where flag was set but never checked |

---

## Gaps vs Legacy (resolved)

### G1 — Exchange endpoint method changed GET → POST
**Legacy**: `GET /exchange`
**New**: `POST /auth/exchange`
Token is still in `Authorization: Bearer` header in both. POST is cleaner for an action endpoint. No issue.

### G2 — URL prefix added
**Legacy**: `/exchange`, `/refresh`, `/claims`, `/key/<kid>`, `/has`
**New**: `/auth/exchange`, `/auth/claims`, `/auth/key/{kid}`, `/auth/has`, `/auth/refresh`
All endpoints now have `/auth/` prefix. Consistent. No issue.

### G3 — Inconsistent error formats in legacy (fixed in new spec)
**Legacy**: JWT path failures returned `StatusResponse` (403), access token failures returned `{"error": "..."}` (401).
**New spec**: Use consistent format. Recommendation: `{"detail": "..."}` matching FastAPI's default `HTTPException` format, or a custom `{"error": "...", "message": "..."}` schema. Pick one and apply everywhere.

**Decision**: Use FastAPI's native `HTTPException(status_code=N, detail="...")` — produces `{"detail": "..."}`. This is already what FastAPI consumers expect.

### G4 — Legacy ISSUER ServiceUser was created per-request (fixed)
**Legacy**: `ServiceUser(issuer)` read the key file on every token issuance.
**New**: `ServiceUser` is a lifespan-scoped singleton from Phase 2. The exchange endpoint uses it via dependency injection.

---

## Implementation Checklist

### `src/dockmaster/auth/token_validator.py` — Access token validator

- [ ] `validate_access_token(token: str, authorized_audiences: list[str]) -> dict`
  - [ ] `GET https://oauth2.googleapis.com/tokeninfo?access_token={token}` via `httpx.AsyncClient`
  - [ ] On non-200: raise `ValueError("Invalid access token")`
  - [ ] On 200: parse JSON response
  - [ ] Check `response["audience"]` is in `authorized_audiences` → raise `ValueError("Audience not allowed")` if not
  - [ ] Return tokeninfo dict (contains `email`, `audience`, `scope`, etc.)
  - [ ] Note: tokeninfo responses do NOT have profile claims (name, picture, etc.)

### `src/dockmaster/routes/exchange.py` — /auth/exchange endpoint

- [ ] `POST /auth/exchange` — no authentication dependency (does its own validation)
- [ ] Extract Bearer token via `HTTPBearer` (or manual header parse)
- [ ] **Step 1: Try JWT verification** (`ServiceRealm.verify(token)`)
  - [ ] On success (claims not None):
    - [ ] Check `claims["iss"]` in `settings.AUTHORIZED_ISSUERS` → 403 if not
    - [ ] Check `claims["aud"]` in `settings.AUTHORIZED_AUDIENCE` → 403 if not
    - [ ] Capture `aud = claims.get("aud")` for service audience fallback
    - [ ] Extract `email = claims.get("email")`
  - [ ] On `ValueError`: fall through to access token path (log at DEBUG level)
- [ ] **Step 2: If JWT failed, try access token** (`validate_access_token()`)
  - [ ] On failure: raise `HTTPException(401, detail="Not authenticated")`
  - [ ] On success: extract `email = claims.get("email")`; `aud` stays None
- [ ] **Step 3: Resolve service audience**
  - [ ] `service = request.query_params.get("service") or aud`
  - [ ] If None: raise `HTTPException(400, detail="The service argument is required for access tokens")`
- [ ] **Step 4: Validate email**
  - [ ] If email is None: raise `HTTPException(400, detail="The email claim is missing")`
  - [ ] Extract domain: `domain = email.partition("@")[2]`
  - [ ] Check domain in `settings.AUTHORIZED_DOMAINS` → 403 if not
- [ ] **Step 5: `can_issue` checks** — all enforced (raises 403 on failure)
- [ ] **Step 6: Copy profile claims**
  - [ ] Copy `name, picture, given_name, family_name, locale` from `claims` if present
  - [ ] Note: access token path has no profile claims (tokeninfo doesn't return them)
- [ ] **Step 7: Parse expiry**
  - [ ] `expiry = int(request.query_params.get("expiry", 3600))`
- [ ] **Step 8: Sign dockmaster JWT**
  - [ ] `token = service_user.get_token(subject=email, service_name=service, expiry=expiry, payload=profile_claims)`
- [ ] **Response 200**:
  ```json
  {"token": "...", "subject": "...", "service": "...", "expiry": 3600}
  ```

### Response model (`src/dockmaster/routes/exchange.py` or `schemas.py`)

```python
class ExchangeResponse(BaseModel):
    token: str
    subject: str
    service: str
    expiry: int
```

### Settings additions for Phase 3 (`src/dockmaster/config.py`)

- [ ] `AUTHORIZED_ISSUERS: list[str] = []` — comma-separated trusted JWT issuers (e.g., `https://accounts.google.com`)
- [ ] `AUTHORIZED_DOMAINS: list[str] = []` — comma-separated allowed email domains (e.g., `shipyard.com`)
- [ ] `AUTHORIZED_AUDIENCE: list[str] = []` — already added in Phase 2

### Tests

- [ ] `tests/test_exchange.py`:
  - [ ] Valid Google JWT → 200 with dockmaster JWT
  - [ ] Valid access token (mocked tokeninfo) → 200 with dockmaster JWT
  - [ ] Missing Bearer → 401
  - [ ] Invalid token (both paths fail) → 401
  - [ ] Issuer not allowed → 403
  - [ ] Audience not allowed → 403
  - [ ] Domain not allowed → 403
  - [ ] Access token without `?service=` → 400
  - [ ] `?expiry=7200` controls dockmaster JWT lifetime
  - [ ] Profile claims forwarded from JWT; absent from access token path
- [ ] `tests/test_token_validator.py`:
  - [ ] Valid tokeninfo response → returns claims dict
  - [ ] Non-200 response → raises ValueError
  - [ ] Audience not in allowed list → raises ValueError
  - [ ] Mocked httpx (no real Google calls)
- [ ] `tests/fixtures/google_jwt.json` — mock Google JWT claims
- [ ] `tests/fixtures/tokeninfo.json` — mock tokeninfo response

### Acceptance gates

- [ ] `POST /auth/exchange` with valid Google JWT → dockmaster JWT returned
- [ ] `POST /auth/exchange` with access token → tokeninfo fallback works
- [ ] Invalid tokens → 401
- [ ] `can_issue` checks (issuer, audience, domain) → 403 on failure
- [ ] `?expiry=` and `?service=` query params work correctly
- [ ] Profile claims forwarded from JWT input
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] `just lint` and `just format` clean
