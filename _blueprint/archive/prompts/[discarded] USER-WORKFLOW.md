# User Workflow Notes

Operational guidance for the human — not for the agent.

---

## Model selection

| Situation | Model |
|---|---|
| Starting a new phase | Opus 4.6 |
| Pass 1 tracer bullet (real GCP, debugging) | Opus 4.6 |
| Stuck on something hard | Opus 4.6 |
| Pass 2 unit test writing | Sonnet 4.6 |
| Refactoring / pattern-following work | Sonnet 4.6 |
| GCP setup review, architecture second opinion | Gemini 3 Pro (one-off) |

Switching models mid-project has a consistency cost — each model re-derives your established
patterns. Prefer staying on Sonnet and only reaching for Opus when it earns the cost.

---

## Starting a new coding session

1. Set your model (see above)
2. Open a fresh context — don't continue a session that's near context limit
3. Paste or reference `_blueprint/prompts/PROMPT-development-approaches.md` as opening context
4. The agent will read `_blueprint/implementation-progress.md` and orient itself
5. Let the agent propose sub-tasks before it writes any code — approve before it starts

---

## Ending a session

Before closing:
- Agent must update `_blueprint/implementation-progress.md` with current status
- Confirm the "Next session: pick up at" line is accurate
- Check that any captured GCP fixtures are committed

---

## GCP access during development

- Real GCP is needed only for **Pass 1 (tracer bullet)** of each phase
- Pass 2 (unit tests) and Pass 3 (fake classes) run entirely offline
- Keep a GCP dev project separate from production; use it freely during tracer bullet passes
- Captured fixture files (`tests/fixtures/gcp/`) should be committed so others don't need GCP
