# Filter-Driven Section Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** While a text filter is active, hide section headers (and, in coverage, major-separator bands) that contain no row that would actually be visible.

**Architecture:** Pure client-side JS extension of the existing `filterMods()` in each generator — no HTML restructuring. After the per-row `filter-hidden` pass, a new `applySectionVisibility(active)` toggles a `filter-empty` (`display:none`) class on sections/bands based on a shared `rowCounts(row)` predicate (matches filter AND not suppressed by the active view toggle; collapse ignored). One markup change in coverage: a `bandless` marker class on the standalone major-separator body so it can be targeted unambiguously.

**Tech Stack:** Python 3 stdlib (HTML/CSS/JS emitted as strings), `unittest`. No third-party deps.

**User decisions (already made):**
- Apply to **both** coverage and diff reports ("Both coverage & diff").
- Coverage: **leave collapse alone** — never auto-expand/collapse on filter; a collapsed section with a matching, would-be-visible mod keeps its header.
- The visibility rule **accounts for the view toggle**: "if I match on 'ABC' but 'abc mod' is common, the header shows only if common is also being shown."

**Design spec:** [docs/design/2026-06-21-filter-section-visibility-design.md](../design/2026-06-21-filter-section-visibility-design.md)

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `tools/generate_coverage.py` | Coverage HTML/CSS/JS emission | Add `bandless` class; add `filter-empty` CSS; extend `filterMods` with `rowCounts`/`unitHasMatch`/`applySectionVisibility`/`refilter`; wire `toggleCommon` + serve ignore handler |
| `tools/generate_diff.py` | Diff HTML/CSS/JS emission | Add `filter-empty` CSS for `tr.section-header`; extend `filterMods` with `rowCounts`/`applySectionVisibility`/`refilter`; wire `toggleUnchanged` |
| `tools/test_generate_coverage.py` | Coverage render tests | Add `FilterSectionVisibilityTest` |
| `tools/test_generate_diff.py` | Diff render tests | Add assertions to `RenderTest` |

The JS for the two reports is separate (different DOM, different toggle predicate) and lives as string literals inside each generator — there is no shared JS module, so the near-duplicate `rowCounts`/`refilter` is expected, not a DRY violation.

Tasks 1 and 2 are independent (different files) and each is independently committable.

---

### Task 1: Coverage — filter-driven section & band visibility

**Goal:** In `generate_coverage.py`, hide `.section` / bandless `.section-body` units with no would-be-visible matching row while a filter is active, and hide a `.band` when every section beneath it is hidden.

**Files:**
- Modify: `tools/generate_coverage.py` (CSS ~line 204; `_render_bandless_rows` ~line 358; script block ~lines 438-458; serve block ~line 500)
- Test: `tools/test_generate_coverage.py`

**Acceptance Criteria:**
- [ ] The standalone major-separator body renders as `<div class="section-body bandless">`.
- [ ] CSS hides `.section.filter-empty`, `.section-body.bandless.filter-empty`, `.band.filter-empty`.
- [ ] `filterMods` calls `applySectionVisibility(terms.length>0)`; `rowCounts` excludes `mod-common`/`mod-ignored` rows when `hide-common` is on; collapse is not part of the predicate.
- [ ] `toggleCommon` and the serve-mode ignore handler call `refilter()`.
- [ ] All coverage tests pass.

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → OK

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append this class to `tools/test_generate_coverage.py` (before the `if __name__` block):

