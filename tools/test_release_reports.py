"""Tests for release_reports.py — the per-release report + CHANGELOG stub tool."""

import json
import os
import tempfile
import unittest

import generate_changelog
import generate_coverage
import generate_diff
import release_reports as rr

EXAMPLES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "examples", "lists"
)
EX_OLD = os.path.join(EXAMPLES, "Example List 1.0.json")
EX_NEW = os.path.join(EXAMPLES, "Example List 1.1.json")


def _touch(directory, name, content=""):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return path


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


class VersionTests(unittest.TestCase):
    def test_trailing_token_wins_over_earlier_tokens(self):
        self.assertEqual(
            rr.parse_version("NORDIC SOULS v3.2.0 - PBR Edition 1.6.0.json"),
            ((1, 6, 0), "1.6.0"),
        )

    def test_plain_forms(self):
        self.assertEqual(rr.parse_version("Meteoric 0.1.0.json"), ((0, 1, 0), "0.1.0"))
        self.assertEqual(rr.parse_version("v2.0.2.json"), ((2, 0, 2), "2.0.2"))
        self.assertEqual(rr.parse_version("2.0.2.json"), ((2, 0, 2), "2.0.2"))
        self.assertEqual(rr.parse_version("my-list_1.10.json"), ((1, 10), "1.10"))

    def test_no_token_or_wrong_extension(self):
        self.assertIsNone(rr.parse_version("My List.json"))
        self.assertIsNone(rr.parse_version("notes 1.0.txt"))
        self.assertIsNone(rr.parse_version("1.0.json.bak"))

    def test_extension_is_case_insensitive(self):
        self.assertEqual(rr.parse_version("List 1.0.JSON"), ((1, 0), "1.0"))


class PairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_pairs_two_newest_numerically(self):
        _touch(self.dir, "Foo 1.9.0.json")
        _touch(self.dir, "Foo 1.10.0.json")
        _touch(self.dir, "Foo 1.2.0.json")
        old, new, label = rr.find_pair(self.dir)
        self.assertEqual(os.path.basename(old), "Foo 1.9.0.json")
        self.assertEqual(os.path.basename(new), "Foo 1.10.0.json")
        self.assertEqual(label, "1.10.0")

    def test_base_name_may_change_between_releases(self):
        _touch(self.dir, "NORDIC SOULS v3.1.1 - PBR Edition 1.5.0.json")
        _touch(self.dir, "NORDIC SOULS v3.2.0 - PBR Edition 1.6.0.json")
        old, new, label = rr.find_pair(self.dir)
        self.assertIn("1.5.0", os.path.basename(old))
        self.assertIn("1.6.0", os.path.basename(new))
        self.assertEqual(label, "1.6.0")

    def test_unversioned_files_are_ignored(self):
        _touch(self.dir, "Foo 1.0.json")
        _touch(self.dir, "Foo 1.1.json")
        _touch(self.dir, "README.json")
        _touch(self.dir, "Foo 9.9.txt")
        _, new, _ = rr.find_pair(self.dir)
        self.assertEqual(os.path.basename(new), "Foo 1.1.json")

    def test_fewer_than_two_versioned_files(self):
        self.assertIsNone(rr.find_pair(self.dir))
        _touch(self.dir, "Foo 1.0.json")
        _touch(self.dir, "Unversioned.json")
        self.assertIsNone(rr.find_pair(self.dir))


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "changelog", "v1.1")
        self.texts = rr.generate_reports(EX_OLD, EX_NEW, self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_exactly_the_three_fixed_names(self):
        self.assertEqual(
            sorted(os.listdir(self.out)),
            ["changelog.md", "coverage.html", "diff.html"],
        )
        self.assertEqual(set(self.texts), {"changelog.md", "coverage.html", "diff.html"})

    def test_content_matches_the_generators(self):
        old, new = _load(EX_OLD), _load(EX_NEW)
        expected = {
            "changelog.md": generate_changelog.generate(old, new),
            "diff.html": generate_diff.generate(
                old, new, "Example List 1.0", "Example List 1.1"),
            "coverage.html": generate_coverage.generate(
                old, new, "Example List 1.0", "Example List 1.1"),
        }
        for name, text in expected.items():
            with self.subTest(report=name):
                self.assertEqual(self.texts[name], text)
                self.assertEqual(_read(os.path.join(self.out, name)), text)


if __name__ == "__main__":
    unittest.main()
