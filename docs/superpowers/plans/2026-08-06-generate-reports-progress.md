# Generate Reports Progress Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A live percent progress dialog with a working Cancel button for the MO2 plugin's Generate Reports tool, plus concise inline hints and tooltips in the dialog.

**Architecture:** Progress callbacks thread through `match_mods` (where the time goes) → each generator's `generate()` → `report_runner.run_reports()` (which maps per-mod progress into an overall 0.0–1.0 fraction). The dialog runs `run_reports` on a `QThread` worker whose callback checks a cancel `threading.Event` and emits throttled Qt signals to a modal `QProgressDialog`. Spec: `docs/superpowers/specs/2026-08-06-generate-reports-progress-design.md`.

**Tech Stack:** Python 3 stdlib (tools), PyQt6 (plugin dialog only), `unittest`.

**Global Constraints:**
- All `progress` parameters default to `None`; with `None`, behavior and output are byte-identical to today (CLI, serve mode, `regenerate.py`, examples smoke test unaffected).
- `progress(done, total)` in `match_mods`/generators: `total = len(old_mods)` (source side), monotonically non-decreasing `done`, final call has `done == total`.
- `progress(fraction, message)` in `run_reports`: fraction in [0.0, 1.0], equal slice per selected report, message format `Generating <type>… (<i> of <n>)` (with the `…` ellipsis character).
- Only `dialog.py` may import Qt; `report_runner` and everything under `tools/` stay Qt-free and mobase-free.
- After changing anything under `tools/`, `python tools/package_plugin.py` must be re-run before plugin tests or manual MO2 testing (`report_runner` imports the vendored copies; `test_report_runner.py` re-vendors itself).

**User decisions (already made):**
- "True percent within reports" — callbacks go through the shared generator code, not just per-report steps.
- "Yes, cancellable" — Cancel stops at the next checkpoint; already-written reports stay on disk; in-progress report discarded; save-exports skipped.
- "QThread worker" — not processEvents pumping, not a subprocess.
- "Inline hints + tooltips" for the dialog help text; wording approved in the spec.
- One refinement over the spec's letter (same approved semantics): `run_reports` catches `Cancelled` internally and returns a `RunResult` with `cancelled=True` instead of letting it propagate — the dialog needs the partial `written` list to show what was kept, and an exception would lose it.

---

### Task 1: `match_mods` progress callback

**Goal:** `modlist_utils.match_mods` gains an optional `progress(done, total)` callback that climbs monotonically to `len(old_mods)`.

**Files:**
- Modify: `tools/modlist_utils.py` (`match_mods`, lines ~544–680)
- Test: `tools/test_modlist_utils.py`

**Acceptance Criteria:**
- [ ] `match_mods(old, new, progress=cb)` calls `cb(done, total)` with `total == len(old_mods)`, `done` non-decreasing, final call `done == total`
- [ ] Empty `old_mods` produces exactly one call `(0, 0)`
- [ ] Match results are identical with and without a callback
- [ ] Exceptions raised by the callback propagate to the caller (no `try` around it)

