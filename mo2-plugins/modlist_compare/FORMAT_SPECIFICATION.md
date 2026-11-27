# Modlist JSON Format Specification

This document describes the JSON format output by the Modlist Compare plugin's *Export Modlist to JSON* tool for Mod Organizer 2.

## Overview

The JSON file contains an array of objects, where each object represents either a **separator** (category/section header) or a **mod** (actual mod entry). The items are ordered sequentially as they appear in the modlist from top to bottom.

## Root Structure

```json
[
  { /* separator or mod object */ },
  { /* separator or mod object */ },
  ...
]
```

## Object Types

There are two types of objects in the array, distinguished by the `type` field:
- `"separator"` - A category/section divider
- `"mod"` - An actual mod entry

## Field Definitions

### Common Fields (Present in both separators and mods)

| Field | Type | Description |
|-------|------|-------------|
| `id` | `number` or `string` or `null` | For mods: Nexus mod ID (number) if available, otherwise the clean mod name (string). For separators: always `null` |
| `type` | `string` | Either `"separator"` or `"mod"` |
| `separatorName` | `string` | Name of the separator/section this item belongs to. For separators: their own name. For mods: the name of their parent separator; `"Unsectioned"` if the mod appears before any separator. Never `null` in practice — the exporter seeds it to `"Unsectioned"` before the first separator is seen |
| `modName` | `string` | The mod name with only its **leading** run of `[bracket]` tags stripped (see [Name Stripping](#name-stripping-modname-vs-tags) below) — tags elsewhere in the name are left in place |
| `displayName` | `string` | Full name as it appears in MO2, including all tags and formatting |
| `plugins` | `array[string]` | List of plugin files (.esp, .esl, .esm) contained in this mod. Empty array for separators |
| `general` | `object` | Data from the `[General]` section of meta.ini; `{}` if the section (or the whole meta.ini) is absent (see below) |
| `installed` | `object` | Data from the `[installedFiles]` section of meta.ini; `{}` if the section (or the whole meta.ini) is absent (see below) |
| `order` | `number` | Sequential position in the modlist (0-indexed) |
| `tags` | `array[string]` | All tags extracted from the display name (e.g., `["NoDelete", "082.00036", "Magic"]` from `[NoDelete] [082.00036] [Magic] Some Mod`) |
| `active` | `boolean` | Whether the mod is enabled in MO2. Always `true` for separators |

### Name Stripping: `modName` vs `tags`

`modName` and `tags` are derived from `displayName` by two independently-anchored regexes, and
they do **not** cover the same ground:

- `modName` (`_strip_tags`) strips only the **leading, contiguous run** of `[bracket]` tags —
  anchored at the start of the string (`^(\[[^\]]+\]\s*)+`). A tag anywhere else in the name is
  left in place. `"[NoDelete] [082.00029] [Magic] Lost Grimoire SSE"` → `"Lost Grimoire SSE"`
  (only the three *leading* tags are removed), but `"Skyrim 3D Trees [SMIM]"` (no leading
  bracket) is left completely untouched, brackets and all: `modName` is still
  `"Skyrim 3D Trees [SMIM]"`.
- `tags` (`_extract_tags`) is unanchored — it collects **every** `[bracket]` group anywhere in
  the name via `findall`. So for `"Skyrim 3D Trees [SMIM]"`, `tags` is `["SMIM"]` even though
  that same `[SMIM]` is still sitting inside `modName`.

In short: `modName` is not a general "no tags" clean name — it only removes a *leading* tag
block. A trailing or mid-string bracket (a common convention for edition/variant tags) survives
into `modName` and is also duplicated into `tags`.

### `general` Object Structure

Contains metadata from the mod's `meta.ini` file, `[General]` section:

```json
{
  "modid": "string",           // Nexus mod ID as string (e.g., "12345"), or empty string
  "version": "string",         // Mod version (e.g., "2.1.0.0")
  "newestVersion": "string",   // Latest known version
  "category": "string",        // MO2 category ID(s) from meta.ini (may be quoted, e.g., "\"42,\"")
  "installationFile": "string" // Original archive filename
}
```

**Note**: This shape only applies when meta.ini has a `[General]` section — in that case all
five keys are always present, and any individual key missing from the section is an empty
string. If meta.ini is missing entirely, unreadable, or simply has no `[General]` section,
`general` is `{}` (no keys at all), not this five-key shape with empty strings.

### `installed` Object Structure

Contains information about installed files from the mod's `meta.ini` file, `[installedFiles]` section:

```json
{
  "size": number,              // Number of installed file entries
  "files": [                   // Array of file entries
    {
      "modid": "string",       // Mod ID for this file
      "fileid": "string"       // File ID for this file
    },
    ...
  ]
}
```

**Note**: This shape only applies when meta.ini has an `[installedFiles]` section — in that
case both `size` and `files` are always present and `files`'s length matches `size`. If
meta.ini is missing entirely, unreadable, or simply has no `[installedFiles]` section,
`installed` is `{}` (no keys at all).

## Separator vs Mod Differences

| Field | Separator Value | Mod Value |
|-------|----------------|-----------|
| `id` | Always `null` | Nexus ID (number) or mod name (string) |
| `type` | `"separator"` | `"mod"` |
| `separatorName` | Own name | Parent separator name |
| `plugins` | Always `[]` | List of .esp/.esl/.esm files |
| `general` | Always `{}` | Metadata from meta.ini, or `{}` if the `[General]` section is absent |
| `installed` | Always `{}` | File info from meta.ini, or `{}` if the `[installedFiles]` section is absent |
| `active` | Always `true` | `true` or `false` |

## Complete Examples

### Separator Example

```json
{
  "id": null,
  "type": "separator",
  "separatorName": "Magic",
  "modName": "Magic",
  "displayName": "[NoDelete] Magic_separator",
  "plugins": [],
  "general": {},
  "installed": {},
  "order": 42,
  "tags": ["NoDelete"],
  "active": true
}
```

### Mod Example (with Nexus ID)

```json
{
  "id": 12345,
  "type": "mod",
  "separatorName": "Magic",
  "modName": "Lost Grimoire SSE",
  "displayName": "[NoDelete] [082.00029] [Magic] Lost Grimoire SSE",
  "plugins": [
    "LostGrimoire.esp"
  ],
  "general": {
    "modid": "12345",
    "version": "3.2.0.0",
    "newestVersion": "3.2.0.0",
    "category": "\"58,\"",
    "installationFile": "Lost Grimoire SSE-12345-3-2-0.7z"
  },
  "installed": {
    "size": 1,
    "files": [
      {
        "modid": "12345",
        "fileid": "67890"
      }
    ]
  },
  "order": 43,
  "tags": ["NoDelete", "082.00029", "Magic"],
  "active": true
}
```

### Mod Example (non-Nexus, no plugins)

```json
{
  "id": "Custom Patches",
  "type": "mod",
  "separatorName": "Patches & Outputs",
  "modName": "Custom Patches",
  "displayName": "Custom Patches",
  "plugins": [],
  "general": {
    "modid": "",
    "version": "",
    "newestVersion": "",
    "category": "",
    "installationFile": ""
  },
  "installed": {
    "size": 0,
    "files": []
  },
  "order": 500,
  "tags": [],
  "active": true
}
```

## Order and Hierarchy

1. **Sequential Order**: The `order` field represents the top-to-bottom position in MO2's mod list (0-indexed)
2. **Separator Hierarchy**: Mods list their parent separator in `separatorName`
3. **Section Grouping**: A separator is immediately followed by all mods belonging to it
4. **Reading Order**: Items appear in the array in the same order they appear in MO2 (top to bottom)

## Use Cases

### Identifying Merged Mods

To detect if mods have been merged between two modlists, compare `plugins` arrays:
- If list A has three separate mods with plugins `[A.esp]`, `[B.esp]`, `[C.esp]`
- And list B has one mod with plugins `[A.esp, B.esp, C.esp]`
- They represent the same content in merged form

### Matching Mods Across Lists

Mods can be matched using:
1. **Nexus ID** (most reliable): Compare `id` when it's a number
2. **Clean name**: Compare `modName` for case-insensitive matching
3. **Plugins**: Compare `plugins` arrays for merged/split detection
4. **File IDs**: Compare `installed.files[].fileid` for FOMOD variants

### Version Tracking

- `general.version`: Current installed version
- `general.newestVersion`: Latest available version (may be outdated)
- Compare these across modlists to identify version changes

### Organization Analysis

- Group by `separatorName` to analyze mod organization
- Sort by `order` to maintain original sequence
- Filter by `active` to see enabled/disabled mods
- Parse `tags` to identify special categories (e.g., `NoDelete`, custom prefixes)

## Data Integrity Notes

1. **Empty metadata**: Mods may have empty `general` and `installed` objects if meta.ini is missing or incomplete
2. **Non-Nexus mods**: Use `modName` as `id` when no Nexus ID exists (check if `id` is a string vs number)
3. **Order consistency**: The `order` field is always sequential from 0 to n-1 for n items
4. **Separator continuity**: Each mod's `separatorName` should match a preceding separator's `modName` (or be `"Unsectioned"`)

## Schema Type Definitions (TypeScript-style)

```typescript
type ModlistItem = Separator | Mod;

interface Separator {
  id: null;
  type: "separator";
  separatorName: string;
  modName: string;
  displayName: string;
  plugins: [];
  general: {};
  installed: {};
  order: number;
  tags: string[];
  active: true;
}

interface Mod {
  id: number | string;  // number for Nexus ID, string for non-Nexus
  type: "mod";
  separatorName: string;  // "Unsectioned" if before any separator; never null
  modName: string;
  displayName: string;
  plugins: string[];
  general: GeneralMetadata | {};    // {} if meta.ini or its [General] section is absent
  installed: InstalledFilesMetadata | {};  // {} if meta.ini or its [installedFiles] section is absent
  order: number;
  tags: string[];
  active: boolean;
}

interface GeneralMetadata {
  modid: string;
  version: string;
  newestVersion: string;
  category: string;
  installationFile: string;
}

interface InstalledFilesMetadata {
  size: number;
  files: Array<{
    modid: string;
    fileid: string;
  }>;
}
```

## Generating This Format

This format is generated by the **Modlist Compare** plugin's *Export Modlist to JSON* tool for Mod Organizer 2. The exporter:
- Reads mods using `IModList.allModsByProfilePriority()` (top-to-bottom order)
- Extracts metadata from MO2 APIs and meta.ini files
- Enumerates plugin files (.esp/.esl/.esm) from mod folders
- Preserves organizational structure with separators and sections
- Exports to UTF-8 encoded JSON with 2-space indentation

---

**Version**: 1.0
**Last Updated**: 2026
**Plugin**: Modlist Compare for MO2
