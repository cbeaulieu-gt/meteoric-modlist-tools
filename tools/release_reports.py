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
