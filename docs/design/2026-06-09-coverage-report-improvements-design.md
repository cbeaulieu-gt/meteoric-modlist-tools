# Coverage Report Improvements — Design

- **Date:** 2026-06-09
- **Status:** Approved (pending spec review)
- **Primary file:** `tools/generate_coverage.py`
- **Shared change:** `tools/modlist_utils.py` (output-path helper, used by all three tools)

## Motivation

Five observations on the `generate_coverage.py` HTML report:

1. The "missing" framing (red) reads as a problem, but those mods are really
   *candidates to add* to the target list — they should read as positive/green.
2. The version display shows `source → target`, which reads backwards. It should
   read as the upgrade you'd be making: `your-version → candidate-version`.
3. Section headers scroll out of view in long lists; they should stick like the
   main header already does.
4. Modlists encode an implicit second level of hierarchy via "major" separators
   whose names are wrapped in dashes (`---------- BASE ----------`,
   `- - - GAMEPLAY CHANGES - - -`). The report currently drops these entirely.
5. Output files are placed by hand. The tools should be able to organize reports
   into per-list subfolders.

Changes 1–4 are coverage-only. Change 5 is shared across all three generators.

## Change 1 — "Missing" → "Add" (green candidates)

Reframe the state from "missing" to "add candidate". It still means *the source
mod is not present in the target*; only the framing and color change.

- Rename `CoverageState.MISSING` → `CoverageState.ADD` (enum value `"add"`).
- Recolor from red to green:
  - `.mod-add` — green left-border and text (replaces `.mod-missing`).
  - `.stat-add` — green summary chip (replaces `.stat-missing`).
- Labels:
  - Summary chip: `"N missing"` → `"N to add"`.
  - Section badge term: `"missing"` → `"add"` (e.g. `1 add · 2 newer`).
- **No "ADD" tag on rows.** The green highlight is the entire signal — a literal
  "ADD" reads like an imperative command, which is not the intent.
- Nexus-link behavior on the mod name is unchanged.
- Update `_STATE_CSS`, `ACTIONABLE_STATES`, and the summary rendering to use the
  renamed member.

## Change 2 — Flip the version arrow (your version → candidate)

In `_version_html`, display **target-first** so the line reads as the upgrade the
user would make by pulling from the source:

| State   | Before            | After                  |
|---------|-------------------|------------------------|
| NEWER   | `↑ {src} → {tgt}` | `{tgt} → {src}`        |
| DIFFERS | `{src} ≠ {tgt}`   | `{tgt} ≠ {src}`        |
| ADD     | `{src}`           | `{src}` (unchanged)    |
| COMMON  | `{src}`           | `{src}` (unchanged)    |

The up-arrow (`↑`) is **dropped** for NEWER — the `→` already conveys direction,
so NEWER reads e.g. `16.0 → 16.3`. After this change there is no `↑` anywhere in
the output.

## Change 3 — Sticky sub-section headers

The main `.header` is already `position: sticky; top: 0`. Make each
`.section-header` sticky too, pinned just beneath the main header.

- CSS: `.section-header { position: sticky; top: var(--header-h); z-index: 40; }`
  - `z-index: 40` keeps it below the main header (`z-50`) and above mod rows.
  - The header already has a solid background, so rows scroll under it cleanly.
- The `--header-h` offset is the main header's rendered height, which varies with
  content. A small inline script sets it on load and on resize:
  `document.documentElement.style.setProperty('--header-h', headerEl.offsetHeight + 'px')`.
- Sticky containment is automatic: each header pins only while its own `.section`
  is onscreen, then unpins as the section scrolls away and the next one takes over.

## Change 4 — Major-section divider bands (layout B)

Represent major separators as full-width, **non-interactive divider bands** in the
otherwise-flat list. (Chosen over a nested/indented layout: simpler markup and
single-level sticky behavior.)

### Detection

A separator is **major** when, after trimming whitespace, its name begins and ends
with `-` and contains at least one alphanumeric character. This matches both
observed conventions:

- `---------- BASE ----------`
- `- - - GAMEPLAY CHANGES - - -`

The **display name** is the decoration stripped from both ends
(`name.strip().strip("- ").strip()`), e.g. `BASE`, `GAMEPLAY CHANGES`. Regular
sub-separators that merely contain dashes internally (e.g.
`NS3 - SKSE Plugins & Fixes`, `21-9 WideScreen Support`) are **not** major because
they do not start *and* end with a dash.

Add a small helper pair (`is_major_separator(name)` / `major_display_name(name)`)
in `generate_coverage.py`.

### Classification

The major/sub-section relationship is **positional**, not structural — MO2's
separator list is flat. To recover it, walk the source items in document order,
tracking the current major:

- A **major separator** sets `current_major = major_display_name(name)`.
- A **regular separator** records `section_major[name] = current_major` (first
  occurrence wins).
