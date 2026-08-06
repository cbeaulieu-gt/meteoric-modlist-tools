# generate_coverage.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `comparisons/generate_coverage.py`, a tool that renders a source modlist's contents (grouped by its own sections) and highlights which mods the target list is missing or has at a different version.

**Architecture:** A new standalone script in the `comparisons/` ecosystem that reuses `modlist_utils.match_mods` (pure waterfall matching, no config files) and a new `modlist_utils.compare_versions` helper. It classifies every source mod into one of five states (Missing / Newer / Older / Differs / Common) and emits a self-contained, collapsible, dark-themed HTML "coverage view" — single column, source-structured.

**Tech Stack:** Python 3.13 (stdlib only: `argparse`, `dataclasses`, `enum`, `html`, `re`, `collections.OrderedDict`). Tests use stdlib `unittest` (pytest is not installed). HTML output uses inline CSS/JS, no external dependencies.

**Spec:** [docs/design/2026-06-07-generate-coverage-tool-design.md](../design/2026-06-07-generate-coverage-tool-design.md)

---

### Task 1: Add `compare_versions` helper to `modlist_utils.py`

**Goal:** A best-effort version comparison helper that returns ordering (-1/0/1) or `None` when direction can't be determined.

**Files:**
- Modify: `comparisons/modlist_utils.py` (append after `get_version`, before the Name Normalization section)
- Create: `comparisons/test_modlist_utils.py`

**Acceptance Criteria:**
- [ ] `compare_versions("4.3.6", "4.3.5") == 1` and `compare_versions("4.3.5", "4.3.6") == -1`
- [ ] `compare_versions("1.7", "1.7beta") is None` (numeric parts equal, strings differ → undeterminable)
- [ ] `compare_versions("7/31/2025", "7/30/2025") == 1` (date form)
- [ ] `compare_versions("MCM-01", "Alpha-58") is None` (no numeric/date part)
- [ ] `compare_versions("2.0", "2.0") == 0` and `compare_versions("1.2", "1.2.0") == 0` (zero-padding)
- [ ] All tests pass via `python comparisons/test_modlist_utils.py -v`

**Verify:** `python comparisons/test_modlist_utils.py -v` → `OK` (all tests pass)

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `comparisons/test_modlist_utils.py`:

```python
"""Unit tests for modlist_utils helpers."""

import os
import sys
import unittest

# Allow `import modlist_utils` when run directly (same-dir import, like the scripts).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modlist_utils import compare_versions


class CompareVersionsTest(unittest.TestCase):
    def test_numeric_greater(self):
        self.assertEqual(compare_versions("4.3.6", "4.3.5"), 1)

    def test_numeric_less(self):
        self.assertEqual(compare_versions("4.3.5", "4.3.6"), -1)

    def test_equal_strings(self):
        self.assertEqual(compare_versions("2.0", "2.0"), 0)

    def test_zero_padding_equal(self):
        self.assertEqual(compare_versions("1.2", "1.2.0"), 0)

    def test_numeric_equal_suffix_differs(self):
        self.assertIsNone(compare_versions("1.7", "1.7beta"))

    def test_letter_suffix_same_numeric(self):
        self.assertIsNone(compare_versions("4.3.6c", "4.3.6"))

    def test_date_greater(self):
        self.assertEqual(compare_versions("7/31/2025", "7/30/2025"), 1)

    def test_date_less(self):
        self.assertEqual(compare_versions("1/1/2024", "12/31/2024"), -1)

    def test_non_numeric_unknown_direction(self):
        self.assertIsNone(compare_versions("MCM-01", "Alpha-58"))

    def test_date_vs_numeric_not_comparable(self):
        self.assertIsNone(compare_versions("7/31/2025", "4.3.6"))

    def test_unknown_inputs(self):
        self.assertIsNone(compare_versions("Unknown", "2.0"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python comparisons/test_modlist_utils.py -v`
Expected: FAIL — `ImportError: cannot import name 'compare_versions' from 'modlist_utils'`

- [ ] **Step 3: Write minimal implementation**

In `comparisons/modlist_utils.py`, add after the `get_version` function (the `re` module is already imported at the top of the file):

