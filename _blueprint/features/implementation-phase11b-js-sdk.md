# Phase 11b: Node.js Browser Auth SDK (`@dockmaster/auth`)

> TypeScript browser client for Astro and React SPAs to integrate with dockmaster —
> login/logout flow, token management, authenticated fetch, and permission checks.

**Status**: Planned
**Priority**: P1
**Phase**: 11b (after Phase 11 server-side route reorg)
**Last updated**: 2026-03-18

---

## Problem

Domain A and Domain B frontend apps (Astro, React) need to integrate with dockmaster for:
- User login/logout via OAuth redirect
- Token management (refresh tokens for cross-domain, cookies for same-domain)
- Authenticated API calls with auto-refreshing Type C JWTs
- Permission-aware UI (check if user has access before showing features)

Without a client SDK, each frontend app would reimplement: OAuth redirect handling, token
storage, refresh logic, Bearer header attachment, and expiry management. This is error-prone
and creates security risk from inconsistent implementations.

**Concrete apps:**
- **Domain A**: Astro site (now) / React SPA (eventually) — same domain as dockmaster, uses
  session cookies
- **Domain B**: React SPA + Astro site — different TLD, uses refresh tokens (Phase 11 design)

---

## Solution Overview

A single TypeScript package (`@dockmaster/auth`) that provides:
1. `DockmasterAuth` class — initialize, login, logout, token management
2. Two auth modes: `'cookie'` (same-domain) and `'token'` (cross-domain)
3. Authenticated fetch wrapper with auto-refresh
4. Typed response models for all dockmaster API interactions
5. `onAuthChange` event for framework integration (React state updates, etc.)

---

## SDK API

### Initialization

```typescript
import { DockmasterAuth } from '@dockmaster/auth'

const auth = new DockmasterAuth({
  // Required
  url: 'https://auth.domainA.com',  // Dockmaster base URL
  mode: 'token',                     // 'cookie' | 'token'

  // Optional
  callbackPath: '/auth/callback',    // Where dockmaster redirects after login (default: '/auth/callback')
  defaultReturnTo: '/dashboard',     // Where to go after login if no returnTo specified (default: '/')
})
```

**Mode validation at construction:**
- `mode: 'cookie'` + cross-origin `url` → throws:
  `"Cookie mode requires same-origin. Use mode: 'token' for cross-domain auth."`
