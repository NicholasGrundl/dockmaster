# Interview & Plan Session Guide

This document defines how you run planning sessions that turn a concept or feature idea into an
implementation-ready spec. Read it at the start of every planning session.

**Purpose**: Interview the user → Outline → Flesh out → Validate → Produce spec.

**Core principle**: You are an interviewer first, a planner second. Your job is to extract what the
user wants by asking structured questions, surfacing tradeoffs, and building shared understanding
before writing any plan. Do not assume you know what the user wants. The user always has more
context than you.

---

## Interviewing Guidance

These rules apply throughout the entire session, not just the interview step.

### Question format

- **Always use `AskUserQuestion`** with selectable options to reduce typing burden.
- **Minimum 3 options** for every question. If there are only 2 real choices, add a third that
  represents a different framing (e.g. "Defer this decision", "Hybrid approach", "Need more info
  first").
- **Always provide a recommended option** when you have a basis for one. Mark it with
  "(Recommended)" and include your reasoning in the description. If you genuinely have no
  recommendation, say so — don't fake one.
- **Use multi-select** when choices are not mutually exclusive (e.g. "Which of these concerns
  should the plan address?").
- **Ask follow-up rounds** based on answers. Don't frontload all questions — let the conversation
  narrow. Each answer should inform what you ask next.

### Interview goals

- **Surface tradeoffs**: When multiple approaches are equally viable, name the tradeoffs
  explicitly and let the user choose. Don't pick for them.
- **Find blindspots**: Ask about edge cases, failure modes, and things the user might not have
  considered. Frame these as "Have you thought about X?" not "You forgot X."
- **Ascertain priorities**: When there are competing concerns (simplicity vs flexibility,
  speed vs correctness, etc.), ask the user to rank them.
- **Confirm assumptions**: When you're building on something the user said earlier, reflect it
  back: "Based on your answer about X, I'm assuming Y — is that right?"

### When to stop interviewing

- You have a clear picture of what the user wants built
- The tradeoffs have been surfaced and decisions made
- You can describe the solution back to the user and they agree
- Aim for 3-5 rounds of questions minimum before proposing a plan outline

---

## Step 0 — Orient

### 0a. Understand the starting point

Ask the user what they're planning:
- A new feature/phase from scratch?
- An extension of existing functionality?
- A redesign of something that exists?

### 0b. Survey existing docs and code

Before asking detailed questions, understand what already exists.

<note>
**Exploration strategy — use the most efficient tool available:**

1. **Primary**: Use the `smart-tree` skill if available. It provides intelligent, heuristic-driven
   directory exploration that minimizes token cost.
2. **Fallback**: Use the `tree` bash command. It is fast, efficient, and flexible.
   - Example: `tree _blueprint/features -L 1` for existing phase specs
   - Example: `tree src/ -L 2 --dirsfirst` for current source structure
   - Run `tree --help` if unfamiliar with flags.
3. **Last resort**: Use `find` with targeted flags if `tree` is unavailable.
   - Dirs only: `find _blueprint -maxdepth 2 -type d`
   - Specific files: `find _blueprint/features -name "*.md" -maxdepth 1`

**Philosophy**: Explore structure and filenames FIRST. Only grep or read file contents after you
know WHERE to look. This limited-disclosure approach prevents wasting context on irrelevant files.
</note>

Read:
- `_blueprint/roadmap/implementation-progress.md` — what's already built
- Any existing specs in `_blueprint/features/` related to the topic
- Any existing planning docs in `_blueprint/features/planning/` related to the topic

### 0c. Check for available context

Lightly scan `_blueprint/context/` directory names to see if reference material exists for
relevant topics (libraries, APIs, services). The subdirectory names are descriptive — a quick
`tree _blueprint/context -L 1 --dirsfirst` is usually enough.

**Do not read context docs yet.** Just note what's available. You'll pull it in when needed
during planning.

### 0d. Present your orientation

Summarize to the user:
- What you found in existing docs/code
- What context material is available
- Your initial understanding of the scope

Then begin the interview.

---

## Step 1 — Interview

### 1a. High-level goals

Start broad. Ask about:
- What problem this solves and for whom
- What the user considers success
- What's explicitly out of scope
- How this relates to existing functionality

### 1b. Technical approach

Narrow into specifics:
- Architecture choices (new module vs extend existing, sync vs async, etc.)
- External dependencies (new libraries, APIs, services)
- Data flow (inputs → processing → outputs)
- Integration points with existing code

### 1c. Tradeoff decisions

For every choice with multiple viable options:
- Name the options (minimum 3)
- Describe the tradeoff for each
- Recommend one with reasoning
- Let the user decide

### 1d. Context sufficiency check

After the technical approach is sketched, ask:

> "Do we have enough context to plan this well?"

Specifically check:
- **Libraries/packages**: Are we using any new library? Do we know its API well enough? Is our
  reference material the same version we'll be using?
- **External services**: Do we understand the API contracts? Do we have docs or examples?
- **Existing code**: Have we read the modules we'll be extending?

If context is missing:
1. Check `_blueprint/context/` for existing reference material on the topic
2. Ask the user if they want to obtain/update context before continuing
3. If the user says yes, pause planning and help gather context first

This check should happen multiple times during the session, not just once.

---

## Step 2 — Outline

### 2a. Produce the outline

Based on the interview, produce a numbered outline of everything the plan needs to cover:

```
1. <Section> — <what it covers>
2. <Section> — <what it covers>
3. ...
```

Include sections for:
- Problem / motivation
- Solution overview
- Each major component or sub-task
- Dependencies and integration points
- Testing approach
- Open questions (if any remain)

### 2b. Review the outline with the user

Present the outline and ask:
- Is anything missing?
- Is the ordering right?
- Should any section be split or merged?
- Are there sections that need more interview before we can flesh them out?

Do not proceed until the user approves the outline.

---

## Step 3 — Flesh Out

Work through the outline **one section at a time**, building on decisions already made.

### 3a. Per-section cycle

For each section:

1. **Draft** the section content based on interview answers and existing context
2. **Check context sufficiency** — do we need to read any source files, reference docs, or
   library APIs to get this right?
   - Scan `_blueprint/context/` if a relevant topic might have reference material
   - Read source code if the section extends existing modules
   - Ask the user if context needs to be obtained
3. **Surface decisions** — if the section requires choices not yet made, use `AskUserQuestion`
   with minimum 3 options and a recommendation
4. **Build on prior sections** — reference decisions and designs from sections already completed.
   Ensure consistency.
5. **Present** the fleshed-out section to the user before moving on

### 3b. Context checks during flesh-out

Anytime you encounter:
- A library or package you haven't used in this project before
- An API endpoint or service contract you're specifying
- A pattern you're recommending but haven't verified exists in the codebase

Stop and ask:
> "I'm about to plan around [X]. Do we have good enough context on this, or should we check
> our references / obtain updated docs first?"

### 3c. Keep the user in the loop

After every 2-3 sections, do a quick alignment check:
- "We've covered sections 1-3. Before I continue — does this still match what you have in mind?
  Anything to adjust?"

---

## Step 4 — Validate

After all sections are fleshed out, do a final coherence pass.

### 4a. Internal consistency check

Review the full plan for:
- **Contradictions**: Does section 3 assume something section 5 contradicts?
- **Missing links**: Does a component reference something that was never defined?
- **Ordering issues**: Are dependencies in the right order? Can sub-tasks actually be done in
  the sequence listed?
- **Scope creep**: Did we add things during flesh-out that weren't in the approved outline?

### 4b. Completeness check

Verify the plan covers:
- [ ] Clear problem statement / motivation
- [ ] Solution with enough detail to implement without re-interviewing
- [ ] File paths for modules to create or modify
- [ ] Integration points with existing code (with file paths)
- [ ] Testing approach (what to test, what approach per module)
- [ ] Dependencies (new packages, external services, GCP setup)
- [ ] Acceptance criteria (how do we know it's done?)

### 4c. Present findings to user

If the validation pass found issues, surface them with recommended fixes. Use `AskUserQuestion`
for any resolution that has multiple viable options.

### 4d. Final approval

Present the complete plan to the user for final sign-off.

---

## Step 5 — Produce the Spec

### 5a. Write the implementation doc

Write the spec to `_blueprint/features/implementation-<name>.md`.

Use the project's feature spec template (see `_blueprint/AGENTS.md`) as a starting point, but
adapt it to what the plan actually needs. Not every section of the template is required for every
feature.

### 5b. Update related docs

If the plan affects:
- `_blueprint/roadmap/implementation-progress.md` — update "Next session" to point to the new plan
- `_blueprint/roadmap/ROADMAP.md` — add/update the phase or feature entry
- `_blueprint/roadmap/decision-log.md` — record major decisions made during interview

Ask the user which of these updates to make.

---

## Anti-Patterns — What NOT to Do

- **Don't skip the interview.** Even if the user gives a detailed brief, ask clarifying questions.
  There are always unstated assumptions.
- **Don't present a plan without the outline step.** Going straight from interview to full spec
  risks building the wrong thing in detail.
- **Don't make tradeoff decisions silently.** If there are multiple good approaches, the user
  must choose.
- **Don't assume library/API knowledge.** Check that your understanding matches the version and
  API surface we're actually using.
- **Don't write code.** This is a planning session. Pseudocode and interface sketches are fine.
  Actual implementation belongs in an implementation session.
- **Don't frontload all questions.** Interview iteratively — let answers inform the next round.
- **Don't proceed with gaps.** If context is missing, pause and obtain it. A plan built on
  assumptions about external APIs will break during implementation.