```python
# ---------------------------------------------------------------------------
# Version Comparison
# ---------------------------------------------------------------------------

def _parse_version_for_compare(v):
    """
    Parse an already-cleaned version string into a comparable representation.

    Returns:
        ("date", (year, month, day))  for M/D/YYYY dates
        ("num", (int, int, ...))      for a leading numeric dotted sequence
        None                          when no numeric/date part is parseable
    """
    if not v or v == "Unknown":
        return None
    v = v.strip()

    # Date form produced by clean_version: M/D/YYYY
    date_match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
    if date_match:
        month, day, year = (int(x) for x in date_match.groups())
        return ("date", (year, month, day))

    # Leading numeric dotted sequence, e.g. "4.3.6c" -> (4, 3, 6)
    num_match = re.match(r"^(\d+(?:\.\d+)*)", v)
    if num_match:
        nums = tuple(int(x) for x in num_match.group(1).split("."))
        return ("num", nums)

    return None


def compare_versions(a, b):
    """
    Best-effort comparison of two already-cleaned version strings.

    Returns:
        -1  if a < b
         0  if a == b
         1  if a > b
       None if the versions differ but the direction can't be determined
            (e.g. equal numeric parts with differing suffixes, non-numeric
            strings, or a date compared against a numeric version).
    """
    if a == b:
        return 0

    pa = _parse_version_for_compare(a)
    pb = _parse_version_for_compare(b)
    if pa is None or pb is None:
        return None

    kind_a, val_a = pa
    kind_b, val_b = pb
    if kind_a != kind_b:
        return None  # date vs numeric — not comparable

    if kind_a == "date":
        if val_a < val_b:
            return -1
        if val_a > val_b:
            return 1
        return None  # same date but original strings differed

    # numeric: zero-pad to equal length, then compare
    la, lb = list(val_a), list(val_b)
    n = max(len(la), len(lb))
    la += [0] * (n - len(la))
    lb += [0] * (n - len(lb))
    if la < lb:
        return -1
    if la > lb:
        return 1
    return None  # numeric parts equal but full strings differ (e.g. "1.7" vs "1.7beta")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python comparisons/test_modlist_utils.py -v`
Expected: PASS — `Ran 11 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add comparisons/modlist_utils.py comparisons/test_modlist_utils.py
git commit -m "feat: add compare_versions helper to modlist_utils"
```

---

### Task 2: Coverage classification logic in `generate_coverage.py`

**Goal:** Create the new script's data structures and classification logic — turn a source/target pair into ordered, section-grouped `CoverageRow`s plus a summary.

**Files:**
- Create: `comparisons/generate_coverage.py` (data structures + classification + summary; rendering/CLI added in Task 3)
- Create: `comparisons/test_generate_coverage.py`

**Acceptance Criteria:**
- [ ] A source mod with no target match → `CoverageState.MISSING`, `target_version == ""`
- [ ] Matched mod, source version > target version → `CoverageState.NEWER`
- [ ] Matched mod, source version < target version → `CoverageState.OLDER`
- [ ] Matched mod, both versions known but direction undeterminable → `CoverageState.DIFFERS`
- [ ] Matched mod, equal versions OR either version `"Unknown"` → `CoverageState.COMMON`
- [ ] Sections are keyed in source order; mods with no separator group under `"Unsectioned"`
- [ ] `compute_summary` returns total and per-state counts matching the rows
- [ ] All tests pass via `python comparisons/test_generate_coverage.py -v`

**Verify:** `python comparisons/test_generate_coverage.py -v` → `OK`

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `comparisons/test_generate_coverage.py`:

