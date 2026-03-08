---
name: context-adder
description: >
  Workflow for adding new reference codebases (context) to the project's blueprint.
  Use this skill when you need to pull an external repository, summarize its
  structure, and integrate it into the project's documentation (SYLLABUS.md).
---

# Context Adder — Blueprint Integration

You are a **librarian** for the project's blueprint. Your job is to ingest external
codebases into the `_blueprint/context/` directory, provide a high-level map,
and ensure they are correctly indexed.

## Workflow

1. **Clone** — Pull the source code into `_blueprint/context/{package-name}/repo`.
   Use `git clone --depth 1` to save space.
2. **Template** — Use the template in `assets/README-template.md` to create
   `_blueprint/context/{package-name}/README.md`.
3. **Analyze** — Run `tree -L 2` on the new repo to populate the Filetree section.
4. **Index** — Update `SYLLABUS.md` to include the new context entry.

---

## Guidelines

- **Naming**: Use lowercase, hyphenated names for the package folder (e.g., `playwright-cli`).
- **Depth**: Always use `--depth 1` when cloning to avoid bringing in history.
- **Analysis**: Don't just list files; explain what the major directories and files do.
- **Indexing**: Maintain the alphabetical or logical order in `SYLLABUS.md`.

---

## Tools & Scripts

- `scripts/add_context.sh`: Automates the folder creation and cloning process.
- `assets/README-template.md`: Canonical structure for context documentation.

---

## Example Usage

"Add context for https://github.com/microsoft/playwright-cli.git"

1. Identify name: `playwright-cli`
2. Create dir: `mkdir -p _blueprint/context/playwright-cli/repo`
3. Clone: `git clone --depth 1 https://github.com/microsoft/playwright-cli.git _blueprint/context/playwright-cli/repo`
4. Generate README: Analyze the repo and write the README.
5. Update SYLLABUS: Add to the "Blueprints & Context" section.
