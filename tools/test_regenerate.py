"""Tests for regenerate job planning (pure, no generation)."""

import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from regenerate import (
    plan_related,
    available_folders,
    run_jobs,
    default_max_workers,
    build_cmd,
    job_display,
    progress_label,
    Job,
)


def touch(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def make_job(source_list, report_type="coverage"):
    """A minimal Job for exercising run_jobs (paths are never opened)."""
    return Job(
        report_type=report_type,
        script="generate_coverage.py",
        source_list=source_list,
        target_list="Example List 1.1",
        source_path="src.json",
        target_path="tgt.json",
        output_path=f"out/{source_list}.{report_type}.html",
    )


class FakeResult:
    """Stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


class OwnFolderPlanTest(unittest.TestCase):
    """plan_related's handling of the list's own folder (where it is the target)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.lists = os.path.join(self.root, "lists")
        self.output = os.path.join(self.root, "output")
        os.makedirs(self.lists)
        os.makedirs(self.output)

    def tearDown(self):
        self._tmp.cleanup()

    def _list(self, name):
        touch(os.path.join(self.lists, f"{name}.json"), "[]")

    def _report(self, folder, filename):
        touch(os.path.join(self.output, folder, filename), "<html>")

    def test_plans_coverage_and_diff_jobs(self):
        self._list("Example List 1.1")
        self._list("Companion List 2.0.1")
        self._report("Example List 1.1", "Companion List 2.0.1.coverage.html")
        self._report("Example List 1.1", "Companion List 2.0.1.diff.html")

        plan = plan_related(self.output, "Example List 1.1", self.lists)

        self.assertEqual(plan.warnings, [])
        self.assertEqual(len(plan.jobs), 2)
        by_type = {j.report_type: j for j in plan.jobs}

        cov = by_type["coverage"]
        self.assertEqual(cov.script, "generate_coverage.py")
        self.assertEqual(cov.source_list, "Companion List 2.0.1")
        self.assertEqual(cov.target_list, "Example List 1.1")
        self.assertEqual(
            cov.source_path, os.path.join(self.lists, "Companion List 2.0.1.json")
        )
        self.assertEqual(
            cov.target_path, os.path.join(self.lists, "Example List 1.1.json")
        )
        self.assertEqual(
            cov.output_path,
            os.path.join(self.output, "Example List 1.1", "Companion List 2.0.1.coverage.html"),
        )

        self.assertEqual(by_type["diff"].script, "generate_diff.py")

    def test_changelog_uses_md_and_changelog_script(self):
        self._list("Example List 1.1")
        self._list("Companion List 2.0.1")
        self._report("Example List 1.1", "Companion List 2.0.1.changelog.md")

        plan = plan_related(self.output, "Example List 1.1", self.lists)

        self.assertEqual(plan.warnings, [])
        self.assertEqual(len(plan.jobs), 1)
        self.assertEqual(plan.jobs[0].report_type, "changelog")
        self.assertEqual(plan.jobs[0].script, "generate_changelog.py")

    def test_source_name_with_dots_parsed_right_to_left(self):
        self._list("Example List 1.1")
        self._list("Other List 2.0.1 - PBR Edition 1.4.0")
        self._report(
            "Example List 1.1",
            "Other List 2.0.1 - PBR Edition 1.4.0.coverage.html",
        )

        plan = plan_related(self.output, "Example List 1.1", self.lists)

        self.assertEqual(len(plan.jobs), 1)
        self.assertEqual(
            plan.jobs[0].source_list, "Other List 2.0.1 - PBR Edition 1.4.0"
        )
        self.assertEqual(plan.jobs[0].report_type, "coverage")

    def test_unrecognized_file_skipped_with_warning(self):
        self._list("Example List 1.1")
        self._report("Example List 1.1", "notes.txt")

        plan = plan_related(self.output, "Example List 1.1", self.lists)

        self.assertEqual(plan.jobs, [])
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("notes.txt", plan.warnings[0])

    def test_mismatched_extension_skipped_with_warning(self):
        self._list("Example List 1.1")
        self._list("Companion List 2.0.1")
        self._report("Example List 1.1", "Companion List 2.0.1.coverage.md")

        plan = plan_related(self.output, "Example List 1.1", self.lists)

        self.assertEqual(plan.jobs, [])
        self.assertEqual(len(plan.warnings), 1)

    def test_missing_source_list_skipped_with_warning(self):
        self._list("Example List 1.1")
        # source list intentionally NOT created
        self._report("Example List 1.1", "Companion List 2.0.1.coverage.html")

        plan = plan_related(self.output, "Example List 1.1", self.lists)

        self.assertEqual(plan.jobs, [])
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("Companion List 2.0.1", plan.warnings[0])

    def test_missing_target_list_is_hard_error(self):
        # target list JSON absent; only a report folder exists
        self._report("Example List 1.1", "Companion List 2.0.1.coverage.html")

        with self.assertRaises(FileNotFoundError):
            plan_related(self.output, "Example List 1.1", self.lists)

    def test_no_related_reports_returns_empty_plan_without_warning(self):
        # Target JSON exists but nothing references it (no own folder, no sibling
        # reports). A related run simply finds nothing — no spurious warning.
        self._list("Example List 1.1")

        plan = plan_related(self.output, "Example List 1.1", self.lists)

        self.assertEqual(plan.jobs, [])
        self.assertEqual(plan.warnings, [])

    def test_jobs_sorted_by_report_filename(self):
        self._list("Example List 1.1")
        self._list("AAA")
        self._list("ZZZ")
        self._report("Example List 1.1", "ZZZ.coverage.html")
        self._report("Example List 1.1", "AAA.coverage.html")

        plan = plan_related(self.output, "Example List 1.1", self.lists)

        self.assertEqual([j.source_list for j in plan.jobs], ["AAA", "ZZZ"])


class AvailableFoldersTest(unittest.TestCase):
    def test_lists_subdirectories_sorted(self):
        with tempfile.TemporaryDirectory() as root:
            output = os.path.join(root, "output")
            os.makedirs(os.path.join(output, "Example List 1.1"))
            os.makedirs(os.path.join(output, "Example List 1.0"))
            touch(os.path.join(output, "readme.txt"))  # stray file ignored

            self.assertEqual(
                available_folders(output), ["Example List 1.0", "Example List 1.1"]
            )

    def test_missing_output_root_returns_empty(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(available_folders(os.path.join(root, "nope")), [])


class RunJobsTest(unittest.TestCase):
    def test_runs_every_job_exactly_once(self):
        jobs = [make_job(f"mod {i}") for i in range(5)]
        seen = []
        lock = threading.Lock()

        def runner(job, output_root):
            with lock:
                seen.append(job.source_list)
            return FakeResult()

        results = list(run_jobs(jobs, "output", max_workers=3, runner=runner))

        self.assertEqual(len(results), 5)
        self.assertEqual(sorted(seen), sorted(j.source_list for j in jobs))

    def test_yields_each_job_paired_with_its_result(self):
        jobs = [make_job("alpha"), make_job("beta")]

        def runner(job, output_root):
            return FakeResult(returncode=1 if job.source_list == "beta" else 0)

        results = {job.source_list: res for job, res in run_jobs(jobs, "o", 2, runner)}

        self.assertEqual(results["alpha"].returncode, 0)
        self.assertEqual(results["beta"].returncode, 1)

    def test_reaches_the_cap_concurrently(self):
        # 6 jobs, cap 3 -> two clean batches of 3 must rendezvous at the barrier.
        # If concurrency were held below the cap, the barrier never fills and
        # wait() times out (BrokenBarrierError), surfacing as a test failure.
        cap = 3
        jobs = [make_job(f"mod {i}") for i in range(6)]
        barrier = threading.Barrier(cap, timeout=5)
        active = 0
        peak = 0
        lock = threading.Lock()

        def runner(job, output_root):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait()  # blocks until `cap` runners are here together
            with lock:
                active -= 1
            return FakeResult()

        list(run_jobs(jobs, "output", max_workers=cap, runner=runner))

        self.assertEqual(peak, cap)

    def test_never_exceeds_the_cap(self):
        cap = 2
        jobs = [make_job(f"mod {i}") for i in range(8)]
        active = 0
        peak = 0
        lock = threading.Lock()

        def runner(job, output_root):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return FakeResult()

        list(run_jobs(jobs, "output", max_workers=cap, runner=runner))

        self.assertLessEqual(peak, cap)


class DefaultMaxWorkersTest(unittest.TestCase):
    def test_capped_by_job_count_when_fewer_than_cpus(self):
        self.assertEqual(default_max_workers(1), 1)

    def test_at_least_one_for_zero_jobs(self):
        self.assertEqual(default_max_workers(0), 1)

    def test_capped_by_cpu_count(self):
        cpu = os.cpu_count() or 1
        self.assertEqual(default_max_workers(10_000), cpu)


class RebasePlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.lists = os.path.join(self.root, "lists")
        self.output = os.path.join(self.root, "output")
        os.makedirs(self.lists)
        os.makedirs(self.output)

    def tearDown(self):
        self._tmp.cleanup()

    def _list(self, name):
        touch(os.path.join(self.lists, f"{name}.json"), "[]")

    def _report(self, folder, filename):
        touch(os.path.join(self.output, folder, filename), "<html>")

    def test_plans_rebase_job(self):
        self._list("PBR 1.5.0")
        self._list("NS 3.1.1")
        self._list("NS 3.0.1")
        self._report("PBR 1.5.0", "NS 3.1.1 (from NS 3.0.1).rebase.html")

        plan = plan_related(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(plan.warnings, [])
        self.assertEqual(len(plan.jobs), 1)
        job = plan.jobs[0]
        self.assertEqual(job.report_type, "rebase")
        self.assertEqual(job.script, "generate_coverage.py")
        self.assertEqual(job.source_list, "NS 3.1.1")
        self.assertEqual(job.base_list, "NS 3.0.1")
        self.assertEqual(job.source_path, os.path.join(self.lists, "NS 3.1.1.json"))
        self.assertEqual(job.base_path, os.path.join(self.lists, "NS 3.0.1.json"))

    def test_rebase_missing_base_warns_and_skips(self):
        self._list("PBR 1.5.0")
        self._list("NS 3.1.1")
        # base list NS 3.0.1 intentionally NOT created
        self._report("PBR 1.5.0", "NS 3.1.1 (from NS 3.0.1).rebase.html")

        plan = plan_related(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(plan.jobs, [])
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("NS 3.0.1", plan.warnings[0])

    def test_rebase_malformed_stem_warns_and_skips(self):
        self._list("PBR 1.5.0")
        self._report("PBR 1.5.0", "JustAName.rebase.html")

        plan = plan_related(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(plan.jobs, [])
        self.assertEqual(len(plan.warnings), 1)

    def test_parenthetical_source_names_parse_rightmost_from(self):
        # A source list whose own name contains " (from " must not confuse the
        # parse; the rightmost ' (from ' anchors the base.
        self._list("PBR 1.5.0")
        self._list("Weird (from scratch)")
        self._list("NS 3.0.1")
        self._report(
            "PBR 1.5.0", "Weird (from scratch) (from NS 3.0.1).rebase.html"
        )

        plan = plan_related(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(len(plan.jobs), 1)
        self.assertEqual(plan.jobs[0].source_list, "Weird (from scratch)")
        self.assertEqual(plan.jobs[0].base_list, "NS 3.0.1")


class BuildCmdTest(unittest.TestCase):
    def test_plain_job_has_no_base_flag(self):
        cmd = build_cmd(make_job("Companion List 2.0.1"), "output")
        self.assertNotIn("--base", cmd)

    def test_rebase_job_appends_base(self):
        job = make_job("NS 3.1.1", report_type="rebase")
        job.base_list = "NS 3.0.1"
        job.base_path = "lists/NS 3.0.1.json"
        cmd = build_cmd(job, "output")
        self.assertEqual(cmd[-2:], ["--base", "lists/NS 3.0.1.json"])
        self.assertIn("-o", cmd)


class JobDisplayTest(unittest.TestCase):
    def test_plain_job_shows_source(self):
        self.assertEqual(job_display(make_job("Companion List 2.0.1")), "Companion List 2.0.1")

    def test_rebase_job_shows_from_base(self):
        job = make_job("NS 3.1.1", report_type="rebase")
        job.base_list = "NS 3.0.1"
        self.assertEqual(job_display(job), "NS 3.1.1 (from NS 3.0.1)")


class PlanRelatedTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.lists = os.path.join(self.root, "lists")
        self.output = os.path.join(self.root, "output")
        os.makedirs(self.lists)
        os.makedirs(self.output)

    def tearDown(self):
        self._tmp.cleanup()

    def _list(self, name):
        touch(os.path.join(self.lists, f"{name}.json"), "[]")

    def _report(self, folder, filename):
        touch(os.path.join(self.output, folder, filename), "<html>")

    def _outputs(self, plan):
        return sorted(
            os.path.relpath(j.output_path, self.output).replace(os.sep, "/")
            for j in plan.jobs
        )

    def test_includes_own_folder_and_source_side_reports(self):
        self._list("PBR 1.5.0")
        self._list("Example List 1.1")
        self._list("NS 3.1.1")
        # own folder: L is the target
        self._report("PBR 1.5.0", "NS 3.1.1.coverage.html")
        # sibling folder: L is the source
        self._report("Example List 1.1", "PBR 1.5.0.coverage.html")
        self._report("Example List 1.1", "PBR 1.5.0.diff.html")
        # sibling folder: unrelated report (must be excluded)
        self._report("Example List 1.1", "NS 3.1.1.coverage.html")

        plan = plan_related(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(plan.warnings, [])
        self.assertEqual(
            self._outputs(plan),
            [
                "Example List 1.1/PBR 1.5.0.coverage.html",
                "Example List 1.1/PBR 1.5.0.diff.html",
                "PBR 1.5.0/NS 3.1.1.coverage.html",
            ],
        )

    def test_includes_sibling_rebase_where_list_is_base(self):
        self._list("NS 3.0.1")
        self._list("PBR 1.5.0")
        self._list("NS 3.1.1")
        self._report("PBR 1.5.0", "NS 3.1.1 (from NS 3.0.1).rebase.html")

        plan = plan_related(self.output, "NS 3.0.1", self.lists)

        self.assertEqual(plan.warnings, [])
        self.assertEqual(len(plan.jobs), 1)
        job = plan.jobs[0]
        self.assertEqual(job.report_type, "rebase")
        self.assertEqual(job.base_list, "NS 3.0.1")
        self.assertEqual(job.source_list, "NS 3.1.1")
        self.assertEqual(job.target_list, "PBR 1.5.0")

    def test_sibling_missing_target_json_warns_and_skips(self):
        self._list("PBR 1.5.0")
        # Example List 1.1 JSON intentionally absent
        self._report("Example List 1.1", "PBR 1.5.0.coverage.html")

        plan = plan_related(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(plan.jobs, [])
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("Example List 1.1", plan.warnings[0])

    def test_unparsable_sibling_file_ignored_silently(self):
        self._list("PBR 1.5.0")
        self._list("Example List 1.1")
        self._report("Example List 1.1", "notes.txt")  # junk in a sibling folder
        self._report("Example List 1.1", "PBR 1.5.0.coverage.html")

        plan = plan_related(self.output, "PBR 1.5.0", self.lists)

        self.assertEqual(plan.warnings, [])
        self.assertEqual(len(plan.jobs), 1)

    def test_missing_own_list_json_is_hard_error(self):
        # references PBR as source, but PBR's own JSON is absent
        self._report("Example List 1.1", "PBR 1.5.0.coverage.html")
        with self.assertRaises(FileNotFoundError):
            plan_related(self.output, "PBR 1.5.0", self.lists)


class ProgressLabelTest(unittest.TestCase):
    def test_own_folder_job_shows_source_only(self):
        job = make_job("Companion List 2.0.1")  # target_list == "Example List 1.1"
        self.assertEqual(progress_label(job, "Example List 1.1"), "Companion List 2.0.1")

    def test_cross_folder_job_shows_target(self):
        job = make_job("PBR 1.5.0")  # target_list == "Example List 1.1"
        self.assertEqual(
            progress_label(job, "PBR 1.5.0"), "PBR 1.5.0  ->  Example List 1.1"
        )


if __name__ == "__main__":
    unittest.main()