**Verify:** `cd tools && python -m unittest test_modlist_utils -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tools/test_modlist_utils.py` (after `MatchModsTest`; reuses the module's existing `_mod` helper):

```python
class MatchModsProgressTest(unittest.TestCase):
    def test_progress_monotonic_and_complete(self):
        old = [_mod("Alpha", id=1), _mod("Beta", id=2), _mod("Gamma")]
        new = [_mod("Alpha", id=1), _mod("Delta")]
        calls = []
        match_mods(old, new, progress=lambda done, total: calls.append((done, total)))
        self.assertTrue(calls)
        self.assertTrue(all(total == 3 for _done, total in calls))
        dones = [done for done, _total in calls]
        self.assertEqual(dones, sorted(dones))
        self.assertEqual(dones[-1], 3)

    def test_progress_empty_old_list(self):
        calls = []
        match_mods([], [_mod("Delta")], progress=lambda d, t: calls.append((d, t)))
        self.assertEqual(calls, [(0, 0)])

    def test_progress_does_not_change_results(self):
        old = [_mod("Alpha", id=1), _mod("Beta", id=2)]
        new = [_mod("Alpha", id=1), _mod("Wildcat", id=3)]
        with_cb = match_mods(old, new, progress=lambda d, t: None)
        without = match_mods(old, new)
        self.assertEqual(with_cb, without)

    def test_progress_callback_exception_propagates(self):
        def boom(done, total):
            raise RuntimeError("cancelled")
        with self.assertRaises(RuntimeError):
            match_mods([_mod("Alpha")], [_mod("Beta")], progress=boom)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd tools && python -m unittest test_modlist_utils.MatchModsProgressTest -v`
Expected: FAIL/ERROR — `match_mods() got an unexpected keyword argument 'progress'`

- [ ] **Step 3: Implement**

In `tools/modlist_utils.py`, change the signature and docstring:

```python
def match_mods(old_mods, new_mods, min_confidence=0.80, progress=None):
    """
    Match mods between old and new lists using waterfall strategy.
    Returns (matched_pairs, added_mods, removed_mods).

    progress, when given, is called as progress(done, total) with
    total == len(old_mods): once after the per-page phase (with the bulk
    count of page-matched mods) and once per mod through the plugin and
    name phases, so done climbs monotonically to total. Exceptions raised
    by the callback propagate to the caller (cancellation relies on this).
    """
```

Immediately after the existing `unmatched_old = [m for m in old_mods if id(m) not in matched_old_ids]` (end of phase 1), insert:

```python
    total = len(old_mods)
    done = total - len(unmatched_old)
    if progress is not None:
        progress(done, total)
```

In the phase 2 loop, add a per-mod tick at the end of each iteration (after the `if result: ... else: ...` block, inside the `for`):

```python
        done += 1
        if progress is not None:
            progress(done, total)
```

Add the identical two-line tick at the end of each phase 3 loop iteration (after its `if result: ... else: ...` block).

- [ ] **Step 4: Run the full module's tests**

Run: `cd tools && python -m unittest test_modlist_utils -v`
Expected: all PASS (existing tests prove default-`None` behavior unchanged)

- [ ] **Step 5: Commit**

```bash
git add tools/modlist_utils.py tools/test_modlist_utils.py
git commit -m "feat: optional progress callback in match_mods"
```

---

### Task 2: Generators forward `progress`

**Goal:** All three `generate()` entry points accept `progress=None` and forward it to their dominant `match_mods` call.

**Files:**
- Modify: `tools/generate_changelog.py` (`generate`, line ~119)
- Modify: `tools/generate_diff.py` (`generate`, line ~871)
- Modify: `tools/generate_coverage.py` (`generate` line ~856, `build_report` line ~176, `classify_source_mods` line ~219)
- Test: `tools/test_generate_changelog.py`, `tools/test_generate_diff.py`, `tools/test_generate_coverage.py`

**Acceptance Criteria:**
- [ ] Each `generate(..., progress=cb)` invokes `cb`, final call `done == total` with `total > 0` on the example fixtures
- [ ] Coverage forwards only on the plain path (`matched is None` in `classify_source_mods`); base mode stays progress-free
- [ ] No output change when `progress` is omitted (full suite + examples smoke test stay green)

**Verify:** `cd tools && python -m unittest test_generate_coverage test_generate_diff test_generate_changelog -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

All three test files already `import os`, `import unittest`, and import their module by name (`import generate_changelog` / `import generate_diff` / `import generate_coverage`). Append to each the class below — identical except for the `generate` call on the marked line.

To `tools/test_generate_changelog.py`:

```python
_PROGRESS_LISTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "examples", "lists"
)


class GenerateProgressTest(unittest.TestCase):
    def _load(self, name):
        from modlist_utils import load_modlist
        return load_modlist(os.path.join(_PROGRESS_LISTS, name))

    def test_generate_forwards_progress(self):
        calls = []
        old = self._load("Example List 1.0.json")
        new = self._load("Example List 1.1.json")
        generate_changelog.generate(
            old, new, progress=lambda d, t: calls.append((d, t))
        )
        self.assertTrue(calls)
        done, total = calls[-1]
        self.assertGreater(total, 0)
        self.assertEqual(done, total)
```

To `tools/test_generate_diff.py`: the same class, with the call replaced by

```python
        generate_diff.generate(
            old, new, "Old", "New", progress=lambda d, t: calls.append((d, t))
        )
```

To `tools/test_generate_coverage.py`: the same class, with the call replaced by

```python
        generate_coverage.generate(
            old, new, "Src", "Tgt", progress=lambda d, t: calls.append((d, t))
        )
