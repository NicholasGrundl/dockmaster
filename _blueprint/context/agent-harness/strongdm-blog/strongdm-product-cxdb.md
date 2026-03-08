---
title: "CXDB"
source: https://factory.strongdm.ai/products/cxdb
repo: https://github.com/strongdm/cxdb
parent: https://factory.strongdm.ai/products
---

# CXDB

> "Self-hosted context store for AI agents. Turn DAG, blob deduplication, dynamic types, and visual debugging."

Source: [strongdm/cxdb](https://github.com/strongdm/cxdb)

## Overview

> "CXDB is a self-hosted context store for AI agents. It persists every turn of every conversation with full type awareness, branching support, and a visual debugger."

> "Observability for AI agents exists. LLM proxies exist. But what's missing is a self-hosted, inexpensive option that is 100% context- and turn-focused. CXDB fills that gap."

## The Gap

Competing solutions and their limitations:

- **LangSmith, Langfuse, Helicone** — SaaS-only with external data hosting
- **OpenTelemetry-based tools** — Built for distributed tracing, not conversations
- **LLM proxies (LiteLLM, etc.)** — Capture requests without context structure
- **Roll your own (Postgres, S3)** — Requires months of development work

## Built for LLM Conversations

Key architectural features:

- **Turn DAG** — Parent linking with O(1) forking capability
- **Blob CAS** — Content-addressed payloads with 70%+ storage reduction
- **Append Performance** — p50 < 1ms for 10KB payloads
- **Self-Hosted** — Single binary, no external dependencies

<!-- diagram: Turn DAG showing conversation branching with turns 1-3 shared, then splitting into approach A and B paths -->

## Dynamic Type System

Type registry with forward-compatible field evolution and custom renderers.

## Performance

- Append latency: p50 < 1ms, p99 < 10ms for 10KB
- Concurrent writers: Thousands
- Storage efficiency: 70%+ with Zstd + dedup
- Retrieval: Sub-ms over TB-scale datasets

## Architecture

Components:

- AI Agents (any framework/language)
- CXDB Server (Turn Store, Blob CAS, Type Registry)
- Local Storage (turns.log, blobs.pack, registry/)
- Binary Protocol (Port 9009)
- HTTP/JSON (Port 9010)

## Open Source Components

- Rust server
- Go client library
- React frontend
- Type registry
- Kubernetes manifests

License: Apache 2.0
