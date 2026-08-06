# Filter-Driven Section Visibility — Design

**Date:** 2026-06-21
**Status:** Approved (design)
**Affects:** `tools/generate_coverage.py`, `tools/generate_diff.py`, their tests
**Supersedes:** the "Sections stay visible — section headers, major-separator bands, and
dividers are never hidden by the filter" rule in
[2026-06-21-report-text-filter-design.md](2026-06-21-report-text-filter-design.md). Section
headers and bands now *do* react to the filter, per the rule below.

## Problem

The text filter added in the report-text-filter work hides only individual mod rows. Section
headers, major-separator bands, and dividers always stay visible. When a filter is active, this
leaves a wall of empty section headers with no rows under them — the headers no longer help you
locate anything; they're noise.

Sections are useful precisely because they tell you *where a mod belongs*. So when a filter
empties a section, hide the section too — but keep just enough structure that a surviving match
is still placed in context.

## Behavior

One rule governs everything:

> **A section header (and, in coverage, a major-separator band) is shown while a filter is active
> iff it contains at least one mod row that *would actually be visible*** — a row that (a) matches
> the filter terms **and** (b) is not suppressed by the active view toggle.

"Active view toggle" means **Hide common** in coverage (suppresses `mod-common` and `mod-ignored`
rows) and **Hide unchanged** in the diff (suppresses `mod-unchanged` rows).

### Worked example (coverage)

Filter on `abc`; the only match is "ABC Mod", which is **common**:

- **Hide common OFF** → "ABC Mod" is visible → its section header shows.
- **Hide common ON** → "ABC Mod" is suppressed → it's the only match → the section header hides.

### Collapse is *not* "hidden"

Collapse state is deliberately excluded from "would actually be visible." A collapsed coverage
section that contains a matching, would-be-visible mod **keeps its header** — the header is the
expand control, so hiding it would make the match unreachable. We never programmatically expand or
collapse based on the filter (carries forward the "leave collapse alone" decision from the
report-text-filter design). "Would actually be visible" therefore means *modulo the view toggle,
ignoring collapse* — not literal on-screen pixels.

### Filter off

When the query is empty (including after Escape), all section/band hiding is undone and the report
returns to its normal state. No section/band is ever hidden when no filter is active.

### Coverage — major bands

A major-separator band (the full-width `---------- BASE ----------` divider) is shown iff **at
least one section beneath it survives** the rule above. If every section under a band is hidden,
the band hides too. So a band tracks its children: it stays while any child section (or the
major-separator's own bandless rows) still shows a match.

### Diff — symmetry

The diff is a flat table with no major bands; only `section-header` rows are affected. A
`section-header` row hides when no mod row between it and the next `section-header` would be
visible (same rule, using **Hide unchanged** as the toggle). This means a `hide-unchanged`-only
empty section (no filter active) is *not* hidden — section hiding only applies while a filter is
active — but when a filter *is* active, `hide-unchanged` is correctly accounted for in the
visibility test.

## Design

### Approach: extend the existing client-side `filterMods()`; no HTML restructuring

Bands and sections are already emitted in document order, so they can be walked with
`querySelectorAll` / `nextElementSibling`. No wrapper `<div>`s, no `<tbody>` grouping, no changes
to the render functions or the sticky-header CSS. The rejected alternative — restructuring the
HTML so each major-group / diff-section is a container — would make the JS trivial but rewrites
recently-shipped render code and risks the sticky-header layout, for no functional gain.

**One markup change (coverage):** `_render_bandless_rows` emits `<div class="section-body">`,
which collides with the inner `.section-body` of a regular section. Add a `bandless` marker class
— `<div class="section-body bandless">` — so the recompute and the CSS can target the standalone
(major-separator) bodies unambiguously without matching the inner body of a normal section. This
is the only HTML change in the whole feature.

### Shared visibility predicate

A mod row "counts" toward keeping its container alive when:

```js
counts(row) = !row.classList.contains('filter-hidden')   // matches the filter terms
              && !suppressedByToggle(row)                 // not hidden by Hide common / Hide unchanged
```

`suppressedByToggle` is report-specific:

- **Coverage:** `document.body.classList.contains('hide-common')` **and** the row is `mod-common`
  or `mod-ignored`.
- **Diff:** `document.body.classList.contains('hide-unchanged')` **and** the row is
  `mod-unchanged`.

Collapse is intentionally absent from the predicate.

### Coverage recompute

A new JS function (e.g. `applySectionVisibility()`):

1. **If no filter terms:** remove `filter-empty` from every `.section`, every bandless
   `.section-body`, and every `.band`; return. (Normal view restored.)
2. **Per section unit:** for each `.section` (toggle the class on the outer `.section`) and each
   `.section-body.bandless`, toggle `filter-empty` based on whether it contains any `counts(row)`
   mod row.
3. **Per band:** for each `.band`, walk `nextElementSibling` until the next `.band` (or end);
   if none of the section units (`.section` / `.section-body.bandless`) in that run has a counting
   row, toggle `filter-empty` on the band.

`.section.filter-empty`, `.section-body.bandless.filter-empty`, and `.band.filter-empty` get
`display: none` in CSS. (The CSS is scoped to `.bandless` so it can never hide a regular
section's inner body.)

### Diff recompute

Same function, adapted to the flat table:

1. **If no filter terms:** remove the hidden marker from every `tr.section-header`; return.
2. Walk table rows; for each `tr.section-header`, scan forward to the next `tr.section-header`
   (or end of tbody) and toggle the hidden marker based on whether any mod row in that run counts.

`tr.section-header.filter-empty` gets `display: none`.

### Wiring

`applySectionVisibility()` is called:

- at the **end of `filterMods()`** (after the per-row `filter-hidden` pass), and
- from **`toggleCommon()`** (coverage) / **`toggleUnchanged()`** (diff), so headers stay correct
  when a toggle changes what's visible while a filter is active, and
- in coverage **`--serve`** mode, after the ignore round-trip's existing `recount()` — toggling a
  mod to/from ignored can change whether it counts (when Hide common is on), so the section/band
  visibility must refresh too.

The `filterMods()` toggle handlers already exist; this adds one call site each and the new
function. The serve-mode block adds one call inside the existing click handler's success path.

## Edge cases

- **Empty filter** → recompute clears all `filter-empty` marks (handled in step 1 of each
  recompute).
- **Filter matches nothing** → every section/band hides (expected; the report reads as "no
  matches").
- **Collapsed section with a match** → header stays (collapse excluded from predicate); user
  expands to reach the match.
- **Match only on a toggle-suppressed row** → section hides, per the worked example.
- **Sections with no major (coverage `section_majors` is `None`)** → standalone sections handled
  by the per-section pass; the band walk simply finds no preceding band for them.

## Testing

Following the suite's existing string-presence style (JS runtime behavior is not executed by the
Python tests):

- **`test_generate_coverage.py`:** assert the generated HTML contains the new `filter-empty` CSS
  rules (`.section`, `.section-body`, `.band`) and the `applySectionVisibility` recompute logic,
  in both static and `--serve` output. Assert `toggleCommon` invokes the recompute.
- **`test_generate_diff.py`** (add if absent, else extend): assert the `tr.section-header`
  `filter-empty` rule and the recompute logic are present, and that `toggleUnchanged` invokes it.

No new Python-side logic is added (this is all generated JS/CSS), so `modlist_utils.py` tests are
unaffected.
