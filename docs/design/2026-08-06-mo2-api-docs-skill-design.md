# MO2 API Docs Skill — Design

**Date:** 2026-08-06
**Status:** Approved

## Problem

`docs/mo2-api/` holds ~4,300 lines of scraped mobase API documentation (9 `.rst.txt`
files), but nothing points Claude at them. When creating or testing MO2 plugins, Claude
either guesses at the mobase API or rediscovers the docs by accident.

## Solution

One project skill: `.claude/skills/mo2-api/SKILL.md`. Auto-discovered by Claude Code;
its frontmatter description triggers loading whenever work touches MO2 plugins.

### Frontmatter

- `name: mo2-api`
- `description`: triggers on creating, modifying, debugging, or testing MO2 plugins —
  anything touching `mo2-plugins/`, `mobase`, `IOrganizer`, or `IPluginTool`. States
  that it maps the local API docs in `docs/mo2-api/`.

### Body (~40 lines)

1. **Ground rule** — never guess mobase signatures. Grep `docs/mo2-api/` for the
   class/method name first (plain-text RST, greppable), then read only the matching file.
2. **File index** — one line per doc file, listing the classes/topics it documents:
   - `01-core-overview.rst.txt` — module map, `MoVariant`, top-level functions
   - `02-file-operations.rst.txt` — `FileInfo`, `FileTreeEntry`, `IFileTree`,
     `BSAInvalidation`, `DataArchives`
   - `03-plugin-interfaces.rst.txt` — `IPlugin` and all `IPlugin*` subtypes
     (`Tool`, `Installer`, `InstallerSimple`, `InstallerCustom`, `Game`, `Diagnose`,
     `FileMapper`, `List`, `ModPage`, `Preview`, `Requirement`)
   - `04-organizer-management.rst.txt` — `IOrganizer`, `IModList`, `IModInterface`,
     `IProfile`, `IDownloadManager`, `IInstallationManager`
   - `05-utility-classes.rst.txt` — enums (`ModState`, `PluginState`, `InstallResult`,
     …), `VersionInfo`, `GuessedString`, `PluginSetting`, `ExecutableInfo`, game-feature
     classes (`ModDataChecker`, `SaveGameInfo`, …)
   - `mo2-widgets-api.rst.txt` — `TaskDialog`, `TaskDialogButton`
   - `plugin-types.rst.txt` — narrative guide: which plugin type to implement
   - `setup-tools.rst.txt` — dev environment setup
   - `writing-plugins.rst.txt` — getting-started walkthrough with examples
3. **Working examples** — the four plugins in `mo2-plugins/` are known-good references;
   `modlist-json-exporter` is the most complete `IPluginTool`.
4. **Constraints** — MO2 2.5.0+ / PyQt6 (not PyQt5). No local mobase stub: plugins are
   tested by copying into MO2's `plugins/` folder.

## Out of scope

No CLAUDE.md changes, no slash command, no doc-refresh tooling, no testing/workflow
guidance beyond the constraints line (per scope decision: docs navigation only).

## Verification

With the skill in place, a prompt like "add a setting to the JSON exporter plugin"
should load the skill and lead to a Grep of `docs/mo2-api/` (e.g. for `PluginSetting`)
before any mobase code is written.
