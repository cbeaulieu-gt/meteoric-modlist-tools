#!/usr/bin/env python3
r"""Generate the per-release reports for a modlist repo and stub its CHANGELOG entry.

Finds the two newest versioned exports in ``lists/`` (version = the trailing
``1.6.0``-style token before ``.json``; the rest of the name is ignored), writes
``changelog/v<ver>/{changelog.md,diff.html,coverage.html}`` under the repo root,
and inserts a ``## Version <ver>`` skeleton into ``CHANGELOG.md`` with TODO
markers for the human-written parts. Idempotent: an existing ``changelog/v<ver>/``
means nothing to do unless ``--force``; an existing ``## Version <ver>`` section is
never rewritten.

Usage::

    python tools/release_reports.py --lists lists --repo . \
        --pages-url https://<user>.github.io/<repo>/

The composite GitHub Action at the repo root wraps this script.
"""

import argparse
import os
import re
import sys

import generate_changelog
import generate_coverage
import generate_diff
from modlist_utils import load_modlist

VERSION_RE = re.compile(r"v?(\d+(?:\.\d+)*)$")


def parse_version(filename):
    """Return ``(int_tuple, label)`` for a ``*.json`` list filename, or None.

    The version is the trailing ``v?N(.N)*`` token immediately before the
    extension. Earlier tokens (``NORDIC SOULS v3.2.0 - PBR Edition 1.6.0``)
    are ignored — the base name may change between releases.
    """
    stem, ext = os.path.splitext(os.path.basename(filename))
    if ext.lower() != ".json":
        return None
    match = VERSION_RE.search(stem)
    if not match:
        return None
    label = match.group(1)
    return tuple(int(part) for part in label.split(".")), label


def find_pair(lists_dir):
    """Return ``(old_path, new_path, new_label)`` for the two newest versioned
    lists in ``lists_dir``, or None when there are fewer than two."""
    versioned = []
    for name in sorted(os.listdir(lists_dir)):
        parsed = parse_version(name)
        if parsed is None:
            if name.lower().endswith(".json"):
                print(f"Ignoring {name}: no trailing version token")
            continue
        versioned.append((parsed[0], parsed[1], os.path.join(lists_dir, name)))
    if len(versioned) < 2:
        return None
    versioned.sort()
    (_, _, old_path), (_, new_label, new_path) = versioned[-2], versioned[-1]
    return old_path, new_path, new_label


REPORT_NAMES = ("changelog.md", "diff.html", "coverage.html")


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def generate_reports(old_path, new_path, out_dir, min_confidence=0.80):
    """Write changelog.md, diff.html and coverage.html for old -> new into
    ``out_dir`` and return ``{filename: text}``.

    Coverage runs with the old list as source and the new as target: what the
    new release dropped or is behind on relative to the previous one.
    """
    old_data, new_data = load_modlist(old_path), load_modlist(new_path)
    old_name, new_name = _stem(old_path), _stem(new_path)
    texts = {
        "changelog.md": generate_changelog.generate(
            old_data, new_data, min_confidence=min_confidence),
        "diff.html": generate_diff.generate(
            old_data, new_data, old_name, new_name, min_confidence=min_confidence),
        "coverage.html": generate_coverage.generate(
            old_data, new_data, old_name, new_name, min_confidence=min_confidence),
    }
    os.makedirs(out_dir, exist_ok=True)
    for name in REPORT_NAMES:
        _write(os.path.join(out_dir, name), texts[name])
    return texts


COUNTS_RE = re.compile(r"\*\*(Added|Removed|Updated):\*\* (\d+) mods")
HEADING_RE = re.compile(r"^## ")


def parse_counts(changelog_text):
    """Return ``{"Added": n, "Removed": n, "Updated": n}`` from a generated
    changelog.md; ValueError if any is missing."""
    counts = {kind: int(n) for kind, n in COUNTS_RE.findall(changelog_text)}
    missing = [k for k in ("Added", "Removed", "Updated") if k not in counts]
    if missing:
        raise ValueError(f"changelog summary is missing counts for: {', '.join(missing)}")
    return counts


def anchor(version):
    """GitHub heading anchor for ``## Version <version>``: dots dropped."""
    return "version-" + version.replace(".", "")


def render_entry(version, counts, pages_url, has_loadorder):
    """Render the ``## Version <version>`` skeleton for CHANGELOG.md.

    ``.md`` and folder links are repo-relative; ``.html`` links go through
    ``pages_url`` (GitHub doesn't render HTML in the repo browser) unless it
    is empty, in which case they are relative too.
    """
    base = pages_url.rstrip("/") + "/" if pages_url else ""
    folder = f"changelog/v{version}"
    lines = [
        f"## Version {version}",
        "",
        "**This update is <!-- TODO: save-safe / probably not save-safe / not save-safe -->.**",
        "",
        "<!-- TODO: write highlights (### Category / - bullet sections) -->",
        "",
        "### Summary",
        f"- **Added:** {counts['Added']} mods",
        f"- **Removed:** {counts['Removed']} mods",
        f"- **Updated:** {counts['Updated']} mods",
        "",
        "### Detailed Reports",
        f"- [Full changelog]({folder}/changelog.md) — complete added/removed/updated mod lists",
        f"- [Diff report]({base}{folder}/diff.html) — full modlist diff",
        f"- [Coverage report]({base}{folder}/coverage.html) — coverage details",
    ]
    if has_loadorder:
        lines.append(
            f"- [Load order](loadorder/v{version}/) — load order, modlist, "
            "plugin groups, and plugins files")
    return "\n".join(lines) + "\n"


