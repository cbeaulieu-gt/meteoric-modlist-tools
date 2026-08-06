# Base Update Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--base OLD.json` option to `generate_coverage.py` that filters the coverage report to mods that changed between an old and a new base list (version, plugin set, added, removed), plus a new "Plugins" coverage state that applies to ALL coverage reports.

**Architecture:** All logic lives in the existing `tools/` scripts. `modlist_utils.py` gains a `plugin_set` helper and a `first_name` override on `resolve_output_path`. `generate_coverage.py` gains two new `CoverageState` members (`PLUGINS`, `REMOVED`), a base change-set computation (`compute_base_changes`), a removed-rows builder (`build_removed_rows`), a shared `build_report` assembler, and `--base` CLI/render wiring. `coverage_server.py` threads the base path through serve mode. `regenerate.py` learns a new `rebase` report type. No third-party dependencies — stdlib only, matching the codebase.

**Tech Stack:** Python 3 stdlib, `unittest`, self-contained HTML/CSS/JS reports.

**Spec:** [docs/design/2026-07-03-base-update-coverage-design.md](../design/2026-07-03-base-update-coverage-design.md) (committed on branch `base-update-coverage`).

**User decisions (already made):**
- Approach A: `--base` option on `generate_coverage.py` (not a diff option, not a standalone tool).
- Change scope: all actionable base changes — adds, version changes, plugin-set changes, removals of mods the target still carries.
- Reference list: the in-progress target (PBR 1.5.0), re-run as work proceeds (live shrinking worklist).
- Load-order/move detection: out of scope.
- The Plugins state applies **everywhere** (plain coverage too); unimportant diffs get click-ignored.
- Filename convention: `output/<target>/<source> (from <base>).rebase.html`; `regenerate.py` learns the `rebase` type.
- **Model split for execution: implementation subagents run on `model: opus`. Fable (the coordinating session) does orchestration, spec/code review, and verification only.** (This overrides the CLAUDE.md default of Sonnet implementers for this plan.)

**Branch:** work happens on the existing `base-update-coverage` branch (already checked out; spec committed).

---

## File map

| File | Change |
|---|---|
| `tools/modlist_utils.py` | Add `plugin_set()`; add `first_name=` param to `resolve_output_path()` |
| `tools/test_modlist_utils.py` | Tests for both |
| `tools/generate_coverage.py` | `PLUGINS` + `REMOVED` states, classification, delta text, CSS/glyphs/badges, `% covered`, serve JS, `compute_base_changes`, `build_removed_rows`, `build_report`, `--base` CLI, base-mode header/naming |
| `tools/test_generate_coverage.py` | Tests for all of the above |
| `tools/coverage_server.py` | `base_path` threading through `serve` / `make_handler` / `_render_current` |
| `tools/test_coverage_server.py` | Base-mode server test |
| `tools/regenerate.py` | `rebase` type: filename parse, `Job.base_*` fields, `build_cmd`, display |
| `tools/test_regenerate.py` | Tests for the `rebase` type |
| `.claude/commands/serve-coverage.md` | Optional `<base>` argument |
| `CLAUDE.md` | Document new states, `--base`, `rebase` naming (git: stage as `CLAUDE.MD`) |
| `output/NORDIC SOULS v3.1.1 - PBR Edition 1.5.0/NORDIC SOULS v3.1.1 (from NORDIC SOULS v3.0.1).rebase.html` | Generated end-to-end (Task 8) |

Note for implementers: every test file starts with `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` and tests run from inside `tools/`. All Verify commands below assume `cd tools` first. The `−` characters in glyphs/deltas are U+2212 MINUS SIGN (matching the spec), not ASCII hyphens; `→` is U+2192; `±` is U+00B1. Copy them exactly from this plan.

---

### Task 1: Utils groundwork — `plugin_set` + `resolve_output_path` override

**Goal:** Shared plugin-set normalization and the output-filename override the rebase naming needs.

**Files:**
- Modify: `tools/modlist_utils.py`
- Test: `tools/test_modlist_utils.py`

**Acceptance Criteria:**
- [ ] `plugin_set(mod)` returns a frozenset of lowercased, trimmed plugin filenames; blank entries dropped; missing `plugins` key → empty frozenset.
- [ ] `resolve_output_path(..., first_name="X")` names the file `X.<type>.<ext>`; omitting `first_name` is byte-identical to today.
- [ ] All existing `test_modlist_utils` tests still pass.

**Verify:** `cd tools; python -m unittest test_modlist_utils -v` → all pass, including `PluginSetTest` and the two new `ResolveOutputPathTest` methods.

**Steps:**

- [ ] **Step 1: Write the failing tests**

In `tools/test_modlist_utils.py`, extend the import block:

```python
from modlist_utils import (
    compare_versions,
    match_mods,
    plugin_set,
    resolve_output_path,
    recover_version,
    parse_archive_identity,
)
```

Add at the end of the file (before the `if __name__ == "__main__":` block if present, otherwise at the end):

```python
class PluginSetTest(unittest.TestCase):
    def test_normalizes_case_and_order(self):
        a = {"plugins": ["Alpha.esp", "beta.ESL"]}
        b = {"plugins": ["BETA.esl", "alpha.ESP"]}
        self.assertEqual(plugin_set(a), plugin_set(b))

    def test_missing_and_empty_are_equal_empty(self):
        self.assertEqual(plugin_set({}), frozenset())
        self.assertEqual(plugin_set({"plugins": []}), plugin_set({}))

    def test_blank_entries_dropped(self):
        self.assertEqual(
            plugin_set({"plugins": ["", "  ", "A.esp"]}), frozenset({"a.esp"})
        )

    def test_whitespace_trimmed(self):
        self.assertEqual(
            plugin_set({"plugins": [" A.esp "]}), frozenset({"a.esp"})
        )

    def test_difference_detected(self):
        a = {"plugins": ["A.esp", "B.esp"]}
        b = {"plugins": ["A.esp"]}
        self.assertNotEqual(plugin_set(a), plugin_set(b))
```

Add two methods to the existing `ResolveOutputPathTest` class:

```python
    def test_first_name_override_names_the_file(self):
        with tempfile.TemporaryDirectory() as root:
            out = resolve_output_path(
                root + os.sep,
                "lists/New.json",
                "lists/Target.json",
                "rebase",
                "html",
                first_name="New (from Old)",
            )
            self.assertEqual(
                out, os.path.join(root, "Target", "New (from Old).rebase.html")
            )

    def test_no_override_uses_first_path_basename(self):
        with tempfile.TemporaryDirectory() as root:
            out = resolve_output_path(
                root + os.sep, "lists/New.json", "lists/Target.json", "coverage", "html"
            )
            self.assertEqual(out, os.path.join(root, "Target", "New.coverage.html"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools; python -m unittest test_modlist_utils -v`
Expected: FAIL — `ImportError: cannot import name 'plugin_set'`.

- [ ] **Step 3: Implement**

In `tools/modlist_utils.py`, change the `resolve_output_path` signature and name line:

```python
def resolve_output_path(output_arg, first_path, second_path, type_label, ext,
                        first_name=None):
```

Inside, replace `name = os.path.splitext(os.path.basename(first_path))[0]` with:

```python
    name = first_name or os.path.splitext(os.path.basename(first_path))[0]
```

and add to the docstring's parameter notes:

```
    first_name overrides the filename stem derived from first_path (the type/ext
    convention is unchanged) — used by rebase reports, whose stem decorates the
    source name with the base list.
```

Then add `plugin_set` right after `extract_mods`:

```python
def plugin_set(mod):
    """Normalized plugin-filename set for cross-list comparison.

    Plugins are compared as filenames only: lowercased, whitespace-trimmed,
    order-independent. Blank entries are dropped; a mod without plugins yields
    an empty frozenset (and two empty sets compare equal).
    """
    return frozenset(
        p.strip().lower() for p in mod.get("plugins", []) if p and p.strip()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools; python -m unittest test_modlist_utils -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/modlist_utils.py tools/test_modlist_utils.py
git commit -m "feat: add plugin_set helper and resolve_output_path first_name override"
```

---

### Task 2: The Plugins state, end to end (all coverage reports)

**Goal:** A matched mod that would be Common but whose plugin set differs from the source's renders as an actionable violet `±` "Plugins" row with an inline delta, counted in badges, `% covered` (half weight), and serve-mode recounting.

**Files:**
- Modify: `tools/generate_coverage.py`
- Test: `tools/test_generate_coverage.py`

**Acceptance Criteria:**
- [ ] Same-version (or Unknown-version) matched pair with differing plugin sets → `CoverageState.PLUGINS`; matching sets → `COMMON` as before.
- [ ] Precedence `Add > Newer > Differs > Plugins > Common`; source-older stays Common even with plugin diff.
- [ ] Row shows version + delta (`+x.esp −y.esp`, ≤3 names inline, else `+N −M plugins`), full delta in the version cell's tooltip.
- [ ] `± N plugins` summary badge; section badges/collapse treat Plugins as actionable; `% covered` counts it half; serve JS recounts it and un-ignore restores the class.
- [ ] All existing coverage tests still pass.

**Verify:** `cd tools; python -m unittest test_generate_coverage -v` → all pass, including `PluginsStateTest`, `PluginDeltaTextTest`, `RenderPluginsTest`.

**Steps:**

- [ ] **Step 1: Write the failing tests**

In `tools/test_generate_coverage.py`:

1. Update the `make_summary` helper to cover the new state (keeps `coverage_percent` callable):

