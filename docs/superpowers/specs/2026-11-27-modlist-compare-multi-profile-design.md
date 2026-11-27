# Modlist Compare: profile-to-profile comparison and Rebase report

Date: 2026-11-27 · Status: draft for approval · Size: project (one plugin, no generator changes)

## Intent

The user maintains a customized MO2 profile derived from a **base profile**. When the base
changes, they need to see what to port into the custom profile. Today the Modlist Compare
plugin can only compare the *active* profile against a JSON file, so two profiles in one MO2
session can't be compared without exporting one by hand first. The base-update worklist
(`generate_coverage --base`, README § Base update mode) is the right report for this job, but the
plugin doesn't expose it.

## Goals

1. Either side of Generate Reports can be any MO2 profile, not just the active one.
2. A new **Rebase worklist** report type: new base → custom, filtered to what the base update
   changed, using an old-base JSON as the reference.
3. Profile exports are identical in shape to today's live export, so every existing report works
   on them unchanged.

## Non-goals

- **Snapshotting.** No automatic saving of a base profile before it's updated. The user supplies
  the old base as an existing JSON file (for example, a previous "save export as JSON"). Revisit
  once the rebase report's usefulness is judged.
- Changes to `generate_*`, matching, `modlist_utils`, the CLI, or `regenerate.py`.
- Extending Tools → Export Modlist to JSON to other profiles.
- Switching the active profile or touching MO2 state.

## Anti-goals

- A profile export that differs from the live export for the same profile. A mod list that diffs
  against itself must show no changes.
- Two sides silently colliding on one output path (see Naming).

## Constraints

- MO2 2.5.0+, PyQt6. `exporter_core.py` and `report_runner.py` stay Qt-free and unit-testable
  outside MO2.
- The `mo2-api` skill's reference docs (`docs/mo2-api/`) are **not present in this checkout**.
  The C++ interface was checked instead (`modorganizer-uibase`, `imoinfo.h` / `iprofile.h`):
  `IOrganizer` has `profileNames()` and `getProfile(name)` (returns the profile or null), but
  `IProfile` exposes only `name()`, `absolutePath()`, save/settings/invalidation flags and INI
  paths. **It has no mod list, order, or enabled-state accessors**, so a non-active profile's
  mods can only come from its `modlist.txt`. Python-binding exposure of the two organizer methods
  is still to be confirmed (Open items).
- Output naming goes through `modlist_utils.resolve_output_path` only.

## Approaches considered

| | Description | Trade-off |
|---|---|---|
| A | Profile picker only. Plain coverage, diff, changelog between profiles. | Smallest, but base-vs-custom coverage mixes the user's own choices with real base changes. |
| **B (chosen)** | A plus an optional "Previous base" JSON and a Rebase worklist report. | Delivers the worklist; relies on the user having an old-base file. |
| C | B plus remembered Base/Custom pairing and automatic dated snapshots. | Most convenient; adds a snapshot convention the CLI lacks. Deferred by the user. |

## Design

### 1. Export any profile (`exporter_core.py`)

- `list_profiles(organizer)` returns `organizer.profileNames()`. The active profile is
  `organizer.profileName()`.
- A profile's folder comes from `organizer.getProfile(name).absolutePath()`, not from guessing
  the profiles directory.
- `export_profile(organizer, name)` builds the JSON-ready list for a **non-active** profile:
  - Parse `<profiles>/<name>/modlist.txt`. `+Name` is enabled, `-Name` is disabled, `*Name`
    (unmanaged) is skipped. The file lists highest priority first, so reverse it to get
    top-to-bottom order, matching `allModsByProfilePriority`.
  - Per-mod data comes from the shared mods folder (`organizer.modsPath()/<Name>`): plugins via
    `get_plugin_files`, `general`/`installed` via `read_meta_ini`, Nexus id from `meta.ini`
    `modid`. A name with no folder on disk is skipped, as `getMod() is None` is in the live path.
  - Separators are detected by the `_separator` name suffix, as the live path already does.
- The per-entry dict construction is extracted from `export_modlist` into one shared helper that
  both paths call, so the two cannot drift. `export_modlist` (live) stays the source for the
  active profile, which keeps unsaved in-memory state.

