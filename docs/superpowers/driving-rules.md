# Superpowers driving rules

Project-local amendments to the superpowers plan workflow, for whoever coordinates plan work
(`writing-plans` / `executing-plans` / `subagent-driven-development`). Superpowers is
battle-tested: let it run as designed, and treat this doc as only what this project inserts. It
binds because the plugin's own priority rule puts project instructions above its skills.

## Escalation

- **Plan silence is not plan contradiction.** Additive, reversible improvements inside a task's
  boundaries — an extra test, a clearer name, a choice between equally valid implementations —
  are the implementer's call: decide, note it, mention it in review. The test: would a seasoned
  engineer just do it and mention it in review?
- **Above your judgment, dispatch the `jarl` agent** ([.claude/agents/jarl.md](../../.claude/agents/jarl.md))
  before interrupting the user. Prepare the escalation as two or three crisp options, each with
  stakes; a recommendation is welcome but must be marked as one. Carry the plan's goal,
  constraints, artifact paths, and any prior rulings. Pass its model explicitly (`fable`). It
  rules when confident the choice is reversible, within recorded intent, and how-not-what;
  otherwise it returns the escalation already shaped for the human.
- **Escalate straight to the High King (the user)** — skipping the jarl — only for:
  irreversible actions, *what*-not-*how* scope changes, or plan-marked user gates.
- **Every judgment call gets a one-line record** — the coordinator's own and the jarl's rulings
  alike (`judgment: <what and why>`, jarl rulings tagged `(jarl)`) — destined for review or PR
  notes.

## Environment facts

- Agent definitions load at session start: a session older than `jarl.md` cannot dispatch it
  and falls back to asking the user directly.
