# Modlist Compare MO2 Plugin — Design

**Date:** 2026-08-06
**Status:** Approved

## Problem

Comparing modlists today takes two contexts: export JSON from MO2 (via the unreleased
`modlist-json-exporter` plugin), then switch to a terminal and run the `tools/` generators.
Users who live in MO2 never see the reports. The exporter and the generators should ship
together as one installable MO2 plugin that can export and generate reports from inside MO2.

## Solution

One package plugin, `mo2-plugins/modlist-compare/`, absorbing the unreleased
`modlist-json-exporter` (its folder is deleted; README and FORMAT_SPECIFICATION.md move
into the new plugin, and links in CLAUDE.md update). `createPlugins()` returns two
`IPluginTool`s whose `displayName()` share the `"Modlist Compare/"` prefix, which MO2
renders as a submenu:

```text
Tools ▸ Modlist Compare ▸ Export Modlist to JSON
                        ▸ Generate Reports…
```

### Plugin structure

```text
mo2-plugins/modlist-compare/
├── __init__.py            # createPlugins() → [ExportModlistTool(), GenerateReportsTool()]
├── plugin_tools.py        # the two thin IPluginTool classes
├── exporter_core.py       # export_modlist(organizer) → list[dict]; first-separator
│                          #   name suggestion (extracted from modlist_json_exporter.py)
├── report_runner.py       # non-Qt: resolve sides → run generators → write outputs
├── dialog.py              # GenerateReportsDialog (PyQt6)
├── _vendor/               # filled by package script; gitignored except __init__.py
│   ├── modlist_utils.py, generate_coverage.py, generate_diff.py,
│   └── generate_changelog.py, coverage_ignore.py
└── README.md
```

- **Export Modlist to JSON** keeps the current exporter UX exactly (save-file dialog,
  first-separator filename suggestion, summary message box) but calls the shared
  `exporter_core.export_modlist()`.
- MO2 2.5.0+ / PyQt6, stdlib-only beyond mobase/PyQt6 — same constraints as today.

### Generate Reports dialog

Modal `GenerateReportsDialog`:

```text
List 1  (source / old):   [ Current profile ▾ | path…        ] [Browse…]
List 2  (target / new):   [ Current profile ▾ | path…        ] [Browse…]
Reports:                  [x] Coverage   [x] Diff   [ ] Changelog
Destination folder:       [ C:\...\output            ] [Browse…]
[x] Save "Current profile" export as JSON
                                        [Generate]  [Cancel]
```

- Each list side is a combo: **Current profile** (live in-memory export) or **JSON
  file…** (picker). Either side may be either kind. Labels carry the semantics:
  coverage treats List 1→2 as source→target, diff/changelog as old→new — the same
  order as the CLI positionals.
- v1 report types: static coverage, diff, changelog. No `--serve`, no `--base`
  rebase mode (deferred; rebase needs a third file pick).
- List names: file side = filename stem; live side = first-separator suggestion.
- Guards (warning box, dialog stays open): same list on both sides, no report type
  checked, unreadable/invalid JSON.
- Destination folder, checkbox states, and last browse folder persist via MO2 plugin
  settings / `setPersistent`.

### Data flow (`report_runner.py`, no Qt)

1. Resolve each side to `(name, data)` — `json.load` for files,
   `exporter_core.export_modlist()` for live.
2. For each checked report, call the generator's entry function (see the tools API
   below) and write to the CLI naming convention
   `<dest>/<list2>/<list1>.<type>.<ext>`. Coverage reads
   `<dest>/<list2>/.coverage-ignore.txt` exactly like a static CLI run.
   `min_confidence` stays at the 0.80 default — no UI knob.
3. If "save export" is checked and a side is live, write `<dest>/<name>.json`
   (predictable location; `regenerate.py --lists` can point at it).
4. Success box lists written files with an "Open folder" button. A failing report is
   collected and reported, not fatal to the others.

### Tools library API (refactor in `tools/`)

The generators are planned to serve multiple UIs — the CLI today, this plugin now, a
Claude skill later. Each generator gains one pure entry function that is the library
API:

- data-in → text-out, e.g. `generate_coverage.generate(source_data, target_data,
  ignore=…) → html str`
- no filesystem, argparse, or path-convention knowledge — callers own IO and naming
- the output-path naming helper lives in `modlist_utils` so all UIs name files
  identically
- `main()` becomes a thin shim over the entry function

This keeps the vendored plugin copies byte-identical consumers of the exact code the
CLI runs. No skill work happens now; the API shape just allows it later.

### Packaging & vendoring

- `tools/package_plugin.py` (stdlib-only) copies `modlist_utils.py`,
  `generate_coverage.py`, `generate_diff.py`, `generate_changelog.py`, and
  `coverage_ignore.py` into `mo2-plugins/modlist-compare/_vendor/`, then zips the
  plugin folder to `dist/modlist-compare-<version>.zip` (version read from the
  plugin's `VersionInfo`).
- `_vendor/*` (except `__init__.py`) and `dist/` are gitignored.
- `_vendor/__init__.py` inserts its own dir on `sys.path` before importing the
  generators (they import `modlist_utils` as a sibling), then removes it — vendored
  files stay unmodified copies.
- A missing `_vendor` (e.g. a fresh dev checkout) fails loudly with "run
  tools/package_plugin.py" instead of a bare ImportError. (Staleness isn't detected —
  that would need hash tracking; re-running the package script is the workflow.)
- Install: unzip into MO2's `plugins/` folder, restart MO2 (documented in the plugin
  README).

## Error handling & testing

- Dialog guards as listed; per-report errors collected into the completion message;
  IO failures surface in a critical message box.
- Unit tests in `tools/` for the new entry functions (existing tests stay green).
- `report_runner` is Qt-free and mobase-free below the resolve step, so it gets unit
  tests using `examples/lists/` fixtures.
- The mobase-facing classes (`plugin_tools.py`, `dialog.py`, `exporter_core.py`) stay
  thin; they are smoke-tested manually by copying the packaged plugin into MO2's
  `plugins/` folder (no local mobase stub exists).

## Out of scope (v1)

- `--serve` interactive coverage (localhost server inside MO2)
- `--base` rebase mode
- The Claude-skill deliverable for the tools
- Any change to the exported JSON format
