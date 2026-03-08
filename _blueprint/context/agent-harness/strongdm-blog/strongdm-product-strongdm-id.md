---
title: "StrongDM ID"
source: https://factory.strongdm.ai/products/strongdm-id
site: https://id.strongdm.ai/
parent: https://factory.strongdm.ai/products
---

# StrongDM ID

> "Identity for humans, workloads, and AI agents with federated authentication and scoped sharing."

> "Traditional identity infrastructure assumes a person in a browser. In our systems we also have workloads and agents that need to authenticate, prove identity, and receive scoped authorization."

The platform enables agents to use appropriate authentication methods to communicate with services and other agents, often leveraging SPIFFE SVIDs with cloud attestation. It provides a unified API delivering credentials, proof, and scope across OIDC, SPIFFE, and other protocols while supporting multiple token types for varying sensitivity levels.

StrongDM ID treats humans, workloads, and AI agents as first-class principals sharing one trust model, token format, and authorization framework.

## What Makes It Agentic?

- **Programmatic Onboarding** — Agents register and acquire credentials without human intervention
- **Evidence-Based Identity** — Platform attestation replaces shared secrets
- **Federated by Default** — Uses existing identity providers
- **Bootstrap Defaults** — Self-bootstrapping trust domains with auditable defaults

## Core Capabilities

- **Multi-IDP Federation** — Google, Microsoft, Apple, or OIDC-compliant providers
- **Workload Identity** — SPIFFE-compatible identity with platform attestation
- **Fine-Grained Authorization** — Cedar-based policy-as-code with attribute-based access control
- **Identity-Scoped Sharing** — Share with specific email addresses via recipients' own identity providers
