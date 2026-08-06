---
name: mo2-api
description: Use when creating, modifying, debugging, or testing MO2 (Mod Organizer 2) plugins — anything touching mo2-plugins/, mobase, IOrganizer, IPluginTool, PyQt6 plugin UI, or plugin settings. Maps the local API docs in docs/mo2-api/ so signatures are looked up, not guessed.
---

# MO2 Plugin API Docs

## Ground rule

**Never guess mobase signatures.** The full mobase API reference is checked in at
`docs/mo2-api/` as plain-text RST (`.rst.txt`) — Grep it for the class or method name,
then read only the matching file. Signatures include parameter types and return types;
class blocks start with `.. py:class::`.

```
Grep pattern:"pluginSetting" path:"docs/mo2-api/"   →  04-organizer-management.rst.txt
```

## File index

| File | Contents |
|------|----------|
| `01-core-overview.rst.txt` | Module map, `MoVariant`, top-level functions |
| `02-file-operations.rst.txt` | `FileInfo`, `FileTreeEntry`, `IFileTree`, `BSAInvalidation`, `DataArchives` |
| `03-plugin-interfaces.rst.txt` | `IPlugin` + all `IPlugin*` subtypes: `Tool`, `Installer`, `InstallerSimple`, `InstallerCustom`, `Game`, `Diagnose`, `FileMapper`, `List`, `ModPage`, `Preview`, `Requirement` |
| `04-organizer-management.rst.txt` | `IOrganizer`, `IModList`, `IModInterface`, `IProfile`, `IDownloadManager`, `IInstallationManager` |
| `05-utility-classes.rst.txt` | Enums (`ModState`, `PluginState`, `InstallResult`, …), `VersionInfo`, `GuessedString`, `PluginSetting`, `ExecutableInfo`, game-feature classes (`ModDataChecker`, `SaveGameInfo`, …) |
| `mo2-widgets-api.rst.txt` | `TaskDialog`, `TaskDialogButton` |
| `plugin-types.rst.txt` | Narrative guide: which plugin type to implement |
| `setup-tools.rst.txt` | Dev environment setup |
| `writing-plugins.rst.txt` | Getting-started walkthrough with worked examples (settings, tool plugins, i18n) |

## Lookalike trap

Some method names exist on more than one interface with different signatures — e.g.
`pluginSetting` is on both `IOrganizer` (no default param) and `IModInterface`
(per-mod, has a `default` param). Always confirm which class block your Grep hit
landed in before copying a signature.

## Working examples

The plugins in `mo2-plugins/` are known-good references;
`modlist-json-exporter/modlist_json_exporter.py` is the most complete `IPluginTool`.

## Constraints

- MO2 2.5.0+ / **PyQt6** — not PyQt5, not PySide.
- No local mobase stub: plugins are tested by copying the plugin folder into MO2's
  `plugins/` directory and restarting MO2. Unit-testable logic should be kept out of
  the mobase-facing class where practical.