```python
class FilterSectionVisibilityTest(unittest.TestCase):
    def setUp(self):
        from generate_coverage import map_sections_to_majors

        # A band (BASE) with one normal section under it plus a mod sitting
        # directly under the major (rendered bandless).
        self.source = [
            {"type": "separator", "separatorName": "---------- BASE ----------", "order": 0},
            {"type": "separator", "separatorName": "Base Stuff", "order": 1},
            {"type": "mod", "modName": "BaseMod", "separatorName": "Base Stuff",
             "order": 2, "id": 1, "general": {"version": "1.0"}},
            {"type": "mod", "modName": "DirectMod",
             "separatorName": "---------- BASE ----------",
             "order": 3, "id": 2, "general": {"version": "1.0"}},
        ]
        self.majors = map_sections_to_majors(self.source)
        self.rows = classify_source_mods(self.source, [])
        self.summary = compute_summary(self.rows)
        self.static = render_html(self.rows, self.summary, "S", "T", self.majors)
        self.served = render_html(
            self.rows, self.summary, "S", "T", self.majors, serve=True
        )

    def test_bandless_body_has_marker_class(self):
        # The standalone major body is tagged so the recompute/CSS can target it
        # without matching a normal section's inner body.
        self.assertIn('class="section-body bandless"', self.static)

    def test_filter_empty_css_rules_present(self):
        self.assertIn(".section.filter-empty", self.static)
        self.assertIn(".section-body.bandless.filter-empty", self.static)
        self.assertIn(".band.filter-empty", self.static)

    def test_section_visibility_js_present(self):
        self.assertIn("function applySectionVisibility", self.static)
        self.assertIn("function rowCounts", self.static)
        self.assertIn("function refilter", self.static)
        # filterMods drives the recompute (active iff there are filter terms).
        self.assertIn("applySectionVisibility(terms.length>0)", self.static)
        # Band visibility is decided by walking its sibling sections.
        self.assertIn("nextElementSibling", self.static)

    def test_rowcounts_accounts_for_hide_common(self):
        # A common/ignored row suppressed by Hide common must not keep its
        # section alive — the predicate checks both classes against hide-common.
        self.assertIn("hide-common", self.static)
        self.assertIn("mod-ignored", self.static)
        self.assertIn("mod-common", self.static)

    def test_toggle_common_refilters(self):
        self.assertIn("refilter();", self.static)

    def test_serve_refreshes_visibility_after_ignore(self):
        # Ignoring a mod can empty a section when Hide common is on, so the serve
        # ignore round-trip recounts AND refreshes section/band visibility.
        self.assertIn("recount();refilter();", self.served)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd tools && python -m unittest test_generate_coverage.FilterSectionVisibilityTest -v`
Expected: FAIL — `'class="section-body bandless"'`, `.section.filter-empty`, `function applySectionVisibility`, etc. are not yet present.

- [ ] **Step 3: Add the `bandless` marker class**

In `tools/generate_coverage.py`, `_render_bandless_rows` (~line 358), change:

```python
    parts.append('<div class="section-body">')
```

to:

```python
    parts.append('<div class="section-body bandless">')
```

- [ ] **Step 4: Add the `filter-empty` CSS**

In `tools/generate_coverage.py`, find (~line 204):

```python
.mod-row.filter-hidden { display: none; }
```

and add the new rule immediately after it (still inside the same CSS string block):

```python
.mod-row.filter-hidden { display: none; }
.section.filter-empty, .section-body.bandless.filter-empty, .band.filter-empty { display: none; }
```

- [ ] **Step 5: Extend `filterMods` with the recompute functions**

In `tools/generate_coverage.py`, inside the main `<script>` `parts.append(...)` block (~lines 448-454), find this line (the end of `filterMods`):

```python
        "row.classList.toggle('filter-hidden',hide);});}"
```

and replace it with:

```python
        "row.classList.toggle('filter-hidden',hide);});"
        "applySectionVisibility(terms.length>0);}"
        "function rowCounts(row){"
        "if(row.classList.contains('filter-hidden'))return false;"
        "if(document.body.classList.contains('hide-common')&&(row.classList.contains('mod-common')||row.classList.contains('mod-ignored')))return false;"
        "return true;}"
        "function unitHasMatch(u){var rows=u.querySelectorAll('.mod-row');"
        "for(var i=0;i<rows.length;i++)if(rowCounts(rows[i]))return true;return false;}"
        "function applySectionVisibility(active){"
        "document.querySelectorAll('.section, .section-body.bandless').forEach(function(u){"
        "u.classList.toggle('filter-empty',active&&!unitHasMatch(u));});"
        "document.querySelectorAll('.band').forEach(function(b){var any=false;"
        "for(var el=b.nextElementSibling;el&&!el.classList.contains('band');el=el.nextElementSibling){"
        "if((el.classList.contains('section')||el.classList.contains('bandless'))&&!el.classList.contains('filter-empty')){any=true;break;}}"
        "b.classList.toggle('filter-empty',active&&!any);});}"
        "function refilter(){var i=document.getElementById('filter-input');filterMods(i?i.value:'');}"
```

