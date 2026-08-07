# Nexus Description Maintenance — Design

**Date:** 2026-08-07
**Status:** Approved

## Problem

Publishing the `modlist_compare` plugin on Nexus Mods requires two description
fields: a plain-text short description (≤350 characters, shown on the mod card)
and a full description in BBCode. Neither should be hand-maintained in Nexus's
web editor: the repo is the source of truth for everything else about the
plugin, and BBCode is unpleasant to write and impossible to preview on GitHub.

## Decision summary

- **Source of truth:** one markdown file checked in next to the plugin,
  previewable on GitHub.
- **Converter:** a standalone stdlib-only script in `tools/` that emits the two
  Nexus fields as files. Not wired into `package_plugin.py` (deliberate — two
  steps per release is fine, and descriptions change on a different cadence
  than code).
- **Escape hatch:** a small allowlist of inline HTML tags for BBCode features
  markdown can't express (color, underline, centering).
- **Content:** a first-pass description for `modlist_compare` is drafted as
  part of this work, in the style of the author's existing Nexus page for the
  download-copier plugin.

## Source file

`mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.md` — one markdown document
with exactly two top-level (`#`) sections, in this order:

```markdown
# Short description

One paragraph of plain text, at most 350 characters.

# Description

Full markdown body: headings, bold, italic, links, images, lists,
and the allowlisted HTML tags.
```

The `#` level is structural only — those two headings never render into
output, and any other `#` heading is an error. The file ships inside the
plugin zip like `README.md` does; that is harmless and requires no
`package_plugin.py` change.

## Converter

`tools/generate_nexus_description.py` — standard library only, line-based,
purpose-built for the subset below. It is **not** a general markdown parser.

### Paths and invocation

```bash
python tools/generate_nexus_description.py
```

No arguments. Paths resolve relative to the script's own location (the repo
root is `Path(__file__).parent.parent`), so it works from any cwd:

- reads `mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.md`
- writes `dist/nexus/short-description.txt` and `dist/nexus/description.bbcode`
  (`dist/` is already gitignored; the directory is created if missing)

Release workflow: run the script, open the two files, paste into the two
Nexus fields (the "Import description" button accepts raw BBCode).

### Short description handling

Treated as plain text: stripped of surrounding whitespace and written
verbatim. The converter fails with the actual character count if it exceeds
350 characters, and errors if the section contains any markdown or HTML
construct from the tables below — the Nexus card renders plain text only.

### Markdown → BBCode mapping (Description body)

| Markdown | BBCode |
| --- | --- |
| `## Heading` | `[size=4][b]Heading[/b][/size]` |
| `### Heading` | `[size=3][b]Heading[/b][/size]` |
| `**bold**` | `[b]bold[/b]` |
| `*italic*` | `[i]italic[/i]` |
| `[text](url)` | `[url=url]text[/url]` |
| `![alt](url)` | `[img]url[/img]` (alt text dropped — BBCode has no slot for it; it still serves the GitHub preview) |
| `- item` lines (consecutive) | `[list]` … `[*]item[/*]` … `[/list]` |
| `1. item` lines (consecutive) | `[list=1]` … `[*]item[/*]` … `[/list]` |
| blank lines / plain paragraphs | passed through unchanged |

Inline transforms (bold, italic, links, images, HTML allowlist) apply inside
headings and list items too — they are per-line substitutions, so they
compose.

### HTML allowlist → BBCode

| HTML | BBCode |
| --- | --- |
| `<font color="X">…</font>` | `[color=X]…[/color]` |
| `<u>…</u>` | `[u]…[/u]` |
| `<center>…</center>` | `[center]…[/center]` |

GitHub's sanitizer strips `<font>`, so colored spans preview uncolored in the
repo — content stays readable; the color only shows on Nexus. `<u>` and
`<center>` survive GitHub preview. The allowlist grows only when a real
description needs another tag.

### Loud errors, no silent mangling

The converter raises with a line number and reason for anything it does not
support, rather than passing it through or degrading it:

- tables, code fences, inline backticks
- `#` headings beyond the two structural ones; `####` or deeper
- nested lists; `*` or `+` bullet lines (bullets must use `-`, so a leading
  asterisk is never confused with italic)
- HTML tags outside the allowlist
- underscore emphasis (`_x_`) is **not** emphasis — underscores pass through
  literally (they appear in filenames like `modlist_compare`)

No escaping mechanism for literal `[`/`]`: square brackets pass through, which
only matters if prose accidentally looks like BBCode — not expected, and the
output is human-reviewed before pasting.

## Drafted content

`NEXUS_DESCRIPTION.md` is written as part of this work, sourced from
[the plugin README](../../../mo2-plugins/modlist_compare/README.md), in the
section style of the author's existing download-copier Nexus page:
What It Does / Key Features / How to Use / Requirements / Known Limitations.
The prose is a first pass for the author to edit; the structure exercises the
full supported subset.

## Tests

`tools/test_nexus_description.py`, run with the existing `tools/` unittest
suite:

- one case per supported construct (each table row above)
- inline composition (bold inside a list item, link inside bold)
- the 350-character limit failure, with count
- loud-error cases: table, code fence, inline backtick, deep heading, unknown
  HTML tag, markdown inside the short description
- round-trip of the real `NEXUS_DESCRIPTION.md`: converts without error,
  short description within limit

## Documentation updates

- CLAUDE.md: add `test_nexus_description` to the tools test command.
- Plugin README, Development section: one paragraph naming the source file,
  the script, and the paste workflow.

## Out of scope

- Packaging integration (`package_plugin.py` untouched)
- Multi-plugin generality — one hardcoded source file until a second plugin
  exists
- BBCode features with no markdown/allowlist mapping (spoilers, quotes,
  YouTube embeds)
