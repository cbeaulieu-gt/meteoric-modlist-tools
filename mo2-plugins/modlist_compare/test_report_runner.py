"""Tests for report_runner (vendors the tool modules first, no Qt/mobase)."""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_PLUGIN_DIR))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))   # mo2-plugins/
sys.path.insert(0, os.path.join(_REPO_ROOT, "tools"))

import package_plugin

package_plugin.vendor()  # report_runner needs a populated _vendor/

from modlist_compare import report_runner

EXAMPLES_LISTS = os.path.join(_REPO_ROOT, "examples", "lists")
OLD_LIST = os.path.join(EXAMPLES_LISTS, "Example List 1.0.json")
NEW_LIST = os.path.join(EXAMPLES_LISTS, "Example List 1.1.json")


def _side(path):
    return report_runner.load_side_from_file(path)


# A rendered coverage row looks like:
#   <div class="mod-row mod-ignored" data-names="sky idles">
# The class list is the state-dependent part; "mod-ignored" also appears in the
# report's inlined CSS/JS, so tests must key on this markup, not on the bare word.
_ROW_RE = re.compile(r'<div class="mod-row ([^"]*)"[^>]*data-names="([^"]*)"')


def _row_classes(html, mod_name):
    """Class list of the rendered coverage row for mod_name (None if absent)."""
    for classes, names in _ROW_RE.findall(html):
        if mod_name.lower() in names.lower().split("\n"):
            return classes.split()
    return None


class TestLoadSideFromFile(unittest.TestCase):
    def test_loads_name_and_data(self):
        side = _side(OLD_LIST)
        self.assertEqual(side.name, "Example List 1.0")
        self.assertFalse(side.from_profile)
        self.assertTrue(isinstance(side.data, list) and side.data)

    def test_rejects_non_list_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                json.dump({"not": "a modlist"}, f)
            with self.assertRaises(ValueError):
                report_runner.load_side_from_file(bad)


class TestRunReports(unittest.TestCase):
    def test_writes_all_three_reports_with_cli_naming(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST),
                ["coverage", "diff", "changelog"], tmp, save_exports=False,
            )
            self.assertEqual(result.errors, [])
            rel = sorted(os.path.relpath(p, tmp) for p in result.written)
            self.assertEqual(rel, [
                os.path.join("Example List 1.0", "Example List 1.1.changelog.md"),
                os.path.join("Example List 1.0", "Example List 1.1.coverage.html"),
                os.path.join("Example List 1.0", "Example List 1.1.diff.html"),
            ])
            # inside the temp dir's lifetime: the files still exist here
            for p in result.written:
                self.assertTrue(os.path.getsize(p) > 0)

    def _coverage_html(self, ignored_names=None):
        """Render coverage (1.1 vs 1.0) with an optional per-target ignore file."""
        with tempfile.TemporaryDirectory() as tmp:
            if ignored_names is not None:
                target_dir = os.path.join(tmp, "Example List 1.0")
                os.makedirs(target_dir)
                with open(os.path.join(target_dir, ".coverage-ignore.txt"), "w",
                          encoding="utf-8") as f:
                    f.write("\n".join(ignored_names) + "\n")
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST), ["coverage"], tmp,
                save_exports=False,
            )
            self.assertEqual(result.errors, [])
            with open(result.written[0], encoding="utf-8") as f:
                return f.read()

    def test_coverage_ignores_nothing_without_an_ignore_file(self):
        # Baseline: Sky Idles is source-only, so it renders as an Add, not Ignored.
        classes = _row_classes(self._coverage_html(), "Sky Idles")
        self.assertIsNotNone(classes, "Sky Idles row missing from coverage report")
        self.assertNotIn("mod-ignored", classes)

    def test_coverage_reads_ignore_file(self):
        html = self._coverage_html(["Sky Idles"])
        # State-dependent: the ignored mod's own row must carry the class.
        self.assertEqual(_row_classes(html, "Sky Idles"), ["mod-ignored"])
        # And only that mod — a blanket class change would fail here.
        self.assertNotIn("mod-ignored", _row_classes(html, "Timing is Everything"))

    def test_saves_live_export(self):
        live = _side(NEW_LIST)
        live.from_profile = True
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                live, _side(OLD_LIST), ["changelog"], tmp, save_exports=True,
            )
            saved = os.path.join(tmp, "Example List 1.1.json")
            self.assertIn(saved, result.written)
            round_trip = report_runner.load_side_from_file(saved)
            # Live sides only: the file-loaded side must NOT be re-exported.
            not_saved = os.path.join(tmp, "Example List 1.0.json")
            self.assertNotIn(not_saved, result.written)
            self.assertFalse(os.path.exists(not_saved))
            self.assertEqual(len(result.written), 2)  # changelog + one export
        self.assertEqual(round_trip.data, live.data)
        self.assertEqual(result.errors, [])

    def test_saves_live_export_into_a_not_yet_created_dest_dir(self):
        # Only the report writes create dest_dir; when every report fails, the
        # live export must still land (dest_dir created by the export branch).
        live = _side(NEW_LIST)
        live.from_profile = True
        boom = mock.Mock(side_effect=RuntimeError("boom"))
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "fresh")  # deliberately does not exist yet
            with mock.patch.object(report_runner.generate_changelog, "generate", boom):
                result = report_runner.run_reports(
                    live, _side(OLD_LIST), ["changelog"], dest, save_exports=True,
                )
            saved = os.path.join(dest, "Example List 1.1.json")
            self.assertEqual(result.written, [saved])
            self.assertTrue(os.path.getsize(saved) > 0)
            self.assertEqual(result.errors, ["changelog: boom"])

    def test_generator_failure_is_collected_and_later_reports_still_run(self):
        # A real generator blows up on the FIRST requested type; the second must
        # still be produced, proving the loop continues past a failure.
        boom = mock.Mock(side_effect=RuntimeError("boom"))
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(report_runner.generate_coverage, "generate", boom):
                result = report_runner.run_reports(
                    _side(NEW_LIST), _side(OLD_LIST), ["coverage", "diff"], tmp,
                    save_exports=False,
                )
            self.assertTrue(boom.called)
            self.assertEqual(result.errors, ["coverage: boom"])
            self.assertEqual(len(result.written), 1)
            self.assertTrue(result.written[0].endswith(".diff.html"))
            self.assertTrue(os.path.getsize(result.written[0]) > 0)
            # The failed report left no partial file behind.
            self.assertFalse(os.path.exists(os.path.join(
                tmp, "Example List 1.0", "Example List 1.1.coverage.html")))

    def test_unknown_report_type_is_collected_not_fatal(self):
        # Bad type first, so a following good type proves loop continuation.
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST), ["nonsense", "diff"], tmp,
                save_exports=False,
            )
            self.assertEqual(len(result.written), 1)
            self.assertTrue(result.written[0].endswith(".diff.html"))
        self.assertEqual(len(result.errors), 1)
        self.assertIn("nonsense", result.errors[0])