(The units pass sets `filter-empty` on sections/bandless bodies first; the band pass then reads those marks via `nextElementSibling`. When `active` is false, every `toggle(..., active&&...)` clears the class, restoring the normal view. Function declarations are hoisted, so the forward reference from `filterMods` is fine.)

- [ ] **Step 6: Wire `toggleCommon` to refilter**

In the same block (~lines 442-444), find:

```python
        "b.textContent=on?'Show common mods':'Hide common mods';}"
```

and replace with:

```python
        "b.textContent=on?'Show common mods':'Hide common mods';refilter();}"
```

- [ ] **Step 7: Wire the serve-mode ignore handler to refilter**

In `tools/generate_coverage.py`, inside the `if serve:` script block (~line 500), find:

```python
            "if(!d.ok)return;setIgnored(row,!on);recount();}).catch(function(){});});"
```

and replace with:

```python
            "if(!d.ok)return;setIgnored(row,!on);recount();refilter();}).catch(function(){});});"
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: PASS (all tests, including the new `FilterSectionVisibilityTest`).

- [ ] **Step 9: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat(coverage): hide filter-emptied sections and bands

A section header (and its major-separator band) hides while a filter is
active when no row in it would actually be visible — accounting for the
Hide common toggle, ignoring collapse state.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Diff — filter-driven section-header visibility

**Goal:** In `generate_diff.py`, hide a `tr.section-header` while a filter is active when no mod row between it and the next section header would be visible (accounting for Hide unchanged).

**Files:**
- Modify: `tools/generate_diff.py` (CSS ~line 498; script block ~lines 651-671)
- Test: `tools/test_generate_diff.py`

**Acceptance Criteria:**
- [ ] CSS hides `tr.section-header.filter-empty`.
- [ ] `filterMods` calls `applySectionVisibility(terms.length>0)`; `rowCounts` excludes `mod-unchanged` rows when `hide-unchanged` is on.
- [ ] `toggleUnchanged` calls `refilter()`.
- [ ] All diff tests pass.

**Verify:** `cd tools && python -m unittest test_generate_diff -v` → OK

**Steps:**

- [ ] **Step 1: Write the failing tests**

Add these methods to the existing `RenderTest` class in `tools/test_generate_diff.py` (after `test_renamed_row_has_both_names_one_attr`):

```python
    def test_section_filter_css_present(self):
        self.assertIn("tr.section-header.filter-empty", self.html)

    def test_section_visibility_js_present(self):
        self.assertIn("function applySectionVisibility", self.html)
        self.assertIn("function rowCounts", self.html)
        self.assertIn("function refilter", self.html)
        self.assertIn("applySectionVisibility(terms.length>0)", self.html)

    def test_rowcounts_accounts_for_hide_unchanged(self):
        # An unchanged row suppressed by Hide unchanged must not keep its section
        # header alive while a filter is active.
        self.assertIn("hide-unchanged", self.html)
        self.assertIn("mod-unchanged", self.html)

    def test_toggle_unchanged_refilters(self):
        self.assertIn("refilter();", self.html)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd tools && python -m unittest test_generate_diff.RenderTest -v`
Expected: FAIL — `tr.section-header.filter-empty`, `function applySectionVisibility`, `refilter();` are not yet present.

- [ ] **Step 3: Add the `filter-empty` CSS**

In `tools/generate_diff.py`, find (~line 498):

```python
tr.filter-hidden { display: none; }
```

and add the new rule immediately after it (same CSS string block):

```python
tr.filter-hidden { display: none; }
tr.section-header.filter-empty { display: none; }
```

- [ ] **Step 4: Extend `filterMods` with the recompute functions**

In `tools/generate_diff.py`, inside the filter `parts.append(...)` block (~lines 661-667), find this line (the end of `filterMods`):

```python
        "row.classList.toggle('filter-hidden',hide);});}"
