# Meteoric Modlist Tools - Claude Assistant Guide

## Project Purpose

This project is a small toolkit for **comparing Mod Organizer 2 (MO2) modlists**. Given two
JSON exports of a modlist, it generates human-readable changelogs, side-by-side diffs, and
"coverage" reports so you can see how lists differ and what one list could pull from another.

The lists are exported from MO2 with the bundled exporter plugin, then fed to the standalone
Python scripts in `tools/`.

## Guiding Principle

The principle "Everything should be made as simple as possible, but not simpler" guides all decisions in this codebase. When weighing options:

- **Prefer the simpler solution** that fully solves the problem
- **Resist adding complexity** for hypothetical future needs
- **Stop when it works** — don't polish beyond what's needed
- **But don't oversimplify** — essential complexity exists for good reasons

## Project Structure

The three generators and `modlist_utils.py` live together in `tools/` so the scripts can import
the shared module as a sibling (`from modlist_utils import ...`). `lists/` (your inputs) and
`output/` (your reports) are shared by all three tools and are gitignored — only their
`.gitkeep` placeholders are tracked. `examples/` ships the synthetic fixtures and their
committed sample output instead, so the toolkit is runnable and testable without any real
modlist data.

## JSON Format

All modlist files follow the format documented in
[FORMAT_SPECIFICATION.md](mo2-plugins/modlist_compare/FORMAT_SPECIFICATION.md).

## The Tools

All three report generators import shared logic from
[modlist_utils.py](tools/modlist_utils.py) (data loading, mod matching, version cleaning, name
normalization). They have no third-party dependencies — standard library only.

**Output paths:** every tool's `-o` accepts either a file path (written as-is) or a directory.
Given a directory (e.g. `-o output/`), the report is auto-named
`<dir>/<second-list>/<first-list>.<type>.<ext>` — the folder is the 2nd positional argument
(coverage→target, diff/changelog→new list), the file the 1st. Omitting `-o` still writes to
stdout.

**Slash commands:** `/regenerate` and `/serve-coverage` (below) are defined in
`.claude/commands/*.md`. Each resolves the toolkit root itself, in order —
`$MODLIST_TOOLS_ROOT` (an explicit override) → `$CLAUDE_PLUGIN_ROOT` (set when this toolkit runs
as an installed Claude Code plugin) → the current directory (if `tools/generate_coverage.py`
exists under it) — so they work whether or not the toolkit is the working directory. `lists/`
and `output/` are still resolved relative to the current directory (the user's modlist
workspace), never the toolkit root. If a command misbehaves, start there.

### Changelog — `generate_changelog.py`

Compares two JSON exports and produces a markdown changelog with three sections: **Added
Mods**, **Removed Mods** (both grouped by section), and **Updated Mods** (version changes,
listed flat). It does not report moved mods — for that, use the diff tool below.

### Coverage view — `generate_coverage.py`

Renders **one source list's contents** (grouped by its own sections) and highlights what the
**target** list is missing or has at a different version. It answers "what can I pull from the
source into my target." Load order is not considered.

**Serve mode (`--serve`):**
`python tools/generate_coverage.py SOURCE TARGET -o output/ --serve`
runs a localhost server (default port 8000, auto-increments if busy; `--port` to set explicitly;
`--no-browser` to suppress auto-open) where **clicking any mod row** toggles it as *ignored* and
writes the change immediately. Ignored mods render muted (gray, like Common) but carry a `⊘`
marker in the icon column, drop out of the actionable counts, and are hidden by "Hide common"; a
section whose last actionable mod is ignored collapses on its own. Also available as the
`/serve-coverage <source> <target>` slash command (partial list names, newest version wins),
which launches this server in the background.

**Ignore file:** ignores are stored per **target** list in
`output/<target>/.coverage-ignore.txt` (one raw mod name per line; `#` comments and blanks
ignored; hand-editable). Matching is by normalized name, so an ignore survives version bumps and
applies to **every** coverage report against that target. Static runs and `/regenerate` always
**read** this file (greying ignored mods); only `--serve` **writes** it. Override the path with
`--ignore-file`.