class RunReportsProgressTest(unittest.TestCase):
    def test_progress_monotonic_labeled_and_complete(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                _side(OLD_LIST), _side(NEW_LIST), ["coverage", "changelog"], tmp,
                save_exports=False,
                progress=lambda fraction, message: calls.append((fraction, message)),
            )
        self.assertEqual(result.errors, [])
        self.assertFalse(result.cancelled)
        fractions = [f for f, _m in calls]
        self.assertEqual(fractions, sorted(fractions))
        self.assertEqual(fractions[-1], 1.0)
        messages = {m for _f, m in calls}
        self.assertIn("Generating coverage… (1 of 2)", messages)
        self.assertIn("Generating changelog… (2 of 2)", messages)

    def test_cancel_keeps_earlier_reports_skips_rest_and_exports(self):
        def cancel_on_changelog(fraction, message):
            if "changelog" in message:
                raise report_runner.Cancelled()
        live = report_runner.ListSide(
            name="Live Profile", data=_side(OLD_LIST).data, from_profile=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                live, _side(NEW_LIST), ["coverage", "changelog"], tmp,
                save_exports=True, progress=cancel_on_changelog,
            )
            self.assertTrue(result.cancelled)
            self.assertEqual(result.errors, [])
            self.assertEqual(len(result.written), 1)
            self.assertTrue(result.written[0].endswith("Live Profile.coverage.html"))
            self.assertFalse(
                os.path.exists(os.path.join(tmp, "Live Profile.json"))
            )


class TestRebase(unittest.TestCase):
    def test_rebase_writes_cli_named_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST), ["rebase"], tmp,
                save_exports=False, base=_side(OLD_LIST),
            )
            self.assertEqual(result.errors, [])
            self.assertEqual(result.written, [os.path.join(
                tmp, "Example List 1.0",
                "Example List 1.1 (from Example List 1.0).rebase.html")])
            self.assertTrue(os.path.getsize(result.written[0]) > 0)

    def test_rebase_without_base_is_an_error_and_other_reports_still_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST), ["rebase", "changelog"], tmp,
                save_exports=False, base=None,
            )
            self.assertEqual(
                result.errors, ["rebase: a previous-base list is required"])
            self.assertEqual(len(result.written), 1)
            self.assertTrue(result.written[0].endswith(".changelog.md"))

    def test_save_exports_writes_every_profile_side(self):
        data = _side(OLD_LIST).data
        a = report_runner.ListSide("Base", data, from_profile=True)
        b = report_runner.ListSide("Custom", data, from_profile=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                a, b, [], tmp, save_exports=True)
            self.assertEqual(result.errors, [])
            for name in ("Base.json", "Custom.json"):
                self.assertTrue(os.path.exists(os.path.join(tmp, name)))


class TestValidateRun(unittest.TestCase):
    def test_same_name_on_both_sides(self):
        msg = report_runner.validate_run(
            report_runner.ListSide("Same", []),
            report_runner.ListSide("same", []), ["diff"])
        self.assertIn("same name", msg)

    def test_rebase_requires_a_base(self):
        msg = report_runner.validate_run(
            report_runner.ListSide("A", []),
            report_runner.ListSide("B", []), ["rebase"], base=None)
        self.assertIn("previous base", msg)

    def test_valid_run_is_none(self):
        self.assertIsNone(report_runner.validate_run(
            report_runner.ListSide("A", []),
            report_runner.ListSide("B", []), ["diff"]))


if __name__ == "__main__":
    unittest.main()
