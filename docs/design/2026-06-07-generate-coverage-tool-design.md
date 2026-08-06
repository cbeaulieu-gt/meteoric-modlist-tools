# Design: `generate_coverage.py` — Source-Structured Coverage View

**Date:** 2026-06-07
**Status:** Approved (pending spec review)

## Purpose

A new script, `comparisons/generate_coverage.py`, that renders **one modlist's contents**
(the *source*) organized by the source's own section structure, highlighting which mods the
*target* list is **missing** or has at a **different version**.

This answers a different question than the existing tools:

- `generate_diff.py` — a load-order-aware, side-by-side diff of two lists.
- `generate_changelog.py` — a flat, grouped changelog of what changed between two lists.
- **`generate_coverage.py` (new)** — "looking at the source list's organization, what does it
  contain that my target list lacks or has at a different version?"

Load order is **not** relevant here — this is about comparing modlist *contents*, presented
through the lens of a single list's structure.

## Terminology

- **Source** — the list being inspected (e.g. `NORDIC SOULS v3.0.1.json`). Its sections and
  mod ordering drive the output.
- **Target** — the user's own list (e.g. `Meteoric 0.0.3.json`). Compared against, never displayed
  directly.

(Note: this is the inverse framing of "target" in the project's general workflow, but within this
tool "source = the list you're viewing, target = your list" is consistent and documented in the CLI help.)

## CLI

Mirrors `generate_diff.py`:

```bash
python comparisons/generate_coverage.py SOURCE.json TARGET.json -o output.html [--min-confidence 0.80]
```

