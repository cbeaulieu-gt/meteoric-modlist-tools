"""Generate Reports dialog for the Modlist Compare plugin."""
import os
import sys
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
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from . import exporter_core, report_runner

JSON_FILE = "JSON file…"
_TITLE = "Generate Reports"
_FILE_TOKEN = "file"
_PROFILE_PREFIX = "profile:"


class _SidePicker:
    """Widgets for one list side (not itself a QWidget).

    Combo items carry a stable token as item data: "profile:<name>" for a
    profile (the active one is labelled "Current profile (<name>)") or "file".
    """

    def __init__(self, on_browse, active, profiles):
        self.combo = QComboBox()
        self.combo.addItem(
            f"Current profile ({active})", _PROFILE_PREFIX + active
        )
        for name in profiles:
            if name.casefold() != active.casefold():
                self.combo.addItem(name, _PROFILE_PREFIX + name)
        self.combo.addItem(JSON_FILE, _FILE_TOKEN)
        self.combo.setToolTip(
            "Any MO2 profile (the current one is exported live, others are "
            "read from their modlist.txt); 'JSON file…' uses a previous export."
        )
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(on_browse)
        self.combo.currentIndexChanged.connect(self._sync_enabled)
        self._sync_enabled()

    def _sync_enabled(self, _index=None):
        is_file = self.token() == _FILE_TOKEN
        self.path_edit.setEnabled(is_file)
        self.browse_btn.setEnabled(is_file)

    def token(self):
        return str(self.combo.currentData())

    def selection(self):
        """("profile", <profile name>) or ("file", "")."""
        token = self.token()
        if token.startswith(_PROFILE_PREFIX):
            return ("profile", token[len(_PROFILE_PREFIX):])
        return ("file", "")

    def select_token(self, token):
        """Select the item with this token if present; otherwise leave as is."""
        index = self.combo.findData(token)
        if index >= 0:
            self.combo.setCurrentIndex(index)

    def path(self):
        return self.path_edit.text().strip()


class _ReportWorker(QThread):
    """Runs report_runner.run_reports off the UI thread.

    The progress callback runs on this thread: it first honors a pending
    cancel request by raising Cancelled, then emits progress_changed,
    throttled to changes in (whole percent, message) so thousands of match
    callbacks don't queue thousands of signal deliveries.

    done is emitted exactly once, from a finally: the dialog it drives is
    modal and only closes on that signal, so a thread that ended without
    emitting would wedge the UI forever.
    """

    progress_changed = pyqtSignal(int, str)
    done = pyqtSignal(object)  # RunResult (its .cancelled reflects an abort)

    def __init__(self, parent, side1, side2, report_types, dest, save_exports,
                 base=None, categories=None):
        super().__init__(parent)
        self._args = (side1, side2, report_types, dest, save_exports, base)
        self._categories = categories
        self.cancel_event = threading.Event()
        self._last_emitted = None

    def _on_progress(self, fraction, message):
        if self.cancel_event.is_set():
            raise report_runner.Cancelled()
        percent = max(0, min(100, int(fraction * 100)))
        # Throttle on (percent, message), not percent alone: consecutive
        # reports can start on the same integer percent, and dropping those
        # would leave a stale "Generating <type>…" label on screen.
        current = (percent, message)
        if current != self._last_emitted:
            self._last_emitted = current
            self.progress_changed.emit(percent, message)

    def run(self):
        result = None
        # A compute-bound thread makes every GIL reacquisition on the main
        # thread wait up to the switch interval, and PyQt releases/reacquires
        # the GIL around each C++ call — so any plugin doing Python work on
        # the main thread (measured live: a widget-tree scan in another
        # installed plugin) runs hundreds of times slower and freezes MO2's
        # event loop. At 0.2ms the amplification disappears and generation
        # itself is not measurably slower.
        old_interval = sys.getswitchinterval()
        sys.setswitchinterval(0.0002)
        try:
            side1, side2, report_types, dest, save_exports, base = self._args
            result = report_runner.run_reports(
                side1, side2, report_types, dest,
                save_exports=save_exports, progress=self._on_progress,
                base=base, categories=self._categories,
            )
        except BaseException as e:
            # Unexpected failure: surface through the same errors path the
            # result box already renders. BaseException, not Exception, so
            # nothing can end this thread without a done emission. The type
            # name is included because bare exceptions (KeyError()) str() to
            # an empty line.
            try:
                result = report_runner.RunResult(
                    errors=[f"{type(e).__name__}: {e}"]
                )
            except BaseException:
                result = None  # the finally builds a last-resort result
        finally:
            sys.setswitchinterval(old_interval)
            if result is None:
                result = report_runner.RunResult(
                    errors=["report generation failed unexpectedly"]
                )
            self.done.emit(result)