```python
def make_summary(total, add=0, newer=0, differs=0, plugins=0, common=0, ignored=0):
    """Build a summary dict shaped like compute_summary's output."""
    return {
        "total": total,
        "ignored": ignored,
        "counts": {
            CoverageState.ADD: add,
            CoverageState.NEWER: newer,
            CoverageState.DIFFERS: differs,
            CoverageState.PLUGINS: plugins,
            CoverageState.COMMON: common,
        },
    }
```

2. Add these test classes at the end of the file (before `if __name__ == "__main__":`):

```python
class PluginsStateTest(unittest.TestCase):
    def _row(self, rows_by_section, name):
        for rows in rows_by_section.values():
            for row in rows:
                if row.mod.get("modName") == name:
                    return row
        raise AssertionError(f"{name} not found")

    def _classify_pair(self, src_kwargs, tgt_kwargs):
        source = [sep("S", 0), mod("X", 1, "S", nexus_id=1, **src_kwargs)]
        target = [sep("T", 0), mod("X", 1, "T", nexus_id=1, **tgt_kwargs)]
        return self._row(classify_source_mods(source, target), "X")

    def test_same_version_different_plugins_is_plugins(self):
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["A.esp", "B.esp"]},
            {"version": "1.0", "plugins": ["A.esp"]},
        )
        self.assertEqual(row.state, CoverageState.PLUGINS)
        self.assertEqual(row.plugins_added, ("b.esp",))
        self.assertEqual(row.plugins_removed, ())

    def test_same_version_same_plugins_is_common(self):
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["A.esp"]},
            {"version": "1.0", "plugins": ["A.esp"]},
        )
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_plugin_order_and_case_ignored(self):
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["a.esp", "B.esp"]},
            {"version": "1.0", "plugins": ["B.ESP", "A.esp"]},
        )
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_unknown_version_with_plugin_diff_is_plugins(self):
        # Versions can't speak — plugin drift is the only usable signal.
        row = self._classify_pair(
            {"plugins": ["A.esp"]},
            {"version": "2.0", "plugins": ["B.esp"]},
        )
        self.assertEqual(row.state, CoverageState.PLUGINS)

    def test_unknown_version_same_plugins_stays_common(self):
        row = self._classify_pair(
            {"plugins": ["A.esp"]},
            {"version": "2.0", "plugins": ["A.esp"]},
        )
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_source_older_with_plugin_diff_stays_common(self):
        # Target is ahead; matching an older source's layout isn't a goal.
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["A.esp"]},
            {"version": "2.0", "plugins": ["B.esp"]},
        )
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_newer_wins_over_plugin_diff(self):
        row = self._classify_pair(
            {"version": "2.0", "plugins": ["A.esp"]},
            {"version": "1.0", "plugins": ["B.esp"]},
        )
        self.assertEqual(row.state, CoverageState.NEWER)

    def test_delta_direction_is_what_target_would_change(self):
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["C.esp"]},
            {"version": "1.0", "plugins": ["D.esp"]},
        )
        self.assertEqual(row.plugins_added, ("c.esp",))   # source has, target lacks
        self.assertEqual(row.plugins_removed, ("d.esp",))  # target has, source lacks


class PluginDeltaTextTest(unittest.TestCase):
    def _row(self, added=(), removed=()):
        from generate_coverage import CoverageRow
        row = CoverageRow({}, CoverageState.PLUGINS, "1.0", "1.0", None)
        row.plugins_added = tuple(added)
        row.plugins_removed = tuple(removed)
        return row

    def test_inline_up_to_three_names(self):
        from generate_coverage import _plugin_delta_text
        row = self._row(added=("a.esp",), removed=("b.esp",))
        self.assertEqual(_plugin_delta_text(row), "+a.esp −b.esp")

    def test_three_names_still_inline(self):
        from generate_coverage import _plugin_delta_text
        row = self._row(added=("a.esp", "b.esp"), removed=("c.esp",))
        self.assertEqual(_plugin_delta_text(row), "+a.esp +b.esp −c.esp")

    def test_four_or_more_collapse_to_counts(self):
        from generate_coverage import _plugin_delta_text
        row = self._row(added=("a.esp", "b.esp", "c.esp"), removed=("d.esp",))
        self.assertEqual(_plugin_delta_text(row), "+3 −1 plugins")

    def test_counts_omit_empty_side(self):
        from generate_coverage import _plugin_delta_text
        row = self._row(added=("a.esp", "b.esp", "c.esp", "d.esp"))
        self.assertEqual(_plugin_delta_text(row), "+4 plugins")


class RenderPluginsTest(unittest.TestCase):
    def setUp(self):
        self.source = [
            sep("S", 0),
            mod("PluginDrift", 1, "S", version="1.0", nexus_id=1,
                plugins=["A.esp", "B.esp"]),
            mod("Fine", 2, "S", version="1.0", nexus_id=2, plugins=["C.esp"]),
        ]
        self.target = [
            sep("T", 0),
            mod("PluginDrift", 1, "T", version="1.0", nexus_id=1,
                plugins=["A.esp"]),
            mod("Fine", 2, "T", version="1.0", nexus_id=2, plugins=["C.esp"]),
        ]
        self.rows = classify_source_mods(self.source, self.target)
        self.summary = compute_summary(self.rows)
        self.html = render_html(self.rows, self.summary, "S", "T")

    def test_row_class_and_glyphs_present(self):
        self.assertIn("mod-plugins", self.html)
        self.assertIn('.mod-plugins::before { content: "±";', self.html)
        self.assertIn('.stat-plugins::before { content: "± ";', self.html)

    def test_summary_badge(self):
        self.assertIn('id="stat-plugins"', self.html)
        self.assertIn("1 plugins", self.html)

    def test_inline_delta_and_tooltip(self):
        self.assertIn("+b.esp", self.html)
        self.assertIn('title="+b.esp"', self.html)

    def test_section_badge_counts_plugins(self):
        self.assertIn("1 plugins", self.html)
        self.assertNotIn("all present", self.html)

    def test_serve_recount_handles_plugins(self):
        served = render_html(self.rows, self.summary, "S", "T", serve=True)
        self.assertIn("c.plugins", served)
        self.assertIn("setStat('stat-plugins'", served)
        self.assertIn("'mod-plugins'", served)
```

3. Extend `CoveragePercentTest` with:

```python
    def test_plugins_counts_half(self):
        # 1 common + 1 plugins of 2 -> (1 + 0.5) / 2 = 75.
        self.assertEqual(coverage_percent(make_summary(2, plugins=1, common=1)), 75)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools; python -m unittest test_generate_coverage -v`
Expected: FAIL — `AttributeError: PLUGINS` (enum member missing) and import errors for `_plugin_delta_text`.

- [ ] **Step 3: Implement in `tools/generate_coverage.py`**

3a. Import `plugin_set` — extend the `modlist_utils` import list:

```python
from modlist_utils import (
    load_modlist,
    extract_mods,
    get_version,
    match_mods,
    compare_versions,
    plugin_set,
    resolve_output_path,
    NEXUS_URL,
)
```

3b. Enum — replace the `CoverageState` body:

```python
class CoverageState(Enum):
    ADD = "add"           # source mod not present in target (candidate to add)
    NEWER = "newer"       # source version > target version (actionable: pull in)
    DIFFERS = "differs"   # both known, differ, direction undeterminable (actionable)
    PLUGINS = "plugins"   # same/unknown version but plugin sets differ (actionable)
    COMMON = "common"     # same version+plugins, source OLDER (target ahead), or unknown
```

3c. `CoverageRow` — add two fields after `ignored`:

```python
    plugins_added: tuple = ()    # sorted: in source, not target (you'd add these)
    plugins_removed: tuple = ()  # sorted: in target, not source (you'd remove these)
```

3d. Classification — in `classify_source_mods`, replace the `if target_mod is None: ... else: ...` block with:

```python
        if target_mod is None:
            state = CoverageState.ADD
            target_version = ""
            src_plugins = tgt_plugins = frozenset()
        else:
            target_version = get_version(target_mod)
            src_plugins = plugin_set(mod)
            tgt_plugins = plugin_set(target_mod)
            plugins_differ = src_plugins != tgt_plugins

            if source_version == "Unknown" or target_version == "Unknown":
                # Versions can't speak; plugin drift is the only usable signal.
                state = (
                    CoverageState.PLUGINS if plugins_differ else CoverageState.COMMON
                )
            else:
                cmp = compare_versions(source_version, target_version)
                if cmp == 1:
                    # Source is newer — worth pulling into the target.
                    state = CoverageState.NEWER
                elif cmp is None:
                    # Direction undeterminable — keep actionable (might be newer).
                    state = CoverageState.DIFFERS
                elif cmp == 0 and plugins_differ:
                    # Right version, wrong plugin set — still work to do.
                    state = CoverageState.PLUGINS
                else:
                    # Equal with matching plugins, or source older (target ahead).
                    # Source-older stays Common even when plugins differ: the
                    # target is past the source, so matching an older source's
                    # plugin layout isn't a goal.
                    state = CoverageState.COMMON
```

and after `row.ignored = is_ignored(ignore, mod)` add:

```python
        if state == CoverageState.PLUGINS:
            row.plugins_added = tuple(sorted(src_plugins - tgt_plugins))
            row.plugins_removed = tuple(sorted(tgt_plugins - src_plugins))
```

3e. Tooltip text update — replace the `COVERED_TOOLTIP` value:

```python
COVERED_TOOLTIP = (
    "Share of source mods the target already handles: "
    "have-it or ignored count full, different-version or different-plugins "
    "counts half, missing counts zero."
)
```

3f. `ACTIONABLE_STATES` — append the plugins entry:

```python
ACTIONABLE_STATES = [
    (CoverageState.ADD, "add"),
    (CoverageState.NEWER, "newer"),
    (CoverageState.DIFFERS, "differs"),
    (CoverageState.PLUGINS, "plugins"),
]
```

