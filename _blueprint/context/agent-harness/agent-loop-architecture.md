# Agent Loop Architecture

> Planning doc for Kit's agent loop, planning system, and orchestration layer.

**Status**: Planning
**Phase**: 2–3
**Last updated**: 2026-02-14

---

## Inform

### Case Study: Claude Code's "Blueprint Reorg" Session

Reconstructed from the memory dump in `_blueprint/context/claude-code-memory/`.
This was a real Claude Code session on `pi-agent` — the same repo we're in now.
It illustrates the three-phase agent loop: **explore → plan → execute**.

Source files: `plans/melodic-coalescing-wadler.md`, `tasks/1-6.json`,
`projects/.../*.jsonl` (262-line session log).

#### Phase 1: Explore (conversation, ~115 inner-loop turns)

The user opened with a broad goal and explicit instructions to work cooperatively:

> "Let's work together to make some clean roadmap planning docs and individual
> feature docs. There is a lot of content and ideas here but unfleshed out.
> Work as a cooperative thought partner with me."

The user gave the agent three concrete first-moves:
1. Search `_blueprint/roadmap` and `_blueprint/features` to surface documents
2. Inspect the repo's CLAUDE.md and README for onboarding quality
3. Surface findings with recommendations for the user to comment on

The agent then ran extensive autonomous exploration — file reads, glob searches,
content analysis — across ~115 assistant/tool-call turns with zero user input.
This is the "inner loop": the agent cycling through `LLM → tool call → result →
LLM` without returning to the user.

#### Phase 1b: Clarify (2 rounds of questions)

After exploring, the agent surfaced decisions via `AskUserQuestion` (a structured
multi-choice tool, not free-text). Two rounds:

**Round 1** (3 questions):
- *TODO format?* → User chose "single flat list"
- *What to do with scattered content?* → User gave a longer answer redefining
  the `roadmap/` vs `features/` distinction and asking for help rethinking it
- *Clean up stubs?* → "Yes, include cleanup"

**Round 2** (2 questions):
- *Where should kit-soul.md and kit-MEMORY.md live?* → User chose
  `agents/nanobot/` and discussed backup strategy
- *Consolidate all items or just future?* → "Consolidate everything" + pointed
  the agent at a draft `_blueprint/CLAUDE.md` to incorporate

Total user messages across the entire session: **4**. The agent did the vast
majority of work autonomously, only surfacing when it needed human decisions.

#### Phase 2: Plan (plan file generation)

After clarification, the agent wrote a structured plan to
`plans/melodic-coalescing-wadler.md` (randomly generated name). The plan had:

- **Context block**: one paragraph summarizing the problem
- **Goal statement**: one sentence
- **7 numbered steps**, each with:
  - Description of what to do
  - Specific commands (e.g. `git mv` paths)
  - List of files affected
  - Acceptance criteria where relevant
- **Verification checklist** at the end (6 items)

The plan was presented to the user for approval before any execution began.
This is the "plan gate" — the human-in-the-loop checkpoint between planning
and execution.

#### Phase 3: Execute (task decomposition + work)

Upon approval, the plan was decomposed into **6 tasks** stored as individual
JSON files (`tasks/1.json` through `tasks/6.json`):

| # | Task | Status |
|---|---|---|
| 1 | Move agent identity files to `agents/nanobot/` | completed |
| 2 | Move and split feature specs into `_blueprint/features/` | in_progress |
| 3 | Create master TODO.md | pending |
| 4 | Create `_blueprint/AGENTS.md` and symlinks | pending |
| 5 | Create root CLAUDE.md | pending |
| 6 | Update all cross-references | pending |

Each task JSON had: `id`, `subject`, `description`, `activeForm` (present
participle for UI display), `status`, `blocks`, `blockedBy`.

The session captured here ended mid-execution (task 2 in progress). The user
gave one course correction during execution: "skip the backups part, add it
to the TODO list" — demonstrating the human-in-the-loop pattern during
execution, not just at the plan gate.

#### Observations

1. **Conversation-to-plan ratio**: ~115 inner-loop turns of exploration +
   4 user messages → 1 plan file + 6 tasks. The planning phase is expensive
   in agent compute but cheap in human attention.

2. **Structured questions, not free-text**: The agent used `AskUserQuestion`
   with predefined choices, reducing user effort. The user could override
   with free-text when the choices didn't fit (and did, twice).

3. **Plan as contract**: The plan file served as a shared artifact — the user
   could review, approve, or reject before any files were touched.

4. **Task state machine**: `pending → in_progress → completed`. Only one task
   `in_progress` at a time. Simple, linear, no parallelism in this session.

5. **The todo list was empty**: The `todos/*.json` file contained `[]`. The
   task system (`tasks/`) and todo system (`todos/`) appear to be separate
   mechanisms — tasks are plan-derived, todos are ad-hoc progress tracking.

---

### Codex: Agent Loop Internals and Harness Engineering