class _ProgressDialog(QDialog):
    """A modal progress dialog that only the worker's finish can dismiss.

    Deliberately NOT a QProgressDialog: when modal, its setValue() pumps the
    event loop (processEvents) from inside the caller's slot, re-entering
    arbitrary event handlers — observed live running another plugin's
    main-window scan for seconds from within a progress update. A plain
    QProgressBar update has no such side channel. It also drops
    QProgressDialog's cancel-hides-the-dialog behavior, which previously
    needed a re-show workaround.

    Esc (reject) and the window's X (closeEvent) would otherwise hide the
    dialog while the worker is still running, and a hidden window-modal
    dialog imposes no modality at all. Both routes are redirected to the same
    cancel request the Cancel button makes, and the dialog stays up until
    _on_reports_done hides it.
    """

    def __init__(self, parent, on_cancel):
        super().__init__(parent)
        self._on_cancel = on_cancel
        self.setWindowTitle(_TITLE)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        self._label = QLabel("Preparing…")
        layout.addWidget(self._label)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        layout.addWidget(self._bar)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        buttons.addWidget(self._cancel_btn)
        layout.addLayout(buttons)

    def setLabelText(self, text):
        self._label.setText(text)

    def setValue(self, value):
        self._bar.setValue(value)

    def disable_cancel(self):
        self._cancel_btn.setEnabled(False)

    def reject(self):
        # Esc lands here.
        self._on_cancel()

    def closeEvent(self, event):
        self._on_cancel()
        event.ignore()