```

- [ ] **Step 2: Run to verify all three fail**

Run: `cd tools && python -m unittest test_generate_coverage.GenerateProgressTest test_generate_diff.GenerateProgressTest test_generate_changelog.GenerateProgressTest -v`
Expected: FAIL/ERROR — unexpected keyword argument `progress`

- [ ] **Step 3: Implement forwarding**

`tools/generate_changelog.py`:

```python
def generate(old_data, new_data, min_confidence=0.80, progress=None):
```

and change its match call to:

```python
    matched, added, removed = match_mods(old_mods, new_mods, min_confidence,
                                         progress=progress)
```

`tools/generate_diff.py`:

```python
def generate(old_data, new_data, old_name, new_name, min_confidence=0.80,
             progress=None):
```

```python
    matched_pairs, added_mods, removed_mods = match_mods(
        old_mods, new_mods, min_confidence, progress=progress
    )
```

`tools/generate_coverage.py` — three hops. `classify_source_mods`:

```python
def classify_source_mods(source_data, target_data, min_confidence=0.80, ignore=None,
                         base_changes=None, matched=None, progress=None):
```

```python
    if matched is None:
        matched, _added, _removed = match_mods(source_mods, target_mods,
                                               min_confidence, progress=progress)
```

`build_report` (forward only into `classify_source_mods` — the base-mode match calls earlier in the function stay untouched):

```python
def build_report(source_data, target_data, min_confidence, ignore, base_data=None,
                 progress=None):
```

```python
    rows_by_section = classify_source_mods(
        source_data, target_data, min_confidence, ignore, base_changes,
        matched=matched, progress=progress,
    )
```

`generate`:

```python
def generate(source_data, target_data, source_name, target_name,
             min_confidence=0.80, ignore=None, base_data=None, base_name=None,
             progress=None):
```

```python
    rows_by_section = build_report(
        source_data, target_data, min_confidence, ignore, base_data,
        progress=progress,
    )
```

In each of the three `generate` docstrings add one line: `progress is forwarded to match_mods — see modlist_utils.match_mods.`

- [ ] **Step 4: Run tests + smoke test**

Run: `cd tools && python -m unittest test_generate_coverage test_generate_diff test_generate_changelog test_examples -v`
Expected: all PASS

Run: `python tools/regenerate.py "Example List 1.1" --lists examples/lists --output examples/reports && git diff --exit-code examples/reports`
Expected: exit 0, no diff

- [ ] **Step 5: Commit**

```bash
git add tools/generate_changelog.py tools/generate_diff.py tools/generate_coverage.py tools/test_generate_changelog.py tools/test_generate_diff.py tools/test_generate_coverage.py
git commit -m "feat: generators forward progress callback to match_mods"
```

---

### Task 3: `report_runner` progress mapping + cancellation

**Goal:** `run_reports` gains `progress(fraction, message)` spanning all selected reports, and a `Cancelled` exception a callback can raise to abort with clean semantics.

**Files:**
- Modify: `mo2-plugins/modlist_compare/report_runner.py`
- Test: `mo2-plugins/modlist_compare/test_report_runner.py`

**Acceptance Criteria:**
- [ ] Fractions are monotonically non-decreasing and end at exactly `1.0` on a completed run
- [ ] Messages read `Generating coverage… (1 of 2)` / `Generating changelog… (2 of 2)` for a two-report run
- [ ] Callback raising `report_runner.Cancelled` → returned `RunResult.cancelled` is `True`, earlier reports remain in `written`, the in-progress report's file does not exist, `errors` is empty, and live-side JSON exports are skipped
- [ ] `Cancelled` is never recorded in `result.errors`

**Verify:** `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v` (repo root) → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `mo2-plugins/modlist_compare/test_report_runner.py`:

```python
class RunReportsProgressTest(unittest.TestCase):
    def test_progress_monotonic_labeled_and_complete(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                _side(OLD_LIST), _side(NEW_LIST), ["coverage", "changelog"], tmp,
                save_exports=False,
                progress=lambda fraction, message: calls.append((fraction, message)),
            )
        self.assertEqual(result.errors, [])
        self.assertFalse(result.cancelled)
        fractions = [f for f, _m in calls]
        self.assertEqual(fractions, sorted(fractions))
        self.assertEqual(fractions[-1], 1.0)
        messages = {m for _f, m in calls}
        self.assertIn("Generating coverage… (1 of 2)", messages)
        self.assertIn("Generating changelog… (2 of 2)", messages)

    def test_cancel_keeps_earlier_reports_skips_rest_and_exports(self):
        def cancel_on_changelog(fraction, message):
            if "changelog" in message:
                raise report_runner.Cancelled()
        live = report_runner.ListSide(
            name="Live Profile", data=_side(OLD_LIST).data, live=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                live, _side(NEW_LIST), ["coverage", "changelog"], tmp,
                save_exports=True, progress=cancel_on_changelog,
            )
            self.assertTrue(result.cancelled)
            self.assertEqual(result.errors, [])
            self.assertEqual(len(result.written), 1)
            self.assertTrue(result.written[0].endswith("Live Profile.coverage.html"))
            self.assertFalse(
                os.path.exists(os.path.join(tmp, "Live Profile.json"))
            )
