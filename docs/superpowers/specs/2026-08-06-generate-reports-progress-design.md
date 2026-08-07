# Generate Reports: progress dialog, cancellation, and dialog help text

**Date:** 2026-08-06
**Status:** Approved

## Problem

The plugin's Generate Reports dialog calls `report_runner.run_reports(...)` synchronously on
the Qt main thread (`dialog.py`, `_on_generate`). On large lists the matching work takes long
enough that MO2's window title shows "(Not Responding)" — the app looks frozen even though it
is working. Separately, the dialog's controls (List 1 vs List 2 roles, report types) are not
self-explanatory.

## Decisions made during brainstorming

- **True percent within reports**, not just per-report steps — progress callbacks are threaded
  through the shared generator code.
- **Cancellable** — a working Cancel button that stops at the next progress checkpoint.
- **QThread worker** — generation moves off the UI thread (rejected: `processEvents` pumping
  — re-entrancy hazards, masks rather than fixes; subprocess worker — temp-file round-trips
  for live exports, IPC overkill).
- **Inline hints + tooltips** for the dialog help text.

## 1. Progress plumbing through the shared generators (`tools/`)

Generation time is dominated by `modlist_utils.match_mods` (the phase 2/3 per-mod loops with
fuzzy `SequenceMatcher` comparisons). Progress comes from there:

- `match_mods(old_mods, new_mods, min_confidence=0.80, progress=None)` — `progress` is a
  callable `progress(done, total)` with `total = len(old_mods)`. It fires once after phase 1
  (with the bulk count of page-matched mods) and once per mod through the phase 2 and phase 3
  loops, climbing monotonically to `total`.
- Each generator's `generate(...)` gains the same optional `progress=None` parameter and
  forwards it to its one dominant `match_mods` call. For coverage that is one hop down through
  `build_report` into the plain (non-base) match call. Rendering is not tracked — it is
  near-instant next to matching.
- `report_runner.run_reports(..., progress=None)` — coarser UI-facing signature
  `progress(fraction, message)`: `fraction` spans 0.0–1.0 across all selected reports, equal
  slice per report (accurate: each report reruns the same matching over the same lists);
  `message` is e.g. `Generating coverage… (1 of 3)`.

Default `None` everywhere: the CLI tools, serve mode, and `regenerate.py` are unaffected; the
examples smoke test stays byte-identical.

## 2. Cancellation

- `class Cancelled(Exception)` lives in `report_runner`.
- The caller's progress callback raises it; it unwinds out of `match_mods` and `generate`
  naturally (they don't catch exceptions).
- `run_reports`'s per-report `except Exception` must re-raise `Cancelled` instead of recording
  it as a report error.
- Semantics on cancel: the in-progress report writes nothing (files are written only after
  `generate` returns), already-written reports stay on disk, and the save-exports step is
  skipped.

## 3. Worker thread + progress UI (`dialog.py`)

- `_on_generate` keeps everything up to and including `_resolve_side` on the main thread (it
  touches `mobase`). `run_reports` moves to a small `QThread` worker.
- The worker's progress callback: (a) checks a `threading.Event` cancel flag — set → raise
  `Cancelled`; (b) emits a `progress_changed(percent, message)` Qt signal, throttled to
  whole-percent changes so thousands of match callbacks don't queue thousands of signal
  deliveries.
- UI: a modal `QProgressDialog` (range 0–100, cancel button wired to the event,
  auto-close/auto-reset off). Modality prevents re-entry into the Generate dialog while
  running.
- On the worker's `finished(result, cancelled)` signal: close the progress dialog,
  `thread.quit()` / `thread.wait()`, then:
  - normal completion → existing `_show_result` + accept-on-no-errors behavior, unchanged;
  - cancelled → show the summary box only if some reports were already written (with a
    "Generation cancelled." line) and stay in the dialog.
- Worker exceptions other than `Cancelled` are caught in the worker and surfaced through the
  same result-errors path as today.

## 4. Dialog help text

Inline hints — small, muted (gray) `QLabel` captions:

- Under the two list rows: "Each side is the current MO2 profile (exported live) or a saved
  JSON export. Coverage: List 1 = source to pull from, List 2 = your list. Diff / Changelog:
  List 1 = old, List 2 = new."
- Under the destination row: "Reports are written to `<folder>/<List 2>/<List 1>.<type>`."

Tooltips (`setToolTip`, one-liner each):

- **Coverage** checkbox: "What List 2 is missing or has at a different version — what it could
  pull from List 1."
- **Diff** checkbox: "Side-by-side HTML of both lists' full ordering — adds, removes, moves,
  updates."
- **Changelog** checkbox: "Markdown summary of added, removed, and updated mods
  (List 1 → List 2)."
- Side picker combos: "'Current profile' exports the active MO2 profile live; 'JSON file…'
  uses a previous export."
- Save-export checkbox: "Also save the live profile's export as JSON in the destination
  folder, so you can reuse it later."

No layout rework, no logic changes.

## 5. Testing and packaging

Qt-free unit tests cover the logic:

- `match_mods`: progress called monotonically, ends at `(total, total)`, correct totals,
  default `None` unchanged behavior.
- Each `generate`: forwards `progress` to matching.
- `run_reports`: fraction mapping across 1–3 selected reports, message text, `Cancelled`
  propagation — partial writes kept, in-progress report absent, save-exports skipped, not
  swallowed into `result.errors`.

The `QThread`/`QProgressDialog` glue cannot run outside MO2; it stays thin and gets a manual
test in MO2 (re-run `tools/package_plugin.py` first — `report_runner` imports the vendored
copies). The examples smoke test (`regenerate` + `git diff --exit-code examples/reports`)
verifies no output drift.

## Out of scope

- Progress display for the CLI tools / `regenerate.py` (callbacks stay opt-in, default off).
- Base-update (`--base`) progress — the plugin dialog never uses base mode; only the plain
  match call reports progress.
- Sharing one `match_mods` result across the three reports (a performance optimization,
  orthogonal to this change).