```python
"""Tests for generate_coverage classification and summary."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_coverage import (
    CoverageState,
    classify_source_mods,
    compute_summary,
)


def sep(name, order):
    return {"type": "separator", "separatorName": name, "order": order}


def mod(name, order, separator, version=None, nexus_id=None, plugins=None):
    item = {
        "type": "mod",
        "modName": name,
        "order": order,
        "separatorName": separator,
    }
    if version is not None:
        item["general"] = {"version": version}
    if nexus_id is not None:
        item["id"] = nexus_id
    if plugins is not None:
        item["plugins"] = plugins
    return item


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        # Source list: 2 sections, 4 mods covering each state.
        self.source = [
            sep("Combat", 0),
            mod("Valhalla Combat", 1, "Combat", version="1.5.0", nexus_id=64741),
            mod("MissingMod", 2, "Combat", version="2.0.0", nexus_id=99999),
            sep("Visuals", 3),
            mod("ENB Helper", 4, "Visuals", version="1.5.0", nexus_id=23174),
            mod("SameMod", 5, "Visuals", version="3.0.0", nexus_id=11111),
        ]
        # Target: has Valhalla (older), ENB Helper (newer), SameMod (equal).
        self.target = [
            sep("Gameplay", 0),
            mod("Valhalla Combat", 1, "Gameplay", version="1.4.0", nexus_id=64741),
            mod("ENB Helper SE", 2, "Gameplay", version="1.6.0", nexus_id=23174),
            mod("SameMod", 3, "Gameplay", version="3.0.0", nexus_id=11111),
        ]

    def _state_of(self, rows_by_section, mod_name):
        for rows in rows_by_section.values():
            for row in rows:
                if row.mod.get("modName") == mod_name:
                    return row
        raise AssertionError(f"{mod_name} not found")

    def test_newer(self):
        result = classify_source_mods(self.source, self.target)
        row = self._state_of(result, "Valhalla Combat")
        self.assertEqual(row.state, CoverageState.NEWER)
        self.assertEqual(row.source_version, "1.5.0")
        self.assertEqual(row.target_version, "1.4.0")

    def test_older(self):
        result = classify_source_mods(self.source, self.target)
        row = self._state_of(result, "ENB Helper")
        self.assertEqual(row.state, CoverageState.OLDER)

    def test_common(self):
        result = classify_source_mods(self.source, self.target)
        row = self._state_of(result, "SameMod")
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_missing(self):
        result = classify_source_mods(self.source, self.target)
        row = self._state_of(result, "MissingMod")
        self.assertEqual(row.state, CoverageState.MISSING)
        self.assertEqual(row.target_version, "")
        self.assertEqual(row.nexus_id, 99999)

    def test_section_order_and_keys(self):
        result = classify_source_mods(self.source, self.target)
        self.assertEqual(list(result.keys()), ["Combat", "Visuals"])

    def test_unsectioned(self):
        source = [mod("Orphan", 0, "")]  # no separator
        result = classify_source_mods(source, [])
        self.assertIn("Unsectioned", result)

    def test_unknown_version_is_common(self):
        source = [sep("S", 0), mod("X", 1, "S", nexus_id=42)]  # no version
        target = [sep("T", 0), mod("X", 1, "T", version="2.0", nexus_id=42)]
        result = classify_source_mods(source, target)
        row = self._state_of(result, "X")
        self.assertEqual(row.state, CoverageState.COMMON)


class SummaryTest(unittest.TestCase):
    def test_counts(self):
        source = [
            sep("S", 0),
            mod("a", 1, "S", version="2.0", nexus_id=1),  # missing
            mod("b", 2, "S", version="2.0", nexus_id=2),  # common
        ]
        target = [sep("T", 0), mod("b", 1, "T", version="2.0", nexus_id=2)]
        rows = classify_source_mods(source, target)
        summary = compute_summary(rows)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["counts"][CoverageState.MISSING], 1)
        self.assertEqual(summary["counts"][CoverageState.COMMON], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python comparisons/test_generate_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'generate_coverage'`

- [ ] **Step 3: Write minimal implementation**

Create `comparisons/generate_coverage.py`:

