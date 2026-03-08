# Service: API Endpoints

**Source file**: `service/dockmaster_service/service.py`

This document provides the complete specification for all six API endpoints exposed by the dockmaster service, including authentication requirements, request/response formats, and error handling.

---

## Table of Contents

1. [Authentication Middleware](#1-authentication-middleware)
2. [GET /exchange -- Token Exchange](#2-get-exchange----token-exchange)
3. [POST /refresh -- Refresh Token Exchange](#3-post-refresh----refresh-token-exchange)
4. [GET /has/\<subject\>/\<target\>/\<permission\> -- Path-based RBAC Check](#4-get-hassubjecttargetpermission----path-based-rbac-check)
5. [GET /has -- Query-based RBAC Check](#5-get-has----query-based-rbac-check)
6. [GET /key/\<kid\> -- Public Key Retrieval](#6-get-keykid----public-key-retrieval)
7. [GET /claims -- JWT Claims Inspection](#7-get-claims----jwt-claims-inspection)
8. [Endpoint Summary Table](#8-endpoint-summary-table)

---

## 1. Authentication Middleware

The `before_request` handler runs before every request and enforces JWT Bearer authentication with these exceptions:

| Path Prefix | Auth Behavior |
|---|---|
| `/exchange` | Skipped -- endpoint does its own token validation |
| `/refresh` | Skipped -- accepts refresh tokens, not JWTs |
| `/apidocs` | Skipped -- public API documentation |
| `/apispec` | Skipped -- public OpenAPI spec |
| All other paths | Requires valid JWT via `jwt_authenticate(get_realm())` |

When JWT auth is applied:
1. Extracts Bearer token from `Authorization` header
2. Verifies token via `ServiceRealm.verify()`
3. On success: stores decoded claims in `request.environ['REMOTE_USER']`
4. On failure: returns `{"error": "Not authenticated"}` with 401

---

## 2. `GET /exchange` -- Token Exchange

Exchanges a Google-issued JWT or access token for a dockmaster-signed JWT.

### Request

```
GET /exchange?service={service}&expiry={expiry}
Authorization: Bearer <google_jwt_or_access_token>
```

**Headers:**

| Header | Required | Value |
|---|---|---|
| `Authorization` | Yes | `Bearer <token>` -- a Google JWT (id_token) or Google access token |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `service` | string | Conditional | JWT's original `aud` | Target service audience for the issued token. Required when input is an access token (access tokens don't have `aud`) |
| `expiry` | int | No | `3600` | Token lifetime in seconds |

### Validation Flow

```
1. Extract Bearer token
   └── No token? → 401

2. Try JWT verification (ServiceRealm.verify)
   ├── Success (token is a JWT):
   │   ├── Check iss in AUTHORIZED_ISSUERS → 403 if not
   │   ├── Check aud in AUTHORIZED_AUDIENCE → 403 if not
   │   └── Extract email from claims
   └── Failure (ValueError):
       └── Fall through to access token validation

3. If JWT verification failed, try access token validation:
   ├── Call check_access_token(tokeninfo_endpoint, token, audiences)
   │   └── Invalid? → 401
   └── Extract email from tokeninfo response

4. Resolve service audience:
   ├── Use ?service query param if provided
   ├── Else use aud from original JWT
   └── If still None → 400 (required for access tokens)

5. Validate email:
   ├── Email missing? → 400
   └── Extract domain, check in AUTHORIZED_DOMAINS → 403 if not

6. Check ISSUER configured → 503 if not

7. Copy profile claims from original token:
   └── name, picture, given_name, family_name, locale

8. Sign new JWT via ServiceUser(issuer):
   └── get_token(subject=email, service_name=service, expiry=expiry, payload=profile_claims)
```

### Response

**200 OK:**
```json
{
  "token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Imtl...",
  "subject": "user@shipyard.com",
  "service": "my-service",
  "expiry": 3600
}
```

Content-Type: `application/json`

**Error Responses:**

| Status | Condition | Body |
|---|---|---|
| 400 | `service` not provided and input was access token | `{"status": "Error", "message": "The service argument is required for access tokens"}` |
| 400 | No `email` claim in token | `{"status": "Error", "message": "The email claim is missing"}` |
| 401 | No Bearer token | `{"error": "Not authenticated"}` |
| 401 | Access token validation failed | `{"error": "Not authenticated"}` |
| 403 | Issuer not in AUTHORIZED_ISSUERS | `{"status": "Error", "message": "Issuer {iss} is not allowed"}` |
| 403 | Audience not in AUTHORIZED_AUDIENCE | `{"status": "Error", "message": "The audience is not allowed"}` |
| 403 | Email domain not in AUTHORIZED_DOMAINS | `{"status": "Error", "message": "Domain {domain} is not allowed"}` |
| 503 | ISSUER not configured | `{"status": "Error", "message": "The service is not configured with an issuer"}` |

### Implementation Notes

- JWT verification is attempted first; access token validation is the fallback
- When input is a JWT, both `iss` and `aud` are validated. When input is an access token, only `aud` (from tokeninfo) is validated -- there is no issuer check for access tokens
- Profile claims are copied from the original token into the new JWT's payload
- The `ServiceUser` is created fresh on every call with the `ISSUER` file path (reads and parses the key file each time)

---

## 3. `POST /refresh` -- Refresh Token Exchange

Exchanges a Google refresh token for a dockmaster-signed JWT. Loads the OAuth client secret from GCP Secret Manager, refreshes the Google tokens, validates the resulting id_token, enriches with user profile data, and issues a dockmaster JWT.

### Request

```
POST /refresh
Content-Type: application/json

{
  "token": "1//0gF...",
  "client_id": "109370504310-p2e82hp5cvubrub37jjrbpgabj0ivlnv",
  "service": "my-service",
  "expiry": 7200
}
```

**Body (JSON):** `RefreshTokenRequest` model

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `token` | string | Yes | -- | Google refresh token |
| `client_id` | string | No | `DEFAULT_CLIENT_ID` from config | Google OAuth client ID |
| `service` | string | No | Audience from refreshed Google token | Target service audience |
| `expiry` | int | No | `3600` | Token lifetime in seconds |

### Validation Flow

```
1. Parse request body as RefreshTokenRequest (via watchtower unmarshaller)

2. Resolve client_id:
   ├── Use request.client_id if provided
   ├── Else use DEFAULT_CLIENT_ID from config
   └── If still None → 400

3. Normalize client_id:
   └── If no '.' in client_id, append CLIENT_ID_SUFFIX
       (e.g., "109370504310" → "109370504310.apps.googleusercontent.com")

4. Load client secret from Secret Manager:
   ├── Extract client_id_name = part before first '.'
   ├── Secret ID = "client_id-{client_id_name}"
   ├── Load secret: projects/{SECRETS_PROJECT}/secrets/{secret_id}/versions/latest
   └── On failure → 400 "Invalid client_id value"

5. Call Google refresh endpoint:
   ├── POST https://www.googleapis.com/oauth2/v4/token
   │   params: grant_type=refresh_token, refresh_token, client_id, client_secret
   └── On non-200 → 401 "Not authenticated"

6. Parse refresh response:
   ├── Extract access_token
   └── Extract id_token

7. Verify id_token via ServiceRealm:
   └── realm.verify(id_token)

8. Validate claims (sets can_issue flag, does NOT return early):
   ├── Check iss in AUTHORIZED_ISSUERS
   ├── Check aud in AUTHORIZED_AUDIENCE
   └── Check email domain in AUTHORIZED_DOMAINS
   Note: All three are checked and logged, but can_issue is set to False
   and the token is STILL ISSUED (see Implementation Notes below)

9. Fetch user profile:
   ├── GET {USERINFO_ENDPOINT} with Bearer access_token
   └── Copy: name, picture, given_name, family_name, locale
   Note: On failure, logs warning but continues without profile

10. Check ISSUER configured → 503 if not

11. Sign dockmaster JWT with profile payload

12. Return Token with claims, id_token, and access_token
```

### Response

**200 OK:**
```json
{
  "token": "eyJhbGciOiJSUzI1NiIs...",
  "subject": "user@shipyard.com",
  "service": "my-service",
  "expiry": 7200,
  "claims": {
    "name": "Jane Doe",
    "picture": "https://lh3.googleusercontent.com/...",
    "given_name": "Jane",
    "family_name": "Doe",
    "locale": "en"
  },
  "id_token": "eyJhbGciOiJSUzI1NiIs...",
  "access_token": "ya29.a0AfB_by..."
}
```

**Error Responses:**

| Status | Condition | Body |
|---|---|---|
| 400 | No client_id resolvable | `{"status": "Error", "message": "No client_id was specified and there is no default."}` |
| 400 | Secret Manager lookup failed | `{"status": "Error", "message": "Invalid client_id value"}` |
| 401 | Google refresh endpoint returned non-200 | `{"status": "Error", "message": "Not authenticated"}` |
| 500 | Refresh endpoint not configured | `{"status": "Error", "message": "Refresh endpoint is not configured"}` |
| 503 | ISSUER not configured | `{"status": "Error", "message": "The service is not configured with an issuer"}` |

### Implementation Notes

- **Security gap:** The `can_issue` flag is set to `False` when issuer/audience/domain checks fail, but the code does NOT check `can_issue` before issuing the token. The token is always issued if the refresh succeeds and the id_token verifies. The issuer/audience/domain checks only produce log errors. This means unauthorized domains could receive tokens.
- The Google refresh endpoint is called with `params=` (query parameters), not `data=` (form body). This differs from how `exchange_code()` sends form data in `flask_integration.py`.
- `requests.post()` is used directly (no retry session) for both the refresh and userinfo calls
- The `service` field defaults to the Google token's `aud` claim if not specified in the request
- Client ID suffixing: if `client_id` is `"109370504310"`, it becomes `"109370504310.apps.googleusercontent.com"`. The secret lookup uses `"client_id-109370504310"`.

---

## 4. `GET /has/<subject>/<target>/<permission>` -- Path-based RBAC Check

Checks whether a subject has a specific permission on a target service using path parameters.

### Request

```
GET /has/{subject}/{target}/{permission}
Authorization: Bearer <dockmaster_jwt>
```

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `subject` | string | Principal to check (e.g., service account email) |
| `target` | string | Service/resource identifier |
| `permission` | string (path) | Permission string. Uses Flask's `<path:permission>` converter, so it can contain `/` characters |

### Auth

Requires JWT Bearer authentication (enforced by `before_request`).

### Response

**204 No Content:**
Permission granted. Empty body.

**403 Forbidden:**
```json
{
  "status": "Error",
  "message": "user@example.com does not have read for my-service"
}
```

**500 Internal Server Error:**
```json
{
  "status": "Error",
  "message": "Exception during processing request."
}
```

### Implementation

```python
if get_authority().has_permission(subject, target, permission):
    return '', 204
else:
    return jsonify(StatusResponse(...)), 403
```

All exceptions are caught, logged, and returned as 500.

---

## 5. `GET /has` -- Query-based RBAC Check

Same permission check as the path-based variant, but with query parameters.

### Request

```
GET /has?subject={subject}&target={target}&permission={permission}
Authorization: Bearer <dockmaster_jwt>
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `subject` | string | Yes | Principal to check |
| `target` | string | Yes | Service/resource identifier |
| `permission` | string | Yes | Permission string |

### Auth

Requires JWT Bearer authentication (enforced by `before_request`).

### Response

Same as path-based endpoint, plus:

**400 Bad Request** (missing parameters):
```json
{"status": "Error", "message": "The status query parameter is missing"}
```
```json
{"status": "Error", "message": "The target query parameter is missing"}
```
```json
{"status": "Error", "message": "The permission query parameter is missing"}
```

**Note:** The error message for a missing `subject` says "The status query parameter is missing" -- this is a typo in the original code. It should say "The subject query parameter is missing".

---

## 6. `GET /key/<kid>` -- Public Key Retrieval

Returns the public key for a given key identifier, used by other services to verify dockmaster-signed JWTs.

### Request

```
GET /key/{kid}
Authorization: Bearer <dockmaster_jwt>
```

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `kid` | string | Key identifier (matches the `kid` field in JWT headers) |

### Auth

Requires JWT Bearer authentication (enforced by `before_request`).

### Response

**200 OK:**
```
-----BEGIN CERTIFICATE-----
MIIDJjCCAg6gAwIBAgIILeRDZfPPFwIwDQYJ...
-----END CERTIFICATE-----
```

Content-Type: `application/x-pem-file`

The response body is the raw PEM-formatted public key/certificate, not JSON.

**404 Not Found:**
```json
{"error": "Key {kid} was not found."}
```

**500 Internal Server Error:**
```json
{
  "status": "Error",
  "message": "Exception during processing request."
}
```

### Implementation

```python
realm = get_realm()
key = realm.key_cache[kid]
if key is None:
    return jsonify({'error': f'Key {kid} was not found.'}), 404
return key, 200, {'Content-Type': 'application/x-pem-file'}
```

Accesses the key cache directly via `realm.key_cache[kid]`, which may trigger a cache refresh if the cache has expired.

---

## 7. `GET /claims` -- JWT Claims Inspection

Returns the verified claims from the caller's JWT Bearer token. This is primarily a debugging/introspection endpoint.

### Request

```
GET /claims
Authorization: Bearer <dockmaster_jwt>
```

### Auth

Requires JWT Bearer authentication (enforced by `before_request`).

### Response

**200 OK:**
```json
{
  "iss": "dock-master@shipyard-auth-2022.iam.gserviceaccount.com",
  "sub": "user@shipyard.com",
  "email": "user@shipyard.com",
  "aud": "my-service",
  "iat": 1683619700,
  "exp": 1683623300,
  "name": "Jane Doe",
  "picture": "https://...",
  "given_name": "Jane",
  "family_name": "Doe",
  "locale": "en"
}
```

### Implementation

```python
return request.environ['REMOTE_USER']
```

Returns the claims dict directly. The claims were stored by `jwt_authenticate()` in the `before_request` handler. Flask auto-serializes the dict to JSON.

**Note:** No explicit Content-Type is set. Flask defaults to `text/html` when returning a raw dict in some versions, though modern Flask may auto-jsonify. The response may not have `application/json` Content-Type depending on Flask version.

---

## 8. Endpoint Summary Table

| Method | Path | Auth | Purpose | Response Model |
|---|---|---|---|---|
| GET | `/exchange` | Self-managed (JWT or access token) | Exchange Google token for dockmaster JWT | `Token` |
| POST | `/refresh` | None (public) | Exchange refresh token for dockmaster JWT | `Token` (with claims, id_token, access_token) |
| GET | `/has/<s>/<t>/<p>` | JWT Bearer | Path-based permission check | 204 or `StatusResponse` |
| GET | `/has` | JWT Bearer | Query-based permission check | 204 or `StatusResponse` |
| GET | `/key/<kid>` | JWT Bearer | Retrieve public key by ID | PEM text |
| GET | `/claims` | JWT Bearer | Inspect caller's JWT claims | dict |
| GET | `/apidocs` | None (public) | Swagger UI | HTML |
| GET | `/apispec` | None (public) | OpenAPI JSON spec | JSON |
