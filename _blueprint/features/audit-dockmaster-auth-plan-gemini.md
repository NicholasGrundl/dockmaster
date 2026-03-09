# Audit: Dockmaster Auth Microservice Implementation Plan

**Author**: Principal Engineer (Gemini CLI)
**Date**: March 8, 2026
**Scope**: Phases 2 through 6 of the Dockmaster clean-room rebuild.

---

## 1. Executive Summary & Architectural Pillars

The proposed plan for Dockmaster is a disciplined, modular approach to centralizing identity and access management (IAM) for the LLC domain. By moving from a legacy, likely brittle implementation to a FastAPI-based microservice, we are gaining type safety, observability, and a clear separation of concerns.

The architectural decision to prioritize **Local JWT Verification** (Phase 2) and **Dual-Mode Exchange** (Phase 3) is the correct "Infrastructure-First" approach. It ensures that internal services can communicate securely without a dependency on the browser flow, which is often the most volatile part of an auth system.

However, as a Principal Engineer, I see several "Day 2" operational risks and architectural shortcuts that, while acceptable for a MVP, could become technical debt or security liabilities if not addressed during implementation.

---

## 2. Phase-by-Phase Deep Dive (The "Nerdy" Scrutiny)

### Phase 2: JWT Infrastructure (The Bedrock)
*   **The `kid` Management**: The plan mentions extracting `kid` from the header. We must ensure that the `ServiceAccountKeyCache` handles key rotation gracefully. Google rotates SA keys periodically; our cache must not only have a TTL but also a "force-refresh" mechanism if a `kid` is missing from the current cache but present in the incoming token.
*   **Signature Algorithm**: RS256 is the standard choice here, but we should ensure the `ServiceUser` doesn't allow "algorithm switching" (the classic `alg: none` or HMAC-as-RSA attack). PyJWT handles this if `algorithms=["RS256"]` is strictly enforced in the decoder.
*   **Introspection vs. Verification**: The `/auth/claims` endpoint is a great debug tool, but it MUST be rate-limited and logging-heavy. We don't want a "token oracle" where an attacker can brute-force or test leaked tokens without a trail.

### Phase 3: Token Exchange (The Bridge)
*   **The `can_issue` Flag**: This is a critical legacy fix. However, the spec is vague on *what* `can_issue` actually validates. Is it just domain-matching, or is it tied to a specific GCP project or IAM role? We should define a strict policy engine (even if hardcoded initially) for this flag.
*   **Latency Concerns**: The access token fallback calls Google's `tokeninfo` API. This is an external HTTP hop. If a service uses access tokens for every request, performance will degrade. We should document that the **JWT mode** is the "fast path" and access tokens are the "slow/compatibility path."

### Phase 4: OAuth Login + Session (The Entry Point)
*   **Session State Safety**: `InMemorySessionStore` is fine for single-node development, but it must be thread-safe (FastAPI runs on an event loop, but the underlying dict access should still be handled with care if we ever scale to multiple workers per process).
*   **Refresh Token Storage**: Refresh tokens are "forever tokens" (mostly). Storing them in a session-tied store means that if the session is lost, the user must re-auth. This is safer but less convenient. We should ensure the `SessionStore` protocol includes a way to revoke refresh tokens specifically.
*   **Security Protocol**: We MUST use PKCE (Proof Key for Code Exchange) even for this server-side client to prevent authorization code injection attacks.

### Phase 5: RBAC (The Brain)
*   **Secret Manager as a Database**: This is my biggest "Staff" concern. Secret Manager is not a database. It's a high-latency, strictly versioned key-value store. 
    *   **The Latency Hit**: A cold cache miss could take 200-500ms. 
    *   **The Solution**: The TTL cache is a must, but we should consider a "Pre-warm" strategy where common roles are loaded at startup.
*   **Wildcard Logic**: The plan supports "wildcards (e.g., `projects/*`)". We need to be specific: is this a regex, a glob, or a prefix match? I recommend **Globbing** (e.g., `fnmatch`) as it's intuitive for users.
*   **Permission Granularity**: Are permissions just strings (`read`, `write`) or can they include conditions? Let's stick to strings for Phase 5 to avoid "Policy-as-Code" complexity.

### Phase 6: Management & CLI (The Hands)
*   **RBAC for the RBAC**: Who can call `/admin/*`? The plan says "auth middleware required," but it doesn't specify which role. We need a "Dockmaster Admin" role defined *inside* the system, or a "Bootstrap Admin" env var to solve the circular dependency.
*   **HTMX UI Security**: Ensure CSRF protection is enabled for all HTMX-triggered POST/PUT/DELETE calls. Since we are using Jinja2, we can't rely on a framework like Django to do this automatically.

---

## 3. Blind Spots & "Hard Questions"

### 1. The Circular Dependency (The "Bootstrap" Problem)
How do I create the first role if I need a role to call the API?
*   **Requirement**: We need a `DOCKMASTER_BOOTSTRAP_ADMIN` environment variable that accepts a comma-separated list of emails. These users should bypass RBAC checks and have full admin rights automatically.