### 2. Dialog (`dialog.py`)

- Each side's combo lists: `Current profile (<name>)`, every other profile by name, and
  `JSON file…`. The path field and Browse button stay enabled only for `JSON file…`.
- Guards: "both sides are the same profile" replaces "both sides are the current profile".
  The existing same-file guard stays.
- `Save "Current profile" export as JSON` becomes `Save profile exports as JSON` and applies to
  any profile side, current or not.
- New report checkbox **Rebase worklist** and a **Previous base** row (JSON file only, with
  Browse). Selecting Rebase without a previous-base file warns and stops. Rebase uses List 1 as
  the new base (source) and List 2 as the custom list (target). It is coverage-only and ignores
  the diff/changelog "old/new" reading of the sides, which the hint text explains.
- Persist the last-chosen side selections and previous-base browse directory alongside the
  existing `dest_dir`/`reports` settings. Use `persistent`/`setPersistent` as today.
- Profile exports run on the main thread inside `_resolve_side`, guarded by the same try/except
  (an exception escaping a Qt slot aborts MO2). Reading `modlist.txt` and `meta.ini` is fast;
  generation stays on the existing worker thread.

### 3. Report runner (`report_runner.py`)

- `REPORT_TYPES` gains `rebase`; extension `html`.
- `run_reports` gains an optional `base` argument (a `ListSide`). For `rebase` it calls
  `generate_coverage.generate(..., base_data=base.data, base_name=base.name)` and writes through
  `resolve_output_path(..., "rebase", "html", first_name=f"{list1.name} (from {base.name})")`,
  exactly as the CLI does. It reads the same `.coverage-ignore.txt` as coverage.
- `ListSide.live` is renamed to reflect "built from a profile, no source file" so
  `save_exports` covers all profile sides. Its meaning is otherwise unchanged.
- Progress follows the existing equal-slice-per-report scheme. Rebase reports no sub-progress
  (base mode never reports progress, per `build_report`); the runner treats it as a single step.

### 4. Naming

- A profile side is named after the **profile**, not the first separator, so two profiles of
  the same list can't collide on `<list2>/<list1>.<type>`. The live "current profile" side
  switches to the same rule, so one convention covers every profile.
- If both sides resolve to the same name (for example a JSON file named like a profile), warn
  and stop rather than overwrite.

### 5. Tests and docs

- `test_exporter_core.py`: `modlist.txt` parsing (enabled, disabled, unmanaged, separators,
  reversal, missing mod folder); `list_profiles`; **parity** between `export_profile` and the
  shared builder against a synthetic mods folder.
- `test_report_runner.py`: rebase output path and content; error when `base` is missing;
  `save_exports` writes for non-active profile sides; same-name collision.
- Docs: plugin README (profile picker, Rebase worklist, previous base), Nexus description and
  short description, `FORMAT_SPECIFICATION.md` (profile export source), and a CLAUDE.md pointer
  if the plugin section changes.

## Left to the builder

- Exact widget layout for the Previous base row and the profile combo labels.
- Wording of warnings and tooltips.
- Whether `list_profiles` filters on `modlist.txt` presence or on any subfolder.

## Open items (need verification before implementation)

1. **Python exposure.** Confirm `profileNames()` and `getProfile()` are reachable from Python in
   MO2 2.5.x (`dir(organizer)` in a real install). If either is missing, fall back to listing
   subfolders of the profiles directory that contain a `modlist.txt`.
2. **Nexus id parity.** The live path uses `mod.nexusId()`; the profile path reads `meta.ini`
   `modid`. Confirm they agree (including mods with no id) before relying on the parity test.
3. **`modlist.txt` ordering.** Confirm in a real profile that the file lists highest priority
   first, as assumed above.

## My calls (not discussed; correct freely)

- Previous base is a JSON file only, not a profile, since a profile can't be an older version of
  itself.
- Profile-name naming replaces separator-name naming for the live side too.
- Rebase is coverage-only and reuses the target's `.coverage-ignore.txt`.
- Parsing `modlist.txt` is required for non-active profiles: the profile API has no mod list.
