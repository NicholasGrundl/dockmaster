# Plan: Blueprint Reorganization & Master TODO

## Context

The pi-agent project has completed MVP1 (stock Nanobot on Pi 4) and is planning MVP2 (hardened fork) and Phase 3 (agent intelligence). Planning content is scattered across 7 files in `_blueprint/roadmap/` with overlap and no clean "here's everything we need to do" list. The `_blueprint/features/` directory is empty despite being intended for implementation specs. Agent identity files (kit-soul, kit-MEMORY) live in the wrong place. No root CLAUDE.md exists.

**Goal**: Create a single master TODO.md, separate planning docs from implementation specs, move agent identity to the right place, and add CLAUDE.md guidance files.

---

## Step 1: Move agent identity files to `agents/nanobot/`

Kit's personality and memory belong with the agent runtime, not in project planning.

- `git mv _blueprint/roadmap/kit-soul.md agents/nanobot/kit-soul.md`
- `git mv _blueprint/roadmap/kit-MEMORY.md agents/nanobot/kit-MEMORY.md`
- Update `agents/README.md` to mention these files

**Files**: `agents/nanobot/kit-soul.md`, `agents/nanobot/kit-MEMORY.md`, `agents/README.md`

---

## Step 2: Move detailed specs into `_blueprint/features/`

Move existing implementation plans from `roadmap/` to `features/`. Split the multi-topic `kit-enhancements.md` into individual specs.

**Moves**:
- `git mv _blueprint/roadmap/mvp2-hardened-nanobot.md _blueprint/features/mvp2-hardening.md`
- `git mv _blueprint/roadmap/kit-plan.md _blueprint/features/dashboard.md`

