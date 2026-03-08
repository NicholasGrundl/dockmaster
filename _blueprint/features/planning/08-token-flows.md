# Service: Token Exchange and Refresh Flows (Deep Dive)

**Source file**: `service/dockmaster_service/service.py` (lines 190-358)

This document traces the exact code paths, data transformations, and edge cases for the two token issuance flows. It complements `07-service-endpoints.md` with implementation-level detail needed for a faithful recreation.

---

## Table of Contents

1. [Exchange Flow](#1-exchange-flow)
2. [Refresh Flow](#2-refresh-flow)
3. [Shared Patterns](#3-shared-patterns)
4. [Error Catalog](#4-error-catalog)
5. [Known Issues](#5-known-issues)

---

## 1. Exchange Flow

**Endpoint:** `GET /exchange`
**Source:** `service.py:190-263`

The exchange endpoint accepts two kinds of tokens and follows a try-JWT-then-fallback-to-access-token strategy.

### Step-by-Step Trace

#### Step 1: Bearer Token Extraction

```python
token = get_bearer_token()
if token is None:
    return jsonify({'error': 'Not authenticated'}), 401
```

`get_bearer_token()` (from `dockmaster.flask_integration`) parses the `Authorization` header. Returns `None` if:
- Header is missing
- Type is not `Bearer`
- Value is empty after stripping

#### Step 2: JWT Verification Attempt

```python
claims = None
aud = None
try:
    realm = get_realm()
    claims = realm.verify(token)
except ValueError as ex:
    logging.debug(f'Token did not parse as JWT: {ex}')
```

Key behaviors:
- `claims` starts as `None` -- used as a flag to determine which path was taken
- `aud` starts as `None` -- will hold the original JWT audience if applicable
- `get_realm()` returns a `ServiceRealm` backed by the global `ServiceAccountKeyCache`
- `realm.verify()` decodes the JWT header, looks up the `kid` in the key cache, and verifies the signature via `google.auth.jwt.decode()`
- On `ValueError` (malformed JWT, unknown kid, bad signature): exception is caught, `claims` stays `None`, flow continues to access token validation
- **Other exceptions are NOT caught** -- unexpected errors (network issues during key cache refresh, etc.) would propagate as 500s

#### Step 3a: JWT Path -- Issuer and Audience Validation

When `claims` is not `None` (JWT verification succeeded):

```python
iss = claims.get('iss')
if iss not in get_authorized_issuers():
    return jsonify(StatusResponse(status=StatusCode.Error,
        message=f'Issuer {iss} is not allowed')), 403

aud = claims.get('aud')
if aud not in get_authorized_audience():
    return jsonify(StatusResponse(status=StatusCode.Error,
        message=f'The audience is not allowed')), 403

email = claims.get('email')
```

- Issuer must be in `AUTHORIZED_ISSUERS` (e.g., `https://accounts.google.com`)
- Audience must be in `AUTHORIZED_AUDIENCE` (e.g., a Google client ID)
- Both checks return immediately on failure (403)
- `aud` is captured for use as default service audience later
- `email` is extracted from claims

**Typical JWT claims from Google Sign-In:**
```json
{
  "iss": "https://accounts.google.com",
  "aud": "109370504310-p2e82hp5cvubrub37jjrbpgabj0ivlnv.apps.googleusercontent.com",
  "sub": "1234567890",
  "email": "user@shipyard.com",
  "name": "Jane Doe",
  "picture": "https://...",
  "given_name": "Jane",
  "family_name": "Doe",
  "locale": "en"
}
```

#### Step 3b: Access Token Path -- Tokeninfo Validation

When `claims` is `None` (JWT verification failed):

```python
valid, message, claims = check_access_token(
    get_access_token_endpoint(), token, get_authorized_audience()
)
if not valid:
    logging.error(message)
    return jsonify({'error': 'Not authenticated'}), 401
email = claims.get('email')
```

- Calls `GET https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={token}`
- `check_access_token()` validates the `audience` field in the response against `AUTHORIZED_AUDIENCE`
- On failure: returns 401 (not 403, different from the JWT path)
- On success: `claims` is now the tokeninfo response dict
- `aud` remains `None` (was never set in this path)

**Typical tokeninfo response:**
```json
{
  "audience": "109370504310-p2e82hp5cvubrub37jjrbpgabj0ivlnv.apps.googleusercontent.com",
  "email": "user@shipyard.com",
  "email_verified": "true",
  "expires_in": 3547,
  "scope": "openid email profile",
  "access_type": "offline"
}
```

**Note:** Tokeninfo responses do NOT include profile claims (name, picture, etc.). The access token path produces JWTs without profile enrichment.

#### Step 4: Service Audience Resolution

```python
requested_aud = request.args.get('service', aud)
if requested_aud is None:
    return jsonify(StatusResponse(status=StatusCode.Error,
        message=f'The service argument is required for access tokens')), 400
```

- If `?service=X` is provided: uses that
- Else uses `aud` from the original JWT
- If both are `None` (access token path without `?service`): returns 400
- This means `?service` is optional for JWTs (defaults to original audience) but effectively required for access tokens

#### Step 5: Email and Domain Validation

```python
if email is None:
    return jsonify(StatusResponse(status=StatusCode.Error,
        message=f'The email claim is missing')), 400

_, _, domain = email.partition('@')
if domain not in get_authorized_domains():
    return jsonify(StatusResponse(status=StatusCode.Error,
        message=f'Domain {domain} is not allowed')), 403
```

- Email must be present in claims (either JWT or tokeninfo)
- Domain is extracted by splitting on `@` and taking the part after
- Domain must be in `AUTHORIZED_DOMAINS` (e.g., `shipyard.com`)

#### Step 6: Issuer Check

```python
issuer = get_issuer()
if issuer is None:
    return jsonify(StatusResponse(status=StatusCode.Error,
        message=f'The service is not configured with an issuer')), 503
```

The `ISSUER` env var must point to the service account key file. Without it, the service cannot sign tokens.

#### Step 7: Profile Claim Extraction and Token Signing

```python
expiry = int(request.args.get('expiry', 3600))

payload = {}
if claims is not None:
    for extra in ['name', 'picture', 'given_name', 'family_name', 'locale']:
        if extra in claims:
            payload[extra] = claims[extra]

user = ServiceUser(issuer)
token = user.get_token(subject=email, service_name=requested_aud,
                       expiry=expiry, payload=payload)
return jsonify(Token(token=token, subject=email,
                     service=requested_aud, expiry=expiry))
```

- Expiry parsed from query param, defaults to 3600
- Profile claims are copied from original claims into the new JWT payload
- **For access tokens:** claims come from tokeninfo which has no profile fields, so `payload` stays empty
- **For JWTs:** Google id_tokens include profile fields, so they carry forward
- `ServiceUser(issuer)` reads the key file on every request (no caching of the parsed credentials)
- `get_token()` signs the JWT with the service account's private key
- Response is serialized via `jsonify(Token(...))` -- Pydantic model is passed to jsonify

### Exchange Flow Data Transformation

**Input (Google JWT):**
```
iss=accounts.google.com, aud=google-client-id,
sub=1234, email=user@shipyard.com,
name=Jane Doe, picture=https://...
```

**Output (Dockmaster JWT):**
```
iss=dock-master@shipyard-auth-2022.iam..., aud=requested-service,
sub=user@shipyard.com, email=user@shipyard.com,
name=Jane Doe, picture=https://...,
iat=now, exp=now+3600
```

Key differences:
- `iss` changes from Google to dockmaster service account
- `aud` changes from Google client ID to the requested service
- `sub` changes from Google's numeric ID to the user's email
- Profile claims are preserved
- New `iat`/`exp` timestamps

---

## 2. Refresh Flow

**Endpoint:** `POST /refresh`
**Source:** `service.py:265-358`

The refresh flow is more complex: it resolves OAuth client credentials from Secret Manager, exchanges the refresh token with Google, validates the result, enriches with user profile, and signs a new JWT.

### Step-by-Step Trace

#### Step 1: Request Parsing

```python
sm_client = get_client()
req = unmarshall(RefreshTokenRequest, request.json)
```

- Creates a Secret Manager client (uses ISSUER credentials)
- Parses request body via watchtower's unmarshaller into a `RefreshTokenRequest` Pydantic model

#### Step 2: Client ID Resolution

```python
client_id = req.client_id if req.client_id is not None else get_default_client_id()
if client_id is None:
    return ..., 400

if client_id.find('.') < 0:
    client_id += get_client_id_suffix()
```

**Resolution chain:**
1. Use `client_id` from request body if provided
2. Else use `DEFAULT_CLIENT_ID` from config/env
3. If still None: return 400

**Suffix normalization:**
- If client_id has no `.` character, append `CLIENT_ID_SUFFIX` (default `.apps.googleusercontent.com`)
- Example: `"109370504310"` → `"109370504310.apps.googleusercontent.com"`
- If client_id already has a `.`, it's used as-is

#### Step 3: Client Secret Lookup

```python
client_id_name, _, _ = client_id.partition('.')
secret_id = 'client_id-' + client_id_name

secret_name = sm_client.secret_version_path(get_project(), secret_id, 'latest')
response = sm_client.access_secret_version(request={"name": secret_name})
client_secret = response.payload.data.decode('utf-8')
```

**Secret naming convention:**
- Extract the part before the first `.` from client_id
- Secret ID: `client_id-{first_part}`
- Example: client_id `109370504310.apps.googleusercontent.com` → secret `client_id-109370504310`

**Secret path:** `projects/{SECRETS_PROJECT}/secrets/client_id-{name}/versions/latest`

On any exception (NotFound, permission error, etc.): returns 400 "Invalid client_id value"

#### Step 4: Google Refresh Token Exchange

```python
endpoint = get_refresh_token_endpoint()
if endpoint is None:
    return ..., 500

response = requests.post(endpoint, params={
    'grant_type': 'refresh_token',
    'refresh_token': req.token,
    'client_id': client_id,
    'client_secret': client_secret
})
```

**Endpoint:** `https://www.googleapis.com/oauth2/v4/token` (default)

**HTTP details:**
- Uses `requests.post()` directly (no retry session)
- Parameters are sent via `params=` (query string), not `data=` (form body)
- No timeout specified (uses requests default -- potentially unlimited)

On non-200 response: returns 401 "Not authenticated"

**Typical Google refresh response:**
```json
{
  "access_token": "ya29.a0AfB_by...",
  "id_token": "eyJhbGciOiJSUzI1NiIs...",
  "expires_in": 3600,
  "token_type": "Bearer",
  "scope": "openid email profile"
}
```

Note: Refresh responses do NOT include a new `refresh_token` (the original remains valid).

#### Step 5: ID Token Verification

```python
refreshed = response.json()
access_token = refreshed.get('access_token')
id_token = refreshed.get('id_token')

realm = get_realm()
claims = realm.verify(id_token)
```

- Extracts `access_token` and `id_token` from the refresh response
- Verifies the `id_token` via `ServiceRealm` (signature verification against Google's public keys)
- If verification fails: exception propagates as unhandled (500)

#### Step 6: Authorization Checks (Non-Blocking)

```python
can_issue = True

iss = claims.get('iss')
if iss not in get_authorized_issuers():
    can_issue = False
    logging.error(f'Issuer {iss} is not allowed')

aud = claims.get('aud')
if aud not in get_authorized_audience():
    can_issue = False
    logging.error(f'The audience is not allowed')

email = claims.get('email')
_, _, domain = email.partition('@')
if domain not in get_authorized_domains():
    can_issue = False
    logging.error(f'Domain {domain} is not allowed')
```

**Critical issue:** `can_issue` is set to `False` when checks fail, but it is **never read after being set**. The code continues to sign and return a token regardless. All three checks (issuer, audience, domain) only produce error logs. See [Known Issues](#5-known-issues).

#### Step 7: User Profile Enrichment

```python
payload = {}
userinfo_request = requests.get(
    get_userinfo_endpoint(),
    headers={'Authorization': f'Bearer {access_token}'}
)
if userinfo_request.status_code == 200:
    userinfo = userinfo_request.json()
    for extra in ['name', 'picture', 'given_name', 'family_name', 'locale']:
        if extra in userinfo:
            payload[extra] = userinfo[extra]
else:
    logging.warning(f'Cannot retrieve user information for {email}, ...')
```

**Endpoint:** `https://www.googleapis.com/oauth2/v3/userinfo` (default)

- Uses the fresh `access_token` from the refresh response
- On success: copies profile claims into payload
- On failure: logs warning, continues with empty payload (non-fatal)
- Uses `requests.get()` directly (no retry, no timeout)

**Why userinfo instead of id_token claims?** The id_token from a refresh response may have fewer claims than the original. The userinfo endpoint always returns the full profile. This ensures the dockmaster JWT has up-to-date profile information.

**Typical userinfo response:**
```json
{
  "sub": "1234567890",
  "name": "Jane Doe",
  "given_name": "Jane",
  "family_name": "Doe",
  "picture": "https://lh3.googleusercontent.com/...",
  "email": "user@shipyard.com",
  "email_verified": true,
  "locale": "en"
}
```

#### Step 8: Token Signing and Response

```python
issuer = get_issuer()
if issuer is None:
    return ..., 503

requested_aud = req.service if req.service is not None else aud
user = ServiceUser(issuer)
token = user.get_token(subject=email, service_name=requested_aud,
                       expiry=req.expiry, payload=payload)

return jsonify(Token(
    token=token, subject=email, service=requested_aud,
    expiry=req.expiry, claims=payload,
    id_token=id_token, access_token=access_token
))
```

- Service audience: from request body, or falls back to the Google token's audience
- Signs JWT with the service account key
- Response includes the dockmaster JWT plus the Google tokens and profile claims

### Refresh Flow Data Transformation

**Input:** Google refresh token + client_id

**Intermediate:** Google access_token + id_token + userinfo

**Output (Dockmaster JWT):**
```
iss=dock-master@shipyard-auth-2022.iam..., aud=requested-service,
sub=user@shipyard.com, email=user@shipyard.com,
name=Jane Doe (from userinfo), picture=https://... (from userinfo),
iat=now, exp=now+expiry
```

**Response envelope also includes:** the Google id_token, access_token, and profile claims dict.

---

## 3. Shared Patterns

### Profile Claims Copying

Both flows copy the same five profile fields into the new JWT payload:

```python
for extra in ['name', 'picture', 'given_name', 'family_name', 'locale']:
    if extra in claims:  # or userinfo
        payload[extra] = claims[extra]
```

These are standard Google OIDC profile claims. They are included as custom claims in the dockmaster JWT so that downstream services can display user information without additional API calls.

### ServiceUser Instantiation

Both flows create a `ServiceUser` from the `ISSUER` file path on every request:

```python
user = ServiceUser(issuer)  # reads and parses the JSON key file
token = user.get_token(...)
```

The key file is read from disk and parsed as JSON on every token issuance. There is no caching of the parsed credentials between requests.

### Domain Extraction

Both flows extract the email domain the same way:

```python
_, _, domain = email.partition('@')
```

This splits on the first `@`. If the email has no `@`, `domain` will be an empty string, which won't match any authorized domain.

### Validation Differences Between Flows

| Check | Exchange (JWT path) | Exchange (access token path) | Refresh |
|---|---|---|---|
| Issuer | Validated, returns 403 | Not checked | Checked but NOT enforced |
| Audience | Validated, returns 403 | Validated by check_access_token | Checked but NOT enforced |
| Domain | Validated, returns 403 | Validated, returns 403 | Checked but NOT enforced |
| Email present | Validated, returns 400 | Validated, returns 400 | Not explicitly checked (would NPE if missing) |

---

## 4. Error Catalog

### Exchange Errors (in evaluation order)

| # | Condition | Status | Error Key | Message |
|---|---|---|---|---|
| 1 | No Bearer token | 401 | `error` | `Not authenticated` |
| 2 | JWT: issuer not allowed | 403 | `StatusResponse` | `Issuer {iss} is not allowed` |
| 3 | JWT: audience not allowed | 403 | `StatusResponse` | `The audience is not allowed` |
| 4 | Access token: validation failed | 401 | `error` | `Not authenticated` |
| 5 | No service resolvable | 400 | `StatusResponse` | `The service argument is required for access tokens` |
| 6 | No email claim | 400 | `StatusResponse` | `The email claim is missing` |
| 7 | Domain not allowed | 403 | `StatusResponse` | `Domain {domain} is not allowed` |
| 8 | ISSUER not configured | 503 | `StatusResponse` | `The service is not configured with an issuer` |

### Refresh Errors (in evaluation order)

| # | Condition | Status | Error Key | Message |
|---|---|---|---|---|
| 1 | No client_id resolvable | 400 | `StatusResponse` | `No client_id was specified and there is no default.` |
| 2 | Secret Manager lookup failed | 400 | `StatusResponse` | `Invalid client_id value` |
| 3 | Refresh endpoint not configured | 500 | `StatusResponse` | `Refresh endpoint is not configured` |
| 4 | Google refresh returned non-200 | 401 | `StatusResponse` | `Not authenticated` |
| 5 | ISSUER not configured | 503 | `StatusResponse` | `The service is not configured with an issuer` |

### Error Response Formats

Two different formats are used:

**Simple error:**
```json
{"error": "Not authenticated"}
```

**StatusResponse (from watchtower):**
```json
{"status": "Error", "message": "Issuer https://example.com is not allowed"}
```

A recreation should standardize on one format.

---

## 5. Known Issues

### 5.1 Refresh Flow: `can_issue` Flag Not Enforced

**Severity:** High -- security gap

The refresh flow sets `can_issue = False` when issuer, audience, or domain checks fail, but never checks the flag before signing the token. Tokens are issued regardless of validation results.

**Location:** `service.py:323-354`

**Fix for recreation:** Add a check after the validation block:
```python
if not can_issue:
    return jsonify(StatusResponse(status=StatusCode.Error,
        message='Token validation failed')), 403
```

### 5.2 Refresh Flow: Query Params Instead of Form Body

**Severity:** Low -- works but non-standard

The Google refresh endpoint call uses `params=` (query string) instead of `data=` (form body):
```python
response = requests.post(endpoint, params={...})
```

Google's token endpoint accepts both, but the OAuth2 spec (RFC 6749 Section 4.1.3) specifies `application/x-www-form-urlencoded` request body. The exchange flow in `flask_integration.py` correctly uses `data=`.

### 5.3 Refresh Flow: No Timeout on HTTP Calls

**Severity:** Medium -- operational risk

Both the Google refresh call and the userinfo call use `requests.post()`/`requests.get()` without a `timeout` parameter. If Google is slow to respond, the worker thread blocks indefinitely. The exchange flow in `flask_integration.py` uses `timeout=(5, 30)`.

### 5.4 Refresh Flow: No Retry Session

**Severity:** Low -- reduced resilience

Both HTTP calls in the refresh flow use plain `requests` instead of `requests_retry_session()`. Transient 500/502/504 errors from Google will fail the request without retry.

### 5.5 Exchange Flow: Inconsistent Error Formats

**Severity:** Low -- API consistency

JWT path failures return `StatusResponse` objects (403), while access token failures return `{"error": "..."}` dicts (401). A recreation should use a consistent format.

### 5.6 ServiceUser Reads Key File Per Request

**Severity:** Low -- performance

`ServiceUser(issuer)` reads and parses the JSON key file from disk on every token issuance. The credentials could be cached in memory since the key file doesn't change at runtime.
