# Nexus Description — Native BBCode + Editor Page Design

**Date:** 2026-08-07
**Status:** Approved

## Problem

Publishing the `modlist_compare` plugin on Nexus Mods requires two description
fields: a plain-text short description (≤350 characters, shown on the mod
card) and a full description in BBCode. The repo should be the source of
truth for both, and editing BBCode blind — no preview until it's pasted into
Nexus — is the pain point to solve.

An earlier design (markdown source + exact markdown→BBCode converter) was
abandoned: the converter had to be exact because its output shipped, which
bought subset restrictions, error machinery, and a test matrix. Maintaining
BBCode natively moves the conversion to the *preview* side, where it only has
to be approximately right — Nexus's own preview stays the final authority.

## Decision summary

- **Source of truth:** raw Nexus BBCode, checked in next to the plugin. No
  conversion step; what's in the file is what gets pasted into Nexus.
- **Preview/editing:** one committed, self-contained HTML editor page with a
  live BBCode preview, hand-rolled inline JS — no vendored libraries
  (SCEditor/BBob considered; the per-tag configuration to match Nexus's
  dialect costs about as much as the renderer itself).
- **Trade accepted:** GitHub renders the description file as plain text, and
  the page's renderer is untested JS verified by eye. In exchange: the full
  Nexus tag set is available, and there is no production converter to keep
  correct.

## Source files

Two files next to the plugin, both drafted as part of this work (prose is a
first pass for the author to edit):

- `mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.bbcode` — the full
  description, raw Nexus BBCode.
- `mo2-plugins/modlist_compare/NEXUS_SHORT_DESCRIPTION.txt` — the mod-card
  blurb: one line of plain text, at most 350 characters.

Both ship inside the plugin zip like `README.md` does — harmless, and
`package_plugin.py` is not modified.

## Editor page

`tools/nexus_bbcode_editor.html` — a single committed file, inline CSS and
JS only, no external requests, opens directly via `file://`.

Layout and behaviour:

- **Short description field** — single-line input with a live character
  counter (`N / 350`) that turns red past the limit. Purely visual; nothing
  blocks typing.
- **BBCode editor** — textarea beside a live preview pane, re-rendered on
  every input event.
- **Load file** — a file-picker button per field (FileReader API, works from
  `file://`) to pull the current repo files in.
- **Copy** — a copy-to-clipboard button per field. Saving back to the repo is
  paste-into-editor: browsers cannot write local files from a `file://` page,
  and a save server is out of scope.
- **Autosave** — both fields mirror to localStorage on input and restore on
  open, so an accidental tab close loses nothing; a reset control clears the
  stored draft.

## Renderer

Roughly 120 lines of inline JS. Pipeline:

1. HTML-escape the raw text first, so stray `<` or `&` cannot inject markup
   and make the preview lie.
2. Apply tag transforms for Nexus's set: `[b]`, `[i]`, `[u]`, `[s]`,
   `[size=1-6]` (mapped to a rough px scale matching Nexus's steps),
   `[color=X]`, `[font=X]`, `[url=X]text[/url]` and bare `[url]link[/url]`,
   `[img]`, `[list]` / `[list=1]` with
   `[*]` items, `[center]`, `[quote]`, `[spoiler]` (rendered as
   `<details>`), `[youtube]` (rendered as a link placeholder — no external
   embeds in a self-contained page), `[line]` (horizontal rule).
3. Newlines become `<br>` outside block constructs.

Unknown or malformed tags are left visible as literal text — no errors, no
stripping. The preview is an approximation; the final check before
publishing is Nexus's own preview.

## Tests

`tools/test_nexus_description.py`, run with the existing `tools/` unittest
suite — the one hard constraint is machine-checked:

- both source files exist
- the short description is a single line, non-empty, and ≤350 characters

The editor page's JS is deliberately untested (the repo's test culture is
Python; the page is a dev-time visual tool).

## Documentation updates

- CLAUDE.md: add `test_nexus_description` to the tools test command.
- Plugin README, Development section: one paragraph naming the two source
  files, the editor page, and the workflow (edit → preview in the page →
  copy into the file and into Nexus).

## Workflow

1. Edit `NEXUS_DESCRIPTION.bbcode` in VS Code, or open
   `tools/nexus_bbcode_editor.html` and load/paste it there.
2. Tweak with live preview; watch the short-description counter.
3. Copy each field back to its repo file (commit) and into the matching
   Nexus form field.

## Out of scope

- Any markdown→BBCode or BBCode→markdown conversion
- Vendored editor/parser libraries (SCEditor, BBob)
- Writing files from the page (File System Access API needs a secure
  context; `file://` pages don't qualify) or a local save server
- Packaging integration — `package_plugin.py` untouched
- Multi-plugin generality — one hardcoded pair of files until a second
  plugin exists
