# NoDelete Tagger and Indexer

A Mod Organizer 2 (MO2) plugin for managing `[NoDelete]` tags, numerical indexes, and
separator name tags by section. Designed for Wabbajack users who need to preserve custom
mods — and their exact order — across modlist updates.

**Published on Nexus:** [NoDelete Tagger and Indexer](https://www.nexusmods.com/skyrimspecialedition/mods/157026)

## Why

Wabbajack deletes mods it doesn't recognize when updating a modlist. Prefixing a mod's name
with `[NoDelete]` protects it, but tagging (and untagging) mods one at a time is tedious,
and a plain tag doesn't preserve *where* the mod sat in your load order. This plugin tags
whole separator sections at once and can embed a sortable index in each name so the original
order can be restored after an update.

## Tag Format

```
[NoDelete] [009.00001] [Section Name] Mod Name
```

Everything after `[NoDelete]` is optional:

- **`[NoDelete]`** — protects the mod from deletion during Wabbajack updates
- **`[009.00001]`** — numerical index: 3-digit section number, dot, 5-digit position within
  the section (separators get position `00000`). Sorting tagged mods by name reproduces
  their original order.
- **`[Section Name]`** — the separator the mod belongs to, for identification after an
  update shuffles things

Only indexes in the exact `[###.#####]` format are ever touched — a tag like `[v1.2]` in a
mod's name is left alone.

## The Three Tools

The plugin registers three entries under MO2's Tools menu:

1. **Add or Remove [NoDelete] tags** — the main dialog. Lists your separator sections with
   checkboxes (with mod counts); select sections and add or remove tags in bulk. Two
   options when adding: also add numerical indexes, and also add the separator name as a
   tag. Removing `[NoDelete]` automatically strips the index and separator tags too.
2. **Update [NoDelete] Mods** — bulk-maintains all currently tagged mods: recalculate
   indexes to match the current order, and add or remove separator name tags.
3. **Remove Indexes** — strips `[###.#####]` indexes from **all** mods (tagged or not)
   while leaving `[NoDelete]` tags in place.

## Installation

Copy `no_delete_tagger.py` into your MO2 installation's `plugins/` directory and restart
MO2. Works on both PyQt6 (MO2 2.5.0+) and PyQt5 (older MO2) — the plugin falls back
automatically.

## Technical Notes

- Renames are performed in a tight loop over `allModsByProfilePriority()` with a single
  `refresh()` at the end (the "LazyModlist" approach) — no UI event processing mid-run, so
  mod order can't be corrupted by MO2 reacting to partial state. The UI is briefly
  unresponsive during processing; a message box warns before starting.
- Sections are derived from separators; mods above the first separator land in an
  implicit "Unsectioned" section.
- Empty separators are only selectable if they already carry a `[NoDelete]` tag (so you can
  untag them); otherwise they're shown as inert labels.
