#!/usr/bin/env python3
"""Generate the per-release reports for a modlist repo and stub its CHANGELOG entry.

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

import os
import re

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
