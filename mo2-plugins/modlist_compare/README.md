# Modlist Compare — MO2 plugin

Export your active Mod Organizer 2 modlist to JSON and compare two modlists without leaving MO2.
The plugin adds a **Modlist Compare** submenu to MO2's Tools menu with two entries: one that
writes the current profile's modlist to a JSON file, and one that generates coverage, diff, and
changelog reports (plus a rebase worklist) between any two lists — any MO2 profile or an exported
JSON file, in any combination. The reports are the same ones the
[command-line tools](../../README.md) in this repository produce, from the same code, with the
same file naming, so plugin output and CLI output are interchangeable.

## Requirements

- Mod Organizer 2 **2.5.0 or newer** (the PyQt6-based Python runtime)
- Nothing else — no third-party Python packages

## Install

1. Download / build `dist/modlist-compare-<version>.zip` (see [Development](#development)).
2. Unzip it into your MO2 installation's `plugins/` folder — the archive already contains the
   `modlist_compare/` folder, so you should end up with `plugins/modlist_compare/`.
3. Restart MO2. **Tools ▸ Modlist Compare** appears in the toolbar's tools menu.

If you installed the earlier, unreleased `modlist-json-exporter` plugin, delete that folder from
MO2's `plugins/` — this plugin absorbs it, and leaving both installed shows two export entries.

The zip is the supported install path. Copying the folder out of the repository by hand also
works *if* you have run `python tools/package_plugin.py` first (the `_vendor/` copies of the
generator modules are not committed), but you also drag along the `test_*.py` files — harmless,
MO2 never imports them, and the zip leaves them out.

## The two tools

### Modlist Compare ▸ Export Modlist to JSON

Asks where to save, then writes the active profile's modlist as JSON. The suggested filename
comes from the list's first separator. This is the export the CLI tools consume.

### Modlist Compare ▸ Generate Reports…

Opens a dialog:

- **List 1 (source / old)** and **List 2 (target / new)** — each side is one of:
  *Current profile (name)* (exported live, in memory), any other MO2 profile, or
  *JSON file…* (**Browse…** to pick an export). Both sides may be profiles, files, or one of
  each; picking the same profile on both sides, or the same file on both, is rejected.
  A non-active profile is read from its `modlist.txt` plus each mod's `meta.ini`; an entry
  whose mod folder is missing is skipped, and an installed mod the file does not list is
  included as disabled, placed last. A profile side is named after the profile.
- **Reports** — any combination of **Coverage**, **Diff**, **Changelog**, and **Rebase**.
  - *Coverage* — what List 2 is missing or behind on compared to List 1 (HTML).
  - *Diff* — both lists' full ordering side by side, colour-coded (HTML).
  - *Changelog* — added / removed / updated mods, List 1 → List 2 (markdown).
  - *Rebase* — a worklist of only what changed in a base update (HTML); see
    [Rebase worklist](#rebase-worklist).
- **Previous base** — a JSON file, used only by the Rebase report.
- **Destination folder** — where the reports are written.
- **Save profile exports as JSON** — also drop each profile side's export in the destination
  folder, so the comparison is reproducible later (and usable as a Previous base).

**Generate** writes the files and reports what was written (a per-report failure is listed as an
error; the other reports still run). **Open Folder** in the result dialog opens the destination.
All dialog settings — destination, selected report types, the save-export checkbox, the last
browse folder — persist across MO2 restarts.

While reports generate, a progress dialog shows live percent and which report is running; MO2
stays responsive. Closing that dialog by any route — the **Cancel** button, the window's X, or
Esc — requests cancellation; the run stops at the next checkpoint and the progress dialog closes
itself then, leaving the Generate Reports dialog open. Reports already written stay on disk, the
in-progress one is discarded, and profile JSON exports are skipped. Any report written
before the cancel is still listed. Hover the list, report, and save-export controls for a short
explanation of what each does; short hints also sit under the list rows and the destination row.

### Rebase worklist

For a custom list that tracks an upstream base. Set **List 1** to the *new* base, **List 2** to
your custom list, and **Previous base** to a JSON export of the *old* base (for example, a
profile export you saved earlier with **Save profile exports as JSON**). The report keeps only
what changed in the base update — version bumps, plugin-set changes, new mods, and a "Removed in
base update" section — and drops everything unchanged, including your own deviations from the
base. It is the same report as the CLI's `--base` mode; see
[Base update mode](../../README.md#base-update-mode).

The output is `<destination>/<List 2 name>/<List 1 name> (from <Previous base name>).rebase.html`.
It shares List 2's `.coverage-ignore.txt` with the Coverage report. Rebase requires a Previous
base; that path is not remembered between sessions (the other dialog settings are). If a profile
side has the same name as the Previous base while **Save profile exports as JSON** is on, the run
is refused, because the export would overwrite the Previous base file — untick the option or
rename the base file.

## Report naming and CLI interop

Reports are named exactly like the CLI tools' directory mode:

```
<destination>/<List 2 name>/<List 1 name>.<type>.<ext>
```

`<type>` is `coverage`, `diff`, `changelog`, or `rebase`; the extension is `html` for all but the
changelog, which is `md`. (Rebase reports are named `<List 1 name> (from <Previous base name>).rebase.html`.)
A list's "name" is the JSON file's basename without extension, or — for a profile side — the
profile's name — including the current profile, which earlier versions named after its first
separator, so move any old report folders and `.coverage-ignore.txt` files to the profile name.
So pointing the plugin at the same `output/`
folder the CLI tools use drops the reports in the same per-target subfolders, and
`python tools/regenerate.py "<List 2 name>"` refreshes them afterwards — with `--lists` pointed
at wherever the exported JSONs live, since `regenerate.py` looks in `lists/` by default while
the plugin's live export lands in the destination folder.

Coverage also honours the per-target ignore file
`<destination>/<List 2 name>/.coverage-ignore.txt` — the same file the CLI coverage tool and its
`--serve` mode read and write. Mods listed there render muted with a `⊘` marker and drop out of
the actionable counts. The plugin only reads it; use `python tools/generate_coverage.py … --serve`
(or a text editor) to change it.

## JSON format

Documented in [FORMAT_SPECIFICATION.md](FORMAT_SPECIFICATION.md) — the same format the CLI tools
expect.

## Known limitation

The generator modules are vendored into `_vendor/` and imported under their plain module names
(`modlist_utils`, `generate_coverage`, `generate_diff`, `generate_changelog`, `coverage_ignore`),
because they import each other as siblings. They therefore occupy those plain names in
`sys.modules` for the whole MO2 session. If another MO2 Python plugin ships a top-level module
with one of those names, whichever loads first wins and the other gets the wrong module. No such
collision is known, but the names are generic enough that it is theoretically possible.

## Development

The plugin lives in the
[meteoric-modlist-tools](../../README.md) repository as `mo2-plugins/modlist_compare/`.

Build the release archive from the repository root:

```bash
python tools/package_plugin.py
```

This copies the five generator modules from `tools/` into `mo2-plugins/modlist_compare/_vendor/`
(byte-identical — the plugin and the CLI run the same code) and writes
`dist/modlist-compare-<version>.zip`, excluding `test_*.py`, `__pycache__`, and `nexus/`. The version comes
from `VERSION = mobase.VersionInfo(...)` in `plugin_tools.py`. Both `_vendor/` and `dist/` are
gitignored.

The plugin's Nexus Mods page is maintained in the repo under [nexus/](nexus/):
[NEXUS_SHORT_DESCRIPTION.txt](nexus/NEXUS_SHORT_DESCRIPTION.txt) (the mod-card
blurb — one line, max 350 characters, enforced by `test_nexus_description`),
[NEXUS_DESCRIPTION.bbcode](nexus/NEXUS_DESCRIPTION.bbcode) (the full
description, raw Nexus BBCode), and the page's images. None of it ships in
the plugin zip. Open `tools/nexus_bbcode_editor.html` in a
browser to edit with a live preview — load or paste the files, tweak, then
copy each field back to its file and into the matching Nexus form field.
The preview is an approximation; Nexus's own preview is the final authority.

Run the plugin's tests from the repository root (they run outside MO2 — `mobase` and Qt are not
needed):

```bash
python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v
```
