"""Tests for the coverage ignore store."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coverage_ignore import (
    IgnoreSet,
    resolve_ignore_path,
    load_ignore,
    save,
    add,
    remove,
    is_ignored,
)


class ResolvePathTest(unittest.TestCase):
    def test_none_for_stdout(self):
        self.assertIsNone(resolve_ignore_path(None, "lists/Example List 1.1.json"))

    def test_directory(self):
        p = resolve_ignore_path("output/", "lists/Example List 1.1.json")
        self.assertEqual(
            os.path.normpath(p),
            os.path.normpath("output/Example List 1.1/.coverage-ignore.txt"),
        )

    def test_explicit_file(self):
        p = resolve_ignore_path("output/x.coverage.html", "lists/Example List.json")
        self.assertEqual(
            os.path.normpath(p), os.path.normpath("output/.coverage-ignore.txt")
        )


class LoadSaveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, ".coverage-ignore.txt")

    def test_missing_file_is_empty(self):
        self.assertEqual(len(load_ignore(self.path)), 0)
        self.assertEqual(len(load_ignore(None)), 0)

    def test_comments_blanks_dupes(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("# a comment\n\nMod One\nMod One\n  Mod Two  \n")
        ig = load_ignore(self.path)
        self.assertEqual(len(ig), 2)  # duplicate collapsed
        self.assertTrue(ig.contains_name("Mod One"))
        self.assertTrue(ig.contains_name("Mod Two"))

    def test_save_sorted_with_header(self):
        save(self.path, ["Zebra", "alpha", "Zebra"])
        with open(self.path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("#"))
        lines = [l for l in text.splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, ["alpha", "Zebra"])  # case-insensitive sort, deduped


class MatchTest(unittest.TestCase):
    def test_normalized_match(self):
        ig = IgnoreSet(["Phoenix - Compendium SSE"])
        self.assertTrue(is_ignored(ig, {"modName": "phoenix compendium"}))

    def test_is_ignored_none(self):
        self.assertFalse(is_ignored(None, {"modName": "Anything"}))


class AddRemoveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, ".coverage-ignore.txt")

    def test_add_remove_roundtrip(self):
        add(self.path, "Cool Mod")
        self.assertTrue(load_ignore(self.path).contains_name("Cool Mod"))
        add(self.path, "Cool Mod")  # idempotent
        self.assertEqual(len(load_ignore(self.path)), 1)
        remove(self.path, "Cool Mod")
        self.assertFalse(load_ignore(self.path).contains_name("Cool Mod"))
        remove(self.path, "Cool Mod")  # idempotent, no error


if __name__ == "__main__":
    unittest.main()
