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

The plugins in `mo2-plugins/` are known-good references; `modlist_compare/` is the most
complete `IPluginTool` package — `plugin_tools.py` holds the mobase-facing classes,
`exporter_core.py` the mobase-free logic, `__init__.py` the `createPlugins()` entry point.

## Constraints

- MO2 2.5.0+ / **PyQt6** — not PyQt5, not PySide.
- No local mobase stub: plugins are tested by copying the plugin folder into MO2's
  `plugins/` directory and restarting MO2. Unit-testable logic should be kept out of
  the mobase-facing class where practical.

## Threading & responsiveness lessons (learned debugging Generate Reports, 2026-08)

One embedded interpreter is shared by **every** installed plugin — yours, MO2's, and
whatever the user's modlist ships. That coupling produced all of the following:

- **A worker QThread is necessary but not sufficient.** A compute-bound Python thread
  makes every main-thread Python/Qt call wait up to the GIL switch interval (default
  5 ms) to reacquire the GIL, and PyQt releases/reacquires the GIL around each C++
  call — so another plugin's main-thread widget scan measured ~380× slower (30 ms →
  17 s), starving MO2's event loop into "(Not Responding)" even though *our* code never
  touched the main thread. Fix: `sys.setswitchinterval(0.0002)` for the duration of the
  compute, restored in a `finally` (0.2 ms kills the amplification; 1 ms does not;
  compute throughput is unaffected). See `_ReportWorker.run()` in
  `modlist_compare/dialog.py`.
- **Modal `QProgressDialog.setValue()` pumps the event loop** (`processEvents`) from
  inside your slot, re-entering arbitrary event handlers — observed running a
  third-party plugin's handler for 9 s nested inside our progress update, and executing
  our own completion path inside a `setValue` frame. Use a plain `QDialog` +
  `QProgressBar` instead; it also avoids QProgressDialog's cancel-hides-the-dialog
  behavior and its workarounds.
- **Test in a real modded setup, not vanilla MO2.** The freeze only manifested with the
  user's modlist because a bundled plugin (`HideButtonsBiggieEdition.py`) rescans the
  whole widget tree on the main thread — likely triggered by our own dialog appearing.
  Pure-Python probes outside MO2 can exonerate your code but cannot reproduce host-app
  interactions.
- **Debugging an in-MO2 freeze:** instrument the installed plugin with (a) a log file in
  `%TEMP%` stamping thread ids, (b) signal emissions vs. slot deliveries, (c) a 500 ms
  `QTimer` heartbeat proving the event loop spins, and (d) a watchdog thread dumping the
  main thread's stack via `sys._current_frames()` every 2 s. The watchdog names the
  exact main-thread blocker; emission-vs-delivery gaps show whether the loop is running.
- Already encoded in code comments but worth repeating: exceptions escaping a Qt slot
  hit `qFatal()` and abort MO2; destroying a running `QThread` is likewise fatal — emit
  a done signal from a `finally` and `wait()` before dropping the thread.
