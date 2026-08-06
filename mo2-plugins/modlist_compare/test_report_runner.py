"""Tests for report_runner (vendors the tool modules first, no Qt/mobase)."""
import json
import os
import sys
import tempfile
import unittest

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


class TestLoadSideFromFile(unittest.TestCase):
    def test_loads_name_and_data(self):
        side = _side(OLD_LIST)
        self.assertEqual(side.name, "Example List 1.0")
        self.assertFalse(side.live)
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

    def test_coverage_reads_ignore_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = os.path.join(tmp, "Example List 1.0")
            os.makedirs(target_dir)
            with open(os.path.join(target_dir, ".coverage-ignore.txt"), "w",
                      encoding="utf-8") as f:
                f.write("Sky Idles\n")
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST), ["coverage"], tmp,
                save_exports=False,
            )
            self.assertEqual(result.errors, [])
            with open(result.written[0], encoding="utf-8") as f:
                html = f.read()
        self.assertIn("mod-ignored", html)

    def test_saves_live_export(self):
        live = _side(NEW_LIST)
        live.live = True
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                live, _side(OLD_LIST), ["changelog"], tmp, save_exports=True,
            )
            saved = os.path.join(tmp, "Example List 1.1.json")
            self.assertIn(saved, result.written)
            round_trip = report_runner.load_side_from_file(saved)
        self.assertEqual(round_trip.data, live.data)

    def test_generator_failure_is_collected_not_fatal(self):
        # An unknown report type forces one failure alongside one success.
        with tempfile.TemporaryDirectory() as tmp:
            result = report_runner.run_reports(
                _side(NEW_LIST), _side(OLD_LIST), ["diff", "nonsense"], tmp,
                save_exports=False,
            )
        self.assertEqual(len(result.written), 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("nonsense", result.errors[0])


if __name__ == "__main__":
    unittest.main()
