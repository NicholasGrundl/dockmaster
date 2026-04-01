# Replan & Align Session Guide

This document defines how you run alignment and replanning sessions. Use it when implementation
has been underway and blueprint docs have drifted out of sync with reality.

**Purpose**: Look backward (fix stale docs) AND forward (adjust upcoming specs based on learnings).

**Core principle**: This process is heavily user-driven. Do not assume you know what the user wants.
Surface every decision that has more than one reasonable approach. Always provide a recommended
option with reasoning. Use `AskUserQuestion` with selectable options whenever possible to reduce
typing burden.

---

## Step 0 — Orient (every session, no exceptions)

### 0a. Read the ground truth files

1. Read `_blueprint/roadmap/implementation-progress.md` — canonical record of what's actually done,
   what phase we're on, decisions made, and where to pick up.
2. Read `_blueprint/roadmap/ROADMAP.md` — the top-level plan, phase statuses, and spec links.
3. Read `_blueprint/roadmap/decision-log.md` — recorded architectural decisions.

### 0b. Check for an existing alignment report

- If `_blueprint/roadmap/implementation-alignment.md` **exists** → read it. It contains known drift
  issues from a prior session. Use it as your starting checklist — some items may already be
  resolved, others may be new.
- If it **does not exist** → you will create one in Step 1.

### 0c. Survey the blueprint structure

Use a lightweight exploration to understand what docs exist and where they live.

<note>
**Exploration strategy — use the most efficient tool available:**

1. **Primary**: Use the `smart-tree` skill if available. It provides intelligent, heuristic-driven
   directory exploration that minimizes token cost.
2. **Fallback**: Use the `tree` bash command. It is fast, efficient, and flexible.
   - Example: `tree _blueprint -L 2 --dirsfirst` for a quick overview
   - Example: `tree _blueprint/features -L 1 --filesfirst` for a specific directory
   - Run `tree --help` if unfamiliar with flags.
3. **Last resort**: Use `find` with targeted flags if `tree` is unavailable.
   - Dirs only: `find _blueprint -maxdepth 2 -type d`
   - Specific files: `find _blueprint -name "*.md" -maxdepth 2`
   - Exclude dirs: `find _blueprint -path "*/context/*" -prune -o -name "*.md" -print`

**Philosophy**: Explore structure and filenames FIRST. Only grep or read file contents after you
know WHERE to look. This limited-disclosure approach prevents wasting context on irrelevant files.
</note>

Key directories to survey:
- `_blueprint/roadmap/` — ROADMAP, decision-log, feature-backlog
- `_blueprint/features/` — phase design specs (`phase{N}-*-v2.md`) and implementation guides
  (`implementation-phase{N}-*.md`)
- `_blueprint/features/planning/` — legacy reference docs (usually skip unless user directs)
- `_blueprint/archive/` — completed/superseded specs

Do NOT read `_blueprint/context/` proactively. Only search there if information you expect to find
in roadmap/features is missing. Then use targeted grep or smart-tree on specific context subfolders.

### 0d. Establish the situation

Determine:
- Which phases are **complete** (per implementation-progress)?
- Which phases are **next** (upcoming implementation)?
- Which docs exist for each phase (design spec, implementation guide, or both)?
- Is there an existing alignment report with unresolved items?

**Present your orientation summary to the user.** Confirm you have the right picture before
proceeding to discovery.

---

## Step 1 — Discover Drift

Systematically compare the ground truth (implementation-progress + source code) against the
planning docs. Check each area below and record every discrepancy.

### 1a. Roadmap statuses vs reality

Compare `ROADMAP.md` phase statuses against `implementation-progress.md`. Flag any phase marked
"PLANNED" that is actually complete, or "IN PROGRESS" that is done.

### 1b. Spec links and references

Check that links in `ROADMAP.md` point to files that actually exist. Check for `-v2` suffix
mismatches, renamed files, or missing implementation guides.

