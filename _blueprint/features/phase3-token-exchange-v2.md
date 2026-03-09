---
state: Finalized
changelog:
  "2026-03-09 v2": "Audit polish — update tokeninfo URL, list profile claims, add ?expiry= param, document can_issue conditions, backlog dual-mode refinement"
  "2026-03-08 15h": "Initial spec created from planning sessions"
---

# Phase 3: Token Exchange

> Exchange a Google JWT or access token for a dockmaster-issued JWT.

**Status**: Planned
**Priority**: P0
**Phase**: 3
**Last updated**: 2026-03-09

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
Query params:
  ?expiry=<seconds>   (optional, default 3600)
  ?service=<audience>  (optional for JWTs, required for access tokens)

Response 200:
{
  "token": "<dockmaster-jwt>",
  "subject": "<email>",
  "service": "<audience>",
  "expiry": 3600,
  "claims": { ... }
}
```

Logic:
1. Extract Bearer token from Authorization header
2. Try JWT verification (ServiceRealm) — fast, local
3. If JWT verification fails (any reason), try access token validation (tokeninfo API) — **try-both strategy matching legacy behavior**
4. Run `can_issue` checks (all must pass):
   - **Issuer check**: `claims.iss` must be in `AUTHORIZED_ISSUERS` (e.g., `https://accounts.google.com`)
   - **Audience check**: `claims.aud` must be in `AUTHORIZED_AUDIENCE` (the allowed Google OAuth client IDs)
   - **Domain check**: email domain (after `@`) must be in `AUTHORIZED_DOMAINS` (e.g., `shipyard.com`)
5. If any `can_issue` check fails, return 403 (legacy bug fix: was set but never checked in refresh flow)
6. Resolve service audience: `?service=` query param, or fall back to original JWT audience. Required for access tokens (return 400 if missing).
7. Copy profile claims into new JWT payload (see Profile Claims below)
8. Parse `?expiry=` query param (default 3600 seconds)
9. Sign with ServiceUser and return

#### Profile Claims

The following claims are copied from the incoming token to the dockmaster JWT if present. All are optional — they are included if available, omitted if not.

| Claim | Description |
|-------|-------------|
| `name` | Full display name |
| `picture` | Profile picture URL |
| `given_name` | First name |
| `family_name` | Last name |
| `locale` | Language/locale preference |

**Note**: Access tokens validated via tokeninfo do NOT include profile claims. Only JWT/ID token inputs carry profile data forward.

#### Access Token Validator (token_validator.py)

Validates Google access tokens by calling the tokeninfo API:

```
GET https://oauth2.googleapis.com/tokeninfo?access_token=<token>
```

- Uses `httpx.AsyncClient` for the HTTP call
- Returns parsed tokeninfo response or raises on invalid token
- Extracts email, audience, scope from response
- Checks `audience` field against `AUTHORIZED_AUDIENCE`

#### Legacy Bug Fix

The legacy code set a `can_issue` flag based on domain/audience checks but never actually used it to gate token issuance. The new implementation checks `can_issue` before signing — if any of the three checks (issuer, audience, domain) fail, the exchange returns 403.

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
| `_blueprint/features/planning/08-token-flows.md` | Token exchange flow details, dual-mode logic, can_issue conditions |
| `_blueprint/features/planning/E-confidence-notes.md` | `can_issue` bug documentation |
| `_blueprint/features/planning/C-api-spec.md` | OpenAPI reference |

## Open Questions

None — all design decisions resolved in planning.

## Acceptance Criteria

- [ ] `POST /auth/exchange` with a valid Google JWT returns a dockmaster JWT
- [ ] `POST /auth/exchange` with a valid access token falls back to tokeninfo and returns a dockmaster JWT
- [ ] Invalid tokens return 401
- [ ] `can_issue` checks enforced: issuer, audience, and domain validation rejects unauthorized tokens with 403
- [ ] `?expiry=` query param controls dockmaster JWT lifetime (default 3600)
- [ ] `?service=` query param sets audience; required for access tokens, optional for JWTs
- [ ] Profile claims (name, picture, given_name, family_name, locale) are forwarded if present
- [ ] Tokeninfo endpoint uses current Google API (`oauth2.googleapis.com/tokeninfo`)
- [ ] All tests pass with mocked Google responses (no real API calls)
- [ ] `uv run pytest tests/ -v` passes
- [ ] `just lint` and `just format` clean
