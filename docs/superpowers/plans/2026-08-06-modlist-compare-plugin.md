# Modlist Compare MO2 Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One installable MO2 plugin (`mo2-plugins/modlist_compare/`) that exports the live modlist to JSON and generates coverage/diff/changelog reports from inside MO2, backed by a library-API refactor of the `tools/` generators.

**Architecture:** The three `tools/` generators each gain a pure `generate(...) → str` entry function (data-in, text-out); `main()` becomes a thin CLI shim. The plugin is a Python package: two thin `IPluginTool`s (submenu via `displayName()` `"Modlist Compare/…"` prefix), a Qt-free `report_runner`, a PyQt6 dialog, and a `_vendor/` folder that `tools/package_plugin.py` fills with byte-identical copies of the tool modules at package time.

**Tech Stack:** Python 3 stdlib only; PyQt6 + mobase inside MO2 (2.5.0+). Tests via `unittest`. Spec: [docs/design/2026-08-06-modlist-compare-plugin-design.md](../../design/2026-08-06-modlist-compare-plugin-design.md).

**Global Constraints:**
- CLI behavior and output must be byte-identical after the refactor: `python tools/regenerate.py "Example List 1.1" --lists examples/lists --output examples/reports` then `git diff --exit-code examples/reports` must pass (the examples smoke test).
- Entry functions are pure: no filesystem, argparse, or path-convention knowledge. Callers own IO; report naming always goes through `modlist_utils.resolve_output_path`.
- Vendored files in `_vendor/` are unmodified copies of `tools/` files — no rewrite step, ever.
- Plugin folder is `modlist_compare` (underscore): MO2 imports package plugins by folder name, so it must be a valid Python identifier. The release zip is `dist/modlist-compare-<version>.zip`.
- mobase/PyQt6 imports must not be required to import `exporter_core` helpers or `report_runner` (unit-testable outside MO2). `mobase` is imported lazily inside `export_modlist`; `__init__.py` only registers plugins when `mobase` is importable.
- Every name-identity rule from CLAUDE.md (case-insensitive via `name_key`, etc.) is inside the generators — the plugin must not add its own matching logic.

**User decisions (already made):**
- v1 reports: static coverage, diff, changelog. No `--serve`, no `--base` rebase mode.
- Both sides of the comparison are user-picked; "Current profile" (live in-memory export) is a selectable option on either side.
- "Save Current profile export as JSON" checkbox, on by default, writes `<dest>/<name>.json`.
- Vendor at package time; `_vendor/` gitignored (except `__init__.py`); staleness not detected, only absence.
- Plugin/submenu name: "Modlist Compare". Old `modlist-json-exporter/` folder is absorbed (deleted; docs move).
- Tools API must stay UI-agnostic (future Claude-skill consumer planned; no skill work now).

---

## File structure

| File | Responsibility |
|---|---|
| `tools/generate_coverage.py` | + `generate(source_data, target_data, source_name, target_name, min_confidence=0.80, ignore=None, base_data=None, base_name=None) → str` |
| `tools/generate_diff.py` | + `generate(old_data, new_data, old_name, new_name, min_confidence=0.80) → str` |
| `tools/generate_changelog.py` | + `generate(old_data, new_data, min_confidence=0.80) → str` |
| `tools/package_plugin.py` | Vendor tool modules into `_vendor/`, build release zip |
| `mo2-plugins/modlist_compare/__init__.py` | `createPlugins()` (only when mobase importable) |
| `mo2-plugins/modlist_compare/plugin_tools.py` | `ExportModlistTool`, `GenerateReportsTool` (thin `IPluginTool`s) |
| `mo2-plugins/modlist_compare/exporter_core.py` | Export logic + pure helpers, extracted from the old exporter |
| `mo2-plugins/modlist_compare/report_runner.py` | Qt-free: `ListSide`, `load_side_from_file`, `run_reports` |
| `mo2-plugins/modlist_compare/dialog.py` | `GenerateReportsDialog` (PyQt6) |
| `mo2-plugins/modlist_compare/_vendor/__init__.py` | Load vendored modules; loud error when unpopulated |

Task order: 1 (tools API) and 2 (plugin skeleton) are independent; 3 (vendoring) needs 2; 4 (runner) needs 1+3; 5 (dialog) needs 4; 6 (wiring+docs) needs all.

---

### Task 1: Tools library API — `generate()` entry functions

**Goal:** Each generator exposes a pure data-in → text-out `generate()` function; `main()` becomes a thin shim; CLI output stays byte-identical.

**Files:**
- Modify: `tools/generate_coverage.py` (main() at ~856)
- Modify: `tools/generate_diff.py` (main() at ~871)
- Modify: `tools/generate_changelog.py` (main() at ~119)
- Test: `tools/test_generate_coverage.py`, `tools/test_generate_diff.py`, create `tools/test_generate_changelog.py`
- Modify: `CLAUDE.md` (add `test_generate_changelog` to the unittest command)

**Acceptance Criteria:**
- [ ] `generate_coverage.generate(...)`, `generate_diff.generate(...)`, `generate_changelog.generate(...)` exist with the exact signatures below and no file IO
- [ ] Each `generate()` output is byte-identical to the corresponding committed `examples/reports/` file (equivalence tests below)
- [ ] Examples smoke test passes: regenerate is a no-op, `git diff --exit-code examples/reports` exits 0
- [ ] Full suite green: all existing tests plus new ones

**Verify:** `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples -v` → all pass; then from repo root `python tools/regenerate.py "Example List 1.1" --lists examples/lists --output examples/reports && git diff --exit-code examples/reports` → exit 0

**Steps:**

- [ ] **Step 1: Write failing equivalence tests**

Append to `tools/test_generate_coverage.py` (it already imports `unittest`; add missing imports at top as needed — `os`, `generate_coverage`, `from modlist_utils import load_modlist`, `from coverage_ignore import load_ignore`):

```python
EXAMPLES_LISTS = os.path.join(os.path.dirname(__file__), "..", "examples", "lists")
EXAMPLES_REPORTS = os.path.join(os.path.dirname(__file__), "..", "examples", "reports")


class TestGenerateEntryPoint(unittest.TestCase):
    """generate() must reproduce the committed sample report byte-for-byte."""

    def test_generate_matches_committed_report(self):
        source = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.1.json"))
        target = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.0.json"))
        ignore = load_ignore(
            os.path.join(EXAMPLES_REPORTS, "Example List 1.0", ".coverage-ignore.txt")
        )
        html = generate_coverage.generate(
            source, target, "Example List 1.1", "Example List 1.0", ignore=ignore
        )
        committed = os.path.join(
            EXAMPLES_REPORTS, "Example List 1.0", "Example List 1.1.coverage.html"
        )
        with open(committed, "r", encoding="utf-8", newline="") as f:
            self.assertEqual(html, f.read())
```

Append to `tools/test_generate_diff.py` (same import pattern):

```python
EXAMPLES_LISTS = os.path.join(os.path.dirname(__file__), "..", "examples", "lists")
EXAMPLES_REPORTS = os.path.join(os.path.dirname(__file__), "..", "examples", "reports")


class TestGenerateEntryPoint(unittest.TestCase):
    def test_generate_matches_committed_report(self):
        old = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.0.json"))
        new = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.1.json"))
        html = generate_diff.generate(old, new, "Example List 1.0", "Example List 1.1")
        committed = os.path.join(
            EXAMPLES_REPORTS, "Example List 1.1", "Example List 1.0.diff.html"
        )
        with open(committed, "r", encoding="utf-8", newline="") as f:
            self.assertEqual(html, f.read())
```

