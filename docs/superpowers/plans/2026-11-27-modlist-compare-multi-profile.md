# Modlist Compare: profile-to-profile + Rebase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let either side of the plugin's Generate Reports dialog be any MO2 profile, and add a Rebase worklist report (new base → custom, filtered by an old-base JSON).

**Architecture:** `exporter_core` gains a `modlist.txt`-based export for non-active profiles that shares its per-entry builders with the live export. `report_runner` gains a `rebase` report type that calls the existing `generate_coverage.generate(base_data=…)`. `dialog` gets a profile-aware side picker and a "Previous base" row. Generators, matching, CLI and `regenerate.py` are untouched.

**Tech Stack:** Python stdlib + PyQt6 (dialog only), `unittest`, MO2 2.5.0+ `mobase`.

**Spec:** [docs/superpowers/specs/2026-11-27-modlist-compare-multi-profile-design.md](../specs/2026-11-27-modlist-compare-multi-profile-design.md)

**Before Task 1:** file a GitHub Issue for this work (repo rule) and put `refs #N` in every commit message below.

## Global Constraints

- MO2 2.5.0+, PyQt6 only; `exporter_core.py` and `report_runner.py` stay Qt-free, and `mobase` is imported lazily inside functions only.
- Output naming only through `modlist_utils.resolve_output_path`; rebase stem is `"<list1> (from <base>)"`, type `rebase`, ext `html`.
- A profile side is named after the **profile**; an exported profile has the same JSON shape as `export_modlist` (see `mo2-plugins/modlist_compare/FORMAT_SPECIFICATION.md`).
- Every mod/separator-name comparison is case-insensitive (`modlist_utils.name_key`); do not add raw `==` between names.
- No changes to `tools/generate_*.py`, `tools/modlist_utils.py`, `tools/regenerate.py`.
- Unit-test commands, from the repo root: `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v`.

## Review Focus

1. `modlist.txt` with CRLF line endings, the `# This file was automatically generated…` header, blank lines, and a UTF-8 non-ASCII mod name must parse cleanly (Task 1).
2. A `modlist.txt` entry with no folder under `mods/` is skipped, not an exception (Task 1).
3. Both sides resolving to the same name (profile vs JSON stem, or the same profile twice) must be refused, not overwrite (Task 2).
4. Rebase requested with no previous-base file is refused with a clear message (Task 2, Task 3).
5. A profile that is disabled-only or empty exports `[]` and still reports (Task 1).

## File Structure

- Modify `mo2-plugins/modlist_compare/exporter_core.py`: item builders, `parse_modlist_txt`, `export_profile_from_files`, `list_profiles`, `profile_dir`, `export_profile`.
- Modify `mo2-plugins/modlist_compare/report_runner.py`: `rebase` type, `base` arg, `ListSide.from_profile`, `validate_run`.
- Modify `mo2-plugins/modlist_compare/dialog.py`: profile-aware `_SidePicker`, Rebase checkbox + Previous base row, persistence.
- Modify `mo2-plugins/modlist_compare/plugin_tools.py`: `VERSION`.
- Modify tests `test_exporter_core.py`, `test_report_runner.py`; docs `README.md` (plugin), `nexus/NEXUS_DESCRIPTION.bbcode`, `nexus/NEXUS_SHORT_DESCRIPTION.txt`, `FORMAT_SPECIFICATION.md`.

---

### Task 1: Profile export in `exporter_core`

**Files:**
- Modify: `mo2-plugins/modlist_compare/exporter_core.py`
- Test: `mo2-plugins/modlist_compare/test_exporter_core.py`

