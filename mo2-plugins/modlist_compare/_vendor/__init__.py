"""Vendored copies of the tools/ generator modules.

Populated by tools/package_plugin.py — the files here are unmodified copies.
The generators import each other as siblings (``from modlist_utils import ...``),
so this dir goes on sys.path just long enough to import them.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPECTED = [
    "modlist_utils.py",
    "generate_coverage.py",
    "generate_diff.py",
    "generate_changelog.py",
    "coverage_ignore.py",
]


def _load():
    missing = [m for m in _EXPECTED if not os.path.exists(os.path.join(_HERE, m))]
    if missing:
        raise ImportError(
            "Modlist Compare: vendored modules missing: "
            + ", ".join(missing)
            + ". Run tools/package_plugin.py to populate _vendor/."
        )
    sys.path.insert(0, _HERE)
    try:
        import coverage_ignore
        import generate_changelog
        import generate_coverage
        import generate_diff
        import modlist_utils
    finally:
        sys.path.remove(_HERE)
    return modlist_utils, coverage_ignore, generate_coverage, generate_diff, generate_changelog


(modlist_utils, coverage_ignore, generate_coverage,
 generate_diff, generate_changelog) = _load()
