#!/usr/bin/env python3
"""Regenerate every report that already exists under ``output/<list name>/``.

The output naming convention (see ``modlist_utils.resolve_output_path``) is
``output/<folder = 2nd list>/<file = 1st list>.<type>.<ext>``. That fully
encodes how each report was produced, so regenerating is just: scan the folder,
parse each filename back into generator arguments, and re-run the matching
generator with ``-o <output>/`` (which reproduces the exact same path).

The scope is **everything related** to the named list: reports where it is the
target (its own ``output/<list name>/`` folder) *and* reports in other folders
where it is the source or the base of a rebase.

Usage::

    python tools/regenerate.py "Example List 1.1"              # regenerate its related reports
    python tools/regenerate.py "Example List 1.1" --dry-run    # preview the plan
    python tools/regenerate.py                                # list available folders
"""

import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List

# report type -> (generator script, expected file extension)
TYPE_SPECS = {
    "coverage": ("generate_coverage.py", "html"),
    "diff": ("generate_diff.py", "html"),
    "changelog": ("generate_changelog.py", "md"),
    "rebase": ("generate_coverage.py", "html"),
}

# Rebase report stems decorate the source with the base list:
# "<source> (from <base>)". The rightmost " (from " anchors the split so a
# source name that itself contains the marker still parses.
REBASE_STEM_RE = re.compile(r"^(?P<source>.+) \(from (?P<base>.+)\)$")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class Job:
    """A single report to regenerate, with its resolved generator arguments."""

    report_type: str
    script: str
    source_list: str
    target_list: str
    source_path: str
    target_path: str
    output_path: str
    base_list: str = ""
    base_path: str = ""


@dataclass
class Plan:
    jobs: List[Job] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _parse_report(entry, folder_path, lists_dir):
    """Parse one report file ``entry`` living in ``folder_path`` into a :class:`Job`.

    The folder name is the report's target list; the filename encodes the source
    (and, for ``rebase`` reports, the base) per the naming convention. Returns a
    ``(job, warning)`` pair with exactly one side set: a ready :class:`Job`, or a
    warning string describing why the file was skipped (unrecognized name,
    unknown type, mismatched extension, malformed rebase stem, or a missing
    source/base list JSON).

    The **target** list JSON is *not* verified here — callers decide whether a
    missing target is a hard error (the list's own folder) or a skip (a sibling
    folder scanned only because it references the subject list).
    """
    target_list = os.path.basename(folder_path.rstrip("\\/"))
    target_path = os.path.join(lists_dir, f"{target_list}.json")
    output_path = os.path.join(folder_path, entry)

    stem, ext = os.path.splitext(entry)
    ext = ext.lstrip(".").lower()
    if "." not in stem:
        return None, f"Skipping '{entry}': unrecognized report name"

    # Parse right-to-left so dots in the list name (e.g. "Companion List 2.0.1")
    # stay with the source list, not the type segment.
    source_list, type_label = stem.rsplit(".", 1)
    type_label = type_label.lower()

    spec = TYPE_SPECS.get(type_label)
    if spec is None:
        return None, f"Skipping '{entry}': unknown report type '{type_label}'"

    script, expected_ext = spec
    if ext != expected_ext:
        return None, (
            f"Skipping '{entry}': '{type_label}' expects .{expected_ext}, "
            f"found .{ext}"
        )

    base_list = ""
    base_path = ""
    if type_label == "rebase":
        m = REBASE_STEM_RE.match(source_list)
        if not m:
            return None, (
                f"Skipping '{entry}': rebase name must look like "
                f"'<source> (from <base>)'"
            )
        source_list = m.group("source")
        base_list = m.group("base")
        base_path = os.path.join(lists_dir, f"{base_list}.json")
        if not os.path.isfile(base_path):
            return None, f"Skipping '{entry}': base list not found ({base_path})"

    source_path = os.path.join(lists_dir, f"{source_list}.json")
    if not os.path.isfile(source_path):
        return None, f"Skipping '{entry}': source list not found ({source_path})"

    return (
        Job(
            report_type=type_label,
            script=script,
            source_list=source_list,
            target_list=target_list,
            source_path=source_path,
            target_path=target_path,
            output_path=output_path,
            base_list=base_list,
            base_path=base_path,
        ),
        None,
    )


def available_folders(output_root):
    """Sorted names of the report folders directly under ``output_root``."""
    if not os.path.isdir(output_root):
        return []
    return sorted(
        name
        for name in os.listdir(output_root)
        if os.path.isdir(os.path.join(output_root, name))
    )


def plan_related(output_root, list_name, lists_dir):
    """Build the plan for every report *related* to ``list_name``.

    A report is related when ``list_name`` is any of its input lists:

    * **target** — reports in its own ``output/<list_name>/`` folder;
    * **source** — reports in *other* folders whose 1st-position list is
      ``list_name``;
    * **base** — ``rebase`` reports in other folders whose base list is
      ``list_name``.

    Raises ``FileNotFoundError`` when ``list_name``'s own list JSON is missing —
    it is required as the source for its source-side reports and as the target
    for its own folder. A sibling report that references ``list_name`` but whose
    folder has no target-list JSON is skipped with a warning; unrelated or
    unparsable files in sibling folders are ignored silently.
    """
    target_path = os.path.join(lists_dir, f"{list_name}.json")
    if not os.path.isfile(target_path):
        raise FileNotFoundError(f"Target list JSON not found: {target_path}")

    plan = Plan()
    for folder_name in available_folders(output_root):
        folder = os.path.join(output_root, folder_name)
        own_folder = folder_name == list_name
        for entry in sorted(os.listdir(folder)):
            if not os.path.isfile(os.path.join(folder, entry)):
                continue
            job, warning = _parse_report(entry, folder, lists_dir)

            if own_folder:
                # Every report here targets list_name — keep them all, along
                # with any skip warnings.
                if warning:
                    plan.warnings.append(warning)
                else:
                    plan.jobs.append(job)
                continue

            # Sibling folder: keep only reports that actually reference list_name
            # (as source or rebase base). Files that don't parse, or parse to some
            # other combination, are none of this run's business.
            if job is None or list_name not in (job.source_list, job.base_list):
                continue
            if not os.path.isfile(job.target_path):
                plan.warnings.append(
                    f"Skipping '{entry}' in '{folder_name}/': "
                    f"target list not found ({job.target_path})"
                )
                continue
            plan.jobs.append(job)

    return plan