```

- [ ] **Step 2: Run to verify they fail**

Run (repo root): `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v`
Expected: the two new tests FAIL/ERROR (`unexpected keyword argument 'progress'` / no attribute `Cancelled`); the rest pass

- [ ] **Step 3: Implement**

In `report_runner.py`, add after the `_EXTENSIONS` constant:

```python
class Cancelled(Exception):
    """Raised by a progress callback to abort generation at a checkpoint."""
```

Add the field to `RunResult`:

```python
@dataclass
class RunResult:
    written: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    cancelled: bool = False
```

Rework `run_reports` (docstring addition + loop; the save-exports block only gains the `not result.cancelled` guard):

```python
def run_reports(list1, list2, report_types, dest_dir, save_exports=True,
                min_confidence=0.80, progress=None):
    """Generate the selected reports from two sides into dest_dir.

    Naming matches the CLI: <dest>/<list2.name>/<list1.name>.<type>.<ext>.
    Coverage reads <dest>/<list2.name>/.coverage-ignore.txt like a static run.
    Per-report failures land in RunResult.errors; the rest still run.

    progress, when given, is called as progress(fraction, message): fraction
    spans 0.0-1.0 across all selected reports (equal slice per report, since
    each reruns the same matching), message reads "Generating <type>… (i of n)".
    A callback that raises Cancelled aborts the run: the in-progress report
    writes nothing, earlier reports stay, save_exports is skipped, and the
    returned RunResult has cancelled=True.
    """
    result = RunResult()
    # resolve_output_path derives names from paths; hand it synthetic filenames
    # so plugin and CLI naming can never drift.
    first = list1.name + ".json"
    second = list2.name + ".json"
    dest = dest_dir if dest_dir.endswith(("/", "\\")) else dest_dir + os.sep
    count = len(report_types)

    for i, rtype in enumerate(report_types):
        message = f"Generating {rtype}… ({i + 1} of {count})"

        def sub_progress(done, total, _i=i, _message=message):
            if progress is not None and total:
                progress((_i + done / total) / count, _message)

        if progress is not None:
            progress(i / count, message)
        try:
            if rtype == "coverage":
                ignore = coverage_ignore.load_ignore(
                    coverage_ignore.resolve_ignore_path(dest, second)
                )
                text = generate_coverage.generate(
                    list1.data, list2.data, list1.name, list2.name,
                    min_confidence=min_confidence, ignore=ignore,
                    progress=sub_progress,
                )
            elif rtype == "diff":
                text = generate_diff.generate(
                    list1.data, list2.data, list1.name, list2.name,
                    min_confidence=min_confidence, progress=sub_progress,
                )
            elif rtype == "changelog":
                text = generate_changelog.generate(
                    list1.data, list2.data, min_confidence=min_confidence,
                    progress=sub_progress,
                )
            else:
                raise ValueError(f"unknown report type: {rtype}")
            out_path = modlist_utils.resolve_output_path(
                dest, first, second, rtype, _EXTENSIONS[rtype]
            )
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            result.written.append(out_path)
        except Cancelled:
            result.cancelled = True
            break
        except Exception as e:
            result.errors.append(f"{rtype}: {e}")

    if save_exports and not result.cancelled:
        for side in (list1, list2):
            if not side.live:
                continue
            try:
                # Only resolve_output_path creates dest_dir, and it may not have
                # run (no reports selected, or every one failed).
                os.makedirs(dest_dir, exist_ok=True)
                path = os.path.join(dest_dir, side.name + ".json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(side.data, f, indent=2, ensure_ascii=False)
                result.written.append(path)
            except Exception as e:
                result.errors.append(f"export {side.name}: {e}")
    return result
```

Note the vendored generators must already have `progress` support — run `python tools/package_plugin.py` if `_vendor/` is stale (the test file re-vendors on import, so tests are safe either way).

- [ ] **Step 4: Run to verify pass**

Run (repo root): `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add mo2-plugins/modlist_compare/report_runner.py mo2-plugins/modlist_compare/test_report_runner.py
git commit -m "feat: run_reports progress mapping and Cancelled abort"
```

---

### Task 4: QThread worker + QProgressDialog in the dialog

**Goal:** `_on_generate` runs `run_reports` on a worker thread behind a modal cancellable progress dialog; the UI thread never blocks.

**Files:**
- Modify: `mo2-plugins/modlist_compare/dialog.py`

**Acceptance Criteria:**
- [ ] `run_reports` executes on a `QThread`, not the UI thread; `mobase` and all Qt widgets are only touched on the main thread
- [ ] Progress dialog shows percent + `Generating <type>… (i of n)`, updates throttled to whole-percent changes
- [ ] Cancel button (or closing the progress dialog) requests cancel; label flips to "Cancelling…"; generation stops at the next checkpoint
- [ ] Normal completion preserves today's behavior exactly (`_show_result`, auto-accept when no errors)
- [ ] Cancelled completion: result box (with "Generation cancelled." line, Warning icon) shown only if something was written; the Generate dialog stays open
- [ ] No automated test (Qt-only glue) — verified manually in Task 6

**Verify:** `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v` still passes (dialog.py is not imported by these tests, but the commit must not break them); full manual check happens in Task 6

**Steps:**

- [ ] **Step 1: Add imports and the worker class**

In `dialog.py`, extend the imports:

```python
import os
import threading

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
)
```

Add above `GenerateReportsDialog`:

```python
class _ReportWorker(QThread):
    """Runs report_runner.run_reports off the UI thread.

    The progress callback runs on this thread: it first honors a pending
    cancel request by raising Cancelled, then emits progress_changed,
    throttled to whole-percent changes so thousands of match callbacks
    don't queue thousands of signal deliveries.
    """

    progress_changed = pyqtSignal(int, str)
    done = pyqtSignal(object)  # RunResult (its .cancelled reflects an abort)

    def __init__(self, parent, side1, side2, report_types, dest, save_exports):
        super().__init__(parent)
        self._args = (side1, side2, report_types, dest, save_exports)
        self.cancel_event = threading.Event()
        self._last_percent = -1

    def _on_progress(self, fraction, message):
        if self.cancel_event.is_set():
            raise report_runner.Cancelled()
        percent = max(0, min(100, int(fraction * 100)))
        if percent != self._last_percent:
            self._last_percent = percent
            self.progress_changed.emit(percent, message)

    def run(self):
        side1, side2, report_types, dest, save_exports = self._args
        try:
            result = report_runner.run_reports(
                side1, side2, report_types, dest,
                save_exports=save_exports, progress=self._on_progress,
            )
        except Exception as e:
            # Unexpected failure: surface through the same errors path the
            # result box already renders.
            result = report_runner.RunResult(errors=[str(e)])
        self.done.emit(result)
