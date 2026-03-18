# Learning 04: Dockmaster Internals

> How Dockmaster works under the hood. Covers the app factory, configuration system, middleware stack, key management, and session management.

**Audience**: Developers who want to understand or modify Dockmaster's implementation.

> **Just need to integrate with Dockmaster?** See [Learning 02: Auth Flows](LEARNING-02-auth-flows.md) instead.

---

## 1. App Factory & Lifespan

[How the FastAPI application is created, configured, and started.]

### 1a. The create_app() Pattern

[`create_app(settings)` is the app factory. Accepts optional Settings (falls back to env vars). Creates FastAPI instance, attaches settings to app.state, sets up middleware, registers route modules. This pattern enables testing — pass test settings, get a test app.]

### 1b. The Lifespan Context Manager

[Expensive objects are created once at startup in the `lifespan()` async context manager and attached to `app.state`. Torn down on shutdown. List of what gets created: signer, token_issuer, realm (with key caches), auth_code_store, oauth_state_store, session_store, oauth client, secrets_storage, authority, admin_storage.]

### 1c. app.state as a Service Locator

[All singletons live on `app.state`. Route handlers access them via `request.app.state.X`. This avoids global state and makes testing straightforward — override `app.state.X = FakeX()` before running tests.]

### 1d. Startup Flow Diagram

[Mermaid flowchart showing: create_app() → Settings loaded → middleware configured → routes registered → lifespan starts → singletons created → app ready to serve. Show the conditional paths (SA key present vs not, OAuth client configured vs not, etc.).]

---

## 2. Configuration

[How Dockmaster loads and validates its configuration.]

### 2a. Pydantic Settings

[Settings class extends BaseSettings from pydantic-settings. Loads from: env vars (highest priority) → .env file → class defaults. All config in one place — no scattered os.environ calls.]

### 2b. CommaSeparatedSet

[Custom annotated type: `Annotated[str | set[str], BeforeValidator(_parse_comma_separated)]`. Allows env vars like `AUTHORIZED_DOMAINS=a.com,b.com` to be parsed into `{"a.com", "b.com"}`. Used for all multi-value fields. Explain why `str | set[str]` — pydantic-settings needs to accept the raw string from env before the validator converts it.]

### 2c. Session Secret Auto-Generation

[`session_secret_key` uses `Field(default_factory=_generate_session_secret)`. If not set in env, a random key is generated at startup. Module-level flag `_SESSION_SECRET_AUTO_GENERATED` tracks this. Accessor function `session_secret_was_auto_generated()` allows lifespan to log a warning. Sessions won't survive restarts without a stable key.]

### 2d. The Settings DI Bridge

[`get_settings(request)` reads from `request.app.state.settings`. Used as a FastAPI dependency in route signatures. Source of truth is always app.state — never import settings directly. In tests: set `app.state.settings = Settings(...)`, no dependency overrides needed.]

---

## 3. Middleware Stack

[The middleware layers and their execution order.]

### 3a. Execution Order

[Starlette executes middleware in reverse-add order. Diagram showing the request/response path through each layer. The order matters — explain why.]

### 3b. SessionMiddleware

[Starlette's built-in session middleware. Creates a signed "session" cookie used by Authlib during OAuth redirect flow. Distinct from Dockmaster's application-level "session_id" cookie. Both signed with session_secret_key.]

### 3c. CORSMiddleware

[Standard CORS handling. Only added when allowed_origins is configured. Allows GET/POST, Authorization + Content-Type headers, credentials. For SPA cross-origin access.]

### 3d. SecurityHeadersMiddleware

[Adds hardening headers to every response: X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy. Why each header matters. What's NOT set at the app level (HSTS — handled by reverse proxy). Disabled via SECURITY_HEADERS=false.]

### 3e. RequireProxyHeadersMiddleware

[Safety net for production behind a reverse proxy. Returns 502 if X-Forwarded-Proto header is missing. Catches misconfigured proxy setups that would break OAuth callbacks and secure cookies. Enabled by default — local dev opts out with REQUIRE_PROXY_HEADERS=false.]

---

## 4. Key Management

[How Dockmaster manages cryptographic keys for JWT signing and verification.]

### 4a. EphemeralKeypairSigner

[Generates a 2048-bit RSA keypair in memory at startup. Private key never touches disk. Signs Type C JWTs. Key ID (kid) is a random UUID. Public key served at /auth/key/{kid}. New keypair on every restart — existing tokens become unverifiable (acceptable trade-off for simplicity).]

### 4b. ServiceAccountSigner

[Loads a GCP SA private key from a JSON key file. Signs Type A JWTs. Key ID comes from the SA key metadata. Used for service-to-service auth where Dockmaster acts as a service.]

### 4c. Key Caches

[Two cache implementations for JWT verification:
- **EphemeralKeyCache** — holds the local ephemeral public key + loads historical keys from a JWKS registry file. Fast, no network calls. Checked first.
- **ServiceAccountKeyCache** — fetches public keys from GCP IAM (for SA keys) and Google OIDC (for Google-signed tokens). Cached with TTL. Checked second.
ServiceRealm chains both caches — given a kid, it tries each until one returns a key.]

### 4d. JWKS Registry

[File-based registry at ~/.local/share/dockmaster/jwks-registry.json. Stores historical ephemeral public keys so tokens issued by previous instances can still be verified (within their TTL). Updated at startup when a new keypair is generated.]

### 4e. Key Management Diagram

[Mermaid diagram showing: signing path (SA key or ephemeral keypair → JWT) and verification path (JWT → extract kid → EphemeralKeyCache or ServiceAccountKeyCache → public key → verify signature).]

---

## 5. Session Management

[How Dockmaster manages user sessions for browser-based auth.]

### 5a. Session Lifecycle

[User authenticates via OAuth → session created in SessionStore → session_id signed with itsdangerous → set as httponly cookie → subsequent requests include cookie → server looks up session by ID → session data (email, name, picture, expiry) available to route handlers.]

### 5b. InMemorySessionStore

[Current implementation: sessions stored in a Python dict. Simple, no external dependencies. Trade-off: sessions lost on restart. Future: Redis-backed store (redis_url setting exists but not yet implemented).]

### 5c. Session Security

[Session IDs are signed with itsdangerous (HMAC). Tampering is detected. httponly flag prevents JavaScript access. Session TTL enforced server-side. Admin can revoke sessions via /admin/sessions endpoint.]
