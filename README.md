# Dockmaster

Centralized authentication and authorization system for service-to-service communication on GCP.

## What It Does

Dockmaster is composed of two components:

1. **Python client library** (`dockmaster/`) — Issues and verifies JWTs using GCP service account keys, provides OAuth2 browser login middleware, and enforces RBAC permissions stored in GCP Secret Manager.

2. **FastAPI microservice** — The centralized token mint and RBAC authority. Exchanges Google OAuth/access tokens for internally-signed Dockmaster JWTs, serves public keys for distributed verification, and exposes RBAC permission checks over HTTP.

## Core Capabilities

| Capability | Description |
|---|---|
| JWT Issuance | Sign JWTs using GCP service account private keys |
| JWT Verification | Verify JWTs against cached public keys (GCP IAM + Google OIDC) |
| Token Exchange | Exchange Google JWTs or access tokens for Dockmaster JWTs |
| Refresh Token Flow | Exchange Google refresh tokens for Dockmaster JWTs with profile enrichment |
| RBAC | Role/permission model backed by GCP Secret Manager, exposed via HTTP |
| Public Key Distribution | Serve public keys at `/key/{kid}` for decentralized verification |
| Google SSO | OAuth2 browser login with server-side sessions |
| CLI | Manage roles, grants, and test permissions from the command line |

## Architecture

```
Browser User ──OAuth login──▶ Dockmaster Service ──▶ Google OAuth2 / IAM APIs
                                    │                         │
Service Account ──Bearer JWT──▶ Consuming Service     GCP Secret Manager
                                    │                   (RBAC storage)
                              Fetch /key/{kid}
                              Check /has/{s}/{t}/{p}
```

**Key flows:**
- **Service-to-service**: A service mints a JWT with its SA key and sends it directly. The receiver verifies against cached public keys from GCP IAM.
- **Browser OAuth**: User authenticates via Google, gets a Dockmaster JWT, uses it to call backend services.
- **Token exchange**: Client with a Google token exchanges it for a Dockmaster JWT at `/exchange`.
- **RBAC checks**: Services call `/has/{subject}/{target}/{permission}` to check permissions.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [just](https://github.com/casey/just) (command runner)

### Install

```bash
just install
```

### Run Dev Server

```bash
just dev
```

### Environment Variables

Create a `.env` file with your Google OAuth2 credentials:

```env
CLIENT_ID=your-google-oauth-client-id
CLIENT_SECRET=your-google-oauth-client-secret
```

See [DEPLOY.md](DEPLOY.md) for the full environment variable reference.

## Development

```bash
just install       # Install all deps (including dev)
just test          # Run tests
just lint          # Lint with ruff (auto-fix)
just format        # Format with ruff
just typecheck     # Type check with ty
just check         # Run all checks (lint + format + typecheck + test)
just build         # Build wheel
just version       # Show current version
just version 0.2.0 # Set version
just publish       # Publish preflight (dry run)
just publish now   # Tag and push
```

## Project Structure

```
.
├── src/dockmaster/       Source code (Python package)
├── tests/                Test suite
├── _blueprint/           Planning docs, specs, and reference material
│   ├── features/         Implementation specs
│   │   └── planning/     Feature planning documents
│   ├── roadmap/          ROADMAP and backlog
│   └── context/          Reference codebases and legacy source
├── pyproject.toml        Package config (hatchling + ruff + pytest)
├── justfile              Development recipes
├── Dockerfile            Multi-stage uv-based container build
├── DEPLOY.md             Deployment guide
└── uv.lock               Locked dependency versions
```

## Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| Data Validation | Pydantic v2 |
| Configuration | pydantic-settings |
| JWT | python-jose (RS256 via GCP SA keys) |
| OAuth2 | Authlib |
| GCP Auth | google-auth, google-api-python-client |
| RBAC Storage | google-cloud-secret-manager |
| HTTP Client | httpx |
| CLI | Click |
| Build | hatchling + uv |
| Linting | ruff |
| Type Checking | ty |
| Testing | pytest + pytest-asyncio |

## License

Apache License 2.0