```

- [ ] **Step 2: Replace the synchronous tail of `_on_generate`**

Replace the last four lines of `_on_generate` (from `self._save_state()` through the `self.accept()` block) with:

```python
        self._save_state()
        self._worker = _ReportWorker(
            self, side1, side2, report_types, dest,
            self._save_export_box.isChecked(),
        )
        self._progress = QProgressDialog("Preparing…", "Cancel", 0, 100, self)
        self._progress.setWindowTitle(_TITLE)
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.setMinimumDuration(0)
        self._progress.canceled.connect(self._on_cancel_clicked)
        self._worker.progress_changed.connect(self._on_progress_changed)
        self._worker.done.connect(lambda result: self._on_reports_done(result, dest))
        self._progress.show()
        self._worker.start()
```

- [ ] **Step 3: Add the three handlers**

Add to `GenerateReportsDialog`, after `_on_generate`:

```python
    def _on_cancel_clicked(self):
        self._worker.cancel_event.set()
        self._progress.setLabelText("Cancelling…")

    def _on_progress_changed(self, percent, message):
        if self._worker.cancel_event.is_set():
            return  # a cancel is pending; keep "Cancelling…" on screen
        self._progress.setLabelText(message)
        self._progress.setValue(percent)

    def _on_reports_done(self, result, dest):
        self._worker.wait()
        # close() fires canceled; disconnect first so a normal finish doesn't
        # route through the cancel handler.
        self._progress.canceled.disconnect(self._on_cancel_clicked)
        self._progress.close()
        self._progress = None
        self._worker = None
        if result.cancelled:
            if result.written:
                self._show_result(result, dest, cancelled=True)
            return
        self._show_result(result, dest)
        if not result.errors:
            self.accept()
