# Modlist Compare — MO2 plugin

Export your active Mod Organizer 2 modlist to JSON and compare two modlists without leaving MO2.
The plugin adds a **Modlist Compare** submenu to MO2's Tools menu with two entries: one that
writes the current profile's modlist to a JSON file, and one that generates coverage, diff, and
changelog reports between any two lists — an exported JSON file, your current profile, or one of
each. The reports are the same ones the
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

- **List 1 (source / old)** and **List 2 (target / new)** — each side is either
  *Current profile* (exported live, in memory) or *JSON file…* (**Browse…** to pick an export).
  At least one side must be a file; both sides live, or both sides the same file, is rejected.
- **Reports** — any combination of **Coverage**, **Diff**, and **Changelog**.
  - *Coverage* — what List 2 is missing or behind on compared to List 1 (HTML).
  - *Diff* — both lists' full ordering side by side, colour-coded (HTML).
  - *Changelog* — added / removed / updated mods, List 1 → List 2 (markdown).
- **Destination folder** — where the reports are written.
- **Save "Current profile" export as JSON** — when a side is the live profile, also drop that
  export in the destination folder so the comparison is reproducible later.

**Generate** writes the files and reports what was written (a per-report failure is listed as an
error; the other reports still run). **Open Folder** in the result dialog opens the destination.
All dialog settings — destination, selected report types, the save-export checkbox, the last
browse folder — persist across MO2 restarts.

## Report naming and CLI interop

Reports are named exactly like the CLI tools' directory mode:

```
<destination>/<List 2 name>/<List 1 name>.<type>.<ext>
```

`<type>` is `coverage`, `diff`, or `changelog`; the extension is `html` for the first two and
`md` for the changelog. A list's "name" is the JSON file's basename without extension, or —
for the live profile — the suggested export name. So pointing the plugin at the same `output/`
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
`dist/modlist-compare-<version>.zip`, excluding `test_*.py` and `__pycache__`. The version comes
from `VERSION = mobase.VersionInfo(...)` in `plugin_tools.py`. Both `_vendor/` and `dist/` are
gitignored.

Run the plugin's tests from the repository root (they run outside MO2 — `mobase` and Qt are not
needed):

```bash
python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v
```
