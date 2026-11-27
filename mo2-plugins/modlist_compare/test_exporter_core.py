"""Tests for exporter_core's pure helpers (no mobase/PyQt6 required)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modlist_compare import exporter_core


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


class TestParseModlistTxt(unittest.TestCase):
    def test_skips_header_blanks_unmanaged_and_reads_state(self):
        text = "# header\r\n+Mod A\r\n-Mod B\r\n*DLC\r\n\r\n+Sep_separator\r\n+Ünïcode\r\n"
        self.assertEqual(
            exporter_core.parse_modlist_txt(text),
            [("Mod A", True), ("Mod B", False), ("Sep_separator", True), ("Ünïcode", True)],
        )


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


class TestExportProfileFromFiles(unittest.TestCase):
    def _make(self, tmp, modlist_text, folders):
        mods = os.path.join(tmp, "mods")
        prof = os.path.join(tmp, "profiles", "P")
        os.makedirs(mods)
        os.makedirs(prof)
        for name in folders:
            os.makedirs(os.path.join(mods, name))
        _write(os.path.join(prof, "modlist.txt"), modlist_text)
        return prof, mods

    def test_order_separator_flags_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, mods = self._make(
                tmp, "+Mod A\n-Mod B\n+Sep_separator\n", ["Mod A", "Sep_separator"]
            )
            _write(os.path.join(mods, "Mod A", "meta.ini"), "[General]\nmodid=5\n")
            _write(os.path.join(mods, "Mod A", "a.esp"), "")
            items = exporter_core.export_profile_from_files(prof, mods)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["type"], "separator")
        self.assertEqual(items[0]["separatorName"], "Sep")
        self.assertEqual(items[0]["order"], 0)
        self.assertEqual(items[1]["type"], "mod")
        self.assertEqual(items[1]["id"], 5)
        self.assertEqual(items[1]["separatorName"], "Sep")
        self.assertEqual(items[1]["plugins"], ["a.esp"])
        self.assertIs(items[1]["active"], True)
        self.assertEqual(items[1]["order"], 1)

    def test_mod_without_modid_uses_clean_name_as_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, mods = self._make(tmp, "-[Tag] Plain\n", ["[Tag] Plain"])
            items = exporter_core.export_profile_from_files(prof, mods)
        self.assertEqual(items[0]["id"], "Plain")
        self.assertEqual(items[0]["tags"], ["Tag"])
        self.assertIs(items[0]["active"], False)

    def test_empty_profile_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, mods = self._make(tmp, "# This file was automatically generated\n", [])
            self.assertEqual(exporter_core.export_profile_from_files(prof, mods), [])


class _Prof:
    def __init__(self, path):
        self._p = path

    def absolutePath(self):
        return self._p


class _FullOrg:
    def __init__(self, path):
        self._path = path

    def profileNames(self):
        return ["Active", "Other"]

    def profileName(self):
        return "Active"

    def getProfile(self, name):
        return _Prof(self._path)


class _BareOrg:
    def __init__(self, profile_path):
        self._pp = profile_path

    def profileName(self):
        return "Active"

    def profilePath(self):
        return self._pp

    def modsPath(self):
        return "unused"


class TestProfileListing(unittest.TestCase):
    def test_full_api(self):
        org = _FullOrg("X:/p/Active")
        self.assertEqual(exporter_core.list_profiles(org), ["Active", "Other"])
        self.assertEqual(exporter_core.active_profile_name(org), "Active")
        self.assertEqual(exporter_core.profile_dir(org, "Active"), "X:/p/Active")

    def test_fallback_scans_profiles_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "profiles")
            for name in ("Active", "Other"):
                os.makedirs(os.path.join(root, name))
                _write(os.path.join(root, name, "modlist.txt"), "")
            os.makedirs(os.path.join(root, "Stray"))
            org = _BareOrg(os.path.join(root, "Active"))
            self.assertEqual(exporter_core.list_profiles(org), ["Active", "Other"])
            self.assertEqual(
                exporter_core.profile_dir(org, "Other"), os.path.join(root, "Other")
            )

    def test_export_profile_active_uses_live_export(self):
        from unittest import mock
        org = _BareOrg("whatever")
        with mock.patch.object(exporter_core, "export_modlist", return_value=["live"]) as m:
            self.assertEqual(exporter_core.export_profile(org, "active"), ["live"])
        m.assert_called_once_with(org)


if __name__ == "__main__":
    unittest.main()
