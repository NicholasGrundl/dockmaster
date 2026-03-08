# AGENTS.md

## Project Overview

Dockmaster is a auth microservice that allows for fine grained RBAC control via google services.

Includes:
- browser based SSO login via OAuth code flow
- service to service auth
- session and token based auth

## Current Status

- **Phase 0 (Scaffold)**: Ongoing

See `_blueprint/roadmap/ROADMAP.md` for the full task list.

## Repository Layout

```
.
├── _blueprint/         Planning, specs, and reference material
│   ├── roadmap/        ROADMAP, backlog, decisions, planning/
│   ├── features/       Committed implementation specs (one per feature)
│   ├── context/        Reference codebases (Nanobot, OpenClaw source)
│   └── archive/        Completed/superseded specs
|
|
```

## Key Files to Read First

1. `_blueprint/roadmap/ROADMAP.md` — master task list (what to work on)
2. `_blueprint/AGENTS.md` — how the blueprint directory is organized

## Conventions

- **Documentation**: Markdown everywhere. Feature specs in `_blueprint/features/`.
- **Planning**: Markdown everywhere and save draft ideas. Start high level and ask user many questions to find blindspots in their thinking. Planning documents go in `_blueeprint/features/planning`

## Working with the Blueprint

See `_blueprint/AGENTS.md` for detailed guidance on the planning and spec
directory structure (roadmap vs features vs archive), the feature spec
template, and the ideation-to-implementation workflow.

## Python & uv

- Always invoke Python through `uv run`. This applies to everything:
  `uv run python`, `uv run pytest`, `uv run <script>`. Never use bare `python`,
  `python3`, or `pytest`.
- Always use `ruff` and `ty` for formatting, linting, and type checking
- When sensible prefer `pydantic` to `dataclasses` for json like objects. pydantic gives us validation and serialization out the box.

## Testing

- **Framework**: pytest. Use pytest-family packages (e.g. `pytest-mock`) instead
  of `unittest` equivalents.
- **Approach**: USe Red Greed based test driven development. Always start by writing a failing test but one that contians the behavior we would like to see pass first. Then write the code so the tests "pass" and turn green indicating completion. Sometimes we may need to modify tests if our implementation changes while coding.
- **Fixtures**: Always start test writing by considering lifecycles and fixtures for testing. Always use conftest and the pytest ecosystem patterns to setup fixtures for our tests.
- **When to run**: Run existing tests after code changes. If a package has no
  tests, surface this and ask whether tests should be added.
- **When to write**: Suggest tests for new functionality but wait for approval
  before writing them.
- **Scope**: Run relevant tests first. If they pass, run the full suite to catch
  regressions.
- **Invocation**: Always `uv run pytest` (never bare `pytest`).

## Git

- Use conventional commit format (`feat:`, `fix:`, `chore:`, etc.).
- Do NOT add `Co-Authored-By: Claude` to commit messages.
- Do NOT make commits unless explicitly instructed. Instead, suggest when a
  commit makes sense and provide the commit message for the user to run.
- Always ask before pushing, creating PRs, or any action visible to others.
- User stages with `git add .` (not surgical staging).

## Dependencies

- Ask before adding any new dependency to a package.
- Updating existing dependencies to compatible versions is fine without asking.

## Publish Workflow

- Package justfiles have `version` (read/set) and `publish` (dry run default, `now` to ship).
- RC versions can publish from any branch; final releases must be on main.
- `publish` is dry run by default, `just publish now` tags and pushes.
- Tags trigger CI publish workflows (dockmaster-v*, etc.).

## Design Philosophy

- Prefer idempotent tooling with clear error messages over silent failures.
