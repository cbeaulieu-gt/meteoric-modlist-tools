"""Tests for release_reports.py — the per-release report + CHANGELOG stub tool."""

import json
import os
import shutil
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

GEN_CHANGELOG = """# Modlist Changelog

### Summary

- **Added:** 41 mods
- **Removed:** 20 mods
- **Updated:** 69 mods

## Added Mods
"""

EXISTING = """![Banner](x.png)

## Contents

- [Version 1.6.0](#version-160)
- [Version 1.5.0](#version-150)

## Version 1.6.0

**This update is probably not save-safe.**

### Summary
- **Added:** 41 mods

## Version 1.5.0

Old stuff
"""

ENTRY_170 = """## Version 1.7.0

**This update is <!-- TODO: save-safe / probably not save-safe / not save-safe -->.**

<!-- TODO: write highlights (### Category / - bullet sections) -->

### Summary
- **Added:** 3 mods
- **Removed:** 2 mods
- **Updated:** 1 mods

### Detailed Reports
- [Full changelog](changelog/v1.7.0/changelog.md) — complete added/removed/updated mod lists
- [Diff report](https://x.github.io/r/changelog/v1.7.0/diff.html) — full modlist diff
- [Coverage report](https://x.github.io/r/changelog/v1.7.0/coverage.html) — coverage details
"""

COUNTS_170 = {"Added": 3, "Removed": 2, "Updated": 1}


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

    def test_duplicate_version_is_an_error(self):
        _touch(self.dir, "Foo 1.6.0.json")
        _touch(self.dir, "Foo v1.6.0.json")
        with self.assertRaises(ValueError) as caught:
            rr.find_pair(self.dir)
        self.assertIn("Foo 1.6.0.json", str(caught.exception))
        self.assertIn("Foo v1.6.0.json", str(caught.exception))


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


