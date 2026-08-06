# Coverage "Ignore" Marks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user mark coverage-view mods as "ignored" so they render muted and drop out of the actionable counts, persisted to a per-target file via a live `--serve` server and honored by every static/regenerate run.

**Architecture:** A new `coverage_ignore.py` owns the per-target ignore file (load/save/add/remove, normalized-name matching). `generate_coverage.py` always reads it (greying ignored mods, recounting) and gains a `--serve` flag that hands off to a new `coverage_server.py` (stdlib HTTP server, click-to-ignore writing to the file). Marking is keyed by `normalize_name_strict(modName)` so it survives version bumps and applies across every source list compared against the target.

**Tech Stack:** Python 3 standard library only (`http.server`, `webbrowser`, `json`, `argparse`, `unittest`), inline HTML/CSS/JS — consistent with the rest of `tools/`.

**User decisions (already made):**
- Coverage view only (not diff/changelog).
- Persistence via local server: `generate_coverage.py --serve` writes the ignore file on click; static + `/regenerate` runs only read it.
- Scope is per target list (global across all source reports against that target).
- Identity is the normalized mod name (not Nexus id/fileid) so ignores survive version bumps.
- Visual treatment is color-only — no glyph/marker on ignored rows.
- Interaction is whole-row click (the mod-name link still navigates to Nexus).
- Code structure: `--serve` flag on `generate_coverage.py` plus helper modules `tools/coverage_ignore.py` and `tools/coverage_server.py`.

---

## File Structure

- **Create `tools/coverage_ignore.py`** — the ignore store: path resolution, load/save, add/remove, `IgnoreSet`, `is_ignored`. Pure file/data logic, no HTTP.
- **Create `tools/coverage_server.py`** — `--serve` HTTP server: `apply_ignore_change`, request handler, `serve()`. Imports render functions from `generate_coverage` and the store from `coverage_ignore`.
- **Modify `tools/generate_coverage.py`** — `CoverageRow.ignored`; ignore-aware classification and counting; muted rendering + serve-mode markup/JS; new CLI flags and serve dispatch.
- **Create `tools/test_coverage_ignore.py`** — unit tests for the store.
- **Create `tools/test_coverage_server.py`** — unit + light integration tests for the server.
- **Modify `tools/test_generate_coverage.py`** — extend with ignore classification/counting/rendering tests.
- **Modify `CLAUDE.md`** — document the flags, ignore file, and new test modules.

Run all tests from inside `tools/`: `cd tools && python -m unittest test_coverage_ignore test_generate_coverage test_coverage_server -v`

---

### Task 1: Ignore store — `coverage_ignore.py`

**Goal:** A standalone, fully tested module that reads/writes the per-target ignore file and matches mods by normalized name.

**Files:**
- Create: `tools/coverage_ignore.py`
- Test: `tools/test_coverage_ignore.py`

**Acceptance Criteria:**
- [ ] `resolve_ignore_path` returns `None` for stdout, `<dir>/<target>/.coverage-ignore.txt` for a directory, and `<dirname>/.coverage-ignore.txt` for an explicit file.
- [ ] `load_ignore` ignores `#` comments and blank lines, de-duplicates by normalized name, and returns an empty set for a missing/`None` path.
- [ ] `is_ignored` matches across case/suffix/punctuation differences via `normalize_name_strict`, and returns `False` when the set is `None`.
- [ ] `add`/`remove` are idempotent and round-trip; `save` writes the header and sorted, de-duplicated names.

**Verify:** `cd tools && python -m unittest test_coverage_ignore -v` → all tests pass (OK).

**Steps:**

- [ ] **Step 1: Write the failing tests** — `tools/test_coverage_ignore.py`

```python
"""Tests for the coverage ignore store."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coverage_ignore import (
    IgnoreSet,
    resolve_ignore_path,
    load_ignore,
    save,
    add,
    remove,
    is_ignored,
)


class ResolvePathTest(unittest.TestCase):
    def test_none_for_stdout(self):
        self.assertIsNone(resolve_ignore_path(None, "lists/Meteoric 0.0.5.json"))

    def test_directory(self):
        p = resolve_ignore_path("output/", "lists/Meteoric 0.0.5.json")
        self.assertEqual(
            os.path.normpath(p),
            os.path.normpath("output/Meteoric 0.0.5/.coverage-ignore.txt"),
        )

    def test_explicit_file(self):
        p = resolve_ignore_path("output/x.coverage.html", "lists/Meteoric.json")
        self.assertEqual(
            os.path.normpath(p), os.path.normpath("output/.coverage-ignore.txt")
        )


class LoadSaveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, ".coverage-ignore.txt")

    def test_missing_file_is_empty(self):
        self.assertEqual(len(load_ignore(self.path)), 0)
        self.assertEqual(len(load_ignore(None)), 0)

    def test_comments_blanks_dupes(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("# a comment\n\nMod One\nMod One\n  Mod Two  \n")
        ig = load_ignore(self.path)
        self.assertEqual(len(ig), 2)  # duplicate collapsed
        self.assertTrue(ig.contains_name("Mod One"))
        self.assertTrue(ig.contains_name("Mod Two"))

    def test_save_sorted_with_header(self):
        save(self.path, ["Zebra", "alpha", "Zebra"])
        with open(self.path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("#"))
        lines = [l for l in text.splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, ["alpha", "Zebra"])  # case-insensitive sort, deduped


class MatchTest(unittest.TestCase):
    def test_normalized_match(self):
        ig = IgnoreSet(["Phoenix - Compendium SSE"])
        self.assertTrue(is_ignored(ig, {"modName": "phoenix compendium"}))

    def test_is_ignored_none(self):
        self.assertFalse(is_ignored(None, {"modName": "Anything"}))


class AddRemoveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, ".coverage-ignore.txt")

    def test_add_remove_roundtrip(self):
        add(self.path, "Cool Mod")
        self.assertTrue(load_ignore(self.path).contains_name("Cool Mod"))
        add(self.path, "Cool Mod")  # idempotent
        self.assertEqual(len(load_ignore(self.path)), 1)
        remove(self.path, "Cool Mod")
        self.assertFalse(load_ignore(self.path).contains_name("Cool Mod"))
        remove(self.path, "Cool Mod")  # idempotent, no error


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m unittest test_coverage_ignore -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coverage_ignore'`.

