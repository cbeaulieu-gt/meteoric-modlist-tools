"""Generate Reports dialog for the Modlist Compare plugin."""
import os

from PyQt6.QtCore import QUrl
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
    QPushButton,
)

from . import exporter_core, report_runner

CURRENT_PROFILE = "Current profile"
JSON_FILE = "JSON file…"
_TITLE = "Generate Reports"


class _SidePicker:
    """Widgets for one list side (not itself a QWidget)."""

    def __init__(self, on_browse):
        self.combo = QComboBox()
        self.combo.addItems([CURRENT_PROFILE, JSON_FILE])
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(on_browse)
        self.combo.currentTextChanged.connect(self._sync_enabled)
        self._sync_enabled(self.combo.currentText())

    def _sync_enabled(self, text):
        is_file = text == JSON_FILE
        self.path_edit.setEnabled(is_file)
        self.browse_btn.setEnabled(is_file)

    def is_live(self):
        return self.combo.currentText() == CURRENT_PROFILE

    def path(self):
        return self.path_edit.text().strip()


class GenerateReportsDialog(QDialog):
    def __init__(self, parent, organizer, plugin_name):
        super().__init__(parent)
        self._organizer = organizer
        self._plugin_name = plugin_name
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

    def _save_state(self):
        self._set("dest_dir", self._dest_edit.text().strip())
        self._set("reports", ",".join(
            r for r, box in self._report_boxes.items() if box.isChecked()
        ))
        self._set("save_export", "true" if self._save_export_box.isChecked() else "false")

    # ---- UI --------------------------------------------------------------

    def _build_ui(self):
        grid = QGridLayout(self)

        self._side1 = _SidePicker(lambda: self._browse_side(self._side1))
        self._side2 = _SidePicker(lambda: self._browse_side(self._side2))
        for row, (label, side) in enumerate(
            (("List 1 (source / old):", self._side1),
             ("List 2 (target / new):", self._side2))
        ):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(side.combo, row, 1)
            grid.addWidget(side.path_edit, row, 2)
            grid.addWidget(side.browse_btn, row, 3)

        grid.addWidget(QLabel("Reports:"), 2, 0)
        reports_row = QHBoxLayout()
        self._report_boxes = {}
        for rtype, label in (("coverage", "Coverage"), ("diff", "Diff"),
                             ("changelog", "Changelog")):
            box = QCheckBox(label)
            self._report_boxes[rtype] = box
            reports_row.addWidget(box)
        reports_row.addStretch()
        grid.addLayout(reports_row, 2, 1, 1, 3)

        grid.addWidget(QLabel("Destination folder:"), 3, 0)
        self._dest_edit = QLineEdit()
        dest_btn = QPushButton("Browse…")
        dest_btn.clicked.connect(self._browse_dest)
        grid.addWidget(self._dest_edit, 3, 1, 1, 2)
        grid.addWidget(dest_btn, 3, 3)

        self._save_export_box = QCheckBox(
            'Save "Current profile" export as JSON'
        )
        grid.addWidget(self._save_export_box, 4, 0, 1, 4)

        buttons = QHBoxLayout()
        generate_btn = QPushButton("Generate")
        generate_btn.setDefault(True)
        generate_btn.clicked.connect(self._on_generate)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(generate_btn)
        buttons.addWidget(cancel_btn)
        grid.addLayout(buttons, 5, 0, 1, 4)

    def _browse_side(self, side):
        start = str(self._get("browse_dir", ""))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select exported modlist JSON", start, "JSON files (*.json)"
        )
        if path:
            side.path_edit.setText(path)
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

    def _resolve_side(self, label, picker):
        """Return a ListSide, or None after warning the user."""
        if picker.is_live():
            data = exporter_core.export_modlist(self._organizer)
            name = exporter_core.suggested_list_name(self._organizer)
            return report_runner.ListSide(name=name, data=data, live=True)
        path = picker.path()
        if not path:
            self._warn(f"{label}: choose a JSON file (or switch to Current profile).")
            return None
        try:
            return report_runner.load_side_from_file(path)
        except Exception as e:
            self._warn(f"{label}: could not load\n{path}\n\n{e}")
            return None

    def _on_generate(self):
        if self._side1.is_live() and self._side2.is_live():
            self._warn("Both sides are the current profile — pick a JSON file for one side.")
            return
        if (not self._side1.is_live() and not self._side2.is_live()
                and self._side1.path() and self._side1.path() == self._side2.path()):
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

        side1 = self._resolve_side("List 1", self._side1)
        if side1 is None:
            return
        side2 = self._resolve_side("List 2", self._side2)
        if side2 is None:
            return

        self._save_state()
        result = report_runner.run_reports(
            side1, side2, report_types, dest,
            save_exports=self._save_export_box.isChecked(),
        )
        self._show_result(result, dest)
        if not result.errors:
            self.accept()

    def _show_result(self, result, dest):
        lines = []
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
            QMessageBox.Icon.Critical if not result.written
            else QMessageBox.Icon.Warning if result.errors
            else QMessageBox.Icon.Information
        )
        box.setText("\n".join(lines) or "Nothing to do.")
        open_btn = box.addButton("Open Folder", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(dest))