Create `tools/test_generate_changelog.py`:

```python
"""Tests for the generate_changelog library entry point."""
import os
import unittest

import generate_changelog
from modlist_utils import load_modlist

EXAMPLES_LISTS = os.path.join(os.path.dirname(__file__), "..", "examples", "lists")
EXAMPLES_REPORTS = os.path.join(os.path.dirname(__file__), "..", "examples", "reports")


class TestGenerateEntryPoint(unittest.TestCase):
    def test_generate_matches_committed_report(self):
        old = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.0.json"))
        new = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.1.json"))
        markdown = generate_changelog.generate(old, new)
        committed = os.path.join(
            EXAMPLES_REPORTS, "Example List 1.1", "Example List 1.0.changelog.md"
        )
        with open(committed, "r", encoding="utf-8", newline="") as f:
            self.assertEqual(markdown, f.read())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m unittest test_generate_coverage.TestGenerateEntryPoint test_generate_diff.TestGenerateEntryPoint test_generate_changelog -v`
Expected: FAIL / ERROR with `AttributeError: module ... has no attribute 'generate'`

- [ ] **Step 3: Add `generate()` to generate_coverage.py**

Insert above `main()`:

```python
def generate(source_data, target_data, source_name, target_name,
             min_confidence=0.80, ignore=None, base_data=None, base_name=None):
    """Library entry point: render the coverage report for loaded modlist data.

    Pure data-in -> HTML-out; callers own all file IO and output naming.
    ``ignore`` is a coverage_ignore.IgnoreSet or None; ``base_data``/``base_name``
    switch on base-update mode exactly like the CLI's --base.
    """
    rows_by_section = build_report(
        source_data, target_data, min_confidence, ignore, base_data
    )
    summary = compute_summary(rows_by_section)
    section_majors = map_sections_to_majors(source_data)
    return render_html(
        rows_by_section, summary, source_name, target_name, section_majors,
        base_name=base_name,
    )
```

In `main()`, replace the block from `rows_by_section = build_report(` through `html_output = render_html(...)` (currently ~lines 932-944) with:

```python
    source_name = os.path.splitext(os.path.basename(args.source))[0]
    target_name = os.path.splitext(os.path.basename(args.target))[0]

    html_output = generate(
        source_data, target_data, source_name, target_name,
        min_confidence=args.min_confidence, ignore=ignore,
        base_data=base_data, base_name=base_name,
    )
```

(Keep the existing `source_name`/`target_name` lines in exactly one place; delete the now-unused direct calls.)

- [ ] **Step 4: Add `generate()` to generate_diff.py**

Insert above `main()`:

```python
def generate(old_data, new_data, old_name, new_name, min_confidence=0.80):
    """Library entry point: render the side-by-side diff for loaded modlist data.

    Pure data-in -> HTML-out; callers own all file IO and output naming.
    """
    old_mods = extract_mods(old_data)
    new_mods = extract_mods(new_data)
    matched_pairs, added_mods, removed_mods = match_mods(
        old_mods, new_mods, min_confidence
    )
    old_section_order = get_separator_order(old_data)
    new_section_order = get_separator_order(new_data)
    section_matches, added_sections, removed_sections = match_sections(
        old_section_order, new_section_order, matched_pairs
    )
    section_match_map = {name_key(old): name_key(new) for old, new in section_matches}
    mod_changes = classify_mod_changes(matched_pairs, section_match_map)
    rows = build_aligned_diff(
        old_data, new_data, matched_pairs, added_mods, removed_mods,
        section_matches, added_sections, removed_sections,
        section_match_map, mod_changes,
    )
    summary = compute_summary(
        mod_changes, added_mods, removed_mods,
        section_matches, added_sections, removed_sections,
    )
    return render_html(rows, old_name, new_name, summary)
```

Rewrite `main()`'s body after arg parsing to:

```python
    old_data = load_modlist(args.old_list)
    new_data = load_modlist(args.new_list)

    import os
    old_name = os.path.splitext(os.path.basename(args.old_list))[0]
    new_name = os.path.splitext(os.path.basename(args.new_list))[0]

    html_output = generate(
        old_data, new_data, old_name, new_name,
        min_confidence=args.min_confidence,
    )

    out_path = resolve_output_path(args.output, args.old_list, args.new_list, "diff", "html")
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(html_output)
        print(f"Diff written to {out_path}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(html_output)
```

