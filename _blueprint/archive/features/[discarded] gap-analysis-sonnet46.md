# Smart Tree: /Users/nicholasgrundl/projects/dockmaster

Goal: Global view of non-_blueprint dirs, current implementation status
Recipe: scan + deep

/Users/nicholasgrundl/projects/dockmaster
├── src/                                ◆
│   └── dockmaster/                     ◆
│       ├── routes/                     ◆
│       │   ├── __init__.py             ·
│       │   └── health.py              ◆
│       ├── __init__.py                 ·
│       ├── config.py                   ◆
│       ├── logging.py                  ◇
│       ├── main.py                     ◆
│       └── py.typed                    ·
├── tests/                              ◆
│   ├── fixtures/                       ?
│   ├── __init__.py                     ·
│   ├── conftest.py                     ◆
│   ├── test_config.py                  ◆
│   └── test_health.py                  ◆
├── docs/                               ◇
│   └── GUIDE-gcp-project-setup.md     ◇
├── AGENTS.md                           ◇
├── CLAUDE.md → AGENTS.md              ·
├── DEPLOY.md                           ·
├── Dockerfile                          ·
├── justfile                            ◇
├── pyproject.toml                      ◆
├── README.md                           ·
└── uv.lock                             ×

◆ key · ◇ useful · ? uncertain · · noted · × skip
Annotations are based on filenames only, not content — treat ? items as worth a quick check.

## Annotations

- src/dockmaster/ ◆ — the entire Phase 1 scaffold lives here; only ~6 files, confirming Phase 1 is complete but
Phase 2+ not yet started
- src/dockmaster/config.py ◆ — Settings model lives here; Phase 2 will add AUTHORIZED_AUDIENCE and other env
vars
- src/dockmaster/main.py ◆ — create_app() factory; all future routes mount here
- tests/fixtures/ ? — directory exists but is empty; Phase 2 plans to add fake_sa_key.json here
- pyproject.toml ◆ — dependency management; Phase 2-6 each add new packages
- tests/conftest.py ◆ — fixture setup for all tests; critical baseline for upcoming phases

## Recommended Read Order

1. src/dockmaster/main.py — app factory, lifespan, router setup
2. src/dockmaster/config.py — current Settings model (what Phase 2 extends)
3. tests/conftest.py — existing fixture patterns to follow
4. pyproject.toml — current dependencies (baseline before Phase 2 additions)
5. justfile — dev workflow commands

## Status summary: 

Phase 1 is fully scaffolded — `src/dockmaster/` has config, logging, app factory, and a single `routes/health.py`. Tests exist for config and health. The `src/dockmaster/auth/`, `src/dockmaster/rbac/`, `src/dockmaster/sessions/`, `src/dockmaster/cli/`, and `src/dockmaster/routes/` (beyond health) directories are all absent — exactly as expected for a "Phase 1 complete, Phase 2 planned" state.



# Phase 2: JWT Infrastructure — Gap Analysis

Here's what the legacy code does that the current v2 spec either differs from or omits:


## Finding 1 — JWT signing library (informational, not a gap)

Legacy: google-auth (google.auth.crypt.RSASigner + google.auth.jwt.encode/decode)
New spec: PyJWT + cryptography
Both produce identical RS256 JWTs (same header/payload/signature format). No compatibility issue. PyJWT is better documented and has cleaner error handling. This
is fine as-is.


## Finding 2 — GET /key/{kid} auth requirement (deliberate improvement)

Legacy: Required JWT Bearer auth (enforced by before_request)
New spec: Unauthenticated (public)
This is actually a correct improvement. Consuming services need to fetch public keys to verify tokens — requiring a valid token to fetch the key is circular. The
v2 spec is right. No action needed.


## Finding 3 — RemoteKeyCache not in new spec (client library, out of scope)

Legacy: Had a RemoteKeyCache for consuming services that fetch keys from the dockmaster service via HTTP rather than hitting GCP IAM directly.
New spec: Not included.
This was part of the client library, not the service itself. The backlog already lists "Client Library / Python SDK" as a future item. No action needed for now.


## Finding 4 — ServiceAccountKeyCache.update() loads Google OIDC certs

Legacy: update() fetches two sources:
1. All user-managed SA keys in the GCP project (via IAM API enumeration)
2. Google's public OIDC signing certs from https://www.googleapis.com/oauth2/v1/certs

New spec: Only mentions "SA-issued tokens" and "Google OIDC certs" — both are captured. This is fine. But there's a subtle implementation detail: the legacy code
loads ALL service accounts in the project (not just the dockmaster SA). This is how it can verify JWTs signed by any SA in the project.


