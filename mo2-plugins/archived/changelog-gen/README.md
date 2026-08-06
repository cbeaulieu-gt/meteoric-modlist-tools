# Changelog Helper (archived)

An MO2 plugin that compares two `modlist.txt` files (plus an optional exported
`versions.json`) and generates a markdown changelog. Based on Bottle's
[Changelog Generator for Modlist Authors](https://www.nexusmods.com/site/mods/2067),
modified to categorize the output.

**Status: archived.** This plugin's comparison logic was the precursor to the
[Modlist Compare exporter](../../modlist_compare/) and the standalone
[`tools/generate_changelog.py`](../../../tools/generate_changelog.py), which supersede it —
the JSON export carries far more matching signal (Nexus IDs, plugins, versions) than
`modlist.txt` names. Kept for reference; not maintained.

## Changes from Bottle's version

- **Section categorization** — Added and Removed mods are grouped under their separator
  sections (in load-order) instead of one flat list; Updated mods stay flat.
- **Tag stripping and case-insensitive matching** — `[NoDelete]`-style tags are stripped
  and names compared case-insensitively, so a retagged or recapitalized mod isn't reported
  as removed + added.
- **MIC redundancy filtering** — if Mesh Improvement Compilation is detected in the new
  list, mods on the bundled [mic-included-mods.txt](mic-included-mods.txt) list are
  filtered out of Added/Removed/Updated and instead reported in a "Redundant Mods
  (Included in MIC)" section, flagging mods you can safely drop.

## Usage

The tool appears in MO2's Tools menu as **Changelog Helper**:

1. Pick the old `modlist.txt`; the new one defaults to the current profile's.
2. Optionally pick an old `versions.json` for the Updated section. **Export Current
   Versions** saves today's versions for use as the "old" file next time.
3. **Generate Changelog** writes a markdown file with a summary plus Added / Removed /
   Updated (and, when applicable, Redundant) sections.

Requires MO2 **2.5.0+** (imports PyQt6). To try it anyway, copy `changeloggen.py` and
`mic-included-mods.txt` into MO2's `plugins/` directory.