def insert_entry(text, version, entry):
    """Return ``text`` with a Contents line and ``entry`` inserted for
    ``version``, or None if ``## Version <version>`` is already present.

    The Contents line becomes the first item of the ``## Contents`` list; the
    entry goes right after that list, before the previous newest section. A
    file without ``## Contents`` (or empty) gets one prepended.
    """
    if re.search(rf"^## Version {re.escape(version)}\s*$", text, re.MULTILINE):
        return None
    contents_line = f"- [Version {version}](#{anchor(version)})"
    block = entry.rstrip("\n").split("\n")
    lines = text.split("\n") if text else []
    if lines and lines[-1] == "":
        lines.pop()  # trailing newline is re-added on join

    heading = next((i for i, l in enumerate(lines) if l.rstrip() == "## Contents"), None)
    if heading is None:
        head = ["## Contents", "", contents_line, "", *block]
        return "\n".join(head + ([""] + lines if lines else [])) + "\n"

    # First list item inside the Contents section, else insert one.
    i = heading + 1
    while i < len(lines) and not lines[i].startswith("- ") and not HEADING_RE.match(lines[i]):
        i += 1
    if i < len(lines) and lines[i].startswith("- "):
        lines.insert(i, contents_line)
    else:
        lines[heading + 1:heading + 1] = ["", contents_line]
        i = heading + 2

    # Entry goes before the next "## " heading after the list, or at the end.
    j = i + 1
    while j < len(lines) and not HEADING_RE.match(lines[j]):
        j += 1
    insert = block + [""] if j < len(lines) else block
    if j > 0 and lines[j - 1] != "":
        insert = [""] + insert
    lines[j:j] = insert
    return "\n".join(lines) + "\n"


def write_github_output(version):
    """Append ``version=<version>`` to $GITHUB_OUTPUT when running in Actions."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"version={version}\n")


def _resolve(repo, path):
    return path if os.path.isabs(path) else os.path.join(repo, path)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate changelog/diff/coverage for the newest modlist export "
                    "into changelog/v<ver>/ and stub the CHANGELOG.md entry.")
    parser.add_argument("--repo", default=".", help="Consumer repo root (default: .)")
    parser.add_argument("--lists", default="lists",
                        help="Directory of versioned list exports, relative to --repo (default: lists)")
    parser.add_argument("--pages-url", default="",
                        help="GitHub Pages base URL for .html links; omit for relative links")
    parser.add_argument("--changelog-file", default="CHANGELOG.md",
                        help="Changelog to insert the entry into, relative to --repo")
    parser.add_argument("--min-confidence", type=float, default=0.80,
                        help="Minimum confidence for fuzzy name matching (default: 0.80)")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate reports even if changelog/v<ver>/ exists")
    args = parser.parse_args(argv)

    repo = os.path.abspath(args.repo)
    lists_dir = _resolve(repo, args.lists)
    pair = find_pair(lists_dir)
    if pair is None:
        print(f"Fewer than two versioned lists in {lists_dir}; nothing to do.")
        write_github_output("")
        return 0
    old_path, new_path, version = pair
    out_dir = os.path.join(repo, "changelog", f"v{version}")
    if os.path.isdir(out_dir) and not args.force:
        print(f"{out_dir} already exists; nothing to do (use --force to regenerate).")
        write_github_output("")
        return 0

    print(f"Comparing {os.path.basename(old_path)} -> {os.path.basename(new_path)}")
    texts = generate_reports(old_path, new_path, out_dir, args.min_confidence)
    for name in REPORT_NAMES:
        print(f"Wrote {os.path.join(out_dir, name)}")

    changelog_path = _resolve(repo, args.changelog_file)
    existing = ""
    if os.path.exists(changelog_path):
        with open(changelog_path, "r", encoding="utf-8") as f:
            existing = f.read()
    has_loadorder = os.path.isdir(os.path.join(repo, "loadorder", f"v{version}"))
    entry = render_entry(version, parse_counts(texts["changelog.md"]),
                         args.pages_url, has_loadorder)
    updated = insert_entry(existing, version, entry)
    if updated is None:
        print(f"{changelog_path} already has a 'Version {version}' section; left untouched")
    else:
        _write(changelog_path, updated)
        print(f"Inserted 'Version {version}' skeleton into {changelog_path}")
    write_github_output(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