Synthesized from three OpenAI engineering posts (see Resources below):
Bolin on the core agent loop, Lopopolo on harness engineering at scale,
and Chen on the App Server protocol. Where the Claude Code case study
above traced a single session, this section extracts architectural patterns
across Codex's design as a system.

#### The Core Loop

Codex runs the same fundamental cycle as Claude Code's inner loop:
**prompt assembly → model inference → tool call → repeat**. Termination
occurs when the model emits an assistant message instead of a tool call,
signaling that control returns to the user.

Each user-initiated exchange is a **turn**. Within a single turn, the model
may issue many tool calls (potentially hundreds), each appended to the
growing input before the next inference call. The agent does not return to
the user between tool calls — the inner loop runs autonomously until the
model decides it has enough information to respond or ask a clarifying
question.

Codex ships two built-in tools:

- **`shell`**: spawns a process in a sandboxed environment with configurable
  file permissions and network access. The sandbox policy is communicated to
  the model via a `role=developer` message in the prompt, not enforced by
  the tool schema itself.
- **`update_plan`**: a structured planning tool the model can invoke to
  record and revise a task plan mid-turn. Takes a `plan` (text) and optional
  `explanation` for why the plan changed. This gives the model a way to
  externalize its reasoning about task decomposition as a tool call rather
  than as prose in the assistant message.

Additional tools come from the Responses API (e.g., `web_search`) or from
user-configured MCP servers. The tool list is declared in the initial API
request and must remain stable throughout the conversation to preserve
prompt caching (see below).

#### Prompt Assembly and Context Management

The prompt is constructed from multiple sources, layered by priority.
Each source is assigned a **role** that determines its weight during
inference (in decreasing priority): `system`, `developer`, `user`,
`assistant`.

The initial prompt is built from these components in order:

1. **System message** (server-controlled): set by the Responses API server,
   not the client.
2. **Tool definitions**: the full JSON schema for every tool available to
   the model. Tool order must be deterministic — an early bug where MCP
   tools were enumerated in inconsistent order caused expensive cache misses.
3. **Instructions** (`role=developer`): model-specific instructions bundled
   into the CLI (e.g., `gpt-5.2-codex_prompt.md`), overridable via config.
4. **Sandbox policy** (`role=developer`): describes file permissions, network
   access, and when to ask the user for approval.
5. **Developer instructions** (`role=developer`, optional): user-specified
   via `config.toml`.
6. **User instructions** (`role=user`, optional): aggregated from `AGENTS.md`
   files at multiple directory levels — global (`$CODEX_HOME`), then each
   directory from the git root to the cwd. More specific instructions appear
   later. Skills metadata is appended here if configured.
7. **Environment context** (`role=user`): current working directory and shell.
8. **User message**: the actual task or question.

This ordering is not arbitrary — it is driven by **prompt caching**. The
Responses API caches computation for exact prefix matches. By placing static
content (system message, tools, instructions) at the beginning and dynamic
content (user messages, tool outputs) at the end, subsequent inference calls
within a turn reuse the cached prefix. When caching hits, the cost model
shifts from quadratic to linear in the number of inner-loop iterations.

Cache misses are triggered by anything that changes the prefix: modifying
the tool list mid-conversation, switching models, or changing sandbox
configuration. When mid-conversation changes are unavoidable (e.g., the
user changes the cwd), Codex **appends** a new message to the input rather
than mutating an earlier one, preserving the cached prefix.

**Compaction** handles the other resource constraint: the finite context
window. As the conversation grows (especially across many tool calls within
a turn), the prompt can exhaust the model's context window. Codex's
solution evolved in three stages:

1. Manual: the user invokes `/compact`, which queries the model with custom
   summarization instructions and replaces the input with the summary.
2. Automatic: when token count exceeds a configurable threshold
   (`auto_compact_limit`), compaction triggers without user intervention.
3. Server-side: a dedicated `/responses/compact` endpoint returns a reduced
   input list including an opaque `encrypted_content` item that preserves
   the model's latent understanding of the original conversation — not just
   a textual summary, but a compressed representation the model can use
   for continuity.

The key design tradeoff: Codex sends the **full input** on every API call
(no `previous_response_id` for server-side state). This keeps requests
stateless and supports zero-data-retention configurations, but means the
JSON payload grows quadratically across inner-loop iterations. Prompt
caching and compaction together mitigate this cost.

#### Conversation Primitives and State

Codex structures conversations around three nested primitives:

- **Item**: the atomic unit of input/output. Typed (user message, agent
  message, tool execution, approval request, diff). Each item has an
  explicit lifecycle: `item/started` → optional `item/*/delta` (streaming) →
  `item/completed`. This lifecycle enables clients to render incrementally.
- **Turn**: one unit of agent work initiated by user input. Contains a
  sequence of items representing intermediate steps and outputs. Begins
  when the client submits input, ends when the agent finishes producing
  outputs for that input.
