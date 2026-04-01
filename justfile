# dockmaster justfile
# Usage: just <recipe>

# Package identity (must match git tag prefix: <pkg>-v*)
pkg := "dockmaster"

default:
    @just --list

# Install dev dependencies
install:
    uv sync --extra dev

# Run all tests
test: test-core test-integration

# Run core tests (excludes integration)
test-core:
    uv run pytest tests/ -v -m "not integration"

# Run only integration tests (requires real GCP credentials)
test-integration:
    uv run pytest tests/ -v -m "integration"

# --- Checks (read-only verification) ---

# Run all checks (lint + format + types + core tests)
check: check-lint check-format check-types test-core

# Check for lint issues (no auto-fix)
check-lint:
    uv run ruff check src/ tests/

# Check formatting (no changes)
check-format:
    uv run ruff format --check src/ tests/

# Type check (informational)
check-types:
    uv run ty check src/ || true

# --- Fixes (auto-fix) ---

# Run all auto-fixes (lint + format)
fix: fix-lint fix-format

# Fix lint issues
fix-lint:
    uv run ruff check --fix src/ tests/

# Fix formatting
fix-format:
    uv run ruff format src/ tests/

# Run FastAPI dev server
dev:
    uv run fastapi dev src/dockmaster/main.py --port 8001

# Build wheel
build:
    uv build --wheel

# --- Version & Publish ---

# Print current version (no arg) or set version (with arg)
version *v:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{v}}" ]; then
        grep '^version' pyproject.toml | sed 's/.*"\(.*\)"/\1/'
        exit 0
    fi
    tag="{{pkg}}-v{{v}}"
    if git tag -l "$tag" | grep -q .; then
        echo "Error: tag $tag already exists. Increment the version." >&2
        exit 1
    fi
    uv run python -c "
    import re, pathlib
    p = pathlib.Path('pyproject.toml')
    p.write_text(re.sub(r'^version = \".*\"', 'version = \"{{v}}\"', p.read_text(), flags=re.MULTILINE))
    "
    uv sync --extra dev
    echo "Version set to {{v}} — commit and run 'just publish' when ready"

# Publish preflight (dry run) or publish for real with 'just publish now'
publish *action:
    #!/usr/bin/env bash
    set -euo pipefail
    version=$(grep '^version' pyproject.toml | sed 's/.*"\(.*\)"/\1/')
    tag="{{pkg}}-v${version}"
    branch=$(git rev-parse --abbrev-ref HEAD)
    if [[ "$version" == *rc* ]]; then
        release_type="candidate (RC publishes from any branch)"
    else
        release_type="final (requires main branch)"
    fi
    echo "────────────────────────────────────────"
    echo "{{pkg}} v${version} — publish preflight"
    echo "────────────────────────────────────────"
    echo "Package:     {{pkg}}"
    echo "Version:     ${version}"
    echo "Tag:         ${tag}"
    echo "Branch:      ${branch}"
    echo "Release:     ${release_type}"
    echo ""
    # Guard: tag must not already exist
    if git tag -l "$tag" | grep -q .; then
        echo "✗ Tag $tag already exists. Nothing to publish."
        echo "  Increment the version to publish a new release."
        exit 1
    fi
    echo "✓ Tag does not exist"
    # Guard: final releases must be on main
    if [[ "$version" != *rc* ]] && [[ "$branch" != "main" ]]; then
        echo "✗ Final release must be published from main (currently on $branch)"
        exit 1
    fi
    echo "✓ Branch OK"
    # Guard: working tree must be clean
    if [ -n "$(git status --porcelain)" ]; then
        echo "✗ Uncommitted changes detected"
        echo "  Commit your changes first, then run publish again."
        exit 1
    fi
    echo "✓ Working tree is clean"
    # Run checks
    echo ""
    echo "Running checks..."
    if check_output=$(just check 2>&1); then
        echo "✓ Checks passed (lint, format, typecheck, test)"
    else
        echo "✗ Checks failed:"
        echo "$check_output"
        exit 1
    fi
    # Dry run or real publish
    if [ "{{action}}" != "now" ]; then
        echo ""
        echo "Ready to publish. Run 'just publish now' to tag and push."
        exit 0
    fi
    echo ""
    echo "Tagging ${tag}..."
    git tag "$tag"
    echo "Pushing ${branch}..."
    git push origin "$branch"
    echo "Pushing tag ${tag}..."
    git push origin "$tag"
    echo ""
    echo "Published {{pkg}} v${version} — watch CI with: gh run watch"