```

- [ ] **Step 4: Extend `_show_result` for the cancelled case**

Replace `_show_result`'s signature and the first/icon lines:

```python
    def _show_result(self, result, dest, cancelled=False):
        lines = []
        if cancelled:
            lines.append("Generation cancelled.")
            lines.append("")
        if result.written:
            lines.append("Written:")
            lines.extend(f"  {p}" for p in result.written)
        if result.errors:
            lines.append("")
            lines.append("Errors:")
            lines.extend(f"  {e}" for e in result.errors)
        box = QMessageBox(self)
        box.setWindowTitle(_TITLE)
        box.setIcon(
            QMessageBox.Icon.Warning if cancelled
            else QMessageBox.Icon.Critical if not result.written
            else QMessageBox.Icon.Warning if result.errors
            else QMessageBox.Icon.Information
        )
```

(the rest of the method is unchanged)

- [ ] **Step 5: Sanity-check imports and commit**

Run (repo root): `python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v`
Expected: all PASS (no regression from the dialog change)

Run: `python -c "import ast; ast.parse(open('mo2-plugins/modlist_compare/dialog.py', encoding='utf-8').read())"`
Expected: no output (syntax valid; PyQt6 may not be importable outside MO2, so a parse check is the honest gate here)

```bash
git add mo2-plugins/modlist_compare/dialog.py
git commit -m "feat: report generation on worker thread with cancellable progress dialog"
```

---

### Task 5: Dialog help text (inline hints + tooltips)

**Goal:** Concise muted captions and hover tooltips explaining the dialog's parts, with the approved wording.

**Files:**
- Modify: `mo2-plugins/modlist_compare/dialog.py` (`_build_ui`, `_SidePicker.__init__`)

**Acceptance Criteria:**
- [ ] Muted, word-wrapped caption under the list rows and a second one under the destination row, wording exactly as in the spec
- [ ] Tooltips on the three report checkboxes, both side-picker combos, and the save-export checkbox, wording exactly as in the spec
- [ ] No logic changes; grid rows renumbered consistently

**Verify:** `python -c "import ast; ast.parse(open('mo2-plugins/modlist_compare/dialog.py', encoding='utf-8').read())"` → no output; visual check in Task 6

**Steps:**

- [ ] **Step 1: Tooltip on the side-picker combos**

In `_SidePicker.__init__`, after `self.combo.addItems(...)`:

```python
        self.combo.setToolTip(
            "'Current profile' exports the active MO2 profile live; "
            "'JSON file…' uses a previous export."
        )
```

- [ ] **Step 2: Rework `_build_ui` rows with hints and tooltips**

Replace the body of `_build_ui` from `grid.addWidget(QLabel("Reports:"), 2, 0)` through the `grid.addLayout(buttons, 5, 0, 1, 4)` line with (rows shift down to make room for the two hint labels):

```python
        list_hint = QLabel(
            "Each side is the current MO2 profile (exported live) or a saved "
            "JSON export. Coverage: List 1 = source to pull from, List 2 = "
            "your list. Diff / Changelog: List 1 = old, List 2 = new."
        )
        list_hint.setWordWrap(True)
        list_hint.setStyleSheet("color: gray;")
        grid.addWidget(list_hint, 2, 0, 1, 4)

        grid.addWidget(QLabel("Reports:"), 3, 0)
        reports_row = QHBoxLayout()
        self._report_boxes = {}
        tooltips = {
            "coverage": "What List 2 is missing or has at a different version "
                        "— what it could pull from List 1.",
            "diff": "Side-by-side HTML of both lists' full ordering — adds, "
                    "removes, moves, updates.",
            "changelog": "Markdown summary of added, removed, and updated mods "
                         "(List 1 → List 2).",
        }
        for rtype, label in (("coverage", "Coverage"), ("diff", "Diff"),
                             ("changelog", "Changelog")):
            box = QCheckBox(label)
            box.setToolTip(tooltips[rtype])
            self._report_boxes[rtype] = box
            reports_row.addWidget(box)
        reports_row.addStretch()
        grid.addLayout(reports_row, 3, 1, 1, 3)

        grid.addWidget(QLabel("Destination folder:"), 4, 0)
        self._dest_edit = QLineEdit()
        dest_btn = QPushButton("Browse…")
        dest_btn.clicked.connect(self._browse_dest)
        grid.addWidget(self._dest_edit, 4, 1, 1, 2)
        grid.addWidget(dest_btn, 4, 3)

        dest_hint = QLabel("Reports are written to <folder>/<List 2>/<List 1>.<type>.")
        dest_hint.setStyleSheet("color: gray;")
        grid.addWidget(dest_hint, 5, 0, 1, 4)

        self._save_export_box = QCheckBox(
            'Save "Current profile" export as JSON'
        )
        self._save_export_box.setToolTip(
            "Also save the live profile's export as JSON in the destination "
            "folder, so you can reuse it later."
        )
        grid.addWidget(self._save_export_box, 6, 0, 1, 4)

        buttons = QHBoxLayout()
        generate_btn = QPushButton("Generate")
        generate_btn.setDefault(True)
        generate_btn.clicked.connect(self._on_generate)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(generate_btn)
        buttons.addWidget(cancel_btn)
        grid.addLayout(buttons, 7, 0, 1, 4)