- [ ] **Step 3: Write the module** — `tools/coverage_ignore.py`

```python
"""
Per-target ignore store for the coverage view.

A coverage report compares a SOURCE list against a TARGET list and surfaces the
source mods the target is missing or has at a different version. As the target
list matures, some surfaced mods are ones the user has decided NOT to pull in.
This module persists those decisions to a small text file, one per target list,
so every coverage run against that target greys them out.

The file lives next to the target's reports
(``output/<target>/.coverage-ignore.txt``), holds one raw modName per line
('#' comments and blank lines ignored), and is matched by ``normalize_name_strict``
so a decision survives version bumps and applies across every source list
compared against the target.
"""

import os

from modlist_utils import normalize_name_strict


IGNORE_FILENAME = ".coverage-ignore.txt"

_HEADER = (
    "# Coverage ignore list for this target modlist.\n"
    "# One mod name per line; these mods render muted (like 'common') in every\n"
    "# coverage report against this target and drop out of the actionable counts.\n"
    "# Lines starting with '#' and blank lines are ignored. Edit by hand or via\n"
    "# the coverage server (generate_coverage.py --serve).\n"
)


class IgnoreSet:
    """An immutable view of the ignore file: raw names plus a normalized lookup.

    Names are de-duplicated by their normalized key, keeping the first raw spelling
    for round-tripping back to the file.
    """

    def __init__(self, raw_names):
        self.raw = []
        self.norm = set()
        for name in raw_names:
            key = normalize_name_strict(name)
            if key and key not in self.norm:
                self.norm.add(key)
                self.raw.append(name)

    def contains_name(self, name):
        key = normalize_name_strict(name)
        return bool(key) and key in self.norm

    def __len__(self):
        return len(self.raw)


def is_ignored(ignore, mod):
    """True if a mod dict should be treated as ignored under this IgnoreSet.

    ``ignore`` may be None (no ignore file), in which case nothing is ignored.
    """
    if ignore is None:
        return False
    return ignore.contains_name(mod.get("modName", ""))


def resolve_ignore_path(output_arg, target_path):
    """Locate the per-target ignore file, or None when it can't be determined.

    Mirrors ``modlist_utils.resolve_output_path``'s directory detection:
      - output_arg falsy (stdout)      -> None
      - output_arg is a directory      -> <output_arg>/<target_basename>/.coverage-ignore.txt
      - output_arg is an explicit file -> <dirname(output_arg)>/.coverage-ignore.txt
    """
    if not output_arg:
        return None
    is_dir = output_arg.endswith(("/", "\\")) or os.path.isdir(output_arg)
    if is_dir:
        target_name = os.path.splitext(os.path.basename(target_path))[0]
        return os.path.join(output_arg, target_name, IGNORE_FILENAME)
    return os.path.join(os.path.dirname(output_arg) or ".", IGNORE_FILENAME)


def load_ignore(path):
    """Load an IgnoreSet from a file. Missing file or None path -> empty set."""
    if not path or not os.path.exists(path):
        return IgnoreSet([])
    names = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            names.append(line)
    return IgnoreSet(names)


def save(path, names):
    """Write the ignore file: header + sorted (case-insensitive), de-duplicated names."""
    ignore = IgnoreSet(names)
    ordered = sorted(ignore.raw, key=lambda n: n.lower())
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_HEADER)
        for name in ordered:
            f.write(name + "\n")


def add(path, name):
    """Add a name to the ignore file (idempotent). Returns the updated IgnoreSet."""
    ignore = load_ignore(path)
    if not ignore.contains_name(name):
        save(path, ignore.raw + [name])
        return load_ignore(path)
    return ignore


def remove(path, name):
    """Remove a name from the ignore file (idempotent). Returns the updated IgnoreSet."""
    ignore = load_ignore(path)
    if ignore.contains_name(name):
        key = normalize_name_strict(name)
        kept = [n for n in ignore.raw if normalize_name_strict(n) != key]
        save(path, kept)
        return load_ignore(path)
    return ignore
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools && python -m unittest test_coverage_ignore -v`
Expected: PASS (OK, all tests).

- [ ] **Step 5: Commit**

