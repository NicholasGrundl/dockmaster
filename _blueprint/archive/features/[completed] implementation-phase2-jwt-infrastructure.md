---
state: Finalized
changelog:
  "2026-03-09": "Created from gap analysis of legacy vs phase2-jwt-infrastructure-v2.md"
---

# Phase 2: JWT Infrastructure — Implementation Guide

> Concrete coding checklist and gap-analysis notes for implementing Phase 2.
> Reference alongside: `phase2-jwt-infrastructure-v2.md` (design spec).

**Status**: ✅ COMPLETE
**Phase**: 2
**Last updated**: 2026-03-09

---

## Decisions Locked In

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Use `PyJWT` + `cryptography` for signing/verification (not `google-auth`) | Better docs, cleaner error handling, identical RS256 wire format |
| D2 | `ServiceAccountKeyCache.update()` loads ALL SA keys in the GCP project | Required for service-to-service auth — any SA in the project can sign JWTs dockmaster verifies |
| D3 | Google OIDC certs always loaded (no config toggle) | Required for /auth/exchange to verify Google id_tokens; always-on is intentional, not a bug |
| D4 | `ServiceRealm` includes no-`kid` fallback (try all cached keys) | Some Google-issued tokens omit kid; fallback is low cost, high compatibility |
| D5 | `GET /auth/key/{kid}` is unauthenticated (public) | Consuming services need keys to *verify* tokens — requiring auth is circular |
| D6 | `ServiceUser` initialized once at app startup via lifespan | Avoid re-parsing the JSON key file on every request (legacy performance issue) |

---

## Gaps vs Legacy (resolved)

### G1 — `RemoteKeyCache` not implemented
**Legacy**: A `RemoteKeyCache` class let consuming services fetch public keys from the dockmaster HTTP endpoint instead of calling GCP IAM directly.
**Decision**: Out of scope for the service. Part of the future "Client Library / Python SDK" backlog item.

### G2 — `ServiceUser` per-request key file reads
**Legacy**: `ServiceUser(issuer)` read and parsed the JSON key file on every token issuance.
**Fix**: Parse the key file once during app lifespan startup. Store the loaded credentials on the app state. `ServiceUser` is a lifespan-scoped singleton, not per-request.

### G3 — `load_google_keys` parameter was silently ignored in legacy
**Legacy bug**: Constructor accepted `load_google_keys` param but always set `self._load_google_keys = True`.
**Fix**: Don't expose the parameter at all. Always load Google certs. Document this as intentional behavior.

### G4 — Legacy `ServiceRealm.verify()` had two key lookup modes
**Legacy**: `kid` present → look up specific key. `kid` absent → pass full `{kid: pem}` dict to decoder (tries all keys).
**Fix**: Replicate both modes. PyJWT's `jwt.decode()` with `algorithms=["RS256"]` accepts either a single key or a list. Implement the fallback explicitly.

