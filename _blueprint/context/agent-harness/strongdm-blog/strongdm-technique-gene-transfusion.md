---
title: "Gene Transfusion"
source: https://factory.strongdm.ai/techniques/gene-transfusion
parent: https://factory.strongdm.ai/techniques
---

# Gene Transfusion

Move working patterns between codebases by pointing agents at concrete exemplars.

Gene transfusion is how we move a working pattern from one codebase into another.

In its basic form, it consists of directing coding agents to concrete exemplars drawn from inside or outside the StrongDM code estate.

## Example

Identifying Caddy's Let's Encrypt integration as a reference and using it as the basis for synthesizing native Let's Encrypt support in another module.

## Pattern Propagation

Once introduced, patterns spread through a code estate. When we pair a solution with a validation-friendly exemplar, we can reproduce it in other contexts. We use this to:

- **Cross-Language Application** — Reuse patterns across languages (for example, Go to Python or TypeScript)
- **Direct Inlining** — Be inlined directly into an existing system without abstraction overhead
- **Library Embodiment** — Be embodied as a conventional library or dependency relationship

> "Gene transfusion functions as a mechanism for structure reuse without shared authorship or manual refactoring."

## The Flow

1. **Identify Exemplar** — Find working implementation (internal or external)
2. **Extract Pattern** — Agent analyzes structure, invariants, edge cases
3. **Synthesize** — Generate equivalent implementation in target context
4. **Validate** — Behavioral tests confirm equivalence
5. **Propagate** — Pattern becomes available for future transfusions

The key insight is that patterns encode solutions to recurring problems. With a working exemplar and good tests, an agent can reproduce the same behavior in a new context while adapting to local constraints.