class ChangelogTests(unittest.TestCase):
    def test_parse_counts(self):
        self.assertEqual(rr.parse_counts(GEN_CHANGELOG),
                         {"Added": 41, "Removed": 20, "Updated": 69})

    def test_parse_counts_requires_all_three(self):
        with self.assertRaises(ValueError):
            rr.parse_counts("- **Added:** 1 mods\n- **Removed:** 1 mods\n")

    def test_render_entry_with_pages_url(self):
        self.assertEqual(
            rr.render_entry("1.7.0", COUNTS_170, "https://x.github.io/r/", False),
            ENTRY_170,
        )

    def test_render_entry_adds_trailing_slash_to_pages_url(self):
        self.assertEqual(
            rr.render_entry("1.7.0", COUNTS_170, "https://x.github.io/r", False),
            ENTRY_170,
        )

    def test_render_entry_relative_links_without_pages_url(self):
        text = rr.render_entry("1.7.0", COUNTS_170, "", False)
        self.assertIn("[Diff report](changelog/v1.7.0/diff.html)", text)
        self.assertIn("[Coverage report](changelog/v1.7.0/coverage.html)", text)
        self.assertNotIn("http", text)

    def test_render_entry_load_order_line(self):
        text = rr.render_entry("1.7.0", COUNTS_170, "", True)
        self.assertTrue(text.endswith(
            "- [Load order](loadorder/v1.7.0/) — load order, modlist, plugin groups, and plugins files\n"))

    def test_insert_into_existing_changelog(self):
        out = rr.insert_entry(EXISTING, "1.7.0", ENTRY_170)
        self.assertEqual(out, """![Banner](x.png)

## Contents

- [Version 1.7.0](#version-170)
- [Version 1.6.0](#version-160)
- [Version 1.5.0](#version-150)

""" + ENTRY_170 + """
## Version 1.6.0

**This update is probably not save-safe.**

### Summary
- **Added:** 41 mods

## Version 1.5.0

Old stuff
""")

    def test_insert_is_noop_when_section_exists(self):
        self.assertIsNone(rr.insert_entry(EXISTING, "1.6.0", "## Version 1.6.0\n"))

    def test_insert_into_empty_file(self):
        self.assertEqual(
            rr.insert_entry("", "1.7.0", ENTRY_170),
            "## Contents\n\n- [Version 1.7.0](#version-170)\n\n" + ENTRY_170,
        )

    def test_insert_when_no_contents_list(self):
        out = rr.insert_entry("# Changelog\n\n## Version 1.6.0\n\nx\n", "1.7.0", ENTRY_170)
        self.assertEqual(
            out,
            "## Contents\n\n- [Version 1.7.0](#version-170)\n\n" + ENTRY_170
            + "\n# Changelog\n\n## Version 1.6.0\n\nx\n",
        )

    def test_anchor_drops_dots(self):
        self.assertEqual(rr.anchor("1.10.2"), "version-1102")


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        lists = os.path.join(self.repo, "lists")
        os.makedirs(lists)
        shutil.copy(EX_OLD, lists)
        shutil.copy(EX_NEW, lists)
        self.gh_out = os.path.join(self.repo, "gh_output.txt")
        os.environ["GITHUB_OUTPUT"] = self.gh_out

    def tearDown(self):
        os.environ.pop("GITHUB_OUTPUT", None)
        self.tmp.cleanup()

    def _run(self, *extra):
        return rr.main(["--repo", self.repo, "--pages-url", "https://x/", *extra])

    def _gh_output(self):
        return _read(self.gh_out)

    def test_first_run_generates_everything(self):
        self.assertEqual(self._run(), 0)
        out = os.path.join(self.repo, "changelog", "v1.1")
        self.assertEqual(sorted(os.listdir(out)), ["changelog.md", "coverage.html", "diff.html"])
        changelog = _read(os.path.join(self.repo, "CHANGELOG.md"))
        self.assertIn("## Version 1.1\n", changelog)
        self.assertIn("- [Version 1.1](#version-11)", changelog)
        self.assertIn("https://x/changelog/v1.1/diff.html", changelog)
        self.assertNotIn("Load order", changelog)
        self.assertEqual(self._gh_output(), "version=1.1\n")

    def test_second_run_is_a_noop(self):
        self._run()
        before = _read(os.path.join(self.repo, "CHANGELOG.md"))
        self.assertEqual(self._run(), 0)
        self.assertEqual(_read(os.path.join(self.repo, "CHANGELOG.md")), before)
        self.assertEqual(self._gh_output(), "version=1.1\nversion=\n")

    def test_force_regenerates_reports_but_not_the_entry(self):
        self._run()
        report = os.path.join(self.repo, "changelog", "v1.1", "diff.html")
        _touch(os.path.join(self.repo, "changelog", "v1.1"), "diff.html", "stale")
        before = _read(os.path.join(self.repo, "CHANGELOG.md"))
        self.assertEqual(self._run("--force"), 0)
        self.assertNotEqual(_read(report), "stale")
        self.assertEqual(_read(os.path.join(self.repo, "CHANGELOG.md")), before)
        self.assertEqual(self._gh_output(), "version=1.1\nversion=1.1\n")

    def test_single_list_is_a_noop(self):
        os.remove(os.path.join(self.repo, "lists", "Example List 1.0.json"))
        self.assertEqual(self._run(), 0)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "changelog")))
        self.assertFalse(os.path.exists(os.path.join(self.repo, "CHANGELOG.md")))
        self.assertEqual(self._gh_output(), "version=\n")

    def test_load_order_line_when_folder_exists(self):
        os.makedirs(os.path.join(self.repo, "loadorder", "v1.1"))
        self._run()
        self.assertIn("[Load order](loadorder/v1.1/)", _read(os.path.join(self.repo, "CHANGELOG.md")))

    def test_crlf_changelog_keeps_its_terminator(self):
        path = os.path.join(self.repo, "CHANGELOG.md")
        seeded = ["## Contents", "", "- [Version 1.0](#version-10)", "",
                  "## Version 1.0", "", "Old stuff", ""]
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\r\n".join(seeded))

        self.assertEqual(self._run(), 0)

        after = _read(path)
        self.assertEqual(after.count("\n"), after.count("\r\n"))  # no bare LF left
        self.assertIn("## Version 1.1\r\n", after)
        self.assertIn("- [Version 1.1](#version-11)\r\n", after)
        # Seeded lines survive byte-for-byte and in order: lines were only added.
        rest = after.split("\r\n")
        for line in seeded:
            self.assertIn(line, rest)
            rest = rest[rest.index(line) + 1:]

    def test_custom_lists_and_changelog_paths(self):
        os.rename(os.path.join(self.repo, "lists"), os.path.join(self.repo, "exports"))
        rc = rr.main(["--repo", self.repo, "--lists", "exports", "--changelog-file", "HISTORY.md"])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "HISTORY.md")))
        self.assertIn("[Diff report](changelog/v1.1/diff.html)",
                      _read(os.path.join(self.repo, "HISTORY.md")))


if __name__ == "__main__":
    unittest.main()