```bash
git add tools/coverage_ignore.py tools/test_coverage_ignore.py
git commit -m "Add coverage ignore store (per-target ignore file)"
```

---

### Task 2: Ignore-aware classification & counting in `generate_coverage.py`

**Goal:** Classification flags ignored rows and the summary counts them separately (excluded from add/newer/differs/common). No rendering change yet.

**Files:**
- Modify: `tools/generate_coverage.py` (imports; `CoverageRow`; `classify_source_mods`; `compute_summary`)
- Test: `tools/test_generate_coverage.py` (add an `IgnoreTest` class)

**Acceptance Criteria:**
- [ ] `CoverageRow` has an `ignored: bool = False` field.
- [ ] `classify_source_mods(..., ignore=None)` sets `row.ignored` from the supplied `IgnoreSet`.
- [ ] `compute_summary` returns an `"ignored"` count and excludes ignored rows from `"counts"` (an ignored Add counts as ignored, not add).
- [ ] All existing coverage tests still pass.

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → all tests pass (OK).

**Steps:**

- [ ] **Step 1: Write the failing tests** — append to `tools/test_generate_coverage.py` (before the `if __name__` block). The helpers `sep`/`mod` already exist at module top.

```python
class IgnoreTest(unittest.TestCase):
    def setUp(self):
        from coverage_ignore import IgnoreSet

        self.source = [
            sep("Combat", 0),
            mod("Valhalla Combat", 1, "Combat", version="1.5.0", nexus_id=64741),
            mod("MissingMod", 2, "Combat", version="2.0.0", nexus_id=99999),
        ]
        self.target = [
            sep("T", 0),
            mod("Valhalla Combat", 1, "T", version="1.5.0", nexus_id=64741),
        ]
        self.ignore = IgnoreSet(["MissingMod"])

    def _row(self, rows_by_section, name):
        for rows in rows_by_section.values():
            for row in rows:
                if row.mod.get("modName") == name:
                    return row
        raise AssertionError(f"{name} not found")

    def test_classify_sets_ignored(self):
        rows = classify_source_mods(self.source, self.target, ignore=self.ignore)
        self.assertTrue(self._row(rows, "MissingMod").ignored)
        self.assertFalse(self._row(rows, "Valhalla Combat").ignored)

    def test_default_no_ignore(self):
        rows = classify_source_mods(self.source, self.target)
        self.assertFalse(self._row(rows, "MissingMod").ignored)

    def test_summary_counts_ignored_separately(self):
        rows = classify_source_mods(self.source, self.target, ignore=self.ignore)
        summary = compute_summary(rows)
        self.assertEqual(summary["ignored"], 1)
        # MissingMod would be ADD, but ignored -> excluded from the add count.
        self.assertEqual(summary["counts"][CoverageState.ADD], 0)
        self.assertEqual(summary["total"], 2)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd tools && python -m unittest test_generate_coverage.IgnoreTest -v`
Expected: FAIL — `classify_source_mods()` has no `ignore` kwarg / `summary` has no `"ignored"` key.

- [ ] **Step 3: Add the import** in `tools/generate_coverage.py`, after the existing `from modlist_utils import (...)` block:

```python
from coverage_ignore import is_ignored
```

- [ ] **Step 4: Add the `ignored` field** to the `CoverageRow` dataclass:

```python
@dataclass
class CoverageRow:
    mod: dict
    state: CoverageState
    source_version: str
    target_version: str          # "" when the mod is missing
    nexus_id: Optional[int]      # numeric Nexus id, or None
    ignored: bool = False
```

- [ ] **Step 5: Thread `ignore` through `classify_source_mods`.** Change the signature and the row construction. New signature line:

```python
def classify_source_mods(source_data, target_data, min_confidence=0.80, ignore=None):
```

Replace the row-append block at the end of the loop:

```python
        raw_id = mod.get("id")
        nexus_id = raw_id if isinstance(raw_id, int) else None

        row = CoverageRow(mod, state, source_version, target_version, nexus_id)
        row.ignored = is_ignored(ignore, mod)
        rows_by_section[section].append(row)
```

- [ ] **Step 6: Update `compute_summary`** to count ignored separately:

```python
def compute_summary(rows_by_section):
    """Compute total, per-state, and ignored counts across all sections.

    Ignored rows are counted under "ignored" only — never under their underlying
    state — so the actionable stats reflect what still needs attention.
    """
    counts = {state: 0 for state in CoverageState}
    ignored = 0
    total = 0
    for rows in rows_by_section.values():
        for row in rows:
            total += 1
            if row.ignored:
                ignored += 1
            else:
                counts[row.state] += 1
    return {"total": total, "counts": counts, "ignored": ignored}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: PASS (OK) — new `IgnoreTest` and all existing tests.

- [ ] **Step 8: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "Coverage: ignore-aware classification and summary counts"
```

---

### Task 3: Muted rendering, serve-mode markup & client JS in `generate_coverage.py`

**Goal:** Ignored rows render with the muted `mod-ignored` color (no glyph), are excluded from section badges/collapse, hidden by "Hide common", and counted in a new "ignored" summary stat; in serve mode every row is a click target wired to `/api/ignore`.