```

- [ ] **Step 3: Parse-check and commit**

Run: `python -c "import ast; ast.parse(open('mo2-plugins/modlist_compare/dialog.py', encoding='utf-8').read())"`
Expected: no output

```bash
git add mo2-plugins/modlist_compare/dialog.py
git commit -m "feat: inline hints and tooltips in Generate Reports dialog"
```

---

### Task 6: Package, full verification, docs, version bump

**Goal:** Vendored copies refreshed, every suite green, examples byte-identical, plugin version bumped, README notes the new behavior; manual MO2 checklist handed to the user.

**Files:**
- Modify: `mo2-plugins/modlist_compare/plugin_tools.py` (VERSION line 12)
- Modify: `mo2-plugins/modlist_compare/README.md`

**Acceptance Criteria:**
- [ ] `python tools/package_plugin.py` rebuilds `_vendor/` and `dist/modlist-compare-1.1.0.zip`
- [ ] Both unittest suites pass; examples smoke test shows no diff
- [ ] README's Generate Reports section mentions the progress dialog, Cancel semantics, and the new hints
- [ ] Manual MO2 checklist delivered to the user (progress bar advances, cancel works, tooltips/hints visible, "(Not Responding)" gone)

**Verify:** the three commands in Step 2, all exiting 0

**Steps:**

- [ ] **Step 1: Version bump and README**

In `plugin_tools.py`: `VERSION = mobase.VersionInfo(1, 1, 0)`

In `mo2-plugins/modlist_compare/README.md`, in the Generate Reports section, add a short paragraph:

```markdown
While reports generate, a progress dialog shows live percent and which report
is running; MO2 stays responsive. **Cancel** stops at the next checkpoint —
reports already written stay on disk, the in-progress one is discarded, and
live-profile JSON exports are skipped. Hover any control in the dialog for a
short explanation of what it does.
```

- [ ] **Step 2: Package and run everything**

```bash
python tools/package_plugin.py
cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin -v && cd ..
python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v
python tools/regenerate.py "Example List 1.1" --lists examples/lists --output examples/reports && git diff --exit-code examples/reports
```

Expected: all PASS, smoke test exits 0 with no diff, `dist/modlist-compare-1.1.0.zip` exists.

- [ ] **Step 3: Commit**

```bash
git add mo2-plugins/modlist_compare/plugin_tools.py mo2-plugins/modlist_compare/README.md
git commit -m "chore: bump plugin to 1.1.0; document progress dialog and hints"
```

- [ ] **Step 4: Hand the user the manual MO2 checklist**

Report completion and ask the user to unzip `dist/modlist-compare-1.1.0.zip` into MO2's `plugins/` and verify:
1. Generate Reports on a large list → progress dialog appears immediately, percent climbs, label names the current report; MO2 title bar never shows "(Not Responding)".
2. Click Cancel mid-run → label flips to "Cancelling…", run stops, result box lists only the reports written before cancel, dialog stays open.
3. Hover the report checkboxes / combos / save-export box → tooltips; hints visible under the list rows and destination row.

Do not claim MO2-verified until the user confirms.