**Interfaces:**
- Produces (all in `exporter_core`):
  - `parse_modlist_txt(text: str) -> list[tuple[str, bool]]`: file order (highest priority first); `+` → True, `-` → False; `*` unmanaged, `#` comments and blanks skipped; `\r\n` tolerated.
  - `make_separator_item(mod_name: str, order: int) -> dict`
  - `make_mod_item(mod_name: str, current_separator: str, nexus_id: int, mod_path: str, active: bool, order: int) -> dict`: `id` is `nexus_id` when `> 0` else the tag-stripped name.
  - `export_profile_from_files(profile_dir: str, mods_path: str) -> list[dict]`: top-to-bottom order (reverse of file), entries with no folder in `mods_path` skipped, separators by `_separator` suffix, nexus id = `int(meta.ini modid)` or `0` when blank or invalid.
  - `list_profiles(organizer) -> list[str]`, `active_profile_name(organizer) -> str`, `profile_dir(organizer, name: str) -> str`, `export_profile(organizer, name: str) -> list[dict]`.

- [ ] **Step 1: Write failing tests** in `test_exporter_core.py` (new `unittest.TestCase` classes; use `tempfile.TemporaryDirectory`, and small fake organizer classes defined in the test file):
  - `TestParseModlistTxt.test_skips_header_blanks_unmanaged_and_reads_state`: input `"# header\r\n+Mod A\r\n-Mod B\r\n*DLC\r\n\r\n+Sep_separator\r\n+Ünïcode\r\n"` → `[("Mod A", True), ("Mod B", False), ("Sep_separator", True), ("Ünïcode", True)]`.
  - `TestExportProfileFromFiles.test_order_separator_flags_and_ids`: mods dir has folders `Mod A` (with `meta.ini` `modid=5`, file `a.esp`) and `Sep_separator`, but **no** folder `Mod B`; `modlist.txt` = `"+Mod A\n-Mod B\n+Sep_separator\n"`. Assert result is 2 items: `[0]` has `type == "separator"`, `separatorName == "Sep"`, `order == 0`; `[1]` has `type == "mod"`, `id == 5`, `separatorName == "Sep"`, `plugins == ["a.esp"]`, `active is True`, `order == 1`.
  - `test_mod_without_modid_uses_clean_name_as_id`: folder `[Tag] Plain` (no `meta.ini`) listed as `-[Tag] Plain` → item `id == "Plain"`, `tags == ["Tag"]`, `active is False`.
  - `test_empty_profile_returns_empty_list`: `modlist.txt` containing only the header → `[]`.
  - `TestProfileListing`: fake organizer with `profileNames()`, `profileName()`, `getProfile(name)` (object with `absolutePath()`) → `list_profiles`, `active_profile_name`, `profile_dir` return those; a second fake lacking `profileNames`/`getProfile` but with `profilePath()` returning `<tmp>/profiles/Active` and real subfolders `Active`, `Other` (each with a `modlist.txt`) plus a stray folder without one → `list_profiles == ["Active", "Other"]` (sorted), `profile_dir(org, "Other") == <tmp>/profiles/Other`.
  - `test_export_profile_active_uses_live_export`: patch `exporter_core.export_modlist` with `unittest.mock.patch`; `export_profile(fake, "Active")` returns its value and never reads `modlist.txt`.

- [ ] **Step 2: Run tests, expect FAIL** (`AttributeError: module 'exporter_core' has no attribute 'parse_modlist_txt'`):
  `python -m unittest mo2-plugins/modlist_compare/test_exporter_core.py -v` run from the repo root with `PYTHONPATH=mo2-plugins`; or use the discover command from Global Constraints.

- [ ] **Step 3: Implement** the Interfaces above in `exporter_core.py`.
  - Extract the two dict literals from `export_modlist` into `make_separator_item` / `make_mod_item` verbatim (same keys: `id,type,separatorName,modName,displayName,plugins,general,installed,order,tags,active`), then make `export_modlist` call them. Behavior of the live export must not change.
  - `modlist.txt` is read as UTF-8; mods path for the organizer variant is `organizer.modsPath()`.
  - `list_profiles`: try `organizer.profileNames()`; on `AttributeError` scan `os.path.dirname(organizer.profilePath())` for subfolders containing `modlist.txt`, sorted. `profile_dir`: try `organizer.getProfile(name).absolutePath()` (treat `None` result or `AttributeError` as fallback to `join(dirname(profilePath()), name)`).
  - `export_profile`: `name` equal (via `name_key`-style `casefold()`) to `active_profile_name` → `export_modlist(organizer)`; else `export_profile_from_files(profile_dir(...), organizer.modsPath())`.

