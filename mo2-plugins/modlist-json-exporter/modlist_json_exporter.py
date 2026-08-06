"""
Modlist JSON Exporter
A MO2 plugin to export detailed modlist information to JSON format for comparison and analysis.
"""
import json
import os
import re
import configparser
from pathlib import Path
from typing import List, Dict, Any, Optional

from PyQt6.QtCore import QFileInfo
from PyQt6.QtWidgets import QFileDialog, QMessageBox
import mobase


class ModlistJsonExporter(mobase.IPluginTool):
    """Plugin to export modlist information to structured JSON format."""

    def __init__(self):
        super().__init__()
        self._organizer: Optional[mobase.IOrganizer] = None
        self._parent_widget = None

    def init(self, organizer: mobase.IOrganizer) -> bool:
        """Initialize the plugin."""
        self._organizer = organizer
        return True

    def name(self) -> str:
        """Internal name of the plugin."""
        return "Modlist JSON Exporter"

    def author(self) -> str:
        """Author of the plugin."""
        return "meteor"

    def description(self) -> str:
        """Description of the plugin."""
        return "Export detailed modlist information to JSON format for comparison and analysis."

    def version(self) -> mobase.VersionInfo:
        """Version of the plugin."""
        return mobase.VersionInfo(1, 0, 0)

    def settings(self) -> List[mobase.PluginSetting]:
        """Plugin settings."""
        return []

    def displayName(self) -> str:
        """Display name shown in the tools menu."""
        return "Export Modlist to JSON"

    def tooltip(self) -> str:
        """Tooltip for the plugin."""
        return self.description()

    def icon(self):
        """Icon for the plugin."""
        from PyQt6.QtGui import QIcon
        return QIcon()

    def setParentWidget(self, widget):
        """Set the parent widget."""
        self._parent_widget = widget

    def display(self):
        """Main plugin execution - export modlist to JSON."""
        if not self._organizer:
            return

        # Get suggested filename from first separator
        suggested_filename = self._get_suggested_filename()

        # Ask user where to save the JSON file
        save_path, _ = QFileDialog.getSaveFileName(
            self._parent_widget,
            "Save Modlist JSON",
            suggested_filename,
            "JSON files (*.json)"
        )

        if not save_path:
            return

        try:
            # Export the modlist
            modlist_data = self._export_modlist()

            # Write to file
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(modlist_data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(
                self._parent_widget,
                "Export Complete",
                f"Modlist exported successfully to:\n{save_path}\n\n"
                f"Total mods: {len(modlist_data)}"
            )
        except Exception as e:
            QMessageBox.critical(
                self._parent_widget,
                "Export Failed",
                f"Failed to export modlist:\n{str(e)}"
            )

    def _get_suggested_filename(self) -> str:
        """Get suggested filename from first separator name."""
        mod_list = self._organizer.modList()

        # Use allModsByProfilePriority() to get mods in correct order (top-to-bottom)
        all_mods = list(mod_list.allModsByProfilePriority())

        # Find the first separator (it will be the first in the actual modlist)
        first_separator_name = None
        for mod_name in all_mods:
            mod = self._organizer.getMod(mod_name)
            if mod and (mod.isSeparator() or mod_name.endswith('_separator')):
                # First separator we find is the first in the actual modlist
                first_separator_name = self._strip_tags(mod_name).replace("_separator", "").strip()
                break  # Take the first one we find

        if first_separator_name:
            # Sanitize filename - remove unsafe characters
            safe_name = self._sanitize_filename(first_separator_name)
            return f"{safe_name}.json"
        else:
            return "modlist_export.json"

    def _sanitize_filename(self, filename: str) -> str:
        """Remove unsafe characters from filename."""
        # Replace unsafe characters with underscores
        unsafe_chars = r'<>:"/\|?*'
        for char in unsafe_chars:
            filename = filename.replace(char, '_')
        # Remove leading/trailing spaces and dots
        filename = filename.strip('. ')
        return filename if filename else "modlist_export"

    def _export_modlist(self) -> List[Dict[str, Any]]:
        """Export modlist to structured format."""
        modlist_data = []
        mod_list = self._organizer.modList()

        # Track the current separator - mods are assigned to the most recent separator encountered
        current_separator = "Unsectioned"  # Default for mods without a separator

        # Get all mods in priority order (top-to-bottom)
        all_mods = list(mod_list.allModsByProfilePriority())

        for mod_name in all_mods:
            mod = self._organizer.getMod(mod_name)
            if not mod:
                continue

            # Check if this is a separator
            if mod.isSeparator() or mod_name.endswith('_separator'):
                # Get separator name
                separator_name = self._strip_tags(mod_name).replace("_separator", "").strip()

                # Update current separator for subsequent mods
                current_separator = separator_name

                # Add separator to output
                separator_data = {
                    "id": None,
                    "type": "separator",
                    "separatorName": separator_name,
                    "modName": separator_name,
                    "displayName": mod_name,
                    "plugins": [],
                    "general": {},
                    "installed": {},
                    "order": len(modlist_data),
                    "tags": self._extract_tags(mod_name),
                    "active": True  # Separators are always considered active
                }
                modlist_data.append(separator_data)

            else:
                # Regular mod - assign to current separator
                mod_data = self._extract_mod_data(
                    mod,
                    mod_name,
                    current_separator,
                    len(modlist_data)
                )
                modlist_data.append(mod_data)

        # Fix the order values to be sequential (in case we had gaps)
        for idx, mod_data in enumerate(modlist_data):
            mod_data["order"] = idx

        return modlist_data

    def _extract_mod_data(self, mod: mobase.IModInterface, mod_name: str,
                          separator_name: Optional[str], order: int) -> Dict[str, Any]:
        """Extract all relevant data from a mod."""
        # Get basic info
        mod_path = mod.absolutePath()
        nexus_id = mod.nexusId()

        # Get version info
        version_obj = mod.version()
        version = version_obj.displayString() if version_obj else "Unknown"

        newest_version_obj = mod.newestVersion()
        newest_version = newest_version_obj.displayString() if newest_version_obj else version

        # Extract mod name without tags
        clean_mod_name = self._strip_tags(mod_name)

        # Extract tags
        tags = self._extract_tags(mod_name)

        # Get plugin files (.esp, .esl, .esm)
        plugins = self._get_plugin_files(mod_path)

        # Read meta.ini for additional info
        general_data, installed_files_data = self._read_meta_ini(mod_path)

        # Check if mod is active
        is_active = mod_list = self._organizer.modList()
        is_active = mod_list.state(mod_name) & mobase.ModState.ACTIVE != 0

        # Use nexus_id if available, otherwise use mod name
        mod_id = nexus_id if nexus_id > 0 else clean_mod_name

        return {
            "id": mod_id,
            "type": "mod",
            "separatorName": separator_name,
            "modName": clean_mod_name,
            "displayName": mod_name,
            "plugins": plugins,
            "general": general_data,
            "installed": installed_files_data,
            "order": order,
            "tags": tags,
            "active": is_active
        }

    def _strip_tags(self, mod_name: str) -> str:
        """Remove all tags in square brackets from the beginning of a mod name."""
        pattern = r'^(\[[^\]]+\]\s*)+\s*'
        return re.sub(pattern, '', mod_name).strip()

    def _extract_tags(self, mod_name: str) -> List[str]:
        """Extract all tags from a mod name."""
        pattern = r'\[([^\]]+)\]'
        return re.findall(pattern, mod_name)

    def _get_plugin_files(self, mod_path: str) -> List[str]:
        """Get list of plugin files (.esp, .esl, .esm) in the mod folder."""
        plugins = []

        if not os.path.exists(mod_path):
            return plugins

        try:
            for file in os.listdir(mod_path):
                if file.lower().endswith(('.esp', '.esl', '.esm')):
                    plugins.append(file)
        except Exception as e:
            # If we can't read the directory, just return empty list
            pass

        return sorted(plugins)

    def _read_meta_ini(self, mod_path: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Read meta.ini file and extract General and installedFiles sections."""
        general_data = {}
        installed_files_data = {}

        meta_ini_path = os.path.join(mod_path, "meta.ini")

        if not os.path.exists(meta_ini_path):
            return general_data, installed_files_data

        try:
            config = configparser.ConfigParser()
            config.read(meta_ini_path, encoding='utf-8')

            # Read [General] section
            if 'General' in config:
                general_section = config['General']
                general_data = {
                    'modid': general_section.get('modid', ''),
                    'version': general_section.get('version', ''),
                    'newestVersion': general_section.get('newestVersion', ''),
                    'category': general_section.get('category', ''),
                    'installationFile': general_section.get('installationFile', '')
                }

            # Read [installedFiles] section
            if 'installedFiles' in config:
                installed_section = config['installedFiles']
                size = int(installed_section.get('size', 0))

                installed_files_data['size'] = size
                installed_files_data['files'] = []

                # Read each installed file entry
                for i in range(1, size + 1):
                    file_entry = {
                        'modid': installed_section.get(f'{i}\\modid', ''),
                        'fileid': installed_section.get(f'{i}\\fileid', '')
                    }
                    installed_files_data['files'].append(file_entry)

        except Exception as e:
            # If we can't read the meta.ini, just return empty dicts
            pass

        return general_data, installed_files_data


def createPlugin() -> mobase.IPlugin:
    """Create and return the plugin instance."""
    return ModlistJsonExporter()
