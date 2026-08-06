# Coverage: show the target's mod name first for matched mods

**Date:** 2026-06-23
**Tool:** `tools/generate_coverage.py`
**Status:** Approved (design)

## Problem

The coverage view renders the **source** list's mods, so every row shows the
**source's** `modName`. But the reader is working against their **target** list,
where the same mod is sometimes named differently (e.g. a renamed install, a
different author label). Seeing only the source's name for a mod that already
exists in the target — under a different name — is mildly disorienting: "do I
have this or not?"

This is a clarity tweak, not a bug fix. When a mod exists in **both** lists with
**different** names, surface the name the reader already knows (the target's)
first, with the source's name in parentheses for cross-reference.

## Behavior

For each row:

- **Matched** mod (states `Newer` / `Differs` / `Common`) whose target raw
  `modName` **differs** from the source raw `modName`:
  render `Target Name (Source Name)`.
- **Matched** mod with **identical** names: render the single name (unchanged).
- **Unmatched** mod (state `Add`): render the source name only (unchanged) —
  there is no target counterpart.

Notes:

- Comparison is on the **raw** `modName` strings (exact, case-sensitive). Two
  names that normalize equal but read differently — `Cathedral Landscapes` vs
  `Cathedral - Landscapes` — are exactly the case we want to surface, so they
  count as "differ" and show both.
- The parenthetical `(Source Name)` renders **muted** (dimmer, ~11px) so the
  primary (target) name stays the visual anchor.
- The **whole** rendered name (primary + parenthetical) is the Nexus link,
  pointing at the source's Nexus page (from the source mod's `id`), exactly as
  today. The source `id` is what the reader pulls *from*, so the link target is
  unchanged.

## Code changes (`tools/generate_coverage.py`)

1. **`CoverageRow`** — add `target_name: str = ""`. Empty for unmatched rows.
2. **`classify_source_mods`** — when `target_mod` is found, set
   `target_name = target_mod.get("modName", "")`. (The matched target mod is
   already in hand via `match_lookup`; only its version is kept today.)
3. **`_name_html(row)`** — compute:
   - `source_name = row.mod.get("modName", "Unknown")`
   - `primary = target_name if (target_name and target_name != source_name) else source_name`
   - if a distinct target name exists, append
     `<span class="src-alias">(source_name)</span>` after the primary.
   - wrap the whole thing in the existing `<a href=nexus>` when `nexus_id` is set
     (unchanged link logic); otherwise plain text.
4. **CSS** — add `.src-alias { color: #8b94a8; font-size: 11px; margin-left: 4px; }`
   — a muted grey in the same family as the existing `.badge` (`#94a3b8`) /
   common (`#9ca3af`) palette, dimmer than the primary name but still legible.
   On `mod-common` / `mod-ignored` rows (already grey) it inherits fine; no
   per-state override needed.

## Filtering

`_render_mod_row` writes `data-names` (lowercased) for the text filter, and the
filter JS already splits that attribute on `\n` to support multiple names —
today only the source name is written. Add the target name as a second line so a
row matches when the user types **either** name.

`data-mod` (serve-mode ignore key) stays the **source** name, so click-to-ignore
is unaffected (ignores are keyed by the source mod's normalized name).

## Serve mode

`render_html` is shared between static and `--serve` output, so the change
applies to both with no serve-specific work. The recount/ignore JS keys off CSS
classes and `data-mod`, neither of which changes.

## Testing (`tools/test_generate_coverage.py`)

Add cases:

- Matched mod, **different** names → output contains `Target (Source)` with the
  `src-alias` span; primary text is the target name.
- Matched mod, **identical** names → single name, no `src-alias` span.
- Unmatched mod (`Add`) → source name only, no `src-alias` span.
- `data-names` for a renamed match contains **both** lowercased names.
- Nexus link still wraps the full name for a matched-renamed mod with an `id`.

## Out of scope

- No change to matching logic in `modlist_utils.py`.
- No change to `generate_diff.py` / `generate_changelog.py`.
- No change to the ignore-file format or serve API.