## Finding 5 — ServiceRealm missing keys property / fallback for no-kid JWTs

Legacy: When a JWT has no kid header, ServiceRealm.verify() tries ALL cached keys (passes the full {kid: pem} dict to google.auth.jwt.decode()).
New spec: Only mentions the happy path (extract kid → look up key). Silent on what happens with no kid.
Recommended: Add this to the implementation doc — try kid-specific lookup first, fall back to all keys if no kid.

## Finding 6 — ServiceUser creates a key file per-call (fixed in new design)

Legacy: Reads the SA JSON key file from disk on every token issuance — no caching.
New spec: Doesn't specify, but FastAPI's lifespan/dependency injection makes it natural to parse once at startup.
Recommended: Explicitly specify in the implementation doc that ServiceUser is initialized once at app startup (in the lifespan), not per-request.

---

# Phase 3: Token Exchange — Gap Analysis

## Finding 1 — Exchange endpoint is GET in legacy, POST in new spec

Legacy: GET /exchange?service=X with Authorization: Bearer <token>
New spec: POST /auth/exchange with Authorization: Bearer <token> + query params
The token is still in the Authorization header in both. The method change to POST makes sense for a "do something" operation. No issue — new spec is better REST design.

## Finding 2 — /auth/exchange response is missing fields vs legacy

Legacy response:
{"token": "...", "subject": "...", "service": "...", "expiry": 3600}
New spec response: same four fields. ✅ Matches.

## Finding 3 — Tokeninfo URL discrepancy (minor, already fixed in v2 spec)

Legacy: https://www.googleapis.com/oauth2/v1/tokeninfo
New spec v2 changelog: "update tokeninfo URL" — spec uses https://oauth2.googleapis.com/tokeninfo
Both work. The v2 spec already noted this fix.

## Finding 4 — MAJOR GAP: /auth/refresh response is missing Google tokens

Legacy POST /refresh response:
{
"token": "<dockmaster-jwt>",
"subject": "user@...",
"service": "lims-api",
"expiry": 3600,
"claims": {"name": ..., "picture": ...},
"id_token": "<google-id-token>",
"access_token": "<google-access-token>"
}
New Phase 4 spec response:
{"token": "<new-dockmaster-jwt>", "claims": {...}}
Legacy returns the Google id_token and access_token to the caller. This allows clients to use the Google tokens directly (e.g., call Google APIs). The new spec drops this.

## Finding 5 — MAJOR GAP: /auth/refresh client secret storage

Legacy: Client secrets stored in GCP Secret Manager as client_id-{name} secrets. The refresh endpoint fetches them at runtime.
New Phase 4 spec: "Loads client secret from Secret Manager (or config for dev)" — mentions this but gives no
detail on the secret naming convention or client_id resolution logic.

Legacy client_id normalization:
- If client_id has no .: append .apps.googleusercontent.com
- Extract part before first . → becomes the secret name suffix
- Secret ID: client_id-{part_before_first_dot}
- Example: "109370504310" → secret client_id-109370504310

## Finding 6 — MAJOR GAP: /auth/refresh uses UserInfo API for profile enrichment

Legacy: Calls GET https://www.googleapis.com/oauth2/v3/userinfo with the fresh access token to get profile claims (name, picture, etc.). This is richer than the id_token alone.
New Phase 4 spec: "Verifies returned id_token" — implies profile comes from id_token. But id_tokens from
refresh responses may have fewer claims than the UserInfo API response.

## Finding 7 — /auth/refresh request body: missing service and expiry fields

Legacy request body:
{"token": "...", "client_id": "...", "service": "lims-api", "expiry": 7200}
New Phase 4 spec request body:
{"refresh_token": "...", "client_id": "..."}
Missing service (audience for issued dockmaster JWT) and expiry fields.

---


# Phase 4: OAuth Login + Session — Gap Analysis


## Finding 1 — /auth/refresh body is incomplete in the current spec                                                         

The current Phase 4 spec has:
{"refresh_token": "...", "client_id": "<optional>"}
Legacy (and your decisions above) requires:
{"token": "...", "client_id": "<optional>", "service": "<optional>", "expiry": <optional>}
Note the field name is token in legacy, not refresh_token. Minor but worth matching.

## Finding 2 — /auth/refresh response is missing Google tokens (your decision: include them)

New spec must return:
{
"token": "<dockmaster-jwt>",
"subject": "...",
"service": "...",
"expiry": 3600,
"claims": {"name": ..., "picture": ...},
"id_token": "<google-id-token>",
"access_token": "<google-access-token>"
}

