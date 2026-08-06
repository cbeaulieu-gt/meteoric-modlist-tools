"""The two IPluginTool entries for the Modlist Compare plugin."""
import json
from typing import List, Optional

import mobase
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from . import exporter_core

SUBMENU = "Modlist Compare"
VERSION = mobase.VersionInfo(1, 0, 0)


class _BaseTool(mobase.IPluginTool):
    def __init__(self):
        super().__init__()
        self._organizer: Optional[mobase.IOrganizer] = None
        self._parent_widget = None

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        return True

    def author(self) -> str:
        return "meteor"

    def version(self) -> mobase.VersionInfo:
        return VERSION

    def settings(self) -> List[mobase.PluginSetting]:
        return []

    def icon(self) -> QIcon:
        return QIcon()

    def setParentWidget(self, widget):
        self._parent_widget = widget


class ExportModlistTool(_BaseTool):
    def name(self) -> str:
        return "Modlist Compare Exporter"

    def description(self) -> str:
        return "Export the active modlist to JSON for comparison and analysis."

    def displayName(self) -> str:
        return f"{SUBMENU}/Export Modlist to JSON"

    def tooltip(self) -> str:
        return self.description()

    def display(self):
        if not self._organizer:
            return
        suggested = exporter_core.suggested_list_name(self._organizer) + ".json"
        save_path, _ = QFileDialog.getSaveFileName(
            self._parent_widget, "Save Modlist JSON", suggested, "JSON files (*.json)"
        )
        if not save_path:
            return
        try:
            modlist_data = exporter_core.export_modlist(self._organizer)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(modlist_data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(
                self._parent_widget,
                "Export Complete",
                f"Modlist exported successfully to:\n{save_path}\n\n"
                f"Total mods: {len(modlist_data)}",
            )
        except Exception as e:
            QMessageBox.critical(
                self._parent_widget,
                "Export Failed",
                f"Failed to export modlist:\n{str(e)}",
            )


class GenerateReportsTool(_BaseTool):
    def name(self) -> str:
        return "Modlist Compare Reports"

    def description(self) -> str:
        return "Generate coverage, diff, and changelog reports between two modlists."

    def displayName(self) -> str:
        return f"{SUBMENU}/Generate Reports…"

    def tooltip(self) -> str:
        return self.description()

    def display(self):
        if not self._organizer:
            return
        # Imported here, not at module level: a dialog.py import-time problem
        # then surfaces as an error on click instead of silently dropping the
        # whole plugin at registration time.
        from .dialog import GenerateReportsDialog

        dialog = GenerateReportsDialog(
            self._parent_widget, self._organizer, self.name()
        )
        dialog.exec()
