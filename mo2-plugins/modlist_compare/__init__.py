"""Modlist Compare — MO2 plugin: export modlists to JSON and generate
coverage/diff/changelog reports.

Plugin classes register only inside MO2 (mobase importable); importing this
package outside MO2 (unit tests) exposes just the plain modules.
"""
try:
    import mobase  # noqa: F401

    _HAVE_MOBASE = True
except ImportError:
    _HAVE_MOBASE = False

if _HAVE_MOBASE:
    # Outside the try on purpose: a PyQt6 ImportError here (MO2 < 2.5) must
    # fail loudly rather than silently skip plugin registration.
    from .plugin_tools import ExportModlistTool

    def createPlugins():
        return [ExportModlistTool()]