- A **mod** records `section_major[mod.separatorName] = current_major` if not
  already set.

Sections that appear before the first major separator map to `None` (no band).
This mapping is built alongside the existing `rows_by_section` grouping.

### Rendering

Walk `rows_by_section` in its existing order. Track the previously-emitted major;
whenever a section's major differs from the previous one and is not `None`, emit a
`<div class="band">` divider with the major's display name *before* that section.
Sub-sections render exactly as today (flat indent, collapsible, count badge).

- Bands carry **no badge, no caret, no collapse, and are not sticky** — they
  scroll away. `.band` is a centered, full-width divider.
- **Edge case:** a major separator that has mods directly under it (the mod's
  `separatorName` is itself a major-pattern string). Its rows render directly
  beneath the band with **no** sub-header (the band is their header). Detect this
  by `is_major_separator(section_name)` during rendering.
- `Expand all` / `Collapse all` and the "Hide common" toggle continue to operate
  on `.section` elements only; bands are unaffected.

## Change 5 — Output subfolders (all three tools)

Add a shared helper to `modlist_utils.py`:

```python
def resolve_output_path(output_arg, first_path, second_path, type_label, ext):
    """
    Resolve the final output file path.

    - output_arg is None/empty  -> return None (caller writes to stdout).
    - output_arg is a directory -> return
        <output_arg>/<basename(second_path)>/<basename(first_path)>.<type_label>.<ext>
      creating intermediate directories. "Directory" means it ends with a path
      separator or names an existing directory.
    - otherwise                 -> return output_arg verbatim (explicit file path).
    """
```

- Folder name = basename (without extension) of the **2nd** positional argument.
- Inner file name = basename (without extension) of the **1st** positional
  argument + `.<type_label>.<ext>`.
- Names derive from input *filenames*, which already exist on disk and are
  therefore filesystem-safe (no separate sanitization needed).
- Directory creation uses `os.makedirs(..., exist_ok=True)`.

### Per-tool wiring

Each `main()` currently does:

```python
if args.output:
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"... written to {args.output}", file=sys.stderr)
else:
    <stdout>
```

Replace the `if args.output:` guard with a resolved path:

```python
out_path = resolve_output_path(args.output, <first>, <second>, "<type>", "<ext>")
if out_path:
    ...write to out_path...
else:
    <stdout>
```

| Tool                | first / second        | type / ext        | Example output path                                          |
|---------------------|-----------------------|-------------------|-------------------------------------------------------------|
| `generate_coverage` | `source` / `target`   | `coverage` / `html` | `output/Meteoric 0.0.3/NORDIC SOULS v3.0.1.coverage.html`  |
| `generate_diff`     | `old_list` / `new_list` | `diff` / `html` | `output/<new>/<old>.diff.html`                              |
| `generate_changelog`| `old_list` / `new_list` | `changelog` / `md` | `output/<new>/<old>.changelog.md`                         |

`-o` omitted still goes to stdout; an explicit file path (`-o foo.html`) still
writes exactly there. Only a directory-valued `-o` triggers the new auto-naming.

## Testing

`tools/test_generate_coverage.py`:

- Update version-direction assertions to target-first and no up-arrow:
  `1.4 → 1.5` (was `1.5 → 1.4`), `1.0alpha ≠ 1.0beta` (was `1.0beta ≠ 1.0alpha`),
  and drop the `assertIn("↑", ...)`.
- Replace `CoverageState.MISSING` references with `CoverageState.ADD`.
- Add: major-separator detection + display-name stripping (positive and negative
  cases); band emitted once per major and grouping order preserved; a
  `.section-header` sticky CSS assertion.

`tools/test_modlist_utils.py`:

- Add `resolve_output_path` cases: `None` → `None`; explicit file path returned
  verbatim; directory input → correct `<dir>/<2nd>/<1st>.<type>.<ext>` and folder
  created; folder/name derived from the right arguments.

Run from inside `tools/`:

```bash
cd tools
python -m unittest test_modlist_utils test_generate_coverage -v
```

Update the `CLAUDE.md` coverage section (mod-state descriptions, version display,
and the new output-path behavior) to match.

## Out of scope

- Nested/indented major-section layout (explicitly rejected in favor of bands).
- Making bands collapsible or sticky.
- Changes to matching/version logic in `modlist_utils.py`.
- Regenerating committed reports in `output/` (a follow-up, not part of this work).

## Files touched

- `tools/generate_coverage.py` — changes 1–4, plus wiring change 5.
- `tools/modlist_utils.py` — `resolve_output_path` helper.
- `tools/generate_diff.py`, `tools/generate_changelog.py` — wiring for change 5.
- `tools/test_generate_coverage.py`, `tools/test_modlist_utils.py` — test updates.
- `CLAUDE.md` — documentation updates.
