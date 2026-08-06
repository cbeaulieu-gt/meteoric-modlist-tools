# Coverage Target-Name Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the coverage report, render a matched mod's row as `Target Name (Source Name)` when the two lists name the same mod differently, so the reader sees the name they already know first.

**Architecture:** Carry the matched target mod's name on `CoverageRow`, then rework the single name-rendering helper (`_name_html`) to emit a muted `(Source Name)` parenthetical after the target name when they differ. The text-filter index gains the second name. All changes are confined to `tools/generate_coverage.py` and its test file; serve mode inherits the change for free because it reuses `render_html`.

**Tech Stack:** Python 3 standard library only (no third-party deps). `unittest` for tests.

**User decisions (already made):**
- Format is "Target (Source)" — target name primary, source name in parens, only when the raw names differ.
- The **whole** rendered name (primary + parenthetical) is the Nexus link.
- The parenthetical renders muted (`.src-alias`, `#8b94a8`, 11px).
- Filtering matches **either** name.
- `data-mod` (serve ignore key) stays the source name — click-to-ignore unaffected.

**Spec:** [docs/design/2026-06-23-coverage-target-name-display-design.md](../design/2026-06-23-coverage-target-name-display-design.md)

---

## File Structure

- **Modify** `tools/generate_coverage.py`
  - `CoverageRow` dataclass — add `target_name: str = ""`.
  - `classify_source_mods` — populate `target_name` from the matched target mod.
  - `_name_html` — emit `Target (Source)` with a `.src-alias` span when names differ.
  - `_render_mod_row` — write both names into `data-names`.
  - `CSS` — add a `.src-alias` rule.
- **Modify** `tools/test_generate_coverage.py` — add coverage for the new behavior.
- **Modify** `CLAUDE.md` — one-line note under the coverage section (tracked as `CLAUDE.MD`; see Task 3).

All tests run from inside `tools/`:
```bash
cd tools
python -m unittest test_generate_coverage -v
```

---

### Task 1: Carry the matched target name on `CoverageRow`

**Goal:** `CoverageRow` exposes the matched target mod's name (empty for unmatched/`Add` rows), populated during classification.

**Files:**
- Modify: `tools/generate_coverage.py` (`CoverageRow` dataclass ~line 47-55; `classify_source_mods` ~line 92-147)
- Test: `tools/test_generate_coverage.py`

**Acceptance Criteria:**
- [ ] `CoverageRow` has a `target_name: str = ""` field.
- [ ] A matched row's `target_name` is the target mod's `modName`.
- [ ] An unmatched (`Add`) row's `target_name` is `""`.

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Add this test class to `tools/test_generate_coverage.py` (after the existing `ClassifyTest` class, before `SummaryTest`). It reuses the module-level `sep`/`mod` helpers:

