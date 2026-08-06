# Coverage Report Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the `generate_coverage.py` HTML report (green "add" candidates, flipped version arrow, sticky section headers, major-section divider bands) and add a shared output-subfolder helper used by all three generators.

**Architecture:** Changes 1–4 are isolated to `tools/generate_coverage.py` and its tests. Change 5 adds one pure helper, `resolve_output_path`, to `tools/modlist_utils.py`, then wires it into the `main()` of all three generators. TDD throughout; each task is one commit.

**Tech Stack:** Python 3 standard library only (`argparse`, `html`, `os`, `enum`, `dataclasses`, `unittest`). No third-party deps.

**Reference spec:** [docs/design/2026-06-09-coverage-report-improvements-design.md](../design/2026-06-09-coverage-report-improvements-design.md)

---

## File Structure

| File | Responsibility | Tasks |
|------|----------------|-------|
| `tools/modlist_utils.py` | Add `resolve_output_path` (shared path logic) | 1 |
| `tools/test_modlist_utils.py` | Tests for `resolve_output_path` | 1 |
| `tools/generate_coverage.py` | `main()` wiring (T2) + changes 1–4 (T3–T6) | 2,3,4,5,6 |
| `tools/generate_changelog.py` | `main()` wiring | 2 |
| `tools/generate_diff.py` | `main()` wiring | 2 |
| `tools/test_generate_coverage.py` | Update + add coverage tests | 3,4,5,6 |
| `CLAUDE.md` | Document the new behavior | 7 |

**Execution order is linear (1 → 2 → 3 → 4 → 5 → 6 → 7).** Tasks 1–2 form the output-path track; 3–6 the coverage-display track. They are serialized to avoid concurrent edits to `generate_coverage.py` / `test_generate_coverage.py`.

**Test command (used throughout), run from inside `tools/`:**

```bash
cd tools
python -m unittest test_modlist_utils test_generate_coverage -v
```

---

### Task 1: `resolve_output_path` helper in `modlist_utils.py`

**Goal:** Add a pure function that turns the `-o` argument into a final file path (or `None` for stdout), auto-nesting into a per-list subfolder when `-o` is a directory.

**Files:**
- Modify: `tools/modlist_utils.py` (imports at lines 8–10; add function after `load_modlist`, ~line 20)
- Modify: `tools/test_modlist_utils.py` (imports at lines 3–10; append a TestCase)

**Acceptance Criteria:**
- [ ] `resolve_output_path(None, ...)` returns `None`.
- [ ] An explicit file path (e.g. `"out/foo.html"`) is returned unchanged.
- [ ] A directory `-o` (trailing separator OR existing dir) returns `<dir>/<basename(second)>/<basename(first)>.<type>.<ext>` and creates the folder.
- [ ] `python -m unittest test_modlist_utils -v` is green.

**Verify:** `cd tools && python -m unittest test_modlist_utils -v` → OK (all tests pass, including `ResolveOutputPathTest`).

**Steps:**

- [ ] **Step 1: Add the tests (failing).** In `tools/test_modlist_utils.py`, change the import line `from modlist_utils import compare_versions` to:

```python
import tempfile

from modlist_utils import compare_versions, resolve_output_path
```

Then append this TestCase to the end of the file (before the `if __name__` guard if present, otherwise at end):

```python
class ResolveOutputPathTest(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(
            resolve_output_path(None, "a/Source.json", "b/Target.json", "coverage", "html")
        )

    def test_empty_returns_none(self):
        self.assertIsNone(
            resolve_output_path("", "a/Source.json", "b/Target.json", "coverage", "html")
        )

    def test_explicit_file_path_unchanged(self):
        self.assertEqual(
            resolve_output_path(
                "out/foo.html", "a/Source.json", "b/Target.json", "coverage", "html"
            ),
            "out/foo.html",
        )

    def test_trailing_separator_builds_nested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = resolve_output_path(
                tmp + os.sep,
                "lists/NORDIC SOULS v3.0.1.json",
                "lists/Meteoric 0.0.3.json",
                "coverage",
                "html",
            )
            expected = os.path.join(
                tmp, "Meteoric 0.0.3", "NORDIC SOULS v3.0.1.coverage.html"
            )
            self.assertEqual(result, expected)
            self.assertTrue(os.path.isdir(os.path.dirname(result)))

    def test_existing_directory_without_trailing_sep(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = resolve_output_path(tmp, "old.json", "new.json", "diff", "html")
            expected = os.path.join(tmp, "new", "old.diff.html")
            self.assertEqual(result, expected)
            self.assertTrue(os.path.isdir(os.path.dirname(result)))
```