- [ ] **Step 4: Run tests, expect PASS** (full plugin suite via the discover command; the existing exporter tests must still pass).

- [ ] **Step 5: Commit**
```bash
git add mo2-plugins/modlist_compare/exporter_core.py mo2-plugins/modlist_compare/test_exporter_core.py
git commit -m "feat(plugin): export any MO2 profile from modlist.txt (refs #N)"
```

---

### Task 2: Rebase report and run validation in `report_runner`

**Files:**
- Modify: `mo2-plugins/modlist_compare/report_runner.py`
- Test: `mo2-plugins/modlist_compare/test_report_runner.py`

**Interfaces:**
- Consumes: `generate_coverage.generate(source_data, target_data, source_name, target_name, min_confidence, ignore, base_data, base_name, progress)`; `modlist_utils.resolve_output_path(..., first_name=…)`.
- Produces:
  - `REPORT_TYPES = ("coverage", "diff", "changelog", "rebase")`; `_EXTENSIONS["rebase"] = "html"`.
  - `ListSide.from_profile: bool = False`, which **replaces** `ListSide.live` (rename everywhere, including the existing test `test_loads_name_and_data`, which asserts `assertFalse(side.live)`).
  - `run_reports(list1, list2, report_types, dest_dir, save_exports=True, min_confidence=0.80, progress=None, base=None)`: `rebase` uses `list1` as source, `list2` as target, `base` as old base; written to `<dest>/<list2.name>/<list1.name> (from <base.name>).rebase.html`; reads the same `.coverage-ignore.txt` as coverage; reports no sub-progress. `base is None` with `rebase` selected lands in `RunResult.errors` as `"rebase: a previous-base list is required"`.
  - `validate_run(list1, list2, report_types, base=None) -> str | None`: an error message or `None`.

- [ ] **Step 1: Write failing tests** in `test_report_runner.py`:
  - `test_rebase_writes_cli_named_report`: `run_reports(_side(NEW_LIST), _side(OLD_LIST), ["rebase"], tmp, save_exports=False, base=_side(OLD_LIST))` → `errors == []`, one written path equal to `join(tmp, "Example List 1.0", "Example List 1.1 (from Example List 1.0).rebase.html")`, file non-empty.
  - `test_rebase_without_base_is_an_error_and_other_reports_still_run`: `["rebase", "changelog"]`, `base=None` → `errors == ["rebase: a previous-base list is required"]` and the changelog is written.
  - `test_save_exports_writes_every_profile_side`: two `ListSide(..., from_profile=True)` built from the example data with names `"Base"` and `"Custom"`; `save_exports=True`, `report_types=[]` → both `Base.json` and `Custom.json` exist in `tmp`.
  - `TestValidateRun`: same `name` on both sides → message containing `"same name"`; `"rebase"` selected with `base=None` → message containing `"previous base"`; distinct names, no rebase → `None`.

- [ ] **Step 2: Run tests, expect FAIL** (unknown `from_profile` / `base` argument / `validate_run`).

- [ ] **Step 3: Implement** the Interfaces. In the `run_reports` loop add an `elif rtype == "rebase":` branch: raise `ValueError("a previous-base list is required")` when `base is None` (the existing handler formats it as `"rebase: …"`); otherwise load the ignore set exactly as for coverage and call `generate_coverage.generate(list1.data, list2.data, list1.name, list2.name, min_confidence=min_confidence, ignore=ignore, base_data=base.data, base_name=base.name)`. Compute `out_path` with `first_name=f"{list1.name} (from {base.name})"` only for rebase. Update the `save_exports` loop and docstrings for the rename. `validate_run` compares names with `modlist_utils.name_key`.