- **Thread**: the durable container for an ongoing conversation. Contains
  multiple turns. Threads can be created, resumed, forked, and archived.
  History is persisted so clients can reconnect and render a consistent
  timeline.

This is a more formal state model than Claude Code's file-based approach
(plan files + task JSONs + session logs). The Item/Turn/Thread hierarchy
defines clear lifecycle boundaries, making it straightforward to implement
features like reconnection, forking, and multi-agent orchestration.

The approval flow illustrates how the primitives interact with
human-in-the-loop control: during a turn, the server can emit an
approval-request item, **pause the turn**, and wait for the client to
respond with "allow" or "deny" before the agent loop continues. This is
the equivalent of Claude Code's plan gate, but at the granularity of
individual tool calls rather than whole plans.

#### Repository as Agent Interface

One of the strongest patterns from the Codex engineering experience is
the treatment of the repository itself as the primary interface for agent
work. The principle: **if it isn't in the repo, it doesn't exist to the
agent.** Knowledge in Slack threads, Google Docs, or people's heads is
invisible.

This led to a specific stance on `AGENTS.md`: treat it as a **table of
contents, not an encyclopedia**. The team tried a monolithic AGENTS.md
and found predictable failure modes:

- **Context crowding**: a giant instruction file displaces the actual task
  and relevant code from the context window.
- **Non-guidance**: when everything is marked "important," the agent
  pattern-matches locally instead of navigating intentionally.
- **Rot**: a monolithic file becomes a graveyard of stale rules that agents
  can't distinguish from current ones.
- **Unverifiability**: a single blob doesn't lend itself to mechanical
  checks for coverage, freshness, or cross-linking.

The alternative: a short AGENTS.md (~100 lines) that points to a structured
knowledge store:

```
docs/
├── design-docs/       # Catalogued, indexed, with verification status
├── exec-plans/        # Active plans, completed plans, tech debt tracker
│   ├── active/
│   └── completed/
├── generated/         # Machine-generated docs (e.g., DB schema)
├── product-specs/     # Feature specifications
└── references/        # LLM-friendly reference docs for dependencies
```

This enables **progressive disclosure**: the agent reads a small, stable
entry point and navigates to deeper sources on demand, rather than being
front-loaded with everything. User instructions in Codex are aggregated
from `AGENTS.md` files at each directory level (global → project root →
cwd), reinforcing this layered approach.

Plans are treated as **first-class versioned artifacts** checked into the
repo. Ephemeral plans for small changes, full execution plans with progress
and decision logs for complex work. Active, completed, and known technical
debt are co-located so agents can operate without external context.

The team also found that technology choices matter for agent legibility.
"Boring" technologies — composable, API-stable, well-represented in
training data — are easier for agents to model. In some cases, reimplementing
a subset of functionality was cheaper than working around opaque upstream
behavior from external libraries.

#### Enforcing Coherence Without Human Review

At high throughput (1,500 PRs across 5 months, 3 engineers), conventional
code review becomes a bottleneck. The team's response: encode quality
standards mechanically rather than relying on human review.

**Architectural enforcement**: the codebase is organized around a rigid
layering model. Each business domain follows a fixed dependency direction
(Types → Config → Repo → Service → Runtime → UI). Cross-cutting concerns
(auth, telemetry, feature flags) enter through a single explicit interface.
These constraints are enforced by custom linters and structural tests, not
by convention or review comments.

**Taste invariants**: a small set of opinionated mechanical rules that
preserve stylistic coherence — structured logging, naming conventions for
schemas and types, file size limits, platform-specific reliability
requirements. Critically, the linter error messages are written as
**remediation instructions for the agent**, not diagnostic messages for
humans. The error message itself becomes context injection.

**Entropy and garbage collection**: agent-generated code replicates existing
patterns, including suboptimal ones. Without intervention, drift accumulates.
The team initially spent 20% of each week manually cleaning up. The
scalable solution: "golden principles" encoded in the repo, plus recurring
background agents that scan for deviations, update quality grades, and
open targeted refactoring PRs. Most cleanup PRs can be reviewed in under
a minute and automerged. This functions as continuous garbage collection —
paying down technical debt in small increments rather than letting it
compound.

**Agent-to-agent review**: the workflow pushes review responsibility from
humans to agents. An engineer instructs Codex to review its own changes
locally, request additional agent reviews (both local and cloud), respond
to feedback, and iterate until all reviewers are satisfied. Humans may
review but aren't required to.

#### The Harness as Shared Infrastructure

Codex runs across five surfaces — CLI, VS Code extension, JetBrains/Xcode
IDEs, web app, and macOS desktop app — all powered by the same agent loop.
The architectural enabler is the **App Server**: a long-lived process that
hosts the agent core and exposes it via a bidirectional JSON-RPC protocol
over stdio (JSONL framing).

The App Server has four components:

1. **Stdio reader**: reads JSON-RPC requests from the client.
2. **Message processor**: translates client requests into core operations
   and transforms internal events into stable, UI-ready notifications.
