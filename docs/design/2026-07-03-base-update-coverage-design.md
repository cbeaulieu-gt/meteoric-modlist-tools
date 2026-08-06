# Base Update Coverage (`--base` filter on generate_coverage)

**Date:** 2026-07-03
**Status:** Approved

## Problem

NS PBR Edition is a custom list derived from NORDIC SOULS. When the base list updates
(NS 3.0.1 → 3.1.1), the PBR maintainer needs to see *which base changes affect the PBR
list* so they can apply them. Existing reports don't answer this:

- A plain diff of 3.0.1 vs 3.1.1 shows all base changes but says nothing about which
  ones PBR already handles.
- A plain coverage of 3.1.1 vs PBR is drowned in noise: every deliberate PBR deviation
  (mods intentionally added/removed/pinned) shows up alongside the actual update work.

This is the "customized Wabbajack list whose base updated" problem: the change set is
diff(base-old → base-new); the target list decides which changes matter.

## Decision summary (from brainstorming)

- **Approach:** a new `--base OLD.json` option on `generate_coverage.py` (not a diff
  option, not a standalone tool). Coverage's existing states map directly onto the
  desired "live worklist" semantics, and serve mode / ignore persistence come free.
- **Change scope:** all actionable base changes — adds, version changes, plugin-set
  changes, and removals of mods the target still carries.
- **Plugins state everywhere:** the "plugins differ" detection is a general coverage
  enhancement, not gated to `--base` — an unimportant plugin diff can always be
  click-ignored via the per-target ignore list.
- **Reference list:** the in-progress target (e.g. PBR 1.5.0), re-exported and
  re-run as work proceeds, so the report shrinks toward "done".
- **Moves:** out of scope (nice-to-have only). Coverage groups by the new base's own
  sections, which implicitly shows new placement; the plain diff remains available for
  load-order questions.

## CLI

```bash
python tools/generate_coverage.py \
  "lists/NORDIC SOULS v3.1.1.json" \
  "lists/NORDIC SOULS v3.1.1 - PBR Edition 1.5.0.json" \
  --base "lists/NORDIC SOULS v3.0.1.json" \
  -o output/ [--serve]
```

