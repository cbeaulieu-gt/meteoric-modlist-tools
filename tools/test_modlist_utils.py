"""Unit tests for modlist_utils helpers."""

import os
import sys
import unittest

# Allow `import modlist_utils` when run directly (same-dir import, like the scripts).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tempfile

from modlist_utils import (
    compare_versions,
    get_separator_order,
    is_major_separator,
    major_display_name,
    match_mods,
    name_key,
    plugin_set,
    resolve_output_path,
    recover_version,
    parse_archive_identity,
    same_name,
)


class CategoryNamesTest(unittest.TestCase):
    def test_parses_id_and_name(self):
        from modlist_utils import parse_category_names
        text = "\ufeff1|Animations|2|0\n2|Armour|3,4|0\n\nbad line\nx|Nope|1|0\n3||1|0\n"
        self.assertEqual(parse_category_names(text), {"1": "Animations", "2": "Armour"})

    def test_load_reads_file(self):
        from modlist_utils import load_category_names
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "categories.dat")
            with open(p, "w", encoding="utf-8") as f:
                f.write("5|Gameplay|1|0\n")
            self.assertEqual(load_category_names(p), {"5": "Gameplay"})


class NameKeyTest(unittest.TestCase):
    def test_case_insensitive(self):
        self.assertEqual(name_key("Core"), name_key("CORE"))
        self.assertTrue(same_name("Core", "cORe"))

    def test_trims_surrounding_whitespace(self):
        self.assertTrue(same_name("  Core ", "Core"))

    def test_distinct_names_stay_distinct(self):
        self.assertFalse(same_name("Core", "Core Patches"))

    def test_none_is_empty(self):
        self.assertEqual(name_key(None), "")

    def test_unlike_normalize_name_nothing_else_is_stripped(self):
        # normalize_name() strips version/edition suffixes; name_key must not.
        self.assertNotEqual(name_key("My Mod SSE"), name_key("My Mod"))


class MajorSeparatorTest(unittest.TestCase):
    def test_dash_wrapped_is_major(self):
        self.assertTrue(is_major_separator("---------- BASE ----------"))
        self.assertTrue(is_major_separator("- - - GAMEPLAY CHANGES - - -"))

    def test_ordinary_separator_is_not_major(self):
        self.assertFalse(is_major_separator("Core - SKSE Plugins & Fixes"))
        self.assertFalse(is_major_separator("21-9 WideScreen Support"))
        self.assertFalse(is_major_separator(""))

    def test_display_name_strips_decoration(self):
        self.assertEqual(major_display_name("---------- BASE ----------"), "BASE")
        self.assertEqual(
            major_display_name("- - - GAMEPLAY CHANGES - - -"), "GAMEPLAY CHANGES")


class SeparatorOrderTest(unittest.TestCase):
    def test_case_variants_collapse_to_first_spelling(self):
        data = [
            {"type": "separator", "separatorName": "Core"},
            {"type": "separator", "separatorName": "CORE"},
            {"type": "separator", "separatorName": "Visuals"},
        ]
        self.assertEqual(get_separator_order(data), ["Core", "Visuals"])


class CompareVersionsTest(unittest.TestCase):
    def test_numeric_greater(self):
        self.assertEqual(compare_versions("4.3.6", "4.3.5"), 1)

    def test_numeric_less(self):
        self.assertEqual(compare_versions("4.3.5", "4.3.6"), -1)

    def test_equal_strings(self):
        self.assertEqual(compare_versions("2.0", "2.0"), 0)

    def test_zero_padding_equal(self):
        self.assertEqual(compare_versions("1.2", "1.2.0"), 0)

    def test_numeric_equal_suffix_differs(self):
        self.assertIsNone(compare_versions("1.7", "1.7beta"))

    def test_letter_suffix_same_numeric(self):
        self.assertIsNone(compare_versions("4.3.6c", "4.3.6"))

    def test_date_greater(self):
        self.assertEqual(compare_versions("7/31/2025", "7/30/2025"), 1)

    def test_date_less(self):
        self.assertEqual(compare_versions("1/1/2024", "12/31/2024"), -1)

    def test_non_numeric_unknown_direction(self):
        self.assertIsNone(compare_versions("MCM-01", "Alpha-58"))

    def test_date_vs_numeric_not_comparable(self):
        self.assertIsNone(compare_versions("7/31/2025", "4.3.6"))

    def test_unknown_inputs(self):
        self.assertIsNone(compare_versions("Unknown", "2.0"))


