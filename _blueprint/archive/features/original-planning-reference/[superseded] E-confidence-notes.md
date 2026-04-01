# Appendix E: Confidence Notes & Open Questions

This appendix catalogs areas of lower confidence, unverified assumptions, and open questions identified during the documentation analysis. Each entry references the document where the topic is covered.

---

## 02 - Client Authentication (`02-client-authentication.md`)

### 1.1 `requests_retry_session()` Usage Inventory
**Confidence: Medium**
The usage list across the codebase is based on grep-level analysis. Service-level usages in `service.py` (refresh flow, userinfo calls) are noted generically. Some call sites in `service.py` use plain `requests` directly instead of `requests_retry_session()`, which may be intentional or an oversight.

### 1.2 Mutable Default `payload={}`
**Confidence: High (code is clear), Impact: Uncertain**
The mutable default argument is definitively present in the code. Whether it causes actual bugs in practice is uncertain -- standard claims are overwritten on each call, so it likely works correctly in normal usage. However, custom claims from a prior call could leak into subsequent calls if the caller doesn't pass an explicit payload dict.

### 1.3 Unreachable `from_service_account_file` Branch
**Confidence: High**
In `ServiceUser.get_token()`, the `else` branch (`RSASigner.from_service_account_file`) appears unreachable because the constructor always converts file paths to dicts. Not verified by running the code, but the logic is straightforward.

---

## 03 - Token Verification (`03-token-verification.md`)

### 2.1 `RemoteKeyCache` Expiry Behavior
**Confidence: High**
The `__getitem__` override bypasses the base class expiry mechanism entirely. Confirmed by reading `ServiceRealm.verify()` which calls `self._key_cache[kid]` (dispatches to the override) and `self._key_cache.keys` (property, no expiry check). The base class expiry is effectively unused for `RemoteKeyCache`.

### 2.2 `google.auth.jwt.decode()` Cert Formats
**Confidence: Medium**
Stated that `google.auth.jwt.decode()` accepts both a single PEM string and a `{kid: pem}` dict. This is based on general knowledge of the `google-auth` library, but not verified against the specific version pinned by this project (no version pin exists -- `google-auth` is unpinned).

### 2.3 `load_google_keys` Bug
**Confidence: High**
The constructor sets `self._load_google_keys = True` regardless of the parameter value (`load_google_keys` is accepted but ignored). Line 102: `self._load_google_keys = True` instead of `self._load_google_keys = load_google_keys`. Could be intentional (always load Google keys), but the parameter name implies it should be controllable.

---

## 04 - RBAC (`04-rbac.md`)

### 3.1 `Entity.name` Class Attribute vs Dataclass Field Shadowing
**Confidence: Medium-High**
The `Role` class has both a class attribute `name = 'name'` and a dataclass field `name: str`. `SecretsStorage.save()` uses `instance.__class__.name` (gets the class attribute `'name'`) while `instance.name` (on an instance) gets the dataclass field value. This works in Python's data model, but it's subtle -- not verified by running the code. If Python's dataclass machinery overwrites the class attribute, `save()` would break.

### 3.2 `from_data()` Without Decorators
**Confidence: High**
These are plain functions (no `@staticmethod`), called as `Role.from_data(data)`. This works because the first positional arg fills `data`, not `self`/`cls`. However, calling `instance.from_data(data)` would fail since `self` would consume the first argument. This is a known Python pattern quirk.

### 3.3 Replication Config
**Confidence: High (code), Low (migration relevance)**
The `_ensure_secret_exists` uses `{'replication': {'automatic': {}}}`. Didn't evaluate whether this matters for migration or if other replication modes should be considered.

---

## 05 - Flask Integration (`05-flask-integration.md`)

