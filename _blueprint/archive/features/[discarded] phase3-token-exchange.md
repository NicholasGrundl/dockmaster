---
state: Finalized
changelog:
  "2026-03-08 15h": "Initial spec created from planning sessions"
---

# Phase 3: Token Exchange

> Exchange a Google JWT or access token for a dockmaster-issued JWT.

**Status**: Planned
**Priority**: P0
**Phase**: 3
**Last updated**: 2026-03-08

---

## Problem

External services and browser contexts need to exchange their Google-issued credentials (either a JWT or an access token) for a dockmaster JWT. This dockmaster JWT is then used for subsequent authenticated requests within the ecosystem.

## Solution

### Overview

A single `/auth/exchange` endpoint that accepts Google credentials in dual-mode:
1. **JWT mode** (preferred): Verify the Google JWT locally using ServiceRealm from Phase 2
2. **Access token fallback**: Validate via Google's tokeninfo API

On success, issue a new dockmaster JWT with forwarded profile claims.

### Implementation Details

#### /auth/exchange Endpoint (exchange.py)

```
POST /auth/exchange
Authorization: Bearer <google-jwt-or-access-token>

Response 200:
{
  "token": "<dockmaster-jwt>",
  "claims": { ... }
}
```

Logic:
1. Extract Bearer token from Authorization header
2. Try JWT verification (ServiceRealm) — fast, local
3. If JWT verification fails, try access token validation (tokeninfo API)
4. Validate: issuer in `authorized_issuers`, email domain in `authorized_domains`, audience in `authorized_audience`
5. **Check `can_issue` flag** (legacy bug fix: was set but never checked)
6. Copy profile claims (name, picture, email, etc.) into new JWT
7. Sign with ServiceUser and return

#### Access Token Validator (token_validator.py)

Validates Google access tokens by calling the tokeninfo API:

```
GET https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=<token>
```

- Uses `httpx.AsyncClient` for the HTTP call
- Returns parsed tokeninfo response or raises on invalid token
- Extracts email, audience, scope from response

#### Legacy Bug Fix

The legacy code set a `can_issue` flag based on domain/audience checks but never actually used it to gate token issuance. The new implementation checks `can_issue` before signing.

### File Structure

```
src/dockmaster/
    auth/
        token_validator.py  # access token validation via tokeninfo
    routes/
        exchange.py         # /auth/exchange endpoint
tests/
    test_exchange.py
    test_token_validator.py
    fixtures/
        google_jwt.json     # mock Google JWT claims
        tokeninfo.json      # mock tokeninfo response
```

## Dependencies

- **Requires**: Phase 2 (ServiceUser for signing, ServiceRealm for verification)
- **Enables**: Phase 4 (OAuth login uses exchange flow internally)
- **New packages**: `httpx` (async HTTP client for Google API calls)

## Source References

| Planning Doc | Relevant Sections |
|---|---|
| `_blueprint/features/planning/07-service-endpoints.md` | Section 2: /auth/exchange endpoint spec |
| `_blueprint/features/planning/08-token-flows.md` | Token exchange flow details, dual-mode logic |
| `_blueprint/features/planning/E-confidence-notes.md` | `can_issue` bug documentation |
| `_blueprint/features/planning/C-api-spec.md` | OpenAPI reference |

## Open Questions

None — all design decisions resolved in planning.

## Acceptance Criteria

- [ ] `POST /auth/exchange` with a valid Google JWT returns a dockmaster JWT
- [ ] `POST /auth/exchange` with a valid access token falls back to tokeninfo and returns a dockmaster JWT
- [ ] Invalid tokens return 401
- [ ] Domain/audience/issuer validation rejects unauthorized tokens
- [ ] `can_issue` flag is enforced (bug fix verified)
- [ ] Profile claims (name, picture, email) are forwarded to the dockmaster JWT
- [ ] All tests pass with mocked Google responses (no real API calls)
- [ ] `uv run pytest tests/ -v` passes
- [ ] `just lint` and `just format` clean