3. **Thread manager**: spins up one core session per thread.
4. **Core threads**: the actual agent loop instances.

Integration patterns vary by surface:

- **Local apps/IDEs**: bundle a platform-specific App Server binary, launch
  as a child process, keep a bidirectional stdio channel open.
- **Web**: a worker provisions a container with the workspace, launches the
  App Server inside it, and maintains a long-lived channel. The browser
  talks to a backend over HTTP/SSE. State lives on the server so work
  continues if the tab closes.
- **CLI/TUI**: historically a special case (direct Rust core access), being
  refactored to use the App Server like any other client.

The key design decision: the protocol is backward-compatible, so older
clients can talk to newer servers. This decouples release cycles between
the agent core and its surfaces. The App Server started as a pragmatic
hack to reuse the harness in VS Code and evolved into the standard
integration protocol — a pattern where internal needs drove API design.

#### Observations

1. **Same fundamental loop, different state management.** Both Claude Code
   and Codex run the same core cycle: prompt → inference → tool call → loop,
   terminating on assistant message. The divergence is in how state is
   managed. Claude Code uses file-based artifacts (plan files, task JSONs,
   session logs). Codex uses API-level primitives (Items/Turns/Threads)
   with server-side persistence and an opaque encrypted state for reasoning
   continuity.

2. **Prompt caching shapes architecture.** The "static prefix, dynamic
   suffix" constraint is not a minor optimization — it's a structural
   decision that affects how every feature is built. Any change to the
   prompt prefix (tool list, instructions, sandbox config) causes an
   expensive cache miss. This pressure keeps the prompt stable and pushes
   dynamic content to the end.

3. **Compaction is the universal answer to finite context.** Both systems
   face the same fundamental problem: the prompt grows with every tool call,
   and context windows are finite. Both converge on summarization/compaction.
   Codex's evolution (manual → automatic → server-side with encrypted
   latent state) shows the maturation path.

4. **AGENTS.md as map, not manual.** The failure modes of monolithic
   instruction files are well-documented here: context crowding, rot,
   non-guidance, unverifiability. The alternative — a short entry point
   with pointers to deeper structured docs — is the progressive disclosure
   pattern. This validates treating `AGENTS.md` as a table of contents
   with layered knowledge stores behind it.

5. **Plans as versioned artifacts.** Both systems treat plans as first-class
   objects. Claude Code writes plan files that serve as contracts for user
   approval. Codex checks execution plans into the repo with progress and
   decision logs. In both cases, the plan is a shared artifact between
   human and agent, not ephemeral reasoning.

6. **Entropy is inevitable; garbage collection is required.** Agent-generated
   code replicates existing patterns, including bad ones. Without mechanical
   enforcement (linters, structural tests) and continuous cleanup (recurring
   agents that scan for drift), quality degrades. The "golden principles"
   pattern — encode taste once, enforce continuously — is the scalable
   alternative to manual review.

7. **Mechanical enforcement over review.** Custom linters with
   agent-targeted error messages, structural tests for dependency
   directions, and automated quality scoring replace human code review
   as the primary quality mechanism. The error message becomes a form of
   context injection — the linter is teaching the agent how to fix the
   problem.

8. **Harness decoupling enables surface flexibility.** One agent loop
   powering multiple UIs (CLI, IDE, web, desktop) via a stable protocol
   is an architectural pattern worth noting. The App Server emerged from
   practical need (reusing the harness in VS Code) rather than upfront
   design, but the resulting separation of agent core from presentation
   layer enables independent evolution of both.

---

### StrongDM: The Software Factory and Non-Interactive Development

Synthesized from StrongDM's Software Factory site, twelve technique and
product pages, and Justin McCarthy's manifesto (see Resources below). Where
the Claude Code and Codex sections above trace systems designed around
human-in-the-loop collaboration, StrongDM's thesis is the elimination of
human involvement from the code-write-review cycle entirely. A three-person
team (founded July 2025) building production software where no human writes
or reviews code. The techniques they developed to make that work —
validation architecture, agent memory patterns, context management, pattern
propagation — are largely separable from that thesis and applicable to
systems that retain human oversight.

Source files: `_blueprint/roadmap/planning/resources/strongdm-*.md`
(12 documents covering the manifesto, principles, six techniques, three
products, and the weather report).

#### Philosophy: Grown Software

The manifesto states two rules:

1. Code **must not be** written by humans.
2. Code **must not be** reviewed by humans.

And a litmus test: "if you haven't spent at least $1,000 on tokens today
per human engineer, your software factory has room for improvement."

The catalyst was a behavioral shift observed in late 2024: with Claude 3.5
Sonnet (October 2024 revision), long-horizon agentic coding workflows began
to **compound correctness** rather than compound error. Prior to this,
iterative LLM application to coding tasks accumulated misunderstandings,
hallucinations, DRY violations, and library incompatibilities until the
codebase "collapsed." After the threshold, agents could sustain and build
on their own work across extended sessions.

