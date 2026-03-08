---
state: Finalized
changelog:
  "2026-03-08 15h": "Initial spec created from planning sessions"
---

# Phase 2: JWT Infrastructure

> JWT signing, verification, key caching, auth middleware, and introspection endpoints.

**Status**: Planned
**Priority**: P0
**Phase**: 2
**Last updated**: 2026-03-08

---

## Problem

Dockmaster needs to issue and verify JWTs for service-to-service authentication. Services authenticate by presenting a JWT signed with their GCP service account private key. Dockmaster must verify these tokens using cached public keys and provide middleware for protecting endpoints.

## Solution

### Overview

Two core classes mirror the legacy architecture:
- **ServiceUser** — signs JWTs using a GCP SA private key (the "client" side)
- **ServiceRealm** — verifies JWTs using cached public keys (the "server" side)

Plus auth middleware for FastAPI and two introspection endpoints.

### Implementation Details

#### ServiceUser (jwt_signer.py)

Signs JWTs with a GCP service account's RSA private key.

- Reads SA JSON key file, extracts `private_key`, `private_key_id`, `client_email`
- Signs JWTs with PyJWT using RS256: `iss`, `sub`, `aud`, `iat`, `exp`, `kid` header
- Configurable token lifetime (default 1 hour)

#### ServiceRealm (jwt_verifier.py)

Verifies incoming JWTs against cached public keys.

- Decodes JWT header to extract `kid`
- Looks up public key in `KeyCache`
- Verifies signature, expiry, audience, issuer
- Returns decoded claims on success

#### KeyCache (key_cache.py)

Base class with TTL-based key expiry and two implementations:

- **`KeyCache`** — abstract base with TTL management, `get_key(kid)` interface
- **`ServiceAccountKeyCache`** — fetches public keys from:
  - IAM API: `projects/-/serviceAccounts/{email}/keys` for SA-issued tokens
  - Google OIDC certs: `https://www.googleapis.com/oauth2/v3/certs` for Google-issued tokens
- Keys cached in-memory with configurable TTL
- Cache miss triggers fetch, cache hit returns immediately

#### Auth Middleware (middleware.py)

FastAPI dependency for Bearer token extraction + verification:

```python
async def get_current_user(
    authorization: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> dict:
    # Extract Bearer token
    # Verify with ServiceRealm
    # Return decoded claims
```

#### Endpoints

- `GET /auth/key/{kid}` — serve a specific public key for external verification
- `GET /auth/claims` — return decoded JWT claims from the Authorization header (debug/introspection, requires auth)

### File Structure

```
src/dockmaster/
    auth/
        __init__.py
        jwt_signer.py      # ServiceUser equivalent
        jwt_verifier.py     # ServiceRealm equivalent
        key_cache.py        # KeyCache, ServiceAccountKeyCache
        middleware.py        # get_current_user dependency
    routes/
        keys.py             # /auth/key/{kid}
        claims.py           # /auth/claims
tests/
    test_jwt_signer.py
    test_jwt_verifier.py
    test_key_cache.py
    test_middleware.py
    test_keys_endpoint.py
    test_claims_endpoint.py
    fixtures/
        fake_sa_key.json    # mock SA key for testing
```

## Dependencies

- **Requires**: Phase 1 (config, app skeleton, test infra)
- **Enables**: Phase 3 (token exchange needs JWT signing/verification)
- **New packages**: `PyJWT>=2.0`, `cryptography` (for RS256), `google-api-python-client` (IAM key listing)

## Source References

| Planning Doc | Relevant Sections |
|---|---|
| `_blueprint/features/planning/02-client-authentication.md` | ServiceUser design, SA key loading, JWT signing |
| `_blueprint/features/planning/03-token-verification.md` | ServiceRealm design, KeyCache, key fetching |
| `_blueprint/features/planning/05-flask-integration.md` | `jwt_authenticate` → auth middleware pattern |
| `_blueprint/features/planning/07-service-endpoints.md` | `/auth/key/{kid}` and `/auth/claims` endpoint specs |
| `_blueprint/features/planning/C-api-spec.md` | OpenAPI reference for endpoint schemas |

## Open Questions

None — all design decisions resolved in planning.

## Acceptance Criteria

- [ ] `ServiceUser` can sign a JWT with a test SA key and produce a valid RS256 token
- [ ] `ServiceRealm` can verify a JWT signed by `ServiceUser`
- [ ] `KeyCache` fetches and caches public keys with TTL expiry
- [ ] Auth middleware extracts Bearer token and returns decoded claims
- [ ] `GET /auth/key/{kid}` returns the correct public key
- [ ] `GET /auth/claims` returns decoded claims for a valid token, 401 for invalid
- [ ] All tests pass with mocked SA keys (no real GCP calls in tests)
- [ ] `uv run pytest tests/ -v` passes
- [ ] `just lint` and `just format` clean
