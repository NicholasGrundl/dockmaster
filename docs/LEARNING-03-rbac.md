# Learning 03: Role-Based Access Control (RBAC)

> How authorization works in Dockmaster. Covers RBAC concepts, the data model, permission resolution, and the admin API.

**Audience**: Anyone who needs to understand how Dockmaster decides who can do what.

> **Already familiar with RBAC concepts?** Skip to [2. Dockmaster's RBAC Model](#2-dockmasters-rbac-model).

---

## 1. What is RBAC?

[General introduction to Role-Based Access Control for someone who has never encountered it.]

### 1a. The Problem RBAC Solves

[Without RBAC: permissions assigned directly to users — doesn't scale, hard to audit, easy to get wrong. With RBAC: permissions assigned to roles, roles granted to subjects — manageable, auditable, principle of least privilege.]

### 1b. Core Concepts

[Define with simple examples:
- **Permission** — a specific action (e.g. "read", "experiment:approve", "admin:delete")
- **Role** — a named collection of permissions (e.g. "viewer" has read+list, "admin" has everything)
- **Subject** — who is asking (identified by email — user email or SA email)
- **Target** — what service/resource they're asking about (e.g. "data-pipeline", "nanobot")
- **Grant** — the link: "subject X has role Y on target Z"
]

### 1c. RBAC Diagram

[Mermaid entity diagram showing: Subject → (has grant) → Role → (contains) → Permission. With a concrete example: "alice@company.com has role 'editor' on service 'data-pipeline', which grants permissions 'read', 'write', 'list'".]

---

## 2. Dockmaster's RBAC Model

[How the general RBAC concepts are implemented specifically in Dockmaster.]

### 2a. Storage: GCP Secret Manager

[RBAC data lives in GCP Secret Manager as JSON secrets. Why SM: encrypted at rest, IAM-controlled access, versioned, no database needed. Trade-offs: not designed for high-frequency reads (hence caching), eventually consistent.]

### 2b. Data Model

[Two entity types stored in SM:]

#### Roles

[JSON schema: `{"name": "viewer", "permissions": ["read", "list"]}`. Secret ID pattern: `role-{name}`. One secret per role. Example roles: viewer, editor, admin.]

#### Service Grants

[JSON schema: `{"service": "data-pipeline", "grants": [{"subject": "alice@co.com", "roles": ["editor"]}, ...]}`. Secret ID pattern: `service-grants-{service}`. One secret per target service. Lists all subjects and their roles for that service.]

### 2c. Entity Relationship Diagram

[Mermaid ER diagram showing: Service Grants (1) → (*) Grant Entries → (*) Role References → (1) Roles → (*) Permissions. Show how a permission check traverses this structure.]

---

## 3. Permission Resolution

[How Dockmaster answers the question: "Does subject X have permission P on target T?"]

### 3a. The Resolution Flow

[Step by step: 1. Load service grants for target T. 2. Find grant entries for subject X. 3. Collect all role names from those entries. 4. Load each role definition. 5. Collect all permissions from those roles. 6. Check if permission P is in the collected set.]

### 3b. Resolution Flow Diagram

[Mermaid flowchart or sequence diagram showing the resolution steps with a concrete example.]

### 3c. The Authority Engine

[The Authority class orchestrates resolution. It wraps SecretsStorage with TTL-based caching to avoid hitting SM on every request. Cache TTL is configurable (default 300s). Cache is per-secret (roles cached independently from grants).]

### 3d. Caching & Performance

[Why caching matters: SM has rate limits and latency. TTL-based cache balances freshness vs performance. Cache invalidation: admin operations clear the cache after writes. In-memory only — no distributed cache (single-instance assumption for now).]

---

## 4. Admin Operations

[How roles and grants are created, updated, and deleted.]

### 4a. The Admin SA

[Admin operations use a separate service account (dockmaster-admin) with SM write permissions. The runtime SA only has read access. This separation enforces least privilege — even if the runtime SA is compromised, RBAC data can't be mutated.]

### 4b. Admin API Endpoints

[Table of admin endpoints: POST/PUT/DELETE for roles and grants. Each requires admin auth (admin email in dockmaster_admin_emails or admin session). Brief description of each operation.]

### 4c. Admin UI

[The web-based admin dashboard at /ui/. Roles page (list, create, edit, delete). Grants page (list by service, add/remove grants). Session management page. All operations go through the admin API.]

### 4d. CLI Admin Commands

[`dockmaster roles list`, `dockmaster roles create`, `dockmaster grants list <service>`, `dockmaster grants add`. How they map to the admin API.]

---

## 5. Putting It All Together

### 5a. End-to-End Example

[Walk through a complete scenario: admin creates a "viewer" role with "read" and "list" permissions. Admin grants alice@co.com the "viewer" role on service "data-pipeline". The data-pipeline service receives a request from Alice with a Dockmaster JWT. It calls GET /auth/has/alice@co.com/data-pipeline/read → true. It calls GET /auth/has/alice@co.com/data-pipeline/delete → false.]

### 5b. RBAC Decision Diagram

[Mermaid sequence diagram showing the end-to-end flow from the consuming service's perspective: receive request → extract identity from JWT → call Dockmaster permission check → allow/deny.]