- [ ] **Step 4: Run tests, expect PASS** (full plugin suite; also `cd tools && python -m unittest test_package_plugin -v`, since the vendored copy must still package).

- [ ] **Step 5: Commit**
```bash
git add mo2-plugins/modlist_compare/report_runner.py mo2-plugins/modlist_compare/test_report_runner.py
git commit -m "feat(plugin): rebase worklist report and run validation (refs #N)"
```

---

### Task 3: Dialog: profile picker and Previous base

**Files:**
- Modify: `mo2-plugins/modlist_compare/dialog.py`

**Interfaces:**
- Consumes: `exporter_core.list_profiles`, `active_profile_name`, `export_profile`; `report_runner.ListSide(name, data, from_profile)`, `validate_run`, `run_reports(..., base=…)`.
- Produces: no new public API. UI behavior below.

This module is Qt/mobase-bound and has no unit tests in the repo; verification is Task 5.

- [ ] **Step 1: Side picker.** `_SidePicker.__init__(on_browse, active, profiles)`: combo items are `Current profile (<active>)`, each other profile name, then `JSON file…`. Replace `is_live()` with `selection() -> tuple[str, str]` returning `("profile", <profile name>)` or `("file", "")` (the current-profile item maps to the active name). The path field and Browse stay enabled only for `JSON file…`. Update the combo tooltip to mention any profile.

- [ ] **Step 2: Resolve.** `_resolve_side` calls `exporter_core.export_profile(self._organizer, name)` for a profile selection (same try/except, same warning text with "profile" wording) and returns `ListSide(name=<profile name>, data=data, from_profile=True)`. File selections are unchanged.

- [ ] **Step 3: Rebase UI.** Add a `Rebase` report checkbox (tooltip: "Only what changed in the base update: List 1 = new base, List 2 = your custom list. Needs the previous base JSON.") and a `Previous base:` row (read-only path field + Browse, JSON only, reuses `browse_dir`). Extend the `list_hint` text to explain Rebase's List 1/List 2 roles. Rename the export checkbox to `Save profile exports as JSON`.

- [ ] **Step 4: Generate guards.** In `_on_generate` replace the "both sides current profile" check with: both profile selections with the same name → warn "Both sides are the same profile — pick a different one." Keep the same-file check. Load the previous-base file via `report_runner.load_side_from_file` when Rebase is checked (warn on failure; warn if empty). After both sides resolve, call `report_runner.validate_run(side1, side2, report_types, base)` and warn with its message. Pass `base` through `_ReportWorker` to `run_reports`.

- [ ] **Step 5: Persistence.** Persist and restore the two side selections (combo text) and the previous-base browse directory using the existing `_get`/`_set`; restore a saved selection only if still present in the combo. Add `rebase` to the saved `reports` list handling (`_restore_state` / `_save_state` already iterate `_report_boxes`).

- [ ] **Step 6: Import check.** `python -c "import ast,sys; ast.parse(open('mo2-plugins/modlist_compare/dialog.py', encoding='utf-8').read())"` exits 0; run the full plugin suite to confirm nothing else broke.

- [ ] **Step 7: Commit**
```bash
git add mo2-plugins/modlist_compare/dialog.py
git commit -m "feat(plugin): profile picker and rebase options in Generate Reports (refs #N)"
```

---

### Task 4: Version and documentation

**Files:**
- Modify: `mo2-plugins/modlist_compare/plugin_tools.py` (`VERSION` → `mobase.VersionInfo(1, 2, 0)`)
- Modify: `mo2-plugins/modlist_compare/README.md`, `nexus/NEXUS_DESCRIPTION.bbcode`, `nexus/NEXUS_SHORT_DESCRIPTION.txt`, `FORMAT_SPECIFICATION.md`

