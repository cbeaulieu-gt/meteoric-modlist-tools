"""Report pipeline for the Generate Reports dialog. No Qt, no mobase.

Resolves nothing itself: callers hand in two ListSide objects (already loaded)
plus options; this module runs the vendored generators and writes files using
the same naming convention as the CLI tools.
"""
import json
import os
from dataclasses import dataclass, field

from ._vendor import (
    coverage_ignore,
    generate_changelog,
    generate_coverage,
    generate_diff,
    modlist_utils,
)

REPORT_TYPES = ("coverage", "diff", "changelog")
_EXTENSIONS = {"coverage": "html", "diff": "html", "changelog": "md"}


class Cancelled(Exception):
    """Raised by a progress callback to abort generation at a checkpoint."""


@dataclass
class ListSide:
    """One side of a comparison: a display name plus loaded modlist data."""
    name: str
    data: list
    live: bool = False


@dataclass
class RunResult:
    written: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    cancelled: bool = False


def load_side_from_file(path):
    """Load an exported modlist JSON into a ListSide (name = filename stem)."""
    data = modlist_utils.load_modlist(path)
    if not isinstance(data, list):
        raise ValueError("not a modlist export (expected a JSON array)")
    name = os.path.splitext(os.path.basename(path))[0]
    return ListSide(name=name, data=data, live=False)


def run_reports(list1, list2, report_types, dest_dir, save_exports=True,
                min_confidence=0.80, progress=None):
    """Generate the selected reports from two sides into dest_dir.

    Naming matches the CLI: <dest>/<list2.name>/<list1.name>.<type>.<ext>.
    Coverage reads <dest>/<list2.name>/.coverage-ignore.txt like a static run.
    Per-report failures land in RunResult.errors; the rest still run.

    progress, when given, is called as progress(fraction, message): fraction
    spans 0.0-1.0 across all selected reports (equal slice per report, since
    each reruns the same matching), message reads "Generating <type>… (i of n)".
    A callback that raises Cancelled aborts the run: the in-progress report
    writes nothing, earlier reports stay, save_exports is skipped, and the
    returned RunResult has cancelled=True.
    """
    result = RunResult()
    # resolve_output_path derives names from paths; hand it synthetic filenames
    # so plugin and CLI naming can never drift.
    first = list1.name + ".json"
    second = list2.name + ".json"
    dest = dest_dir if dest_dir.endswith(("/", "\\")) else dest_dir + os.sep
    count = len(report_types)

    for i, rtype in enumerate(report_types):
        message = f"Generating {rtype}… ({i + 1} of {count})"

        def sub_progress(done, total, _i=i, _message=message):
            if progress is not None and total:
                progress((_i + done / total) / count, _message)

        try:
            # Inside the try: this checkpoint is also a cancellation point.
            if progress is not None:
                progress(i / count, message)
            if rtype == "coverage":
                ignore = coverage_ignore.load_ignore(
                    coverage_ignore.resolve_ignore_path(dest, second)
                )
                text = generate_coverage.generate(
                    list1.data, list2.data, list1.name, list2.name,
                    min_confidence=min_confidence, ignore=ignore,
                    progress=sub_progress,
                )
            elif rtype == "diff":
                text = generate_diff.generate(
                    list1.data, list2.data, list1.name, list2.name,
                    min_confidence=min_confidence, progress=sub_progress,
                )
            elif rtype == "changelog":
                text = generate_changelog.generate(
                    list1.data, list2.data, min_confidence=min_confidence,
                    progress=sub_progress,
                )
            else:
                raise ValueError(f"unknown report type: {rtype}")
            out_path = modlist_utils.resolve_output_path(
                dest, first, second, rtype, _EXTENSIONS[rtype]
            )
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            result.written.append(out_path)
        except Cancelled:
            result.cancelled = True
            break
        except Exception as e:
            result.errors.append(f"{rtype}: {e}")

    if save_exports and not result.cancelled:
        for side in (list1, list2):
            if not side.live:
                continue
            try:
                # Only resolve_output_path creates dest_dir, and it may not have
                # run (no reports selected, or every one failed).
                os.makedirs(dest_dir, exist_ok=True)
                path = os.path.join(dest_dir, side.name + ".json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(side.data, f, indent=2, ensure_ascii=False)
                result.written.append(path)
            except Exception as e:
                result.errors.append(f"export {side.name}: {e}")
    return result