**Files:**
- Modify: `tools/generate_coverage.py` (`CSS`; `_section_state_counts`; `_render_mod_row`; `_render_bandless_rows`; `_render_section`; `render_html`)
- Test: `tools/test_generate_coverage.py` (add a `RenderIgnoreTest` class)

**Acceptance Criteria:**
- [ ] Ignored rows render with class `mod-ignored` and no `mod-add`/`mod-newer`/etc. class.
- [ ] An ignored row is excluded from its section's badge count and collapse decision.
- [ ] `body.hide-common` hides `.mod-ignored` as well as `.mod-common`.
- [ ] The summary bar includes an "N ignored" stat with `id="stat-ignored"`.
- [ ] `render_html(..., serve=True)` adds `class="serve"` to `<body>`, `data-mod`/`data-state`/`data-ignored` attributes on mod rows, and the `/api/ignore` client script; `serve=False` includes none of these.

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → all tests pass (OK).

**Steps:**

- [ ] **Step 1: Write the failing tests** — append to `tools/test_generate_coverage.py`:

```python
class RenderIgnoreTest(unittest.TestCase):
    def setUp(self):
        from coverage_ignore import IgnoreSet

        self.source = [
            sep("Combat", 0),
            mod("KeepMod", 1, "Combat", version="2.0", nexus_id=111),    # ADD
            mod("DropMod", 2, "Combat", version="2.0", nexus_id=222),    # ADD -> ignored
        ]
        self.target = [sep("T", 0)]
        self.ignore = IgnoreSet(["DropMod"])
        self.rows = classify_source_mods(self.source, self.target, ignore=self.ignore)
        self.summary = compute_summary(self.rows)

    def test_ignored_row_uses_muted_class(self):
        html = render_html(self.rows, self.summary, "S", "T")
        # The ignored row carries mod-ignored and not its underlying state class.
        self.assertIn("mod-ignored", html)
        # CSS rule for the muted color exists.
        self.assertIn(".mod-ignored", html)

    def test_hide_common_covers_ignored(self):
        html = render_html(self.rows, self.summary, "S", "T")
        self.assertIn("body.hide-common .mod-ignored", html)

    def test_ignored_summary_stat(self):
        html = render_html(self.rows, self.summary, "S", "T")
        self.assertIn('id="stat-ignored"', html)
        self.assertIn("1 ignored", html)

    def test_ignored_excluded_from_section_badge(self):
        # Section badge counts only the un-ignored ADD (KeepMod) -> "1 add".
        html = render_html(self.rows, self.summary, "S", "T")
        self.assertIn("1 add", html)
        self.assertNotIn("2 add", html)

    def test_serve_markup_only_when_serving(self):
        static = render_html(self.rows, self.summary, "S", "T")
        served = render_html(self.rows, self.summary, "S", "T", serve=True)
        self.assertNotIn("/api/ignore", static)
        self.assertNotIn("data-mod=", static)
        self.assertIn("/api/ignore", served)
        self.assertIn("data-mod=", served)
        self.assertIn('<body class="serve">', served)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m unittest test_generate_coverage.RenderIgnoreTest -v`
Expected: FAIL — `mod-ignored` / `stat-ignored` / serve markup absent.

- [ ] **Step 3: Extend the `CSS` string.** Add the `stat-ignored` rule right after the `.stat-common` line:

```python
.stat-common { background: #232333; color: #9ca3af; }
.stat-ignored { background: #232333; color: #6b7280; }
```

Add the muted row rules right after the `.mod-common .ver` line:

```python
.mod-common { color: #9ca3af; }
.mod-common .ver { color: #6b7280; }
.mod-ignored { color: #6b7280; }
.mod-ignored .ver { color: #5b6270; }
```

Replace the existing hide-common line so it also hides ignored rows, and add serve-mode interactivity rules:

```python
body.hide-common .mod-common,
body.hide-common .mod-ignored { display: none; }

body.serve .mod-row { cursor: pointer; }
body.serve .mod-row:hover { background: #20203a; }
```

- [ ] **Step 4: Update `_section_state_counts`** to exclude ignored rows and also report the ignored count (its only caller is `_render_section`, updated in Step 6):

```python
def _section_state_counts(rows):
    counts = {state: 0 for state in CoverageState}
    ignored = 0
    for row in rows:
        if row.ignored:
            ignored += 1
        else:
            counts[row.state] += 1
    return counts, ignored
```

- [ ] **Step 5: Update `_render_mod_row`, `_render_bandless_rows`** to accept and emit serve markup:

```python
def _render_mod_row(parts, row, serve=False):
    cls = "mod-ignored" if row.ignored else _STATE_CSS[row.state]
    ver = _version_html(row)
    ver_html = f'<span class="ver">{ver}</span>' if ver else ""
    attrs = ""
    if serve:
        name = _esc(row.mod.get("modName", ""))
        state_cls = _STATE_CSS[row.state]
        flag = "1" if row.ignored else "0"
        action = "un-ignore" if row.ignored else "ignore"
        attrs = (
            f' data-mod="{name}" data-state="{state_cls}" data-ignored="{flag}"'
            f' title="Click to {action}"'
        )
    parts.append(f'<div class="mod-row {cls}"{attrs}>')
    parts.append(f'<span class="mod-name">{_name_html(row)}</span>')
    parts.append(ver_html)
    parts.append("</div>")


def _render_bandless_rows(parts, rows, serve=False):
    # Mods sitting directly under a major separator: rows render beneath the band
    # with no sub-header (the band is their header).
    parts.append('<div class="section-body">')
    for row in rows:
        _render_mod_row(parts, row, serve)
    parts.append("</div>")
```

