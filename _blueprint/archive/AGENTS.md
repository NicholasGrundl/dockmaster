# Archive Directory

This directory stores documents that are no longer active in the planning/features workflow.
It mirrors the `_blueprint/` directory structure (e.g., `features/`, `prompts/`) so files
stay categorized by type.

## Status Prefixes

Every file in this directory uses a status prefix in its filename:

- **`[completed]`** — The work described in this document was built and shipped. Archived
  because the phase/feature is done and the spec is now historical reference.
- **`[discarded]`** — The document was superseded (e.g., v1 replaced by v2), found to be
  stale/incorrect, or the approach was abandoned. Kept for historical context but should
  not be used as a reference for future work.

## When to Archive

- **Completed specs**: When a phase or feature is done, move its design spec and
  implementation guide here with the `[completed]` prefix.
- **Superseded docs**: When a v2 replaces a v1, or a new approach replaces an old one,
  move the old version here with `[discarded]`.
- **Stale prompts/workflows**: When a prompt or workflow doc is no longer used, move it
  here with `[discarded]`.

## When NOT to Archive

- Don't archive docs that are still being referenced by upcoming phases.
- Don't archive research/planning docs that haven't been acted on yet — those belong
  in `features/planning/`.
- Don't archive the ROADMAP, decision log, or feature backlog — those are living documents.

## Subdirectories

| Directory | Mirrors | Contents |
|-----------|---------|----------|
| `features/` | `_blueprint/features/` | Design specs (v2), implementation guides, audit docs |
| `prompts/` | `_blueprint/prompts/` | Retired prompt templates and workflow docs |

Add new subdirectories as needed to mirror any new `_blueprint/` subdirectory that
accumulates completed or discarded work.