This led to a distinction between two modes of system growth, which they
call **shift work** (`strongdm-technique-shift-work.md`):

- **Interactive**: the familiar cadence of generate → clarify → approve →
  correct. Cursor, Claude Code, and Codex operate here. Human and agent
  jointly evolve a shared vision.
- **Non-interactive**: tasks where intent is already fully specified —
  formal specifications (RFCs with validation suites), existing working
  applications (an old Java system as executable spec for a Python rewrite).
  Agents run end-to-end without human-in-the-loop clarification.

The team advocates **deliberate naivete**: systematically questioning
assumptions inherited from the pre-agent era about what's economically
feasible. Building a full in-memory behavioral clone of Okta was always
*possible* but would have been dismissed without discussion in a traditional
engineering org. Agents change the cost calculus.

#### The Core Loop: Seed → Validation → Feedback

The fundamental architecture (`strongdm-principles.md`) is a convergence
loop, not a planning pipeline:

```
Seed (spec, screenshot, existing codebase)
  ↓
  ┌──→ Agent generates / modifies code
  │         ↓
  │    Validation harness evaluates
  │         ↓
  │    Feedback (sample of output fed back as input)
  │         ↓
  └──── Loop until holdout scenarios pass and stay passing
```

This differs structurally from Claude Code's **explore → plan → execute**
and Codex's **prompt → inference → tool call → loop**. There is no explicit
planning phase — the seed *is* the plan, and convergence happens through
iteration rather than task decomposition. The loop terminates not when the
model emits an assistant message, but when an external validation criterion
is met: holdout scenarios pass and remain passing.

**Tokens as fuel.** Every obstacle is reframed as a conversion problem:
"how can we represent this in a form the model can understand?" The inputs
they list include traces, screen captures, conversation transcripts,
incident replays, adversarial use, agentic simulation, just-in-time
surveys, customer interviews, and price elasticity testing. The pattern is
aggressive context enrichment — when the agent is stuck, add more signal,
not more instructions.

#### Technique: Scenarios and Satisfaction

The team found conventional tests insufficient for agent-generated code,
for two reasons (`strongdm-story.md`):

1. **Tests are too rigid.** When the software itself contains LLM
   components, success is probabilistic. Boolean pass/fail doesn't capture
   "works 94% of the time."
2. **Tests can be reward-hacked.** An agent optimizing to pass narrowly
   written tests will find shortcuts (`return true`). Tests stored in the
   codebase are accessible to the generating agent and can be lazily
   rewritten to match the code.

Their response was a progression through three levels of validation:

**Tests → Scenarios → Satisfaction**

- **Scenarios** replace "tests" as the validation primitive. A scenario is
  an end-to-end user story, often stored *outside the codebase* — analogous
  to a holdout set in model training. The agent cannot access or rewrite
  them during generation.
- **Satisfaction** replaces boolean pass/fail. It quantifies: "of all
  observed trajectories through all scenarios, what fraction likely satisfy
  the user?" This is a probabilistic, empirical metric evaluated by
  LLM-as-judge.

The holdout set pattern is architecturally significant. By keeping scenarios
external to the codebase, the validation harness maintains independence
from the generation process — the same principle that prevents data leakage
in ML evaluation. Neither Claude Code nor Codex have an equivalent
mechanism; both rely on in-repo tests and linters that the agent can see
and potentially game.

#### Technique: Digital Twin Universe (DTU)

The Digital Twin Universe (`strongdm-technique-dtu.md`) is a set of
behavioral clones of the third-party services StrongDM's software depends
on: Okta, Jira, Slack, Google Docs, Google Drive, and Google Sheets.

**How it works.** Each twin replicates behavior at the API boundary — built
from API contracts and observed edge cases. The twin is validated against
the live dependency until behavioral differences stop appearing. This is
boundary-level replication, not full reimplementation: the twin matches
observable behavior, not internal architecture.

**Why it matters for validation:**

- **Volume**: thousands of scenarios per hour without rate limits or API
  costs
- **Dangerous failure modes**: test edge cases impossible against live
  services
- **Determinism**: replayable, controlled test conditions
- **No abuse detection**: stress-test integrations without triggering
  security controls

**The economic argument.** Building a high-fidelity clone of a SaaS
application was always possible but never proposed — engineers self-censored
because they knew the answer would be "no." With agents doing the
implementation, the cost calculus shifts. This is the deliberate naivete
principle in action.

The DTU is what makes the scenario/satisfaction validation loop practical
at scale. Without it, running thousands of end-to-end scenarios per hour
against real Okta and Jira would be rate-limited, expensive, and potentially
dangerous.

*At Pi scale, the DTU pattern is worth noting as a principle — mock your
dependencies at the boundary — even if building full behavioral clones of
Gmail and Google Calendar would be disproportionate. A lightweight variant
(a mock Gmail API that replays recorded responses) captures the core
benefit at lower cost.*

