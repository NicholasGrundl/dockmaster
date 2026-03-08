---
title: "Attractor"
source: https://factory.strongdm.ai/products/attractor
repo: https://github.com/strongdm/attractor
parent: https://factory.strongdm.ai/products
---

# Attractor

> "A non-interactive coding agent structured as a graph of phases. Runs end-to-end when the work is fully specified."

Source: [strongdm/attractor](https://github.com/strongdm/attractor)

## Graph Structure

Attractor composes models, prompts, and tools into a graph-structured pipeline designed to operate end-to-end once work specifications are complete.

The system organizes work as nodes representing development phases, each governed by a core prompt. Example nodes:

- **Implement** — "Implement the functionality"
- **Identify** — "Identify the bottleneck"
- **Optimize** — "Optimize for performance"
- **Validate** — "Verify behavioral correctness"

## Natural Language Edges

Connections between nodes use natural language evaluated by the language model, such as proceeding when bottlenecks are identified or branching based on standards compliance.

## Execution Model

The system traverses the graph until convergence or termination. Key properties:

- Deterministic execution
- Observable node transitions
- Checkpoint resumability
- Composability with other graphs

## Community Implementations

Six community-built implementations across multiple languages:

- **Kilroy** (Go) — Converts English requirements into Attractor pipelines
- **Forge** (Rust) — Multi-provider LLM client with deterministic testing
- **brynary's Attractor** (TypeScript) — DOT-syntax orchestration with HTTP API
- **anishkny's Attractor** (Python) — Handler-based architecture with Server-Sent Events
- **attractor-ruby** (Ruby) — Full-stack gem with five-step edge selection
- **samueljklee's Attractor** (Python) — Graphviz-defined workflows with conditional branching