**Mod states** (source-ahead and drifted-plugins are actionable). Each row carries its state
glyph in a left **icon column** aligned under the section caret (Common shows none); the same
glyphs prefix the matching summary badges:

- **Add** (green, `+`) — not in the target; a candidate to pull into your list; name links to its
  Nexus page
- **Newer** (orange, `↑`) — source version is newer than target's; shown as `your-version → candidate`
- **Differs** (amber, `≠`) — versions differ but direction is unclear (kept actionable)
- **Plugins** (violet, `±`) — same (or unknown) version but the plugin file set differs from the
  source's; shown as the delta the target would apply (`+Foo.esp −Bar.esp`, collapsed to counts
  past 3 names, full list in the tooltip). When the target is *ahead* in version, plugin diffs
  stay Common (matching an older layout isn't a goal).
- **Common** (gray, no glyph) — same version **with matching plugins**, or source is *older*
  than the target, or either version is unknown **with no plugin drift**. Source-older is
  folded into Common because it isn't actionable.
- **Ignored** (gray, `⊘`) — manually set aside via serve mode; see the ignore file above.
- **Removed** (red, `−`, `--base` mode only) — removed in the base update but still in the
  target; rendered in a synthetic "Removed in base update" section at the top of the report
  (base removals are the most urgent thing to act on).

**% covered:** the summary bar leads with a `% covered` badge — how much of the source the
target already handles, each mod weighted by how done it is: **Common**/**Ignored** count full,
**Newer**/**Differs**/**Plugins** (present but a different version or plugin set) count half,
**Add** (missing) counts zero, floored to a whole percent (`—` when the source has no mods).
Formally `(common + ignored + ½·(newer + differs + plugins)) / total` — **Add** and **Removed**
weigh zero. Ignoring a mod nudges it up; in `--serve` the badge recomputes live on every ignore
toggle.

**Mod names:** rows show the **source** mod's name, except for a mod that also exists
in the target under a *different* name — there the row reads `Target Name (Source Name)`
(the name you know it by, with the source's label muted in parentheses). The whole name
links to the source's Nexus page; the text filter matches either name.

**Base update mode (`--base`):** for a *derived* list tracking an upstream base (e.g. a
resource-pack edition of a modlist), pass the **old** base with `--base` to filter the report to
mods that changed in the base update — version changes, plugin-set changes, new mods — plus a
"Removed in base update" section for base-removed mods the target still carries (a target mod
claimed by a still-present source mod is never listed as Removed). Everything unchanged in the
base (your deliberate deviations included) is dropped. Rows carry a tooltip noting what changed
in the base (`Base: 1.2 → 1.5`, `Base plugins: +A.esp`). Design:
[docs/design/2026-07-03-base-update-coverage-design.md](docs/design/2026-07-03-base-update-coverage-design.md).

```bash
python tools/generate_coverage.py \
  NEW_BASE.json \
  YOUR_LIST.json \
  --base OLD_BASE.json \
  -o output/ [--serve]
```

With `-o <dir>` the report is named `output/<target>/<source> (from <base>).rebase.html` (a
distinct artifact from plain coverage — both can coexist). It shares the target's
`.coverage-ignore.txt`, works with `--serve` (the worklist shrinks live as you re-export the
target), and `% covered` reads as "how much of the base update the target has absorbed".

Features: single column grouped by source separator; a left **icon column** of per-state glyphs
aligned under the section caret; **major separators** (dash-wrapped names
like `---------- BASE ----------`) render as full-width divider bands; **sticky** collapsible
section headers with count badges; all-common sections start collapsed while sections with gaps
start expanded; summary bar; "Hide common mods" toggle; Expand all / Collapse all.

### Side-by-side diff — `generate_diff.py`

Generates a self-contained HTML file showing both lists' full mod ordering in parallel
columns, aligned by matched mods/sections. This is the one tool of the three that reports moves.

Features: side-by-side columns; color-coded rows (green added, red removed, blue moved, orange
updated, gray unchanged); section matching that detects renames; move detection across
sections; summary bar; self-contained HTML (inline CSS, no external deps).

**Separator styling (shared with the coverage report):** ordinary section headers are centered,
bold and light (`#cbd5e1`). **Major separators** (dash-wrapped names like
`---------- BASE ----------`) render as coverage-style divider bands — decoration stripped,
uppercase, centered, letter-spaced, in the band palette (`#141d3a` on `#8aa0c8`). An unchanged
major spans both columns as one full-width band; an added / removed / renamed one keeps the
two-column layout so you can see which side changed, and its add/remove/rename background wins
over the band's. Under an active filter a band hides only when every section beneath it (up to
the next band) has hidden too. `is_major_separator` / `major_display_name` live in
[modlist_utils.py](tools/modlist_utils.py) and are shared by both generators.

**Section matching waterfall:** exact name → content-based (≥50% of an old section's matched
mods landed in one new section) → fuzzy name (SequenceMatcher ≥ 0.70). All three stages compare
case-insensitively (see [Name Case](#name-case) below).

### Regenerate — `tools/regenerate.py`

Re-runs **every existing report related to a given list** — reports where it is the target (its
own `output/<list name>/` folder) *and* reports in other folders where it is the source or the
base of a rebase. After re-exporting a list into `lists/`, this refreshes everything that
references it in one shot instead of re-running each generator by hand.

```bash
python tools/regenerate.py "My List v2"              # regenerate its related reports
python tools/regenerate.py "My List v2" --dry-run    # preview the plan
python tools/regenerate.py                           # list available folders
```

For each existing report it parses the filename convention (`<source>.<type>.<ext>`) back into
generator arguments — `<type>` (`coverage`/`diff`/`changelog`) selects the script, the filename
is the 1st positional list, the folder is the 2nd — then re-runs that generator with `-o output/`,
reproducing the exact same path. It does this for the list's own `output/<list name>/` folder
(where it is the target) **and** sweeps every other folder for reports where the list is the
source or rebase base.

`rebase` reports (`<source> (from <base>).rebase.html`) are re-run through
`generate_coverage.py --base`; a missing base list JSON skips with a warning.

**Arguments:** `list_name` (positional; omit to list available folders) · `--dry-run` ·
`--lists` (default `lists`) · `--output` (default `output`) · `-j/--jobs N` (max reports to run
at once).

**Runs reports in parallel.** Each report is an independent subprocess, so they run concurrently
in a rolling thread pool — as soon as one finishes the next queued report starts. The cap is
`-j/--jobs N`; omitted, it defaults to `min(report count, CPU count)` (the generators are
CPU-bound, so more workers than cores wouldn't help). Pass `-j 1` to run sequentially. Progress
lines (`+`/`x`) print in **completion order**, not plan order; the failure summary is unchanged.

**Scope:** every report where the named list participates as target, source, or rebase base is
refreshed. Stray files, mismatched extensions, and reports whose source/base list JSON is missing
are skipped with a warning (unparsable or unrelated files in *other* lists' folders are ignored
silently); a missing JSON for the named list itself is a hard error. The tool only refreshes
reports that already exist — it never creates new combinations. Also available as the
`/regenerate <list name>` slash command. Design:
[docs/design/2026-06-17-regenerate-reports-design.md](docs/design/2026-06-17-regenerate-reports-design.md).

### Modlist Compare plugin — `mo2-plugins/modlist_compare/`

The MO2 plugin that both **produces** the JSON exports the scripts consume and **runs** the same
three generators from inside MO2. Requires MO2 2.5.0+ (PyQt6). Installed by unzipping
`dist/modlist-compare-<version>.zip` into MO2's `plugins/`; it adds a **Modlist Compare**
submenu (the `"Modlist Compare/"` prefix in each tool's `displayName()` is what MO2 renders as a
submenu) with two entries. User docs:
[the plugin README](mo2-plugins/modlist_compare/README.md). Design:
[docs/design/2026-08-06-modlist-compare-plugin-design.md](docs/design/2026-08-06-modlist-compare-plugin-design.md).

**Export Modlist to JSON** (`ExportModlistTool`) — save-file dialog, then writes the active
profile's modlist. The export logic lives in
[`exporter_core.py`](mo2-plugins/modlist_compare/exporter_core.py) as plain functions
(`strip_tags`, `extract_tags`, `sanitize_filename`, `read_meta_ini`, `get_plugin_files`,
`suggested_list_name`, `export_modlist`) — only `export_modlist` touches `mobase`, and it imports
it lazily, so the helpers are unit-testable outside MO2 (`test_exporter_core.py`). Output format:
[FORMAT_SPECIFICATION.md](mo2-plugins/modlist_compare/FORMAT_SPECIFICATION.md).

**Generate Reports…** (`GenerateReportsTool`) — opens
[`dialog.py`](mo2-plugins/modlist_compare/dialog.py)'s `GenerateReportsDialog`, where each side of
the comparison is either the current profile (exported live) or a JSON file, and any combination
of coverage/diff/changelog is written to a chosen folder. The dialog import sits *inside*
`display()` so an import-time problem in `dialog.py` surfaces on click instead of dropping the
whole plugin at registration. Dialog state persists via `IOrganizer.setPersistent` keyed on the
tool's `name()`.

Both `IPluginTool` wrappers live in
[`plugin_tools.py`](mo2-plugins/modlist_compare/plugin_tools.py) on a shared `_BaseTool`;
`__init__.py` registers them via `createPlugins()` only when `mobase` is importable.

**Same code as the CLI.** [`report_runner.py`](mo2-plugins/modlist_compare/report_runner.py)
(Qt-free, unit-tested) calls each generator's pure `generate(...) → str` entry function — the same
one `main()` uses — and writes files through `modlist_utils.resolve_output_path`, so plugin and
CLI naming (`<dest>/<list2>/<list1>.<type>.<ext>`) can never drift. Coverage reads the target's
`.coverage-ignore.txt` exactly like a static CLI run.

**Packaging.** `python tools/package_plugin.py` copies the five generator modules from `tools/`
into `mo2-plugins/modlist_compare/_vendor/` (byte-identical) and builds
`dist/modlist-compare-<version>.zip` (version read from `VersionInfo(...)` in `plugin_tools.py`;
`test_*.py` and `__pycache__` excluded). `_vendor/` (except its `__init__.py`) and `dist/` are
gitignored — **run the script before testing or shipping the plugin**, since `report_runner`
imports the vendored copies. `_vendor/__init__.py` puts its own directory on `sys.path` just long
enough to import the modules under their plain names (they import each other as siblings), and
raises a loud `ImportError` naming `tools/package_plugin.py` when the folder is unpopulated.

## The `examples/` smoke test

`examples/lists/Example List 1.0.json` and `Example List 1.1.json` are small, synthetic
fixtures — no real modlist data — used throughout the README and this file. `examples/reports/`
holds the corresponding **committed** changelog/diff/coverage output, so the sample reports can
be browsed without running anything.

The committed coverage sample also ships a per-target ignore file,
[`examples/reports/Example List 1.0/.coverage-ignore.txt`](<examples/reports/Example List 1.0/.coverage-ignore.txt>),
which deliberately ignores one mod (`Sky Idles`) so the sample demonstrates the `⊘` Ignored
state and its effect on `% covered`. Running the coverage command against `output/` instead
of `examples/reports/` starts with no ignore file and so reads a few points lower until you
ignore something yourself.

That committed output must stay reproducible: regenerating it from the fixtures must be a no-op.

```bash
python tools/regenerate.py "Example List 1.1" --lists examples/lists --output examples/reports
git diff --exit-code examples/reports
```

The regenerate run should print no changes and the `git diff` should exit `0`. If it doesn't,
either a generator's output changed and `examples/reports/` needs to be re-committed
deliberately, or something regressed. `tools/test_examples.py` also locks in the comparison
cases these fixtures cover (added/removed/updated/moved mods, merges, renames, case-only
differences) as unit tests, independent of the committed HTML/markdown.

## Mod Matching Logic

`modlist_utils.py` matches the same mod across lists with a **waterfall** (priority order):

1. **Per-page assignment** — a Nexus `id` identifies a *page* that can host many distinct mods
   (e.g. a texture page with a patch per mod), so mods sharing an `id` are matched as a group.
   Every source/target pair in the group is scored and assigned **best-first**, so a weaker
   signal can never steal a target that a stronger pairing wants. Priority: a shared
   `(modid, fileid)` from `installed.files` (same upload) → **exact strict name** → an identical
   `installationFile` archive (compared whole — never parsed, since its version/timestamp segments
   vary — after lowercasing and stripping a leading `1_`-style rename prefix) → fuzzy name ≥
   `--min-confidence`. A page that hosts a single mod in each list matches **blindly**, so a plain
   rename (no fileid/archive/name signal) is still caught. (Putting exact name above the archive
   match is deliberate: a mod whose archive happens to be another file on the page can't outrank a
   clean name-to-name pairing.)
2. **Plugin-based** — compare `plugins` arrays as sets (exact, or ≥50% overlap). Handles
   merged mods (one list has `[A.esp, B.esp]` where another has separate `[A.esp]`, `[B.esp]`).
3. **Strict normalized name** — strip all non-alphanumeric, case-insensitive.
4. **Fuzzy name** — `difflib.SequenceMatcher` with the configurable `--min-confidence`
   threshold.

These tools use pure-waterfall matching only — there are no ignore/alias/compendium config
files.

## Name Case

**MO2 is case-insensitive about mod, separator, and plugin names** — one list cannot hold both
`Core` and `CORE`, and the same separator can be spelled differently in two exports (or in two
files of the same profile). So **every name equality test in this repo is case-insensitive**;
a recapitalized name must never read as one added plus one removed.

- `modlist_utils.name_key(name)` — the identity key: `strip().casefold()`, nothing else. Use it
  for any dict key, set member, or `==` between two names. `same_name(a, b)` is the equality
  shorthand. Distinct from `normalize_name` / `normalize_name_strict`, which *also* strip
  version and edition suffixes — those are for fuzzy matching, `name_key` for identity.
- Mod names were already covered (`normalize_name` lowercases) and so were plugin filenames
  (`plugin_set` lowercases) and `installationFile` (`_norm_install_file` lowercases).
- **Separator names** go through `name_key` in `get_separator_order`, `generate_diff`'s section
  matching / grouping / move detection, `generate_coverage`'s section grouping and
  `map_sections_to_majors`, and `generate_changelog`'s `organize_by_section`.

Where names are only *displayed*, keep the source list's own spelling — key on `name_key`, but
show the raw name. Case variants collapsing onto one entry keep the first spelling seen.

## Version Cleaning

Raw `meta.ini` version strings are normalized to MO2 display format by
`modlist_utils.clean_version` (see its tests for the full case list). Empty/missing versions
become `Unknown` and are excluded from "Updated" sections, since `Unknown → X.Y` isn't a
meaningful version change.

## Testing

Run the unit tests from inside `tools/`:

```bash
cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin -v
```

The plugin's own tests (`exporter_core`, `report_runner`) run outside MO2 — no `mobase`, no Qt —
from the repo root:

```bash
python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v
```

When changing matching or version logic in `modlist_utils.py`, keep these green and add cases
for new behavior. `test_examples.py` runs against the fixtures in `examples/lists/` — if you
change those fixtures, re-run the [smoke test](#the-examples-smoke-test) above and re-commit
`examples/reports/` deliberately.

## Superpowers driving rules

Project-local amendments to the superpowers plan workflow live in
[docs/superpowers/driving-rules.md](docs/superpowers/driving-rules.md) — read it before
coordinating a plan run. Its core rule: a subagent question that a seasoned engineer would just
handle goes to the `jarl` agent (delegated arbitration, [.claude/agents/jarl.md](.claude/agents/jarl.md))
before interrupting the user; only irreversible actions, scope changes, and plan-marked user
gates go straight to the human.

## Working Notes

- **Always read** the relevant JSON exports before reasoning about a comparison.
- **Flag ambiguous matches** — name-based matches can be wrong; explain confidence.
- `general.version` is the installed version; `general.newestVersion` may be stale.
- `active: false` mods are installed but disabled.
- Keep generated reports in `output/` and inputs in `lists/` — both gitignored; only
  `examples/lists/` and `examples/reports/` are tracked.