```python
"""
Source-structured coverage view generator.

Renders one modlist (the SOURCE) organized by its own section structure,
highlighting which mods the TARGET list is missing or has at a different
version. Unlike generate_diff.py, load order is not considered — this compares
modlist *contents* through the lens of the source list's organization.

Reuses the pure-waterfall matching in modlist_utils (no ignore/alias/compendium
config files), consistent with generate_diff.py and generate_changelog.py.

Usage:
    python generate_coverage.py SOURCE.json TARGET.json [-o output.html]
"""

import argparse
import html
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from modlist_utils import (
    load_modlist,
    extract_mods,
    get_version,
    match_mods,
    compare_versions,
)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class CoverageState(Enum):
    MISSING = "missing"   # source mod not present in target
    NEWER = "newer"       # source version > target version
    OLDER = "older"       # source version < target version
    DIFFERS = "differs"   # both known, differ, direction undeterminable
    COMMON = "common"     # equal, or either version unknown


@dataclass
class CoverageRow:
    mod: dict
    state: CoverageState
    source_version: str
    target_version: str          # "" when the mod is missing
    nexus_id: Optional[int]      # numeric Nexus id, or None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_source_mods(source_data, target_data, min_confidence=0.80):
    """
    Classify every source mod against the target list.

    Returns an OrderedDict {section_name: [CoverageRow, ...]} keyed in the order
    sections first appear in the source list. Mods with no separator are grouped
    under "Unsectioned".
    """
    source_mods = extract_mods(source_data)
    target_mods = extract_mods(target_data)

    matched, _added, _removed = match_mods(source_mods, target_mods, min_confidence)
    match_lookup = {id(s): t for s, t in matched}

    rows_by_section = OrderedDict()

    for mod in source_mods:
        section = mod.get("separatorName") or "Unsectioned"
        if section not in rows_by_section:
            rows_by_section[section] = []

        source_version = get_version(mod)
        target_mod = match_lookup.get(id(mod))

        if target_mod is None:
            state = CoverageState.MISSING
            target_version = ""
        else:
            target_version = get_version(target_mod)
            if source_version == "Unknown" or target_version == "Unknown":
                state = CoverageState.COMMON
            else:
                cmp = compare_versions(source_version, target_version)
                if cmp == 1:
                    state = CoverageState.NEWER
                elif cmp == -1:
                    state = CoverageState.OLDER
                elif cmp is None:
                    state = CoverageState.DIFFERS
                else:  # cmp == 0
                    state = CoverageState.COMMON

        raw_id = mod.get("id")
        nexus_id = raw_id if isinstance(raw_id, int) else None

        rows_by_section[section].append(
            CoverageRow(mod, state, source_version, target_version, nexus_id)
        )

    return rows_by_section


def compute_summary(rows_by_section):
    """Compute total and per-state counts across all sections."""
    counts = {state: 0 for state in CoverageState}
    total = 0
    for rows in rows_by_section.values():
        for row in rows:
            counts[row.state] += 1
            total += 1
    return {"total": total, "counts": counts}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python comparisons/test_generate_coverage.py -v`
Expected: PASS — `Ran 9 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add comparisons/generate_coverage.py comparisons/test_generate_coverage.py
git commit -m "feat: add coverage classification logic"
```

---

### Task 3: HTML rendering + CLI in `generate_coverage.py`

**Goal:** Render the classified rows into a self-contained, collapsible HTML coverage view and wire up the argparse CLI.

**Files:**
- Modify: `comparisons/generate_coverage.py` (append rendering helpers, `render_html`, and `main`)
- Modify: `comparisons/test_generate_coverage.py` (add rendering tests)

**Acceptance Criteria:**
- [ ] `render_html` returns a string starting with `<!DOCTYPE html>` and containing the summary chips
- [ ] A missing mod with a numeric id renders an `<a href="https://www.nexusmods.com/skyrimspecialedition/mods/99999"` link
- [ ] A newer mod renders `↑` and `1.5.0 → 1.4.0`; an older mod renders `↓`
- [ ] A section whose mods are all `COMMON` is rendered with the `collapsed` class; a section with any actionable mod is not
- [ ] The output contains the `Hide common mods`, `Expand all`, and `Collapse all` controls and the `toggleCommon`/`expandAll`/`collapseAll` JS functions
- [ ] CLI: `python comparisons/generate_coverage.py SRC TGT -o OUT.html` writes a file and prints a confirmation to stderr
- [ ] All tests pass via `python comparisons/test_generate_coverage.py -v`

**Verify:** `python comparisons/test_generate_coverage.py -v` → `OK`

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `comparisons/test_generate_coverage.py` (before the `if __name__` block):