- [ ] **Step 2: Run the tests to confirm they fail.**

Run: `cd tools && python -m unittest test_modlist_utils -v`
Expected: FAIL/ERROR — `ImportError: cannot import name 'resolve_output_path'`.

- [ ] **Step 3: Implement the helper.** In `tools/modlist_utils.py`, change the import block:

```python
import difflib
import json
import os
import re
```

Then add this function immediately after `load_modlist` (after line 20):

```python
def resolve_output_path(output_arg, first_path, second_path, type_label, ext):
    """Resolve the final output file path for a generated report.

    - output_arg is falsy (None/"")  -> return None (caller writes to stdout).
    - output_arg names a directory   -> return
        <output_arg>/<basename(second_path)>/<basename(first_path)>.<type_label>.<ext>
      creating intermediate directories. "Directory" means it ends with a path
      separator or is an existing directory. The folder is named after the SECOND
      positional list, the file after the FIRST.
    - otherwise                      -> return output_arg unchanged (explicit file).

    Names derive from the input *filenames*, which already exist on disk and are
    therefore filesystem-safe.
    """
    if not output_arg:
        return None

    is_dir = output_arg.endswith(("/", "\\")) or os.path.isdir(output_arg)
    if not is_dir:
        return output_arg

    folder = os.path.splitext(os.path.basename(second_path))[0]
    name = os.path.splitext(os.path.basename(first_path))[0]
    target_dir = os.path.join(output_arg, folder)
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, f"{name}.{type_label}.{ext}")
```

- [ ] **Step 4: Run the tests to confirm they pass.**

Run: `cd tools && python -m unittest test_modlist_utils -v`
Expected: OK.

- [ ] **Step 5: Commit.**

```bash
git add tools/modlist_utils.py tools/test_modlist_utils.py
git commit -m "feat(tools): add resolve_output_path for per-list output subfolders"
```

---

### Task 2: Wire `resolve_output_path` into all three generators' `main()`

**Goal:** Make `-o <dir>` auto-name reports into `<dir>/<2nd-list>/<1st-list>.<type>.<ext>` for coverage, diff, and changelog; `-o <file>` and omitting `-o` (stdout) behave as before.

**Files:**
- Modify: `tools/generate_coverage.py` (import block lines 25–31; `main()` output block lines 378–384)
- Modify: `tools/generate_changelog.py` (import block lines 20–26; `main()` output block lines 159–164)
- Modify: `tools/generate_diff.py` (import block lines 23–29; `main()` output block lines 789–795)

**Acceptance Criteria:**
- [ ] Each tool imports `resolve_output_path` and uses it to compute the path.
- [ ] coverage: folder = target (2nd arg), file = source (1st arg) → `.coverage.html`.
- [ ] diff/changelog: folder = new_list (2nd arg), file = old_list (1st arg) → `.diff.html` / `.changelog.md`.
- [ ] Running a tool with `-o <dir>` creates the nested file; omitting `-o` still prints to stdout.
- [ ] `python -m unittest test_modlist_utils test_generate_coverage -v` still green.

**Verify:**

```bash
cd tools
python generate_coverage.py "../lists/NORDIC SOULS v3.0.1.json" "../lists/Meteoric 0.0.3.json" -o ../_verify_out/
python generate_changelog.py "../lists/NORDIC SOULS v3.0.1.json" "../lists/Meteoric 0.0.3.json" -o ../_verify_out/
```