def build_cmd(job, output_root):
    """The generator command for a job. A trailing separator on -o guarantees
    resolve_output_path treats it as a directory and reproduces
    <output_root>/<target>/<file>.<type>.<ext>."""
    out_arg = os.path.join(output_root, "")
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, job.script),
        job.source_path,
        job.target_path,
        "-o",
        out_arg,
    ]
    if job.base_path:
        cmd += ["--base", job.base_path]
    return cmd


def run_job(job, output_root):
    """Run one generator via subprocess; return the CompletedProcess."""
    return subprocess.run(build_cmd(job, output_root), capture_output=True, text=True)


def job_display(job):
    """Progress-line label: rebase jobs show their base list too."""
    if job.base_list:
        return f"{job.source_list} (from {job.base_list})"
    return job.source_list


def progress_label(job, subject_list):
    """Progress-line label for a job during a run.

    In a related run (the default), a job whose target differs from the subject
    list is shown as ``<source>  ->  <target>`` so the direction is unmistakable;
    an own-folder job (target == subject) shows just the source, as before.
    """
    label = job_display(job)
    if job.target_list != subject_list:
        label += f"  ->  {job.target_list}"
    return label


def default_max_workers(job_count):
    """Concurrency cap when ``--jobs`` isn't given: one worker per report, but
    never more than the CPU count (each generator is CPU-bound), and at least 1
    so the pool is always valid even with zero jobs."""
    return max(1, min(job_count, os.cpu_count() or 1))


def run_jobs(jobs, output_root, max_workers, runner=run_job):
    """Run ``jobs`` concurrently, at most ``max_workers`` at a time.

    Each job is dispatched to ``runner(job, output_root)`` in a thread pool. The
    pool is a rolling queue — the moment a worker finishes it picks up the next
    waiting job, so concurrency stays at the cap until the work runs dry rather
    than draining in fixed batches. Threads (not processes) are correct here
    because the real work happens in ``runner``'s child subprocess; each thread
    only blocks waiting on it.

    Yields ``(job, result)`` pairs in completion order, so callers can report
    progress live as each report finishes.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(runner, job, output_root): job for job in jobs}
        for future in concurrent.futures.as_completed(futures):
            yield futures[future], future.result()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Regenerate every existing report related to a list: its own "
        "output/<list name>/ folder, plus reports in other folders where it is the "
        "source or rebase base."
    )
    parser.add_argument(
        "list_name",
        nargs="?",
        help="List whose reports to regenerate (the output/<list name>/ folder). "
        "Omit to list available folders.",
    )
    parser.add_argument(
        "--lists", default="lists", help="Lists directory (default: lists)."
    )
    parser.add_argument(
        "--output", default="output", help="Output directory (default: output)."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the plan; run nothing."
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=0,
        metavar="N",
        help="Max reports to run at once (default: min(report count, CPU count); "
        "pass 1 to run sequentially).",
    )
    args = parser.parse_args(argv)

    if not args.list_name:
        folders = available_folders(args.output)
        if folders:
            print("Available report folders (pass one as the list name):")
            for name in folders:
                print(f"  {name}")
        else:
            print(f"No report folders found under {args.output}/")
        return 0

    try:
        plan = plan_related(args.output, args.list_name, args.lists)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    for warning in plan.warnings:
        print(f"  ! {warning}")

    if not plan.jobs:
        print(f"Nothing to regenerate for '{args.list_name}'.")
        return 0

    if args.dry_run:
        print(f"Would regenerate {len(plan.jobs)} report(s) for '{args.list_name}':")
        for job in plan.jobs:
            print(f"  {job.report_type:9} {job_display(job)}  ->  {job.output_path}")
        return 0

    workers = args.jobs if args.jobs > 0 else default_max_workers(len(plan.jobs))
    workers = min(workers, len(plan.jobs))
    suffix = "" if workers == 1 else f", up to {workers} at a time"
    print(
        f"Regenerating {len(plan.jobs)} report(s) for '{args.list_name}'{suffix}:"
    )
    failures = 0
    # Completion order, so lines appear as each report finishes (not in plan order).
    for job, result in run_jobs(plan.jobs, args.output, workers):
        if result.returncode == 0:
            print(f"  + {job.report_type:9} {progress_label(job, args.list_name)}")
        else:
            failures += 1
            print(
                f"  x {job.report_type:9} {progress_label(job, args.list_name)}  (exit {result.returncode})",
                file=sys.stderr,
            )
            if result.stderr:
                print(result.stderr.strip(), file=sys.stderr)

    if failures:
        print(f"{failures} of {len(plan.jobs)} report(s) failed.", file=sys.stderr)
        return 1
    print(f"Done: {len(plan.jobs)} report(s) regenerated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
