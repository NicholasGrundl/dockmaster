---
title: "The Filesystem"
source: https://factory.strongdm.ai/techniques/filesystem
parent: https://factory.strongdm.ai/techniques
---

# The Filesystem

Mutable, inspectable world-state. Agents navigate and contour their own context.

Early on, we observed: agents reliably build an on-disk index, write scratch state, and rehydrate context via rg/open.

## The Thought Experiment

If all you had were $HOME and vi, how would you keep track of an email you just sent, a grocery list, a Slack conversation, or compatibility constraints such as tire sizes versus rims?

## The Answer

The answer is straightforward:

- **Create directories** with meaningful names
- **Create indexes** (typically Markdown)
- **Write state** to disk

In practice this state is most often Markdown, but frequently JSON or YAML, and in specific circumstances XML.

## Genrefying

As the hierarchy of concepts evolves, it inevitably becomes unbalanced, redundant, or confusing. At that point, the corrective action is the same as for a human operator: reorganize.

> "In library science this process is called genrefying: restructuring information to optimize future retrieval."

Functionally, this resembles a familiar data-structures operation: rebalancing and reindexing. Here it is mediated by LLMs operating directly over the filesystem.

## Implications

- **Self-Organizing Context** — Agents can create and maintain their own knowledge structures as they work
- **Persistent Memory** — State survives across sessions. This makes long-running work practical across many model calls.
- **Inspectable State** — Humans can audit, modify, or reset agent state at any time
- **Composable Knowledge** — Multiple agents can share and build on the same filesystem state

The filesystem becomes a substrate for agent memory, state, and coordination. It is both an artifact store and a mutable, inspectable world-state.