Expected stderr (path separators may be `\` on Windows):
`Coverage view written to ../_verify_out/Meteoric 0.0.3/NORDIC SOULS v3.0.1.coverage.html`
`Changelog written to ../_verify_out/Meteoric 0.0.3/NORDIC SOULS v3.0.1.changelog.md`
Then confirm both files exist and delete the scratch dir (`Remove-Item -Recurse -Force ../_verify_out` on PowerShell, or `rm -rf ../_verify_out`). **Do not commit `_verify_out/`.**

**Steps:**

- [ ] **Step 1: Wire `generate_coverage.py`.** Change its import block (lines 25–31) to add `resolve_output_path`:

```python
from modlist_utils import (
    load_modlist,
    extract_mods,
    get_version,
    match_mods,
    compare_versions,
    resolve_output_path,
)
```

Replace the output block (lines 378–384):

```python
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html_output)
        print(f"Coverage view written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(html_output)
```

with:

```python
    out_path = resolve_output_path(args.output, args.source, args.target, "coverage", "html")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_output)
        print(f"Coverage view written to {out_path}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(html_output)
```

- [ ] **Step 2: Wire `generate_changelog.py`.** Change its import block (lines 20–26) to add `resolve_output_path`:

```python
from modlist_utils import (
    load_modlist,
    extract_mods,
    get_separator_order,
    match_mods,
    classify_updates,
    resolve_output_path,
)
```

Replace the output block (lines 159–164):

```python
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Changelog written to {args.output}", file=sys.stderr)
    else:
        print(markdown)
```

with:

```python
    out_path = resolve_output_path(args.output, args.old_list, args.new_list, "changelog", "md")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Changelog written to {out_path}", file=sys.stderr)
    else:
        print(markdown)
```

- [ ] **Step 3: Wire `generate_diff.py`.** Change its import block (lines 23–29) to add `resolve_output_path`:

```python
from modlist_utils import (
    load_modlist,
    extract_mods,
    get_separator_order,
    get_version,
    match_mods,
    resolve_output_path,
)
```

Replace the output block (lines 789–795):

```python
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html_output)
        print(f"Diff written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(html_output)
```

with:

```python
    out_path = resolve_output_path(args.output, args.old_list, args.new_list, "diff", "html")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_output)
        print(f"Diff written to {out_path}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(html_output)
```

- [ ] **Step 4: Smoke-test the CLI wiring.** Run the two commands in **Verify** above, confirm the nested files were created, then delete `../_verify_out/`.

- [ ] **Step 5: Confirm unit tests still pass.**

Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage -v`
Expected: OK.

- [ ] **Step 6: Commit.**

```bash
git add tools/generate_coverage.py tools/generate_changelog.py tools/generate_diff.py
git commit -m "feat(tools): -o accepts a directory, auto-nesting reports by list"
```

---

### Task 3: Reframe "Missing" → green "Add"

**Goal:** Rename `CoverageState.MISSING` → `CoverageState.ADD`, recolor red → green, and relabel the summary chip/badge from "missing" to "to add"/"add". No row tag.

**Files:**
- Modify: `tools/generate_coverage.py` (enum lines 38–43; classify line 85; `ACTIONABLE_STATES` lines 134–138; CSS lines 158 & 197; `_STATE_CSS` lines 208–213; summary render line 317)
- Modify: `tools/test_generate_coverage.py` (rename `test_missing`; update `SummaryTest`; add a recolor assertion)

**Acceptance Criteria:**
- [ ] `CoverageState.ADD` (value `"add"`) replaces `MISSING` everywhere; no `MISSING`/`mod-missing`/`stat-missing` remains.
- [ ] Add rows use the green `.mod-add` style; summary chip reads `N to add` with `.stat-add`.
- [ ] Section badge term for that state is `add` (e.g. `1 add · 2 newer`).
- [ ] `python -m unittest test_generate_coverage -v` is green.

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → OK.

**Steps:**

- [ ] **Step 1: Update the tests (failing).** In `tools/test_generate_coverage.py`:

Rename `test_missing` and switch the state to `ADD`:

```python
    def test_add(self):
        result = classify_source_mods(self.source, self.target)
        row = self._state_of(result, "MissingMod")
        self.assertEqual(row.state, CoverageState.ADD)
        self.assertEqual(row.target_version, "")
        self.assertEqual(row.nexus_id, 99999)
```

In `SummaryTest.test_counts`, change the assertion:

```python
        self.assertEqual(summary["counts"][CoverageState.ADD], 1)
```

Add a render test to `RenderTest`:

```python
    def test_add_recolor(self):
        # "Missing" mods are reframed as green "to add" candidates (no red).
        self.assertIn("mod-add", self.html)
        self.assertIn("to add", self.html)
        self.assertNotIn("mod-missing", self.html)
        self.assertNotIn("stat-missing", self.html)
```

- [ ] **Step 2: Run tests to confirm failure.**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: FAIL — `AttributeError: ADD` (enum member doesn't exist yet).

- [ ] **Step 3: Rename the enum** (lines 38–43):

```python
class CoverageState(Enum):
    ADD = "add"           # source mod not present in target (candidate to add)
    NEWER = "newer"       # source version > target version (actionable: pull in)
    DIFFERS = "differs"   # both known, differ, direction undeterminable (actionable)
    COMMON = "common"     # same version, source is OLDER (target ahead), or unknown
```

- [ ] **Step 4: Update the classify assignment** (line 85), changing `MISSING` to `ADD`:

```python
        if target_mod is None:
            state = CoverageState.ADD
            target_version = ""
```

- [ ] **Step 5: Update `ACTIONABLE_STATES`** (lines 134–138):

```python
ACTIONABLE_STATES = [
    (CoverageState.ADD, "add"),
    (CoverageState.NEWER, "newer"),
    (CoverageState.DIFFERS, "differs"),
]
```

- [ ] **Step 6: Recolor the CSS.** Replace the missing stat rule (line 158):

```css
.stat-missing { background: #3a1a1a; color: #f87171; }
```

with:

```css
.stat-add { background: #0d2a16; color: #4ade80; }
```

Replace the missing mod-row rule (line 197):

```css
.mod-missing { background: #2a0a0a; border-left-color: #f87171; color: #f87171; }
```

with:

```css
.mod-add { background: #0d2a16; border-left-color: #4ade80; color: #4ade80; }
```

- [ ] **Step 7: Update `_STATE_CSS`** (lines 208–213):

```python
_STATE_CSS = {
    CoverageState.ADD: "mod-add",
    CoverageState.NEWER: "mod-newer",
    CoverageState.DIFFERS: "mod-differs",
    CoverageState.COMMON: "mod-common",
}
```

- [ ] **Step 8: Update the summary chip** (line 317). Replace:

```python
    parts.append(f'<span class="stat stat-missing">{counts[CoverageState.MISSING]} missing</span>')
```

with:

```python
    parts.append(f'<span class="stat stat-add">{counts[CoverageState.ADD]} to add</span>')
```

- [ ] **Step 9: Run tests to confirm they pass.**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: OK.

- [ ] **Step 10: Commit.**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat(coverage): reframe missing mods as green 'to add' candidates"
```

---

### Task 4: Flip the version arrow (target → source), drop the up-arrow

**Goal:** Display versions target-first so a row reads as the upgrade you'd make; remove the `↑` for NEWER.

**Files:**
- Modify: `tools/generate_coverage.py` (`_version_html`, lines 249–258)
- Modify: `tools/test_generate_coverage.py` (`test_newer_direction_and_versions`, `test_differs_glyph`)

**Acceptance Criteria:**
- [ ] NEWER renders `{target} → {source}` (e.g. `1.4 → 1.5`) with no `↑`.
- [ ] DIFFERS renders `{target} ≠ {source}` (e.g. `1.0alpha ≠ 1.0beta`).
- [ ] ADD/COMMON still show the source (candidate) version.
- [ ] No `↑` anywhere in the output.

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → OK.

**Steps:**

- [ ] **Step 1: Update the tests (failing).** In `tools/test_generate_coverage.py`, replace `test_newer_direction_and_versions`:

```python
    def test_newer_direction_and_versions(self):
        # Target-first (your version -> candidate), no up-arrow.
        self.assertIn("1.4 → 1.5", self.html)  # tgt -> src (cleaned)
        self.assertNotIn("↑", self.html)
```

In `test_differs_glyph`, change the version assertion line:

```python
        self.assertIn("1.0alpha ≠ 1.0beta", self.html)      # tgt ≠ src (DiffMod)
```

- [ ] **Step 2: Run tests to confirm failure.**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: FAIL — `1.4 → 1.5` not found (current output still `↑ 1.5 → 1.4`).

- [ ] **Step 3: Rewrite `_version_html`** (lines 249–258):

```python
def _version_html(row):
    state = row.state
    src = _esc(row.source_version) if row.source_version != "Unknown" else ""
    tgt = _esc(row.target_version) if row.target_version != "Unknown" else ""
    if state == CoverageState.NEWER:
        # Read as the upgrade you'd make: your (target) version -> candidate (source).
        return f"{tgt} → {src}"
    if state == CoverageState.DIFFERS:
        return f"{tgt} ≠ {src}"
    # ADD and COMMON (incl. source-older / target-ahead): show the source version.
    return src
```

- [ ] **Step 4: Run tests to confirm they pass.**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: OK.

- [ ] **Step 5: Commit.**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat(coverage): show versions as your-version -> candidate, drop up-arrow"
```

---

### Task 5: Major-section divider bands

**Goal:** Render dash-wrapped "major" separators (`---------- BASE ----------`) as full-width, non-interactive divider bands grouping the sub-sections that follow.

**Files:**
- Modify: `tools/generate_coverage.py` (add `is_major_separator` / `major_display_name` / `map_sections_to_majors` helpers; add `.band` CSS; add `_render_band` / `_render_bandless_rows`; change `render_html` loop + signature; call mapper in `main()`)
- Modify: `tools/test_generate_coverage.py` (add `MajorSectionTest`)

**Acceptance Criteria:**
- [ ] `is_major_separator` is True for `---------- BASE ----------` and `- - - GAMEPLAY CHANGES - - -`, False for `NS3 - SKSE Plugins & Fixes`, `21-9 WideScreen Support`, and `""`.
- [ ] `major_display_name` strips decoration → `BASE`, `GAMEPLAY CHANGES`.
- [ ] A `<div class="band">NAME</div>` is emitted once when the major changes; sub-sections still render with their headers.
- [ ] Sections before the first major emit no band; existing `RenderTest` (no majors) still passes (`render_html` keeps a 4-arg form via a defaulted param).

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → OK.

**Steps:**

- [ ] **Step 1: Add the tests (failing).** Append to `tools/test_generate_coverage.py`:

```python
class MajorSectionTest(unittest.TestCase):
    def test_is_major_separator(self):
        from generate_coverage import is_major_separator, major_display_name
        self.assertTrue(is_major_separator("---------- BASE ----------"))
        self.assertTrue(is_major_separator("- - - GAMEPLAY CHANGES - - -"))
        self.assertFalse(is_major_separator("NS3 - SKSE Plugins & Fixes"))
        self.assertFalse(is_major_separator("21-9 WideScreen Support"))
        self.assertFalse(is_major_separator(""))
        self.assertEqual(major_display_name("---------- BASE ----------"), "BASE")
        self.assertEqual(
            major_display_name("- - - GAMEPLAY CHANGES - - -"), "GAMEPLAY CHANGES"
        )

    def test_band_emitted_per_major(self):
        from generate_coverage import (
            classify_source_mods,
            compute_summary,
            render_html,
            map_sections_to_majors,
        )
        source = [
            {"type": "separator", "separatorName": "---------- BASE ----------", "order": 0},
            {"type": "separator", "separatorName": "Base Game Cleaned", "order": 1},
            {"type": "mod", "modName": "Cleaned Masters", "order": 2,
             "separatorName": "Base Game Cleaned", "id": 1, "general": {"version": "1.0"}},
            {"type": "separator", "separatorName": "---------- USER INTERFACE ----------", "order": 3},
            {"type": "separator", "separatorName": "UI Stuff", "order": 4},
            {"type": "mod", "modName": "SkyUI", "order": 5,
             "separatorName": "UI Stuff", "id": 2, "general": {"version": "1.0"}},
        ]
        rows = classify_source_mods(source, [])
        summary = compute_summary(rows)
        majors = map_sections_to_majors(source)
        html = render_html(rows, summary, "S", "T", majors)
        self.assertIn('<div class="band">BASE</div>', html)
        self.assertIn('<div class="band">USER INTERFACE</div>', html)
        self.assertIn("Base Game Cleaned", html)
        self.assertIn("UI Stuff", html)
```

- [ ] **Step 2: Run tests to confirm failure.**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: FAIL — `ImportError: cannot import name 'is_major_separator'`.

- [ ] **Step 3: Add the detection + mapping helpers.** In `tools/generate_coverage.py`, add directly above `classify_source_mods` (before line 58):

```python
def is_major_separator(name):
    """A 'major' separator is one whose name is wrapped in dashes, e.g.
    '---------- BASE ----------' or '- - - GAMEPLAY CHANGES - - -'. It denotes an
    implicit top-level grouping in MO2's otherwise-flat separator list."""
    s = (name or "").strip()
    return len(s) >= 2 and s[0] == "-" and s[-1] == "-" and any(c.isalnum() for c in s)


def major_display_name(name):
    """Strip surrounding dash/space decoration: '---------- BASE ----------' -> 'BASE'."""
    return (name or "").strip().strip("- ").strip()


def map_sections_to_majors(source_data):
    """Walk the source list in order, mapping each section name to the display name
    of the major separator in effect when it first appears (None before the first)."""
    section_majors = {}
    current_major = None
    for item in source_data:
        item_type = item.get("type")
        if item_type == "separator":
            name = item.get("separatorName") or ""
            if is_major_separator(name):
                current_major = major_display_name(name)
            section_majors.setdefault(name, current_major)
        elif item_type == "mod":
            name = item.get("separatorName") or "Unsectioned"
            section_majors.setdefault(name, current_major)
    return section_majors
```

- [ ] **Step 4: Add the `.band` CSS.** In the `CSS` string, add this rule right after the `.badge` rule (after line 186):

```css
.band {
    background: #141d3a; color: #8aa0c8; text-align: center;
    font-weight: 800; letter-spacing: 2px; font-size: 11px; padding: 8px 12px;
    border-top: 1px solid #24345a; border-bottom: 1px solid #24345a;
}
```

- [ ] **Step 5: Add band/bandless render helpers.** In `tools/generate_coverage.py`, add above `_render_section` (before line 271):

```python
def _render_band(parts, display_name):
    parts.append(f'<div class="band">{_esc(display_name)}</div>')


def _render_bandless_rows(parts, rows):
    # Mods sitting directly under a major separator: rows render beneath the band
    # with no sub-header (the band is their header).
    parts.append('<div class="section-body">')
    for row in rows:
        _render_mod_row(parts, row)
    parts.append("</div>")
```

- [ ] **Step 6: Update `render_html`.** Change the signature (line 288) to accept `section_majors`:

```python
def render_html(rows_by_section, summary, source_name, target_name, section_majors=None):
    """Render the coverage view as a self-contained HTML document."""
    section_majors = section_majors or {}
    counts = summary["counts"]
```

Then replace the section loop (lines 324–326):

```python
    # Sections
    for section_name, rows in rows_by_section.items():
        _render_section(parts, section_name, rows)
```

with:

```python
    # Sections, with a divider band emitted whenever the major section changes.
    prev_major = object()  # sentinel: distinct from any real value, including None
    for section_name, rows in rows_by_section.items():
        major = section_majors.get(section_name)
        if major != prev_major:
            if major:
                _render_band(parts, major)
            prev_major = major
        if is_major_separator(section_name):
            _render_bandless_rows(parts, rows)
        else:
            _render_section(parts, section_name, rows)
```

- [ ] **Step 7: Compute and pass the mapping in `main()`.** After `rows_by_section = classify_source_mods(...)` (line 370), add:

```python
    section_majors = map_sections_to_majors(source_data)
```

Change the `render_html` call (line 376) to:

```python
    html_output = render_html(rows_by_section, summary, source_name, target_name, section_majors)
```

- [ ] **Step 8: Run tests to confirm they pass.**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: OK (including `MajorSectionTest` and the unchanged `RenderTest`).

- [ ] **Step 9: Regenerate a real report and eyeball the bands.**

```bash
cd tools
python generate_coverage.py "../lists/NORDIC SOULS v3.0.1.json" "../lists/Meteoric 0.0.3.json" -o ../_verify_out/
```

Open `../_verify_out/Meteoric 0.0.3/NORDIC SOULS v3.0.1.coverage.html`; confirm `BASE`, `AUDIO`, `USER INTERFACE`, etc. appear as centered divider bands with sub-sections grouped under them. Delete `../_verify_out/` afterward.

- [ ] **Step 10: Commit.**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat(coverage): render dash-wrapped major separators as divider bands"
```

---

### Task 6: Sticky sub-section headers

**Goal:** Pin each `.section-header` just beneath the already-sticky main header while its section is onscreen.

**Files:**
- Modify: `tools/generate_coverage.py` (`.section-header` CSS lines 177–181; the `<script>` block lines 329–338)
- Modify: `tools/test_generate_coverage.py` (add `test_section_headers_sticky`)

**Acceptance Criteria:**
- [ ] `.section-header` has `position: sticky` and `top: var(--header-h, ...)` with `z-index` below the main header (`z-50`).
- [ ] An inline script sets `--header-h` from the main header's height on load and resize.
- [ ] `python -m unittest test_generate_coverage -v` is green.

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → OK; then scroll a regenerated report and confirm sub-headers pin under the main header.

**Steps:**

- [ ] **Step 1: Add the test (failing).** Append to `RenderTest` in `tools/test_generate_coverage.py`:

```python
    def test_section_headers_sticky(self):
        # Sub-section headers pin under the main header while scrolling.
        match = re.search(r"\.section-header \{[^}]*\}", self.html)
        self.assertIsNotNone(match, "no .section-header CSS rule found")
        rule = match.group()
        self.assertIn("position: sticky", rule)
        self.assertIn("var(--header-h", rule)
        # The offset variable is set from the main header's measured height.
        self.assertIn("--header-h", self.html)
```

- [ ] **Step 2: Run the test to confirm failure.**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: FAIL — `position: sticky` not in `.section-header` rule.

- [ ] **Step 3: Make `.section-header` sticky.** Replace the rule (lines 177–181):

```css
.section-header {
    background: #1e2a4a; padding: 8px 16px; font-weight: 700; font-size: 14px;
    color: #cbd5e1; cursor: pointer; user-select: none;
    display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #0f3460;
}
```

with:

```css
.section-header {
    position: sticky; top: var(--header-h, 0px); z-index: 40;
    background: #1e2a4a; padding: 8px 16px; font-weight: 700; font-size: 14px;
    color: #cbd5e1; cursor: pointer; user-select: none;
    display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #0f3460;
}
```

- [ ] **Step 4: Set `--header-h` from JS.** In `render_html`'s `<script>` block, extend the appended string (lines 330–337). Replace:

```python
    parts.append(
        "function toggleSection(h){h.parentElement.classList.toggle('collapsed');}"
        "function expandAll(){document.querySelectorAll('.section').forEach(function(s){s.classList.remove('collapsed');});}"
        "function collapseAll(){document.querySelectorAll('.section').forEach(function(s){s.classList.add('collapsed');});}"
        "function toggleCommon(){var on=document.body.classList.toggle('hide-common');"
        "var b=document.getElementById('toggle-common');b.classList.toggle('active',on);"
        "b.textContent=on?'Show common mods':'Hide common mods';}"
    )
```

with:

```python
    parts.append(
        "function toggleSection(h){h.parentElement.classList.toggle('collapsed');}"
        "function expandAll(){document.querySelectorAll('.section').forEach(function(s){s.classList.remove('collapsed');});}"
        "function collapseAll(){document.querySelectorAll('.section').forEach(function(s){s.classList.add('collapsed');});}"
        "function toggleCommon(){var on=document.body.classList.toggle('hide-common');"
        "var b=document.getElementById('toggle-common');b.classList.toggle('active',on);"
        "b.textContent=on?'Show common mods':'Hide common mods';}"
        "function setHeaderH(){var h=document.querySelector('.header');"
        "if(h)document.documentElement.style.setProperty('--header-h',h.offsetHeight+'px');}"
        "window.addEventListener('resize',setHeaderH);setHeaderH();"
    )
```

- [ ] **Step 5: Run the test to confirm it passes.**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: OK.

- [ ] **Step 6: Eyeball the sticky behavior.** Regenerate a report (as in Task 5 Step 9), scroll a long section, and confirm the sub-section header stays pinned just under the main header, then hands off to the next section. Delete `../_verify_out/` afterward.

- [ ] **Step 7: Commit.**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat(coverage): sticky sub-section headers under the main header"
```

---

### Task 7: Update `CLAUDE.md`

**Goal:** Document the reframed states, version direction, major-section bands, sticky headers, and the new `-o` directory behavior.

**Files:**
- Modify: `CLAUDE.md` (coverage "Mod states" + "Features" block; "The Tools" intro)

**Acceptance Criteria:**
- [ ] "Missing (red)" is replaced by "Add (green)"; Newer note reflects `your-version → candidate` and no `↑`.
- [ ] Features mention major-section divider bands and sticky section headers.
- [ ] A shared note documents `-o <dir>` auto-nesting for all three tools.
- [ ] Full test suite still green.

**Verify:** `cd tools && python -m unittest test_modlist_utils test_generate_coverage -v` → OK; `git diff --stat` shows `CLAUDE.md` modified.

**Steps:**

- [ ] **Step 1: Update the "Mod states" + "Features" block.** In `CLAUDE.md`, replace:

```markdown
**Mod states** (source-ahead only is actionable):

- **Missing** (red) — not in the target; name links to its Nexus page
- **Newer** (orange, ↑) — source version is newer than target's
- **Differs** (amber, ≠) — versions differ but direction is unclear (kept actionable)
- **Common** (gray) — same version, source is *older* than the target, or either version is
  unknown. Source-older is folded into Common because it isn't actionable.

Features: single column grouped by source separator; collapsible headers with count badges;
all-common sections start collapsed while sections with gaps start expanded; summary bar;
"Hide common mods" toggle; Expand all / Collapse all.
```

with:

```markdown
**Mod states** (source-ahead only is actionable):

- **Add** (green) — not in the target; a candidate to pull into your list; name links to its
  Nexus page
- **Newer** (orange) — source version is newer than target's; shown as `your-version → candidate`
- **Differs** (amber, ≠) — versions differ but direction is unclear (kept actionable)
- **Common** (gray) — same version, source is *older* than the target, or either version is
  unknown. Source-older is folded into Common because it isn't actionable.

Features: single column grouped by source separator; **major separators** (dash-wrapped names
like `---------- BASE ----------`) render as full-width divider bands; **sticky** collapsible
section headers with count badges; all-common sections start collapsed while sections with gaps
start expanded; summary bar; "Hide common mods" toggle; Expand all / Collapse all.
```

- [ ] **Step 2: Add the shared output-path note.** In `CLAUDE.md`, immediately after the "The Tools" intro paragraph (ending "standard library only."), add:

```markdown
**Output paths:** every tool's `-o` accepts either a file path (written as-is) or a directory.
Given a directory (e.g. `-o output/`), the report is auto-named
`<dir>/<second-list>/<first-list>.<type>.<ext>` — the folder is the 2nd positional argument
(coverage→target, diff/changelog→new list), the file the 1st. Omitting `-o` still writes to
stdout.
```

- [ ] **Step 3: Confirm the suite is green.**

Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage -v`
Expected: OK.

- [ ] **Step 4: Commit.**

```bash
git add CLAUDE.md
git commit -m "docs: document coverage report improvements and -o directory behavior"
```

---

## Self-Review

**Spec coverage:** Change 1 → T3; Change 2 → T4; Change 3 (sticky) → T6; Change 4 (bands) → T5; Change 5 (output folders) → T1 (helper) + T2 (wiring); testing/docs → woven into each task + T7. No spec section is unaddressed.

**Placeholder scan:** No "TBD"/"handle edge cases"/"write tests for the above" — every step shows the actual code or command.

**Type/name consistency:** `CoverageState.ADD`, `resolve_output_path(output_arg, first_path, second_path, type_label, ext)`, `is_major_separator` / `major_display_name` / `map_sections_to_majors`, `_render_band` / `_render_bandless_rows`, and `render_html(..., section_majors=None)` are used identically across the tasks and tests. The `render_html` default keeps the existing 4-arg `RenderTest` call valid while T5 adds the 5-arg form.