### G5 — Legacy loaded Google OIDC certs from v1 endpoint
**Legacy**: `https://www.googleapis.com/oauth2/v1/certs`
**Note**: v3 endpoint returns JWK Set format (`https://www.googleapis.com/oauth2/v3/certs`). Use v1 for PEM certs (compatible with PyJWT's RSA key format), OR use v3 and convert JWK → RSA. Simpler: use v1 which returns `{kid: pem_cert}` directly.

---

## Implementation Checklist

### `src/dockmaster/auth/jwt_signer.py` — ServiceUser

- [ ] Constructor: accept `credentials: str | dict` (file path or parsed dict), extract `private_key`, `private_key_id`, `client_email`
- [ ] If string: open file and parse JSON on init (NOT per-call)
- [ ] `get_token(subject, service_name, expiry=3600, payload=None) -> str`
  - [ ] Build claims: `iss=client_email`, `sub=subject or client_email`, `email=subject or client_email`, `aud=service_name`, `iat=now`, `exp=now+expiry`, plus extra `payload` claims
  - [ ] Sign with PyJWT: `jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": private_key_id})`
  - [ ] Return str (not bytes — PyJWT returns str in v2+)
  - [ ] Use `payload=None` default with `payload = payload or {}` inside (fix legacy mutable-default bug)
- [ ] `get_authorization(...) -> str` — convenience wrapper returning `"Bearer {token}"`

### `src/dockmaster/auth/key_cache.py` — KeyCache + ServiceAccountKeyCache

- [ ] `KeyCache` base class:
  - [ ] `__init__(expiry=300)` — sets `_keys: dict[str, str] = {}`, `_updated_at: float = 0`
  - [ ] `get_key(kid: str) -> str | None` — check TTL, call `update()` if expired, return `_keys.get(kid)`
  - [ ] `get_all_keys() -> dict[str, str]` — return full `_keys` dict (for no-kid fallback)
  - [ ] `update()` — no-op in base, override in subclass
  - [ ] `_is_expired() -> bool` — `time.time() - _updated_at >= expiry`
- [ ] `ServiceAccountKeyCache(KeyCache)`:
  - [ ] Constructor: `credentials: str | dict`, `project: str | None = None`, `expiry: int = 300`
  - [ ] If credentials is str: load and parse JSON; extract project from `project_id` field
  - [ ] `update()`:
    - [ ] Fetch Google OIDC certs from `https://www.googleapis.com/oauth2/v1/certs` (returns `{kid: pem_cert}`)
    - [ ] Enumerate ALL SA keys in project via GCP IAM API (`google-api-python-client`):
      - [ ] `googleapiclient.discovery.build('iam', 'v1', credentials=sa_creds)`
      - [ ] List all SAs: `projects.serviceAccounts.list(name='projects/{project}', pageSize=50)` with pagination
      - [ ] For each SA, list user-managed keys: `serviceAccounts.keys.list(keyTypes='USER_MANAGED')`
      - [ ] For each key, fetch PEM: `keys.get(publicKeyType='TYPE_X509_PEM_FILE')`
      - [ ] kid = last segment of resource name
      - [ ] base64-decode `publicKeyData`
    - [ ] Atomic replace: `self._keys = new_keys`
  - [ ] Error handling: non-fatal failures for individual sources (log, continue); retry once on `RefreshError`

### `src/dockmaster/auth/jwt_verifier.py` — ServiceRealm

- [ ] Constructor: `key_cache: KeyCache`
- [ ] `verify(token: str) -> dict`:
  - [ ] Structural check: token must have 3 dot-separated parts (raise `ValueError` if not)
  - [ ] Decode header (base64, handle missing padding): extract `kid`
  - [ ] If `kid` present: `key = key_cache.get_key(kid)` → raise `ValueError(f"Unknown key {kid}")` if None
  - [ ] If `kid` absent: `keys = key_cache.get_all_keys()` → try each key
  - [ ] Verify with PyJWT: `jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})`
  - [ ] Return decoded claims dict
  - [ ] Raise `ValueError` with descriptive message on any failure

### `src/dockmaster/auth/middleware.py` — FastAPI dependency

- [ ] Use `HTTPBearer` security scheme:
  ```python
  security = HTTPBearer()
  async def get_current_user(
      credentials: HTTPAuthorizationCredentials = Depends(security),
      settings: Settings = Depends(get_settings),
  ) -> dict:
  ```
- [ ] Extract `credentials.credentials` (Bearer token string)
- [ ] Verify with `ServiceRealm.verify(token)`
- [ ] Return decoded claims on success
- [ ] Raise `HTTPException(status_code=401)` on missing or invalid token (NOT 422)
- [ ] `HTTPBearer` auto-returns 403 for missing header by default — override with `auto_error=False` + manual 401

### `src/dockmaster/routes/keys.py` — /auth/key/{kid}

- [ ] `GET /auth/key/{kid}` — **unauthenticated**
- [ ] Look up key in `ServiceAccountKeyCache` via `realm.key_cache.get_key(kid)`
  - [ ] May trigger `update()` on first call or after TTL expiry
- [ ] 200: return PEM string, `Content-Type: application/x-pem-file`
- [ ] 404: return `{"error": "Key {kid} was not found."}`

### `src/dockmaster/routes/claims.py` — /auth/claims

- [ ] `GET /auth/claims` — **requires authentication**
- [ ] Use `get_current_user` dependency
- [ ] Return decoded claims dict as JSON

### App lifespan wiring (`src/dockmaster/main.py`)

- [ ] In lifespan: load `Settings.ISSUER` key file once, create `ServiceUser` singleton
- [ ] Create `ServiceAccountKeyCache` singleton (TTL=300, loads all SA keys + Google certs on first request)
- [ ] Create `ServiceRealm` singleton wrapping the cache
- [ ] Attach all three to `app.state` for use in dependencies
- [ ] Register `/auth/key/{kid}` and `/auth/claims` routes

### `tests/fixtures/fake_sa_key.json`

- [ ] Generate a test RSA key pair (2048-bit)
- [ ] Create fake SA key JSON with standard fields (`client_email`, `private_key`, `private_key_id`, etc.)
- [ ] Store public key PEM for test assertions

### Settings additions (`src/dockmaster/config.py`)

- [ ] `AUTHORIZED_AUDIENCE: list[str] = []` — parsed from comma-separated env var (matches Phase 1 pattern)
- [ ] `ISSUER: str` — path to SA JSON key file (already planned but confirm added)
- [ ] `SECRETS_PROJECT: str` — GCP project for IAM key enumeration
- [ ] `KEY_CACHE_TTL: int = 300` — TTL for public key cache

### Tests

- [ ] `tests/test_jwt_signer.py` — sign a JWT with fake key, verify claims and header
- [ ] `tests/test_jwt_verifier.py` — sign with fake key, verify round-trip; test unknown kid → ValueError
- [ ] `tests/test_key_cache.py` — TTL expiry triggers update(); mocked GCP IAM; mocked Google certs endpoint
- [ ] `tests/test_middleware.py` — valid Bearer → 200; missing Bearer → 401; invalid token → 401
- [ ] `tests/test_keys_endpoint.py` — known kid → 200 PEM; unknown kid → 404; no auth required
- [ ] `tests/test_claims_endpoint.py` — valid auth → 200 claims; no auth → 401

### Acceptance gates

- [ ] `ServiceUser` signs JWT; `ServiceRealm` verifies it (round-trip with fake key)
- [ ] `ServiceRealm` returns 401 (not 422) for missing/invalid Authorization header
- [ ] `AUTHORIZED_AUDIENCE` setting is accessible via `get_settings()`
- [ ] `GET /auth/key/{kid}` works without auth
- [ ] `GET /auth/claims` requires auth
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] `just lint` and `just format` clean