- [ ] **Step 6: Update `_render_section`** to unpack the new counts tuple and thread `serve`:

```python
def _render_section(parts, section_name, rows, serve=False):
    state_counts, _ignored = _section_state_counts(rows)
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
        _render_mod_row(parts, row, serve)
    parts.append("</div>")
    parts.append("</div>")
```

- [ ] **Step 7: Update `render_html`** — new `serve` param, body class, ignored stat with ids, thread `serve` into section rendering, and append the serve-mode client script. Change the signature:

```python
def render_html(rows_by_section, summary, source_name, target_name, section_majors=None, serve=False):
```

Replace the `<body>` open line:

```python
    parts.append('<body class="serve">' if serve else "<body>")
```

Replace the summary block (add ids + the ignored stat). The new block:

```python
    parts.append('<div class="summary">')
    parts.append(f'<span class="stat stat-total">{summary["total"]} mods</span>')
    parts.append(f'<span id="stat-add" class="stat stat-add">{counts[CoverageState.ADD]} to add</span>')
    parts.append(f'<span id="stat-newer" class="stat stat-newer">{counts[CoverageState.NEWER]} newer</span>')
    parts.append(f'<span id="stat-differs" class="stat stat-differs">{counts[CoverageState.DIFFERS]} differs</span>')
    parts.append(f'<span id="stat-ignored" class="stat stat-ignored">{summary.get("ignored", 0)} ignored</span>')
    parts.append(f'<span id="stat-common" class="stat stat-common">{counts[CoverageState.COMMON]} common</span>')
    parts.append("</div>")
```

Replace the section-rendering loop body to pass `serve`:

```python
        if is_major_separator(section_name):
            _render_bandless_rows(parts, rows, serve)
        else:
            _render_section(parts, section_name, rows, serve)
```

Add the serve-mode client script immediately before the final `parts.append("</body></html>")` line:

```python
    if serve:
        parts.append("<script>")
        parts.append(
            "(function(){"
            "function setStat(id,t){var e=document.getElementById(id);if(e)e.textContent=t;}"
            "function recount(){"
            "var c={add:0,newer:0,differs:0,common:0,ignored:0};"
            "document.querySelectorAll('.mod-row').forEach(function(r){"
            "if(r.classList.contains('mod-ignored'))c.ignored++;"
            "else if(r.classList.contains('mod-add'))c.add++;"
            "else if(r.classList.contains('mod-newer'))c.newer++;"
            "else if(r.classList.contains('mod-differs'))c.differs++;"
            "else if(r.classList.contains('mod-common'))c.common++;});"
            "setStat('stat-add',c.add+' to add');setStat('stat-newer',c.newer+' newer');"
            "setStat('stat-differs',c.differs+' differs');"
            "setStat('stat-ignored',c.ignored+' ignored');"
            "setStat('stat-common',c.common+' common');"
            "document.querySelectorAll('.section').forEach(function(s){"
            "var a=0,n=0,d=0;"
            "s.querySelectorAll('.mod-row').forEach(function(r){"
            "if(r.classList.contains('mod-add'))a++;"
            "else if(r.classList.contains('mod-newer'))n++;"
            "else if(r.classList.contains('mod-differs'))d++;});"
            "var b=s.querySelector('.badge');if(!b)return;"
            "var p=[];if(a)p.push(a+' add');if(n)p.push(n+' newer');if(d)p.push(d+' differs');"
            "b.textContent=p.length?p.join(' \\u00b7 '):'all present';});}"
            "function setIgnored(row,on){var sc=row.getAttribute('data-state');"
            "row.classList.remove('mod-add','mod-newer','mod-differs','mod-common','mod-ignored');"
            "row.classList.add(on?'mod-ignored':sc);"
            "row.setAttribute('data-ignored',on?'1':'0');"
            "row.setAttribute('title','Click to '+(on?'un-ignore':'ignore'));}"
            "document.body.addEventListener('click',function(e){"
            "if(e.target.closest('a'))return;"
            "var row=e.target.closest('.mod-row');if(!row)return;"
            "var name=row.getAttribute('data-mod');if(name===null)return;"
            "var on=row.getAttribute('data-ignored')==='1';"
            "fetch('/api/ignore',{method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({name:name,ignored:!on})})"
            ".then(function(r){return r.json();}).then(function(d){"
            "if(!d.ok)return;setIgnored(row,!on);recount();}).catch(function(){});});"
            "})();"
        )
        parts.append("</script>")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: PASS (OK) — `RenderIgnoreTest` plus all existing render tests.

- [ ] **Step 9: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "Coverage: muted ignored rendering + serve-mode click markup"
```

---

### Task 4: Live server — `coverage_server.py`

**Goal:** A stdlib HTTP server that serves the serve-mode report and persists clicks to the ignore file, bound to localhost only.

**Files:**
- Create: `tools/coverage_server.py`
- Test: `tools/test_coverage_server.py`

