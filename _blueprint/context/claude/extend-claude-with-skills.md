# Extend Claude with Skills | Claude Docs

Skills (beta) enable you to customize Claude with specialized knowledge and procedures. A skill is a package of instructions, resources, and optional executable code that helps Claude handle specific types of tasks more effectively.

Skills are currently available in beta for [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) users and API users with the [Code Execution Tool](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/code-execution) enabled.

## Why use skills?

Skills offer several key benefits over simply prompting Claude:

*   **Progressive Disclosure**: Claude loads skill content only when relevant, saving context window space.
*   **Procedural Knowledge**: Package your best practices for handling complex workflows.
*   **Consistency**: Ensure Claude follows standard procedures across different conversations.
*   **Composability**: Claude can combine multiple skills to handle complex requests.

## Creating a skill

A skill is defined by a folder containing a `SKILL.md` file.

### Structure of a skill

```text
my-skill/
├── SKILL.md          # Required: Instructions and metadata
├── scripts/          # Optional: Executable code
│   └── analyze.py
└── references/       # Optional: Documentation files
    └── api-docs.md
```

### The `SKILL.md` file

This file requires a YAML frontmatter block followed by markdown instructions.

```markdown
---
name: data-analyzer
description: Analyzes CSV files to find trends and anomalies. Use when the user asks to "analyze data" or upload a CSV file.
---

# Data Analysis Skill

## Instructions
1. Load the CSV file using pandas.
2. Check for missing values and data types.
3. Generate summary statistics.
4. Identify any outliers using the IQR method.
5. Summarize key findings for the user.
```

### Best practices for skill creation

*   **Clear Descriptions**: The `description` field in the frontmatter is critical. It tells Claude *when* to use the skill. Include trigger phrases.
*   **Specific Instructions**: Be prescriptive about the steps Claude should take.
*   **Modular Design**: Keep skills focused on a single capability.
*   **Testing**: Test your skill with various prompts to ensure it triggers correctly.

## Using skills with the API

To use skills with the API, you must include them in the `container` block of your request. This feature requires the `code_execution` tool to be enabled.

See the [API Reference](https://docs.anthropic.com/en/api/messages) for detailed request structure.

## Community and Support

Join the [Claude Discord](https://discord.com/invite/anthropic) to share your skills and get help from the community.
