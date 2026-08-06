# Coverage "Ignore" Marks — Design

**Date:** 2026-06-21
**Status:** Implemented (`tools/coverage_ignore.py`, `tools/coverage_server.py`)

## Problem

The coverage view (`generate_coverage.py`) renders a **source** list's mods grouped by its
sections and highlights what the **target** list (the actively-maintained project list, currently
`Meteoric 0.0.x`) is missing — the green **Add** candidates plus **Newer**/**Differs** version
gaps. It answers "what can I pull from the source into my list."

As the target list matures, more and more of those candidates are mods the user has *deliberately
decided not to transfer in*. There is currently no way to record that decision, so every
regeneration re-surfaces the same already-rejected mods as actionable, drawing attention away from
the candidates still worth triaging. With many mods still to go through, the actionable list needs
to shrink as decisions are made, not stay constant.

## Goal

Let the user **mark a coverage-view mod as "ignored"** so it renders muted (like Common) and drops
out of the actionable counts — and have that decision **persist across regenerations**. Marking
happens by clicking in a live-served report; the decision is written to a file that every
subsequent run reads.

## Decisions made during brainstorming

- **Coverage view only.** Not the diff or changelog. The "candidate to pull in / won't pull in"
  concept only exists in coverage. (The diff is a load-order comparison; the changelog is a
  version delta.)
- **Persistence model: local server (`--serve`).** A browser cannot silently write to a file path
  when an HTML report is opened via `file://`. Rather than a manual export/download step or a
  hand-edited file, `generate_coverage.py --serve` starts a stdlib HTTP server; clicking a mod
  writes the ignore file **instantly**. The static `file://` flow and the `/regenerate` batch flow
  still *read* the ignore file and grey accordingly — only writing requires the server.
- **Scope: per target list (global across sources).** One ignore set per target. Marking a mod in
  the BottleRim-vs-Meteoric report greys it in the CSVO-vs-Meteoric report and every other report
  whose target is Meteoric. This matches the user's framing ("mods I won't transfer into Meteoric")
  which is a property of the mod and the target, independent of which source surfaces it. Per-report
  scoping was considered and rejected as requiring the same mod to be re-marked in each report.
- **Identity: normalized mod name.** The ignore must survive version bumps (re-exporting BottleRim
  2.1.1 → 2.2.0 keeps the mark) and apply across sources — `modName` does both, and matches how the
  tools already match mods by name. Keying by Nexus `id` was rejected: an `id` is a *page* that can
  host several distinct mods, so id-keying would over-ignore siblings on the same page. Tradeoff: a
  hard rename requires re-marking (rare).
- **Visual treatment: color only, no glyph.** An ignored row takes the muted Common-like color and
  nothing else — no icon or marker. The goal is to draw *less* attention, and the codebase uses no
  per-row icons today. A persistent marker would work against the intent.
- **Interaction: whole-row click.** With no icon, the click target is the whole row (in serve mode),
  except the mod-name link, which still navigates to Nexus. The only affordance is `cursor: pointer`,
  a subtle hover background, and a tooltip. Click again to un-ignore.
- **Code structure: `--serve` flag + two helper modules.** `generate_coverage.py` gains the flag and
  the always-on ignore read; the ignore store and the HTTP server live in focused, unit-testable
  sibling modules so the generator barely grows and `/regenerate` is untouched.

## The ignore file

- **Location:** one per target list, in that target's report folder:
  `output/<target>/.coverage-ignore.txt`. Derived the same way `resolve_output_path` derives the
  report folder (the folder is named after the 2nd positional list = the target).
- **Format:** UTF-8 plain text. One raw `modName` per line. Lines beginning with `#` are comments;
  blank lines are ignored. A header comment block explains the file's purpose and that it is
  hand-editable. Written back sorted and de-duplicated.
- **Matching:** on load, build a set of `normalize_name_strict(name)` (the existing matcher
  normalization) while retaining the raw names for round-tripping. A source mod is ignored iff
  `normalize_name_strict(mod["modName"])` is in that set.
- **Bonus:** because the file is plain, legible text, the "just hand-edit a list of names" workflow
  falls out for free — no server required to author it.

## Architecture

### Ignore store — `tools/coverage_ignore.py` (new)

Pure file/data logic, no HTTP, standard library only. The unit-testable seam.

- `resolve_ignore_path(output_arg, target_path)` → the per-target ignore file path, or `None` when
  undeterminable (e.g. output goes to stdout with no `-o`). Mirrors `resolve_output_path`'s "is this
  a directory?" logic: when `-o` is a directory the file sits in
  `<output_dir>/<target_basename>/.coverage-ignore.txt` (the per-target case); when `-o` is an
  explicit file it sits beside that file. In `--serve` mode (no static report is written) the path is
  resolved the same way from `-o` — so serving expects `-o output/` (a directory) to land on the
  per-target file — and `--ignore-file` overrides the result in any case.
- `load_ignore(path)` → an object/namedtuple exposing `.raw` (list of stored names) and `.norm` (set
  of normalized keys). Missing file → empty.
- `is_ignored(ignore, mod)` → `bool` (normalized-name membership).
- `add(path, name)` / `remove(path, name)` → idempotent load-modify-save mutations.
- `save(path, names)` → write sorted, unique names with the header comment.

### Generator — `generate_coverage.py` (changed)

- **New flags:** `--serve` (start the live server instead of writing a static report), `--port`
  (default 8000; auto-increments a small range if busy), `--no-browser` (don't auto-open), and
  `--ignore-file` (override the computed ignore-file path).
- **Always-on read:** `classify_source_mods(..., ignore=None)` consults the ignore set and sets a new
  field `CoverageRow.ignored: bool` (default `False`). This happens in normal/static mode and via
  `/regenerate` — honoring ignores never requires the server.
- **Counts (`compute_summary` + section badges):** an ignored mod is counted under a new **`ignored`**
  tally and **not** under its underlying state. So `add`/`newer`/`differs` reflect only un-ignored
  actionable mods; the summary bar gains an "N ignored" stat. Section badges and the
  "start expanded if the section has gaps" rule use the *un-ignored* actionable count, so a fully
  triaged section collapses on its own.
- **Rendering:**
  - Ignored rows get a `mod-ignored` CSS class — the muted Common-like color, no glyph.
  - `body.hide-common` also hides `.mod-ignored` (the existing "Hide common mods" toggle covers them).
  - **Static mode:** no clickable control (nothing can persist); rows render exactly as today plus
    the muted color on ignored ones.
  - **Serve mode:** mod rows carry their raw `modName` in a `data-` attribute, get `cursor: pointer`
    with a hover background and a tooltip, and include the serve-mode JS. The mod-name `<a>` keeps its
    Nexus navigation (its click does not toggle).

### Server — `tools/coverage_server.py` (new)

- stdlib `ThreadingHTTPServer` bound to **127.0.0.1 only** (it writes files; it must not be exposed).
- **`GET /`** → re-renders the report from the *current* source/target JSON + *current* ignore file
  (so a mid-session re-export is reflected on refresh), with serve-mode JS included.
- **`POST /api/ignore`** with body `{"name": "<raw modName>", "ignored": true|false}` → applies the
  change and returns `{"ok": true}`; a malformed body → `400`. The mutation is delegated to a pure
  `apply_ignore_change(ignore_path, name, ignored)` function so it is unit-testable without a socket.
- Any other path → `404`.
- On start: choose a free port, print the URL, and `webbrowser.open` it unless `--no-browser`.

### Browser interaction (serve mode JS)

Self-contained inline script, no external dependencies (consistent with the existing reports):

1. A click anywhere on a mod row (other than the mod-name link) reads the row's raw `modName` and the
   desired new state, then `POST`s to `/api/ignore`.
2. On `{ok:true}`, toggle the row's `mod-ignored` class and recompute the summary stats and the
   affected section badge live by scanning the DOM (cheap for a few hundred rows).
3. Clicking an ignored row un-ignores it (sends `ignored:false`).

Edge case: two mods sharing a normalized name within one report toggle together (they map to the same
ignore key). Rare and acceptable; noted rather than handled.

## Testing

Consistent with the existing suite (`cd tools && python -m unittest ...`), standard library only.

- **`tools/test_coverage_ignore.py` (new):**
  - `resolve_ignore_path` for a directory `-o`, an explicit-file `-o`, and the `None` (stdout) case.
  - `load_ignore` on a missing file, and on a file with comments, blank lines, and duplicate names.
  - normalized-name matching (`is_ignored` true for a differently-cased / suffixed name).
  - `add` / `remove` idempotency and round-trip; `save` output is sorted, unique, and carries the
    header.
- **`tools/test_generate_coverage.py` (extended):**
  - `classify_source_mods` sets `ignored` correctly from a supplied ignore set.
  - `compute_summary` counts an ignored Add as `ignored`, not `add`.
  - section badge and collapse default use the un-ignored actionable count.
  - render emits `mod-ignored` for ignored rows; the whole-row toggle hooks and serve JS appear only
    in serve mode (not in the static render).
- **`tools/test_coverage_server.py` (new):**
  - `apply_ignore_change` adds and removes against a temp ignore file and is idempotent.
  - a light integration test: start the server on an ephemeral port, `GET /` returns HTML,
    `POST /api/ignore` mutates the file and returns ok, a malformed body returns 400.

## Documentation — `CLAUDE.md`

- Coverage subsection: document `--serve`, `--port`, `--no-browser`, `--ignore-file`; the ignore file
  location/format; that static runs and `/regenerate` honor it; and the new "ignored" state/color.
- Add `coverage_ignore.py`, `coverage_server.py`, `test_coverage_ignore.py`, and
  `test_coverage_server.py` to the `tools/` tree diagram.
- Add the two new test modules to the testing section's command list.

## Out of scope (YAGNI)

- Ignore marks for the diff or changelog tools.
- Per-source (per-report) scoping, or an "ignore everywhere regardless of target" global.
- Reasons/notes attached to an ignore.
- Authentication or serving multiple reports from one server process.
- Keying by Nexus id or fileid (rejected above; name-based only).