**Acceptance Criteria:**
- [ ] `apply_ignore_change(path, name, ignored)` adds/removes via the store and is idempotent.
- [ ] `GET /` returns 200 HTML containing the rendered report and the serve-mode `/api/ignore` script; unknown GET paths return 404.
- [ ] `POST /api/ignore` with a valid body mutates the ignore file and returns `{"ok": true}`; a malformed body returns 400.
- [ ] The server binds to `127.0.0.1` and re-reads source/target/ignore on each `GET /`.

**Verify:** `cd tools && python -m unittest test_coverage_server -v` → all tests pass (OK).

**Steps:**

- [ ] **Step 1: Write the failing tests** — `tools/test_coverage_server.py`

```python
"""Tests for the coverage server: ignore mutation and HTTP handling."""

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import coverage_ignore
import coverage_server


class ApplyChangeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, ".coverage-ignore.txt")

    def test_add_then_remove(self):
        coverage_server.apply_ignore_change(self.path, "Some Mod", True)
        self.assertTrue(coverage_ignore.load_ignore(self.path).contains_name("Some Mod"))
        coverage_server.apply_ignore_change(self.path, "Some Mod", False)
        self.assertFalse(coverage_ignore.load_ignore(self.path).contains_name("Some Mod"))

    def test_add_idempotent(self):
        coverage_server.apply_ignore_change(self.path, "Dup", True)
        coverage_server.apply_ignore_change(self.path, "Dup", True)
        self.assertEqual(len(coverage_ignore.load_ignore(self.path)), 1)


class ServerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ignore_path = os.path.join(self.dir, ".coverage-ignore.txt")
        self.source = os.path.join(self.dir, "Source.json")
        self.target = os.path.join(self.dir, "Target.json")
        with open(self.source, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {"type": "separator", "separatorName": "S", "order": 0},
                    {"type": "mod", "modName": "ClickMe", "separatorName": "S",
                     "order": 1, "id": 42, "general": {"version": "1.0"}},
                ],
                f,
            )
        with open(self.target, "w", encoding="utf-8") as f:
            json.dump([], f)
        handler = coverage_server.make_handler(self.source, self.target, 0.80, self.ignore_path)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _conn(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def test_get_root_returns_html(self):
        c = self._conn()
        c.request("GET", "/")
        resp = c.getresponse()
        body = resp.read().decode("utf-8")
        self.assertEqual(resp.status, 200)
        self.assertTrue(body.startswith("<!DOCTYPE html>"))
        self.assertIn("ClickMe", body)
        self.assertIn("/api/ignore", body)  # serve-mode JS present

    def test_unknown_get_404(self):
        c = self._conn()
        c.request("GET", "/nope")
        self.assertEqual(c.getresponse().status, 404)

    def test_post_ignore_mutates_file(self):
        c = self._conn()
        payload = json.dumps({"name": "ClickMe", "ignored": True})
        c.request("POST", "/api/ignore", payload, {"Content-Type": "application/json"})
        resp = c.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertTrue(json.loads(resp.read())["ok"])
        self.assertTrue(coverage_ignore.load_ignore(self.ignore_path).contains_name("ClickMe"))

    def test_post_bad_body_400(self):
        c = self._conn()
        c.request("POST", "/api/ignore", "{not json", {"Content-Type": "application/json"})
        self.assertEqual(c.getresponse().status, 400)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m unittest test_coverage_server -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coverage_server'`.

- [ ] **Step 3: Write the module** — `tools/coverage_server.py`

```python
"""
Local server for the coverage view's click-to-ignore feature.

``generate_coverage.py --serve`` starts this server instead of writing a static
HTML file. It serves the coverage report at http://127.0.0.1:<port>/ with
interactive rows; clicking a mod row POSTs to /api/ignore, which updates the
per-target ignore file immediately. The report is re-rendered from the current
source/target JSON and ignore file on every GET, so a mid-session re-export is
reflected on refresh.

Bound to 127.0.0.1 only — it writes files and must not be exposed.
"""

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import coverage_ignore
from modlist_utils import load_modlist
from generate_coverage import (
    classify_source_mods,
    compute_summary,
    map_sections_to_majors,
    render_html,
)


def apply_ignore_change(ignore_path, name, ignored):
    """Add or remove a name in the ignore file. Pure dispatch over the store."""
    if ignored:
        coverage_ignore.add(ignore_path, name)
    else:
        coverage_ignore.remove(ignore_path, name)


def _render_current(source_path, target_path, min_confidence, ignore_path):
    """Render the coverage HTML from the current files, in serve mode."""
    source_data = load_modlist(source_path)
    target_data = load_modlist(target_path)
    ignore = coverage_ignore.load_ignore(ignore_path)
    rows_by_section = classify_source_mods(source_data, target_data, min_confidence, ignore)
    summary = compute_summary(rows_by_section)
    section_majors = map_sections_to_majors(source_data)
    source_name = os.path.splitext(os.path.basename(source_path))[0]
    target_name = os.path.splitext(os.path.basename(target_path))[0]
    return render_html(
        rows_by_section, summary, source_name, target_name, section_majors, serve=True
    )


def make_handler(source_path, target_path, min_confidence, ignore_path):
    """Build a request handler class bound to these report parameters."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def do_GET(self):
            if self.path not in ("/", ""):
                self.send_error(404)
                return
            body = _render_current(
                source_path, target_path, min_confidence, ignore_path
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/api/ignore":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                name = payload["name"]
                ignored = bool(payload["ignored"])
            except (ValueError, KeyError, TypeError):
                self._json(400, {"ok": False, "error": "bad request"})
                return
            apply_ignore_change(ignore_path, name, ignored)
            self._json(200, {"ok": True})

        def _json(self, status, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _bind(port, handler, max_tries=20):
    """Bind to 127.0.0.1:port, incrementing on OSError up to max_tries."""
    last_err = None
    for p in range(port, port + max_tries):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), handler), p
        except OSError as e:
            last_err = e
    raise last_err


def serve(source_path, target_path, min_confidence, ignore_path, port=8000, open_browser=True):
    """Serve the coverage report with click-to-ignore until interrupted."""
    if not ignore_path:
        print(
            "Serve mode needs an ignore file location: pass -o <dir> or --ignore-file.",
            file=sys.stderr,
        )
        sys.exit(2)
    handler = make_handler(source_path, target_path, min_confidence, ignore_path)
    httpd, bound_port = _bind(port, handler)
    url = f"http://127.0.0.1:{bound_port}/"
    print(f"Coverage server running at {url}", file=sys.stderr)
    print(f"Ignore file: {ignore_path}", file=sys.stderr)
    print("Press Ctrl-C to stop.", file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.", file=sys.stderr)
    finally:
        httpd.server_close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools && python -m unittest test_coverage_server -v`
