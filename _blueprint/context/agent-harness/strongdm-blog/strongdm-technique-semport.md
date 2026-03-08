---
title: "Semport"
source: https://factory.strongdm.ai/techniques/semport
parent: https://factory.strongdm.ai/techniques
---

# Semport

Semantically-aware automated ports, one-time or ongoing. Move code between languages or frameworks while preserving intent.

Semantic Ports (Semports) are an umbrella term we use for one-time or ongoing automated ports, often between languages.

## Learning from the Best

We have great examples of LLM-native designs in the wild: the Vercel AI SDK, the OpenAI Agents SDK, and others. These examples have already thought through the best loop shapes, the best tool-calling abstractions, and so on. We want to benefit from that work, automatically.

## Dependency Through Translation

Semports deliver changes from an upstream we trust into an internal library we can use. It's a form of dependency, like a traditional library, but the dependency can also be rewritten and adapted to our specific needs, automatically, while our human team members sleep.

## In Practice

Once a day we launch an automated check of openai/openai-agents-python. We find this description of agentic primitives best reflects the intended use of the OpenAI APIs. We want to include those intents and patterns in our product, however we need them in Go.

Every time our Semport process wakes, it considers the most recent commits and evaluates whether they apply to the Go implementation. It turns out there are some Python bugs that aren't expressible in Go, or were caught by the coding agent during the original port. Attractor ledgers the fix, runs the tests, tags the release.

One of the most profound aspects of Semport is how little we think about it: the OpenAI team does great work (in Python), and we receive it (in Go) and it just ... works.

> If you've read this far, we're curious: should we publish openai-agents-go and openai-agents-rust? E-mail justin@strongdm.com or DM @BuiltByJustin.

## One-Time vs. Ongoing

- **One-Time Ports** — Migrate a library from one language to another, then own the result
- **Ongoing Ports** — Continuously sync changes from upstream, merging new features automatically
- **Adaptive Ports** — Reshape APIs to match internal conventions while preserving semantics

## Why Not Just Use the Original?

Sometimes the original library is in the wrong language. Sometimes it has dependencies we can't accept. Sometimes we need to integrate deeply with internal systems. Semports let us benefit from upstream thinking without being constrained by upstream choices.