### 4.1 Timezone Handling in `has_principal()`
**Confidence: Medium**
The expiry is stored as naive `datetime.now()` but checked with `datetime.now().astimezone()` + `.replace(tzinfo=tz)`. The `.replace()` call doesn't convert -- it grafts a timezone onto a naive datetime. This should work when server timezone is consistent between write and read, but could produce incorrect results if the timezone changes (e.g., container restart in a different timezone configuration).

### 4.2 `redirect_uri()` Construction
**Confidence: Medium**
Multiple config values interact (`REDIRECT_URI`, `HOST_URL`, `AUTH_PREFIX`, `REDIRECT_PREFIX`). The default `AUTH_PREFIX` has a trailing slash (`'auth/'`) which differs from the Blueprint's `url_prefix='/auth'` (no trailing slash). Didn't enumerate all permutations of set vs defaulted values to verify correctness.

### 4.3 Redis Session Usage in Service
**Confidence: High**
The dockmaster service (`service.py`) does NOT set `app.session_interface = RedisSessionInterface(...)`. The console UI that would use sessions is disabled. The `RedisSessionInterface` is only available as a library export for consuming Flask applications. Verified by reading the full `service.py`.

---

## 06 - Service Configuration (`06-service-configuration.md`)

### 5.1 `get_project()` Inconsistency
**Confidence: High**
`get_project()` uses Flask config → env var lookup order, while all other accessors use env var → Flask config. Confirmed by reading the code. Whether intentional or accidental is unknown.

### 5.2 `watchtower` Unmarshaller Behavior
**Confidence: Low**
The `unmarshaller(RefreshTokenRequest)` factory returns a function called as `unmarshall(RefreshTokenRequest, request.json)`. The double reference to `RefreshTokenRequest` (at factory creation and invocation) is unusual. Haven't read watchtower source to understand why. Also unclear what happens on `None` or malformed JSON input.

### 5.3 `SERVICE_CONFIG` Import Mechanism
**Confidence: Medium**
`__import__(modulename)` for nested modules (e.g., `myapp.config.ProductionConfig`) returns the top-level module `myapp`, so `getattr(m, 'ProductionConfig')` would fail. This may limit `SERVICE_CONFIG` to single-level modules. Not tested.

---

## 07 - Service Endpoints (`07-service-endpoints.md`)

### 6.1 `/refresh` Security Gap (`can_issue`)
**Confidence: High**
The `can_issue` flag is set but never checked. Lines 323-336 set `can_issue = False` on validation failures; lines 348-355 sign and return the token without checking the flag. This is a confirmed code-level finding, not verified by runtime testing.

### 6.2 `/refresh` HTTP Method (`params=` vs `data=`)
**Confidence: Medium**
The Google refresh call uses `requests.post(endpoint, params=...)` which sends query parameters, not form body. Google's token endpoint likely accepts both, but the OAuth2 spec (RFC 6749) specifies form-encoded body. The exchange flow in `flask_integration.py` correctly uses `data=`. Not tested against Google's endpoint.

### 6.3 `/claims` Response Content-Type
**Confidence: Medium**
`return request.environ['REMOTE_USER']` returns a raw dict. Flask 2.2+ auto-jsonifies dicts, but older versions may return `text/html`. The project doesn't pin a Flask version, so behavior depends on what's installed.

---

## 08 - Token Flows (`08-token-flows.md`)

### 7.1 Google Refresh `params=` Behavior
**Confidence: Medium**
Stated that Google's token endpoint accepts both query params and form body. Believed to be true based on Google's general API flexibility, but not verified against current documentation.

### 7.2 `unmarshall` Error Handling
**Confidence: Low**
Didn't trace what happens when `request.json` is `None` (missing Content-Type or empty body) or malformed. The watchtower unmarshaller may raise an exception that propagates as an unhandled 500.

### 7.3 `realm.verify(id_token)` Failure in Refresh
**Confidence: High**
If `realm.verify()` raises `ValueError` in the refresh flow (line 322), the exception is unhandled (no try/except around it, unlike the exchange endpoint). This would produce a 500 error. Confirmed by code reading.

