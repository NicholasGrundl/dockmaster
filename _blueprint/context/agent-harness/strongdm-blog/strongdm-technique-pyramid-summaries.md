---
title: "Pyramid Summaries"
source: https://factory.strongdm.ai/techniques/pyramid-summaries
parent: https://factory.strongdm.ai/techniques
---

# Pyramid Summaries

Reversible summarization at multiple zoom levels. Compress context without losing the ability to expand back to full detail.

Originally inspired by multi-resolution image formats (such as Pyramid TIFF) and the map tiles common to applications like Google Maps, our Pyramid Summaries allow any agent to zoom in or out on any semantic piece.

## Collapsible Detail

Concretely: "Summarize this bug report in 2 words. Now 4. Now 8. Now 16." And so on. Each level preserves the essential meaning while expanding or contracting detail as needed.

Collapsible summaries allow for rapid enumeration with less context displacement. An agent can survey hundreds of items at their 2-word level, identify the interesting ones, and expand only those.

### Examples

- **Bug Report** — "Login fails silently on Safari." (~8 words)
- **Feature Request** — "Users want bulk export." (~8 words)
- **Incident Report** — "Database failover caused 4-minute outage." (~8 words)

## Combining with MapReduce

A very common pattern we've found is to combine Pyramid Summaries with MapReduce and Clustering, using appropriate models at each stage. The net effect: a capable model with limited context can "see" much more of the terrain of a problem, then zoom in as required through tool calling.

1. **Map** — Generate pyramid summaries for each item in parallel
2. **Cluster** — Group related items by their compressed representations
3. **Reduce** — Synthesize insights across clusters, expanding detail where needed

## The Executive Parallel

The pattern mirrors how an executive drills down during a diagnostic: starting with a high-level view of the organization, then a department, then a team, and ultimately an individual, expanding detail only where the signal demands it.

> "Context windows are finite. Attention is precious. Pyramid Summaries let you see the forest and the trees, just not all at once."
