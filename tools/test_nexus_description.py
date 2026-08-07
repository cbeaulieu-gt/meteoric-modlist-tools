"""Checks on the committed Nexus description source files."""
import os
import unittest

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.join(
    os.path.dirname(TOOLS_DIR), "mo2-plugins", "modlist_compare"
)
SHORT_PATH = os.path.join(PLUGIN_DIR, "NEXUS_SHORT_DESCRIPTION.txt")
BBCODE_PATH = os.path.join(PLUGIN_DIR, "NEXUS_DESCRIPTION.bbcode")
SHORT_LIMIT = 350


class TestNexusDescriptionFiles(unittest.TestCase):
    def test_bbcode_description_exists_and_non_empty(self):
        with open(BBCODE_PATH, encoding="utf-8") as f:
            self.assertTrue(f.read().strip())

    def test_short_description_is_one_line_within_limit(self):
        with open(SHORT_PATH, encoding="utf-8") as f:
            short = f.read().strip()
        self.assertTrue(short)
        self.assertNotIn("\n", short)
        self.assertLessEqual(
            len(short), SHORT_LIMIT,
            f"short description is {len(short)} characters (limit {SHORT_LIMIT})",
        )


if __name__ == "__main__":
    unittest.main()
