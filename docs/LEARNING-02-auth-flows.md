# Learning 02: Authentication Flows

> How authentication works in Dockmaster, flow by flow. Each flow includes a sequence diagram, step-by-step explanation, and the security considerations involved.

**Audience**: Developers integrating with Dockmaster or learning how OAuth/JWT auth works in practice.

> **Already understand OAuth 2.0 authorization code flow?** Skip to [2. CLI Login](#2-cli-login-flow).
> **Just want the service-to-service flow?** Skip to [4. Token Exchange](#4-service-to-service-token-exchange).

---

## 1. Browser SSO (OAuth Login)

[The primary flow for human users accessing Dockmaster via a web browser. Uses Google OAuth 2.0 authorization code flow to authenticate the user, then establishes a server-side session.]

### 1a. Overview

[One-paragraph summary: user visits /auth/login, gets redirected to Google, authenticates, Google redirects back with an auth code, Dockmaster exchanges it for user info, creates a session, sets a signed cookie.]

### 1b. Sequence Diagram

[Mermaid sequence diagram showing: Browser → /auth/login → Google OAuth → /auth/login/callback → SessionStore → Browser (cookie set). Include state parameter for CSRF, code exchange with Google, domain validation.]

### 1c. Step-by-Step

[Numbered walkthrough of each HTTP request/response in the flow. What happens at each step, what gets checked (state, domain, etc.), what gets created (session).]

### 1d. Security Considerations

[CSRF protection via state parameter (TTLStore). Domain validation against authorized_domains. Session cookie signing with itsdangerous. httponly/secure flags. Session TTL.]

---

## 2. CLI Login Flow

[How the Dockmaster CLI authenticates a human user. Similar to browser SSO but redirects back to a localhost port where the CLI is listening, delivering a JWT instead of a session cookie.]

### 2a. Overview

[One-paragraph summary: CLI starts a local HTTP server on a random port, opens browser to /auth/cli/login?redirect_uri=http://localhost:PORT/callback, user authenticates with Google, Dockmaster redirects to localhost with a Type C JWT in the query string, CLI captures it and stores to disk.]

### 2b. Sequence Diagram

[Mermaid sequence diagram showing: CLI → Browser → /auth/cli/login → Google OAuth → /auth/cli/callback → 302 to localhost:PORT/callback?token=<JWT> → CLI captures token → stores to ~/.local/share/dockmaster/.]

### 2c. Step-by-Step

[Numbered walkthrough. Emphasis on: how redirect_uri is validated against allowed_redirect_uris, how localhost is treated specially, how the token is delivered via query parameter (and why this is acceptable for localhost).]

### 2d. Security Considerations

[Redirect URI validation. localhost-only for direct token delivery. Token delivered via query param — acceptable because localhost traffic never leaves the machine. Token stored with file permissions. Token TTL.]

---

## 3. Auth Code Flow (External App)

[How an external application (SPA, mobile app, another web service) authenticates users through Dockmaster. Uses an intermediate auth code to avoid exposing the JWT in the redirect URL.]

### 3a. Overview

[One-paragraph summary: external app redirects user to /auth/login?redirect_uri=https://app.example.com/callback, user authenticates, Dockmaster redirects back with a short-lived login ticket code (not a JWT), app exchanges the code for a refresh_token and profile via POST /auth/login/exchange.]

### 3b. Sequence Diagram

[Mermaid sequence diagram showing: SPA → /auth/login → Google OAuth → /auth/login/callback → 302 to redirect_uri?code=<code>&state=<state> → SPA → POST /auth/login/exchange → {refresh_token, profile, return_to} returned.]

### 3c. Step-by-Step

[Numbered walkthrough. Emphasis on: why auth code (not JWT) in the redirect — browser history, referer headers. How the code is stored (AuthCodeStore with TTL). The exchange endpoint validates code + redirect_uri match.]

### 3d. Security Considerations

[Auth code is single-use and short-lived (TTL). redirect_uri must match allowed_redirect_uris exactly. Code exchange requires the same redirect_uri that initiated the flow. State parameter for CSRF.]

---

## 4. Service-to-Service Token Exchange

[How a backend service with a Google credential (SA JWT or access token) obtains a Dockmaster Type C JWT scoped to a target service.]

### 4a. Overview

[One-paragraph summary: service presents a Google SA JWT or access token to POST /auth/service/token?service=<target>, Dockmaster verifies the credential, checks the service identity, issues a Type C JWT with the caller's identity.]

### 4b. Sequence Diagram

[Mermaid sequence diagram showing: Service → signs JWT with SA key → POST /auth/service/token (Bearer: <JWT>) → Dockmaster verifies via ServiceRealm → issues Type C JWT → Service uses Type C JWT to call target service.]

### 4c. Step-by-Step

[Numbered walkthrough. Two paths: Bearer JWT (verified via key cache → GCP IAM public keys) and access token (verified via Google tokeninfo endpoint). Domain validation. Type C JWT issuance with EphemeralKeypairSigner.]

### 4d. Security Considerations

[JWT signature verification against cached GCP public keys. Issuer must be in authorized_issuers. Domain must be in authorized_domains. Access tokens validated against Google's tokeninfo endpoint. Returned JWT has limited TTL.]

---

## 5. Token Issuance

[How an already-authenticated user (via session or JWT) requests a new Type C JWT, optionally scoped to a specific audience or target.]

### 5a. Overview

[One-paragraph summary: authenticated user (session cookie or refresh_token) calls POST /auth/session/token?service=<target>, receives a fresh Type C JWT. Used when a browser user needs a JWT to call an API, or when an external app with a refresh_token needs a service-scoped token.]

### 5b. Sequence Diagram

[Mermaid sequence diagram showing: Browser/Service (with session cookie or refresh_token) → POST /auth/session/token?service=<target> → Dockmaster verifies identity → issues Type C JWT.]

### 5c. Step-by-Step

[Numbered walkthrough. Auth gate: allow_jwt_or_session. Extracts user identity from session or JWT claims. Signs new Type C token with requested audience/TTL.]

---

## 6. How Verification Works

[How Dockmaster (and consuming services) verify JWTs they receive.]

### 6a. The Verification Pipeline

[JWT arrives → extract kid from header → look up public key → verify signature → validate claims (exp, iss, aud). ServiceRealm orchestrates this.]

### 6b. Key Cache Architecture

[Diagram showing the two key caches: EphemeralKeyCache (local, fast — for Type C tokens) and ServiceAccountKeyCache (GCP IAM + Google OIDC — for Type A tokens). ServiceRealm checks them in order.]

### 6c. Public Key Distribution

[Dockmaster serves its ephemeral public keys at /auth/key/{kid} and /auth/keys (JWKS). Consuming services fetch these to verify Type C tokens independently — no need to call Dockmaster for every request.]

### 6d. Verification Diagram

[Mermaid sequence diagram showing: Consuming Service receives JWT → extracts kid → fetches /auth/key/{kid} (cached) → verifies signature → reads claims → authorized.]
