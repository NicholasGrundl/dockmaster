# Workflow Rules

## Planning

- Never jump to a solution. Interview the user first to understand what they
  actually want. Do at least 3 rounds of questions (aim for 5) before proposing
  a plan. Keep asking until you feel ready, then check if the user is done.
- Present facts, tradeoffs, and options — then let the user decide. Do not
  assume you have all the background context. The user always has more context
  that needs to be consulted.
- Always present multiple approaches when there are real alternatives. Explain
  the tradeoffs of each. Do not pick one and run with it.
- Always ask the user before making decisions about: file/folder structure,
  API/interface design, and architecture choices.

## During Implementation

- Elevate any new decision that was not already covered during planning. Ask
  before proceeding.
- If the user explicitly told you to proceed autonomously on a scope, do so —
  but only within that scope.

## Explore Agents

- HARD RULE: Never spawn an Explore agent without asking the user first.
- Always try smart-tree and Grep/Glob before considering an Explore agent.
- If direct searches come up short, explain what you tried and ask if you can
  use an Explore agent.

## Saving Context

- When a planning session or research produces useful artifacts (plans,
  decisions, research), tell the user what you want to save and do it.
- Always ask the user WHERE to save (blueprint docs, memory, etc.) — do not
  assume.
- Do not let valuable generated context disappear. If we discussed something
  worth preserving, surface it.

## Deployments

- Use step-by-step guided deployments: one command at a time, wait for output
  before proceeding.

## Communication

- Ask questions using the AskUserQuestion tool when possible to reduce typing
  burden (provide selectable options).
- Be direct. Lead with the question or action, not the reasoning.
