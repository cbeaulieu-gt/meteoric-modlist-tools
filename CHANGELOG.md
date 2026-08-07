# Changelog

All notable changes to this project are documented here. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-08-06

Modlist Compare plugin: **Generate Reports…** no longer freezes MO2 while it
works, and it can be stopped part-way.

### Added

- **Progress dialog** for report generation — a live percent and a per-report
  status line while the run proceeds. Generation moved to a worker thread, so
  MO2 stays responsive instead of locking up until the last report is written.
- **Cancellation** from any close route (the Cancel button, Esc, the window's
  X). The run stops at its next checkpoint: reports already written stay on
  disk, the in-progress one is discarded, and any remaining live-profile JSON
  exports are skipped.
- **Inline hints and tooltips** in the Generate Reports dialog, explaining which
  list goes on which side for each report, what each report type produces, and
  where the files land.

### Fixed

- While generation runs, the worker lowers the Python GIL switch interval so
  other MO2 plugins' main-thread code keeps normal speed. Without this, each of
  their Python/Qt calls stalls up to the default 5 ms interval waiting on the
  compute thread (measured ~380× slowdown), which froze MO2's event loop — and
  the progress bar with it — despite generation running off the UI thread.

## [1.0.0] — 2026-08-05

First public release. Extracted from a private workspace where these tools were
developed and used against real Skyrim modlists.

### Added

- **Modlist JSON Exporter** — a Mod Organizer 2 plugin that exports the active
  modlist to JSON, preserving separators, plugin lists, versions, and install
  metadata. See its [format specification](mo2-plugins/modlist_compare/FORMAT_SPECIFICATION.md).
- **`generate_changelog.py`** — markdown changelog between two exports: added,
  removed, and updated mods.
- **`generate_coverage.py`** — HTML report showing what a target list is missing
  or has at a different version compared to a source list, with a `% covered`
  score, per-mod state glyphs, an interactive `--serve` mode for marking mods
  ignored, and a `--base` mode for tracking an upstream list's updates.
- **`generate_diff.py`** — self-contained HTML side-by-side view of both lists'
  full ordering, aligned by matched mods and sections, with move detection
  across sections.
- **`regenerate.py`** — re-runs every existing report related to a list, in
  parallel.
- **Example modlists and sample reports** under `examples/`, which double as the
  project's smoke test.
- Slash commands for Claude Code under `.claude/commands/`.