Expected: PASS (OK, all tests).

- [ ] **Step 5: Commit**

```bash
git add tools/coverage_server.py tools/test_coverage_server.py
git commit -m "Add coverage --serve HTTP server (click-to-ignore)"
```

---

### Task 5: CLI wiring in `generate_coverage.py` `main()`

**Goal:** New flags (`--serve`, `--port`, `--no-browser`, `--ignore-file`), static runs read the ignore file, and `--serve` hands off to the server.

**Files:**
- Modify: `tools/generate_coverage.py` (imports; `main()`)

**Acceptance Criteria:**
- [ ] A normal run reads the resolved ignore file and greys ignored mods (verified end-to-end with a temp ignore file).
- [ ] `--serve` starts the server (manual smoke check) and respects `--ignore-file`.
- [ ] Existing CLI behavior (stdout, `-o` file, `-o` directory) is unchanged.

**Verify (automated end-to-end):**
```bash
cd tools && python - <<'PY'
import json, os, tempfile, subprocess, sys
d = tempfile.mkdtemp()
src = os.path.join(d, "Src.json"); tgt = os.path.join(d, "Tgt.json")
out = os.path.join(d, "rep.html"); ign = os.path.join(d, "ig.txt")
json.dump([{"type":"separator","separatorName":"S","order":0},
           {"type":"mod","modName":"DropMod","separatorName":"S","order":1,
            "id":1,"general":{"version":"1.0"}}], open(src,"w"))
json.dump([], open(tgt,"w"))
open(ign,"w").write("DropMod\n")
subprocess.run([sys.executable,"generate_coverage.py",src,tgt,"-o",out,"--ignore-file",ign],check=True)
html = open(out,encoding="utf-8").read()
assert "mod-ignored" in html, "ignored row not muted"
assert "1 ignored" in html, "ignored stat missing"
print("OK: static run honored the ignore file")
PY
```
Expected: prints `OK: static run honored the ignore file`.

**Steps:**

- [ ] **Step 1: Extend the import** in `tools/generate_coverage.py`. Replace the line added in Task 2 (`from coverage_ignore import is_ignored`) with:

```python
from coverage_ignore import is_ignored, resolve_ignore_path, load_ignore
```

- [ ] **Step 2: Add the CLI flags** in `main()`, after the existing `--min-confidence` argument:

```python
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start a local click-to-ignore server instead of writing a static report.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for --serve (default: 8000; auto-increments if busy).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the browser in --serve mode.",
    )
    parser.add_argument(
        "--ignore-file",
        help="Override the per-target ignore file path (default: derived from -o).",
    )
```

- [ ] **Step 3: Rewrite the body of `main()`** after `args = parser.parse_args()` to resolve the ignore path, branch on `--serve`, and read the ignore file in the static path:

```python
    args = parser.parse_args()

    ignore_path = args.ignore_file or resolve_ignore_path(args.output, args.target)

    if args.serve:
        from coverage_server import serve

        serve(
            source_path=args.source,
            target_path=args.target,
            min_confidence=args.min_confidence,
            ignore_path=ignore_path,
            port=args.port,
            open_browser=not args.no_browser,
        )
        return

    source_data = load_modlist(args.source)
    target_data = load_modlist(args.target)
    ignore = load_ignore(ignore_path)

    rows_by_section = classify_source_mods(
        source_data, target_data, args.min_confidence, ignore
    )
    summary = compute_summary(rows_by_section)
    section_majors = map_sections_to_majors(source_data)

    source_name = os.path.splitext(os.path.basename(args.source))[0]
    target_name = os.path.splitext(os.path.basename(args.target))[0]

    html_output = render_html(
        rows_by_section, summary, source_name, target_name, section_majors
    )

    out_path = resolve_output_path(args.output, args.source, args.target, "coverage", "html")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_output)
        print(f"Coverage view written to {out_path}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(html_output)
```