---

## 09 - RBAC Endpoints (`09-rbac-endpoints.md`)

### 8.1 All Subjects Resolved on Cache Miss
**Confidence: High**
When `Authority.get_permissions()` loads a target's `ServiceGrants`, it resolves ALL subjects' roles (not just the requested subject's). Confirmed by reading the for loop at `rbac.py:149`. A target with 50 subjects would load 50+ roles on first access even if only one subject is queried.

### 8.2 Performance Estimates
**Confidence: Low**
The 50-100ms per Secret Manager call estimate is based on general GCP knowledge, not measurements from this deployment. Actual latency depends on cluster region, Workload Identity overhead, and whether the Secret Manager client does gRPC connection pooling.

### 8.3 Secret Manager Client Pooling
**Confidence: Medium**
A new `SecretManagerServiceClient` is created per request via `get_authority()`. The gRPC-based client library may do internal connection pooling, so "new client per request" might not be as expensive as it appears. Not verified.

---

## 11 - CLI Tool (`11-cli-tool.md`)

### 9.1 Revoke Wildcard Bug (`found > 0`)
**Confidence: High**
The code at `__main__.py:124` checks `if found > 0` which fails for position 0 (the first grant). Should be `if found >= 0`. Not verified by running the CLI, but the logic error is clear from the code.

### 9.2 `role remove` ValueError
**Confidence: High**
`list.remove(permission)` at `__main__.py:61` raises `ValueError` if the permission isn't present. No guard check exists (unlike `add` which checks `if permission not in r.permissions`). Would crash the CLI with a traceback.

### 9.3 `PyYAML` Dependency
**Confidence: Medium**
The CLI imports `yaml` for output formatting, but `PyYAML` is not listed in `requirements.txt` or `setup.cfg` `install_requires`. It may be a transitive dependency (e.g., via `google-api-python-client`), or it may need to be explicitly added. Didn't verify the full dependency tree.

---

## 12 - Infrastructure (`12-infrastructure.md`)

### 10.1 TLS Termination
**Confidence: Low**
No TLS configuration in the ingress manifests. Assumed to be handled at the NGINX ingress controller level or via cert-manager, but no evidence in the codebase. A recreation needs to determine whether to configure TLS per-ingress or rely on cluster defaults.

### 10.2 Deployment Queue Consumer
**Confidence: N/A (out of scope)**
The Redis stream consumer that reads `deploy-staging`/`deploy-prod` and applies manifests is not in this codebase. The pipeline's output (manifest YAML + queue entry) is documented, but the deployment application mechanism is unknown.

### 10.3 Shiv Cache Behavior
**Confidence: Medium**
Shiv extracts dependencies to a cache directory at runtime. In Kubernetes pods (ephemeral), this cache is rebuilt on every pod startup. Didn't quantify the startup time impact or verify the exact cache location within the container.

---

## 13 - Migration Guide (`13-migration-guide.md`)

### 11.1 Async Secret Manager Client
**Confidence: Low**
Didn't address whether `google-cloud-secret-manager` supports async natively via `SecretManagerServiceAsyncClient`. The current sync client would block the event loop in async FastAPI handlers. Options include `run_in_executor()`, the async client, or keeping sync handlers for RBAC endpoints. This is a significant architectural decision left unresolved.

### 11.2 `httpx` Retry Pattern
**Confidence: Medium**
Proposed `tenacity` for retry logic. There may be better httpx-native solutions (`httpx-retries` package, custom transport). Didn't evaluate alternatives in depth.

### 11.3 Client Library Backward Compatibility
**Confidence: Medium**
Proposed making Flask optional via try/except imports in `__init__.py`. This means `from dockmaster import auth_endpoint` would silently not be available if Flask isn't installed (no ImportError at the import site). A cleaner approach might be `extras_require` (`pip install dockmaster[flask]` or `dockmaster[fastapi]`), but this wasn't fully spec'd.