- `mode: 'token'` on any domain → works (developer's choice)

### Login / Logout

```typescript
// Redirect to dockmaster login
auth.login({ returnTo: '/dashboard' })
// Stores returnTo in sessionStorage, redirects to:
// GET {url}/auth/login?redirect_uri={origin}{callbackPath}

// Handle OAuth callback (call this on your callback page)
await auth.handleCallback()
// Token mode: reads ?code= from URL, calls POST /auth/login/exchange,
//   stores refresh_token in sessionStorage, redirects to returnTo
// Cookie mode: no-op (dockmaster already set cookie and redirected)

// Logout
await auth.logout()
// Token mode: calls POST /auth/logout with refresh_token body,
//   clears sessionStorage, sets auth state to unauthenticated
// Cookie mode: calls POST /auth/logout (cookie sent automatically),
//   sets auth state to unauthenticated
```

### Auth State

```typescript
auth.isAuthenticated  // boolean — true if valid session exists
auth.user             // DockmasterUser | null — { email, name, picture }

// Listen for changes (login, logout, token refresh failure)
const unsubscribe = auth.onAuthChange((state: AuthState) => {
  // state.isAuthenticated, state.user
  // Use this to trigger React re-renders, Astro island updates, etc.
})
```

### Token Management

```typescript
// Get a Type C JWT for a specific service (auto-cached, auto-refreshed)
const token = await auth.getToken('billing')
// Token mode: calls POST /auth/session/token { refresh_token, service }
// Cookie mode: calls POST /auth/session/token?service=billing (cookie auto-sent)
// Returns cached JWT if not expired, refreshes if needed

// JWT cache: keyed by service name, cached until (exp - 60s) buffer
// If refresh fails (session expired) → sets isAuthenticated=false, fires onAuthChange
```

### Authenticated Fetch

```typescript
// Fetch wrapper — attaches Bearer JWT, auto-refreshes on 401
const response = await auth.fetch('https://api.domainA.com/data', {
  service: 'billing',       // Which service audience to use for the JWT
  // ...standard fetch options (method, body, headers, etc.)
})

// Under the hood:
// 1. getToken('billing') → JWT (cached or refreshed)
// 2. fetch(url, { ...options, headers: { Authorization: 'Bearer <JWT>' } })
// 3. If 401 → refresh token, retry once
// 4. If retry fails → throw AuthError
```

### Permission Checks

```typescript
// Check if current user has a permission (uses cached JWT as Bearer)
const canRead = await auth.hasPermission({
  subject: auth.user.email,  // or from JWT claims
  target: 'billing',
  permission: 'read',
  service: 'billing',        // which JWT to use for the API call
})
// Calls GET /auth/has/{subject}/{target}/{permission} with Bearer JWT
// Result cached by subject+target+permission for a configurable TTL
```

---

## Auth Flows in Detail

### Token Mode (Domain B — cross-domain)

```
User clicks Login
  ├─ SDK stores returnTo in sessionStorage
  ├─ SDK redirects to: GET {dockmaster}/auth/login?redirect_uri={origin}/auth/callback
  │
  ├─ Dockmaster → Google OAuth → Dockmaster callback
  ├─ Dockmaster creates auth code, redirects to: {origin}/auth/callback?code=ABC&state=XYZ
  │
  ├─ User lands on /auth/callback page
  ├─ App calls auth.handleCallback()
  │   ├─ SDK reads ?code= and ?state= from URL
  │   ├─ SDK calls POST {dockmaster}/auth/login/exchange { code, redirect_uri }
  │   ├─ Response: { refresh_token, profile: { email, name, picture } }
  │   ├─ SDK stores refresh_token in sessionStorage
  │   ├─ SDK sets auth state: isAuthenticated=true, user=profile
  │   └─ SDK navigates to returnTo (from sessionStorage, default '/')
  │
  └─ User is now authenticated

API call:
  ├─ auth.getToken('billing') or auth.fetch(...)
  ├─ SDK calls POST {dockmaster}/auth/session/token { refresh_token, service: 'billing' }
  ├─ Response: { access_token: '<JWT>', expires_in: 900 }
  ├─ SDK caches JWT in memory, keyed by service
  └─ Returns JWT (or attaches as Bearer for auth.fetch)

Page refresh:
  ├─ Refresh token survives (sessionStorage)
  ├─ JWT cache lost (in-memory) → next getToken() call re-fetches
  ├─ auth.user is null until first API call or explicit restore
  └─ SDK can restore user by calling GET /auth/session/principal with refresh_token
      (or by decoding the JWT claims from the next getToken() call)

Tab close:
  ├─ sessionStorage cleared → refresh token gone
  └─ User must re-login on next visit
```

### Cookie Mode (Domain A — same domain)

```
User clicks Login
  ├─ SDK stores returnTo in sessionStorage
  ├─ SDK redirects to: GET {dockmaster}/auth/login
  │   (no redirect_uri — dockmaster handles the cookie flow)
  │
  ├─ Dockmaster → Google OAuth → Dockmaster callback
  ├─ Dockmaster creates session, sets session_id cookie
  ├─ Dockmaster redirects to /ui/ (default) — BUT we want returnTo
  │
  │   NOTE: In cookie mode, the SDK needs dockmaster to redirect back to
  │   the app, not to /ui/. Options:
  │   (a) Use redirect_uri pointing to the app's callback page (same as token mode)
  │   (b) Add a return_to param to /auth/login that dockmaster uses after setting cookie
  │   Decision: Use redirect_uri (option a) — same flow as token mode, but dockmaster
  │   sees it's same-origin and sets cookie + redirects (no auth code needed)
  │
  ├─ User lands on /auth/callback
  ├─ auth.handleCallback()
  │   ├─ Cookie mode: no code exchange needed (cookie already set)
  │   ├─ SDK calls GET /auth/session/principal (cookie auto-sent) to get user profile
  │   ├─ Sets auth state: isAuthenticated=true, user=profile
  │   └─ Navigates to returnTo
  │
  └─ User is now authenticated

API call:
  ├─ auth.getToken('billing')
  ├─ SDK calls POST /auth/session/token?service=billing (cookie auto-sent)
  └─ Response: { access_token: '<JWT>', expires_in: 900 }
```

### Cookie Mode — Server-Side Consideration

In cookie mode, when using `redirect_uri` to send the user back to the app, dockmaster's
current callback handler would create an auth code (external redirect flow) instead of setting
a cookie. This needs a server-side adjustment:

**Option**: If `redirect_uri` is same-origin as dockmaster (or on a configured list of
"cookie-eligible" origins), the callback should set the cookie AND redirect to the URI. No
auth code needed.

**Alternative**: Cookie mode apps don't use redirect_uri at all. Instead, dockmaster has a
`return_to` query param on `/auth/login` that it passes through the OAuth flow and uses as the
post-login redirect destination after setting the cookie. This is simpler and keeps the auth
code flow purely for cross-domain.

**Recommendation**: The `return_to` approach is cleaner. Add `return_to` param support to
`GET /auth/login` — dockmaster stores it in OAuth state, and after setting the cookie, redirects
to `return_to` instead of `/ui/`. This is a small server-side change in Phase 11.

---

## Token Management Details

### Storage Strategy

| Token | Storage | Why |
|---|---|---|
| Refresh token | sessionStorage | Persists across page refresh, back/forward, in-page navigation. Cleared on tab close. Cross-domain safe (same-origin policy). |
| Type C JWT | In-memory (Map) | Short-lived (15 min). Cheap to regenerate from refresh token. No persistence needed. |
| User profile | In-memory | Derived from login response or JWT claims. Restored on first API call after page refresh. |
| returnTo URL | sessionStorage | Stored before OAuth redirect, consumed after callback. |

### JWT Cache Logic

```
getToken(service):
  1. Check in-memory cache for service
  2. If cached AND (exp - now > 60s) → return cached JWT
  3. If cached AND expired/near-expiry → refresh
  4. If not cached → fetch new

refresh:
  Token mode: POST /auth/session/token { refresh_token, service }
  Cookie mode: POST /auth/session/token?service=X (cookie auto-sent)

  If 401 (session expired):
    → Clear all tokens and auth state
    → Fire onAuthChange({ isAuthenticated: false, user: null })
    → Throw SessionExpiredError

  If success:
    → Cache new JWT in memory (keyed by service)
    → Return JWT
```

### Auth State Restoration After Page Refresh

On page load, if sessionStorage has a refresh token (token mode):
1. `isAuthenticated` = true (optimistic, refresh token exists)
2. `user` = null (not yet loaded)
3. First `getToken()` call fetches a JWT, from which we decode user claims
4. Or: explicit `auth.restore()` method calls `GET /auth/session/principal` with the refresh token

For cookie mode: call `GET /auth/session/principal` on load. If 200 → authenticated. If 401 → not.

---

## TypeScript Types & Response Models

```typescript
// === Configuration ===

interface DockmasterAuthConfig {
  url: string                         // Dockmaster base URL
  mode: 'cookie' | 'token'           // Auth mode
  callbackPath?: string               // Default: '/auth/callback'
  defaultReturnTo?: string            // Default: '/'
  tokenCacheBufferSeconds?: number    // Refresh JWT this many seconds before expiry (default: 60)
  permissionCacheTTL?: number         // Cache permission results for N seconds (default: 60)
}

// === Auth State ===

interface AuthState {
  isAuthenticated: boolean
  user: DockmasterUser | null
}

interface DockmasterUser {
  email: string
  name?: string
  picture?: string
  given_name?: string
  family_name?: string
}

// === API Responses ===

interface LoginCodeResponse {
  refresh_token: string
  profile: DockmasterUser
}

interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

interface PermissionCheckResponse {
  allowed: boolean
  subject: string
  target: string
  permission: string
}

// === JWT Claims (decoded from Type C JWT) ===

interface DockmasterJWTClaims {
  sub: string           // User email or service account email
  aud: string           // Target service name
  iss: string           // Dockmaster issuer
  exp: number           // Expiry timestamp
  iat: number           // Issued-at timestamp
  [key: string]: unknown
}

// === Errors ===

class DockmasterAuthError extends Error {
  code: 'SESSION_EXPIRED' | 'NETWORK_ERROR' | 'INVALID_CONFIG' | 'AUTH_CODE_INVALID'
}

// === Permission Check ===

interface PermissionCheckOptions {
  subject: string       // User email (usually auth.user.email)
  target: string        // Service/resource name
  permission: string    // Permission name
  service: string       // Which service JWT to use for the API call
}

// === Fetch Options ===

interface DockmasterFetchOptions extends RequestInit {
  service: string       // Which service audience for the Bearer JWT
}
```

---

## Package Structure

### Monorepo layout

```
dockmaster/
├── src/dockmaster/                  # Python package (unchanged)
├── packages/
│   └── auth-js/                     # Node.js/browser SDK
│       ├── src/
│       │   ├── index.ts             # Public exports
│       │   ├── client.ts            # DockmasterAuth class
│       │   ├── token-manager.ts     # JWT cache, refresh logic, storage
│       │   ├── auth-flows.ts        # Login/logout/callback handling
│       │   ├── permissions.ts       # Permission check client + cache
│       │   └── types.ts             # All exported TypeScript interfaces
│       ├── tests/
│       │   ├── client.test.ts       # DockmasterAuth integration tests
│       │   ├── token-manager.test.ts
│       │   ├── auth-flows.test.ts
│       │   └── permissions.test.ts
│       ├── package.json
│       ├── tsconfig.json
│       ├── vitest.config.ts         # Test runner (Vitest — fast, ESM-native)
│       └── README.md
├── tests/                           # Python tests (unchanged)
├── pyproject.toml
└── justfile                         # Add js-* targets
```

### Source module responsibilities

| Module | Responsibility |
|---|---|
| `index.ts` | Re-exports `DockmasterAuth`, all types, error classes |
| `client.ts` | `DockmasterAuth` class — orchestrates flows, exposes public API, manages auth state + event listeners |
| `token-manager.ts` | Token storage (sessionStorage + in-memory), JWT cache with expiry, refresh logic |
| `auth-flows.ts` | `login()`, `handleCallback()`, `logout()` — OAuth redirect handling, returnTo management, mode-specific behavior |
| `permissions.ts` | `hasPermission()` — HTTP client for `/auth/has`, result caching |
| `types.ts` | All exported interfaces (config, auth state, API responses, JWT claims, errors) |

### Build configuration

**TypeScript → ESM only** (for now):
- `tsconfig.json`: `target: "ES2022"`, `module: "ESNext"`, `moduleResolution: "bundler"`
- Output: `dist/` directory with `.js` + `.d.ts` files
- `package.json`: `"type": "module"`, `"exports": { ".": { "import": "./dist/index.js", "types": "./dist/index.d.ts" } }`

**Future**: Add CJS output if needed (dual `import`/`require` exports).

### Dependencies

| Package | Purpose | Notes |
|---|---|---|
| `jose` | JWT decoding (`decodeJwt`) | Zero-dependency, browser-native, well-maintained |

**Dev dependencies**: `typescript`, `vitest`, `@types/node` (if needed for build)

No other runtime dependencies. Uses browser-native `fetch`, `URL`, `sessionStorage`, `crypto`.

---

## Registry & Publishing

### Primary: GCP Artifact Registry

Host the package in GCP Artifact Registry (npm format). Your apps configure a `.npmrc` to
pull from the registry:

```
# .npmrc in consuming app
@dockmaster:registry=https://{REGION}-npm.pkg.dev/{PROJECT_ID}/{REPO_NAME}/
///{REGION}-npm.pkg.dev/{PROJECT_ID}/{REPO_NAME}/:_authToken=${ARTIFACT_REGISTRY_TOKEN}
```

**Setup**:
1. Create an npm Artifact Registry repo in your GCP project (one-time)
2. Authenticate with `gcloud auth application-default print-access-token` or a service account key
3. Publish with `npm publish --registry=https://...`

### Future: npm (public)

Publish to public npm if/when you want external consumers. Requires:
- Claim the `@dockmaster` scope on npmjs.com (or choose another scope)
- Set up npm token as GitHub Actions secret
- Tag-based publish workflow

---

## CI/CD

### Build & test (on PR / push)

GitHub Actions workflow triggered by changes to `packages/auth-js/**`:

```yaml
# .github/workflows/js-ci.yml
on:
  push:
    paths: ['packages/auth-js/**']
  pull_request:
    paths: ['packages/auth-js/**']

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - run: cd packages/auth-js && npm ci
      - run: cd packages/auth-js && npm run lint
      - run: cd packages/auth-js && npm run typecheck
      - run: cd packages/auth-js && npm test
      - run: cd packages/auth-js && npm run build
```

### Publish (on tag)

Triggered by tags matching `auth-js-v*` on main:

```yaml
# .github/workflows/js-publish.yml
on:
  push:
    tags: ['auth-js-v*']

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - uses: google-github-actions/auth@v2
        with: { credentials_json: '${{ secrets.GCP_SA_KEY }}' }
      - run: cd packages/auth-js && npm ci && npm run build
      - run: cd packages/auth-js && npm publish --registry=https://...
```

### Justfile targets

```makefile
# Add to existing justfile
js-install:
    cd packages/auth-js && npm ci

js-build:
    cd packages/auth-js && npm run build

js-test:
    cd packages/auth-js && npm test

js-lint:
    cd packages/auth-js && npm run lint

js-typecheck:
    cd packages/auth-js && npx tsc --noEmit

js-check: js-lint js-typecheck js-test
```

---

## Testing Approach

### Unit tests (Vitest)

**`token-manager.test.ts`**:
- JWT cache: stores by service key, returns cached until buffer before expiry
- Refresh: calls correct endpoint based on mode (cookie vs token)
- Expiry: clears cache, fires state change on session expired (401)
- Storage: refresh token in sessionStorage, JWT in memory

**`auth-flows.test.ts`**:
- Login: stores returnTo, constructs correct redirect URL per mode
- Callback (token mode): reads code from URL, calls /auth/login/code, stores refresh token
- Callback (cookie mode): calls /auth/session/principal, sets user
- Logout: calls /auth/logout, clears state
- returnTo validation: rejects external URLs, allows relative paths and same-origin

**`permissions.test.ts`**:
- Calls correct endpoint with Bearer JWT
- Caches results by subject+target+permission
- Cache expires after TTL
- Handles network errors gracefully

**`client.test.ts`**:
- Mode validation (cookie + cross-origin → error)
- Config defaults
- onAuthChange fires on login, logout, session expiry
- auth.fetch attaches Bearer, retries on 401

### Mocking strategy

- Mock `fetch` globally (Vitest can do this)
- Mock `sessionStorage` with an in-memory implementation
- Mock `window.location` for redirect tests
- No real dockmaster server needed for unit tests

### Integration tests (future)

- Full flow against running dockmaster (`@playwright/test` or similar)
- Login redirect → Google OAuth mock → callback → token → API call
- Marked as integration, not run in CI by default

---

## Server-Side Changes (additions to Phase 11)

### `return_to` parameter on `GET /auth/login` — ✅ ALREADY IMPLEMENTED

Phase 11 Step E implemented `return_to` support on the login flow (cookie flow + refresh
token flow, with open redirect prevention). No additional server-side work needed for this.

### Logout content negotiation — PENDING (Phase 11 Step H)

`POST /auth/logout` needs to return JSON `{"ok": true}` when the request includes a
`refresh_token` body (API/cross-domain clients) instead of redirecting. This is Phase 11
Step H, not yet implemented.

---

## Deferred Items (explicitly out of scope)

| Item | Why deferred | When to revisit |
|---|---|---|
| React hooks (`useAuth`, `AuthProvider`) | Framework-specific, build on core first | When actively building React SPA |
| Astro middleware/integration | Framework-specific | When actively building Astro SSR app |
| SSR server middleware | Requires Node.js runtime patterns different from browser | When an SSR app needs it |
| CommonJS output | Modern bundlers use ESM | If a CJS consumer appears |
| npm public publish | Only using GCP Artifact Registry for now | When external consumers exist |
| Refresh token rotation | Security enhancement | After core flows are stable |
| Offline/service worker support | Edge case | If PWA use case arises |

---

## Dependencies

- **Requires**: Phase 11 server-side (route reorg + refresh token endpoints)
- **Requires**: `return_to` param on `GET /auth/login` (small addition to Phase 11)
- **Enables**: Domain B SPA integration (React, Astro)
- **Enables**: Domain A SPA integration (cookie mode)
- **Enables**: Future React hooks / Astro middleware packages

## Acceptance Criteria

- [ ] `DockmasterAuth` class initializes with url + mode, validates config at construction
- [ ] `auth.login()` redirects to dockmaster with correct params per mode
- [ ] `auth.handleCallback()` exchanges auth code (token mode) or fetches principal (cookie mode)
- [ ] `auth.getToken(service)` returns cached JWT or fetches new one via refresh token/cookie
- [ ] `auth.fetch(url, { service })` attaches Bearer JWT, retries on 401
- [ ] `auth.hasPermission()` calls `/auth/has` with bearer passthrough + caching
- [ ] `auth.logout()` destroys session and clears local state
- [ ] `auth.onAuthChange()` fires on login, logout, session expiry
- [ ] Refresh token stored in sessionStorage, JWT cached in memory
- [ ] Config validation: cookie mode + cross-origin → error with helpful message
- [ ] returnTo validation: only relative paths or same-origin URLs
- [ ] Package builds as ESM TypeScript → JS + .d.ts
- [ ] All types exported (`DockmasterUser`, `TokenResponse`, `JWTClaims`, etc.)
- [ ] Published to GCP Artifact Registry
- [ ] CI workflow runs lint + typecheck + tests on changes to packages/auth-js/
- [ ] Publish workflow triggers on auth-js-v* tags
- [ ] Unit tests cover token management, auth flows, permissions, and client config
