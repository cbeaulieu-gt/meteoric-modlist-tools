# Jarl escalation agent, driving rules, Concise style — design

Port of three concepts from the private `atlas` repo, simplified for this project: a delegated-arbitration subagent (atlas's "director", here named **jarl**), a minimal driving-rules doc for superpowers plan runs, and the Concise output style plus Guiding Principle for CLAUDE.md.

## Problem

During plan runs, subagents interrupt the user with questions a seasoned engineer would just handle — e.g. "this code is missing test coverage, but the plan didn't specify it; can I add the test?" Each interruption stalls an otherwise-autonomous run. The fix is a triage layer: an agent that answers such questions itself when it confidently can, and otherwise passes the escalation to the user, already shaped for a quick decision.

## Naming

The agent is the **jarl**; the user is the **High King**. A jarl rules on the disputes brought to their hall; matters above a jarl's authority go to the High King. Atlas's "director" terminology does not appear in this repo's files.

## Artifacts

### 1. `.claude/agents/jarl.md` — the agent

Self-contained (no separate role doc, unlike atlas). Frontmatter: `name: jarl`, `model: fable`, `effort: high`, read-only tools (`Read`, `Grep`, `Glob`, `Bash`). Body carries everything:

- **Purpose.** Dispatched by a plan-run coordinator when a subagent's question would otherwise interrupt the High King. Rules when confident; otherwise returns the escalation shaped for the human. Never does analysis or implementation work itself.
- **Bounds** — all three must hold to rule; one failure means escalate regardless of confidence:
  1. The choice is **reversible**.
  2. It stays **within the recorded intent** of the plan / spec / request.
  3. It is a question of **how** something is built, never **what** is being built.
- **Method**, in order:
  1. **Standing rulings first.** A recorded human decision that answers the class of question answers the instance — rule accordingly and cite it.
  2. **Verify cheap claims.** Stated stakes are claims, not facts; when a one-minute read-only probe (read the code, grep for the pattern) settles one, run it. Never modify files, never commit.
  3. **Check every bound** (above).
  4. **Then confidence.** Rule only when genuinely surprised to be overruled. A close call between defensible options is itself the answer — that is what the High King exists for. Never rule to keep a run moving.
- **Output contract** — exactly one of two shapes, consumed by a coordinator, no preamble:
  - `RULING: <choice>` + rationale (citing any standing ruling or probe) + a one-line record for the run log.
  - `ESCALATE: <which bound failed or why confidence is lacking>` + the options block, refined by any probe findings, ready to present to the High King verbatim.
  - No third shape. A ruling hedged with "but check with the human" is an escalation.
- **Target case** (from real experience): "plan didn't mention tests for this code — add them?" Additive, reversible, how-not-what → `RULING: add the tests.`

### 2. `docs/superpowers/driving-rules.md` — coordinator rules

One short file binding whoever coordinates plan work (`writing-plans` / `executing-plans` / `subagent-driven-development`). It binds because superpowers' own priority rule puts project instructions above plugin skills.

- **Plan silence is not plan contradiction.** Additive, reversible improvements inside a task's boundaries — an extra test, a clearer name, a pick between equally valid implementations — are the implementer's call: decide, note it, mention it in review. The test: would a seasoned engineer just do it and mention it in review?
- **Above your judgment, dispatch `jarl`** before interrupting the user. Prepare the escalation as 2–3 crisp options with stakes (a recommendation is welcome but must be marked as one), and pass along the plan's goal and any prior decisions. Pass its model explicitly (`fable`).
- **Escalate straight to the High King** (skip the jarl) only for: irreversible actions, *what*-not-*how* scope changes, or plan-marked user gates.
- **Every judgment call gets a one-line record** — the coordinator's own and the jarl's rulings alike — destined for review / PR notes.
- **Environment fact:** agent definitions load at session start; a session older than `jarl.md` cannot dispatch it and falls back to asking the user directly.

Not ported from atlas: model routing tables, findings record, review councils, ledgers, planning-time probe rules, end-of-run steps — none have counterparts in this project.

### 3. `.claude/output-styles/Concise.md` — output style

Verbatim copy of atlas's Concise style ("say more with less — full information, zero filler," named filler patterns banned with rewrites). Wired as the default via `"outputStyle": "Concise"` in `.claude/settings.json` (an addition to the existing settings file; hooks and permissions untouched).

### 4. `CLAUDE.md` edits

- **Guiding Principle** section added verbatim from atlas (Einstein: "Everything should be made as simple as possible, but not simpler," plus the four weighing bullets), placed directly after the Project Purpose section.
- A short **Superpowers driving rules** section pointing at `docs/superpowers/driving-rules.md`, so sessions discover the rules; it names the jarl and when coordinators dispatch it.

## Testing

No unit-testable surface — all four artifacts are markdown/config consumed by the Claude Code harness. Verification is by inspection plus one live check in a *future* session (per the environment fact above): dispatch `jarl` with a sample prepared escalation and confirm it returns one of the two contract shapes.
