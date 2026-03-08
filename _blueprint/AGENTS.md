# Orientation

This `_blueprint` folder is used to hold reference content, planning documents, knowledge we can pull for context enrichment, and generally any documents an agent may use to learn how and what to develop the project but that is not directly relevant to the project itself.

When directed to this `_blueprint` folder use the following guidance for finding the information you need more efficiently.


# Guidance

## Directory Structure

### `context/` — Technical Reference Material
- One subfolder per topic or package (e.g., `pytest/`, `ruff/`, `google-iap/`)
- Contains files (i.e. markdown, text, html , etc) with reference docs relevant to that topic
- If a topic is missing, ask the user if they want you to create a new directory and populate it with content from the web (TODO make a obtain context skill)

### `roadmap/` — Planning, iteration, ideation
- `ROADMAP.md` — master plan and status, the canonical "what needs doing"
- `feature-backlog.md` — brainstorm/ideation pool (feeds into ROADMAP)
- `decisions.md` — architecture decision log
- `planning/` directory to store plans we are iterating on
- `backlog/` — draft specs needing re-evaluation before implementation
- Plan mode outputs should be saved to `planning/`

### `features/` — Committed implementation specs
- One file per feature/initiative (e.g., mvp2-hardening.md, kit-portal.md, gcp-registry.md)
- Each linked from roadmap/ROADMAP.md
- Ready-to-execute implementation plans and manual setup checklists
- Includes both code-level implementation plans and browser/hands-on step guides (e.g., GitHub settings, PyPI setup)

### `archive/` — Completed Work
- Finished implementation plans and completed design docs move here
- Serves as the historical record of completed work


# Feature Spec Template

When creating a new feature spec in `features/`, use this structure:

```markdown
# <Feature Name>

> One-line summary of what this feature does.

**Status**: Planned | In Progress | Done
**Priority**: P0 | P1 | P2 | P3
**Phase**: 2 | 3 | Future
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

## Source References

Where to look in the codebase for relevant code.

## Open Questions

Unresolved design decisions or trade-offs.

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
```


# Workflow

1. **Ideation** happens in `roadmap/feature-backlog.md`
2. When an idea is committed to, create a spec in `features/` using the template above and link it from `roadmap/ROADMAP.md`
3. When work is complete, move the spec to `archive/` and check off the ROADMAP item
4. Draft/stale specs that need re-evaluation go to `roadmap/backlog/`

