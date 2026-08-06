# Regenerate Reports — Design

**Date:** 2026-06-17
**Status:** Implemented (`tools/regenerate.py`)

## Problem

The workflow for the actively-maintained target list (currently `Meteoric 0.0.x`) is iterative:
re-export the list from MO2, drop the new JSON into `lists/`, then regenerate the same set of
comparison reports against several source lists. Today that means re-running six commands by
hand (`generate_coverage.py` and `generate_diff.py`, each against BottleRim 2.0.1, NORDIC SOULS
v3.0.1 - PBR Edition 1.4.0, and NORDIC SOULS v3.1.0). It is repetitive, easy to get an argument
wrong, and there is no single "refresh everything for this list" action.

## Goal

A one-shot way to **regenerate every report that already exists for a given list** by name —
`regenerate.py "Meteoric 0.0.5"` (or `/regenerate Meteoric 0.0.5`) re-runs exactly the reports
already present under `output/<list name>/`, with identical naming, after the underlying list
JSON has changed. The set of reports is discovered from disk, not configured — whatever exists
is what gets refreshed.

## Key insight

The output naming convention already encodes everything needed to regenerate a report. From
`modlist_utils.resolve_output_path`, a report lives at:

```
output/<folder = 2nd positional list>/<file = 1st positional list>.<type>.<ext>
```

So for any existing report file, the folder name is the 2nd positional argument, the filename
stem (before `.<type>.<ext>`) is the 1st positional argument, and the `<type>` segment selects
the generator. Regeneration is therefore: scan `output/<list name>/`, parse each filename back
into its arguments, and re-invoke the matching generator with `-o output/` (which reproduces the
exact same path).

Type → generator → extension map:

| type        | script                  | ext  | positional semantics       |
| ----------- | ----------------------- | ---- | -------------------------- |
| `coverage`  | `generate_coverage.py`  | html | 1st = source, 2nd = target |
| `diff`      | `generate_diff.py`      | html | 1st = old, 2nd = new       |
| `changelog` | `generate_changelog.py` | md   | 1st = old, 2nd = new       |

In every case the invocation is uniform: `python tools/generate_<type>.py
"lists/<first>.json" "lists/<list name>.json" -o output/` — first positional = filename stem,
second positional = the folder/list name.

## Decisions made during brainstorming

- **Form factor: Python script + slash command.** A tested `tools/regenerate.py` holds all the
  logic; a thin `.claude/commands/regenerate.md` wraps it for convenient invocation from Claude
  Code. The command adds no logic of its own.
- **Match scope: folder-only.** "By list name" means everything inside `output/<list name>/`
  (reports where that list is the 2nd-position target/new list). The broader "regenerate every
  report referencing this list in either position" was considered and deferred (YAGNI) — the
  current workflow always updates the target list, which is always the folder.
- **Invocation by subprocess, not in-process import.** `regenerate.py` shells out to the
  existing generators rather than importing them. The generators stay the single source of
  truth, output paths are guaranteed identical (same `resolve_output_path`), and nothing about
  the three generators changes. The in-process alternative (refactor each generator to expose a
  `generate(...)` function) was rejected as more invasive for a tool that runs in well under a
  second per report.
- **Right-to-left filename parsing.** Because list names contain dots (`BottleRim 2.0.1`), the
  filename is parsed from the right: strip the extension, then the trailing dotted segment must
  be a known type; the remainder is the 1st-position list name.
- **Skip-with-warning, not abort.** A file that doesn't match the `<first>.<type>.<ext>` pattern,
  has a mismatched `(type, ext)` pair, or whose source JSON is absent from `lists/` is skipped
  with a warning so one stray file cannot abort the whole run. A missing **target** list JSON
  (`lists/<list name>.json`) is a hard error — nothing can be regenerated without it.
- **No-argument behavior: list available folders.** Running with no list name prints the folders
  under `output/` and exits, for discoverability.

## Architecture

### Engine — `tools/regenerate.py`

Standard library only, consistent with the rest of `tools/`. Imports the sibling module for any
shared constants if useful (`from modlist_utils import ...`), mirroring the existing generators.

**Pure core — `plan_jobs(output_root, list_name, lists_dir)` → `list[Job]`**

The unit-testable seam. Lists `output_root/<list_name>/` and, for each file:

1. Strip the extension; split the remaining stem on the last `.` into `(first_list, type)`.
2. Validate `type` is one of `coverage` / `diff` / `changelog` and the original extension
   matches that type's expected ext. Mismatch → skip (collected as a warning).
3. Resolve input paths `lists_dir/<first_list>.json` and `lists_dir/<list_name>.json`. Missing
   source JSON → skip (warning). Missing target JSON → raise (hard error).
4. Emit a `Job` record: `{type, script, first_list, second_list (= list_name), source_path,
   target_path, expected_output}`.

`plan_jobs` performs no generation and no subprocess calls, so tests can assert the full plan
(scripts chosen, positional ordering, expected output paths, skip reasons) from a temp fixture.

**Runner / CLI — `main()`**

- Positional `list_name` (optional). Flags: `--dry-run` (print the plan, run nothing),
  `--lists DIR` (default `lists/`), `--output DIR` (default `output/`).
- No `list_name` → print available folders under `output/` and exit 0.
- Otherwise call `plan_jobs`, print any skip warnings, then (unless `--dry-run`) run each job via
  `subprocess` as `python tools/generate_<type>.py "<source>" "<target>" -o <output>/`.
- Print a per-report ✓ / skipped summary and exit non-zero if any job's subprocess failed.

### Slash command — `.claude/commands/regenerate.md`

Runs `python tools/regenerate.py "<args>"` from the repo root and relays the summary. With no
argument it runs the bare command (available-folders listing). No logic beyond invocation.

## Testing — `tools/test_regenerate.py`

Targets the pure `plan_jobs` against a temporary `output/<list>/` fixture (plus a temp `lists/`),
no heavy generation:

- Mixed `coverage` / `diff` / `changelog` files → correct script, positional ordering
  (first = filename stem, second = folder), and expected output path for each.
- List name with dots (`BottleRim 2.0.1.coverage.html`) parses correctly via right-to-left split.
- Unknown/stray file (`notes.txt`) and malformed `(type, ext)` pair (`X.coverage.md`) → skipped
  with a warning, absent from the plan.
- Report whose source JSON is missing from `lists/` → skipped with a warning.
- Missing target list JSON (`lists/<list name>.json`) → hard error.
- Empty / nonexistent `output/<list>/` → clean "nothing to do".

Runs with the existing suite: `cd tools && python -m unittest test_regenerate -v`.

## Documentation — `CLAUDE.md`

- Add a "Regenerate — `tools/regenerate.py`" subsection under **The Tools**, documenting the
  list-name argument, `--dry-run`, the folder-only scope, and the `/regenerate` slash command.
- Add `regenerate.py` and `test_regenerate.py` to the `tools/` tree diagram.
- Add `test_regenerate` to the testing section's command list.

## Out of scope (YAGNI for v1)

- `--min-confidence` passthrough to the generators (trivial to add later; the default has never
  been changed in this workflow).
- "Either-position" matching (regenerate every report referencing a list as source *or* target).
- Generating *new* report combinations — this tool only refreshes reports that already exist.