- [ ] **Step 1:** `grep` for the version string `1.1.0` / `1, 1, 0` under `mo2-plugins/` and `tools/package_plugin.py` and bump every plugin-version occurrence to 1.2.0 (the packaged zip name derives from it).
- [ ] **Step 2: README.** Generate Reports: each side can be the current profile, any other profile, or a JSON file; add a **Rebase worklist** subsection (List 1 = new base, List 2 = custom, Previous base = JSON of the old base, output name `<List 1> (from <Previous base>).rebase.html`, link the root README § Base update mode); rename the save-export option.
- [ ] **Step 3: Nexus text.** Replace "at least one side a file" / "current profile" wording in `NEXUS_DESCRIPTION.bbcode` and the short description with any-profile wording and a Rebase bullet.
- [ ] **Step 4: FORMAT_SPECIFICATION.** In the exporter section (near line 293) note that non-active profiles are read from `modlist.txt` plus each mod's `meta.ini`, producing the same structure.
- [ ] **Step 5: Verify + commit.** Run `python tools/package_plugin.py` (exit 0, zip named with the new version) and the full plugin suite plus the `tools/` suite from the CLAUDE.md Testing section.
```bash
git add -A mo2-plugins
git commit -m "docs(plugin): profile comparison and rebase worklist, v1.2.0 (refs #N)"
```

---

### Task 5: Manual verification in a real MO2 (resolves the spec's open items)

No file changes unless a check fails. Install the packaged zip from `dist/` into a real MO2 `plugins/` folder and restart.

- [ ] **Step 1: Python exposure.** In MO2's Python console (or a throwaway one-line `print` in the dialog), confirm `organizer.profileNames()` and `organizer.getProfile(name).absolutePath()` work. If either is missing, the `exporter_core` fallbacks must have been exercised instead: confirm the profile combo still lists every profile.
- [ ] **Step 2: Order and parity.** Export the **active** profile via Tools → Export Modlist to JSON and save/rename it to `<P>-live.json` (a distinct filename: `<P>.json` has the same name as profile `<P>`, so `validate_run` would reject the comparison), then run Generate Reports with *List 1 = that JSON*, *List 2 = the same profile selected as a non-active profile entry* (switch MO2's active profile first so the profile under test is non-active) and Changelog + Diff. Expect no added/removed/moved/updated mods. A reversed list shows up as everything moved; a Nexus-id mismatch shows up as updated/renamed mods. Fix `export_profile_from_files` ordering or id handling if either appears.
- [ ] **Step 3: Rebase end to end.** Pick a base profile and a derived custom profile plus a saved JSON of an earlier base state; run Rebase with *List 1 = base profile*, *List 2 = custom profile*, *Previous base = the JSON*. Open the written `<List 1> (from <Previous base>).rebase.html` and confirm it lists only base changes plus the "Removed in base update" section.
- [ ] **Step 4: Guards.** Confirm warnings for: same profile on both sides; Rebase checked with no previous base; Cancel mid-run still leaves the dialog responsive (existing worker behavior unchanged).
- [ ] **Step 5:** Record results in the PR description; open the PR per the repo's PR workflow (feature branch, `Closes #N`).

---

## Self-review

- **Spec coverage:** §1 export → Task 1; §2 dialog → Task 3; §3 runner → Task 2; §4 naming and collision → Task 2 (`validate_run`) + Task 3; §5 tests/docs → Tasks 1, 2, 4; open items 1–3 → Task 5 (items 1–3 map to Steps 1, 2, 2).
- **Type consistency:** `ListSide.from_profile` (Task 2) is what Task 3 constructs; `validate_run` and the `base` argument signatures match between Tasks 2 and 3; `export_profile(organizer, name)` matches between Tasks 1 and 3.
- **Known gap:** `dialog.py` has no automated tests (repo convention: Qt/mobase-bound, verified in MO2), covered by Task 5.
