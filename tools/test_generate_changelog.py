"""Tests for the generate_changelog library entry point."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_changelog
from modlist_utils import load_modlist

EXAMPLES_LISTS = os.path.join(os.path.dirname(__file__), "..", "examples", "lists")
EXAMPLES_REPORTS = os.path.join(os.path.dirname(__file__), "..", "examples", "reports")


class TestGenerateEntryPoint(unittest.TestCase):
    def test_generate_matches_committed_report(self):
        old = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.0.json"))
        new = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.1.json"))
        markdown = generate_changelog.generate(old, new)
        committed = os.path.join(
            EXAMPLES_REPORTS, "Example List 1.1", "Example List 1.0.changelog.md"
        )
        with open(committed, "r", encoding="utf-8", newline="") as f:
            self.assertEqual(markdown, f.read())


_PROGRESS_LISTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "examples", "lists"
)


class GenerateProgressTest(unittest.TestCase):
    def _load(self, name):
        from modlist_utils import load_modlist
        return load_modlist(os.path.join(_PROGRESS_LISTS, name))

    def test_generate_forwards_progress(self):
        calls = []
        old = self._load("Example List 1.0.json")
        new = self._load("Example List 1.1.json")
        generate_changelog.generate(
            old, new, progress=lambda d, t: calls.append((d, t))
        )
        self.assertTrue(calls)
        done, total = calls[-1]
        self.assertGreater(total, 0)
        self.assertEqual(done, total)


if __name__ == "__main__":
    unittest.main()
