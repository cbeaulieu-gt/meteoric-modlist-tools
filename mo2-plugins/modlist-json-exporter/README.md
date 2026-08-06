# Modlist JSON Exporter

A Mod Organizer 2 (MO2) plugin that exports detailed modlist information to JSON format for comparison and analysis.

## Documentation

- **[FORMAT_SPECIFICATION.md](FORMAT_SPECIFICATION.md)** - Complete JSON format specification for AI tools and developers

## Requirements

- Mod Organizer 2 **2.5.0 or later**. The plugin imports `PyQt6`
  (`from PyQt6.QtCore import QFileInfo`, `from PyQt6.QtWidgets import QFileDialog, QMessageBox`),
  which MO2's plugin API only exposes from 2.5.0 onward — on an older MO2 the plugin fails to
  load with a bare `ImportError`.

## Purpose

This plugin addresses limitations in basic modlist text files by capturing comprehensive mod metadata in a structured JSON format. This enables more sophisticated modlist comparisons, especially when dealing with:

- **Merged mods** - Tracks plugin files to detect when mods have been merged or split
- **Name variations** - Captures both display names and clean names without tags
- **Metadata** - Preserves Nexus IDs, versions, and installation details
- **Organization** - Records separator hierarchy and mod ordering

## JSON Structure

Each mod is exported as a JSON object with the following structure:

```json
{
  "id": "<nexus modid, or modName if non-nexus>",
  "type": "<separator or mod>",
  "separatorName": "<name of separator the mod is under>",
  "modName": "<name without tags>",
  "displayName": "<name as it appears in MO2>",
  "plugins": ["<list of .esp, .esl, .esm files>"],
  "general": {
    "modid": "<from meta.ini>",
    "version": "<from meta.ini>",
    "newestVersion": "<from meta.ini>",
    "category": "<from meta.ini>",
    "installationFile": "<from meta.ini>"
  },
  "installed": {
    "size": "<number of installed files>",
    "files": [
      {
        "modid": "<installed file modid>",
        "fileid": "<installed file fileid>"
      }
    ]
  },
  "order": "<position in modlist>",
  "tags": ["<list of tags like 'NoDelete'>"],
  "active": "<true/false - is the mod enabled>"
}
```

## Features

- **Comprehensive metadata extraction** from meta.ini files
- **Plugin file enumeration** to track .esp/.esl/.esm files
- **Tag parsing** to extract all [bracketed] tags
- **Separator tracking** to maintain modlist organization
- **Active state detection** to distinguish enabled/disabled mods

## Usage

1. Copy this `modlist-json-exporter/` folder into your MO2 installation's `plugins/`
   directory (e.g. `C:\path\to\ModOrganizer2\plugins\modlist-json-exporter\`), so
   `modlist_json_exporter.py` ends up directly inside it
2. Run MO2 and open the Tools menu
3. Select "Export Modlist to JSON"
4. Choose where to save the JSON file
5. The plugin will export your current modlist with all metadata

## Use Cases

### Modlist Comparison

Compare two modlists even when:
- Mods have been renamed or retagged
- Mods have been merged (compare plugin lists)
- Installation sources differ (use Nexus IDs)

### Merge Detection

Identify when mods have been merged by comparing plugin lists:
- One modlist has separate mods with plugins A, B, C
- Another modlist has a single merged mod with plugins A, B, C

### Version Tracking

Track mod updates across modlist versions using:
- `general.version` from meta.ini
- `general.newestVersion` for available updates
- `id` for identifying the same mod across lists

## Using the Export

This plugin focuses on data collection; the exported JSON is consumed by the comparison
tools that live alongside it in this repository:

- [`tools/generate_changelog.py`](../../tools/generate_changelog.py) — markdown changelog
  between two exports (added / removed / updated mods).
- [`tools/generate_coverage.py`](../../tools/generate_coverage.py) — HTML coverage report
  showing what one list has that another doesn't.
- [`tools/generate_diff.py`](../../tools/generate_diff.py) — self-contained HTML side-by-side
  diff of two lists' full ordering.

See the [top-level README](../../README.md) for how to run them. Import/sync capabilities
(writing changes back into MO2) are not implemented.

## Technical Details

- Reads mod metadata from MO2's IModInterface API
- Parses meta.ini files using Python's configparser
- Enumerates files using standard filesystem operations
- Exports to UTF-8 encoded JSON with proper formatting
