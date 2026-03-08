# Appendix C: API Specification

This appendix provides a complete OpenAPI 3.0 specification for all dockmaster service endpoints, derived from the source code and inline docstrings.

---

## OpenAPI 3.0 Specification

```yaml
openapi: 3.0.3
info:
  title: Dockmaster Authentication Service
  version: 0.12.3
  description: OAuth2 token exchange, JWT verification, and RBAC permission checking service.

servers:
  - url: https://dockmaster.service.example.net
    description: Production
  - url: https://dockmaster.staging.example.net
    description: Staging

security:
  - BearerAuth: []

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: >
        JWT signed by a trusted issuer (listed in AUTHORIZED_ISSUERS).
        Not required for /exchange, /refresh, /apidocs, /apispec endpoints.

  schemas:
    Token:
      type: object
      properties:
        token:
          type: string
          description: Signed JWT token (base64url-encoded)
        subject:
          type: string
          description: Email address of the token subject
        service:
          type: string
          description: Audience (service) the token is issued for
        expiry:
          type: integer
          description: Token lifetime in seconds
        claims:
          type: object
          description: Profile claims included in the token (only in /refresh response)
        id_token:
          type: string
          description: Original Google ID token (only in /refresh response)
        access_token:
          type: string
          description: Google access token (only in /refresh response)
      required:
        - token
        - subject
        - service
        - expiry

    RefreshTokenRequest:
      type: object
      properties:
        token:
          type: string
          description: Google refresh token
        client_id:
          type: string
          description: Google OAuth2 client ID. If omitted, uses DEFAULT_CLIENT_ID. Short-form IDs (without dots) get CLIENT_ID_SUFFIX appended.
        service:
          type: string
          description: Audience for the issued JWT. If omitted, uses the audience from the refreshed token.
        expiry:
          type: integer
          description: Requested token lifetime in seconds
          default: 3600
      required:
        - token

    StatusResponse:
      type: object
      properties:
        status:
          type: string
          enum: [Ok, Error]
        message:
          type: string
      required:
        - status
        - message

    Claims:
      type: object
      description: JWT claims dictionary. Contents vary by token.
      additionalProperties: true

paths:
  /has/{subject}/{target}/{permission}:
    get:
      summary: Check permission (path parameters)
      description: >
        Checks whether the subject has the specified permission on the target.
        Uses path parameters. The permission segment uses Flask's path converter,
        allowing hierarchical permissions with slashes (e.g., data/read).
      security:
        - BearerAuth: []
      parameters:
        - name: subject
          in: path
          required: true
          schema:
            type: string
          description: Principal identifier (email address)
          example: worker@my-project.iam.gserviceaccount.com
        - name: target
          in: path
          required: true
          schema:
            type: string
          description: Service/resource identifier
          example: data-pipeline
        - name: permission
          in: path
          required: true
          schema:
            type: string
          description: Permission string (may contain slashes)
          example: execute
      responses:
        '204':
          description: Permission granted (empty body)
        '403':
          description: Permission denied
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              example:
                status: Error
                message: "worker@example.com does not have execute for data-pipeline"
        '401':
          description: Not authenticated (JWT missing or invalid, from before_request)
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
              example:
                error: Not authenticated
        '500':
          description: Internal server error
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              example:
                status: Error
                message: "Exception during processing request."

  /has:
    get:
      summary: Check permission (query parameters)
      description: >
        Checks whether the subject has the specified permission on the target.
        Uses query parameters. Identical logic to the path-based endpoint.
      security:
        - BearerAuth: []
      parameters:
        - name: subject
          in: query
          required: true
          schema:
            type: string
          description: Principal identifier (email address)
        - name: target
          in: query
          required: true
          schema:
            type: string
          description: Service/resource identifier
        - name: permission
          in: query
          required: true
          schema:
            type: string
          description: Permission string
      responses:
        '204':
          description: Permission granted (empty body)
        '400':
          description: Missing required query parameter
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              examples:
                missing_subject:
                  value:
                    status: Error
                    message: "The status query parameter is missing"
                  summary: "Note: error message says 'status' instead of 'subject' (known bug)"
                missing_target:
                  value:
                    status: Error
                    message: "The target query parameter is missing"
                missing_permission:
                  value:
                    status: Error
                    message: "The permission query parameter is missing"
        '403':
          description: Permission denied
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
        '401':
          description: Not authenticated
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
        '500':
          description: Internal server error
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'

  /key/{kid}:
    get:
      summary: Get public key by key ID
      description: >
        Returns the public key (PEM format) for the given key identifier.
        Used by other services to verify JWTs signed by dockmaster.
      security:
        - BearerAuth: []
      parameters:
        - name: kid
          in: path
          required: true
          schema:
            type: string
          description: Key identifier (matches the JWT header kid value)
      responses:
        '200':
          description: Public key in PEM format
          content:
            application/x-pem-file:
              schema:
                type: string
              example: |
                -----BEGIN PUBLIC KEY-----
                MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
                -----END PUBLIC KEY-----
        '404':
          description: Key not found
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
              example:
                error: "Key abc123 was not found."
        '401':
          description: Not authenticated
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
        '500':
          description: Internal server error
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'

  /exchange:
    get:
      summary: Exchange Google token for dockmaster JWT
      description: >
        Exchanges a Google Login JWT or Google access token for a dockmaster-issued JWT.
        The Google token must be provided as a Bearer token in the Authorization header.
        This endpoint is NOT protected by the before_request JWT check.

        **Flow:**
        1. Try to verify Bearer token as a JWT via ServiceRealm
        2. If JWT verification fails, validate as a Google access token via tokeninfo endpoint
        3. Validate issuer, audience, and email domain
        4. Sign and return a new dockmaster JWT
      security:
        - BearerAuth: []
      parameters:
        - name: service
          in: query
          required: false
          schema:
            type: string
          description: >
            Audience for the issued JWT. If omitted, uses the audience from the
            incoming JWT. Required when exchanging an access token (no aud claim).
        - name: expiry
          in: query
          required: false
          schema:
            type: integer
            default: 3600
          description: Token lifetime in seconds
      responses:
        '200':
          description: Successfully issued dockmaster JWT
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Token'
              example:
                token: "eyJhbGciOiJSUzI1NiIs..."
                subject: "user@shipyard.com"
                service: "https://my-api.example.com/"
                expiry: 3600
        '400':
          description: Missing required parameter
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              examples:
                no_service:
                  value:
                    status: Error
                    message: "The service argument is required for access tokens"
                no_email:
                  value:
                    status: Error
                    message: "The email claim is missing"
        '401':
          description: Not authenticated (token invalid or missing)
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
              example:
                error: Not authenticated
        '403':
          description: Authorization failed (issuer, audience, or domain not allowed)
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              examples:
                bad_issuer:
                  value:
                    status: Error
                    message: "Issuer https://evil.com is not allowed"
                bad_audience:
                  value:
                    status: Error
                    message: "The audience is not allowed"
                bad_domain:
                  value:
                    status: Error
                    message: "Domain evil.com is not allowed"
        '503':
          description: Service not configured
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              example:
                status: Error
                message: "The service is not configured with an issuer"

  /refresh:
    post:
      summary: Refresh token exchange
      description: >
        Uses a Google refresh token to obtain a new dockmaster JWT.
        This endpoint is NOT protected by the before_request JWT check.

        **Flow:**
        1. Look up client secret from Secret Manager using client_id
        2. Call Google's token endpoint with the refresh token
        3. Verify the returned ID token
        4. Validate issuer, audience, and domain (NOTE: can_issue flag is set but never checked -- known bug)
        5. Fetch user profile info via userinfo endpoint
        6. Sign and return a new dockmaster JWT
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RefreshTokenRequest'
            example:
              token: "1//0abc..."
              client_id: "109370504310-p2e82hp5cvubrub37jjrbpgabj0ivlnv"
              service: "https://my-api.example.com/"
              expiry: 3600
      responses:
        '200':
          description: Successfully issued dockmaster JWT
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Token'
              example:
                token: "eyJhbGciOiJSUzI1NiIs..."
                subject: "user@shipyard.com"
                service: "https://my-api.example.com/"
                expiry: 3600
                claims:
                  name: "Jane Doe"
                  picture: "https://lh3.googleusercontent.com/..."
                  given_name: "Jane"
                  family_name: "Doe"
                  locale: "en"
                id_token: "eyJhbGciOiJSUzI1NiIs..."
                access_token: "ya29.a0..."
        '400':
          description: Invalid client_id or missing parameters
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              examples:
                no_client_id:
                  value:
                    status: Error
                    message: "No client_id was specified and there is no default."
                invalid_client_id:
                  value:
                    status: Error
                    message: "Invalid client_id value"
        '401':
          description: Refresh token rejected by Google
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              example:
                status: Error
                message: "Not authenticated"
        '500':
          description: Refresh endpoint not configured
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              example:
                status: Error
                message: "Refresh endpoint is not configured"
        '503':
          description: Issuer not configured
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              example:
                status: Error
                message: "The service is not configured with an issuer"

  /claims:
    get:
      summary: Get JWT claims
      description: >
        Returns the decoded claims from the authenticated JWT.
        The JWT must be provided as a Bearer token and is verified by the before_request handler.
      security:
        - BearerAuth: []
      responses:
        '200':
          description: JWT claims dictionary
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Claims'
              example:
                iss: "dock-master@shipyard-auth-2022.iam.gserviceaccount.com"
                sub: "user@shipyard.com"
                aud: "https://my-api.example.com/"
                iat: 1700000000
                exp: 1700003600
                email: "user@shipyard.com"
                name: "Jane Doe"
        '401':
          description: Not authenticated
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
```

