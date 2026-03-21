# Orientation

This `_blueprint` folder holds reference content, planning documents, and knowledge for
developing the project. Nothing here is part of the application itself.

# Guidance

## Directory Structure

### `roadmap/` — Planning, status, and history

| File | Role |
|---|---|
| `ROADMAP.md` | Slim index — phase status, one-liner, spec link |
| `phase-history.md` | Append-only narrative log of completed phases (decisions, detours, full story) |
| `implementation-progress.md` | Deep index of current active phase(s) only |
| `decision-log.md` | Working decisions for active/recent phase — flushed to history during cleanup |
| `feature-backlog.md` | Plans for non-active phases + backlog ideas/fixes/enhancements |
| `implementation-alignment.md` | Temporary triage file for alignment sessions — items dispatched then cleared |

### `features/` — Active implementation specs
- Active specs for upcoming or in-progress phases
- `planning/` subfolder for draft ideas and research docs not yet committed
- Each active spec linked from `roadmap/ROADMAP.md`
- See `features/AGENTS.md` for naming conventions and workflow primitives

### `archive/` — Completed and superseded work
- Mirrors the blueprint structure (`features/`, `prompts/`, etc.)
- Files prefixed with `[completed]` (shipped) or `[discarded]` (superseded/stale)
- See `archive/AGENTS.md` for archiving guidelines

### `context/` — Technical Reference Material
- One subfolder per topic or package (e.g., `pytest/`, `ruff/`, `google-iap/`)
- Contains markdown, text, HTML with reference docs relevant to that topic
- If a topic is missing, ask the user if they want to create a new directory

### `prompts/` — Session prompt templates
- Reusable prompt templates for different session types (planning, implementation, alignment)

### `memory/` — Agent memory
- `MEMORY.md` index file + individual memory files
- Persistent across sessions

### `skills/` — Custom skills
- Skill definitions for specialized agent capabilities

# Feature Spec Template

When creating a new feature spec in `features/`, use this structure:

```markdown
# <Feature Name>

> One-line summary of what this feature does.

**Status**: Planned | In Progress | Done
**Priority**: P0 | P1 | P2 | P3
**Phase**: N
**Last updated**: YYYY-MM-DD

---

## Problem

What problem does this solve? Why does it matter?

## Solution

### Overview
High-level description of the approach.

### Implementation Details
Detailed design, code locations, pseudocode, architecture changes.

## Dependencies

- **Requires**: What must be done first (link to other feature specs)
- **Enables**: What this unblocks

## Open Questions

Unresolved design decisions or trade-offs.

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
```

# Workflow

1. **Ideation** happens in `roadmap/feature-backlog.md`
2. When an idea is committed to, create a spec in `features/` and link from `roadmap/ROADMAP.md`
3. When work is complete, move the spec to `archive/features/` with `[completed]` prefix
4. Superseded or stale docs go to `archive/` with `[discarded]` prefix
