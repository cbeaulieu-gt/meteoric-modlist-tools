# Changelog

All notable changes to this project are documented here. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
