"""The example lists are documentation: they must keep demonstrating every
comparison case the README and the sample reports claim they do. This suite
fails loudly if an edit quietly removes one."""

import json
import os
import unittest

from modlist_utils import (
    extract_mods,
    get_separator_order,
    is_major_separator,
    match_mods,
    name_key,
    plugin_set,
)

EXAMPLES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "examples", "lists"
)
OLD_PATH = os.path.join(EXAMPLES, "Example List 1.0.json")
NEW_PATH = os.path.join(EXAMPLES, "Example List 1.1.json")


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _by_name(mods, name):
    for mod in mods:
        if name_key(mod.get("modName")) == name_key(name):
            return mod
    return None


class ExampleListStructureTests(unittest.TestCase):
    """Both files must be structurally valid exports."""

    def setUp(self):
        self.lists = {"1.0": _load(OLD_PATH), "1.1": _load(NEW_PATH)}

    def test_order_is_sequential_from_zero(self):
        for label, data in self.lists.items():
            with self.subTest(list=label):
                self.assertEqual(
                    [item["order"] for item in data], list(range(len(data)))
                )

    def test_every_mod_sits_under_a_preceding_separator(self):
        for label, data in self.lists.items():
            with self.subTest(list=label):
                seen = set()
                for item in data:
                    if item["type"] == "separator":
                        seen.add(name_key(item["modName"]))
                    else:
                        self.assertIn(name_key(item["separatorName"]), seen)

    def test_separators_have_null_id_and_no_plugins(self):
        for label, data in self.lists.items():
            with self.subTest(list=label):
                for item in data:
                    if item["type"] == "separator":
                        self.assertIsNone(item["id"])
                        self.assertEqual(item["plugins"], [])

    def test_each_list_has_two_major_separators(self):
        for label, data in self.lists.items():
            with self.subTest(list=label):
                majors = [n for n in get_separator_order(data) if is_major_separator(n)]
                self.assertEqual(len(majors), 2)


class ExampleListCaseCoverageTests(unittest.TestCase):
    """Each documented comparison case must still be demonstrated."""

    def setUp(self):
        self.old = _load(OLD_PATH)
        self.new = _load(NEW_PATH)
        self.old_mods = extract_mods(self.old)
        self.new_mods = extract_mods(self.new)

    def test_version_bump(self):
        old = _by_name(self.old_mods, "powerofthree's Papyrus Extender")
        new = _by_name(self.new_mods, "powerofthree's Papyrus Extender")
        self.assertNotEqual(old["general"]["version"], new["general"]["version"])

    def test_mod_added(self):
        self.assertIsNotNone(_by_name(self.new_mods, "Dear Diary Dark Mode"))
        self.assertIsNone(_by_name(self.old_mods, "Dear Diary Dark Mode"))

    def test_mod_removed(self):
        self.assertIsNotNone(_by_name(self.old_mods, "Old Menu Replacer"))
        self.assertIsNone(_by_name(self.new_mods, "Old Menu Replacer"))

    def test_mod_renamed_under_same_nexus_id(self):
        old = _by_name(self.old_mods, "Skyrim Landscape Overhaul")
        new = _by_name(self.new_mods, "Landscape Fixes For Grass Mods")
        self.assertEqual(old["id"], new["id"])

    def test_mod_moved_between_sections(self):
        old = _by_name(self.old_mods, "SkyUI")
        new = _by_name(self.new_mods, "SkyUI")
        self.assertNotEqual(
            name_key(old["separatorName"]), name_key(new["separatorName"])
        )

    def test_plugin_merge(self):
        merged = _by_name(self.new_mods, "Cutting Room Floor Merged")
        crf = _by_name(self.old_mods, "Cutting Room Floor")
        patch = _by_name(self.old_mods, "Cutting Room Floor - USSEP Patch")
        self.assertEqual(plugin_set(merged), plugin_set(crf) | plugin_set(patch))

    def test_plugin_drift_at_equal_version(self):
        old = _by_name(self.old_mods, "Wet and Cold")
        new = _by_name(self.new_mods, "Wet and Cold")
        self.assertEqual(old["general"]["version"], new["general"]["version"])
        self.assertNotEqual(plugin_set(old), plugin_set(new))

    def test_unknown_version_present(self):
        mod = _by_name(self.new_mods, "Custom Patches")
        self.assertEqual(mod["general"]["version"], "")
        self.assertIsInstance(mod["id"], str)

    def test_separator_differs_only_by_case(self):
        old_names = get_separator_order(self.old)
        new_names = get_separator_order(self.new)
        self.assertIn("Bug Fixes", old_names)
        self.assertIn("BUG FIXES", new_names)
        self.assertNotIn("BUG FIXES", old_names)

    def test_matching_pairs_the_renamed_mod(self):
        matched, _, _ = match_mods(self.old_mods, self.new_mods)
        pairs = {
            name_key(o["modName"]): name_key(n["modName"]) for o, n in matched
        }
        self.assertEqual(
            pairs.get(name_key("Skyrim Landscape Overhaul")),
            name_key("Landscape Fixes For Grass Mods"),
        )


if __name__ == "__main__":
    unittest.main()