## Finding 3 — Missing GET /auth/principal endpoint

Legacy: GET /auth/principal returns the current user's profile from session as JSON. Used by SPAs/frontends to check auth status without re-rendering.
{"name": "Jane Doe", "email": "...", "picture": "..."}  // authenticated
{}  // not authenticated
New spec: Not included.

## Finding 4 — Callback route name differs

Legacy: GET /auth/authenticated (the OAuth2 callback)
New spec: GET /auth/callback
Both work. The new name is cleaner. No issue.

## Finding 5 — Post-login redirect is hardcoded in new spec

Legacy: Stored the original request path and args in session (state.path, state.args). After OAuth callback, redirected to the original URL.
New spec: Hardcodes redirect to /ui/test after callback (MVP simplification — already noted in spec).
This is a conscious MVP simplification. The backlog already notes this. Fine for now.

## Finding 6 — No email whitelist check in new spec

Legacy: AUTHORIZED config — optional list of allowed emails. If set, only those emails could log in via OAuth.
New spec: Not included. Domain check (AUTHORIZED_DOMAINS) provides broader control.
This is a deliberate simplification. Domain-level control is sufficient for the LLC use case. Fine.


# Phase 5: RBAC — Gap Analysis


## Finding 1 — Legacy loads ALL subjects' roles on a cache miss (performance issue, fixed in new spec)                      

Legacy: When Authority resolved a target (e.g., data-pipeline), it loaded all grants for that target AND resolved every subject's roles — even subjects not being queried. For a service with 50 grants, that's 50+ Secret Manager calls on first access.
New spec: TTL cache + run_in_executor wrapping. The new design is better. No gap — new spec is an improvement.

## Finding 2 — Legacy secret JSON includes a kind field not in new Pydantic models

Legacy JSON in Secret Manager:
{"kind": "Role", "name": "viewer", "permissions": ["read", "list"]}
{"kind": "ServiceGrants", "service": "lims", "grants": [{"kind": "Grant", "subject": "...", "roles": [...]}]}
New Pydantic models: No kind field.

If you're migrating existing secrets from the legacy system, the new models need to either:
- Accept and ignore kind on read (Pydantic ignores extra fields by default ✅)
- Omit kind when writing new secrets (the new models won't include it)

This means old secrets are readable by new code (extra fields ignored), but new secrets won't have kind. Legacy CLI reading new secrets would fail since it checks for kind field.

## Finding 3 — SecretsStorage needs a list_roles() and list_service_grants() method for Phase 6

Legacy: No list endpoints. Phase 6 adds GET /admin/roles and GET /admin/grants.
Required: Add list methods to SecretsStorage that enumerate secrets by prefix (role-*, service-grants-*).

## Finding 4 — Authority.has_permission() needs clear_cache() for Phase 6

New spec (Phase 6): After any CRUD write, authority.clear_cache() is called.
Authority needs a clear_cache() method. Note this in the Phase 5 implementation doc.

---

# Phase 6: RBAC Management + CLI — Gap Analysis

## Finding 1 — Legacy CLI accessed Secret Manager directly; new CLI goes through the API                                               

Legacy: python -m dockmaster used Application Default Credentials + direct SM access.
New spec: dockmaster CLI calls the dockmaster API. Documented in backlog as "Direct Secret Manager CLI Access" deferred item.
This is a deliberate architectural change. ✅

## Finding 2 — Legacy service grant used subject:role1,role2 comma-separated format

Legacy: python -m dockmaster service grant lims "sarah@co.com:pi,lab-tech" — multiple roles in one call
New spec: dockmaster service grant <service> <subject> <role> — appears to be single role per call?
The spec isn't explicit about whether multiple roles can be granted at once.

## Finding 3 — Legacy service revoke supports a wildcard * to revoke all roles

Legacy: dockmaster service revoke data-pipeline "worker@...:*" — removes the subject's entire grant
New spec: dockmaster service revoke <service> <subject> — no role arg means "revoke all" (good simplification)

## Finding 4 — Legacy CLI had YAML output format; new spec doesn't specify

Legacy: Used PyYAML for get command output. Outputs human-readable YAML.
New spec: No output format specified. JSON is more machine-friendly; YAML is more human-readable.

## Finding 5 — SecretsStorage needs list methods for GET /admin/roles and GET /admin/grants

To list all roles: enumerate secrets matching role-* prefix.
To list all service grants: enumerate secrets matching service-grants-* prefix.
GCP Secret Manager supports list_secrets with a filter.  