class GenerateReportsDialog(QDialog):
    def __init__(self, parent, organizer, plugin_name):
        super().__init__(parent)
        self._organizer = organizer
        self._plugin_name = plugin_name
        self._worker = None
        self._progress = None
        self.setWindowTitle(_TITLE)
        self.setMinimumWidth(560)
        self._build_ui()
        self._restore_state()

    # ---- persistence -----------------------------------------------------

    def _get(self, key, default):
        return self._organizer.persistent(self._plugin_name, key, default)

    def _set(self, key, value):
        self._organizer.setPersistent(self._plugin_name, key, value)

    def _restore_state(self):
        self._dest_edit.setText(str(self._get("dest_dir", "")))
        saved = str(self._get("reports", "coverage,diff"))
        chosen = {r for r in saved.split(",") if r}
        for rtype, box in self._report_boxes.items():
            box.setChecked(rtype in chosen)
        self._save_export_box.setChecked(str(self._get("save_export", "true")) == "true")
        self._enabled_only_box.setChecked(
            str(self._get("enabled_only", "false")) == "true")
        self._side1.select_token(str(self._get("side1", "")))
        self._side2.select_token(str(self._get("side2", "")))

    def _save_state(self):
        self._set("dest_dir", self._dest_edit.text().strip())
        self._set("reports", ",".join(
            r for r, box in self._report_boxes.items() if box.isChecked()
        ))
        self._set("save_export", "true" if self._save_export_box.isChecked() else "false")
        self._set("enabled_only",
                  "true" if self._enabled_only_box.isChecked() else "false")
        self._set("side1", self._side1.token())
        self._set("side2", self._side2.token())

    # ---- UI --------------------------------------------------------------

    def _build_ui(self):
        grid = QGridLayout(self)

        active = exporter_core.active_profile_name(self._organizer)
        try:
            profiles = exporter_core.list_profiles(self._organizer)
        except Exception:
            profiles = []
        self._side1 = _SidePicker(
            lambda: self._browse_side(self._side1), active, profiles)
        self._side2 = _SidePicker(
            lambda: self._browse_side(self._side2), active, profiles)
        for row, (label, side) in enumerate(
            (("List 1 (source / old):", self._side1),
             ("List 2 (target / new):", self._side2))
        ):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(side.combo, row, 1)
            grid.addWidget(side.path_edit, row, 2)
            grid.addWidget(side.browse_btn, row, 3)

        list_hint = QLabel(
            "Each side is any MO2 profile or a saved JSON export. Coverage: "
            "List 1 = source to pull from, List 2 = your list. Diff / "
            "Changelog: List 1 = old, List 2 = new. Rebase: List 1 = the new "
            "base, List 2 = your custom list (plus the previous base below)."
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
            "rebase": "Only what changed in the base update: List 1 = new "
                      "base, List 2 = your custom list. Needs the previous "
                      "base JSON.",
        }
        for rtype, label in (("coverage", "Coverage"), ("diff", "Diff"),
                             ("changelog", "Changelog"), ("rebase", "Rebase")):
            box = QCheckBox(label)
            box.setToolTip(tooltips[rtype])
            self._report_boxes[rtype] = box
            reports_row.addWidget(box)
        reports_row.addStretch()
        grid.addLayout(reports_row, 3, 1, 1, 3)

        grid.addWidget(QLabel("Previous base:"), 4, 0)
        self._base_edit = QLineEdit()
        self._base_edit.setReadOnly(True)
        base_btn = QPushButton("Browse…")
        base_btn.clicked.connect(self._browse_base)
        grid.addWidget(self._base_edit, 4, 1, 1, 2)
        grid.addWidget(base_btn, 4, 3)

        grid.addWidget(QLabel("Destination folder:"), 5, 0)
        self._dest_edit = QLineEdit()
        dest_btn = QPushButton("Browse…")
        dest_btn.clicked.connect(self._browse_dest)
        grid.addWidget(self._dest_edit, 5, 1, 1, 2)
        grid.addWidget(dest_btn, 5, 3)

        dest_hint = QLabel("Reports are written to <folder>/<List 2>/<List 1>.<type>.")
        # PlainText, not AutoText: Qt's rich-text heuristic reads "<folder>" as
        # a tag and would swallow every placeholder in this line.
        dest_hint.setTextFormat(Qt.TextFormat.PlainText)
        dest_hint.setStyleSheet("color: gray;")
        grid.addWidget(dest_hint, 6, 0, 1, 4)

        self._save_export_box = QCheckBox("Save profile exports as JSON")
        self._save_export_box.setToolTip(
            "Also save each profile side's export as JSON in the destination "
            "folder, so you can reuse it later."
        )
        grid.addWidget(self._save_export_box, 7, 0, 1, 4)

        self._enabled_only_box = QCheckBox("Only compare enabled mods")
        self._enabled_only_box.setToolTip(
            "All MO2 profiles share one mods folder, so a profile's list also "
            "contains the mods only other profiles use, marked disabled. "
            "Ticking this ignores disabled mods on every side (and the "
            "Previous base), so they are not counted as present. Saved "
            "profile exports contain the filtered list too."
        )
        grid.addWidget(self._enabled_only_box, 8, 0, 1, 4)

        buttons = QHBoxLayout()
        generate_btn = QPushButton("Generate")
        generate_btn.setDefault(True)
        generate_btn.clicked.connect(self._on_generate)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(generate_btn)
        buttons.addWidget(cancel_btn)
        grid.addLayout(buttons, 9, 0, 1, 4)

    def _browse_side(self, side):
        start = str(self._get("browse_dir", ""))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select exported modlist JSON", start, "JSON files (*.json)"
        )
        if path:
            side.path_edit.setText(path)
            self._set("browse_dir", os.path.dirname(path))

    def _browse_base(self):
        start = str(self._get("browse_dir", ""))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select previous base JSON", start, "JSON files (*.json)"
        )
        if path:
            self._base_edit.setText(path)
            self._set("browse_dir", os.path.dirname(path))

    def _browse_dest(self):
        start = self._dest_edit.text().strip() or str(self._get("dest_dir", ""))
        path = QFileDialog.getExistingDirectory(
            self, "Select destination folder", start
        )
        if path:
            self._dest_edit.setText(path)

    # ---- generate --------------------------------------------------------

    def _warn(self, message):
        QMessageBox.warning(self, _TITLE, message)

    @staticmethod
    def _same_path(a, b):
        """Compare two paths the way the filesystem does (case-insensitive)."""
        if not a or not b:
            return False
        return (os.path.normcase(os.path.abspath(a))
                == os.path.normcase(os.path.abspath(b)))

    def _apply_enabled_filter(self, data):
        """Drop disabled mods from data when "Only compare enabled mods" is on."""
        if self._enabled_only_box.isChecked():
            return report_runner.filter_enabled(data)
        return data

    def _resolve_side(self, label, picker):
        """Return a ListSide, or None after warning the user."""
        kind, name = picker.selection()
        if kind == "profile":
            # Unhandled exceptions escaping a Qt slot go through qFatal() and
            # abort MO2, so the profile export is guarded like the file branch.
            try:
                data = self._apply_enabled_filter(
                    exporter_core.export_profile(self._organizer, name))
            except Exception as e:
                self._warn(
                    f"{label}: could not export profile '{name}'\n\n{e}"
                )
                return None
            return report_runner.ListSide(name=name, data=data, from_profile=True)
        path = picker.path()
        if not path:
            self._warn(f"{label}: choose a JSON file (or pick a profile).")
            return None
        try:
            side = report_runner.load_side_from_file(path)
            side.data = self._apply_enabled_filter(side.data)
            return side
        except Exception as e:
            self._warn(f"{label}: could not load\n{path}\n\n{e}")
            return None

    def _on_generate(self):
        if self._worker is not None:
            return  # a run is already in flight; never overwrite its wiring
        sel1, sel2 = self._side1.selection(), self._side2.selection()
        if (sel1[0] == "profile" and sel2[0] == "profile"
                and sel1[1].casefold() == sel2[1].casefold()):
            self._warn("Both sides are the same profile — pick a different one.")
            return
        if (sel1[0] == "file" and sel2[0] == "file"
                and self._same_path(self._side1.path(), self._side2.path())):
            self._warn("Both sides are the same file.")
            return
        report_types = [r for r, box in self._report_boxes.items() if box.isChecked()]
        if not report_types:
            self._warn("Select at least one report type.")
            return
        dest = self._dest_edit.text().strip()
        if not dest:
            self._warn("Choose a destination folder.")
            return

        base = None
        if "rebase" in report_types:
            base_path = self._base_edit.text().strip()
            if not base_path:
                self._warn("Rebase needs a previous base JSON — choose one.")
                return
            try:
                base = report_runner.load_side_from_file(base_path)
                base.data = self._apply_enabled_filter(base.data)
            except Exception as e:
                self._warn(f"Previous base: could not load\n{base_path}\n\n{e}")
                return
            if not base.data:
                self._warn("Previous base: the file contains no mods.")
                return

        side1 = self._resolve_side("List 1", self._side1)
        if side1 is None:
            return
        side2 = self._resolve_side("List 2", self._side2)
        if side2 is None:
            return

        problem = report_runner.validate_run(
            side1, side2, report_types, base,
            save_exports=self._save_export_box.isChecked(),
        )
        if problem:
            self._warn(problem)
            return

        self._save_state()
        self._worker = _ReportWorker(
            self, side1, side2, report_types, dest,
            self._save_export_box.isChecked(), base,
            exporter_core.find_category_names(self._organizer),
        )
        self._progress = _ProgressDialog(self, self._on_cancel_clicked)
        self._worker.progress_changed.connect(self._on_progress_changed)
        self._worker.done.connect(lambda result: self._on_reports_done(result, dest))
        self._progress.show()
        self._worker.start()

    def _on_cancel_clicked(self):
        """Request cancellation. Every close route funnels here; idempotent."""
        if self._worker is None:
            return  # already finished — a stray close route, nothing to cancel
        self._worker.cancel_event.set()
        if self._progress is None:
            return
        self._progress.setLabelText("Cancelling…")
        self._progress.disable_cancel()

    def _on_progress_changed(self, percent, message):
        if self._worker is None or self._progress is None:
            return  # a late delivery after teardown
        if self._worker.cancel_event.is_set():
            return  # a cancel is pending; keep "Cancelling…" on screen
        self._progress.setLabelText(message)
        self._progress.setValue(percent)

    def _on_reports_done(self, result, dest):
        worker, progress = self._worker, self._progress
        if worker is None:
            return  # already torn down; nothing left to do
        worker.wait()  # the thread must be finished before it can be dropped
        # Clear the handles first: _show_result spins a nested event loop, and
        # every close route below checks these to decide whether a run is live.
        self._worker = None
        self._progress = None
        if progress is not None:
            # hide(), not close(): closeEvent is overridden to request cancel.
            progress.hide()
            progress.deleteLater()
        worker.deleteLater()
        if result.cancelled:
            if result.written:
                self._show_result(result, dest, cancelled=True)
            return
        self._show_result(result, dest)
        if not result.errors:
            self.accept()

    # ---- close routes ----------------------------------------------------

    def reject(self):
        """Refuse to close while a worker is live.

        The dialog is Qt-parented to the MO2 main window, so closing it does
        not immediately destroy it — but it does end window modality while the
        worker still runs, reopening every race this design leans on modality
        to prevent, and it queues a deferred destruction that can then land on
        a live QThread (destroying a running QThread is an unconditional
        qFatal that takes MO2 with it). Cancel is requested instead;
        _on_reports_done waits for the thread and the user can close normally
        after that.
        """
        if self._worker is not None:
            self._on_cancel_clicked()
            return
        super().reject()

    def closeEvent(self, event):
        if self._worker is not None:
            self._on_cancel_clicked()
            event.ignore()
            return
        super().closeEvent(event)

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
        box.setText("\n".join(lines) or "Nothing to do.")
        open_btn = box.addButton("Open Folder", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(dest))