#### Technique: Filesystem as Agent Memory

StrongDM observed (`strongdm-technique-filesystem.md`) that agents reliably
build on-disk organization when given filesystem access: creating
directories with meaningful names, writing Markdown indexes, persisting
state as Markdown/JSON/YAML, and rehydrating context via `rg` and file
reads.

Their framing uses a thought experiment: "if all you had were `$HOME` and
`vi`, how would you keep track of an email you just sent, a grocery list,
compatibility constraints like tire sizes versus rims?" The answer —
directories, indexes, written state — is what agents naturally do when
given a filesystem.

**Genrefying.** As the agent's on-disk hierarchy evolves, it becomes
unbalanced, redundant, or confusing. The corrective action is
reorganization — what library science calls "genrefying": restructuring
information to optimize future retrieval. StrongDM treats this as a
data-structures operation (rebalancing and reindexing) mediated by LLMs
operating directly over the filesystem.

**Properties of filesystem-as-memory:**

- **Self-organizing**: agents create and maintain their own knowledge
  structures as they work
- **Persistent**: state survives across sessions, enabling long-running
  work across many model calls
- **Inspectable**: humans can audit, modify, or reset agent state at any
  time
- **Composable**: multiple agents can share and build on the same
  filesystem state

This validates the approach already in use for Kit — `kit-MEMORY.md` and
the `_blueprint/` directory structure are filesystem-based agent memory.
The genrefying pattern suggests a concrete addition: periodic LLM-mediated
reorganization of accumulated state, rather than letting it grow unbounded.

#### Technique: Pyramid Summaries

Multi-resolution summarization (`strongdm-technique-pyramid-summaries.md`)
inspired by pyramid TIFF image formats and map tiles. The core operation:
"Summarize this bug report in 2 words. Now 4. Now 8. Now 16." Each level
preserves essential meaning while expanding or contracting detail.

**Why it matters for agents.** Collapsible summaries allow rapid
enumeration with less context displacement. An agent can survey hundreds of
items at their 2-word level, identify the interesting ones, and expand only
those — progressive disclosure applied to context management.

**Combined with MapReduce and clustering:**

1. **Map** — generate pyramid summaries for each item in parallel
2. **Cluster** — group related items by their compressed representations
3. **Reduce** — synthesize insights across clusters, expanding detail
   where needed

The parallel to an executive drill-down is explicit: start with the
org-level view, narrow to a department, then a team, then an individual,
expanding detail only where the signal demands it.

**Contrast with Codex's compaction.** Codex's compaction (manual →
automatic → server-side with encrypted latent state) is *lossy* — once
compacted, the original detail is gone. Pyramid summaries are *reversible*:
the full-detail version still exists, and the agent can zoom back in at any
time. The tradeoff is storage — pyramid summaries require maintaining
multiple resolution levels — while compaction discards to reclaim context
window space.

*This pattern is scale-independent. Even with a small context window,
pyramid summaries of email threads, conversation histories, or task
backlogs would let Kit survey more terrain before committing context to a
specific item.*

#### Technique: Gene Transfusion

Moving working patterns between codebases
(`strongdm-technique-gene-transfusion.md`) by pointing agents at concrete
exemplars. The metaphor is biological: a working implementation is a "gene"
that can be transplanted into a new host.

**The flow:**

1. **Identify exemplar** — find a working implementation (internal or
   external). Example: Caddy's Let's Encrypt integration as reference for
   synthesizing native Let's Encrypt support in another module.
2. **Extract pattern** — agent analyzes structure, invariants, edge cases
3. **Synthesize** — generate equivalent implementation in target context
4. **Validate** — behavioral tests confirm equivalence
5. **Propagate** — pattern becomes available for future transfusions

**Application modes:**

- **Cross-language**: reuse patterns from Go in Python or TypeScript
- **Direct inlining**: embed into an existing system without abstraction
  overhead
- **Library embodiment**: wrap as a conventional dependency

The key insight: patterns encode solutions to recurring problems. With a
working exemplar and good tests, an agent can reproduce behavior in a new
context while adapting to local constraints. Once introduced, patterns
spread through a code estate — each successful transfusion creates a new
exemplar for future use. This is structure reuse without shared authorship
or manual refactoring. It differs from copy-paste or library dependency:
the agent *understands* the exemplar well enough to adapt it, not just
duplicate it.

*Directly relevant to Kit's development workflow. When implementing a new
capability (e.g., a ReAct loop), pointing the agent at a reference
implementation in another project and saying "transplant this pattern" is
the gene transfusion technique in practice.*

#### Technique: Semports (Semantic Ports)

Automated, ongoing translation of upstream libraries
(`strongdm-technique-semport.md`) between languages or frameworks while
preserving semantic intent. One-time or continuous.

