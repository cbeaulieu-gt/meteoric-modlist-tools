"""
Per-target ignore store for the coverage view.

A coverage report compares a SOURCE list against a TARGET list and surfaces the
source mods the target is missing or has at a different version. As the target
list matures, some surfaced mods are ones the user has decided NOT to pull in.
This module persists those decisions to a small text file, one per target list,
so every coverage run against that target greys them out.

The file lives next to the target's reports
(``output/<target>/.coverage-ignore.txt``), holds one raw modName per line
('#' comments and blank lines ignored), and is matched by ``normalize_name_strict``
so a decision survives version bumps and applies across every source list
compared against the target.
"""

import os

from modlist_utils import normalize_name_strict


IGNORE_FILENAME = ".coverage-ignore.txt"

_HEADER = (
    "# Coverage ignore list for this target modlist.\n"
    "# One mod name per line; these mods render muted (like 'common') in every\n"
    "# coverage report against this target and drop out of the actionable counts.\n"
    "# Lines starting with '#' and blank lines are ignored. Edit by hand or via\n"
    "# the coverage server (generate_coverage.py --serve).\n"
)


class IgnoreSet:
    """An immutable view of the ignore file: raw names plus a normalized lookup.

    Names are de-duplicated by their normalized key, keeping the first raw spelling
    for round-tripping back to the file.
    """

    def __init__(self, raw_names):
        self.raw = []
        self.norm = set()
        for name in raw_names:
            key = normalize_name_strict(name)
            if key and key not in self.norm:
                self.norm.add(key)
                self.raw.append(name)

    def contains_name(self, name):
        key = normalize_name_strict(name)
        return bool(key) and key in self.norm

    def __len__(self):
        return len(self.raw)


def is_ignored(ignore, mod):
    """True if a mod dict should be treated as ignored under this IgnoreSet.

    ``ignore`` may be None (no ignore file), in which case nothing is ignored.
    """
    if ignore is None:
        return False
    return ignore.contains_name(mod.get("modName", ""))


def resolve_ignore_path(output_arg, target_path):
    """Locate the per-target ignore file, or None when it can't be determined.

    Mirrors ``modlist_utils.resolve_output_path``'s directory detection:
      - output_arg falsy (stdout)      -> None
      - output_arg is a directory      -> <output_arg>/<target_basename>/.coverage-ignore.txt
      - output_arg is an explicit file -> <dirname(output_arg)>/.coverage-ignore.txt
    """
    if not output_arg:
        return None
    is_dir = output_arg.endswith(("/", "\\")) or os.path.isdir(output_arg)
    if is_dir:
        target_name = os.path.splitext(os.path.basename(target_path))[0]
        return os.path.join(output_arg, target_name, IGNORE_FILENAME)
    return os.path.join(os.path.dirname(output_arg) or ".", IGNORE_FILENAME)


def load_ignore(path):
    """Load an IgnoreSet from a file. Missing file or None path -> empty set."""
    if not path or not os.path.exists(path):
        return IgnoreSet([])
    names = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            names.append(line)
    return IgnoreSet(names)


def save(path, names):
    """Write the ignore file: header + sorted (case-insensitive), de-duplicated names."""
    ignore = IgnoreSet(names)
    ordered = sorted(ignore.raw, key=lambda n: n.lower())
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(_HEADER)
        for name in ordered:
            f.write(name + "\n")


def add(path, name):
    """Add a name to the ignore file (idempotent). Returns the updated IgnoreSet."""
    ignore = load_ignore(path)
    if not ignore.contains_name(name):
        save(path, ignore.raw + [name])
        return load_ignore(path)
    return ignore


def remove(path, name):
    """Remove a name from the ignore file (idempotent). Returns the updated IgnoreSet."""
    ignore = load_ignore(path)
    if ignore.contains_name(name):
        key = normalize_name_strict(name)
        kept = [n for n in ignore.raw if normalize_name_strict(n) != key]
        save(path, kept)
        return load_ignore(path)
    return ignore