`source` and `target` keep their existing meanings: source = the **new base** (drives
the report's structure and rows), target = **your list** (never displayed directly).
`--base` names the **old base**. Without `--base`, behavior is byte-identical to today.

## Semantics

### Plugin-set comparison (shared definition)

Two mods' plugins are compared as **sets of filenames, case-insensitive, order
ignored** (`plugins` in the export is a flat array of `.esp/.esl/.esm` filenames
enumerated from the mod folder; there is no enabled/disabled state). Two empty sets
are equal. A small helper (e.g. `plugin_set(mod)` in `modlist_utils.py`) provides
the normalized set.

### Base change set

Match base-old ↔ source with the existing `match_mods` waterfall (same
`--min-confidence`). Classify each source mod:

- **Added in base:** source mod with no base-old match → kept.
- **Updated in base:** matched pair whose versions differ, i.e.
  `compare_versions(old_ver, new_ver) != 0` (both `-1`/`1` and `None`-undeterminable
  count as changed; downgrades count as changed). Per the existing convention
  (`classify_updates`), a pair where either cleaned version is `Unknown` counts as
  version-unchanged.
- **Plugins changed in base:** matched pair whose plugin sets differ → kept, even at
  the same (or Unknown) version. Different FOMOD choices, a patch esp added or
  hidden, a merge — all are real base changes the version string can't see.
- **Unchanged in base:** everything else → **dropped from the report entirely**,
  including mods the target is missing (those are pre-existing deliberate deviations —
  the noise this feature removes). Sections left with no rows do not render.

### Kept rows

Kept rows classify against the target as today — **Add** (target lacks it),
**Newer**/**Differs** (target is behind the update), **Common** (already absorbed —
hidden by "Hide common") — plus the new **Plugins** state described below. Notes:

- A mod base-updated but deliberately absent from the target shows as Add; one
  click-to-ignore in serve mode silences it permanently (the ignore file is per-target,
  name-normalized, and survives version bumps).
- A mod added in base that the target *already* has (added independently before the
  base adopted it) naturally shows Common/Newer — correct without special casing.

### New state: Plugins (applies to ALL coverage reports, not just `--base`)

A matched source/target pair that would otherwise classify as **Common** — versions
equal, or either version Unknown — but whose **plugin sets differ** gets a new
`CoverageState.PLUGINS`:

- Meaning: the target has the mod (at the right/unknowable version) but its plugin
  set doesn't match the source's — different FOMOD choices, a missing patch esp, a
  merge/split. Without this state such rows render muted Common and look "done".
- Precedence: `Add > Newer > Differs > Plugins > Common`. A version-based actionable
  state wins (its plugin delta is presumed to follow from the version gap). The
  **source-older** case (target ahead, `cmp == -1`) stays **Common** even when
  plugins differ — the target is past the source, so matching the older source's
  plugin layout is not a goal.
- Styling: violet (`±` glyph in the icon column), matching `N plugins` summary and
  section badges; counts as actionable (sections with only Plugins rows start
  expanded); half-weight in `% covered`, like Newer/Differs.
- Row shows the version as Common does, followed by a compact plugin delta expressed
  as what the target would change to match the source: `+Foo.esp` (source has it,
  target lacks it), `−Bar.esp` (target has it, source doesn't). At most 3 names
  inline (alphabetical); more collapse to counts (`+4 −2 plugins`); the full delta is
  always in the row's tooltip.
- Click-to-ignore, "Hide common" interaction, and serve-mode recount treat it like
  the other actionable states.

**Scope decision:** this state applies **everywhere**, including plain coverage
without `--base`. Existing reports (e.g. NS vs Meteoric) will gain Plugins rows and
their `% covered` will drop accordingly — accepted; plugin drift is real signal.
Consequently, pairs matched by plugin *overlap* (merged/split mods, phase-2 matching)
will usually flag as Plugins — that difference is genuinely worth reviewing.

### New state: Removed

Mods present in base-old, absent from source (base-new), **and still present in the
target** get a new `CoverageState.REMOVED`:

- Red styling, `−` glyph in the icon column, matching summary badge (`N removed`).
- Rendered in one synthetic section, **"Removed in base update"**, appended after all
  source sections (no major band of its own).
- Row content: the mod's name from base-old (Nexus-linked via its `id`), and the
  **target's** version in the version cell (that's what you'd be deleting).
- Actionable: appears in section/summary badges, weighs **0** in `% covered`,
  click-to-ignorable like any row (serve-mode recount JS learns the class).
- Base-removed mods the target doesn't have are dropped (nothing to do).
- A target mod already matched to a **still-present** source mod is never listed as
  Removed. When the base replaces a mod with a successor (e.g. a different Nexus page
  that fuzzy-matches the same target mod), the report would otherwise give the same
  physical target mod two contradictory rows — "delete this" and "update this". The
  source row's advice wins; deleting the target mod would delete the thing the source
  still ships.
- Once the mod is deleted from the target and the list re-exported, the row vanishes
  on the next run/refresh.

### % covered

Same weighting scheme with the new states slotted in:
`(common + ignored + ½·(newer + differs + plugins) + 0·(add + removed)) / total`,
floored.
Under `--base` it reads as "how much of the base update the target has absorbed" and
walks to 100% as work completes.

## Rendering

- h1 becomes **"Base Update Coverage"** (title tag likewise) when `--base` is given.
- Header lists line shows all three lists:
  `Base update: <base> → <source> · applied to: <target>`.
- Updated-in-base rows get a tooltip on the version cell with the base transition
  (`Base: 1.2 → 1.5`) — useful when the target's version differs from the old base's.
  Rows kept for a base plugin change likewise get the base's plugin delta in the
  tooltip (`Base plugins: +A.esp −B.esp`) for context.
- Everything else (sticky sections, bands, filter, toggles, collapse rules, ignore
  greying) is inherited unchanged.

## Serve mode

`--base` threads through `coverage_server.py`: the handler re-renders from all three
JSONs and the ignore file on every GET, so re-exporting the target mid-session
refreshes the worklist live. Click-to-ignore is unchanged. The `/serve-coverage`
slash command gains an optional base-list argument with the same partial-name,
newest-version-wins resolution.

## Output naming & regenerate

A base-filtered report is a distinct artifact from plain coverage of the same pair
(both may coexist), so it gets its own type label, **`rebase`**:

```
output/<target>/<source> (from <base>).rebase.html
e.g. output/NORDIC SOULS v3.1.1 - PBR Edition 1.5.0/
       NORDIC SOULS v3.1.1 (from NORDIC SOULS v3.0.1).rebase.html
```

- `generate_coverage.py` auto-names this way when `-o` is a directory and `--base` is
  set (the `(from …)` decoration and `rebase` label replace `<source>.coverage.html`).
- `regenerate.py` learns the `rebase` type: parse the filename's first segment with
  `^(?P<source>.+) \(from (?P<base>.+)\)$`, resolve all three list JSONs, and re-run
  `generate_coverage.py` with `--base` and `-o <output>/` (reproducing the same path).
  A missing base JSON skips with a warning, same as missing sources today; the
  existing right-to-left `rsplit(".", 1)` type parsing is unaffected because the
  `rebase` segment contains no dots.
- The per-target ignore file is shared with plain coverage (same
  `output/<target>/.coverage-ignore.txt`) — an ignore applies to both report kinds,
  by design.

## Testing

- `test_generate_coverage.py`: base change-set computation (added / updated /
  plugins-changed / unchanged / Unknown-version convention / downgrades), row
  filtering and section dropping, Removed classification (target-has vs
  target-lacks), Plugins classification (precedence over Common, source-older stays
  Common, Unknown-version pairs, empty sets equal, delta direction and truncation),
  `% covered` weighting with Removed and Plugins, header/title switch, plain-coverage
  runs gaining Plugins rows but otherwise unchanged.
- `test_modlist_utils.py`: `plugin_set` normalization (case, order, empties).
- `test_regenerate.py`: `rebase` filename parse round-trip, missing-base warning,
  command construction with `--base`.
- `test_coverage_server.py`: base path threads through to rendering.

## Out of scope

- Load-order / move detection.
- Any change to `generate_diff.py` or `generate_changelog.py`.
- Ignore-file schema changes.