**Split `kit-enhancements.md` into**:
- `_blueprint/features/email-sessions.md` (Enhancement #001 content)
- `_blueprint/features/email-attachments.md` (Enhancement #002 content)
- `_blueprint/features/event-compaction.md` (Enhancement #003 content)
- `_blueprint/features/multi-channel-linking.md` (Enhancement #004 content)

Then `git rm _blueprint/roadmap/kit-enhancements.md` and remove `features/.gitkeep`.

Add a **metadata header** to each moved/created feature spec (existing body content preserved as-is):
```markdown
**Status**: Planned | In Progress | Done
**Priority**: P0 | P1 | P2 | P3
**Phase**: 2 | 3 | Future
**Last updated**: YYYY-MM-DD
```

**After this step, `_blueprint/features/` contains**:
```
mvp2-hardening.md
dashboard.md
email-sessions.md
email-attachments.md
event-compaction.md
multi-channel-linking.md
```

---

## Step 3: Create `_blueprint/roadmap/TODO.md`

Single flat master TODO consolidating ALL items from roadmap-tracker, feature-backlog, kit-enhancements, and mvp2 plan. Checkboxes with status. Links to feature specs where they exist.

**Structure**:
```
## Phase 0 — Host & Platform Foundation
- [x] items (8 total, all done)

## Phase 1 — MVP1: Stock Nanobot Exploration
- [x] items (7 done, 2 parked with strikethrough)

## Phase 2 — Nanobot Fork & Hardening
> Link to features/mvp2-hardening.md
- [ ] items (10 total, all planned)

## Phase 3 — Agent Intelligence & Features
### P0: Foundational
- [ ] ReAct loop improvements
- [ ] Multi-LLM routing
### P1: High-Value
- [ ] Email attachments → link to features/email-attachments.md
- [ ] Email markdown rendering
- [ ] Email session management → link to features/email-sessions.md
- [ ] File tree tool
### P2: Larger Scope
- [ ] Dashboard → link to features/dashboard.md
### P3: Nice-to-Have
- [ ] Event compaction → link to features/event-compaction.md
- [ ] Multi-channel linking → link to features/multi-channel-linking.md

## Operational Runbook
- [ ] 5 items (audit, rotation, monitoring, memory review, backup)

## Repo Maintenance
- [ ] items from repo-review-feedback.md open items
- [ ] Agent identity backup recipe (justfile rsync with date stamps)

## Future Enhancements
- [ ] 11+ items (Tailscale, WhatsApp, subagents, Ollama, etc.)
```

Also create `_blueprint/roadmap/planning/.gitkeep` for the planning subfolder.

**Files**: `_blueprint/roadmap/TODO.md`, `_blueprint/roadmap/planning/.gitkeep`

---

## Step 4: Create `_blueprint/AGENTS.md` (canonical agent guidance)

Use the user's draft as the base content for `_blueprint/AGENTS.md`. This is the canonical orientation file for any AI agent working in the blueprint directory. Content covers:
- Orientation (what the folder is for)
- Directory structure guidance (context/, roadmap/, features/, archive/)
- Feature spec template
- Workflow (ideation → committed spec → archive when done)

Add the **feature spec template** to the bottom:
```markdown
## Feature Spec Template
# <Feature Name>
> One-line summary
**Status / Priority / Phase / Last updated**
## Problem
## Solution
## Dependencies
## Source References
## Open Questions
## Acceptance Criteria
```

Then **symlink** CLAUDE.md and GEMINI.md to AGENTS.md:
- `ln -sf AGENTS.md _blueprint/CLAUDE.md`
- `ln -sf AGENTS.md _blueprint/GEMINI.md`

**Files**: `_blueprint/AGENTS.md`, `_blueprint/CLAUDE.md` (symlink), `_blueprint/GEMINI.md` (symlink)

---

## Step 5: Create root `CLAUDE.md`

New file at project root. Agent orientation for the whole repo:
- Project overview (what pi-agent is, current status)
- Repository layout (updated tree reflecting new structure)
- Key files to read first (TODO.md, _blueprint/CLAUDE.md, SYLLABUS.md, kit-soul.md)
- Conventions (markdown, config format, security posture, hardware constraints)
- Pointer to `_blueprint/CLAUDE.md` for blueprint-specific guidance

**File**: `/Users/nicholasgrundl/projects/pi-agent/CLAUDE.md`

---

## Step 6: Update cross-references

### SYLLABUS.md
- Update the high-level tree to show new `features/` contents and trimmed `roadmap/`
- Update Blueprints & Context section: remove moved files, add new files
- Update Agent Runtimes section: add kit-soul.md and kit-MEMORY.md under nanobot/
- Mark AGENTS.md/CLAUDE.md/GEMINI.md as populated (remove "placeholder")

### README.md
- Update project structure tree: add `features/` line, update `roadmap/` description
- Mention Kit identity under `agents/nanobot/`

### roadmap-tracker.md
- Update internal references from old file locations to new ones in `features/`

### feature-backlog.md
- Update references to `kit-enhancements.md` → individual feature file paths
- Update reference to `kit-plan.md` → `features/dashboard.md`

### docs/decisions.md
- Add 3 new decision entries: blueprint reorg, single TODO.md, feature spec template

**Files**: `SYLLABUS.md`, `README.md`, `_blueprint/roadmap/roadmap-tracker.md`, `_blueprint/roadmap/feature-backlog.md`, `docs/decisions.md`

---

## Verification

1. **File existence**: All 6 feature specs in `features/`, identity files in `agents/nanobot/`, TODO.md in `roadmap/`, CLAUDE.md at root
2. **No orphans**: `_blueprint/roadmap/` no longer contains kit-soul, kit-MEMORY, kit-enhancements, kit-plan, mvp2-hardened-nanobot
3. **Link integrity**: `grep -r "kit-enhancements\|kit-plan\.md\|mvp2-hardened-nanobot" _blueprint/` returns zero stale references
4. **Symlinks work**: `cat _blueprint/CLAUDE.md` shows AGENTS.md content
5. **SYLLABUS accuracy**: Every path listed in SYLLABUS.md exists on disk
6. **Git clean**: `git status` shows expected moves, new files, and modifications
