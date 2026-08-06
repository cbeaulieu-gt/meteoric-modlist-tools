# Meteoric Modlist Tools

Compare Mod Organizer 2 modlists: changelogs, side-by-side diffs, and coverage reports.

## What it answers

- **What changed between my two releases?** — a markdown changelog of added, removed, and
  updated mods.
- **What does that other list have that mine doesn't?** — an HTML coverage report showing
  what you could pull in, and how far along you already are.
- **What did the upstream base update actually change?** — a filtered coverage view that
  isolates just what moved in the list you're tracking, so your own deviations don't drown
  it out.

All three work from the same input: a JSON export of an MO2 modlist, produced by the
exporter plugin in this repo.

## How you'll use it

Two ways: the Python scripts you run from a terminal — the terminal commands below are the
actual entry point, not a placeholder for one — or the **Modlist Compare** MO2 plugin, which
exports your active modlist and generates the same three reports from inside MO2 (see its
[README](mo2-plugins/modlist_compare/README.md)). If you use Claude Code, two slash commands
(`/regenerate` and `/serve-coverage`) already ship in `.claude/commands/` and wrap the scripts
for you; see [Claude Code slash commands](#claude-code-slash-commands) below. Still planned:
packaging the slash commands as an installable Claude Code plugin (for now, using them means
having this repo cloned somewhere Claude Code can see it).

## Requirements

- Python 3.9+
- Mod Organizer 2 **2.5.0 or later** (to produce the JSON exports) — the exporter plugin
  imports `PyQt6`, which MO2's plugin API only exposes from 2.5.0 onward; on an older MO2 it
  fails to load with an import error.
- No third-party dependencies — everything here is Python standard library.

## Quickstart

Clone or download this repository, then try it right now against the shipped examples — no
export needed. This repository ships two small example lists under `examples/lists/`, used
throughout this README:

```bash
python tools/generate_changelog.py \
  "examples/lists/Example List 1.0.json" \
  "examples/lists/Example List 1.1.json" \
  -o output/
```

This writes `output/Example List 1.1/Example List 1.0.changelog.md`, matching the sample
already committed at
[`examples/reports/Example List 1.1/Example List 1.0.changelog.md`](<examples/reports/Example List 1.1/Example List 1.0.changelog.md>) —
open that one now to see the format without running anything.

> **Windows note:** all three tools force UTF-8 encoding on stdout, so printing to the terminal
> (omitting `-o`) won't crash with a console-encoding error on the arrow character (`→`) the
> changelog uses. `-o` (writing to a file) is still the more convenient way to browse output —
> your terminal's font or code page can still render `→` oddly even though writing it no longer
> fails.

**Then, on your own lists:**

**1. Install the Modlist Compare plugin.** Build it with `python tools/package_plugin.py` and
unzip the resulting `dist/modlist-compare-<version>.zip` into your MO2 installation's `plugins/`
folder, then restart MO2 and use Tools → Modlist Compare → Export Modlist to JSON. (The same
submenu's *Generate Reports…* entry runs the three reports below without leaving MO2 — see the
[plugin README](mo2-plugins/modlist_compare/README.md).) See the
[format specification](mo2-plugins/modlist_compare/FORMAT_SPECIFICATION.md) for what gets
captured.

**2. Export two versions of your modlist** to JSON (e.g. before and after an update), then run
the same command above against your own JSON files instead of the examples.

## Sample reports

Browse real output without exporting anything — the HTML ones open locally in any browser,
no server required:

- [Changelog](<examples/reports/Example List 1.1/Example List 1.0.changelog.md>) —
  markdown, added/removed/updated mods between the two example lists.
- [Side-by-side diff](<examples/reports/Example List 1.1/Example List 1.0.diff.html>) —
  both lists' full ordering, aligned and color-coded.
- [Coverage view](<examples/reports/Example List 1.0/Example List 1.1.coverage.html>) —
  what "Example List 1.0" (as target) is missing or behind on, compared against
  "Example List 1.1" (as source).

## The three tools

Each tool takes two JSON modlist exports and an optional `-o/--output`. `-o` accepts either
an explicit file path (written as-is) or a directory — pointed at a directory, the report is
auto-named `<dir>/<second-list>/<first-list>.<type>.<ext>`, so you can point every report at
the same `output/` folder and let the tool sort them into per-list subfolders. Omitting `-o`
prints to stdout.

Every tool also takes `--min-confidence` (default `0.80`), the threshold for the fuzzy
name-matching fallback described in [How matching works](#how-matching-works) below.

### Changelog — `generate_changelog.py`

Compares two exports and writes a markdown changelog with three sections: **Added Mods**,
**Removed Mods** (both grouped by section), and **Updated Mods** (version changes, listed
flat). It does not report moved mods — for that, use the diff tool below.

```bash
python tools/generate_changelog.py OLD.json NEW.json -o output/
```

**Arguments:** `old_list`, `new_list` (positional, in that order) · `-o/--output`
(auto-names `<dir>/<new_list>/<old_list>.changelog.md`) · `--min-confidence`.

### Coverage — `generate_coverage.py`

Renders one list (the **source**) organized by its own sections, and flags what a **target**
list (yours) is missing or has at a different version. Load order isn't considered — this is
about content, not position. See [Coverage states](#coverage-states) below for what each
row's marker means.

```bash
python tools/generate_coverage.py SOURCE.json TARGET.json -o output/
```

**Arguments:** `source` (drives the report; its sections and order are what you see) ·
`target` (your list — never shown directly, only compared against) · `-o/--output`
(auto-names `<dir>/<target>/<source>.coverage.html`) · `--min-confidence`.

Worked example, using the shipped fixtures as source and target:

```bash
python tools/generate_coverage.py \
  "examples/lists/Example List 1.1.json" \
  "examples/lists/Example List 1.0.json" \
  -o output/
```

writes `output/Example List 1.0/Example List 1.1.coverage.html` — a report on what
"Example List 1.0" could still pull from "Example List 1.1". Run exactly as shown, this reads
**67% covered, 2 to add, 0 ignored** — close to, but not identical to, the committed sample
linked above (**75% / 1 to add / 1 ignored**). The gap is the ignore file, not a bug: the
committed sample was generated with
[`examples/reports/Example List 1.0/.coverage-ignore.txt`](<examples/reports/Example List 1.0/.coverage-ignore.txt>)
present, which has one mod (`Sky Idles`) deliberately marked ignored to demonstrate the `⊘`
state described in [Coverage states](#coverage-states); your own `output/` folder starts with
no ignore file, so nothing is ignored yet. Point `-o` at `examples/reports/` instead of
`output/` to reuse that ignore file and reproduce the sample byte-for-byte.

### Diff — `generate_diff.py`

Generates a self-contained HTML file showing both lists' full mod ordering side by side,
aligned by matched mods and sections, with **move detection** across sections (this is the
one tool of the three that reports moves).

```bash
python tools/generate_diff.py OLD.json NEW.json -o output/
```

**Arguments:** `old_list`, `new_list` (positional) · `-o/--output`
(auto-names `<dir>/<new_list>/<old_list>.diff.html`) · `--min-confidence`.

Color coding: green added, red removed, blue moved, orange updated, gray unchanged. Section
headers are matched by a waterfall (exact name → which new section most of an old section's
mods landed in → fuzzy name), so a renamed section still lines up instead of reading as one
section removed and another added.

## Coverage states

Every row in a coverage report carries one of these states, shown as a glyph in a left icon
column (Common carries none):

| Glyph | State   | Meaning |
| ----- | ------- | ------- |
| `+`   | Add     | Not in the target — a candidate to pull in. |
| `↑`   | Newer   | Source's version is newer than the target's. |
| `≠`   | Differs | Versions differ but which is newer isn't determinable — still actionable. |
| `±`   | Plugins | Same (or unknown) version, but the plugin file set differs from the source's. |
| —     | Common  | Same version **with matching plugins**, or the source is *older* than the target, or either version is unknown with no plugin drift. Not actionable. |
| `⊘`   | Ignored | Manually set aside (see [Serve mode](#serve-mode)). Renders like Common but still marked. |
| `−`   | Removed | `--base` mode only — removed in the base update but the target still carries it. |

The summary bar's **% covered** badge scores how much of the source the target already
handles, each mod weighted by how done it is:

```text
(common + ignored + ½·(newer + differs + plugins)) / total
```

Add and Removed count zero; the result is floored to a whole percent (`—` when the source has
no mods).

## Serve mode

`--serve` starts a local server instead of writing a static file, so you can click any mod
row to toggle it as **ignored** — the decision is written immediately, no page reload needed.
Ignored mods render muted like Common but keep the `⊘` marker and drop out of the actionable
counts.

```bash
python tools/generate_coverage.py SOURCE.json TARGET.json -o output/ --serve
```

Ignores are stored per **target** list, at `output/<target>/.coverage-ignore.txt` — one raw
mod name per line, `#` comments and blanks ignored, hand-editable. Because it's keyed by
target and matched by normalized name, one ignore decision applies to every coverage report
you run against that target, and survives version bumps in the source. Other flags:
`--port` (default `8000`, auto-increments if busy), `--no-browser` (skip auto-opening a
browser tab), and `--ignore-file PATH` (use a specific ignore file instead of the
auto-derived `<output-dir>/<target>/.coverage-ignore.txt`).

## Base update mode

If your list is a derivative that tracks an upstream base list, `--base OLD_BASE.json`
filters the coverage report down to only what changed in the base update — version bumps,
plugin-set changes, new mods — plus a synthetic "Removed in base update" section for base
mods your target still carries. Everything unchanged in the base (including your own
deliberate deviations from it) is dropped, so the report reads as a worklist for absorbing
just the base's update.

```bash
python tools/generate_coverage.py NEW_BASE.json YOUR_LIST.json --base OLD_BASE.json -o output/
```

This writes to `<dir>/<target>/<source> (from <base>).rebase.html` — a distinct filename from
plain coverage, so both can coexist for the same source/target pair. It shares the target's
`.coverage-ignore.txt` and works with `--serve`.

## Regenerate

After re-exporting a list, `regenerate.py` re-runs every report that already references it —
both its own report folder (where it's the target) and any other folder where it appears as
a source or rebase base — instead of you having to re-run each generator by hand. It expects
your own working `lists/` and `output/` folders at the repo root (that's what `--lists` and
`--output` default to):

```bash
python tools/regenerate.py "My List v2"              # regenerate its related reports
python tools/regenerate.py "My List v2" --dry-run    # preview the plan without running it
python tools/regenerate.py                            # list available report folders
```

You can point it at any pair of lists/reports folders, which lets you try `--dry-run` (which
only prints a plan — nothing is written) against the sample reports:

```bash
python tools/regenerate.py "Example List 1.1" --lists examples/lists --output examples/reports --dry-run
```

It reparses each existing report's filename back into the arguments that produced it, so it
only recreates combinations that already exist — it won't invent a new report pairing.
Reports run in a rolling parallel pool (`-j/--jobs` to cap it, `-j 1` for sequential).

## Claude Code slash commands

If you use [Claude Code](https://claude.com/claude-code), two slash commands already ship in
`.claude/commands/` and wrap the scripts above — no separate install step, they work as soon as
this repo is cloned:

- **`/regenerate <list name>`** — runs `regenerate.py` for the named list (see
  [Regenerate](#regenerate) above): every report where it's the target, source, or rebase base.
- **`/serve-coverage <source> <target> [<base>]`** — resolves partial list names against
  `lists/*.json` (newest version wins on a tie) and launches `generate_coverage.py --serve` in
  the background for the resolved pair (or triple, for a `--base` rebase worklist).

Each command resolves the toolkit root itself, in this order: an explicit
`$MODLIST_TOOLS_ROOT` environment variable → `$CLAUDE_PLUGIN_ROOT` (set automatically once this
toolkit is installed as a Claude Code plugin) → the current directory, if
`tools/generate_coverage.py` exists under it. That means you can run these commands from a
different directory than this checkout — e.g. your actual MO2-adjacent modlist workspace, with
its own `lists/` and `output/` folders — by setting `$MODLIST_TOOLS_ROOT` to wherever you cloned
this repo. `lists/` and `output/` are always resolved relative to the current directory, never
the toolkit root, since those hold your modlist data, not the toolkit's code.

## How matching works

Every tool needs to answer "is this the same mod across two lists," even through renames,
re-uploads, and merges. The matching logic (in `tools/modlist_utils.py`) tries, in order:

1. **Per-page assignment** — mods sharing a Nexus page id are grouped and matched pairwise by
   the strongest available signal: a shared installed file id, then an exact name, then an
   identical archive filename, then a fuzzy name above `--min-confidence`. A page hosting only
   one mod in each list matches automatically, so a plain rename with no other signal is still
   caught.
2. **Plugin-based** — mods are compared by their `.esp`/`.esl`/`.esm` file sets (exact match,
   or ≥50% overlap), which catches merges and splits a name-only comparison would miss.
3. **Strict normalized name** — names stripped of all non-alphanumeric characters, compared
   case-insensitively.
4. **Fuzzy name** — a similarity ratio against `--min-confidence`; below the threshold, the
   mod is reported as added/removed rather than matched.

If a report shows a mod as added and removed instead of matched (or matches two mods that
aren't really the same one), `--min-confidence` is the dial to turn — raise it to be
stricter, lower it to catch a rename the default missed.

## Testing

```bash
cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples -v
```

The example lists under `examples/` double as this suite's fixtures — `test_examples.py`
locks in every comparison case (added/removed/updated/moved mods, merges, renames, case-only
differences) that the sample reports and this README rely on.

## Design notes

The reasoning behind the matching waterfall, version cleaning, the coverage state model, and
the report naming convention lives in [`docs/design/README.md`](docs/design/README.md). It's
internal design history, not user documentation — for how to use the tools, this file is the
one to read.

## License

[GPL-3.0](LICENSE).
