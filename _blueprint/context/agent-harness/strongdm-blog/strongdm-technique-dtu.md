---
title: "Digital Twin Universe (DTU)"
source: https://factory.strongdm.ai/techniques/dtu
parent: https://factory.strongdm.ai/techniques
---

# Digital Twin Universe (DTU)

Behavioral clones of the third-party services our software depends on.

We built twins of Okta, Jira, Slack, Google Docs, Google Drive, and Google Sheets, replicating their APIs, edge cases, and observable behaviors.

With the DTU, we can validate at volumes and rates far exceeding production limits. We can test failure modes that would be dangerous or impossible against live services. We can run thousands of scenarios per hour without hitting rate limits, triggering abuse detection, or accumulating API costs.

<!-- image: Behavioral clones of Okta, Jira, Google Docs, Slack, Drive, and Sheets -->

## Why DTU?

Creating a high fidelity clone of a significant SaaS application was always possible, but never economically feasible. Generations of engineers may have wanted a full in-memory replica of their CRM to test against, but self-censored the proposal to build it. They didn't even bring it to their manager, because they knew the answer would be no.

The DTU is our proof that what was unthinkable six months ago is now routine.

## Benefits

1. **High-Volume Validation** — Thousands of scenarios per hour without rate limits or API costs
2. **Dangerous Failure Modes** — Test edge cases that would be impossible against live services
3. **No Abuse Detection** — Avoid triggering security controls while stress-testing integrations
4. **Determinism** — Replayable, controlled test conditions for every scenario

## How It Works

```
Real Dependency        →  Behavioral Clone  →  Validation at Scale
(Google Drive API)        (DTU Twin)            (Unlimited scenarios)
```

The key insight is to replicate behavior at the boundary. We build test doubles from API contracts and observed edge cases, then validate them against the live dependency until we stop finding behavioral differences.