```python
from generate_coverage import render_html


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.source = [
            sep("Combat", 0),
            mod("Valhalla Combat", 1, "Combat", version="1.5.0", nexus_id=64741),
            mod("MissingMod", 2, "Combat", version="2.0.0", nexus_id=99999),
            sep("Done", 3),
            mod("SameMod", 4, "Done", version="3.0.0", nexus_id=11111),
        ]
        self.target = [
            sep("T", 0),
            mod("Valhalla Combat", 1, "T", version="1.4.0", nexus_id=64741),
            mod("SameMod", 2, "T", version="3.0.0", nexus_id=11111),
        ]
        self.rows = classify_source_mods(self.source, self.target)
        self.summary = compute_summary(self.rows)
        self.html = render_html(self.rows, self.summary, "Source", "Target")

    def test_doctype_and_summary(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))
        self.assertIn("Source", self.html)
        self.assertIn("Target", self.html)

    def test_nexus_link_for_missing(self):
        self.assertIn(
            'href="https://www.nexusmods.com/skyrimspecialedition/mods/99999"',
            self.html,
        )

    def test_newer_direction_and_versions(self):
        self.assertIn("↑", self.html)          # up arrow
        self.assertIn("1.5.0 → 1.4.0", self.html)  # src -> tgt

    def test_all_common_section_collapsed(self):
        # "Done" section has only SameMod (COMMON) -> collapsed by default.
        idx = self.html.index("Done")
        snippet = self.html[max(0, idx - 200):idx]
        self.assertIn("collapsed", snippet)

    def test_controls_present(self):
        self.assertIn("Hide common mods", self.html)
        self.assertIn("Expand all", self.html)
        self.assertIn("Collapse all", self.html)
        self.assertIn("function toggleCommon", self.html)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python comparisons/test_generate_coverage.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_html'`

- [ ] **Step 3: Write the implementation**

Append to `comparisons/generate_coverage.py`:

```python
# ---------------------------------------------------------------------------
# HTML Rendering
# ---------------------------------------------------------------------------

NEXUS_URL = "https://www.nexusmods.com/skyrimspecialedition/mods/{id}"

# Display order and labels for actionable states (used in badges/summary).
ACTIONABLE_STATES = [
    (CoverageState.MISSING, "missing"),
    (CoverageState.NEWER, "newer"),
    (CoverageState.OLDER, "older"),
    (CoverageState.DIFFERS, "differs"),
]

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #1a1a2e; color: #e0e0e0; font-size: 13px; line-height: 1.4;
    max-width: 1024px; margin: 0 auto 64px;
}
.header { background: #16213e; padding: 16px 24px; border-bottom: 2px solid #0f3460; }
.header h1 { font-size: 20px; color: #e94560; margin-bottom: 8px; }
.header .lists { color: #a0a0b0; font-size: 13px; margin-bottom: 8px; }
.header .lists span { color: #e0e0e0; font-weight: 600; }
.summary { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; }
.summary .stat { padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.stat-total { background: #2a2a3a; color: #cbd5e1; }
.stat-missing { background: #3a1a1a; color: #f87171; }
.stat-newer { background: #3a2a1a; color: #fb923c; }
.stat-older { background: #1a2a3a; color: #60a5fa; }
.stat-differs { background: #3a2f1a; color: #fbbf24; }
.stat-common { background: #232333; color: #9ca3af; }

.controls {
    position: fixed; top: 12px; z-index: 100;
    right: max(16px, calc(50% - 512px + 16px));
    display: flex; gap: 8px; align-items: center;
}
.toggle-btn {
    background: #0f3460; color: #e0e0e0; border: 1px solid #1a4a7a;
    border-radius: 4px; padding: 6px 12px; font-size: 12px; font-weight: 600;
    cursor: pointer; font-family: inherit; box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}
.toggle-btn:hover { background: #16498a; }
.toggle-btn.active { background: #e94560; border-color: #e94560; color: #fff; }

.section { border-bottom: 1px solid #252540; }
.section-header {
    background: #1e2a4a; padding: 8px 16px; font-weight: 700; font-size: 14px;
    color: #cbd5e1; cursor: pointer; user-select: none;
    display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #0f3460;
}
.section-header:hover { background: #243456; }
.caret { color: #888; font-size: 11px; width: 12px; display: inline-block; transition: transform 0.1s; }
.section.collapsed .caret { transform: rotate(-90deg); }
.section.collapsed .section-body { display: none; }
.badge { font-size: 11px; font-weight: 600; color: #94a3b8; margin-left: auto; }

.mod-row {
    padding: 3px 16px 3px 32px; display: flex; align-items: baseline; gap: 10px;
    border-left: 3px solid transparent;
}
.mod-row a { color: inherit; text-decoration: none; }
.mod-row a:hover { text-decoration: underline; }
.mod-name { flex: 1; }
.ver { font-size: 11px; white-space: nowrap; }

.mod-missing { background: #2a0a0a; border-left-color: #f87171; color: #f87171; }
.mod-newer  { background: #2a1c0a; border-left-color: #fb923c; }
.mod-newer .ver { color: #fb923c; }
.mod-older  { background: #0a1a2e; border-left-color: #60a5fa; }
.mod-older .ver { color: #60a5fa; }
.mod-differs { background: #2a240a; border-left-color: #fbbf24; }
.mod-differs .ver { color: #fbbf24; }
.mod-common { color: #9ca3af; }
.mod-common .ver { color: #6b7280; }

body.hide-common .mod-common { display: none; }
"""

_STATE_CSS = {
    CoverageState.MISSING: "mod-missing",
    CoverageState.NEWER: "mod-newer",
    CoverageState.OLDER: "mod-older",
    CoverageState.DIFFERS: "mod-differs",
    CoverageState.COMMON: "mod-common",
}


def _esc(text):
    """HTML-escape text."""
    return html.escape(str(text)) if text else ""


def _section_state_counts(rows):
    counts = {state: 0 for state in CoverageState}
    for row in rows:
        counts[row.state] += 1
    return counts


def _actionable_count(state_counts):
    return sum(state_counts[state] for state, _ in ACTIONABLE_STATES)


def _section_badge(state_counts):
    parts = [
        f"{state_counts[state]} {label}"
        for state, label in ACTIONABLE_STATES
        if state_counts[state]
    ]
    return " · ".join(parts) if parts else "all present"


def _name_html(row):
    name = _esc(row.mod.get("modName", "Unknown"))
    if row.nexus_id is not None:
        url = NEXUS_URL.format(id=row.nexus_id)
        return f'<a href="{url}" target="_blank" rel="noopener">{name}</a>'
    return name


def _version_html(row):
    state = row.state
    src = _esc(row.source_version) if row.source_version != "Unknown" else ""
    tgt = _esc(row.target_version) if row.target_version != "Unknown" else ""
    if state == CoverageState.NEWER:
        return f"↑ {src} → {tgt}"
    if state == CoverageState.OLDER:
        return f"↓ {src} → {tgt}"
    if state == CoverageState.DIFFERS:
        return f"{src} ≠ {tgt}"
    # MISSING and COMMON: show the source version (may be empty)
    return src


def _render_mod_row(parts, row):
    cls = _STATE_CSS[row.state]
    ver = _version_html(row)
    ver_html = f'<span class="ver">{ver}</span>' if ver else ""
    parts.append(f'<div class="mod-row {cls}">')
    parts.append(f'<span class="mod-name">{_name_html(row)}</span>')
    parts.append(ver_html)
    parts.append("</div>")


def _render_section(parts, section_name, rows):
    state_counts = _section_state_counts(rows)
    collapsed = "" if _actionable_count(state_counts) else " collapsed"
    badge = _esc(_section_badge(state_counts))
    parts.append(f'<div class="section{collapsed}">')
    parts.append('<div class="section-header" onclick="toggleSection(this)">')
    parts.append('<span class="caret">▾</span>')
    parts.append(f"<span>{_esc(section_name)}</span>")
    parts.append(f'<span class="badge">{badge}</span>')
    parts.append("</div>")
    parts.append('<div class="section-body">')
    for row in rows:
        _render_mod_row(parts, row)
    parts.append("</div>")
    parts.append("</div>")


def render_html(rows_by_section, summary, source_name, target_name):
    """Render the coverage view as a self-contained HTML document."""
    counts = summary["counts"]
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append("<title>Modlist Coverage</title>")
    parts.append(f"<style>{CSS}</style>")
    parts.append("</head>")
    parts.append("<body>")

    # Controls
    parts.append('<div class="controls">')
    parts.append('<button class="toggle-btn" onclick="expandAll()">Expand all</button>')
    parts.append('<button class="toggle-btn" onclick="collapseAll()">Collapse all</button>')
    parts.append('<button id="toggle-common" class="toggle-btn" onclick="toggleCommon()">Hide common mods</button>')
    parts.append("</div>")

    # Header + summary
    parts.append('<div class="header">')
    parts.append("<h1>Modlist Coverage</h1>")
    parts.append(
        f'<div class="lists">Source: <span>{_esc(source_name)}</span>'
        f' &nbsp;vs&nbsp; Target: <span>{_esc(target_name)}</span></div>'
    )
    parts.append('<div class="summary">')
    parts.append(f'<span class="stat stat-total">{summary["total"]} mods</span>')
    parts.append(f'<span class="stat stat-missing">{counts[CoverageState.MISSING]} missing</span>')
    parts.append(f'<span class="stat stat-newer">{counts[CoverageState.NEWER]} newer</span>')
    parts.append(f'<span class="stat stat-older">{counts[CoverageState.OLDER]} older</span>')
    parts.append(f'<span class="stat stat-differs">{counts[CoverageState.DIFFERS]} differs</span>')
    parts.append(f'<span class="stat stat-common">{counts[CoverageState.COMMON]} common</span>')
    parts.append("</div>")
    parts.append("</div>")

    # Sections
    for section_name, rows in rows_by_section.items():
        _render_section(parts, section_name, rows)

    # Scripts
    parts.append("<script>")
    parts.append(
        "function toggleSection(h){h.parentElement.classList.toggle('collapsed');}"
        "function expandAll(){document.querySelectorAll('.section').forEach(function(s){s.classList.remove('collapsed');});}"
        "function collapseAll(){document.querySelectorAll('.section').forEach(function(s){s.classList.add('collapsed');});}"
        "function toggleCommon(){var on=document.body.classList.toggle('hide-common');"
        "var b=document.getElementById('toggle-common');b.classList.toggle('active',on);"
        "b.textContent=on?'Show common mods':'Hide common mods';}"
    )
    parts.append("</script>")

    parts.append("</body></html>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate a source-structured HTML coverage view: shows the SOURCE "
            "list's mods (grouped by its sections) and highlights what the TARGET "
            "list is missing or has at a different version."
        )
    )
    parser.add_argument("source", help="Path to the source modlist JSON (the list being inspected)")
    parser.add_argument("target", help="Path to the target modlist JSON (your list)")
    parser.add_argument("-o", "--output", help="Output HTML file path (default: stdout)")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.80,
        help="Minimum confidence for fuzzy name matching (default: 0.80)",
    )
    args = parser.parse_args()

    source_data = load_modlist(args.source)
    target_data = load_modlist(args.target)

    rows_by_section = classify_source_mods(source_data, target_data, args.min_confidence)
    summary = compute_summary(rows_by_section)

    source_name = os.path.splitext(os.path.basename(args.source))[0]
    target_name = os.path.splitext(os.path.basename(args.target))[0]

    html_output = render_html(rows_by_section, summary, source_name, target_name)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html_output)
        print(f"Coverage view written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(html_output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python comparisons/test_generate_coverage.py -v`
