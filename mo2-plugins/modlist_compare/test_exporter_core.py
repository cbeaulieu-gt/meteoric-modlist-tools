"""Tests for exporter_core's pure helpers (no mobase/PyQt6 required)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modlist_compare import exporter_core


class TestFindCategoryNames(unittest.TestCase):
    class _Org:
        def __init__(self, base):
            self._base = base

        def basePath(self):
            return self._base

    def test_reads_categories_dat(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "categories.dat"), "w", encoding="utf-8") as f:
                f.write("1|Animations|2|0\n")
            self.assertEqual(exporter_core.find_category_names(self._Org(d)),
                             {"1": "Animations"})

    def test_missing_file_or_api_error_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(exporter_core.find_category_names(self._Org(d)), {})
        self.assertEqual(exporter_core.find_category_names(object()), {})


class TestTagHelpers(unittest.TestCase):
    def test_strip_tags(self):
        self.assertEqual(exporter_core.strip_tags("[NoDelete] Awesome Mod"), "Awesome Mod")
        self.assertEqual(
            exporter_core.strip_tags("[A] [B] Mod Name"), "Mod Name"
        )
        self.assertEqual(exporter_core.strip_tags("Plain Mod"), "Plain Mod")

    def test_extract_tags(self):
        self.assertEqual(exporter_core.extract_tags("[A] [B] Mod"), ["A", "B"])
        self.assertEqual(exporter_core.extract_tags("Plain"), [])


class TestSanitizeFilename(unittest.TestCase):
    def test_unsafe_chars_replaced(self):
        self.assertEqual(exporter_core.sanitize_filename('My<List>: v1?'), "My_List__ v1_")

    def test_empty_falls_back(self):
        self.assertEqual(exporter_core.sanitize_filename(""), "modlist_export")


class TestReadMetaIni(unittest.TestCase):
    def test_reads_general_and_installed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "meta.ini"), "w", encoding="utf-8") as f:
                f.write(
                    "[General]\nmodid=123\nversion=1.2\nnewestVersion=1.3\n"
                    "category=4\ninstallationFile=Mod-1-2.7z\n"
                    "[installedFiles]\nsize=1\n1\\modid=123\n1\\fileid=456\n"
                )
            general, installed = exporter_core.read_meta_ini(tmp)
        self.assertEqual(general["modid"], "123")
        self.assertEqual(general["version"], "1.2")
        self.assertEqual(installed["size"], 1)
        self.assertEqual(installed["files"][0], {"modid": "123", "fileid": "456"})

    def test_missing_meta_ini(self):
        with tempfile.TemporaryDirectory() as tmp:
            general, installed = exporter_core.read_meta_ini(tmp)
        self.assertEqual(general, {})
        self.assertEqual(installed, {})


class TestGetPluginFiles(unittest.TestCase):
    def test_finds_and_sorts_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("b.esp", "a.ESM", "readme.txt", "c.esl"):
                open(os.path.join(tmp, name), "w").close()
            self.assertEqual(
                exporter_core.get_plugin_files(tmp), ["a.ESM", "b.esp", "c.esl"]
            )

    def test_missing_dir(self):
        self.assertEqual(exporter_core.get_plugin_files("Z:\\does\\not\\exist"), [])


if __name__ == "__main__":
    unittest.main()