**In practice.** StrongDM runs a daily automated check of
`openai/openai-agents-python`. They find this SDK best reflects the
intended use of the OpenAI APIs, but need the functionality in Go. Each
time the semport process wakes, it evaluates recent upstream commits,
determines which changes apply to the Go implementation, handles
language-specific differences (some Python bugs aren't expressible in Go,
or were already caught during the original port), runs tests, and tags a
release.

**Variants:**

- **One-time**: migrate a library from one language to another, then own
  the result
- **Ongoing**: continuously sync upstream changes, merging new features
  automatically
- **Adaptive**: reshape APIs to match internal conventions while preserving
  semantics

**Why not just use the original?** Wrong language, unacceptable
dependencies, or need for deep integration with internal systems. Semports
capture upstream *thinking* without being constrained by upstream *choices*.

The technique depends on the same validation infrastructure — scenarios and
tests confirm that the ported version preserves behavior. The one-time
variant is essentially gene transfusion across a language boundary; the
ongoing variant adds continuous synchronization.

*The ongoing variant is the most novel — treating upstream libraries as
living specifications continuously consumed in a different language. This
requires substantial automation infrastructure and token budget, more
applicable at enterprise scale. The one-time variant (port a reference
implementation once, validate, own the result) is broadly useful and
low-cost.*

#### Graph-Structured Execution: Attractor

Attractor (`strongdm-product-attractor.md`) is StrongDM's non-interactive
coding agent, structured as a graph of phases rather than a linear task
list. The repo (`strongdm/attractor`) is pure markdown specs with zero
code — the specification *is* the product, with six community
implementations across Go, Rust, TypeScript, Python, and Ruby.

**Graph structure.** Work is organized as nodes representing development
phases, each governed by a core prompt:

- **Implement** — "Implement the functionality"
- **Identify** — "Identify the bottleneck"
- **Optimize** — "Optimize for performance"
- **Validate** — "Verify behavioral correctness"

**Natural-language edges.** Connections between nodes use natural-language
predicates evaluated by the LLM — e.g., proceed when bottlenecks are
identified, branch based on standards compliance. The model decides when
transition conditions are met.

**Key properties:**

- **Deterministic execution**: given the same graph and inputs, traversal
  follows the same path
- **Observable transitions**: each node change is logged
- **Checkpoint resumability**: execution can pause and resume at any node
- **Composability**: graphs can be nested or chained

**Contrast with other execution models.** Claude Code uses a linear task
sequence (pending → in_progress → completed), one task active at a time.
Codex uses a turn-based inner loop where the model decides implicitly when
to continue or stop. Attractor makes the execution structure *explicit and
declarative* — a DAG with named phases and LLM-evaluated transitions. This
enables convergence loops (retry until validation passes) that are implicit
in the other systems but structurally guaranteed in Attractor.

#### Infrastructure: CXDB and StrongDM ID

Two products that address infrastructure gaps specific to agent-heavy
development:

**CXDB** (`strongdm-product-cxdb.md`) is a self-hosted context store for
AI agents. It persists every turn of every conversation with full type
awareness, branching support, and a visual debugger.

Architecture: Turn DAG with O(1) forking, content-addressed blob storage
(70%+ dedup via Zstd), sub-ms append latency (p50 < 1ms for 10KB), and a
dynamic type registry. Ships as a single binary with no external
dependencies. Clients in Go and TypeScript, React frontend for debugging.

The gap it fills: LangSmith and Langfuse are SaaS-only. OpenTelemetry
tools are built for distributed tracing, not conversations. LLM proxies
capture requests without context structure. Rolling your own on Postgres
takes months. CXDB provides turn-level observability purpose-built for
agent workflows.

**StrongDM ID** (`strongdm-product-strongdm-id.md`) provides identity for
agents as first-class principals. Traditional identity infrastructure
assumes a person in a browser; agents need to authenticate, prove identity,
and receive scoped authorization via different mechanisms.

Key capabilities: SPIFFE-compatible workload identity with platform
attestation (evidence-based, not shared secrets), Cedar-based
policy-as-code for fine-grained authorization, programmatic onboarding
(agents register without human intervention), and multi-IDP federation.

Both address the question: *what infrastructure do agents need that humans
never required?* For Kit, the relevant design principle is that agent
identity and turn persistence are first-class concerns, not afterthoughts.
Kit already has identity (`kit-soul.md`, OAuth scopes in `identity/`) and
append-only audit logs — simpler versions of the same architectural
instinct.

#### Observations

1. **Non-interactive as the limiting case of agent autonomy.** StrongDM's
   system occupies one end of a spectrum. Claude Code and Codex optimize the
   human-in-the-loop experience. StrongDM asks: what if the spec is
   complete enough that no human interaction is needed? The techniques they
   developed to make this work — validation, DTU, scenarios — are valuable
   regardless of where on the spectrum a system operates.

2. **Validation replaces review across all three systems.** Claude Code
   uses plan gates (human approves before execution). Codex uses mechanical
   linters with agent-targeted error messages. StrongDM uses probabilistic
   scenario satisfaction with LLM-as-judge. Three points on a continuum
   from human judgment to mechanical enforcement to empirical measurement.

