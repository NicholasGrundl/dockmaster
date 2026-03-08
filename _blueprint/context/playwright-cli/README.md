# Resources

github repo:
<https://github.com/microsoft/playwright-cli>

# Filetree

```text
_blueprint/context/playwright-cli/ : Contextual resources and documentation for the Playwright CLI.
├── README.md : External links to the source repository and usage overview.
└── repo/ : The core Playwright CLI codebase.
    ├── playwright-cli.js : Main entry point for the CLI application.
    ├── playwright.config.ts : Default Playwright configuration for the CLI.
    ├── package.json : Project metadata and dependencies.
    ├── scripts/ : Utility scripts, including repository updates.
    │   └── update.js : Script for updating the repository or its components.
    ├── skills/ : Definition of skills for integration with coding agents.
    │   └── playwright-cli : Playwright-specific skill implementations.
    ├── tests/ : Integration tests for the CLI.
    │   └── integration.spec.ts : Main integration test suite.
    └── CONTRIBUTING.md : Guidelines for contributing to the project.
```

# File Breakdown

A detailed look at the components in the Playwright CLI repository.

## Core Application

### `playwright-cli.js`
The central script that handles CLI command parsing and orchestration of Playwright actions. It maps CLI commands (like `open`, `click`, `type`) to underlying Playwright API calls.

### `playwright.config.ts`
Configuration file that defines browser behavior, timeouts, and other Playwright-specific settings used by the CLI.

## Skills Integration

### `skills/playwright-cli/`
Contains the logic and metadata required for coding agents (like Claude Code or GitHub Copilot) to discover and use Playwright CLI as a set of tools (skills). This enables agents to perform browser automation tasks directly through the CLI.

## Testing and Maintenance

### `tests/integration.spec.ts`
Ensures that the CLI commands correctly interact with the Playwright browser instances and return the expected results/snapshots.

### `scripts/update.js`
A helper script for maintenance tasks within the repository.

## Key Concepts

### Token Efficiency
Unlike traditional browser automation tools that might feed entire DOM trees into an LLM, Playwright CLI focuses on providing concise snapshots and specific element references, making it highly efficient for LLM-based agents.

### Session Management
Supports named sessions (`-s=name`) allowing agents to maintain persistent browser contexts across multiple commands or even separate agent runs.