```python
class TargetNameTest(unittest.TestCase):
    def setUp(self):
        # ENB Helper (source) is named "ENB Helper SE" in the target -> renamed match.
        self.source = [
            sep("Visuals", 0),
            mod("ENB Helper", 1, "Visuals", version="1.5.0", nexus_id=23174),
            mod("SameMod", 2, "Visuals", version="3.0.0", nexus_id=11111),
            mod("MissingMod", 3, "Visuals", version="2.0.0", nexus_id=99999),
        ]
        self.target = [
            sep("T", 0),
            mod("ENB Helper SE", 1, "T", version="1.6.0", nexus_id=23174),
            mod("SameMod", 2, "T", version="3.0.0", nexus_id=11111),
        ]
        self.rows = classify_source_mods(self.source, self.target)

    def _row(self, name):
        for rows in self.rows.values():
            for row in rows:
                if row.mod.get("modName") == name:
                    return row
        raise AssertionError(f"{name} not found")

    def test_matched_renamed_carries_target_name(self):
        self.assertEqual(self._row("ENB Helper").target_name, "ENB Helper SE")

    def test_matched_same_name_carries_target_name(self):
        # Even when identical, the field is populated (render decides whether to show it).
        self.assertEqual(self._row("SameMod").target_name, "SameMod")

    def test_unmatched_has_empty_target_name(self):
        self.assertEqual(self._row("MissingMod").target_name, "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m unittest test_generate_coverage.TargetNameTest -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument` is NOT expected (we don't pass it yet); instead `AttributeError: 'CoverageRow' object has no attribute 'target_name'`.

- [ ] **Step 3: Add the `target_name` field to `CoverageRow`**

In `tools/generate_coverage.py`, change the dataclass:

```python
@dataclass
class CoverageRow:
    mod: dict
    state: CoverageState
    source_version: str
    target_version: str          # "" when the mod is missing
    nexus_id: Optional[int]      # numeric Nexus id, or None
    target_name: str = ""        # matched target mod's modName; "" when unmatched
    ignored: bool = False
```

- [ ] **Step 4: Populate `target_name` in `classify_source_mods`**

In `classify_source_mods`, the loop currently builds the row like this:

```python
        raw_id = mod.get("id")
        nexus_id = raw_id if isinstance(raw_id, int) else None

        row = CoverageRow(mod, state, source_version, target_version, nexus_id)
        row.ignored = is_ignored(ignore, mod)
        rows_by_section[section].append(row)
```

Replace the `row = ...` line so the matched target name is passed. `target_mod` is already in scope from `match_lookup.get(id(mod))` earlier in the loop:

```python
        raw_id = mod.get("id")
        nexus_id = raw_id if isinstance(raw_id, int) else None

        target_name = target_mod.get("modName", "") if target_mod else ""
        row = CoverageRow(
            mod, state, source_version, target_version, nexus_id, target_name
        )
        row.ignored = is_ignored(ignore, mod)
        rows_by_section[section].append(row)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd tools && python -m unittest test_generate_coverage.TargetNameTest -v`
Expected: PASS (3 tests).

Then run the full file to confirm nothing regressed:
Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "Carry matched target mod name on CoverageRow"
```

---

### Task 2: Render `Target (Source)` with a muted alias, and filter on both names

**Goal:** `_name_html` renders the target name primary with a muted `(Source Name)` parenthetical when the names differ (whole thing is the Nexus link); the text filter matches either name.

**Files:**
- Modify: `tools/generate_coverage.py` (`CSS` ~line 254-279; `_name_html` ~line 318-323; `_render_mod_row` ~line 339-357)
- Test: `tools/test_generate_coverage.py`

**Acceptance Criteria:**
- [ ] A matched, renamed mod renders `Target Name<span class="src-alias">(Source Name)</span>`, wrapped in the Nexus `<a>`.
- [ ] A matched mod with identical names renders the single name, no `src-alias` span.
- [ ] An `Add` (unmatched) mod renders the source name only, no `src-alias` span.
- [ ] A `.src-alias` CSS rule exists.
- [ ] A renamed mod's `data-names` attribute carries both lowercased names, newline-separated.

**Verify:** `cd tools && python -m unittest test_generate_coverage -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Add this test class to `tools/test_generate_coverage.py` (after `TargetNameTest`):

```python
class RenderTargetNameTest(unittest.TestCase):
    def setUp(self):
        self.source = [
            sep("Visuals", 0),
            # Renamed match: source "ENB Helper" vs target "ENB Helper SE".
            mod("ENB Helper", 1, "Visuals", version="1.5", nexus_id=23174),
            # Same-name match.
            mod("SameMod", 2, "Visuals", version="3.0", nexus_id=11111),
            # Unmatched -> Add.
            mod("MissingMod", 3, "Visuals", version="2.0", nexus_id=99999),
        ]
        self.target = [
            sep("T", 0),
            mod("ENB Helper SE", 1, "T", version="1.6", nexus_id=23174),
            mod("SameMod", 2, "T", version="3.0", nexus_id=11111),
        ]
        self.rows = classify_source_mods(self.source, self.target)
        self.summary = compute_summary(self.rows)
        self.html = render_html(self.rows, self.summary, "Source", "Target")

    def test_renamed_shows_target_first_with_source_alias(self):
        # Target name is primary; source name follows in a muted span.
        self.assertIn(
            'ENB Helper SE<span class="src-alias">(ENB Helper)</span>',
            self.html,
        )

    def test_renamed_whole_name_is_one_link(self):
        # Both names sit inside a single anchor to the source's Nexus page.
        self.assertIn(
            '<a href="https://www.nexusmods.com/skyrimspecialedition/mods/23174"'
            ' target="_blank" rel="noopener">'
            'ENB Helper SE<span class="src-alias">(ENB Helper)</span></a>',
            self.html,
        )

    def test_same_name_has_no_alias(self):
        self.assertIn(">SameMod</a>", self.html)
        # No alias span anywhere for SameMod.
        self.assertNotIn("(SameMod)", self.html)

    def test_add_shows_source_name_only(self):
        self.assertIn(">MissingMod</a>", self.html)
        self.assertNotIn("(MissingMod)", self.html)

    def test_src_alias_css_present(self):
        self.assertIn(".src-alias", self.html)

    def test_data_names_carries_both_names(self):
        self.assertIn('data-names="enb helper\nenb helper se"', self.html)

    def test_same_name_data_names_single(self):
        self.assertIn('data-names="samemod"', self.html)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m unittest test_generate_coverage.RenderTargetNameTest -v`
Expected: FAIL (no `src-alias` span yet; `data-names` carries only the source name).

- [ ] **Step 3: Add the `.src-alias` CSS rule**

In `tools/generate_coverage.py`, the `CSS` string has these rules near the mod row styling:

```python
.mod-row a { color: inherit; text-decoration: none; }
.mod-row a:hover { text-decoration: underline; }
.mod-name { flex: 1; }
.ver { font-size: 11px; white-space: nowrap; }
```

Add a `.src-alias` rule immediately after `.mod-name`:

```python
.mod-row a { color: inherit; text-decoration: none; }
.mod-row a:hover { text-decoration: underline; }
.mod-name { flex: 1; }
.src-alias { color: #8b94a8; font-size: 11px; margin-left: 4px; }
.ver { font-size: 11px; white-space: nowrap; }
```

- [ ] **Step 4: Rework `_name_html`**

Replace the whole `_name_html` function:

```python
def _name_html(row):
    source_name = row.mod.get("modName", "Unknown")
    target_name = row.target_name
    if target_name and target_name != source_name:
        # Target name (what the reader knows it as) is primary; the source's
        # label follows in a muted alias span. Both sit inside the one link.
        inner = (
            f'{_esc(target_name)}'
            f'<span class="src-alias">({_esc(source_name)})</span>'
        )
    else:
        inner = _esc(source_name)
    if row.nexus_id is not None:
        url = NEXUS_URL.format(id=row.nexus_id)
        return f'<a href="{url}" target="_blank" rel="noopener">{inner}</a>'
    return inner
```

- [ ] **Step 5: Write both names into `data-names`**

In `_render_mod_row`, the current line builds the filter index from the source name only:

```python
    data_names = _esc((row.mod.get("modName", "") or "").lower())
    attrs = f' data-names="{data_names}"'
```

Replace it so a distinct target name is appended as a second newline-separated entry (the filter JS already splits `data-names` on `\n`):

```python
    names = [(row.mod.get("modName", "") or "").lower()]
    target_lower = (row.target_name or "").lower()
    if target_lower and target_lower != names[0]:
        names.append(target_lower)
    data_names = _esc("\n".join(names))
    attrs = f' data-names="{data_names}"'
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd tools && python -m unittest test_generate_coverage.RenderTargetNameTest -v`
Expected: PASS (7 tests).

Then the full file (confirms `test_mod_rows_carry_data_names` for the same-name "valhalla combat" case still holds, since identical names append no second entry):
Run: `cd tools && python -m unittest test_generate_coverage -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "Coverage: render target name first with muted source alias"
```

---

### Task 3: Document the target-first naming in CLAUDE.md

**Goal:** The coverage section of `CLAUDE.md` notes the target-first naming so the guide stays accurate.

**Files:**
- Modify: `CLAUDE.md` (the "Coverage view" section, under the `--serve`/states description)

**Acceptance Criteria:**
- [ ] `CLAUDE.md` mentions that matched mods render `Target (Source)` when names differ.

**Verify:** `git diff --staged CLAUDE.MD` shows the added note; tests unaffected.

**Steps:**

- [ ] **Step 1: Add the note**

In `CLAUDE.md`, find the `Features:` line at the end of the "Coverage view" section (begins `Features: single column grouped by source separator;`). Immediately **before** that `Features:` line, add this paragraph:

```markdown
**Mod names:** rows show the **source** mod's name, except for a mod that also exists
in the target under a *different* name — there the row reads `Target Name (Source Name)`
(the name you know it by, with the source's label muted in parentheses). The whole name
links to the source's Nexus page; the text filter matches either name.
```

- [ ] **Step 2: Stage with the correct casing and commit**

Git tracks this file as `CLAUDE.MD` (uppercase extension); `git add CLAUDE.md` silently misses it. Stage the tracked path explicitly:

```bash
git add CLAUDE.MD
git status   # confirm CLAUDE.MD is staged (not left in "Changes not staged")
git commit -m "Docs: note target-first mod naming in coverage view"
```

---

## Notes for the implementer

- **Do NOT** touch `modlist_utils.py`, `generate_diff.py`, `generate_changelog.py`, `coverage_server.py`, or the ignore-file format. Serve mode works automatically because it renders through the same `render_html`.
- The `data-names` attribute carries a **literal** newline between names — that is intentional and matches the existing filter JS (`data-names.split('\n')`). Do not convert it to a `&#10;` entity or a space.
- When the source mod has no `modName`, `row.mod.get("modName", "Unknown")` yields `"Unknown"`; the alias logic still behaves (no target name → single "Unknown"). No special-casing needed.
- Run the full `test_generate_coverage` suite after each task, not just the new class.