Expected: PASS — all classification, summary, and render tests `OK`

- [ ] **Step 5: Commit**

```bash
git add comparisons/generate_coverage.py comparisons/test_generate_coverage.py
git commit -m "feat: add HTML rendering and CLI to generate_coverage"
```

---

### Task 4: Real-data verification run + documentation

**Goal:** Confirm the tool works end-to-end on real exports, save a sample output, and document the tool in CLAUDE.md.

**Files:**
- Modify: `CLAUDE.md` (add a "Coverage View Tool" subsection under the `comparisons/` documentation, after the Side-by-Side Diff Tool section)
- Create: `comparisons/ns3.0.1-vs-meteoric-0.0.3.coverage.html` (generated artifact)

**Acceptance Criteria:**
- [ ] Running the tool on `NORDIC SOULS v3.0.1.json` vs `Meteoric 0.0.3.json` produces an HTML file without errors
- [ ] The generated HTML opens in a browser and shows: a summary bar, collapsible sections, red missing rows with Nexus links, and at least the controls (Hide common / Expand all / Collapse all)
- [ ] CLAUDE.md documents the new script: purpose, CLI args, and how it differs from `generate_diff.py`

**Verify:**
```
python comparisons/generate_coverage.py "comparisons/modlist-json-exporter/lists/NORDIC SOULS v3.0.1.json" "comparisons/modlist-json-exporter/lists/Meteoric 0.0.3.json" -o comparisons/ns3.0.1-vs-meteoric-0.0.3.coverage.html
```
Expected: stderr prints `Coverage view written to comparisons/ns3.0.1-vs-meteoric-0.0.3.coverage.html`; the file exists and is non-empty.