### 2. Multi-Region / Multi-Instance Consistency
The `InMemorySessionStore` and `Authority` cache are local to the process.
*   **Risk**: If we run 3 instances of Dockmaster behind a load balancer, an RBAC update on Instance A won't be reflected on Instance B for up to 300 seconds (the TTL).
*   **Principal Recommendation**: This is acceptable for Phase 5, but we MUST document that "RBAC updates are eventually consistent across nodes." If immediate consistency is required, we need a Redis Pub/Sub invalidation mechanism.

### 3. Subject Identity vs. Subject Email
The plan uses `subject` (email) as the key.
*   **Risk**: Google accounts can theoretically change primary emails (though rare for Workspace). More importantly, service account emails look like `name@project.iam.gserviceaccount.com`.
*   **Scrutiny**: Does our wildcard logic handle service account naming patterns correctly? If I grant `projects/*` to `*@prod-project.iam.gserviceaccount.com`, will it work? (The answer should be yes).

### 4. Token Leakage & Revocation
The system issues "Dockmaster JWTs."
*   **Question**: How do we revoke a Dockmaster JWT before it expires? 
*   **Answer**: Currently, we don't (stateless JWTs). We should ensure the JWT lifetime is short (e.g., 1 hour) to minimize the blast radius of a leak.

---

## 4. Technical Assessment (Syntax & Pydantic)

### Pydantic Model Nit-picks
In Phase 5, `Grant` uses `permissions: set[str]`. This is excellent for $O(1)$ lookups. However, `ServiceGrants` uses `roles: dict[str, str]`.
*   **The Issue**: This limits a user to **exactly one role** per service. 
*   **Staff Correction**: Change this to `roles: dict[str, list[str]]` or `dict[str, set[str]]` now, before we write the migration/storage logic. Users often need "Viewer" + "FinanceAdmin" simultaneously.

### Secret Manager Pathing
The naming convention `role-{name}` is fine, but we should prefix them with `dockmaster-` to avoid colliding with other secrets in the same GCP project (e.g., `dockmaster-role-viewer`).

---

## 5. Summary of Recommended Adjustments

1.  **Phase 2**: Implement a `force_refresh` on `KeyCache` if a token's `kid` is unknown.
2.  **Phase 4**: Ensure the `SessionStore` protocol is `async` and the in-memory implementation uses an `asyncio.Lock` for writes.
3.  **Phase 5**: Change `ServiceGrants.roles` to a list/set of roles per subject.
4.  **Phase 5**: Explicitly define the wildcard matching algorithm (recommend `fnmatch`).
5.  **Phase 6**: Add a `BOOTSTRAP_ADMINS` env var to solve the initial setup problem.
6.  **Phase 6**: Ensure `/admin/*` is gated by a specific permission (e.g., `dockmaster.admin`), not just "any logged-in user."

---

## 6. Final Verdict

The plan is **Robust** and **High-Quality**. The use of specific "Phase Specs" ensures that we don't drift into "feature creep." The decision to fix legacy bugs rather than porting them is the mark of a mature engineering team. 

If the adjustments in Section 5 are adopted, this architecture will be "Staff-Level" compliant and ready to host critical LLC infrastructure.

**Status**: PROCEED WITH CAUTION (Address Bootstrap & Multi-Role support in P5/P6).

---

## 7. MVP Scope Guardrails: Core vs. Nice-to-Have

To ensure Dockmaster ships for the LLC domain without succumbing to "Architectural Bloat," we must strictly distinguish between the **Functional Core** and **Post-MVP Optimizations**.

### The Functional Core (Do NOT Cut)
1.  **RS256 JWT Issuance & Verification**: This is the non-negotiable security primitive.
2.  **Dual-Mode Exchange**: Essential for unblocking both CLI/Service clients and browser users.
3.  **Basic RBAC (Subject -> Role -> Target/Perm)**: Without this, Dockmaster is just an OAuth proxy, not an auth service.
4.  **Bootstrap Admin Env Var**: Required to make the system operable from day one without circular lockouts.
5.  **CLI 'token' & 'test' Commands**: Essential for developer experience and verifying the RBAC engine without a UI.

### The "Nice-to-Have" (Defer if Over Schedule)
1.  **The Admin UI (HTMX)**: The CLI can handle 100% of the management tasks. The web UI is a convenience. If Phase 6 is dragging, ship the CLI first.
2.  **Redis Session Store**: As long as we run a single instance for the LLC domain, `InMemorySessionStore` is sufficient. Move Redis to Phase 7.
3.  **Detailed Audit Logging**: While a "Staff" requirement for enterprise, for the MVP, standard structured logs (`structlog`) are enough.
4.  **Advanced Wildcarding**: If complex globs are hard to implement, start with simple prefix matching (e.g., `projects/foo*`).

### Operational Guardrails
*   **"No Multi-Region yet"**: Do not spend time on distributed cache invalidation. Accept the 300s staleness for the MVP.
*   **"No Custom Auth Providers"**: Stick strictly to Google SSO. Do not add GitHub/OIDC Generic support in the first pass.
*   **"No Self-Service"**: All role assignments happen via the Admin CLI/API. Do not build "Request Access" workflows.

By adhering to these guardrails, we ensure Dockmaster provides immediate value as a secure gateway for LLC projects while keeping the implementation focused and maintainable.