3g. `_STATE_CSS` — add:

```python
    CoverageState.PLUGINS: "mod-plugins",
```

3h. CSS — in the `CSS` string, after the `.stat-differs { ... }` line add:

```css
.stat-plugins { background: #241a3a; color: #a78bfa; }
```

after the `.stat-differs::before { content: "≠ "; }` line add:

```css
.stat-plugins::before { content: "± "; }
```

after the `.mod-differs .ver { color: #fbbf24; }` line add:

```css
.mod-plugins { background: #221636; border-left-color: #a78bfa; }
.mod-plugins .ver { color: #a78bfa; }
```

and after the `.mod-differs::before { ... }` glyph rule add:

```css
.mod-plugins::before { content: "±"; color: #a78bfa; }
```

3i. Delta helpers — add above `_render_mod_row`:

```python
# Inline plugin-delta cap: up to this many names render in the row; larger
# deltas collapse to counts, with the full list always in the tooltip.
_DELTA_INLINE_LIMIT = 3


def _plugin_delta_parts(row):
    """['+x.esp', ...] + ['−y.esp', ...] — the change the target would make
    to match the source (add what it lacks, remove what the source dropped)."""
    return [f"+{p}" for p in row.plugins_added] + [
        f"−{p}" for p in row.plugins_removed
    ]


def _plugin_delta_text(row):
    """Compact inline delta: names up to the cap, then counts ('+4 −2 plugins')."""
    parts = _plugin_delta_parts(row)
    if len(parts) <= _DELTA_INLINE_LIMIT:
        return " ".join(parts)
    counts = []
    if row.plugins_added:
        counts.append(f"+{len(row.plugins_added)}")
    if row.plugins_removed:
        counts.append(f"−{len(row.plugins_removed)}")
    return " ".join(counts) + " plugins"
```

3j. `_version_html` — add a PLUGINS branch just before the final `# ADD and COMMON` comment/return. (`_version_html` escapes each piece itself — `src`/`tgt` are already `_esc`-ed — so the delta is escaped here too:)

```python
    if state == CoverageState.PLUGINS:
        # Version is right (or unknowable); the actionable bit is the delta.
        delta = _esc(_plugin_delta_text(row))
        return f"{src} {delta}".strip() if src else delta
```

3k. `_render_mod_row` — replace its first three lines (`cls = ...` through `ver_html = ...`) with:

```python
    cls = "mod-ignored" if row.ignored else _STATE_CSS[row.state]
    ver = _version_html(row)
    tips = []
    if row.state == CoverageState.PLUGINS:
        tips.append(" ".join(_plugin_delta_parts(row)))
    tip_attr = f' title="{_esc(" | ".join(tips))}"' if tips else ""
    ver_html = f'<span class="ver"{tip_attr}>{ver}</span>' if ver else ""
```

3l. Summary badge — in `render_html`, after the `stat-differs` span line add:

```python
    parts.append(f'<span id="stat-plugins" class="stat stat-plugins">{counts[CoverageState.PLUGINS]} plugins</span>')
```

3m. `% covered` — in `coverage_percent`, replace the `covered = (...)` expression:

```python
    covered = (
        counts[CoverageState.COMMON]
        + summary["ignored"]
        + 0.5
        * (
            counts[CoverageState.NEWER]
            + counts[CoverageState.DIFFERS]
            + counts[CoverageState.PLUGINS]
        )
    )
```

3n. Serve-mode recount JS — replace the entire serve `<script>` payload string (the argument of the second `parts.append(...)` inside `if serve:`) with:

```python
        parts.append(
            "(function(){"
            "function setStat(id,t){var e=document.getElementById(id);if(e)e.textContent=t;}"
            "function recount(){"
            "var c={add:0,newer:0,differs:0,plugins:0,common:0,ignored:0};"
            "document.querySelectorAll('.mod-row').forEach(function(r){"
            "if(r.classList.contains('mod-ignored'))c.ignored++;"
            "else if(r.classList.contains('mod-add'))c.add++;"
            "else if(r.classList.contains('mod-newer'))c.newer++;"
            "else if(r.classList.contains('mod-differs'))c.differs++;"
            "else if(r.classList.contains('mod-plugins'))c.plugins++;"
            "else if(r.classList.contains('mod-common'))c.common++;});"
            "setStat('stat-add',c.add+' to add');setStat('stat-newer',c.newer+' newer');"
            "setStat('stat-differs',c.differs+' differs');"
            "setStat('stat-plugins',c.plugins+' plugins');"
            "setStat('stat-ignored',c.ignored+' ignored');"
            "setStat('stat-common',c.common+' common');"
            "var tot=c.add+c.newer+c.differs+c.plugins+c.common+c.ignored;"
            "var pct=tot?Math.floor(100*(c.common+c.ignored+0.5*(c.newer+c.differs+c.plugins))/tot):null;"
            "setStat('stat-covered',pct===null?'\\u2014 covered':pct+'% covered');"
            "document.querySelectorAll('.section').forEach(function(s){"
            "var a=0,n=0,d=0,p=0;"
            "s.querySelectorAll('.mod-row').forEach(function(r){"
            "if(r.classList.contains('mod-add'))a++;"
            "else if(r.classList.contains('mod-newer'))n++;"
            "else if(r.classList.contains('mod-differs'))d++;"
            "else if(r.classList.contains('mod-plugins'))p++;});"
            "var act=a+n+d+p;s.classList.toggle('collapsed',act===0);"
            "var b=s.querySelector('.badge');if(b)"
            "b.textContent=(a?[a+' add']:[]).concat(n?[n+' newer']:[],d?[d+' differs']:[],p?[p+' plugins']:[]).join(' \\u00b7 ')||'all present';});}"
            "function setIgnored(row,on){var sc=row.getAttribute('data-state');"
            "row.classList.remove('mod-add','mod-newer','mod-differs','mod-plugins','mod-common','mod-ignored');"
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
            "if(!d.ok)return;setIgnored(row,!on);recount();refilter();}).catch(function(){});});"
            "})();"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools; python -m unittest test_generate_coverage test_coverage_ignore test_coverage_server -v`