(If `os` is already imported at module top, drop the local `import os` — match the file's current import style; today it does a local import inside `main()`.)

- [ ] **Step 5: Add `generate()` to generate_changelog.py**

Insert above `main()`:

```python
def generate(old_data, new_data, min_confidence=0.80):
    """Library entry point: render the markdown changelog for loaded modlist data.

    Pure data-in -> markdown-out; callers own all file IO and output naming.
    """
    old_mods = extract_mods(old_data)
    new_mods = extract_mods(new_data)
    old_section_order = get_separator_order(old_data)
    new_section_order = get_separator_order(new_data)
    matched, added, removed = match_mods(old_mods, new_mods, min_confidence)
    updated = classify_updates(matched)
    added_by_section = organize_by_section(added, new_section_order)
    removed_by_section = organize_by_section(removed, old_section_order)
    summary = {
        "added": len(added),
        "removed": len(removed),
        "updated": len(updated),
    }
    return generate_markdown(added_by_section, removed_by_section, updated, summary)
```

`main()` becomes:

```python
    old_data = load_modlist(args.old_list)
    new_data = load_modlist(args.new_list)

    markdown = generate(old_data, new_data, min_confidence=args.min_confidence)

    out_path = resolve_output_path(args.output, args.old_list, args.new_list, "changelog", "md")
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(markdown)
        print(f"Changelog written to {out_path}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(markdown)
```

- [ ] **Step 6: Update CLAUDE.md test command**

In CLAUDE.md's Testing section, add `test_generate_changelog` to the unittest module list.

- [ ] **Step 7: Run full suite + smoke test**

Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples -v`
Expected: all PASS
Run (repo root): `python tools/regenerate.py "Example List 1.1" --lists examples/lists --output examples/reports` then `git diff --exit-code examples/reports`
Expected: regenerate prints all `+` lines, git diff exits 0

- [ ] **Step 8: Commit**

```bash
git add tools/generate_coverage.py tools/generate_diff.py tools/generate_changelog.py tools/test_generate_coverage.py tools/test_generate_diff.py tools/test_generate_changelog.py CLAUDE.md
git commit -m "refactor: add pure generate() library entry points to the three generators"
```

```json:metadata
{"files": ["tools/generate_coverage.py", "tools/generate_diff.py", "tools/generate_changelog.py", "tools/test_generate_changelog.py", "CLAUDE.md"], "verifyCommand": "cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples -v", "acceptanceCriteria": ["three generate() entry functions exist, pure", "byte-identical to committed examples/reports", "examples smoke test passes", "full suite green"], "modelTier": "standard"}
```

---

### Task 2: Plugin package skeleton — absorb the exporter

**Goal:** `mo2-plugins/modlist_compare/` package exists with `exporter_core` + `ExportModlistTool` reproducing today's export UX; the old `modlist-json-exporter/` folder is gone.

**Files:**
- Create: `mo2-plugins/modlist_compare/__init__.py`
- Create: `mo2-plugins/modlist_compare/plugin_tools.py`
- Create: `mo2-plugins/modlist_compare/exporter_core.py`
- Create: `mo2-plugins/modlist_compare/test_exporter_core.py`
- Move (git mv): `mo2-plugins/modlist-json-exporter/FORMAT_SPECIFICATION.md` → `mo2-plugins/modlist_compare/FORMAT_SPECIFICATION.md`; delete `mo2-plugins/modlist-json-exporter/` (README.md is superseded — a fresh plugin README comes in Task 6)
- Modify: `CLAUDE.md` (FORMAT_SPECIFICATION link + Exporter section path), `.claude/skills/mo2-api/SKILL.md` (references `modlist-json-exporter` as the example `IPluginTool`)

**Acceptance Criteria:**
- [ ] `exporter_core` pure helpers (`strip_tags`, `extract_tags`, `sanitize_filename`, `read_meta_ini`, `get_plugin_files`) import and pass unit tests without mobase/PyQt6 installed
- [ ] `export_modlist` / `suggested_list_name` port the old plugin's logic verbatim (lazy `import mobase` inside `export_modlist` only)
- [ ] `ExportModlistTool.displayName()` == `"Modlist Compare/Export Modlist to JSON"`; export UX identical to the old plugin (save dialog, suggested name, summary box)
- [ ] `mo2-plugins/modlist-json-exporter/` no longer exists; no repo file references it (except git history)
- [ ] All plugin files compile: `python -m py_compile`

**Verify:** `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v` → pass; `python -m py_compile mo2-plugins/modlist_compare/*.py` → exit 0 (plugin_tools imports mobase so compile-only, no import test); `grep -ri "modlist-json-exporter" --include="*.md" --include="*.py" .` (excluding docs/design/, docs/superpowers/) → no hits

**Steps:**

- [ ] **Step 1: Write failing tests for the pure helpers**

Create `mo2-plugins/modlist_compare/test_exporter_core.py`:

```python
"""Tests for exporter_core's pure helpers (no mobase/PyQt6 required)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modlist_compare import exporter_core


class TestTagHelpers(unittest.TestCase):
    def test_strip_tags(self):
        self.assertEqual(exporter_core.strip_tags("[NoDelete] Awesome Mod"), "Awesome Mod")
        self.assertEqual(
            exporter_core.strip_tags("[A] [B] Mod Name"), "Mod Name"
        )
        self.assertEqual(exporter_core.strip_tags("Plain Mod"), "Plain Mod")

    def test_extract_tags(self):
        self.assertEqual(exporter_core.extract_tags("[A] [B] Mod"), ["A", "B"])
        self.assertEqual(exporter_core.extract_tags("Plain"), [])


class TestSanitizeFilename(unittest.TestCase):
    def test_unsafe_chars_replaced(self):
        self.assertEqual(exporter_core.sanitize_filename('My<List>: v1?'), "My_List__ v1_")

    def test_empty_falls_back(self):
        self.assertEqual(exporter_core.sanitize_filename(""), "modlist_export")


class TestReadMetaIni(unittest.TestCase):
    def test_reads_general_and_installed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "meta.ini"), "w", encoding="utf-8") as f:
                f.write(
                    "[General]\nmodid=123\nversion=1.2\nnewestVersion=1.3\n"
                    "category=4\ninstallationFile=Mod-1-2.7z\n"
                    "[installedFiles]\nsize=1\n1\\modid=123\n1\\fileid=456\n"
                )
            general, installed = exporter_core.read_meta_ini(tmp)
        self.assertEqual(general["modid"], "123")
        self.assertEqual(general["version"], "1.2")
        self.assertEqual(installed["size"], 1)
        self.assertEqual(installed["files"][0], {"modid": "123", "fileid": "456"})

    def test_missing_meta_ini(self):
        with tempfile.TemporaryDirectory() as tmp:
            general, installed = exporter_core.read_meta_ini(tmp)
        self.assertEqual(general, {})
        self.assertEqual(installed, {})


class TestGetPluginFiles(unittest.TestCase):
    def test_finds_and_sorts_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("b.esp", "a.ESM", "readme.txt", "c.esl"):
                open(os.path.join(tmp, name), "w").close()
            self.assertEqual(
                exporter_core.get_plugin_files(tmp), ["a.ESM", "b.esp", "c.esl"]
            )

    def test_missing_dir(self):
        self.assertEqual(exporter_core.get_plugin_files("Z:\\does\\not\\exist"), [])


if __name__ == "__main__":
    unittest.main()
```

Also create an empty-for-now `mo2-plugins/modlist_compare/__init__.py` so the package imports (content in Step 3).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v`
Expected: ERROR — `exporter_core` module missing

- [ ] **Step 3: Create `exporter_core.py`, `__init__.py`, `plugin_tools.py`**

`mo2-plugins/modlist_compare/exporter_core.py` — a function-level port of `ModlistJsonExporter` from the old `modlist_json_exporter.py` (same regexes, same meta.ini fields, same ordering; `mobase` imported lazily so the module imports without MO2):

```python
"""Core modlist-export logic shared by both Modlist Compare tools.

Pure helpers live at module level and are unit-tested outside MO2; only
export_modlist touches mobase (imported lazily inside the function).
"""
import configparser
import os
import re


def strip_tags(mod_name):
    """Remove all [tags] from the beginning of a mod name."""
    pattern = r'^(\[[^\]]+\]\s*)+\s*'
    return re.sub(pattern, '', mod_name).strip()


def extract_tags(mod_name):
    """Extract all [tag] values from a mod name."""
    return re.findall(r'\[([^\]]+)\]', mod_name)


def sanitize_filename(filename):
    """Replace filesystem-unsafe characters; empty input falls back."""
    for char in '<>:"/\\|?*':
        filename = filename.replace(char, '_')
    filename = filename.strip('. ')
    return filename if filename else "modlist_export"


def get_plugin_files(mod_path):
    """Sorted plugin filenames (.esp/.esl/.esm) directly inside mod_path."""
    plugins = []
    if not os.path.exists(mod_path):
        return plugins
    try:
        for file in os.listdir(mod_path):
            if file.lower().endswith(('.esp', '.esl', '.esm')):
                plugins.append(file)
    except Exception:
        pass
    return sorted(plugins)


def read_meta_ini(mod_path):
    """Read meta.ini's [General] and [installedFiles] sections."""
    general_data = {}
    installed_files_data = {}
    meta_ini_path = os.path.join(mod_path, "meta.ini")
    if not os.path.exists(meta_ini_path):
        return general_data, installed_files_data
    try:
        config = configparser.ConfigParser()
        config.read(meta_ini_path, encoding='utf-8')
        if 'General' in config:
            section = config['General']
            general_data = {
                'modid': section.get('modid', ''),
                'version': section.get('version', ''),
                'newestVersion': section.get('newestVersion', ''),
                'category': section.get('category', ''),
                'installationFile': section.get('installationFile', ''),
            }
        if 'installedFiles' in config:
            section = config['installedFiles']
            size = int(section.get('size', 0))
            installed_files_data['size'] = size
            installed_files_data['files'] = []
            for i in range(1, size + 1):
                installed_files_data['files'].append({
                    'modid': section.get(f'{i}\\modid', ''),
                    'fileid': section.get(f'{i}\\fileid', ''),
                })
    except Exception:
        pass
    return general_data, installed_files_data


def suggested_list_name(organizer):
    """First separator's cleaned name (sanitized), or 'modlist_export'."""
    mod_list = organizer.modList()
    for mod_name in list(mod_list.allModsByProfilePriority()):
        mod = organizer.getMod(mod_name)
        if mod and (mod.isSeparator() or mod_name.endswith('_separator')):
            name = strip_tags(mod_name).replace("_separator", "").strip()
            return sanitize_filename(name)
    return "modlist_export"


def export_modlist(organizer):
    """Export the active modlist as the JSON-ready list of item dicts.

    Same structure as FORMAT_SPECIFICATION.md; order follows
    allModsByProfilePriority (top-to-bottom).
    """
    import mobase

    modlist_data = []
    mod_list = organizer.modList()
    current_separator = "Unsectioned"

    for mod_name in list(mod_list.allModsByProfilePriority()):
        mod = organizer.getMod(mod_name)
        if not mod:
            continue

        if mod.isSeparator() or mod_name.endswith('_separator'):
            separator_name = strip_tags(mod_name).replace("_separator", "").strip()
            current_separator = separator_name
            modlist_data.append({
                "id": None,
                "type": "separator",
                "separatorName": separator_name,
                "modName": separator_name,
                "displayName": mod_name,
                "plugins": [],
                "general": {},
                "installed": {},
                "order": len(modlist_data),
                "tags": extract_tags(mod_name),
                "active": True,
            })
            continue

        mod_path = mod.absolutePath()
        nexus_id = mod.nexusId()
        clean_mod_name = strip_tags(mod_name)
        general_data, installed_files_data = read_meta_ini(mod_path)
        is_active = mod_list.state(mod_name) & mobase.ModState.ACTIVE != 0

        modlist_data.append({
            "id": nexus_id if nexus_id > 0 else clean_mod_name,
            "type": "mod",
            "separatorName": current_separator,
            "modName": clean_mod_name,
            "displayName": mod_name,
            "plugins": get_plugin_files(mod_path),
            "general": general_data,
            "installed": installed_files_data,
            "order": len(modlist_data),
            "tags": extract_tags(mod_name),
            "active": is_active,
        })

    for idx, item in enumerate(modlist_data):
        item["order"] = idx
    return modlist_data
```

(Note: the old code computed `version`/`newest_version` from mobase but never put them in the output dict — they came from meta.ini's `general` section. The port drops those dead locals.)

`mo2-plugins/modlist_compare/plugin_tools.py`:

```python
"""The two IPluginTool entries for the Modlist Compare plugin."""
import json
from typing import List, Optional

import mobase
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from . import exporter_core

SUBMENU = "Modlist Compare"
VERSION = mobase.VersionInfo(1, 0, 0)


class _BaseTool(mobase.IPluginTool):
    def __init__(self):
        super().__init__()
        self._organizer: Optional[mobase.IOrganizer] = None
        self._parent_widget = None

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        return True

    def author(self) -> str:
        return "meteor"

    def version(self) -> mobase.VersionInfo:
        return VERSION

    def settings(self) -> List[mobase.PluginSetting]:
        return []

    def icon(self) -> QIcon:
        return QIcon()

    def setParentWidget(self, widget):
        self._parent_widget = widget


class ExportModlistTool(_BaseTool):
    def name(self) -> str:
        return "Modlist Compare Exporter"

    def description(self) -> str:
        return "Export the active modlist to JSON for comparison and analysis."

    def displayName(self) -> str:
        return f"{SUBMENU}/Export Modlist to JSON"

    def tooltip(self) -> str:
        return self.description()

    def display(self):
        if not self._organizer:
            return
        suggested = exporter_core.suggested_list_name(self._organizer) + ".json"
        save_path, _ = QFileDialog.getSaveFileName(
            self._parent_widget, "Save Modlist JSON", suggested, "JSON files (*.json)"
        )
        if not save_path:
            return
        try:
            modlist_data = exporter_core.export_modlist(self._organizer)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(modlist_data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(
                self._parent_widget,
                "Export Complete",
                f"Modlist exported successfully to:\n{save_path}\n\n"
                f"Total mods: {len(modlist_data)}",
            )
        except Exception as e:
            QMessageBox.critical(
                self._parent_widget,
                "Export Failed",
                f"Failed to export modlist:\n{str(e)}",
            )
```

(`GenerateReportsTool` is added in Task 6 — do not reference it yet.)

`mo2-plugins/modlist_compare/__init__.py`:

```python
"""Modlist Compare — MO2 plugin: export modlists to JSON and generate
coverage/diff/changelog reports.

Plugin classes register only inside MO2 (mobase importable); importing this
package outside MO2 (unit tests) exposes just the plain modules.
"""
import importlib.util

if importlib.util.find_spec("mobase") is not None:
    from .plugin_tools import ExportModlistTool

    def createPlugins():
        return [ExportModlistTool()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v`
Expected: all PASS
Run: `python -m py_compile mo2-plugins/modlist_compare/__init__.py mo2-plugins/modlist_compare/plugin_tools.py mo2-plugins/modlist_compare/exporter_core.py`
Expected: exit 0

- [ ] **Step 5: Absorb the old exporter folder**

```bash
git mv "mo2-plugins/modlist-json-exporter/FORMAT_SPECIFICATION.md" "mo2-plugins/modlist_compare/FORMAT_SPECIFICATION.md"
git rm "mo2-plugins/modlist-json-exporter/README.md" "mo2-plugins/modlist-json-exporter/modlist_json_exporter.py"
```

Update every reference to the old path:
- `CLAUDE.md`: the JSON Format link (`mo2-plugins/modlist-json-exporter/FORMAT_SPECIFICATION.md` → `mo2-plugins/modlist_compare/FORMAT_SPECIFICATION.md`) and the "Exporter" section (retitle to describe the Modlist Compare plugin's export tool; full rewrite of plugin docs happens in Task 6 — here just keep links valid).
- `.claude/skills/mo2-api/SKILL.md`: "Working examples" names `modlist-json-exporter/modlist_json_exporter.py` — point it at `modlist_compare/` instead.
- Check for other references: `grep -ri "modlist-json-exporter" --include="*.md" --include="*.py" .` — fix any hit outside `docs/design/` and `docs/superpowers/` (historical docs keep their text).

- [ ] **Step 6: Verify and commit**

Run the Verify commands (tests, py_compile, grep).

```bash
git add -A mo2-plugins CLAUDE.md .claude/skills/mo2-api/SKILL.md
git commit -m "feat: modlist_compare plugin package absorbs the JSON exporter"
```

```json:metadata
{"files": ["mo2-plugins/modlist_compare/__init__.py", "mo2-plugins/modlist_compare/plugin_tools.py", "mo2-plugins/modlist_compare/exporter_core.py", "mo2-plugins/modlist_compare/test_exporter_core.py", "CLAUDE.md"], "verifyCommand": "python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p \"test_*.py\" -v", "acceptanceCriteria": ["pure helpers unit-tested without mobase", "export logic ported verbatim", "displayName uses Modlist Compare/ submenu prefix", "old exporter folder gone, links updated"], "modelTier": "standard"}
```

---

### Task 3: Vendoring — package script + `_vendor/`

**Goal:** `tools/package_plugin.py` fills `_vendor/` with byte-identical tool modules and builds the release zip; `_vendor/__init__.py` loads them or fails loudly.

**Files:**
- Create: `tools/package_plugin.py`
- Create: `mo2-plugins/modlist_compare/_vendor/__init__.py`
- Create: `tools/test_package_plugin.py`
- Modify: `.gitignore`

**Acceptance Criteria:**
- [ ] `python tools/package_plugin.py` populates `_vendor/` with the 5 modules (byte-identical to `tools/`) and writes `dist/modlist-compare-1.0.0.zip` whose entries all start with `modlist_compare/` and exclude `test_*.py` / `__pycache__`
- [ ] `from modlist_compare import _vendor` (after vendoring) exposes `modlist_utils`, `coverage_ignore`, `generate_coverage`, `generate_diff`, `generate_changelog`
- [ ] With `_vendor/` unpopulated, importing `_vendor` raises `ImportError` mentioning `tools/package_plugin.py`
- [ ] `.gitignore` covers `_vendor/*` (except `__init__.py`) and `dist/`

**Verify:** `cd tools && python -m unittest test_package_plugin -v` → pass; `python tools/package_plugin.py && git status --porcelain` → no untracked files under `mo2-plugins/` or `dist/`

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `tools/test_package_plugin.py`:

```python
"""Tests for the plugin vendoring/packaging script."""
import os
import tempfile
import unittest
import zipfile

import package_plugin

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))


class TestVendor(unittest.TestCase):
    def test_vendor_copies_modules_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_plugin.vendor(vendor_dir=tmp)
            for name in package_plugin.VENDORED_MODULES:
                with open(os.path.join(TOOLS_DIR, name), "rb") as f:
                    src = f.read()
                with open(os.path.join(tmp, name), "rb") as f:
                    dst = f.read()
                self.assertEqual(src, dst, name)


class TestBuildZip(unittest.TestCase):
    def test_zip_layout_and_exclusions(self):
        package_plugin.vendor()  # real _vendor/, needed for the zip content
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = package_plugin.build_zip(dist_dir=tmp)
            self.assertTrue(os.path.basename(zip_path).startswith("modlist-compare-"))
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
        self.assertTrue(all(n.startswith("modlist_compare/") for n in names))
        self.assertTrue(any(n.endswith("_vendor/modlist_utils.py") for n in names))
        self.assertTrue(any(n.endswith("/plugin_tools.py") for n in names))
        self.assertFalse(any("/test_" in n or "__pycache__" in n for n in names))


class TestVersionParse(unittest.TestCase):
    def test_reads_plugin_version(self):
        version = package_plugin.plugin_version()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m unittest test_package_plugin -v`
Expected: ERROR — `No module named 'package_plugin'`

- [ ] **Step 3: Write package_plugin.py**

Create `tools/package_plugin.py`:

```python
"""Package the Modlist Compare MO2 plugin.

Vendors the generator modules into mo2-plugins/modlist_compare/_vendor/ and
builds dist/modlist-compare-<version>.zip ready to unzip into MO2's plugins/.
"""
import os
import re
import shutil
import sys
import zipfile

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
PLUGIN_DIR = os.path.join(REPO_ROOT, "mo2-plugins", "modlist_compare")
DEFAULT_VENDOR_DIR = os.path.join(PLUGIN_DIR, "_vendor")
DEFAULT_DIST_DIR = os.path.join(REPO_ROOT, "dist")

VENDORED_MODULES = [
    "modlist_utils.py",
    "generate_coverage.py",
    "generate_diff.py",
    "generate_changelog.py",
    "coverage_ignore.py",
]


def vendor(vendor_dir=DEFAULT_VENDOR_DIR):
    """Copy the tool modules into the plugin's _vendor/ directory."""
    os.makedirs(vendor_dir, exist_ok=True)
    for name in VENDORED_MODULES:
        shutil.copy2(os.path.join(TOOLS_DIR, name), os.path.join(vendor_dir, name))


def plugin_version():
    """Read a.b.c from the VersionInfo(...) call in plugin_tools.py."""
    with open(os.path.join(PLUGIN_DIR, "plugin_tools.py"), encoding="utf-8") as f:
        match = re.search(r"VersionInfo\((\d+),\s*(\d+),\s*(\d+)", f.read())
    if not match:
        raise RuntimeError("No VersionInfo(a, b, c) found in plugin_tools.py")
    return ".".join(match.groups())


def build_zip(dist_dir=DEFAULT_DIST_DIR):
    """Zip the plugin folder (tests and caches excluded). Returns the zip path."""
    os.makedirs(dist_dir, exist_ok=True)
    zip_path = os.path.join(dist_dir, f"modlist-compare-{plugin_version()}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PLUGIN_DIR):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in sorted(files):
                if fn.startswith("test_") or fn.endswith(".pyc"):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, os.path.dirname(PLUGIN_DIR))
                zf.write(full, rel.replace(os.sep, "/"))
    return zip_path


def main():
    vendor()
    print(f"Vendored {len(VENDORED_MODULES)} modules into {DEFAULT_VENDOR_DIR}")
    zip_path = build_zip()
    print(f"Built {zip_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `_vendor/__init__.py`**

Create `mo2-plugins/modlist_compare/_vendor/__init__.py`:

```python
"""Vendored copies of the tools/ generator modules.

Populated by tools/package_plugin.py — the files here are unmodified copies.
The generators import each other as siblings (``from modlist_utils import ...``),
so this dir goes on sys.path just long enough to import them.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPECTED = [
    "modlist_utils.py",
    "generate_coverage.py",
    "generate_diff.py",
    "generate_changelog.py",
    "coverage_ignore.py",
]


def _load():
    missing = [m for m in _EXPECTED if not os.path.exists(os.path.join(_HERE, m))]
    if missing:
        raise ImportError(
            "Modlist Compare: vendored modules missing: "
            + ", ".join(missing)
            + ". Run tools/package_plugin.py to populate _vendor/."
        )
    sys.path.insert(0, _HERE)
    try:
        import coverage_ignore
        import generate_changelog
        import generate_coverage
        import generate_diff
        import modlist_utils
    finally:
        sys.path.remove(_HERE)
    return modlist_utils, coverage_ignore, generate_coverage, generate_diff, generate_changelog


(modlist_utils, coverage_ignore, generate_coverage,
 generate_diff, generate_changelog) = _load()
```

(Known tradeoff, fine for v1: the modules land in `sys.modules` under their plain names, so another MO2 plugin shipping a module named e.g. `modlist_utils` would collide. Noted in the plugin README in Task 6.)

- [ ] **Step 5: Update .gitignore**

Append to the "Private working data" area of `.gitignore`:

```gitignore
# Vendored tool copies + release zips, created by tools/package_plugin.py
mo2-plugins/modlist_compare/_vendor/*
!mo2-plugins/modlist_compare/_vendor/__init__.py
dist/
```

- [ ] **Step 6: Run tests, script, and commit**

Run: `cd tools && python -m unittest test_package_plugin -v` → all PASS
Run (repo root): `python tools/package_plugin.py` → prints vendor + zip lines; `git status --porcelain` shows nothing untracked under `mo2-plugins/` or `dist/`

```bash
git add tools/package_plugin.py tools/test_package_plugin.py mo2-plugins/modlist_compare/_vendor/__init__.py .gitignore
git commit -m "feat: package script vendors tool modules into the plugin"
```

```json:metadata
{"files": ["tools/package_plugin.py", "tools/test_package_plugin.py", "mo2-plugins/modlist_compare/_vendor/__init__.py", ".gitignore"], "verifyCommand": "cd tools && python -m unittest test_package_plugin -v", "acceptanceCriteria": ["vendor() copies 5 modules byte-identical", "zip layout modlist_compare/ prefix, tests excluded", "missing _vendor raises ImportError naming the script", "gitignore covers _vendor and dist"], "modelTier": "mechanical"}
```

---

### Task 4: report_runner — resolve sides, run generators, write outputs

**Goal:** Qt-free `report_runner` turns two resolved list sides + options into written report files with per-report error collection.

**Files:**
- Create: `mo2-plugins/modlist_compare/report_runner.py`
- Create: `mo2-plugins/modlist_compare/test_report_runner.py`

**Acceptance Criteria:**
- [ ] `run_reports` writes `<dest>/<list2.name>/<list1.name>.<type>.<ext>` for each selected type (`coverage`/`diff` → `.html`, `changelog` → `.md`) via the vendored `resolve_output_path`
- [ ] Coverage reads `<dest>/<list2.name>/.coverage-ignore.txt` when present (ignored mod appears with the `⊘` state in the HTML)
- [ ] `save_exports=True` writes `<dest>/<name>.json` for each live side only; the JSON round-trips through `load_side_from_file`
- [ ] A generator failure lands in `RunResult.errors` without stopping the other reports
- [ ] `load_side_from_file` raises `ValueError` on a JSON file that isn't a list

**Verify:** `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v` → all pass (test module vendors first via `package_plugin.vendor()`)

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `mo2-plugins/modlist_compare/test_report_runner.py`:

```python
"""Tests for report_runner (vendors the tool modules first, no Qt/mobase)."""
import json
import os
import sys
import tempfile
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_PLUGIN_DIR))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))   # mo2-plugins/
sys.path.insert(0, os.path.join(_REPO_ROOT, "tools"))

import package_plugin

package_plugin.vendor()  # report_runner needs a populated _vendor/

from modlist_compare import report_runner

EXAMPLES_LISTS = os.path.join(_REPO_ROOT, "examples", "lists")
OLD_LIST = os.path.join(EXAMPLES_LISTS, "Example List 1.0.json")
NEW_LIST = os.path.join(EXAMPLES_LISTS, "Example List 1.1.json")


def _side(path):
    return report_runner.load_side_from_file(path)


class TestLoadSideFromFile(unittest.TestCase):
    def test_loads_name_and_data(self):
        side = _side(OLD_LIST)
        self.assertEqual(side.name, "Example List 1.0")
        self.assertFalse(side.live)
        self.assertTrue(isinstance(side.data, list) and side.data)

    def test_rejects_non_list_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                json.dump({"not": "a modlist"}, f)
            with self.assertRaises(ValueError):
                report_runner.load_side_from_file(bad)


class TestRunReports(unittest.TestCase):
    def test_writes_all_three_reports_with_cli_naming(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST),
                ["coverage", "diff", "changelog"], tmp, save_exports=False,
            )
        self.assertEqual(result.errors, [])
        rel = sorted(os.path.relpath(p, tmp) for p in result.written)
        self.assertEqual(rel, [
            os.path.join("Example List 1.0", "Example List 1.1.changelog.md"),
            os.path.join("Example List 1.0", "Example List 1.1.coverage.html"),
            os.path.join("Example List 1.0", "Example List 1.1.diff.html"),
        ])
        for p in result.written:
            self.assertTrue(os.path.getsize(p) > 0)

    def test_coverage_reads_ignore_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = os.path.join(tmp, "Example List 1.0")
            os.makedirs(target_dir)
            with open(os.path.join(target_dir, ".coverage-ignore.txt"), "w",
                      encoding="utf-8") as f:
                f.write("Sky Idles\n")
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST), ["coverage"], tmp,
                save_exports=False,
            )
            self.assertEqual(result.errors, [])
            with open(result.written[0], encoding="utf-8") as f:
                html = f.read()
        self.assertIn("mod-ignored", html)

    def test_saves_live_export(self):
        live = _side(NEW_LIST)
        live.live = True
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                live, _side(OLD_LIST), ["changelog"], tmp, save_exports=True,
            )
            saved = os.path.join(tmp, "Example List 1.1.json")
            self.assertIn(saved, result.written)
            round_trip = report_runner.load_side_from_file(saved)
        self.assertEqual(round_trip.data, live.data)

    def test_generator_failure_is_collected_not_fatal(self):
        # An unknown report type forces one failure alongside one success.
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST), ["diff", "nonsense"], tmp,
                save_exports=False,
            )
        self.assertEqual(len(result.written), 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("nonsense", result.errors[0])


if __name__ == "__main__":
    unittest.main()
```

(`mod-ignored` is the CSS class an ignored row carries in the coverage HTML — see `.mod-ignored` in `tools/generate_coverage.py`; the committed sample report ignores `Sky Idles` the same way.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v`
Expected: ERROR — `report_runner` module missing

- [ ] **Step 3: Write report_runner.py**

Create `mo2-plugins/modlist_compare/report_runner.py`:

```python
"""Report pipeline for the Generate Reports dialog. No Qt, no mobase.

Resolves nothing itself: callers hand in two ListSide objects (already loaded)
plus options; this module runs the vendored generators and writes files using
the same naming convention as the CLI tools.
"""
import json
import os
from dataclasses import dataclass, field

from ._vendor import (
    coverage_ignore,
    generate_changelog,
    generate_coverage,
    generate_diff,
    modlist_utils,
)

REPORT_TYPES = ("coverage", "diff", "changelog")
_EXTENSIONS = {"coverage": "html", "diff": "html", "changelog": "md"}


@dataclass
class ListSide:
    """One side of a comparison: a display name plus loaded modlist data."""
    name: str
    data: list
    live: bool = False


@dataclass
class RunResult:
    written: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def load_side_from_file(path):
    """Load an exported modlist JSON into a ListSide (name = filename stem)."""
    data = modlist_utils.load_modlist(path)
    if not isinstance(data, list):
        raise ValueError("not a modlist export (expected a JSON array)")
    name = os.path.splitext(os.path.basename(path))[0]
    return ListSide(name=name, data=data, live=False)


def run_reports(list1, list2, report_types, dest_dir, save_exports=True,
                min_confidence=0.80):
    """Generate the selected reports from two sides into dest_dir.

    Naming matches the CLI: <dest>/<list2.name>/<list1.name>.<type>.<ext>.
    Coverage reads <dest>/<list2.name>/.coverage-ignore.txt like a static run.
    Per-report failures land in RunResult.errors; the rest still run.
    """
    result = RunResult()
    # resolve_output_path derives names from paths; hand it synthetic filenames
    # so plugin and CLI naming can never drift.
    first = list1.name + ".json"
    second = list2.name + ".json"
    dest = dest_dir if dest_dir.endswith(("/", "\\")) else dest_dir + os.sep

    for rtype in report_types:
        try:
            if rtype == "coverage":
                ignore = coverage_ignore.load_ignore(
                    os.path.join(dest_dir, list2.name, ".coverage-ignore.txt")
                )
                text = generate_coverage.generate(
                    list1.data, list2.data, list1.name, list2.name,
                    min_confidence=min_confidence, ignore=ignore,
                )
            elif rtype == "diff":
                text = generate_diff.generate(
                    list1.data, list2.data, list1.name, list2.name,
                    min_confidence=min_confidence,
                )
            elif rtype == "changelog":
                text = generate_changelog.generate(
                    list1.data, list2.data, min_confidence=min_confidence,
                )
            else:
                raise ValueError(f"unknown report type: {rtype}")
            out_path = modlist_utils.resolve_output_path(
                dest, first, second, rtype, _EXTENSIONS[rtype]
            )
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            result.written.append(out_path)
        except Exception as e:
            result.errors.append(f"{rtype}: {e}")

    if save_exports:
        for side in (list1, list2):
            if not side.live:
                continue
            try:
                path = os.path.join(dest_dir, side.name + ".json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(side.data, f, indent=2, ensure_ascii=False)
                result.written.append(path)
            except Exception as e:
                result.errors.append(f"export {side.name}: {e}")
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v`
Expected: all PASS (exporter_core tests included)

- [ ] **Step 5: Commit**

```bash
git add mo2-plugins/modlist_compare/report_runner.py mo2-plugins/modlist_compare/test_report_runner.py
git commit -m "feat: report_runner runs vendored generators with CLI-identical naming"
```

```json:metadata
{"files": ["mo2-plugins/modlist_compare/report_runner.py", "mo2-plugins/modlist_compare/test_report_runner.py"], "verifyCommand": "python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p \"test_*.py\" -v", "acceptanceCriteria": ["CLI-identical report paths", "coverage honors ignore file", "live export saved and round-trips", "per-report errors non-fatal", "non-list JSON rejected"], "modelTier": "standard"}
```

---

### Task 5: GenerateReportsDialog

**Goal:** The PyQt6 dialog: two side pickers, report checkboxes, destination, save-export toggle, guards, persistence, result box.

**Files:**
- Create: `mo2-plugins/modlist_compare/dialog.py`

**Acceptance Criteria:**
- [ ] Layout matches the spec sketch: List 1/List 2 rows (combo `Current profile` / `JSON file…` + path + Browse), three report checkboxes (Coverage/Diff checked by default), destination row, save-export checkbox (checked by default), Generate/Cancel
- [ ] Guards show a warning and keep the dialog open: both sides live, both sides the same file, no report checked, no/unloadable JSON, no destination
- [ ] State persists across MO2 sessions via `organizer.persistent`/`setPersistent` (keys: `dest_dir`, `browse_dir`, `reports`, `save_export`)
- [ ] Success box lists written files and errors, offers "Open Folder" (opens destination), and the dialog closes after a run with zero errors
- [ ] `python -m py_compile mo2-plugins/modlist_compare/dialog.py` passes (behavior verified in the Task 6 MO2 smoke test — no Qt test rig exists)

**Verify:** `python -m py_compile mo2-plugins/modlist_compare/dialog.py` → exit 0; behavioral check happens in Task 6's manual smoke test

**Steps:**

- [ ] **Step 1: Write dialog.py**

Create `mo2-plugins/modlist_compare/dialog.py`:

```python
"""Generate Reports dialog for the Modlist Compare plugin."""
import os

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

from . import exporter_core, report_runner

CURRENT_PROFILE = "Current profile"
JSON_FILE = "JSON file…"
_TITLE = "Generate Reports"


class _SidePicker:
    """Widgets for one list side (not itself a QWidget)."""

    def __init__(self, on_browse):
        self.combo = QComboBox()
        self.combo.addItems([CURRENT_PROFILE, JSON_FILE])
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(on_browse)
        self.combo.currentTextChanged.connect(self._sync_enabled)
        self._sync_enabled(self.combo.currentText())

    def _sync_enabled(self, text):
        is_file = text == JSON_FILE
        self.path_edit.setEnabled(is_file)
        self.browse_btn.setEnabled(is_file)

    def is_live(self):
        return self.combo.currentText() == CURRENT_PROFILE

    def path(self):
        return self.path_edit.text().strip()


class GenerateReportsDialog(QDialog):
    def __init__(self, parent, organizer, plugin_name):
        super().__init__(parent)
        self._organizer = organizer
        self._plugin_name = plugin_name
        self.setWindowTitle(_TITLE)
        self.setMinimumWidth(560)
        self._build_ui()
        self._restore_state()

    # ---- persistence -----------------------------------------------------

    def _get(self, key, default):
        return self._organizer.persistent(self._plugin_name, key, default)

    def _set(self, key, value):
        self._organizer.setPersistent(self._plugin_name, key, value)

    def _restore_state(self):
        self._dest_edit.setText(str(self._get("dest_dir", "")))
        saved = str(self._get("reports", "coverage,diff"))
        chosen = {r for r in saved.split(",") if r}
        for rtype, box in self._report_boxes.items():
            box.setChecked(rtype in chosen)
        self._save_export_box.setChecked(str(self._get("save_export", "true")) == "true")

    def _save_state(self):
        self._set("dest_dir", self._dest_edit.text().strip())
        self._set("reports", ",".join(
            r for r, box in self._report_boxes.items() if box.isChecked()
        ))
        self._set("save_export", "true" if self._save_export_box.isChecked() else "false")

    # ---- UI --------------------------------------------------------------

    def _build_ui(self):
        grid = QGridLayout(self)

        self._side1 = _SidePicker(lambda: self._browse_side(self._side1))
        self._side2 = _SidePicker(lambda: self._browse_side(self._side2))
        for row, (label, side) in enumerate(
            (("List 1 (source / old):", self._side1),
             ("List 2 (target / new):", self._side2))
        ):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(side.combo, row, 1)
            grid.addWidget(side.path_edit, row, 2)
            grid.addWidget(side.browse_btn, row, 3)

        grid.addWidget(QLabel("Reports:"), 2, 0)
        reports_row = QHBoxLayout()
        self._report_boxes = {}
        for rtype, label in (("coverage", "Coverage"), ("diff", "Diff"),
                             ("changelog", "Changelog")):
            box = QCheckBox(label)
            self._report_boxes[rtype] = box
            reports_row.addWidget(box)
        reports_row.addStretch()
        grid.addLayout(reports_row, 2, 1, 1, 3)

        grid.addWidget(QLabel("Destination folder:"), 3, 0)
        self._dest_edit = QLineEdit()
        dest_btn = QPushButton("Browse…")
        dest_btn.clicked.connect(self._browse_dest)
        grid.addWidget(self._dest_edit, 3, 1, 1, 2)
        grid.addWidget(dest_btn, 3, 3)

        self._save_export_box = QCheckBox(
            'Save "Current profile" export as JSON'
        )
        grid.addWidget(self._save_export_box, 4, 0, 1, 4)

        buttons = QHBoxLayout()
        generate_btn = QPushButton("Generate")
        generate_btn.setDefault(True)
        generate_btn.clicked.connect(self._on_generate)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(generate_btn)
        buttons.addWidget(cancel_btn)
        grid.addLayout(buttons, 5, 0, 1, 4)

    def _browse_side(self, side):
        start = str(self._get("browse_dir", ""))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select exported modlist JSON", start, "JSON files (*.json)"
        )
        if path:
            side.path_edit.setText(path)
            self._set("browse_dir", os.path.dirname(path))

    def _browse_dest(self):
        start = self._dest_edit.text().strip() or str(self._get("dest_dir", ""))
        path = QFileDialog.getExistingDirectory(
            self, "Select destination folder", start
        )
        if path:
            self._dest_edit.setText(path)

    # ---- generate --------------------------------------------------------

    def _warn(self, message):
        QMessageBox.warning(self, _TITLE, message)

    def _resolve_side(self, label, picker):
        """Return a ListSide, or None after warning the user."""
        if picker.is_live():
            data = exporter_core.export_modlist(self._organizer)
            name = exporter_core.suggested_list_name(self._organizer)
            return report_runner.ListSide(name=name, data=data, live=True)
        path = picker.path()
        if not path:
            self._warn(f"{label}: choose a JSON file (or switch to Current profile).")
            return None
        try:
            return report_runner.load_side_from_file(path)
        except Exception as e:
            self._warn(f"{label}: could not load\n{path}\n\n{e}")
            return None

    def _on_generate(self):
        if self._side1.is_live() and self._side2.is_live():
            self._warn("Both sides are the current profile — pick a JSON file for one side.")
            return
        if (not self._side1.is_live() and not self._side2.is_live()
                and self._side1.path() and self._side1.path() == self._side2.path()):
            self._warn("Both sides are the same file.")
            return
        report_types = [r for r, box in self._report_boxes.items() if box.isChecked()]
        if not report_types:
            self._warn("Select at least one report type.")
            return
        dest = self._dest_edit.text().strip()
        if not dest:
            self._warn("Choose a destination folder.")
            return

        side1 = self._resolve_side("List 1", self._side1)
        if side1 is None:
            return
        side2 = self._resolve_side("List 2", self._side2)
        if side2 is None:
            return

        self._save_state()
        result = report_runner.run_reports(
            side1, side2, report_types, dest,
            save_exports=self._save_export_box.isChecked(),
        )
        self._show_result(result, dest)
        if not result.errors:
            self.accept()

    def _show_result(self, result, dest):
        lines = []
        if result.written:
            lines.append("Written:")
            lines.extend(f"  {p}" for p in result.written)
        if result.errors:
            lines.append("")
            lines.append("Errors:")
            lines.extend(f"  {e}" for e in result.errors)
        box = QMessageBox(self)
        box.setWindowTitle(_TITLE)
        box.setIcon(
            QMessageBox.Icon.Critical if not result.written
            else QMessageBox.Icon.Warning if result.errors
            else QMessageBox.Icon.Information
        )
        box.setText("\n".join(lines) or "Nothing to do.")
        open_btn = box.addButton("Open Folder", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(dest))
```

- [ ] **Step 2: Compile check**

Run: `python -m py_compile mo2-plugins/modlist_compare/dialog.py`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add mo2-plugins/modlist_compare/dialog.py
git commit -m "feat: Generate Reports dialog (PyQt6)"
```

```json:metadata
{"files": ["mo2-plugins/modlist_compare/dialog.py"], "verifyCommand": "python -m py_compile mo2-plugins/modlist_compare/dialog.py", "acceptanceCriteria": ["layout matches spec sketch", "all five guards keep dialog open", "state persists via organizer persistent storage", "result box with Open Folder, closes on clean run"], "modelTier": "standard"}
```

---

### Task 6: GenerateReportsTool, plugin README, docs, release zip

**Goal:** Second menu item wired to the dialog, plugin README, CLAUDE.md updated, packaged zip built; the whole feature is install-ready.

**Files:**
- Modify: `mo2-plugins/modlist_compare/plugin_tools.py` (add `GenerateReportsTool`)
- Modify: `mo2-plugins/modlist_compare/__init__.py` (register both tools)
- Create: `mo2-plugins/modlist_compare/README.md`
- Modify: `CLAUDE.md` (plugin section: rename Exporter section to Modlist Compare plugin, document both tools + packaging command)

**Acceptance Criteria:**
- [ ] `GenerateReportsTool.displayName()` == `"Modlist Compare/Generate Reports…"`; `display()` opens `GenerateReportsDialog` with the tool's `name()` for persistence
- [ ] `createPlugins()` returns both tools (inside MO2 only)
- [ ] README covers: what the plugin does, install (unzip into `plugins/`, restart), both menu items, report types + naming convention, the ignore-file interop, the `sys.modules` vendoring caveat, and dev packaging (`python tools/package_plugin.py`)
- [ ] CLAUDE.md documents the plugin (replacing the old Exporter section) and the package script
- [ ] `python tools/package_plugin.py` builds the zip; full test suite green; examples smoke test still passes

**Verify:** `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v && cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin -v` → all pass; `python tools/package_plugin.py` → zip built. Then the **manual MO2 smoke test** (human): unzip into MO2 `plugins/`, restart, check submenu shows both items, export a JSON, generate all three reports live-vs-file, confirm files + Open Folder.

**Steps:**

- [ ] **Step 1: Add GenerateReportsTool**

Append to `mo2-plugins/modlist_compare/plugin_tools.py`:

```python
class GenerateReportsTool(_BaseTool):
    def name(self) -> str:
        return "Modlist Compare Reports"

    def description(self) -> str:
        return "Generate coverage, diff, and changelog reports between two modlists."

    def displayName(self) -> str:
        return f"{SUBMENU}/Generate Reports…"

    def tooltip(self) -> str:
        return self.description()

    def display(self):
        if not self._organizer:
            return
        from .dialog import GenerateReportsDialog

        dialog = GenerateReportsDialog(
            self._parent_widget, self._organizer, self.name()
        )
        dialog.exec()
```

(The `from .dialog import` stays inside `display()` so the plugin still registers even if dialog.py has an import-time problem — MO2 then shows the error on click, not a silent missing plugin.)

Update `mo2-plugins/modlist_compare/__init__.py`'s mobase branch:

```python
if importlib.util.find_spec("mobase") is not None:
    from .plugin_tools import ExportModlistTool, GenerateReportsTool

    def createPlugins():
        return [ExportModlistTool(), GenerateReportsTool()]
```

- [ ] **Step 2: Write the plugin README**

Create `mo2-plugins/modlist_compare/README.md` covering, in this order: one-paragraph overview (export + compare inside MO2); requirements (MO2 2.5.0+, PyQt6 build); install (unzip `dist/modlist-compare-<version>.zip` into MO2's `plugins/`, restart); the two menu items under Tools ▸ Modlist Compare with a short usage walkthrough of the Generate Reports dialog (both sides, report types, destination, save-export); report naming (`<dest>/<list2>/<list1>.<type>.<ext>`) and `.coverage-ignore.txt` interop with the CLI tools; JSON format pointer to `FORMAT_SPECIFICATION.md`; known limitation (vendored modules occupy plain `sys.modules` names — a collision with another plugin's same-named module is theoretically possible); developer section (`python tools/package_plugin.py` vendors + zips; tests via the unittest discover command).

- [ ] **Step 3: Update CLAUDE.md**

Replace the "Exporter" section (`### Exporter — mo2-plugins/modlist-json-exporter/...`) with a "Modlist Compare plugin" section: package path `mo2-plugins/modlist_compare/`, the two tools, that `report_runner`/dialog call the same vendored generator code via `generate()` entry functions, packaging via `tools/package_plugin.py` (vendor + zip, `_vendor/` gitignored), pointer to the plugin README and the design doc. Also add `test_package_plugin` to the Testing command if not already there (Task 3 may have; verify).

- [ ] **Step 4: Full verification + package**

Run: `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v` → PASS
Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin -v` → PASS
Run (repo root): `python tools/regenerate.py "Example List 1.1" --lists examples/lists --output examples/reports && git diff --exit-code examples/reports` → exit 0
Run: `python tools/package_plugin.py` → zip at `dist/modlist-compare-1.0.0.zip`

- [ ] **Step 5: Commit**

```bash
git add mo2-plugins/modlist_compare CLAUDE.md
git commit -m "feat: Generate Reports tool, plugin README, packaged release"
```

- [ ] **Step 6: Manual MO2 smoke test (human-run, after merge or from the zip)**

Ask the user to: unzip `dist/modlist-compare-1.0.0.zip` into MO2's `plugins/`, restart MO2, and confirm — (a) Tools ▸ Modlist Compare shows both items; (b) Export writes a valid JSON; (c) Generate Reports with List 1 = an exported file, List 2 = Current profile produces all three reports plus the saved live export in the chosen folder; (d) Open Folder opens it; (e) settings persist across an MO2 restart. Report any failure back as a bug to fix before release.

```json:metadata
{"files": ["mo2-plugins/modlist_compare/plugin_tools.py", "mo2-plugins/modlist_compare/__init__.py", "mo2-plugins/modlist_compare/README.md", "CLAUDE.md"], "verifyCommand": "python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p \"test_*.py\" -v", "acceptanceCriteria": ["GenerateReportsTool wired to dialog", "createPlugins returns both tools", "README complete", "CLAUDE.md updated", "zip builds, all suites green"], "modelTier": "standard"}
```
