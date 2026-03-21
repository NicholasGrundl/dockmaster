# Project Memory

Memory lives in-repo, not in the hidden auto-memory store.

**Where things are:**
- `CLAUDE.md` — coding conventions, preferences, established patterns
- `_blueprint/memory/MEMORY.md` — model preferences, durable project context
- `_blueprint/roadmap/ROADMAP.md` — slim phase index (status + spec links)
- `_blueprint/roadmap/implementation-progress.md` — current active phase details
- `_blueprint/roadmap/phase-history.md` — completed phase narratives + decisions
- `_blueprint/roadmap/decision-log.md` — working decisions for active phase only

**Rules:**
- Do NOT store implementation status, phase progress, or file paths in memory files — those belong in ROADMAP.md and implementation-progress.md
- Do NOT store coding preferences in hidden auto-memory — those belong in CLAUDE.md
- New coding preferences discovered during sessions should be added to CLAUDE.md
- Model preferences and durable project context go in `_blueprint/memory/MEMORY.md`