| Argument | Description |
|---|---|
| `source` (positional) | Path to the source modlist JSON (the list being inspected) |
| `target` (positional) | Path to the target modlist JSON (the user's list) |
| `-o` / `--output` | Output HTML path (default: stdout) |
| `--min-confidence` | Minimum confidence for fuzzy name matching (default: `0.80`) |

Output is a **self-contained HTML file** (inline CSS + JS, no external dependencies), dark theme,
consistent with `generate_diff.py`.

## Matching

Reuses **`match_mods(source_mods, target_mods)`** from `modlist_utils.py` **unchanged** — the same
waterfall used by the other comparison tools:

1. Nexus ID
2. Plugin overlap
3. Strict normalized name
4. Fuzzy name (threshold = `--min-confidence`)

**No** ignore / alias / compendium config files are used (consistent with `generate_diff.py` and
`generate_changelog.py`; explicitly out of scope per design discussion).

From `match_mods`'s return value `(matched, added, removed)` where source is passed as "old" and
target as "new":

- `matched` — `(source_mod, target_mod)` pairs → mod exists in both.
- `removed` — source mods with no target match → **missing** from target.
- `added` — target-only mods → **ignored** (we display only the source).

## Classification

Every **source** mod is classified into exactly one state:

| State | Condition | Color intent |
|---|---|---|
| **Missing** | source mod has no match in target | red |
| **Newer** | matched; source version **>** target version | orange, `↑` |
| **Older** | matched; source version **<** target version | blue, `↓` |
| **Differs** | matched; both versions known and differ, but direction undeterminable | orange, `≠` |
| **Common** | matched; versions equal, OR at least one version is unknown | muted gray |

Version states (**Newer / Older / Differs**) only trigger when **both** versions are known
(non-empty, not `"Unknown"`), matching `generate_diff.py`'s rule. If either side is unknown, the mod
is **Common** (no actionable version signal).

### Version direction comparison

A new helper **`compare_versions(a, b)`** added to `modlist_utils.py`:

- Inputs are already-cleaned version strings (output of `clean_version` / `get_version`).
- Returns `-1` (a < b), `0` (a == b), `1` (a > b), or `None` (differ, direction undeterminable).
- Strategy (best-effort):
  - Equal strings → `0`.
  - Date form `m/d/yyyy` (both sides) → compare as `(year, month, day)`.
  - Otherwise extract the leading numeric dotted sequence from each (e.g. `4.3.6c` → `(4,3,6)`),
    compare as integer tuples (shorter padded with zeros).
    - If numeric tuples differ → return the comparison.
    - If numeric tuples are equal but the full strings differ (e.g. `1.7` vs `1.7beta`) → `None`.
  - No parseable numeric part on either side and strings differ (e.g. `MCM-01` vs `Alpha-58`) → `None`.
- `None` maps to the **Differs** state; a real ordering maps to **Newer** / **Older**.

This helper lives in `modlist_utils.py` so it is available to the other tools later, but only
`generate_coverage.py` consumes it for now.

## Output Structure (HTML)

Single column, grouped by **source separator**, in **source order**. Mods with no separator are
grouped under `"Unsectioned"`.

### Summary bar (top)

Stat chips mirroring `generate_diff.py`'s summary:

- Total source mods
- Missing
- Newer
- Older
- Differs
- Common

### Controls (fixed, top-right)

- **Hide common mods** toggle — default **off**. When on, hides `Common` mod rows (section
  headers remain). Implemented via a `body` class toggle + CSS, like the diff tool's
  `hide-unchanged`.
- **Expand all** / **Collapse all** — expand or collapse every section.

### Section headers (collapsible)

- Each section is collapsible (click header to toggle).
- Header shows a **count badge** summarizing actionable items, e.g.
  `Combat — 3 missing · 1 newer · 2 differs`. Zero-count categories are omitted from the badge;
  an all-common section shows e.g. `Lighting — all present`.
- **Smart default collapse:** a section with **zero actionable items** (everything `Common`)
  starts **collapsed**; any section with at least one Missing/Newer/Older/Differs mod starts
  **expanded**.

### Mod rows

Each row shows:

- **Mod name** — rendered as a **Nexus link**
  (`https://www.nexusmods.com/skyrimspecialedition/mods/<id>`) when the mod's `id` is a numeric
  Nexus ID; otherwise plain text.
- **Version info:**
  - Missing → source version (plain).
  - Newer / Older / Differs → `source_ver → target_ver` with the direction glyph (`↑` / `↓` / `≠`).
  - Common → the version (plain, muted).
- Row is color-coded by state (background tint + accent), reusing the diff tool's palette
  (`#4ade80` green, `#f87171` red, `#60a5fa` blue, `#fb923c` orange, `#9ca3af` gray).

## Architecture / Code Layout

- New file: `comparisons/generate_coverage.py`.
- One new shared function in `comparisons/modlist_utils.py`: `compare_versions(a, b)`.
- Structure of `generate_coverage.py` (following `generate_diff.py` conventions):
  - Data structures: a `CoverageState` enum and a `CoverageRow` dataclass (mod + state +
    versions + nexus id).
  - `classify_source_mods(...)` — produce ordered `CoverageRow`s grouped by section, using
    `match_mods` results and `compare_versions`.
  - `compute_summary(...)` — counts per state.
  - `render_html(...)` + small `_render_*` helpers — emit the self-contained HTML.
  - `main()` — argparse CLI mirroring `generate_diff.py`, derive list names from filenames.

## Error Handling

- Missing/unreadable input files → clear error message, non-zero exit (consistent with existing
  tools' behavior).
- Empty source list → valid HTML with an empty body and a summary showing zero mods.
- Mods missing `general` / version data → treated as `"Unknown"` (already handled by `get_version`),
  which keeps them in the **Common** state rather than producing spurious version diffs.

## Testing / Verification

- Run against a real pair, e.g.
  `generate_coverage.py "comparisons/NORDIC SOULS v3.0.1.json" "comparisons/modlist-json-exporter/lists/Meteoric 0.0.3.json" -o comparisons/ns3-coverage.html`
  and open in a browser.
- Manual checks:
  - Missing mods appear red and link to Nexus.
  - A known version difference shows the correct direction (`↑`/`↓`) and `src → tgt` versions.
  - An all-common section starts collapsed; a section with gaps starts expanded.
  - "Hide common mods" hides only common rows; "Expand/Collapse all" works.
  - Summary bar counts equal the sum of per-section badge counts.
- `compare_versions` spot-checks: `("4.3.6","4.3.5") -> 1`, `("4.3.5","4.3.6") -> -1`,
  `("1.7","1.7beta") -> None`, `("7/31/2025","7/30/2025") -> 1`, `("MCM-01","Alpha-58") -> None`,
  `("Unknown","2.0")` → not evaluated (Common by the both-known rule).

## Out of Scope (YAGNI)

- Ignore / alias / compendium config files (explicitly declined).
- Compendium recommendation panels (add / redundant / suggested / requirements).
- Showing target-only mods.
- Load-order / positional alignment between the two lists.
- Markdown output (the existing `find_missing_mods.py` already covers a markdown "missing" report).