class ResolveOutputPathTest(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(
            resolve_output_path(None, "a/Source.json", "b/Target.json", "coverage", "html")
        )

    def test_empty_returns_none(self):
        self.assertIsNone(
            resolve_output_path("", "a/Source.json", "b/Target.json", "coverage", "html")
        )

    def test_explicit_file_path_unchanged(self):
        self.assertEqual(
            resolve_output_path(
                "out/foo.html", "a/Source.json", "b/Target.json", "coverage", "html"
            ),
            "out/foo.html",
        )

    def test_trailing_separator_builds_nested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = resolve_output_path(
                tmp + os.sep,
                "lists/Other List 2.0.1.json",
                "lists/Example List 1.0.json",
                "coverage",
                "html",
            )
            expected = os.path.join(
                tmp, "Example List 1.0", "Other List 2.0.1.coverage.html"
            )
            self.assertEqual(result, expected)
            self.assertTrue(os.path.isdir(os.path.dirname(result)))

    def test_existing_directory_without_trailing_sep(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = resolve_output_path(tmp, "old.json", "new.json", "diff", "html")
            expected = os.path.join(tmp, "new", "old.diff.html")
            self.assertEqual(result, expected)
            self.assertTrue(os.path.isdir(os.path.dirname(result)))

    def test_first_name_override_names_the_file(self):
        with tempfile.TemporaryDirectory() as root:
            out = resolve_output_path(
                root + os.sep,
                "lists/New.json",
                "lists/Target.json",
                "rebase",
                "html",
                first_name="New (from Old)",
            )
            self.assertEqual(
                out, os.path.join(root, "Target", "New (from Old).rebase.html")
            )

    def test_no_override_uses_first_path_basename(self):
        with tempfile.TemporaryDirectory() as root:
            out = resolve_output_path(
                root + os.sep, "lists/New.json", "lists/Target.json", "coverage", "html"
            )
            self.assertEqual(out, os.path.join(root, "Target", "New.coverage.html"))


def _mod(modName, id=None, plugins=None, fileid=None, installationFile=None):
    """Build a minimal mod dict for match_mods tests."""
    m = {"type": "mod", "modName": modName, "plugins": plugins or []}
    if id is not None:
        m["id"] = id
    general = {}
    if installationFile is not None:
        general["installationFile"] = installationFile
    m["general"] = general
    files = [{"modid": str(id), "fileid": fileid}] if fileid is not None else []
    m["installed"] = {"size": len(files), "files": files}
    return m


class MatchModsTest(unittest.TestCase):
    def _matched_names(self, matched):
        return {(o["modName"], n["modName"]) for o, n in matched}

    def test_basic_add_and_remove_by_id(self):
        sewers = _mod("Skyrim Sewers", id=1)
        frostfall = _mod("Frostfall", id=2)
        sewers2 = _mod("Skyrim Sewers", id=1)
        wildcat = _mod("Wildcat Combat", id=3)
        matched, added, removed = match_mods([sewers, frostfall], [sewers2, wildcat])
        self.assertEqual(self._matched_names(matched), {("Skyrim Sewers", "Skyrim Sewers")})
        self.assertEqual([m["modName"] for m in removed], ["Frostfall"])
        self.assertEqual([m["modName"] for m in added], ["Wildcat Combat"])

    def test_same_page_no_fileid_matches_by_installation_file(self):
        """Reported bug: same modpage hosts several mods. The first source mod sharing
        the page id must NOT steal the single target mod's slot when names disagree."""
        wyrmstooth = _mod(
            "Faithful Faces - Wyrmstooth", id=143247,
            plugins=["Faithful Faces - Wyrmstooth.esp"], fileid="614068",
            installationFile="Faithful Faces - Wyrmstooth-143247-1-0-1743851064.zip",
        )
        environs_src = _mod(
            "Faithful Faces - Environs", id=143247,
            installationFile="Faithful Faces - Environs-143247-1-0-1743754758.zip",
        )
        environs_tgt = _mod(
            "Faithful Faces - Environs", id=143247,
            installationFile="Faithful Faces - Environs-143247-1-0-1743754758.zip",
        )
        matched, added, removed = match_mods([wyrmstooth, environs_src], [environs_tgt])
        self.assertEqual(
            self._matched_names(matched),
            {("Faithful Faces - Environs", "Faithful Faces - Environs")},
        )
        self.assertEqual([m["modName"] for m in removed], ["Faithful Faces - Wyrmstooth"])
        self.assertEqual(added, [])

    def test_fileid_matches_across_rename_within_shared_page(self):
        """When a page is ambiguous, a shared (modid, fileid) confirms identity even if
        the display names were changed between lists."""
        alpha = _mod("Alpha Patch", id=100, fileid="111")
        beta_old = _mod("Beta Thing Old Title", id=100, fileid="222")
        beta_new = _mod("Completely Renamed Beta", id=100, fileid="222")
        matched, added, removed = match_mods([alpha, beta_old], [beta_new])
        self.assertEqual(
            self._matched_names(matched),
            {("Beta Thing Old Title", "Completely Renamed Beta")},
        )
        self.assertEqual([m["modName"] for m in removed], ["Alpha Patch"])
        self.assertEqual(added, [])

    def test_installation_file_match_ignores_numeric_rename_prefix(self):
        """An identical archive differing only by MO2's leading '1_' rename prefix still
        counts as the same file."""
        sibling = _mod("OAR Sibling", id=98308, fileid="999")
        oar_old = _mod(
            "Open Animation Replacer - IED conditions", id=98308,
            installationFile="Open Animation Replacer - IED conditions-98308-1-0-3-1693587943.zip",
        )
        oar_new = _mod(
            "OAR Conditions Pack", id=98308,
            installationFile="1_Open Animation Replacer - IED conditions-98308-1-0-3-1693587943.zip",
        )
        matched, added, removed = match_mods([sibling, oar_old], [oar_new])
        self.assertEqual(
            self._matched_names(matched),
            {("Open Animation Replacer - IED conditions", "OAR Conditions Pack")},
        )
        self.assertEqual([m["modName"] for m in removed], ["OAR Sibling"])
        self.assertEqual(added, [])

    def test_same_page_exact_name_beats_cross_archive_match(self):
        """A page hosts a main mod and its patch in both lists. In the source, the mod
        named "...USSEP Patch" was installed from the *main* archive, so it shares an
        installationFile with the target's main mod. Exact-name pairs (main<->main,
        patch<->patch) must win over that cross archive match — otherwise the real main
        mod is wrongly reported as an Add instead of a version pair."""
        main_old = _mod(
            "Farmhouse Chimneys SE", id=8766, plugins=["FarmhouseChimneys.esp"],
            installationFile="Farmhouse Chimneys SE v4.2.1-8766-4-2-1-1693263868.7z",
        )
        patch_src = _mod(
            "Farmhouse Chimneys SE - USSEP Patch", id=8766, plugins=["FarmhouseChimneys.esp"],
            installationFile="Farmhouse Chimneys SE v4.3.1-8766-4-3-1-1777212854.7z",
        )
        main_new = _mod(
            "Farmhouse Chimneys SE", id=8766, plugins=["FarmhouseChimneys.esp"],
            installationFile="Farmhouse Chimneys SE v4.3.1-8766-4-3-1-1777212854.7z",
        )
        patch_tgt = _mod(
            "Farmhouse Chimneys SE - USSEP Patch", id=8766,
            plugins=["FarmhouseChimneys - USSEP Patch.esp"], fileid="243226",
            installationFile="Farmhouse Chimneys SE - USSEP Patch-8766-4-1-1-1637503578.7z",
        )
        matched, added, removed = match_mods([main_old, patch_src], [main_new, patch_tgt])
        self.assertEqual(
            self._matched_names(matched),
            {
                ("Farmhouse Chimneys SE", "Farmhouse Chimneys SE"),
                ("Farmhouse Chimneys SE - USSEP Patch", "Farmhouse Chimneys SE - USSEP Patch"),
            },
        )
        self.assertEqual(removed, [])
        self.assertEqual(added, [])

    def test_unique_page_id_still_matches_rename_blindly(self):
        """A page that hosts a single mod in each list keeps blind id matching so a plain
        rename (same id, no fileid/installationFile) is still recognized."""
        old = _mod("Cool Mod SE", id=200)
        new = _mod("Cool Mod Redux Edition", id=200)
        matched, added, removed = match_mods([old], [new])
        self.assertEqual(
            self._matched_names(matched), {("Cool Mod SE", "Cool Mod Redux Edition")}
        )
        self.assertEqual(removed, [])
        self.assertEqual(added, [])


class MatchModsProgressTest(unittest.TestCase):
    def test_progress_monotonic_and_complete(self):
        old = [_mod("Alpha", id=1), _mod("Beta", id=2), _mod("Gamma")]
        new = [_mod("Alpha", id=1), _mod("Delta")]
        calls = []
        match_mods(old, new, progress=lambda done, total: calls.append((done, total)))
        self.assertTrue(calls)
        self.assertTrue(all(total == 3 for _done, total in calls))
        dones = [done for done, _total in calls]
        self.assertEqual(dones, sorted(dones))
        self.assertEqual(dones[-1], 3)

    def test_progress_empty_old_list(self):
        calls = []
        match_mods([], [_mod("Delta")], progress=lambda d, t: calls.append((d, t)))
        self.assertEqual(calls, [(0, 0)])

    def test_progress_does_not_change_results(self):
        old = [_mod("Alpha", id=1), _mod("Beta", id=2)]
        new = [_mod("Alpha", id=1), _mod("Wildcat", id=3)]
        with_cb = match_mods(old, new, progress=lambda d, t: None)
        without = match_mods(old, new)
        self.assertEqual(with_cb, without)

    def test_progress_callback_exception_propagates(self):
        def boom(done, total):
            raise RuntimeError("cancelled")
        with self.assertRaises(RuntimeError):
            match_mods([_mod("Alpha")], [_mod("Beta")], progress=boom)


class TestRecoverVersion(unittest.TestCase):
    def test_basic_with_epoch(self):
        self.assertEqual(
            recover_version("Some Mod-12345-1-0-1700000000.7z", "12345"), "1.0")

    def test_no_epoch_whole_tail_is_version(self):
        self.assertEqual(
            recover_version("Dragon.Priest.2k-4974-1-2.7z", "4974"), "1.2")

    def test_v_prefix_dropped(self):
        self.assertEqual(
            recover_version("Modex - v2.2.1-137877-v2-2-1-1774728262.zip",
                            "137877"), "2.2.1")

    def test_word_tag_with_digit_kept(self):
        self.assertEqual(
            recover_version("DynDOLOD NG-97720-Alpha-41-1778434637.7z",
                            "97720"), "Alpha-41")

    def test_rightmost_modid_anchors(self):
        self.assertEqual(
            recover_version("Mod-12345-extra-12345-1-0-1700000000.7z",
                            "12345"), "1.0")

    def test_timestamp_only_tail_is_none(self):
        self.assertIsNone(
            recover_version("Some Mod-12345-1700000000.7z", "12345"))

    def test_no_modid_marker_is_none(self):
        self.assertIsNone(
            recover_version("Some Mod-99999-1-0-1700000000.7z", "12345"))

    def test_digitless_word_fragment_rejected(self):
        self.assertIsNone(
            recover_version("Ghosts - Reduced Cut-67019-fs-1728018062.zip",
                            "67019"))

    def test_empty_inputs_none(self):
        self.assertIsNone(recover_version("", "12345"))
        self.assertIsNone(recover_version("Some Mod-12345-1-0.7z", ""))
        self.assertIsNone(recover_version(None, "12345"))


class TestParseArchiveIdentity(unittest.TestCase):
    def test_name_stem_and_version(self):
        self.assertEqual(
            parse_archive_identity("Cool Mod-100-2-0-1700000001.zip", "100"),
            ("cool mod", "2.0"))

    def test_leading_spaces_and_punctuation_preserved(self):
        stem, ver = parse_archive_identity(
            "  Superior Hair - Rough Hair-36510-2-0.7z", "36510")
        self.assertEqual(stem, "superior hair - rough hair")
        self.assertEqual(ver, "2.0")

    def test_rename_prefix_stripped(self):
        stem, _ = parse_archive_identity("1_Cool Mod-100-2-0.zip", "100")
        self.assertEqual(stem, "cool mod")

    def test_variants_stay_distinct(self):
        a, _ = parse_archive_identity("LS Compendium (16-9) (2K)-138294-2-1.zip",
                                      "138294")
        b, _ = parse_archive_identity("LS Compendium (21-9) (4K)-138294-2-1.zip",
                                      "138294")
        self.assertNotEqual(a, b)

    def test_anchor_absent_returns_none_pair(self):
        self.assertEqual(
            parse_archive_identity("Cool Mod-999-2-0.zip", "100"), (None, None))

    def test_epoch_only_tail_gives_name_but_no_version(self):
        stem, ver = parse_archive_identity("Cool Mod-100-1700000000.7z", "100")
        self.assertEqual(stem, "cool mod")
        self.assertIsNone(ver)

    def test_empty_inputs(self):
        self.assertEqual(parse_archive_identity("", "100"), (None, None))
        self.assertEqual(parse_archive_identity("Mod-100-1-0.zip", ""),
                         (None, None))


class PluginSetTest(unittest.TestCase):
    def test_normalizes_case_and_order(self):
        a = {"plugins": ["Alpha.esp", "beta.ESL"]}
        b = {"plugins": ["BETA.esl", "alpha.ESP"]}
        self.assertEqual(plugin_set(a), plugin_set(b))

    def test_missing_and_empty_are_equal_empty(self):
        self.assertEqual(plugin_set({}), frozenset())
        self.assertEqual(plugin_set({"plugins": []}), plugin_set({}))

    def test_blank_entries_dropped(self):
        self.assertEqual(
            plugin_set({"plugins": ["", "  ", "A.esp"]}), frozenset({"a.esp"})
        )

    def test_whitespace_trimmed(self):
        self.assertEqual(
            plugin_set({"plugins": [" A.esp "]}), frozenset({"a.esp"})
        )

    def test_difference_detected(self):
        a = {"plugins": ["A.esp", "B.esp"]}
        b = {"plugins": ["A.esp"]}
        self.assertNotEqual(plugin_set(a), plugin_set(b))


if __name__ == "__main__":
    unittest.main()
