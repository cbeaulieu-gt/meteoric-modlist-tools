# Diff report filters — design

## Why
The Diff HTML shows every change; the user wants to narrow it to specific kinds of change. Client-side only, no new CLI flags or dependencies.

## Goals
- Toggle **Added / Removed / Moved / Updated** on and off.
- **Exclude** by mod name, grouping (section/separator), and category — each by text *or* checkbox where it makes sense.

## Non-goals
- Direction filter. Added/Removed already encode Old→New vs New→Old; Moved/Updated read the same either way. Dropped by the user.
- CLI flags, persisted filter state, category *names* (the JSON carries only Nexus category IDs).

## Approaches
1. **Extend the existing in-page filter (chosen):** rows get `data-types`, `data-sec`, `data-cat`; one `filterMods` pass combines the existing text filter, Hide-unchanged and the new controls. Smallest change; plugin gets it free.
2. Regenerate per filter via CLI flags — rejected: the user wants to toggle interactively.

## Design
- The summary stats (`+N added` …) become toggle chips; off = row hidden unless it also carries another enabled type (moved+updated shows if either is on). Unchanged rows are governed only by Hide-unchanged.
- Exclusion controls, each hides a row when any of its terms/values matches:
  - **Hide mods** — text, comma-separated, case-insensitive substring of either side's mod name.
  - **Hide groups** — text (same rules) against the grouping name, plus a checkbox dropdown of every grouping.
  - **Hide categories** — checkbox dropdown of category IDs (`none` for blank). Text is moot: IDs only.
- A mod's grouping is the nearest section header above it; category comes from the new-side mod (old side for removed).
- Section headers with no visible rows collapse whenever any filter is active.
