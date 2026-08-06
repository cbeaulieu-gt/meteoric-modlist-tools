"""Modlist Compare — MO2 plugin: export modlists to JSON and generate
coverage/diff/changelog reports.

Plugin classes register only inside MO2 (mobase importable); importing this
package outside MO2 (unit tests) exposes just the plain modules.
"""
import importlib.util

if importlib.util.find_spec("mobase") is not None:
    from .plugin_tools import ExportModlistTool

    def createPlugins():
        return [ExportModlistTool()]