```

and replace it with:

```python
        "row.classList.toggle('filter-hidden',hide);});"
        "applySectionVisibility(terms.length>0);}"
        "function rowCounts(row){"
        "if(row.classList.contains('filter-hidden'))return false;"
        "if(document.body.classList.contains('hide-unchanged')&&row.classList.contains('mod-unchanged'))return false;"
        "return true;}"
        "function applySectionVisibility(active){var hdr=null,any=false;"
        "function close(){if(hdr)hdr.classList.toggle('filter-empty',active&&!any);}"
        "document.querySelectorAll('.diff-table tr').forEach(function(tr){"
        "if(tr.classList.contains('section-header')){close();hdr=tr;any=false;}"
        "else if(rowCounts(tr))any=true;});close();}"
        "function refilter(){var i=document.getElementById('filter-input');filterMods(i?i.value:'');}"
```

(Walks the flat table once: each `section-header` closes the previous group — toggling its `filter-empty` from whether any mod row in it counted — and starts a new one. `close()` at the end finalizes the last group. When `active` is false, every header's class is cleared.)

- [ ] **Step 5: Wire `toggleUnchanged` to refilter**

In `tools/generate_diff.py`, inside the toggle `parts.append(...)` block (~lines 652-658), find:

```python
        " btn.textContent = on ? 'Show unchanged mods' : 'Hide unchanged mods';"
        " }"
```

and replace with:

```python
        " btn.textContent = on ? 'Show unchanged mods' : 'Hide unchanged mods';"
        " refilter();"
        " }"
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd tools && python -m unittest test_generate_diff -v`
Expected: PASS (all tests, including the four new assertions).

- [ ] **Step 7: Commit**

```bash
git add tools/generate_diff.py tools/test_generate_diff.py
git commit -m "feat(diff): hide filter-emptied section headers

A section-header row hides while a filter is active when no mod row in
it would be visible — accounting for the Hide unchanged toggle.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Full regression + manual smoke check

**Goal:** Confirm the whole `tools/` suite is green and visually confirm the behavior in a real generated report.

**Files:** none (verification only)

**Acceptance Criteria:**
- [ ] The full `tools/` unittest suite passes.
- [ ] A regenerated coverage report visibly hides empty sections/bands while typing in the filter, and a band with a surviving section stays; clearing the filter restores everything; collapse-state is untouched.

**Verify:** `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_coverage_ignore test_coverage_server test_regenerate -v` → OK

**Steps:**

- [ ] **Step 1: Run the full tools suite**

Run:
```bash
cd tools && python -m unittest test_modlist_utils test_generate_coverage test_coverage_ignore test_coverage_server test_regenerate test_generate_diff -v
```
Expected: OK (no failures/errors).

- [ ] **Step 2: Generate a real report and smoke-test in a browser**

Pick an existing list pair (e.g. a coverage report already in `output/`). From the repo root:
```bash
python tools/generate_coverage.py "lists/BottleRim 2.1.1.json" "lists/Meteoric 0.0.5.json" -o output/
python tools/generate_diff.py "lists/NORDIC SOULS v3.0.1 - PBR Edition 1.3.0.json" "lists/NORDIC SOULS v3.0.1 - PBR Edition 1.4.0.json" -o output/
```
(Substitute list filenames that actually exist in `lists/`.)

Open the generated HTML and verify:
- Typing a term that matches mods in only some sections hides the other sections entirely.
- A major band stays visible while at least one section under it has a match; it disappears once all its sections are empty.
- A match that is **common** disappears (and its section hides) when **Hide common** is on, and reappears when off.
- Clearing the filter (or pressing Escape) restores all sections, bands, and the original collapse state.

- [ ] **Step 3: Note the result**

No commit needed (verification only). If the smoke test surfaces a defect, return to Task 1/2.

---

## Self-Review

- **Spec coverage:** single rule → `rowCounts` (Tasks 1 & 2); coverage band tracking → `applySectionVisibility` band walk (Task 1); diff symmetry → Task 2; `bandless` markup change → Task 1 Step 3; wiring (filterMods/toggle/serve) → Task 1 Steps 5-7, Task 2 Steps 4-5; collapse ignored → predicate has no collapse check; testing → string-presence tests in Tasks 1 & 2, full suite in Task 3. No gaps.
- **Placeholders:** none — every code step shows the exact before/after string.
- **Type/name consistency:** `applySectionVisibility`, `rowCounts`, `refilter`, `unitHasMatch`, `filter-empty`, `bandless` used identically across tasks and tests.
