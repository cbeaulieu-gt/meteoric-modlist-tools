# Download Copier for Shared Download Folder Enjoyers

A Mod Organizer 2 (MO2) plugin that copies the download archives for every installed mod
(active *and* inactive) from a shared download folder into the pristine, per-instance
download folder structure that Wabbajack list creation requires.

**Published on Nexus:** [Download Copier for Shared Download Folder Enjoyers](https://www.nexusmods.com/skyrimspecialedition/mods/158127)

## Why

Many mod authors point every MO2 instance at one big shared downloads folder to avoid
re-downloading archives. Wabbajack, however, wants a clean downloads folder containing
exactly the archives (plus their `.meta` files) used by the list being compiled. This
plugin builds that folder automatically: it resolves each installed mod back to its
download archive and copies archive + `.meta` into a destination of your choice.

## Usage

1. In MO2, open the Tools menu and select **Copy Downloads from Shared Folder**.
2. The dialog scans your modlist and shows three tabs:
   - **Found Downloads** — mods whose archive was located in the current downloads folder
   - **Missing Downloads** — mods with no archive, an archive outside the downloads
     folder, or a nonexistent file (each with the reason)
   - **Debug Info** — raw details for troubleshooting
3. Pick a destination (defaults to `<MO2 instance>/downloads`). The dialog shows the total
   copy size and free disk space on the target drive, updating as you change the path.
4. Start the copy. It runs on a worker thread with a progress bar; files already present at
   the destination with the same size are skipped, and each archive's `.meta` file is
   copied alongside it (missing `.meta` files are reported — Wabbajack needs them for Nexus
   IDs and versions).
5. A missing-downloads report can be written as a text file so you know what to
   re-download by hand.

## Caveats

- Only files that live in the instance's **current downloads folder** are copied; archives
  installed from elsewhere are listed under Missing Downloads instead.
- For merged mods, MO2 only records the *last* archive installed into the mod, so only that
  one is detected. Wabbajack needs all of the original individual downloads — check merged
  mods manually.

## Installation

Copy this whole `wabbajack_download_copier/` folder into your MO2 installation's
`plugins/` directory and restart MO2. Requires MO2 **2.5.0 or later** (the plugin imports
PyQt6).

## Structure

- [plugin.py](plugin.py) — `IPluginTool` registration
- [dialog.py](dialog.py) — the main dialog (scan results, destination picker, progress)
- [scanner.py](scanner.py) — resolves installed mods to their download archives and builds
  the missing-downloads report
- [copier.py](copier.py) — threaded copy worker (archive + `.meta`, size-based skip)
- [utils.py](utils.py) — file-size formatting and disk-space queries