**Steps:**

- [ ] **Step 1: Run the tool on real data**

Run:
```bash
python comparisons/generate_coverage.py "comparisons/modlist-json-exporter/lists/NORDIC SOULS v3.0.1.json" "comparisons/modlist-json-exporter/lists/Meteoric 0.0.3.json" -o comparisons/ns3.0.1-vs-meteoric-0.0.3.coverage.html
```
Expected: `Coverage view written to comparisons/ns3.0.1-vs-meteoric-0.0.3.coverage.html` on stderr, no traceback.

- [ ] **Step 2: Sanity-check the output**

Confirm the file is non-empty and contains expected markers:
```bash
python -c "t=open('comparisons/ns3.0.1-vs-meteoric-0.0.3.coverage.html',encoding='utf-8').read(); assert t.startswith('<!DOCTYPE html>'); assert 'Modlist Coverage' in t; assert 'class=\"section\"' in t or 'class=\"section collapsed\"' in t; print('OK', len(t), 'bytes')"
```
Expected: `OK <N> bytes`. Then open the file in a browser and visually confirm sections collapse/expand, the "Hide common mods" toggle works, and missing rows link to Nexus.

- [ ] **Step 3: Document in CLAUDE.md**

In `CLAUDE.md`, after the "### Side-by-Side Diff Tool" subsection (within the "## Cross-List Changelog Generation" area), add:

```markdown
### Coverage View Tool

`comparisons/generate_coverage.py` generates a self-contained HTML "coverage view" of a
single list. Where `generate_diff.py` compares two lists by load order side-by-side, the
coverage view renders **one source list's contents** (grouped by its own sections) and
highlights what the **target** list is missing or has at a different version. Load order is
not considered — it is about comparing modlist *contents* through the source list's structure.

```bash
python comparisons/generate_coverage.py \
  "comparisons/modlist-json-exporter/lists/NORDIC SOULS v3.0.1.json" \
  "comparisons/modlist-json-exporter/lists/Meteoric 0.0.3.json" \
  -o "comparisons/ns3.0.1-vs-meteoric-0.0.3.coverage.html"
```

**Arguments:**

- `source` (positional) — the list being inspected (its sections/mods drive the output)
- `target` (positional) — your list, compared against (never displayed directly)
- `-o/--output` — output HTML file path (default: stdout)
- `--min-confidence` — threshold for fuzzy name matching (default: 0.80)

**Mod states** (each source mod is classified into one):

- **Missing** (red) — not present in the target; the name links to its Nexus page
- **Newer** (orange, ↑) — source version is newer than target's
- **Older** (blue, ↓) — source version is older than target's
- **Differs** (amber, ≠) — versions differ but direction can't be determined
- **Common** (gray) — same version, or either version unknown

**Features:**

- Single column, grouped by source separator, in source order
- Collapsible section headers with count badges (e.g. `Combat — 3 missing · 1 newer`)
- Smart default collapse: all-common sections start collapsed; sections with gaps start expanded
- Summary bar with per-state counts
- "Hide common mods" toggle (default off), plus Expand all / Collapse all
- Uses the same pure-waterfall matching as the diff/changelog tools (no ignore/alias/compendium configs)
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md comparisons/ns3.0.1-vs-meteoric-0.0.3.coverage.html
git commit -m "docs: document generate_coverage tool and add sample output"
```

---

## Self-Review Notes

- **Spec coverage:** Task 1 → `compare_versions`; Task 2 → matching/classification/states/sections/summary; Task 3 → HTML structure, summary bar, controls, collapsible sections + smart collapse, mod rows with Nexus links and version info, CLI; Task 4 → verification + docs. Error handling (missing files, empty list, Unknown versions) is covered by reusing `load_modlist`/`get_version` and the both-known rule (Task 2 `test_unknown_version_is_common`).
- **Type consistency:** `CoverageState`, `CoverageRow(mod, state, source_version, target_version, nexus_id)`, `classify_source_mods`, `compute_summary` (returns `{"total", "counts"}`), `render_html(rows_by_section, summary, source_name, target_name)` are referenced identically across tasks and tests.
- **No placeholders:** every code step contains complete code.
