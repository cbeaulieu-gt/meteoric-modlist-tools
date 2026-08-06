"""Package the Modlist Compare MO2 plugin.

Vendors the generator modules into mo2-plugins/modlist_compare/_vendor/ and
builds dist/modlist-compare-<version>.zip ready to unzip into MO2's plugins/.
"""
import os
import re
import shutil
import zipfile

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
PLUGIN_DIR = os.path.join(REPO_ROOT, "mo2-plugins", "modlist_compare")
DEFAULT_VENDOR_DIR = os.path.join(PLUGIN_DIR, "_vendor")
DEFAULT_DIST_DIR = os.path.join(REPO_ROOT, "dist")

VENDORED_MODULES = [
    "modlist_utils.py",
    "generate_coverage.py",
    "generate_diff.py",
    "generate_changelog.py",
    "coverage_ignore.py",
]


def vendor(vendor_dir=DEFAULT_VENDOR_DIR):
    """Copy the tool modules into the plugin's _vendor/ directory."""
    os.makedirs(vendor_dir, exist_ok=True)
    for name in VENDORED_MODULES:
        shutil.copy2(os.path.join(TOOLS_DIR, name), os.path.join(vendor_dir, name))


def plugin_version():
    """Read a.b.c from the VersionInfo(...) call in plugin_tools.py."""
    with open(os.path.join(PLUGIN_DIR, "plugin_tools.py"), encoding="utf-8") as f:
        match = re.search(r"VersionInfo\((\d+),\s*(\d+),\s*(\d+)", f.read())
    if not match:
        raise RuntimeError("No VersionInfo(a, b, c) found in plugin_tools.py")
    return ".".join(match.groups())


def build_zip(dist_dir=DEFAULT_DIST_DIR):
    """Zip the plugin folder (tests and caches excluded). Returns the zip path."""
    os.makedirs(dist_dir, exist_ok=True)
    zip_path = os.path.join(dist_dir, f"modlist-compare-{plugin_version()}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PLUGIN_DIR):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in sorted(files):
                if fn.startswith("test_") or fn.endswith(".pyc"):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, os.path.dirname(PLUGIN_DIR))
                zf.write(full, rel.replace(os.sep, "/"))
    return zip_path


def main():
    vendor()
    print(f"Vendored {len(VENDORED_MODULES)} modules into {DEFAULT_VENDOR_DIR}")
    zip_path = build_zip()
    print(f"Built {zip_path}")


if __name__ == "__main__":
    main()