### 1c. Completed phase specs — content accuracy

For each completed phase, spot-check its implementation guide:
- Is the status still "Ready to implement" when the phase is done?
- Does the spec mention features/decisions that changed during implementation?
- Are there sub-phases (like 4a/4b/4c) that the original spec didn't anticipate?

### 1d. Decision log completeness

Compare decisions recorded in `implementation-progress.md` (Decisions log section) against
`roadmap/decision-log.md`. Flag decisions that exist in progress but not in the decision log.

### 1e. Feature backlog staleness

Scan `roadmap/feature-backlog.md` for items that reference outdated assumptions (e.g., tech
choices that changed, features that were already built, descriptions that no longer match).

### 1f. Upcoming phase specs — forward-looking drift

For the next 1-2 upcoming phases, check if their implementation guides assume things that
changed:
- Dependencies that were already pulled forward into earlier phases
- Settings/singletons that already exist
- UI patterns or route prefixes that shifted
- Architecture decisions made during implementation that aren't reflected

### 1g. CLAUDE.md and .claude/rules/ staleness

Check if alignment fixes affect:
- `CLAUDE.md` — project overview, phase status, conventions
- `.claude/rules/*.md` — workflow rules, development approach references

### 1h. Completed specs — archive candidates

List any specs in `_blueprint/features/` that are for completed phases and could be archived.

### 1i. Produce the alignment report

Write or update `_blueprint/roadmap/implementation-alignment.md` with all findings. Use this format:

```markdown
# Implementation Alignment Report

*Generated: YYYY-MM-DD*
*Purpose: Identify inconsistencies between blueprint docs and actual implementation state.*
*Action: Use this list to triage and fix with the user.*

---

## 1. <Area> — <Summary>

**File**: `path/to/file.md`

### 1a. <Specific issue>
<Description of the discrepancy>
**Current**: <what the doc says>
**Reality**: <what's actually true>

---

## Summary: Priority Order for Fixes

1. **<Most impactful>** — <why>
2. **<Next>** — <why>
...
```

**After writing the report, present a summary to the user before moving to triage.**

---

## Step 2 — Triage with User

This is the most important step. Do not skip or rush it.

### 2a. Present findings by priority group

Group the alignment issues into categories:
- **Critical** — blocks or misleads the next implementation phase (e.g., upcoming spec assumes
  code that already exists differently)
- **Important** — single source of truth is wrong (e.g., ROADMAP statuses, broken links)
- **Housekeeping** — stale references, backlog cleanup, archiving completed specs

### 2b. Ask user what to do with each group

Use `AskUserQuestion` for each priority group. Always:
- Provide a **recommended option** as the first choice, marked with "(Recommended)"
- Include **reasoning** in the option description explaining why you recommend it
- Offer "Defer" and "Skip" as options alongside "Fix now"

Example interaction pattern:
```
Question: "ROADMAP.md has 3 phases marked PLANNED that are actually COMPLETE, and 5 broken
spec links. How should we handle this?"
Options:
  - Fix all now (Recommended) — ROADMAP is the top-level source of truth; stale statuses
    will mislead any new session
  - Fix statuses only, defer links — links are less urgent if agents know the -v2 naming
  - Defer all — note in alignment report for later
```

### 2c. For completed specs, ask per-spec

For each completed phase spec, ask:
- **Archive** — move to `_blueprint/archive/`, update any links pointing to it
- **Update in-place** — mark as COMPLETE, update stale content, keep in `features/`
- **Leave as-is** — it's fine where it is for now

### 2d. For forward-looking changes, present options

When an upcoming phase spec needs adjustment, present the specific options:
- What the spec currently says
- What reality suggests it should say
- Whether to update now or flag for the implementation session to handle

### 2e. Build the fix list

After triage, compile an ordered list of what to fix. Confirm the list with the user before
starting.

---

## Step 3 — Execute Fixes

Work through the fix list one area at a time.

### 3a. Fix cadence

