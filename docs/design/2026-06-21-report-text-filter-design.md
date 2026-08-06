# Report Text Filter — Design

**Date:** 2026-06-21
**Status:** Approved (design)
**Affects:** `tools/generate_coverage.py`, `tools/generate_diff.py`, their tests

## Problem

The coverage and diff HTML reports can list hundreds of mods. There is no fast way to
find a specific mod by name — you scroll. Add a simple, live text filter in each report's
header that hides mod rows whose name doesn't match what you type.

## Behavior

- **Input:** a text box in the report header.
- **Case-insensitive** substring matching on the **mod name only**.
- **Multi-term AND:** the query is split on whitespace into terms; a name matches only if it
  contains *every* term. Example: `3d thing` matches a mod whose name contains `3d` **and**
  `thing` (in any order, anywhere in the name).
- **Empty query = filter off** — all rows shown.
- **Sections stay visible:** section headers, major-separator bands, and dividers are never
  hidden by the filter. Only individual **mod rows** are hidden.

### Report-specific behavior

- **Coverage — collapsed sections stay collapsed.** All-common sections start collapsed. The
  filter does *not* force them open; a match inside a collapsed section remains hidden until the
  user expands it (the existing **Expand all** button opens everything, after which the filter
  spans all sections). This keeps the filter free of collapse-state bookkeeping.
- **Diff — either name matches.** A diff row can carry two names (old on the left, new on the
  right) when a mod is renamed. A row stays visible if **either** the old name **or** the new
  name contains all terms. (Per-name evaluation, not a combined string, so a term in the old
  name plus a different term in the new name does not produce a false match.)

## Design

### Matching target — `data-names` attribute

Every **mod row** gets a `data-names` attribute holding its lowercased mod name(s), joined by a
newline (`\n`) delimiter:

- Coverage: exactly one name per row.
- Diff: one name (added/removed rows) or two (renamed rows).

The filter JS reads `data-names`, so it matches the **name only** — never version strings,
Nexus-link text, or move/section annotations rendered in the same row. Pre-lowercasing in the
attribute avoids re-lowercasing on every keystroke. Only mod rows carry the attribute, so
section-header and band rows are inherently excluded from filtering.

Newline is a safe delimiter: mod names never contain newlines, and HTML attribute values may
contain literal newlines (emitted via the existing `_esc` escaping path).

### Hiding mechanism — `filter-hidden` class

Non-matching rows receive a `filter-hidden` class; matching rows have it removed.

```css
/* coverage */ .mod-row.filter-hidden { display: none; }
/* diff     */ tr.filter-hidden       { display: none; }
```

This composes cleanly with the existing visibility toggles
(`body.hide-common` in coverage, `body.hide-unchanged` in diff): if *either* the toggle rule or
the filter rule sets `display: none`, the row is hidden. No coordinating logic is needed.

### Filter JS

A single small function bound to the input's `input` event, plus an Esc-to-clear handler:

```js
function filterMods() {
  var q = (this.value || "").trim().toLowerCase();
  var terms = q ? q.split(/\s+/) : [];
  document.querySelectorAll("[data-names]").forEach(function (row) {
    var hidden = false;
    if (terms.length) {
      var names = row.getAttribute("data-names").split("\n");
      // row matches if ANY of its names contains EVERY term
      var match = names.some(function (n) {
        return terms.every(function (t) { return n.indexOf(t) !== -1; });
      });
      hidden = !match;
    }
    row.classList.toggle("filter-hidden", hidden);
  });
}
```

- Empty query → `terms` is empty → no row is hidden (`filter-hidden` cleared from all).
- The `[data-names]` selector is generator-agnostic; the same logic ships in both files.
- Coverage's copy lives in the **always-present** `<script>` block (not the serve-only block),
  so it works in both static and served coverage. It is independent of the serve-mode
  ignore/recount logic — filtering toggles `filter-hidden` only and never triggers a recount;
  recount counts by state class and is unaffected by `filter-hidden`.

### Diff sticky header

Diff's `.header` is currently not sticky, so the filter box would scroll out of view. Add, to
match coverage:

```css
.header {
  position: sticky; top: 0; z-index: 50;
  /* existing background / padding / border-bottom retained */
  box-shadow: 0 4px 12px rgba(0,0,0,0.45);
}
```

Coverage's header is already `position: sticky; top: 0; z-index: 50` — no change there. The
fixed-position `.controls` cluster uses `z-index: 100` in both files and continues to float
above the sticky header.

### Input markup

In each report's `.header` block, after the lists/summary line:

```html
<input type="search" class="filter-input" placeholder="Filter mods… (space = AND)">
```

- `type="search"` provides a native clear (×) button. An explicit `keydown` handler clears the
  box on **Esc** for reliability across browsers.
- Minimal `.filter-input` CSS styled to match the existing dark theme (full-width within the
  header, dark background, light text).
- **No live match count** in v1 (YAGNI; trivial to add later).

## Testing

String-presence tests in the existing style (e.g. `assertIn("position: sticky", …)`); there is
no JS-execution harness, so assertions are on emitted markup / CSS / JS text.

- **Coverage** (`test_generate_coverage.py`):
  - output contains the `<input ... class="filter-input">`
  - output contains the `.mod-row.filter-hidden { display: none; }` rule
  - a rendered mod row carries a `data-names="…"` attribute with the lowercased name
  - output contains the `filterMods` function
- **Diff** (`test_generate_diff.py` — no diff test file exists today, so create it):
  - output contains the filter input and the `tr.filter-hidden` rule
  - `.header` has `position: sticky`
  - a renamed row's `data-names` carries **both** old and new names (lowercased, newline-joined)
  - output contains the `filterMods` function

## Out of scope

- No changes to `modlist_utils.py` or any matching logic.
- No filtering of section-header / band rows.
- No persistence, regex, per-state filtering, or live match count.
