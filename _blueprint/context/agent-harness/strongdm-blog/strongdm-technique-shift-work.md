---
title: "Shift Work"
source: https://factory.strongdm.ai/techniques/shift-work
parent: https://factory.strongdm.ai/techniques
---

# Shift Work

Distinguishing between interactive and non-interactive system growth.

## Two Modes of Growth

We distinguish between interactive and non-interactive system growth.

### Interactive

The familiar cadence: generate, clarify, generate, approve, correct.

- Cursor, Claude Code, Codex
- Jointly evolving shared vision
- Expressing human intent into new systems

### Non-Interactive

Tasks that are already fully specified.

- Formal specifications (RFCs)
- Existing working applications
- Execution runs end-to-end once intent is complete

## Functional vs Non-Functional

Historically, software engineering distinguished between functional and non-functional specification.

### The Instagram Example

A plausible Instagram clone can be described in a few sentences of functional intent. The technical difficulty of a global, image-oriented social network lies primarily outside the functional specification: scalability, performance, availability, security, efficiency, and related properties.

## Non-Interactive Inputs

Canonical examples of non-interactive inputs include:

- **Formal Specifications** — RFC 9113 for HTTP/2, often accompanied by validation suites (h2spec, nghttp2). Spec + Test Suite = Complete Intent.
- **Existing Working Applications** — A system in an older Java dialect serves as a complete behavioral specification for reimplementation in Python.

> "An existing application constitutes an executable specification."

These cases motivated the development of reliable non-interactive coding agents, capable of operating over fully specified intent without human-in-the-loop clarification.

## Our Implementation: Attractor

Our non-interactive coding agent, designed to operate without human interaction over fully specified work.

See: [Attractor product page](https://factory.strongdm.ai/products/attractor)
