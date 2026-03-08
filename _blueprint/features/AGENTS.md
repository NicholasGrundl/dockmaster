# Features Directory Standards

This directory is the primary workspace for planning, auditing, and implementing Kit's features. It follows a strict topology and naming convention to ensure scannability and context retention for both humans and LLMs.

## Topology

- **Root (`_blueprint/features/`)**: Contains active LLM rule files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) and all files related to the **current** active feature(s) being implemented.
- **Planning (`_blueprint/features/planning/`)**: A "parking lot" for features not currently in development. Use this for logging ideas, draft plans, or documents that emerge during other work but are not yet prioritized for implementation.

## Filename Convention

Filenames must be semantic and descriptive. Use the following structure:
`<primitive>-<descriptive-name>[-<distinguisher>].md`

1. **Primitive**: Indicates the file's purpose (see Workflow section below).
2. **Descriptive Name**: A concise, dash-separated name for the feature (e.g., `kit-portal-dashboard`).
3. **Distinguisher** (Optional): Used to differentiate between versions or contributors (e.g., `v1`, `gemini`, `audit-report`).

**Example**: `proposal-kit-portal-dashboard-v1.md`

## Header Convention (YAML Frontmatter)

Every file in this folder MUST start with a YAML frontmatter block. LLMs should read this section first to determine the document's state and history without reading the entire file.

```yaml
---
state: [Ideation | Draft | Review | Finalized | Superseded]
changelog:
  "YYYY-MM-DD HHh": "Newest change description"
  "YYYY-MM-DD HHh": "Previous change description"
---
```

- **state**: The current maturity of the document.
- **changelog**: A reverse-chronological mapping. The key is the date and hour (ISO-Lite), and the value is a concise description of the change. Use quotes for the key.

## Workflow-Aligned Primitives

Use these primitives to categorize files based on Kit's development lifecycle:

- **`research`**: Notes, POCs, prototypes, and initial discovery. Often unorganized or experimental.
- **`proposal`**: A draft plan or architectural proposal focusing on patterns, tech stack, and logic.
- **`audit`**: Reviews, feedback, and soundcheck documents from stakeholders or LLMs.
- **`plan`**: The polished, finalized plan derived from the proposal and audit feedback.
- **`implementation`**: The tactical checklist or coding steps used during the actual build.

---
**Instruction for LLMs**: When entering this directory, scan the filenames and read the YAML headers of relevant files to synchronize with the current feature's trajectory before suggesting changes.
