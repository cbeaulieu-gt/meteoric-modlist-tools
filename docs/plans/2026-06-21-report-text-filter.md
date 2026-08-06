# Report Text Filter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live, case-insensitive, multi-term-AND text filter to the header of the coverage and diff HTML reports that hides mod rows whose name doesn't match.

**Architecture:** Pure client-side. Each mod row gets a pre-lowercased `data-names` attribute (1 name for coverage, 1–2 for diff). A small inlined `filterMods()` JS splits the query on whitespace and toggles a `filter-hidden` class (`display:none`) on rows whose names don't contain every term. CSS composes with the existing hide-common / hide-unchanged toggles. The diff header gains `position: sticky` so the box stays pinned. No Python matching-logic changes.

**Tech Stack:** Python 3 stdlib only (no third-party deps, no node); vanilla inline JS/CSS in the generated self-contained HTML; `unittest`.

**User decisions (already made):**
- Filter behavior: case-insensitive, multi-term **AND** by **mod name** (e.g. `3d thing` → name contains `3d` AND `thing`); sections always visible (only mod rows hidden).
- "keep it inlined" — filter JS stays inline in both generators; asset/template extraction deferred (separate note).
- Coverage: collapsed sections stay collapsed while filtering ("Leave collapsed").
- Diff: a row matches if **either** the old or the new name matches ("Either name matches").
- Diff header made sticky (it currently isn't).
- Input uses `type="search"` (native clear ×) + Esc-to-clear; no live match count (YAGNI).
- Work on branch `feature/report-text-filter`; merge to `main` locally when done.

**Spec:** [docs/design/2026-06-21-report-text-filter-design.md](../design/2026-06-21-report-text-filter-design.md)

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `tools/generate_coverage.py` | Coverage report HTML | Modify: CSS (filter-input, filter-hidden), header input, `data-names` on rows, filter JS |
| `tools/generate_diff.py` | Diff report HTML | Modify: sticky `.header`, CSS (filter-input, filter-hidden), header input, `data-names` on rows, filter JS |
| `tools/test_generate_coverage.py` | Coverage tests | Modify: add filter/`data-names` tests to `RenderTest` |
| `tools/test_generate_diff.py` | Diff tests | **Create**: render tests for sticky header, filter, `data-names` |

Tasks 1 and 2 are independent (different files) and may be done in either order.

### Shared inline JS (identical in both generators)

Both generators inline this exact `filterMods` block (duplicated by the "keep it inlined"
decision). Note the **double backslashes** in the Python source: `"\\s"` emits JS `\s` (regex
whitespace) and `"\\n"` emits JS `\n` (a newline, matching the real newline used to join
`data-names`). Do **not** "simplify" them to single backslashes.

```python
        "function filterMods(q){"
        "var terms=(q||'').trim().toLowerCase().split(/\\s+/).filter(Boolean);"
        "document.querySelectorAll('[data-names]').forEach(function(row){"
        "var hide=false;"
        "if(terms.length){var names=row.getAttribute('data-names').split('\\n');"
        "hide=!names.some(function(n){return terms.every(function(t){return n.indexOf(t)!==-1;});});}"
        "row.classList.toggle('filter-hidden',hide);});}"
        "(function(){var i=document.getElementById('filter-input');if(!i)return;"
        "i.addEventListener('input',function(){filterMods(this.value);});"
        "i.addEventListener('keydown',function(e){if(e.key==='Escape'){this.value='';filterMods('');}});})();"
```

---

## Task 1: Coverage report filter

**Goal:** Add the header filter input, per-row `data-names`, filter CSS, and filter JS to `generate_coverage.py`, with tests.

**Files:**
- Modify: `tools/generate_coverage.py` (CSS ~196 & ~230; row render ~322–339; header HTML ~407; JS ~424–435)
- Test: `tools/test_generate_coverage.py` (`RenderTest` class)

**Acceptance Criteria:**
- [ ] Generated HTML contains `<input type="search" id="filter-input" class="filter-input" ...>` inside `.header`.
- [ ] Every mod row carries a lowercased `data-names` attribute (e.g. `data-names="valhalla combat"`), in both static and serve modes.
- [ ] CSS contains `.filter-input` style and `.mod-row.filter-hidden { display: none; }`.
- [ ] JS contains `function filterMods`, wires the input's `input` event, and clears on `Escape`.
- [ ] Existing coverage tests still pass (serve-mode `data-mod`/`data-state` attrs unchanged).

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → OK (all pass)

**Steps:**

- [ ] **Step 1: Write failing tests** — add to the `RenderTest` class in `tools/test_generate_coverage.py` (after `test_section_headers_sticky`):

```python
    def test_filter_input_present(self):
        self.assertIn('id="filter-input"', self.html)
        self.assertIn('class="filter-input"', self.html)
        self.assertIn('type="search"', self.html)

    def test_filter_css_and_js(self):
        self.assertIn(".mod-row.filter-hidden", self.html)
        self.assertIn("function filterMods", self.html)
        self.assertIn("'Escape'", self.html)  # Esc clears the box

    def test_mod_rows_carry_data_names(self):
        # Every mod row exposes a lowercased name for the client filter.
        self.assertIn('data-names="valhalla combat"', self.html)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m unittest test_generate_coverage.RenderTest -v`
Expected: FAIL — `test_filter_input_present`, `test_filter_css_and_js`, `test_mod_rows_carry_data_names` (feature absent).

- [ ] **Step 3: Add filter CSS.** In `tools/generate_coverage.py`, find:

```python
.header .lists span { color: #e0e0e0; font-weight: 600; }
```

Insert immediately after it:

```python
.filter-input {
    width: 100%; margin-top: 10px; padding: 6px 10px;
    background: #0f1830; color: #e0e0e0;
    border: 1px solid #1a4a7a; border-radius: 4px;
    font-family: inherit; font-size: 13px;
}
.filter-input::placeholder { color: #6b7a90; }
.mod-row.filter-hidden { display: none; }
```

- [ ] **Step 4: Add the input to the header.** Find (the close of `.summary` then `.header`):

```python
    parts.append(f'<span id="stat-common" class="stat stat-common">{counts[CoverageState.COMMON]} common</span>')
    parts.append("</div>")
    parts.append("</div>")
```

Replace with:

```python
    parts.append(f'<span id="stat-common" class="stat stat-common">{counts[CoverageState.COMMON]} common</span>')
    parts.append("</div>")
    parts.append(
        '<input type="search" id="filter-input" class="filter-input" '
        'placeholder="Filter mods… (space = AND)" autocomplete="off">'
    )
    parts.append("</div>")
```

- [ ] **Step 5: Add `data-names` to every mod row.** In `_render_mod_row`, find:

```python
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
```

Replace with:

```python
    data_names = _esc((row.mod.get("modName", "") or "").lower())
    attrs = f' data-names="{data_names}"'
    if serve:
        name = _esc(row.mod.get("modName", ""))
        state_cls = _STATE_CSS[row.state]
        flag = "1" if row.ignored else "0"
        action = "un-ignore" if row.ignored else "ignore"
        attrs += (
            f' data-mod="{name}" data-state="{state_cls}" data-ignored="{flag}"'
            f' title="Click to {action}"'
        )
```

- [ ] **Step 6: Add the filter JS.** Find the always-present script block and its last line:

```python
        "window.addEventListener('resize',setHeaderH);setHeaderH();"
    )
```

Replace with (append the shared `filterMods` block before the closing `)`):

```python
        "window.addEventListener('resize',setHeaderH);setHeaderH();"
        "function filterMods(q){"
        "var terms=(q||'').trim().toLowerCase().split(/\\s+/).filter(Boolean);"
        "document.querySelectorAll('[data-names]').forEach(function(row){"
        "var hide=false;"
        "if(terms.length){var names=row.getAttribute('data-names').split('\\n');"
        "hide=!names.some(function(n){return terms.every(function(t){return n.indexOf(t)!==-1;});});}"
        "row.classList.toggle('filter-hidden',hide);});}"
        "(function(){var i=document.getElementById('filter-input');if(!i)return;"
        "i.addEventListener('input',function(){filterMods(this.value);});"
        "i.addEventListener('keydown',function(e){if(e.key==='Escape'){this.value='';filterMods('');}});})();"
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: OK — all tests pass (new + existing).

- [ ] **Step 8: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat(coverage): add header text filter (multi-term AND by mod name)"
```

---

## Task 2: Diff report filter + sticky header

**Goal:** Add the header filter input, sticky header, per-row `data-names`, filter CSS, and filter JS to `generate_diff.py`, and create `test_generate_diff.py`.

**Files:**
- Modify: `tools/generate_diff.py` (`.header` CSS ~483; filter CSS ~488; row render ~698; header HTML ~614; JS ~637–646)
- Create: `tools/test_generate_diff.py`

**Acceptance Criteria:**
- [ ] `.header` CSS rule contains `position: sticky` and `top: 0`.
- [ ] Generated HTML contains the filter `<input type="search" id="filter-input" ...>` inside `.header`.
- [ ] Each mod `<tr>` carries a lowercased `data-names`; a renamed row (differing left/right names) carries **both** names, newline-joined, in one attribute.
- [ ] CSS contains `.filter-input` and `tr.filter-hidden { display: none; }`.
- [ ] JS contains `function filterMods`, wires the `input` event, and clears on `Escape`.

**Verify:** `cd tools && python -m unittest test_generate_diff -v` → OK (all pass)

**Steps:**

- [ ] **Step 1: Write the failing test file.** Create `tools/test_generate_diff.py`:

```python
"""Tests for generate_diff HTML rendering: sticky header, filter, data-names."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_diff import ChangeType, DiffRow, render_html


def _summary(**over):
    s = {
        "added": 0, "removed": 0, "moved": 0, "updated": 0,
        "sections_added": 0, "sections_removed": 0, "sections_renamed": 0,
    }
    s.update(over)
    return s


class RenderTest(unittest.TestCase):
    def setUp(self):
        # One unchanged mod, plus a "renamed" mod whose left/right names differ,
        # so we can assert both names land in a single data-names attribute.
        self.rows = [
            DiffRow(
                left_mod={"modName": "Skyland AIO"},
                right_mod={"modName": "Skyland AIO"},
                change=ChangeType.UNCHANGED,
            ),
            DiffRow(
                left_mod={"modName": "Old Faces 3D"},
                right_mod={"modName": "New Faces Thing"},
                change=ChangeType.UNCHANGED,
            ),
        ]
        self.html = render_html(self.rows, "Old List", "New List", _summary())

    def test_doctype(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))

    def test_header_is_sticky(self):
        match = re.search(r"\.header \{[^}]*\}", self.html)
        self.assertIsNotNone(match, "no .header CSS rule found")
        rule = match.group()
        self.assertIn("position: sticky", rule)
        self.assertIn("top: 0", rule)

    def test_filter_input_present(self):
        self.assertIn('id="filter-input"', self.html)
        self.assertIn('class="filter-input"', self.html)
        self.assertIn('type="search"', self.html)

    def test_filter_css_and_js(self):
        self.assertIn("tr.filter-hidden", self.html)
        self.assertIn("function filterMods", self.html)
        self.assertIn("'Escape'", self.html)

    def test_rows_carry_data_names(self):
        self.assertIn('data-names="skyland aio"', self.html)

    def test_renamed_row_has_both_names_one_attr(self):
        # Either-name matching: both names in ONE attribute, newline-joined.
        self.assertIn('data-names="old faces 3d\nnew faces thing"', self.html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd tools && python -m unittest test_generate_diff -v`
Expected: FAIL — sticky/filter/data-names assertions fail (feature absent).

- [ ] **Step 3: Make the header sticky.** In `tools/generate_diff.py`, find:

```python
.header {
    background: #16213e; padding: 16px 24px; border-bottom: 2px solid #0f3460;
}
```

Replace with:

```python
.header {
    position: sticky; top: 0; z-index: 50;
    background: #16213e; padding: 16px 24px; border-bottom: 2px solid #0f3460;
    box-shadow: 0 4px 12px rgba(0,0,0,0.45);
}
```

- [ ] **Step 4: Add filter CSS.** Find:

```python
.header .lists span { color: #e0e0e0; font-weight: 600; }
```

Insert immediately after it:

```python
.filter-input {
    width: 100%; margin-top: 10px; padding: 6px 10px;
    background: #0f1830; color: #e0e0e0;
    border: 1px solid #1a4a7a; border-radius: 4px;
    font-family: inherit; font-size: 13px;
}
.filter-input::placeholder { color: #6b7a90; }
tr.filter-hidden { display: none; }
```

- [ ] **Step 5: Add the input to the header.** Find (summary close, header close, then the legend comment):

```python
    parts.append("</div>")
    parts.append("</div>")

    # Legend
```

Replace with:

```python
    parts.append("</div>")
    parts.append(
        '<input type="search" id="filter-input" class="filter-input" '
        'placeholder="Filter mods… (space = AND)" autocomplete="off">'
    )
    parts.append("</div>")

    # Legend
```

- [ ] **Step 6: Add `data-names` to mod rows.** In `_render_mod_row`, find:

```python
    parts.append(f'<tr class="{cls}">')
```

Replace with:

```python
    names = []
    for m in (row.left_mod, row.right_mod):
        if m:
            nl = (m.get("modName", "Unknown") or "Unknown").lower()
            if nl not in names:  # dedup: unchanged rows have the same name twice
                names.append(nl)
    data_names = _esc("\n".join(names))
    parts.append(f'<tr class="{cls}" data-names="{data_names}">')
```

- [ ] **Step 7: Add the filter JS.** Find the toggle script and insert a second `parts.append(...)` before `parts.append("</script>")`:

```python
    parts.append(
        "function toggleUnchanged() {"
        " var on = document.body.classList.toggle('hide-unchanged');"
        " var btn = document.getElementById('toggle-unchanged');"
        " btn.classList.toggle('active', on);"
        " btn.textContent = on ? 'Show unchanged mods' : 'Hide unchanged mods';"
        " }"
    )
    parts.append("</script>")
```

Replace with:

```python
    parts.append(
        "function toggleUnchanged() {"
        " var on = document.body.classList.toggle('hide-unchanged');"
        " var btn = document.getElementById('toggle-unchanged');"
        " btn.classList.toggle('active', on);"
        " btn.textContent = on ? 'Show unchanged mods' : 'Hide unchanged mods';"
        " }"
    )
    parts.append(
        "function filterMods(q){"
        "var terms=(q||'').trim().toLowerCase().split(/\\s+/).filter(Boolean);"
        "document.querySelectorAll('[data-names]').forEach(function(row){"
        "var hide=false;"
        "if(terms.length){var names=row.getAttribute('data-names').split('\\n');"
        "hide=!names.some(function(n){return terms.every(function(t){return n.indexOf(t)!==-1;});});}"
        "row.classList.toggle('filter-hidden',hide);});}"
        "(function(){var i=document.getElementById('filter-input');if(!i)return;"
        "i.addEventListener('input',function(){filterMods(this.value);});"
        "i.addEventListener('keydown',function(e){if(e.key==='Escape'){this.value='';filterMods('');}});})();"
    )
    parts.append("</script>")
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd tools && python -m unittest test_generate_diff -v`
Expected: OK — all tests pass.

- [ ] **Step 9: Commit**

```bash
git add tools/generate_diff.py tools/test_generate_diff.py
git commit -m "feat(diff): add header text filter and sticky header"
```

---

## Task 3: Full-suite verification & manual smoke

**Goal:** Confirm the whole tool test suite is green and the generated reports actually filter in a browser.

**Files:** none (verification only)

**Acceptance Criteria:**
- [ ] `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_regenerate -v` → OK.
- [ ] Coverage and diff reports regenerate without error and the filter visibly hides non-matching rows; a multi-term query (`3d thing`) ANDs; Esc/clear restores; sections stay visible.

**Verify:** commands below.

**Steps:**

- [ ] **Step 1: Run the tool suite**

Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_regenerate -v`
Expected: OK (0 failures).

- [ ] **Step 2: Regenerate a coverage and a diff report against real lists**

```bash
cd /path/to/your/modlist-tools/checkout
python tools/generate_coverage.py "lists/NORDIC SOULS v3.1.0.json" "lists/Meteoric 0.0.5.json" -o /tmp/cov-filter-check.html
python tools/generate_diff.py "lists/NORDIC SOULS v3.0.1 - PBR Edition 1.3.0.json" "lists/NORDIC SOULS v3.0.1 - PBR Edition 1.4.0.json" -o /tmp/diff-filter-check.html
```
Expected: both write without error. (Substitute any two real lists present in `lists/` if these names differ.)

- [ ] **Step 3: Manual browser check** — open both files; type a single term (rows narrow, sections remain), type two terms separated by a space (AND — both must appear in the name), press Esc / click the × (all rows return). In the diff, scroll and confirm the filter box stays pinned.

- [ ] **Step 4: Final verification gate** — only claim done after Steps 1–3 pass. No commit (verification only); proceed to branch finish.

---

## Self-Review

**Spec coverage:**
- Header input, case-insensitive, multi-term AND, sections-always-visible → Tasks 1 & 2 input + `filterMods` (iterates `[data-names]`, `terms.every`).
- `data-names` matching target (name only, pre-lowercased, newline-joined) → Task 1 Step 5, Task 2 Step 6.
- `filter-hidden` composes with existing toggles → CSS in Task 1 Step 3 / Task 2 Step 4 (both use `display:none`; independent body-class toggles still apply).
- Coverage collapsed-stay-collapsed → no force-open code added; collapse CSS untouched. ✓
- Diff "either name matches" → Task 2 Step 6 dedup list + JS `names.some(...)`. ✓
- Diff sticky header → Task 2 Step 3. ✓
- `type="search"` + Esc, no live count → input markup + JS keydown handler. ✓
- Tests (string-presence) for both, new `test_generate_diff.py` → Tasks 1 & 2. ✓
- Out of scope (no `modlist_utils` change, no section filtering, no persistence/regex) → respected. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type/name consistency:** `filterMods`, `filter-input` (id+class), `filter-hidden`, `data-names` used identically across both generators, their JS, and both test files. Coverage `render_html(rows, summary, src, tgt)` and diff `render_html(rows, old, new, summary)` signatures match each suite's existing calls.
