# Learning 01: Dockmaster Overview

> What Dockmaster is, who uses it, and why it exists. Introduces the core concepts, terminology, and system architecture.

**Audience**: Anyone new to Dockmaster or auth microservices in general.

> **Already familiar with OAuth, JWT, and RBAC?** Skip to [3. The Three User Types](#3-the-three-user-types).

---

## 1. The Problem

[Why does Dockmaster exist? Modern cloud systems have multiple authentication paradigms that need to coexist: browser users expect SSO, services authenticate with tokens, CLI tools need interactive login. Without a centralized auth boundary, each service implements its own auth — inconsistent, error-prone, and hard to audit. Dockmaster unifies these into a single microservice.]

### 1a. The Two Paradigms: Stateful vs Stateless

[Browser auth is stateful (sessions, cookies). Service auth is stateless (JWTs, bearer tokens). These are fundamentally different, yet both need to be trusted by downstream services. Dockmaster bridges this gap.]

### 1b. What Dockmaster Does

[One-paragraph summary: Dockmaster is an auth microservice that wraps Google OAuth/IAM, issues its own JWTs, manages sessions, and enforces RBAC. It sits at the perimeter — downstream services trust Dockmaster tokens and don't need to implement auth themselves.]

---

## 2. Terminology

[Glossary of key terms used throughout the docs. Each term gets a concise definition and a note on how it relates to Dockmaster specifically.]

### Core Concepts

[Table or definition list:
- **JWT (JSON Web Token)** — [compact signed token with claims, self-contained, stateless verification]
- **OAuth 2.0** — [authorization framework, delegates user authentication to a provider (Google)]
- **OIDC (OpenID Connect)** — [identity layer on top of OAuth, provides user info claims]
- **RBAC (Role-Based Access Control)** — [permissions assigned to roles, roles granted to subjects per service]
- **Service Account (SA)** — [non-human identity in GCP, has its own key pair for signing JWTs]
- **Claims** — [key-value pairs in a JWT (sub, iss, aud, exp, email, etc.)]
- **kid (Key ID)** — [identifier in JWT header, tells the verifier which public key to use]
- **Bearer Token** — [token sent in Authorization header, the holder is presumed authorized]
]

### Dockmaster-Specific Terms

[Table or definition list:
- **Type A Token** — [JWT signed by a GCP service account, used for service-to-service auth]
- **Type C Token** — [JWT signed by Dockmaster's ephemeral keypair, issued to users/services after authentication]
- **ServiceRealm** — [the JWT verifier — resolves kid to public key, validates signature and claims]
- **Authority** — [the RBAC engine — resolves subject + target + permission to allow/deny]
- **EphemeralKeypairSigner** — [generates RSA keypair in memory at startup, signs Type C tokens]
- **ServiceAccountSigner** — [signs with a GCP SA private key from a JSON key file]
]

---

## 3. The Three User Types

[Diagram showing the three types of clients that interact with Dockmaster, their auth mechanisms, and what they receive.]

### 3a. Browser User

[Human using a web browser. Authenticates via Google OAuth (SSO). Receives a session cookie for the Dockmaster UI, and/or a Type C JWT for API access. Use case: admin dashboard, managing roles and grants.]

### 3b. Service Account

[Non-human service (API gateway, worker, pipeline). Already has a GCP SA key. Signs its own JWT (Type A) and either uses it directly or exchanges it at Dockmaster for a Type C token with specific permissions. Use case: service-to-service API calls.]

### 3c. CLI User

[Human using the Dockmaster CLI. Authenticates via Google OAuth (browser popup), receives a Type C JWT stored locally. Use case: checking permissions, managing roles from the terminal.]

### 3d. User Types Diagram

[Mermaid diagram showing: Browser User, Service Account, CLI User → Dockmaster → downstream services. Show the different auth mechanisms (OAuth redirect, Bearer JWT, CLI redirect to localhost) and what each receives (session cookie, Type C JWT).]

---

## 4. System Architecture

[High-level view of Dockmaster and its surrounding systems.]

### 4a. Architecture Diagram

[Mermaid diagram showing: Dockmaster at center. External systems: Google OAuth, Google IAM, GCP Secret Manager. Clients: browsers, services, CLI. Data flows: OAuth redirects, JWT exchange, public key distribution, RBAC lookups. Trust boundaries marked.]

### 4b. What Dockmaster Owns

[List of responsibilities: OAuth login flow, session management, JWT issuance (Type C), JWT verification (Type A + C), public key distribution, RBAC authority, admin API.]

### 4c. What Dockmaster Delegates

[List: user authentication (→ Google OAuth), service account identity (→ GCP IAM), secret storage (→ GCP Secret Manager). Dockmaster is an orchestrator, not a credential store.]

---

## 5. Token Types

[Deep dive into the two token types and their lifecycle.]

### 5a. Type A — Service Account JWT

[Signed by GCP SA private key. Issuer is the SA email. Audience is the target service. Verified by fetching the SA's public keys from GCP IAM. Used for direct service-to-service auth. Dockmaster can also exchange these for Type C tokens.]

### 5b. Type C — Dockmaster JWT

[Signed by Dockmaster's ephemeral RSA keypair (generated at startup, lives in memory only). Issuer is "dockmaster". Contains user identity claims (email, name). Verified by fetching the public key from /auth/key/{kid}. Issued after: OAuth login, CLI login, token exchange, auth code exchange.]

### 5c. Token Lifecycle Diagram

[Mermaid diagram showing: how each token type is created, who signs it, how it's verified, and when it expires. Show the key lookup paths (GCP IAM for Type A, /auth/key/{kid} for Type C).]

### 5d. Why Two Types?

[Type A tokens are infrastructure-level (GCP native, any service can mint them). Type C tokens are application-level (Dockmaster-specific, carry user identity, scoped permissions). The exchange endpoint bridges them: present a Type A, get a Type C with the permissions you need.]
