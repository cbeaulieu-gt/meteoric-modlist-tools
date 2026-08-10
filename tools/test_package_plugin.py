"""Tests for the plugin vendoring/packaging script."""
import os
import tempfile
import unittest
import zipfile

import package_plugin

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))


class TestVendor(unittest.TestCase):
    def test_vendor_copies_modules_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_plugin.vendor(vendor_dir=tmp)
            for name in package_plugin.VENDORED_MODULES:
                with open(os.path.join(TOOLS_DIR, name), "rb") as f:
                    src = f.read()
                with open(os.path.join(tmp, name), "rb") as f:
                    dst = f.read()
                self.assertEqual(src, dst, name)


class TestBuildZip(unittest.TestCase):
    def test_zip_layout_and_exclusions(self):
        package_plugin.vendor()  # real _vendor/, needed for the zip content
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = package_plugin.build_zip(dist_dir=tmp)
            self.assertTrue(os.path.basename(zip_path).startswith("modlist-compare-"))
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
        self.assertTrue(all(n.startswith("modlist_compare/") for n in names))
        self.assertTrue(any(n.endswith("_vendor/modlist_utils.py") for n in names))
        self.assertTrue(any(n.endswith("/plugin_tools.py") for n in names))
        self.assertFalse(any("/test_" in n or "__pycache__" in n for n in names))
        self.assertFalse(any("/nexus/" in n for n in names))


class TestVersionParse(unittest.TestCase):
    def test_reads_plugin_version(self):
        version = package_plugin.plugin_version()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