- [ ] **Step 4: Run the end-to-end verify above**, then the full coverage suite:

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: PASS (OK).

- [ ] **Step 5: Manual smoke check (serve mode).** Pick any two real lists and confirm the server boots and a click greys a row + writes the file:

```bash
cd tools && python generate_coverage.py "../lists/BottleRim 2.1.1.json" "../lists/Meteoric 0.0.5.json" -o ../output/ --no-browser
```
(Then with `--serve` instead of `-o`-only, open the printed URL, click a green "Add" row, confirm it greys and that `output/Meteoric 0.0.5/.coverage-ignore.txt` gains the name. Ctrl-C to stop.) Expected: row greys, count updates, file written.

- [ ] **Step 6: Commit**

```bash
git add tools/generate_coverage.py
git commit -m "Coverage: --serve/--port/--no-browser/--ignore-file CLI wiring"
```

---

### Task 6: Documentation & full suite

**Goal:** `CLAUDE.md` documents the feature; the whole test suite is green.

**Files:**
- Modify: `CLAUDE.md` (tools tree diagram; Coverage subsection; Testing command list)

**Acceptance Criteria:**
- [ ] The Coverage subsection documents `--serve`, `--port`, `--no-browser`, `--ignore-file`, the ignore file location/format, that static and `/regenerate` runs honor it, and the muted "ignored" state.
- [ ] `coverage_ignore.py`, `coverage_server.py`, `test_coverage_ignore.py`, `test_coverage_server.py` appear in the `tools/` tree diagram.
- [ ] The Testing section's command list includes the two new test modules.
- [ ] The entire test suite passes.

**Verify:** `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_coverage_ignore test_coverage_server test_regenerate -v` → all pass (OK).

**Steps:**

- [ ] **Step 1: Update the `tools/` tree diagram** in `CLAUDE.md` — add the four files under the existing `tools/` entries:

```text
│   ├── coverage_ignore.py            # Shared: per-target coverage ignore file store
│   ├── coverage_server.py            # generate_coverage --serve HTTP server
│   ├── test_coverage_ignore.py       # Unit tests
│   ├── test_coverage_server.py       # Unit tests
```

- [ ] **Step 2: Extend the Coverage subsection** in `CLAUDE.md`. After the existing **Arguments** line for coverage, add:

```markdown
**Serve mode (`--serve`):** `python tools/generate_coverage.py SOURCE TARGET -o output/ --serve`
runs a localhost server (default port 8000, `--port` to change, `--no-browser` to suppress
auto-open) where **clicking any mod row** toggles it as *ignored* and writes the change
immediately. Ignored mods render muted (like Common), drop out of the actionable counts, and are
hidden by "Hide common".

**Ignore file:** ignores are stored per **target** list in
`output/<target>/.coverage-ignore.txt` (one raw mod name per line; `#` comments and blanks
ignored; hand-editable). Matching is by normalized name, so an ignore survives version bumps and
applies to **every** coverage report against that target. Static runs and `/regenerate` always
**read** this file (greying ignored mods); only `--serve` **writes** it. Override the path with
`--ignore-file`.
```

- [ ] **Step 3: Update the Testing section** command list in `CLAUDE.md`:

```bash
cd tools
python -m unittest test_modlist_utils test_generate_coverage test_coverage_ignore test_coverage_server test_regenerate -v
```

- [ ] **Step 4: Run the full suite to verify**

Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_coverage_ignore test_coverage_server test_regenerate -v`
Expected: PASS (OK) across all modules.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "Document coverage ignore marks (--serve, ignore file)"
```

---

## Self-Review

**Spec coverage:**
- Ignore file (location/format/matching) → Task 1. ✓
- `coverage_ignore.py` API → Task 1. ✓
- `CoverageRow.ignored` + always-on read → Tasks 2 & 5. ✓
- Counts (ignored excluded from actionable; "N ignored" stat; badge/collapse) → Tasks 2 & 3. ✓
- Rendering (muted color, no glyph; hide-common; static vs serve markup; whole-row click) → Task 3. ✓
- `coverage_server.py` (localhost, GET re-render, POST mutate, apply_ignore_change, port handling) → Task 4. ✓
- CLI flags + serve dispatch + static read → Task 5. ✓
- Tests for all three modules → Tasks 1, 3, 4 (+2). ✓
- CLAUDE.md docs → Task 6. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows complete code; every verify has an exact command and expected output.

**Type consistency:** `IgnoreSet`/`is_ignored`/`resolve_ignore_path`/`load_ignore`/`add`/`remove`/`save` names match across Tasks 1, 2, 4, 5. `classify_source_mods(..., ignore=None)`, `render_html(..., serve=False)`, and `compute_summary` returning `{"total","counts","ignored"}` are consistent across tasks. `_section_state_counts` returns a `(counts, ignored)` tuple in Task 3 and its only caller `_render_section` is updated in the same task. `apply_ignore_change(path, name, ignored)` and `make_handler(source, target, min_confidence, ignore_path)` signatures match between Task 4's module and tests.