Expected: all PASS (serve tests unaffected; ignore tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat: add Plugins coverage state for same-version plugin-set drift"
```

---

### Task 3: Base change set + report filtering

**Goal:** `compute_base_changes(base, source)` classifies what changed in the base update, and `classify_source_mods(..., base_changes=...)` filters the report to those mods, tagging each row with a human-readable `base_note`.

**Files:**
- Modify: `tools/generate_coverage.py`
- Test: `tools/test_generate_coverage.py`

**Acceptance Criteria:**
- [ ] `compute_base_changes` returns `(changed, removed_base_mods)`: `changed` keys are `id(source_mod)` for base-added, version-changed (both known, `compare_versions != 0`, downgrades included), and plugin-set-changed mods; values are notes (`"New in base update"`, `"Base: 1.2 → 1.5"`, `"Base plugins: +a.esp"`, combined with `"; "`).
- [ ] Unknown-version pairs count as version-unchanged (but still flag on plugin change).
- [ ] With `base_changes` passed, `classify_source_mods` drops unlisted mods entirely; sections with no kept rows are absent from the result; `row.base_note` carries the note.
- [ ] Without `base_changes`, behavior is unchanged (`base_note == ""`).

**Verify:** `cd tools; python -m unittest test_generate_coverage -v` → all pass, including `ComputeBaseChangesTest`, `BaseFilterTest`.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Add to `tools/test_generate_coverage.py`:

```python
class ComputeBaseChangesTest(unittest.TestCase):
    def _changes(self, base, source):
        from generate_coverage import compute_base_changes
        return compute_base_changes(base, source)

    def test_added_in_base(self):
        base = [sep("S", 0)]
        source = [sep("S", 0), mod("NewMod", 1, "S", version="1.0", nexus_id=1)]
        changed, removed = self._changes(base, source)
        self.assertEqual(len(changed), 1)
        self.assertEqual(list(changed.values()), ["New in base update"])
        self.assertEqual(removed, [])

    def test_version_change_flagged_with_note(self):
        base = [sep("S", 0), mod("Upd", 1, "S", version="1.2", nexus_id=1)]
        source = [sep("S", 0), mod("Upd", 1, "S", version="1.5", nexus_id=1)]
        changed, _ = self._changes(base, source)
        self.assertEqual(list(changed.values()), ["Base: 1.2 → 1.5"])

    def test_downgrade_counts_as_changed(self):
        base = [sep("S", 0), mod("Down", 1, "S", version="2.0", nexus_id=1)]
        source = [sep("S", 0), mod("Down", 1, "S", version="1.0", nexus_id=1)]
        changed, _ = self._changes(base, source)
        self.assertEqual(len(changed), 1)

    def test_unchanged_not_flagged(self):
        base = [sep("S", 0), mod("Same", 1, "S", version="1.0", nexus_id=1,
                                 plugins=["A.esp"])]
        source = [sep("S", 0), mod("Same", 1, "S", version="1.0", nexus_id=1,
                                   plugins=["A.esp"])]
        changed, removed = self._changes(base, source)
        self.assertEqual(changed, {})
        self.assertEqual(removed, [])

    def test_unknown_version_pair_is_version_unchanged(self):
        # Per the classify_updates convention: either side Unknown -> no version change.
        base = [sep("S", 0), mod("NoVer", 1, "S", nexus_id=1)]
        source = [sep("S", 0), mod("NoVer", 1, "S", version="2.0", nexus_id=1)]
        changed, _ = self._changes(base, source)
        self.assertEqual(changed, {})

    def test_plugin_change_flagged_even_at_same_version(self):
        base = [sep("S", 0), mod("Plug", 1, "S", version="1.0", nexus_id=1,
                                 plugins=["A.esp"])]
        source = [sep("S", 0), mod("Plug", 1, "S", version="1.0", nexus_id=1,
                                   plugins=["A.esp", "B.esp"])]
        changed, _ = self._changes(base, source)
        self.assertEqual(list(changed.values()), ["Base plugins: +b.esp"])

    def test_version_and_plugin_notes_combined(self):
        base = [sep("S", 0), mod("Both", 1, "S", version="1.0", nexus_id=1,
                                 plugins=["A.esp"])]
        source = [sep("S", 0), mod("Both", 1, "S", version="2.0", nexus_id=1,
                                   plugins=["B.esp"])]
        changed, _ = self._changes(base, source)
        self.assertEqual(
            list(changed.values()),
            ["Base: 1.0 → 2.0; Base plugins: +b.esp −a.esp"],
        )

    def test_removed_in_base_returned(self):
        base = [sep("S", 0), mod("Gone", 1, "S", version="1.0", nexus_id=1)]
        source = [sep("S", 0)]
        changed, removed = self._changes(base, source)
        self.assertEqual(changed, {})
        self.assertEqual([m["modName"] for m in removed], ["Gone"])


class BaseFilterTest(unittest.TestCase):
    def setUp(self):
        from generate_coverage import compute_base_changes
        self.base = [
            sep("Combat", 0),
            mod("Updated", 1, "Combat", version="1.0", nexus_id=1),
            mod("Stable", 2, "Combat", version="1.0", nexus_id=2),
            sep("Quiet", 3),
            mod("AlsoStable", 4, "Quiet", version="1.0", nexus_id=3),
        ]
        self.source = [
            sep("Combat", 0),
            mod("Updated", 1, "Combat", version="2.0", nexus_id=1),
            mod("Stable", 2, "Combat", version="1.0", nexus_id=2),
            sep("Quiet", 3),
            mod("AlsoStable", 4, "Quiet", version="1.0", nexus_id=3),
        ]
        self.target = [sep("T", 0)]
        self.base_changes, _ = compute_base_changes(self.base, self.source)

    def test_only_changed_mods_kept(self):
        rows = classify_source_mods(
            self.source, self.target, base_changes=self.base_changes
        )
        names = [r.mod["modName"] for rs in rows.values() for r in rs]
        self.assertEqual(names, ["Updated"])

    def test_empty_sections_absent(self):
        rows = classify_source_mods(
            self.source, self.target, base_changes=self.base_changes
        )
        self.assertEqual(list(rows.keys()), ["Combat"])  # "Quiet" gone

    def test_base_note_set_on_rows(self):
        rows = classify_source_mods(
            self.source, self.target, base_changes=self.base_changes
        )
        row = rows["Combat"][0]
        self.assertEqual(row.base_note, "Base: 1.0 → 2.0")

    def test_no_base_changes_means_no_filter_and_empty_note(self):
        rows = classify_source_mods(self.source, self.target)
        names = [r.mod["modName"] for rs in rows.values() for r in rs]
        self.assertEqual(names, ["Updated", "Stable", "AlsoStable"])
        self.assertEqual(rows["Combat"][0].base_note, "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools; python -m unittest test_generate_coverage -v`
Expected: FAIL — `ImportError: cannot import name 'compute_base_changes'`.

- [ ] **Step 3: Implement in `tools/generate_coverage.py`**

3a. `CoverageRow` — add after `plugins_removed`:

```python
    base_note: str = ""          # --base mode: what changed in the base (tooltip)
```

3b. Add after `map_sections_to_majors` (before `classify_source_mods`):

```python
def compute_base_changes(base_data, source_data, min_confidence=0.80):
    """Diff the old base list against the source (the new base).

    Returns (changed, removed_base_mods):

    - changed: dict keyed by id(source_mod), covering every source mod that is
      new or changed since the base — added mods, version changes (both versions
      known and compare_versions != 0; downgrades included), and plugin-set
      changes (which the version string can't see, and which work even when a
      version is Unknown). The value is a human-readable note about what changed
      ("New in base update", "Base: 1.2 → 1.5", "Base plugins: +a.esp"),
      rendered as a row tooltip.
    - removed_base_mods: base mods with no source match — candidates for the
      synthetic Removed section (the caller filters to target-present).
    """
    base_mods = extract_mods(base_data)
    source_mods = extract_mods(source_data)
    matched, added, removed = match_mods(base_mods, source_mods, min_confidence)

    changed = {}
    for src_mod in added:
        changed[id(src_mod)] = "New in base update"
    for base_mod, src_mod in matched:
        old_ver = get_version(base_mod)
        new_ver = get_version(src_mod)
        notes = []
        if (
            old_ver != "Unknown"
            and new_ver != "Unknown"
            and compare_versions(old_ver, new_ver) != 0
        ):
            notes.append(f"Base: {old_ver} → {new_ver}")
        old_plugins = plugin_set(base_mod)
        new_plugins = plugin_set(src_mod)
        if old_plugins != new_plugins:
            delta = [f"+{p}" for p in sorted(new_plugins - old_plugins)]
            delta += [f"−{p}" for p in sorted(old_plugins - new_plugins)]
            notes.append("Base plugins: " + " ".join(delta))
        if notes:
            changed[id(src_mod)] = "; ".join(notes)
    return changed, removed
```

3c. `classify_source_mods` — new signature:

```python
def classify_source_mods(source_data, target_data, min_confidence=0.80, ignore=None,
                         base_changes=None):
```

Append to its docstring:

```
    base_changes (from compute_base_changes) restricts the report to mods that
    changed in the base update: source mods not in it are dropped entirely (their
    sections vanish when emptied), and kept rows carry the note in base_note.
```

At the top of the `for mod in source_mods:` loop body (before the `section = ...` line) add:

```python
        if base_changes is not None and id(mod) not in base_changes:
            continue  # unchanged in the base update — not part of this report
```

After `row.ignored = is_ignored(ignore, mod)` (and the Task 2 plugins-delta block) add:

```python
        if base_changes:
            row.base_note = base_changes.get(id(mod), "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools; python -m unittest test_generate_coverage -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat: compute base change set and filter coverage rows to it"
```

---

### Task 4: The Removed state

**Goal:** Base-removed mods the target still carries render in a synthetic "Removed in base update" section as red `−` rows showing the target's version, actionable and ignorable, weighing zero in `% covered`.

**Files:**
- Modify: `tools/generate_coverage.py`
- Test: `tools/test_generate_coverage.py`

**Acceptance Criteria:**
- [ ] `build_removed_rows(removed_base_mods, target_data, ...)` yields REMOVED rows only for target-present mods, with the base mod's name/Nexus id and the target's version; `ignore` applies.
- [ ] REMOVED is actionable (in `ACTIONABLE_STATES`, section badges, serve JS recount) and weighs 0 in `% covered` (in total, not in covered).
- [ ] Version cell shows the target's version; red styling + `−` glyph CSS present.

**Verify:** `cd tools; python -m unittest test_generate_coverage -v` → all pass, including `RemovedStateTest`, `RenderRemovedTest`.

**Steps:**

- [ ] **Step 1: Write the failing tests**

1. Update `make_summary` again to add `removed`:

```python
def make_summary(total, add=0, newer=0, differs=0, plugins=0, removed=0, common=0,
                 ignored=0):
    """Build a summary dict shaped like compute_summary's output."""
    return {
        "total": total,
        "ignored": ignored,
        "counts": {
            CoverageState.ADD: add,
            CoverageState.NEWER: newer,
            CoverageState.DIFFERS: differs,
            CoverageState.PLUGINS: plugins,
            CoverageState.REMOVED: removed,
            CoverageState.COMMON: common,
        },
    }
```

2. Add test classes:

```python
class RemovedStateTest(unittest.TestCase):
    def setUp(self):
        # Base mods that vanished from the new base (as returned by
        # compute_base_changes' removed list).
        self.removed_base_mods = [
            mod("StillHave", 0, "S", version="1.0", nexus_id=10),
            mod("NeverHad", 1, "S", version="1.0", nexus_id=11),
        ]
        self.target = [
            sep("T", 0),
            mod("StillHave", 1, "T", version="1.2", nexus_id=10),
        ]

    def test_only_target_present_mods_produce_rows(self):
        from generate_coverage import build_removed_rows
        rows = build_removed_rows(self.removed_base_mods, self.target)
        self.assertEqual([r.mod["modName"] for r in rows], ["StillHave"])

    def test_row_shape(self):
        from generate_coverage import build_removed_rows
        row = build_removed_rows(self.removed_base_mods, self.target)[0]
        self.assertEqual(row.state, CoverageState.REMOVED)
        self.assertEqual(row.nexus_id, 10)
        self.assertEqual(row.target_version, "1.2")
        self.assertEqual(row.target_name, "StillHave")

    def test_ignore_applies(self):
        from coverage_ignore import IgnoreSet
        from generate_coverage import build_removed_rows
        rows = build_removed_rows(
            self.removed_base_mods, self.target, ignore=IgnoreSet(["StillHave"])
        )
        self.assertTrue(rows[0].ignored)

    def test_empty_input_empty_output(self):
        from generate_coverage import build_removed_rows
        self.assertEqual(build_removed_rows([], self.target), [])


class RenderRemovedTest(unittest.TestCase):
    def setUp(self):
        from generate_coverage import build_removed_rows, REMOVED_SECTION
        removed_base_mods = [mod("GoneMod", 0, "S", version="1.0", nexus_id=10)]
        target = [sep("T", 0), mod("GoneMod", 1, "T", version="1.2", nexus_id=10)]
        rows = build_removed_rows(removed_base_mods, target)
        self.rows_by_section = {REMOVED_SECTION: rows}
        self.summary = compute_summary(self.rows_by_section)
        self.html = render_html(self.rows_by_section, self.summary, "S", "T")

    def test_removed_row_class_and_glyphs(self):
        self.assertIn("mod-removed", self.html)
        self.assertIn('.mod-removed::before { content: "−";', self.html)
        self.assertIn('.stat-removed::before { content: "− ";', self.html)

    def test_section_present_with_badge(self):
        self.assertIn("Removed in base update", self.html)
        self.assertIn("1 removed", self.html)

    def test_version_cell_shows_target_version(self):
        self.assertIn('<span class="ver">1.2</span>', self.html)

    def test_serve_recount_handles_removed(self):
        served = render_html(self.rows_by_section, self.summary, "S", "T", serve=True)
        self.assertIn("c.removed", served)
        self.assertIn("'mod-removed'", served)
```

3. Extend `CoveragePercentTest`:

```python
    def test_removed_counts_zero(self):
        # 1 common + 1 removed of 2 -> (1 + 0) / 2 = 50.
        self.assertEqual(coverage_percent(make_summary(2, removed=1, common=1)), 50)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools; python -m unittest test_generate_coverage -v`
Expected: FAIL — `AttributeError: REMOVED`.

- [ ] **Step 3: Implement in `tools/generate_coverage.py`**

3a. Enum — add after `PLUGINS`:

```python
    REMOVED = "removed"   # (--base only) removed in the base update, still in target
```

3b. Constant — add right below the `CoverageState` class:

```python
# Synthetic section holding REMOVED rows, appended after all source sections.
REMOVED_SECTION = "Removed in base update"
```

3c. Import `is_ignored` is already imported at module top — no change needed.

3d. Add after `compute_base_changes`:

```python
def build_removed_rows(removed_base_mods, target_data, min_confidence=0.80,
                       ignore=None):
    """Rows for mods removed in the base update that the target still carries.

    removed_base_mods are the base mods compute_base_changes found no source
    match for. Each is matched against the target; only target-present mods
    produce rows (a mod neither list has needs no action). The row keeps the
    base mod (name + Nexus link) and shows the target's version — that is
    what you'd be deleting.
    """
    target_mods = extract_mods(target_data)
    matched, _added, _removed = match_mods(
        removed_base_mods, target_mods, min_confidence
    )
    rows = []
    for base_mod, target_mod in matched:
        raw_id = base_mod.get("id")
        nexus_id = raw_id if isinstance(raw_id, int) else None
        row = CoverageRow(
            base_mod,
            CoverageState.REMOVED,
            get_version(base_mod),
            get_version(target_mod),
            nexus_id,
            target_mod.get("modName", ""),
        )
        row.ignored = is_ignored(ignore, base_mod)
        rows.append(row)
    return rows
```

3e. `ACTIONABLE_STATES` — append:

```python
    (CoverageState.REMOVED, "removed"),
```

3f. `_STATE_CSS` — add:

```python
    CoverageState.REMOVED: "mod-removed",
```

3g. CSS — after the `.stat-plugins { ... }` line add:

```css
.stat-removed { background: #2a0d12; color: #f87171; }
```

after `.stat-plugins::before { content: "± "; }` add:

```css
.stat-removed::before { content: "− "; }
```

after `.mod-plugins .ver { color: #a78bfa; }` add:

```css
.mod-removed { background: #2a0d12; border-left-color: #f87171; color: #f87171; }
```

after `.mod-plugins::before { ... }` add:

```css
.mod-removed::before { content: "−"; color: #f87171; }
```

3h. `_version_html` — add a REMOVED branch above the PLUGINS branch:

```python
    if state == CoverageState.REMOVED:
        # The target still carries it; show the version you'd be deleting.
        return tgt
```

3i. Update `COVERED_TOOLTIP` (final wording):

```python
COVERED_TOOLTIP = (
    "Share of source mods the target already handles: "
    "have-it or ignored count full, different-version or different-plugins "
    "counts half, missing or base-removed count zero."
)
```

3j. Serve JS — apply these line-level replacements inside the serve script string from Task 2:

- `"var c={add:0,newer:0,differs:0,plugins:0,common:0,ignored:0};"` → `"var c={add:0,newer:0,differs:0,plugins:0,removed:0,common:0,ignored:0};"`
- after the `mod-plugins` count line insert: `"else if(r.classList.contains('mod-removed'))c.removed++;"`
- after `"setStat('stat-plugins',c.plugins+' plugins');"` insert: `"setStat('stat-removed',c.removed+' removed');"`
- `"var tot=c.add+c.newer+c.differs+c.plugins+c.common+c.ignored;"` → `"var tot=c.add+c.newer+c.differs+c.plugins+c.removed+c.common+c.ignored;"` (the `pct` numerator is unchanged — removed weighs zero)
- `"var a=0,n=0,d=0,p=0;"` → `"var a=0,n=0,d=0,p=0,rm=0;"`
- after the section-loop `mod-plugins` count line insert: `"else if(r.classList.contains('mod-removed'))rm++;"`
- `"var act=a+n+d+p;s.classList.toggle('collapsed',act===0);"` → `"var act=a+n+d+p+rm;s.classList.toggle('collapsed',act===0);"`
- badge concat: `...concat(n?[n+' newer']:[],d?[d+' differs']:[],p?[p+' plugins']:[])...` → `...concat(n?[n+' newer']:[],d?[d+' differs']:[],p?[p+' plugins']:[],rm?[rm+' removed']:[])...`
- `"row.classList.remove('mod-add','mod-newer','mod-differs','mod-plugins','mod-common','mod-ignored');"` → `"row.classList.remove('mod-add','mod-newer','mod-differs','mod-plugins','mod-removed','mod-common','mod-ignored');"`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools; python -m unittest test_generate_coverage -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat: add Removed state for base-removed mods the target still carries"
```

---

### Task 5: `--base` CLI wiring, base-mode header, rebase naming

**Goal:** `generate_coverage.py --base OLD.json` produces the filtered report with a "Base Update Coverage" header, the removed-badge, base-note tooltips, and `<source> (from <base>).rebase.html` auto-naming.

**Files:**
- Modify: `tools/generate_coverage.py`
- Test: `tools/test_generate_coverage.py`

**Acceptance Criteria:**
- [ ] `build_report(...)` assembles rows (with optional base data) and is used by `main()`.
- [ ] `render_html(..., base_name=...)`: title/h1 "Base Update Coverage", lists line `Base update: <base> → <source> · applied to: <target>`, `stat-removed` badge rendered only in base mode.
- [ ] Rows with `base_note` get it in the version-cell tooltip (joined with the plugin delta when both).
- [ ] With `-o <dir>` and `--base`, output is `<dir>/<target>/<source> (from <base>).rebase.html`; without `--base`, naming unchanged.

**Verify:** `cd tools; python -m unittest test_generate_coverage -v` → all pass, including `RenderBaseModeTest`, `BuildReportTest`.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Add to `tools/test_generate_coverage.py`:

```python
class BuildReportTest(unittest.TestCase):
    def setUp(self):
        from generate_coverage import REMOVED_SECTION
        self.REMOVED_SECTION = REMOVED_SECTION
        self.base = [
            sep("Combat", 0),
            mod("Updated", 1, "Combat", version="1.0", nexus_id=1),
            mod("Stable", 2, "Combat", version="1.0", nexus_id=2),
            mod("GoneMod", 3, "Combat", version="1.0", nexus_id=3),
        ]
        self.source = [
            sep("Combat", 0),
            mod("Updated", 1, "Combat", version="2.0", nexus_id=1),
            mod("Stable", 2, "Combat", version="1.0", nexus_id=2),
        ]
        self.target = [
            sep("T", 0),
            mod("GoneMod", 1, "T", version="1.0", nexus_id=3),
        ]

    def test_without_base_matches_classify(self):
        from generate_coverage import build_report
        rows = build_report(self.source, self.target, 0.80, None)
        names = [r.mod["modName"] for rs in rows.values() for r in rs]
        self.assertEqual(names, ["Updated", "Stable"])

    def test_with_base_filters_and_appends_removed(self):
        from generate_coverage import build_report
        rows = build_report(self.source, self.target, 0.80, None,
                            base_data=self.base)
        self.assertEqual(list(rows.keys()), ["Combat", self.REMOVED_SECTION])
        self.assertEqual(
            [r.mod["modName"] for r in rows["Combat"]], ["Updated"]
        )
        self.assertEqual(
            [r.mod["modName"] for r in rows[self.REMOVED_SECTION]], ["GoneMod"]
        )

    def test_removed_section_absent_when_nothing_removed(self):
        from generate_coverage import build_report
        source_with_gone = self.source + [
            mod("GoneMod", 3, "Combat", version="1.0", nexus_id=3)
        ]
        rows = build_report(source_with_gone, self.target, 0.80, None,
                            base_data=self.base)
        self.assertNotIn(self.REMOVED_SECTION, rows)

    def test_replaced_mod_not_double_listed(self):
        # Base removed "Mod X" (page 30); the new base ships a renamed
        # successor "ModRebornX" (page 31) whose plugins claim the target's
        # "Mod X" (plugin-overlap match). Without the guard the same target
        # mod would get a Removed row (via its page-30 match to the removed
        # base mod) AND the successor's update row. The source claim wins:
        # no Removed section, just the successor row.
        from generate_coverage import build_report
        base = [
            sep("Combat", 0),
            mod("Mod X", 1, "Combat", version="1.0", nexus_id=30),
        ]
        source = [
            sep("Combat", 0),
            mod("ModRebornX", 1, "Combat", version="2.0", nexus_id=31,
                plugins=["x.esp"]),
        ]
        target = [
            sep("T", 0),
            mod("Mod X", 1, "T", version="1.0", nexus_id=30,
                plugins=["x.esp"]),
        ]
        rows = build_report(source, target, 0.80, None, base_data=base)
        self.assertNotIn(self.REMOVED_SECTION, rows)
        names = [r.mod["modName"] for rs in rows.values() for r in rs]
        self.assertEqual(names, ["ModRebornX"])


class RenderBaseModeTest(unittest.TestCase):
    def setUp(self):
        source = [sep("S", 0),
                  mod("NewMod", 1, "S", version="1.0", nexus_id=1)]
        self.rows = classify_source_mods(source, [sep("T", 0)])
        self.summary = compute_summary(self.rows)
        self.plain = render_html(self.rows, self.summary, "NewBase", "MyList")
        self.based = render_html(
            self.rows, self.summary, "NewBase", "MyList", base_name="OldBase"
        )

    def test_title_and_h1_switch(self):
        self.assertIn("<title>Base Update Coverage</title>", self.based)
        self.assertIn("<h1>Base Update Coverage</h1>", self.based)
        self.assertIn("<title>Modlist Coverage</title>", self.plain)
        self.assertIn("<h1>Modlist Coverage</h1>", self.plain)

    def test_lists_line_names_all_three(self):
        self.assertIn("Base update:", self.based)
        self.assertIn("OldBase", self.based)
        self.assertIn("applied to:", self.based)
        self.assertNotIn("Base update:", self.plain)

    def test_stat_removed_badge_only_in_base_mode(self):
        self.assertIn('id="stat-removed"', self.based)
        self.assertNotIn('id="stat-removed"', self.plain)

    def test_base_note_tooltip_rendered(self):
        row = next(iter(self.rows.values()))[0]
        row.base_note = "Base: 1.0 → 2.0"
        html = render_html(self.rows, self.summary, "NewBase", "MyList",
                           base_name="OldBase")
        self.assertIn('title="Base: 1.0 → 2.0"', html)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools; python -m unittest test_generate_coverage -v`
Expected: FAIL — `ImportError: cannot import name 'build_report'` / `TypeError: render_html() got an unexpected keyword argument 'base_name'`.

- [ ] **Step 3: Implement in `tools/generate_coverage.py`**

3a. **(Amended after Task 4 code review.)** A base-removed mod can fuzzy-match a target mod that a *still-present* source mod also claims (base replaced a mod with a successor on a different Nexus page). Without a guard the same physical target mod gets two contradictory rows — REMOVED ("delete") and NEWER/DIFFERS ("update"). The source row wins: target mods already matched to any source mod are excluded from Removed candidates.

First, extend `build_removed_rows` (from Task 4) with an `exclude_target_ids` parameter — new signature and one guard line inside the loop:

```python
def build_removed_rows(removed_base_mods, target_data, min_confidence=0.80,
                       ignore=None, exclude_target_ids=frozenset()):
```

Append to its docstring:

```
    exclude_target_ids (id()s of target mods) suppresses rows for target mods
    already claimed by a still-present source mod — the source row's advice
    (update/common) wins over a contradictory "removed" row.
```

and at the top of the `for base_mod, target_mod in matched:` loop body add:

```python
        if id(target_mod) in exclude_target_ids:
            continue  # a still-present source mod claims this target mod
```

Then add after `build_removed_rows`:

```python
def build_report(source_data, target_data, min_confidence, ignore, base_data=None):
    """Assemble the full rows_by_section for a report.

    Without base_data this is exactly classify_source_mods. With it, the report
    is filtered to the base change set and a synthetic REMOVED_SECTION is
    appended for base-removed mods the target still carries (skipping target
    mods a still-present source mod already claims). Shared by the CLI and the
    serve-mode renderer so both build identical reports.
    """
    base_changes = None
    removed_rows = []
    if base_data is not None:
        base_changes, removed_base_mods = compute_base_changes(
            base_data, source_data, min_confidence
        )
        if removed_base_mods:
            # Target mods matched to any still-present source mod are not
            # "removed" — the source row's advice wins (see build_removed_rows).
            matched, _added, _removed = match_mods(
                extract_mods(source_data), extract_mods(target_data), min_confidence
            )
            claimed = {id(t) for _s, t in matched}
            removed_rows = build_removed_rows(
                removed_base_mods, target_data, min_confidence, ignore,
                exclude_target_ids=claimed,
            )
    rows_by_section = classify_source_mods(
        source_data, target_data, min_confidence, ignore, base_changes
    )
    if removed_rows:
        # REMOVED_SECTION is a synthetic key; a real source separator with the
        # same name would merge into it (accepted — vanishingly unlikely).
        rows_by_section[REMOVED_SECTION] = removed_rows
    return rows_by_section
```

(`match_mods` and `extract_mods` are already imported in generate_coverage.py.) Also fix the `coverage_percent` docstring, which drifted from the code (Task 2/4 review note) — replace its body text so it reads:

```python
    """Floor percent of the source the target already 'handles'.

    Each mod is weighted by how done it is: common/ignored count full (1.0),
    newer/differs/plugins (present but at a different version or with a
    different plugin set) count half (0.5), and add/removed count zero.
    Returns None when there are no mods, so the header can render a dash
    instead of dividing by zero.
    """
```

3b. `_render_mod_row` — extend the `tips` block from Task 2:

```python
    tips = []
    if row.state == CoverageState.PLUGINS:
        tips.append(" ".join(_plugin_delta_parts(row)))
    if row.base_note:
        tips.append(row.base_note)
    tip_attr = f' title="{_esc(" | ".join(tips))}"' if tips else ""
```

3c. `render_html` — new signature:

```python
def render_html(rows_by_section, summary, source_name, target_name,
                section_majors=None, serve=False, base_name=None):
```

Inside, replace the hardcoded title line with:

```python
    title = "Base Update Coverage" if base_name else "Modlist Coverage"
    parts.append(f"<title>{title}</title>")
```

replace `parts.append("<h1>Modlist Coverage</h1>")` with:

```python
    parts.append(f"<h1>{title}</h1>")
```

replace the `lists` line append with:

```python
    if base_name:
        parts.append(
            f'<div class="lists">Base update: <span>{_esc(base_name)}</span>'
            f' → <span>{_esc(source_name)}</span>'
            f' &nbsp;·&nbsp; applied to: <span>{_esc(target_name)}</span></div>'
        )
    else:
        parts.append(
            f'<div class="lists">Source: <span>{_esc(source_name)}</span>'
            f' &nbsp;vs&nbsp; Target: <span>{_esc(target_name)}</span></div>'
        )
```

and after the `stat-plugins` span (from Task 2) add:

```python
    if base_name:
        parts.append(f'<span id="stat-removed" class="stat stat-removed">{counts[CoverageState.REMOVED]} removed</span>')
```

(Note: the current code's h1 is rendered via `parts.append("<h1>Modlist Coverage</h1>")` — if the literal differs, adjust the h1 append accordingly; the requirement is that both title and h1 switch on `base_name`.)

3d. CLI — in `main()`, add the argument after `--min-confidence`:

```python
    parser.add_argument(
        "--base",
        help="Path to the OLD base modlist JSON. Filters the report to mods "
             "that changed between it and SOURCE (the new base), adds a "
             "'Removed in base update' section, and switches output naming to "
             "<source> (from <base>).rebase.html.",
    )
```

Replace the report-building body of `main()` (from `source_data = load_modlist(args.source)` through the `out_path = resolve_output_path(...)` line) with:

```python
    source_data = load_modlist(args.source)
    target_data = load_modlist(args.target)
    ignore = load_ignore(ignore_path)

    base_data = None
    base_name = None
    if args.base:
        base_data = load_modlist(args.base)
        base_name = os.path.splitext(os.path.basename(args.base))[0]

    rows_by_section = build_report(
        source_data, target_data, args.min_confidence, ignore, base_data
    )
    summary = compute_summary(rows_by_section)
    section_majors = map_sections_to_majors(source_data)

    source_name = os.path.splitext(os.path.basename(args.source))[0]
    target_name = os.path.splitext(os.path.basename(args.target))[0]

    html_output = render_html(
        rows_by_section, summary, source_name, target_name, section_majors,
        base_name=base_name,
    )

    if args.base:
        out_path = resolve_output_path(
            args.output, args.source, args.target, "rebase", "html",
            first_name=f"{source_name} (from {base_name})",
        )
    else:
        out_path = resolve_output_path(
            args.output, args.source, args.target, "coverage", "html"
        )
```

(The `--serve` branch earlier in `main()` is untouched here; Task 6 wires it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools; python -m unittest test_generate_coverage -v`
Expected: all PASS.

Also smoke-test the CLI end to end from the repo root:

```powershell
python tools/generate_coverage.py "lists/NORDIC SOULS v3.1.1.json" "lists/NORDIC SOULS v3.1.1 - PBR Edition 1.5.0.json" --base "lists/NORDIC SOULS v3.0.1.json" -o "$env:TEMP\rebase-smoke\"
```

Expected: prints `Coverage view written to ...\NORDIC SOULS v3.1.1 - PBR Edition 1.5.0\NORDIC SOULS v3.1.1 (from NORDIC SOULS v3.0.1).rebase.html` (delete the temp dir afterwards).

- [ ] **Step 5: Commit**

```bash
git add tools/generate_coverage.py tools/test_generate_coverage.py
git commit -m "feat: wire --base into the coverage CLI with rebase naming and base-mode header"
```

---

### Task 6: Serve mode with `--base`

**Goal:** `--serve --base OLD.json` serves the live base-update worklist; every GET re-renders from all three JSONs, so re-exporting the target refreshes the report.

**Files:**
- Modify: `tools/coverage_server.py`
- Modify: `tools/generate_coverage.py` (the `--serve` branch of `main()`)
- Test: `tools/test_coverage_server.py`

**Acceptance Criteria:**
- [ ] `serve` / `make_handler` / `_render_current` accept `base_path=None` and thread it through; base mode renders via `build_report` + `base_name`.
- [ ] Plain serve mode unchanged; existing server tests pass.
- [ ] GET in base mode returns "Base Update Coverage" HTML filtered to base changes, with the Removed section when applicable.

**Verify:** `cd tools; python -m unittest test_coverage_server -v` → all pass, including `ServerBaseModeTest`.

**Steps:**

- [ ] **Step 1: Write the failing test**

Add to `tools/test_coverage_server.py`:

```python
class ServerBaseModeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ignore_path = os.path.join(self.dir, ".coverage-ignore.txt")

        def write(name, items):
            path = os.path.join(self.dir, name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f)
            return path

        def m(name, version, mod_id):
            return {"type": "mod", "modName": name, "separatorName": "S",
                    "order": 1, "id": mod_id, "general": {"version": version}}

        s = {"type": "separator", "separatorName": "S", "order": 0}
        self.base = write("Base.json", [s, m("ChangedMod", "1.0", 1),
                                        m("StableMod", "1.0", 2),
                                        m("GoneMod", "1.0", 3)])
        self.source = write("Source.json", [s, m("ChangedMod", "2.0", 1),
                                            m("StableMod", "1.0", 2)])
        self.target = write("Target.json", [s, m("GoneMod", "1.0", 3)])

        handler = coverage_server.make_handler(
            self.source, self.target, 0.80, self.ignore_path, self.base
        )
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_get_renders_base_update_view(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/")
        body = c.getresponse().read().decode("utf-8")
        self.assertIn("Base Update Coverage", body)
        self.assertIn("ChangedMod", body)           # changed in base -> kept
        self.assertNotIn("StableMod", body)          # unchanged -> filtered out
        self.assertIn("Removed in base update", body)
        self.assertIn("GoneMod", body)               # removed in base, target has it
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools; python -m unittest test_coverage_server -v`
Expected: FAIL — `TypeError: make_handler() takes 4 positional arguments but 5 were given`.

- [ ] **Step 3: Implement**

3a. `tools/coverage_server.py` — replace the `generate_coverage` import with:

```python
from generate_coverage import (
    build_report,
    compute_summary,
    map_sections_to_majors,
    render_html,
)
```

Replace `_render_current` with:

```python
def _render_current(source_path, target_path, min_confidence, ignore_path,
                    base_path=None):
    """Render the coverage HTML from the current files, in serve mode."""
    source_data = load_modlist(source_path)
    target_data = load_modlist(target_path)
    ignore = coverage_ignore.load_ignore(ignore_path)
    base_data = load_modlist(base_path) if base_path else None
    base_name = (
        os.path.splitext(os.path.basename(base_path))[0] if base_path else None
    )
    rows_by_section = build_report(
        source_data, target_data, min_confidence, ignore, base_data
    )
    summary = compute_summary(rows_by_section)
    section_majors = map_sections_to_majors(source_data)
    source_name = os.path.splitext(os.path.basename(source_path))[0]
    target_name = os.path.splitext(os.path.basename(target_path))[0]
    return render_html(
        rows_by_section, summary, source_name, target_name, section_majors,
        serve=True, base_name=base_name,
    )
```

`make_handler` — new signature and the one call-site change inside `do_GET`:

```python
def make_handler(source_path, target_path, min_confidence, ignore_path,
                 base_path=None):
```

```python
                body = _render_current(
                    source_path, target_path, min_confidence, ignore_path, base_path
                ).encode("utf-8")
```

`serve` — new signature and handler construction:

```python
def serve(source_path, target_path, min_confidence, ignore_path, port=8000,
          open_browser=True, base_path=None):
```

```python
    handler = make_handler(
        source_path, target_path, min_confidence, ignore_path, base_path
    )
```

3b. `tools/generate_coverage.py` — in `main()`'s `--serve` branch, add the parameter:

```python
        serve(
            source_path=args.source,
            target_path=args.target,
            min_confidence=args.min_confidence,
            ignore_path=ignore_path,
            port=args.port,
            open_browser=not args.no_browser,
            base_path=args.base,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools; python -m unittest test_coverage_server test_generate_coverage -v`
Expected: all PASS (including the pre-existing `ServerIntegrationTest`, untouched by the default `base_path=None`).

- [ ] **Step 5: Commit**

```bash
git add tools/coverage_server.py tools/generate_coverage.py tools/test_coverage_server.py
git commit -m "feat: thread --base through the coverage serve mode"
```

---

### Task 7: `regenerate.py` learns the `rebase` type

**Goal:** `/regenerate <list>` re-runs existing `*.rebase.html` reports by parsing `<source> (from <base>)` back into three lists and re-invoking `generate_coverage.py --base`.

**Files:**
- Modify: `tools/regenerate.py`
- Test: `tools/test_regenerate.py`

**Acceptance Criteria:**
- [ ] `<source> (from <base>).rebase.html` plans a job with `script=generate_coverage.py`, parsed `source_list`/`base_list`, resolved paths; re-running reproduces the same output path (via the generator's own naming).
- [ ] Missing base JSON or malformed rebase stem → warning + skip (existing behavior style).
- [ ] The command line for a rebase job appends `--base <base_path>`; plain jobs unchanged.
- [ ] Progress/dry-run lines show `<source> (from <base>)` for rebase jobs.

**Verify:** `cd tools; python -m unittest test_regenerate -v` → all pass, including `RebasePlanTest`, `BuildCmdTest`.

**Steps:**

- [ ] **Step 1: Write the failing tests**

In `tools/test_regenerate.py`, extend the import:

```python
from regenerate import (
    plan_jobs,
    available_folders,
    run_jobs,
    default_max_workers,
    build_cmd,
    job_display,
    Job,
)
```

Add test classes:

```python
class RebasePlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.lists = os.path.join(self.root, "lists")
        self.output = os.path.join(self.root, "output")
        os.makedirs(self.lists)
        os.makedirs(self.output)

    def tearDown(self):
        self._tmp.cleanup()

    def _list(self, name):
        touch(os.path.join(self.lists, f"{name}.json"), "[]")

    def _report(self, folder, filename):
        touch(os.path.join(self.output, folder, filename), "<html>")

    def test_plans_rebase_job(self):
        self._list("PBR 1.5.0")
        self._list("NS 3.1.1")
        self._list("NS 3.0.1")
        self._report("PBR 1.5.0", "NS 3.1.1 (from NS 3.0.1).rebase.html")

        plan = plan_jobs(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(plan.warnings, [])
        self.assertEqual(len(plan.jobs), 1)
        job = plan.jobs[0]
        self.assertEqual(job.report_type, "rebase")
        self.assertEqual(job.script, "generate_coverage.py")
        self.assertEqual(job.source_list, "NS 3.1.1")
        self.assertEqual(job.base_list, "NS 3.0.1")
        self.assertEqual(job.source_path, os.path.join(self.lists, "NS 3.1.1.json"))
        self.assertEqual(job.base_path, os.path.join(self.lists, "NS 3.0.1.json"))

    def test_rebase_missing_base_warns_and_skips(self):
        self._list("PBR 1.5.0")
        self._list("NS 3.1.1")
        # base list NS 3.0.1 intentionally NOT created
        self._report("PBR 1.5.0", "NS 3.1.1 (from NS 3.0.1).rebase.html")

        plan = plan_jobs(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(plan.jobs, [])
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("NS 3.0.1", plan.warnings[0])

    def test_rebase_malformed_stem_warns_and_skips(self):
        self._list("PBR 1.5.0")
        self._report("PBR 1.5.0", "JustAName.rebase.html")

        plan = plan_jobs(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(plan.jobs, [])
        self.assertEqual(len(plan.warnings), 1)

    def test_parenthetical_source_names_parse_rightmost_from(self):
        # A source list whose own name contains " (from " must not confuse the
        # parse; the rightmost ' (from ' anchors the base.
        self._list("PBR 1.5.0")
        self._list("Weird (from scratch)")
        self._list("NS 3.0.1")
        self._report(
            "PBR 1.5.0", "Weird (from scratch) (from NS 3.0.1).rebase.html"
        )

        plan = plan_jobs(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(len(plan.jobs), 1)
        self.assertEqual(plan.jobs[0].source_list, "Weird (from scratch)")
        self.assertEqual(plan.jobs[0].base_list, "NS 3.0.1")


class BuildCmdTest(unittest.TestCase):
    def test_plain_job_has_no_base_flag(self):
        cmd = build_cmd(make_job("BottleRim 2.0.1"), "output")
        self.assertNotIn("--base", cmd)

    def test_rebase_job_appends_base(self):
        job = make_job("NS 3.1.1", report_type="rebase")
        job.base_list = "NS 3.0.1"
        job.base_path = "lists/NS 3.0.1.json"
        cmd = build_cmd(job, "output")
        self.assertEqual(cmd[-2:], ["--base", "lists/NS 3.0.1.json"])
        self.assertIn("-o", cmd)


class JobDisplayTest(unittest.TestCase):
    def test_plain_job_shows_source(self):
        self.assertEqual(job_display(make_job("BottleRim 2.0.1")), "BottleRim 2.0.1")

    def test_rebase_job_shows_from_base(self):
        job = make_job("NS 3.1.1", report_type="rebase")
        job.base_list = "NS 3.0.1"
        self.assertEqual(job_display(job), "NS 3.1.1 (from NS 3.0.1)")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools; python -m unittest test_regenerate -v`
Expected: FAIL — `ImportError: cannot import name 'build_cmd'`.

- [ ] **Step 3: Implement in `tools/regenerate.py`**

3a. Add `import re` to the imports, and extend `TYPE_SPECS`:

```python
TYPE_SPECS = {
    "coverage": ("generate_coverage.py", "html"),
    "diff": ("generate_diff.py", "html"),
    "changelog": ("generate_changelog.py", "md"),
    "rebase": ("generate_coverage.py", "html"),
}
```

3b. Add below `TYPE_SPECS`:

```python
# Rebase report stems decorate the source with the base list:
# "<source> (from <base>)". The rightmost " (from " anchors the split so a
# source name that itself contains the marker still parses.
REBASE_STEM_RE = re.compile(r"^(?P<source>.+) \(from (?P<base>.+)\)$")
```

3c. `Job` — append two defaulted fields:

```python
    base_list: str = ""
    base_path: str = ""
```

3d. In `plan_jobs`, after the extension check (`if ext != expected_ext: ... continue`) and before the `source_path = ...` line, add:

```python
        base_list = ""
        base_path = ""
        if type_label == "rebase":
            m = REBASE_STEM_RE.match(source_list)
            if not m:
                plan.warnings.append(
                    f"Skipping '{entry}': rebase name must look like "
                    f"'<source> (from <base>)'"
                )
                continue
            source_list = m.group("source")
            base_list = m.group("base")
            base_path = os.path.join(lists_dir, f"{base_list}.json")
            if not os.path.isfile(base_path):
                plan.warnings.append(
                    f"Skipping '{entry}': base list not found ({base_path})"
                )
                continue
```

(Regex greediness note for the reviewer: `(?P<source>.+)` is greedy, so it consumes as much as possible and the match anchors on the **rightmost** `" (from "` — exactly the behavior the parenthetical-source test pins down.)

and extend the `Job(...)` construction with:

```python
                base_list=base_list,
                base_path=base_path,
```

3e. Split command construction out of `run_job`:

```python
def build_cmd(job, output_root):
    """The generator command for a job. A trailing separator on -o guarantees
    resolve_output_path treats it as a directory and reproduces
    <output_root>/<target>/<file>.<type>.<ext>."""
    out_arg = os.path.join(output_root, "")
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, job.script),
        job.source_path,
        job.target_path,
        "-o",
        out_arg,
    ]
    if job.base_path:
        cmd += ["--base", job.base_path]
    return cmd


def run_job(job, output_root):
    """Run one generator via subprocess; return the CompletedProcess."""
    return subprocess.run(build_cmd(job, output_root), capture_output=True, text=True)
```

3f. Display helper + call sites:

```python
def job_display(job):
    """Progress-line label: rebase jobs show their base list too."""
    if job.base_list:
        return f"{job.source_list} (from {job.base_list})"
    return job.source_list
```

In `main()`, replace `{job.source_list}` with `{job_display(job)}` in the three print statements (dry-run line, success line, failure line).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools; python -m unittest test_regenerate -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/regenerate.py tools/test_regenerate.py
git commit -m "feat: teach regenerate the rebase report type"
```

---

### Task 8: Docs, slash command, full verification, real report

**Goal:** CLAUDE.md and `/serve-coverage` document the new capability; the full test suite is green; the actual NS PBR rebase report exists in `output/`.

**Files:**
- Modify: `CLAUDE.md` (**git: stage as `CLAUDE.MD`** — git tracks the uppercase name; `git add CLAUDE.md` silently misses it)
- Modify: `.claude/commands/serve-coverage.md`
- Create (generated): `output/NORDIC SOULS v3.1.1 - PBR Edition 1.5.0/NORDIC SOULS v3.1.1 (from NORDIC SOULS v3.0.1).rebase.html`

**Acceptance Criteria:**
- [ ] CLAUDE.md documents the Plugins and Removed states, `--base`, the rebase filename convention, and regenerate's `rebase` type.
- [ ] `/serve-coverage` accepts an optional third `<base>` token.
- [ ] All four test suites pass (`tools/`, `plugin-order/`, `download-state/`, `version-fix/`).
- [ ] The real rebase report generates without error and renders "Base Update Coverage".

**Verify:**
```powershell
cd tools; python -m unittest test_modlist_utils test_generate_coverage test_coverage_ignore test_coverage_server test_regenerate -v
```
→ all pass; then the report-generation command below succeeds.

**Steps:**

- [ ] **Step 1: Update CLAUDE.md**

In the **Coverage view** section:

1. In the paragraph starting `**Mod states** (source-ahead only is actionable)`, change the opening to `**Mod states** (source-ahead and drifted-plugins are actionable).` and add these bullets after the **Differs** bullet:

```markdown
- **Plugins** (violet, `±`) — same (or unknown) version but the plugin file set differs from the
  source's; shown as the delta the target would apply (`+Foo.esp −Bar.esp`, collapsed to counts
  past 3 names, full list in the tooltip). When the target is *ahead* in version, plugin diffs
  stay Common (matching an older layout isn't a goal).
- **Removed** (red, `−`, `--base` mode only) — removed in the base update but still in the
  target; rendered in a synthetic "Removed in base update" section at the bottom.
```

2. Update the `% covered` paragraph's formula sentence to:

```markdown
`(common + ignored + ½·(newer + differs + plugins)) / total` — **Removed** and **Add** weigh zero.
```

3. Add a new subsection after the **Mod names** paragraph:

```markdown
**Base update mode (`--base`):** for a *derived* list tracking an upstream base (e.g. PBR
Edition on NORDIC SOULS), pass the **old** base with `--base` to filter the report to mods
that changed in the base update — version changes, plugin-set changes, new mods — plus a
"Removed in base update" section for base-removed mods the target still carries. Everything
unchanged in the base (your deliberate deviations included) is dropped. Rows carry a tooltip
noting what changed in the base (`Base: 1.2 → 1.5`, `Base plugins: +A.esp`).

```bash
python tools/generate_coverage.py \
  "lists/NORDIC SOULS v3.1.1.json" \
  "lists/NORDIC SOULS v3.1.1 - PBR Edition 1.5.0.json" \
  --base "lists/NORDIC SOULS v3.0.1.json" \
  -o output/ [--serve]
```

With `-o <dir>` the report is named `output/<target>/<source> (from <base>).rebase.html` (a
distinct artifact from plain coverage — both can coexist). It shares the target's
`.coverage-ignore.txt`, works with `--serve` (the worklist shrinks live as you re-export the
target), and `% covered` reads as "how much of the base update the target has absorbed".
Design: [2026-07-03-base-update-coverage-design.md](../design/2026-07-03-base-update-coverage-design.md).
```

4. In the **Regenerate** section, after the sentence about parsing the filename convention, add:

```markdown
`rebase` reports (`<source> (from <base>).rebase.html`) are re-run through
`generate_coverage.py --base`; a missing base list JSON skips with a warning.
```

- [ ] **Step 2: Update `.claude/commands/serve-coverage.md`**

- Change `argument-hint` to: `<source> <target> [<base>]  — partial names ok (newest wins); base = the OLD base list for a base-update worklist`
- In step 1, change the parse description: two **or three** tokens; the optional third is the **base** (old base list). Fewer than two → usage error as today.
- In step 2, resolve the third token the same way when present, and include it in the report-back line (`base -> lists/....json`).
- In step 3, append `--base "lists/<base>.json"` to the command when a base was given:

```bash
python tools/generate_coverage.py "lists/<source>.json" "lists/<target>.json" -o output/ --serve --base "lists/<base>.json"
```

- In step 4's notes, add: with a base, the page is the **Base Update Coverage** worklist (only mods changed in the base update; re-exporting the target and refreshing shrinks it).

- [ ] **Step 3: Run every test suite**

```powershell
cd tools; python -m unittest test_modlist_utils test_generate_coverage test_coverage_ignore test_coverage_server test_regenerate -v
cd ../plugin-order; python -m unittest test_order_by_groups -v
cd ../download-state; python -m unittest test_reset_download_state -v
cd ../version-fix; python -m unittest test_fix_versions -v
```

Expected: all PASS everywhere (the last three suites don't touch changed code; they're the repo's full-green convention).

- [ ] **Step 4: Generate the real report**

From the repo root:

```powershell
python tools/generate_coverage.py "lists/NORDIC SOULS v3.1.1.json" "lists/NORDIC SOULS v3.1.1 - PBR Edition 1.5.0.json" --base "lists/NORDIC SOULS v3.0.1.json" -o output/
```

Expected output line: `Coverage view written to output\NORDIC SOULS v3.1.1 - PBR Edition 1.5.0\NORDIC SOULS v3.1.1 (from NORDIC SOULS v3.0.1).rebase.html`

Sanity-check the file: contains `Base Update Coverage`, a plausible mod count (far fewer than the ~3000-mod full list — only base-changed mods), and (if any base removals match) `Removed in base update`. Then confirm regenerate round-trips it:

```powershell
python tools/regenerate.py "NORDIC SOULS v3.1.1 - PBR Edition 1.5.0" --dry-run
```

Expected: the plan lists the existing reports for that folder **plus** `rebase     NORDIC SOULS v3.1.1 (from NORDIC SOULS v3.0.1)`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.MD .claude/commands/serve-coverage.md "output/NORDIC SOULS v3.1.1 - PBR Edition 1.5.0/NORDIC SOULS v3.1.1 (from NORDIC SOULS v3.0.1).rebase.html"
git commit -m "docs: document base update coverage; generate the NS PBR rebase report"
```

---

## Post-plan (coordinator, not a task)

- Review the generated report visually with the user; iterate on noise if needed.
- `superpowers-extended-cc:finishing-a-development-branch` — merge `base-update-coverage` to `main` locally (no remote), per the user's standing workflow.