3. **The holdout set pattern.** Storing validation scenarios outside the
   codebase — inaccessible to the generating agent — is a direct
   application of ML evaluation methodology to software engineering. It has
   no equivalent in Claude Code or Codex, where tests live in-repo
   alongside the code.

4. **Filesystem memory is convergent design.** StrongDM, Claude Code (plan
   files, task JSONs), and Codex (AGENTS.md, exec plans) all use the
   filesystem as the persistence layer for agent state. StrongDM's
   genrefying pattern — LLM-mediated periodic reorganization — is a
   concrete technique for maintaining filesystem-based memory over time.

5. **Pyramid summaries as reversible context management.** Where Codex
   compacts lossy to reclaim context window space, StrongDM maintains
   multi-resolution summaries that preserve drill-down capability. The
   tradeoff is storage vs. fidelity. For context-constrained environments,
   the pyramid approach lets an agent survey more terrain before committing
   context budget to a specific item.

6. **Exemplar-driven development.** Gene transfusion and semports
   operationalize a pattern common in human development — reading a
   reference implementation before building your own — but formalize it as
   an agent workflow with explicit steps and validation. The one-time
   variant is immediately useful; the ongoing variant requires
   infrastructure investment.

7. **Graph execution vs. linear tasks.** Attractor's DAG model with
   natural-language edges is more expressive than linear task sequences,
   enabling convergence loops and conditional branching. The tradeoff is
   implementation complexity — the spec-only repo has six community
   implementations, suggesting the concept is simpler to specify than
   to build.

8. **Multi-model as standard practice.** StrongDM's weather report
   (`strongdm-weather-report.md`) normalizes using different models for
   different task types: one for CS/math, another for frontend aesthetics,
   another for security review. They also use a "consensus operator" —
   independent plans from multiple models, then LLM-merged. Kit currently
   uses a single model; this signals future optionality as model access
   diversifies.

9. **Enterprise scale vs. Pi scale.** The patterns — seed → validate →
   feedback, filesystem memory, pyramid summaries, gene transfusion,
   scenario-based validation — are scale-independent. The infrastructure —
   DTU (behavioral clones of six SaaS products), CXDB (Rust server with
   sub-ms performance), continuous semports, $1K/day token budgets —
   assumes resources well beyond a Raspberry Pi. The techniques transfer;
   the operational intensity does not.

---

## Resources / References

### Claude Code - file based planning and task system

- **Claude Code memory dump**: `_blueprint/context/claude-code-memory/20260212-claudecode-memory/`
  - `plans/melodic-coalescing-wadler.md` — plan format
  - `tasks/1b0ca6c7.../1-6.json` — task decomposition structure
  - `todos/...json` — todo persistence format
  - `projects/.../*.jsonl` — session logs, subagent traces
- **OpenClaw vs Nanobot comparison**: `_blueprint/roadmap/planning/compare-openclaw-nanobot.md`
- **Nanobot source**: `_blueprint/context/nanobot/repo/`
- **Nanobot summary**: `_blueprint/context/nanobot/nanobot-summary.md`
- **OpenClaw source**: `_blueprint/context/openclaw/repo/`
- **TODO.md** (master task list): `_blueprint/roadmap/TODO.md`
- **Feature backlog**: `_blueprint/roadmap/feature-backlog.md`

### OpenAI — Codex agent loop

- [Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/) — Michael Bolin. Agent loop internals: prompt assembly, tool orchestration, inner loop turns, compaction, prompt caching.
- [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/) — Ryan Lopopolo. Zero hand-written code experiment; 1M LOC across 1,500 PRs. Key insight: "give Codex a map, not a 1,000-page instruction manual."
- [Unlocking the Codex harness: how we built the App Server](https://openai.com/index/unlocking-the-codex-harness/) — follow-up on the shared harness powering CLI, web, IDE, and macOS surfaces.

### StrongDM — Software Factory

- [How StrongDM's AI team build serious software without even looking at the code](https://simonwillison.net/2026/Feb/7/software-factory/) — Simon Willison's analysis. "Code must not be written by humans. Code must not be reviewed by humans."
- [The StrongDM Software Factory (manifesto)](https://factory.strongdm.ai/) — official site
- [The StrongDM Software Factory: Building Software with AI](https://discover.strongdm.com/blog/the-strongdm-software-factory-building-software-with-ai) — StrongDM blog post
- [strongdm/attractor](https://github.com/strongdm/attractor) — their non-interactive coding agent; repo is pure markdown specs, zero code
- [strongdm/cxdb](https://github.com/strongdm/cxdb) — AI Context Store; immutable DAG for conversation histories and tool outputs (Rust/Go/TS)
- [Built by Agents, Tested by Agents, Trusted by Whom?](https://law.stanford.edu/2026/02/08/built-by-agents-tested-by-agents-trusted-by-whom/) — Stanford Law / CodeX critical analysis