- Fix one document or one logical group of changes at a time
- After each fix, briefly state what was changed
- Before moving to the next area, check in with the user if the fix involved any judgment calls

### 3b. Decision points during fixing

As you fix docs, you will encounter micro-decisions. Surface them rather than assuming:
- "This spec mentions HTMX but we used Tailwind. Should I just replace the reference, or add
  a note about why the approach changed?"
- "The decision log is missing 5 decisions from Phase 4. Should I backfill all of them, or
  just the ones that affect future phases?"

Use `AskUserQuestion` with recommended options for any decision that has more than one
reasonable approach.

### 3c. What to fix (common patterns)

| Pattern | Fix |
|---|---|
| Phase status wrong in ROADMAP | Update status to match implementation-progress |
| Broken spec link in ROADMAP | Fix path (usually add `-v2` suffix or link implementation guide) |
| Spec still says "Ready to implement" | Update status to COMPLETE |
| Decision exists in progress but not decision-log | Backfill into decision-log |
| Upcoming spec assumes code that already exists | Add "Already implemented" note with file path |
| Backlog item references outdated tech choice | Update description to match reality |
| Completed spec in features/ | Ask user: archive, update, or leave |
| CLAUDE.md phase status outdated | Update to match current state |

### 3d. Forward-looking spec updates

When updating upcoming phase specs:
- **Do** note what already exists (with file paths) so the implementation session doesn't
  rebuild it
- **Do** flag design questions that surfaced during prior phases
- **Don't** rewrite the spec — that's for an implementation planning session
- **Don't** change interfaces or architecture without explicit user approval

---

## Step 4 — Close the Session

### 4a. Update the alignment report

Edit `_blueprint/roadmap/implementation-alignment.md`:
- Mark resolved items (or remove them)
- Keep deferred items with a note about why they were deferred
- Add any new issues discovered during fixing
- Update the "Generated" date

### 4b. Update implementation-progress if needed

If the alignment session changed the "next steps" or revealed that progress was further along
(or behind) than recorded, update `implementation-progress.md`.

### 4c. Update memory if needed

If implementation status changed (e.g., realizing a phase is more complete than thought, or
that upcoming work scope changed), update `_blueprint/memory/MEMORY.md`.

### 4d. Session summary

Present to the user:
- **Fixed**: list of docs updated and what changed
- **Deferred**: list of items saved for later (with reasoning)
- **Decisions made**: any new decisions that should be recorded
- **Next**: what the next implementation or alignment session should focus on

---

## Search Hierarchy — Where to Find Information

When looking for information during this session, search in this order:

1. `_blueprint/roadmap/implementation-progress.md` — ground truth of what's done
2. `_blueprint/roadmap/ROADMAP.md` — top-level plan and phase overview
3. `_blueprint/roadmap/decision-log.md` — architectural decisions
4. `_blueprint/features/implementation-phase{N}-*.md` — phase implementation guides
5. `_blueprint/features/phase{N}-*-v2.md` — phase design specs
6. `_blueprint/roadmap/feature-backlog.md` — backlog and deferred items
7. `_blueprint/context/` — **only as fallback** when info isn't found above. Use targeted
   grep or smart-tree on specific subfolders, not a broad scan.
8. Source code (`src/`, `tests/`) — for verifying claims in docs against actual implementation

---

## Anti-Patterns — What NOT to Do

- **Don't silently fix things.** Every fix that involves a judgment call should be surfaced.
- **Don't batch all fixes without check-ins.** Fix one area, check in, move to the next.
- **Don't rewrite upcoming phase specs.** Note what changed and flag questions — full rewrites
  are for implementation planning sessions.
- **Don't read `_blueprint/context/` proactively.** It's reference material, not planning docs.
  Only search there when something is missing from the expected locations.
- **Don't assume the user wants to archive completed specs.** Always ask.
- **Don't skip the triage step.** The user may want to defer things you think are urgent, or
  prioritize things you think are minor.