---

## Endpoint Summary Table

| Method | Path | Auth Required | Skip `before_request` | Description |
|---|---|---|---|---|
| GET | `/has/{subject}/{target}/{permission}` | Yes (JWT) | No | RBAC permission check (path params) |
| GET | `/has` | Yes (JWT) | No | RBAC permission check (query params) |
| GET | `/key/{kid}` | Yes (JWT) | No | Public key retrieval |
| GET | `/exchange` | Yes (Bearer) | Yes | Token exchange (Google → dockmaster) |
| POST | `/refresh` | No | Yes | Refresh token exchange |
| GET | `/claims` | Yes (JWT) | No | Return authenticated JWT claims |
| GET | `/apidocs` | No | Yes | Swagger UI (provided by watchtower) |
| GET | `/apispec` | No | Yes | OpenAPI JSON spec (provided by watchtower) |

---

## Authentication Notes

### before_request Skip List

The following path prefixes bypass JWT authentication:
- `/exchange` -- handles its own token verification
- `/refresh` -- unauthenticated endpoint
- `/apidocs` -- Swagger UI
- `/apispec` -- OpenAPI spec

All other paths require a valid JWT in the `Authorization: Bearer <token>` header, verified by `ServiceRealm.verify()`.

### Error Response Formats

The service uses two different error response formats:

**From `jwt_authenticate` (401 responses):**
```json
{"error": "Not authenticated"}
```

**From endpoint handlers (400/403/500/503 responses):**
```json
{"status": "Error", "message": "..."}
```

This inconsistency should be unified in a recreation.
