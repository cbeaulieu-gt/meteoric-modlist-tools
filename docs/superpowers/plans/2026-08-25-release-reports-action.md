# Release Reports GitHub Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A composite GitHub Action (`action.yml` + `tools/release_reports.py`) that a modlist repo installs so that committing a new list JSON export opens a PR containing `changelog/v<ver>/{changelog.md,coverage.html,diff.html}` and a `CHANGELOG.md` entry skeleton.

**Architecture:** `tools/release_reports.py` is a stdlib-only script beside the other generators: it finds the two newest versioned `*.json` in `lists/`, calls the three generators' pure `generate(...)` functions, writes fixed-name reports, and splices a skeleton entry into `CHANGELOG.md`. `action.yml` at the repo root wraps it: run the script from `${{ github.action_path }}`, and if it produced a version, branch/commit/push/`gh pr create` with the runner's own `git` and `gh`. No third-party actions, no install step.

**Tech Stack:** Python 3 stdlib (`argparse`, `re`, `json`, `os`), `unittest`; GitHub composite action YAML, `bash`, `gh`.

**Spec:** [docs/superpowers/specs/2026-08-25-release-reports-action-design.md](../specs/2026-08-25-release-reports-action-design.md)

## Global Constraints

- Version = trailing `v?(\d+(?:\.\d+)*)` before `.json`, compared as an int tuple; the rest of the filename is ignored. Only the two newest files are paired.
- Report paths are exactly `changelog/v<ver>/changelog.md`, `diff.html`, `coverage.html` under the consumer repo root. Coverage is `source=old, target=new`. Default `min_confidence=0.80`.
- Report content must equal what the CLI generators produce for the same pair (same `generate()` calls; display names = filename stems, as in `generate_diff.main`).
- `CHANGELOG.md` skeleton is the exact block in the spec §5 (headings immediately followed by their list — no blank line between `### Summary` and `- **Added:**`). `.md`/folder links relative; `.html` links `<pages-url>changelog/v<ver>/<file>` when `--pages-url` is given, relative otherwise. Load-order line only when `loadorder/v<ver>/` exists.
- Script exits 0 with a notice when there is nothing to do (<2 lists, or `changelog/v<ver>/` exists without `--force`); an existing `## Version <ver>` section is never rewritten, even with `--force`.
- Files are written UTF-8 with `\n` newlines.
- Tests run from `tools/` with `python -m unittest …`, same as the rest of the suite; all existing tests stay green.

**User decisions (already made):**
- Compare each new export against the previous version of the same list (not against other lists / declared pairs).
- Versioned filenames in `lists/`, one modlist per consumer repo.
- Output committed to the consumer repo and served by GitHub Pages "deploy from branch" (`main`, `/`); all three report types published per release.
- The action lands its changes as a PR (no direct-to-main mode).
- The action lives in this repo (`imightbemeteor/meteoric-modlist-tools@v1`); the consumer holds only its workflow, lists, and outputs.
- `GITHUB_TOKEN` via a `token` input defaulting to `${{ github.token }}`; consumers grant `contents: write, pull-requests: write` and enable the Actions PR-creation setting.
- Save-safety and highlights are always human-written: the skeleton carries `<!-- TODO -->` markers (no parsing of the generator Summary for them).

---

### Task 1: Version parsing and list pairing

**Goal:** `tools/release_reports.py` exists with `parse_version` and `find_pair`, covered by tests.

**Files:**
- Create: `tools/release_reports.py`
- Create: `tools/test_release_reports.py`

**Acceptance Criteria:**
- [ ] `parse_version("NORDIC SOULS v3.2.0 - PBR Edition 1.6.0.json") == ((1, 6, 0), "1.6.0")`; the `v3.2.0` in the base name is ignored.
- [ ] `parse_version("v2.0.2.json") == ((2, 0, 2), "2.0.2")`, `parse_version("my-list_1.10.json") == ((1, 10), "1.10")`, `parse_version("My List.json") is None`, `parse_version("notes 1.0.txt") is None`.
- [ ] `find_pair` on a dir with `Foo 1.9.0.json`, `Foo 1.10.0.json`, `Foo 1.2.0.json` returns `(…/Foo 1.9.0.json, …/Foo 1.10.0.json, "1.10.0")` (numeric order, not string order).
- [ ] `find_pair` returns `None` with fewer than two versioned files; unversioned `.json` files are ignored.

**Verify:** `cd tools && python -m unittest test_release_reports -v` → all `VersionTests`/`PairTests` pass.

**Steps:**

- [ ] **Step 1: Write the failing tests**

`tools/test_release_reports.py`:

```python
"""Tests for release_reports.py — the per-release report + CHANGELOG stub tool."""

import os
import tempfile
import unittest

import release_reports as rr


def _touch(directory, name, content=""):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return path


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools && python -m unittest test_release_reports -v`
Expected: `ModuleNotFoundError: No module named 'release_reports'`

- [ ] **Step 3: Write the implementation**

`tools/release_reports.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd tools && python -m unittest test_release_reports -v`
Expected: 8 tests, `OK`

- [ ] **Step 5: Commit**

```bash
git add tools/release_reports.py tools/test_release_reports.py
git commit -m "feat(release-reports): version parsing and newest-pair discovery"
```

```json:metadata
{"files": ["tools/release_reports.py", "tools/test_release_reports.py"], "verifyCommand": "cd tools && python -m unittest test_release_reports -v", "acceptanceCriteria": ["parse_version handles trailing token, v-prefix, two-part, no-token, non-json", "find_pair sorts numerically and returns the two newest", "find_pair returns None with <2 versioned files"], "modelTier": "mechanical"}
```

---

### Task 2: Report generation into `changelog/v<ver>/`

**Goal:** `generate_reports(old_path, new_path, out_dir)` writes the three fixed-name reports whose content equals the generators' output for the `examples/lists/` fixtures.

**Files:**
- Modify: `tools/release_reports.py`
- Modify: `tools/test_release_reports.py`

**Acceptance Criteria:**
- [ ] After `generate_reports(EX10, EX11, out)`, `out/` contains exactly `changelog.md`, `diff.html`, `coverage.html`.
- [ ] `changelog.md` content equals `generate_changelog.generate(load(EX10), load(EX11))`; `diff.html` equals `generate_diff.generate(old, new, "Example List 1.0", "Example List 1.1")`; `coverage.html` equals `generate_coverage.generate(old, new, "Example List 1.0", "Example List 1.1")`.
- [ ] The return value is `{"changelog.md": text, "diff.html": text, "coverage.html": text}`.
- [ ] `out_dir` is created if missing (including parents).

**Verify:** `cd tools && python -m unittest test_release_reports.GenerateTests -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing tests** — append to `tools/test_release_reports.py`:

```python
import json  # add to the imports at the top

import generate_changelog
import generate_coverage
import generate_diff

EXAMPLES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "examples", "lists"
)
EX_OLD = os.path.join(EXAMPLES, "Example List 1.0.json")
EX_NEW = os.path.join(EXAMPLES, "Example List 1.1.json")


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools && python -m unittest test_release_reports.GenerateTests -v`
Expected: `AttributeError: module 'release_reports' has no attribute 'generate_reports'`

- [ ] **Step 3: Implement** — add to `tools/release_reports.py` (imports at top, function after `find_pair`):

```python
import generate_changelog
import generate_coverage
import generate_diff
from modlist_utils import load_modlist

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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd tools && python -m unittest test_release_reports -v`
Expected: 10 tests, `OK`

- [ ] **Step 5: Commit**

```bash
git add tools/release_reports.py tools/test_release_reports.py
git commit -m "feat(release-reports): write the three fixed-name reports"
```

```json:metadata
{"files": ["tools/release_reports.py", "tools/test_release_reports.py"], "verifyCommand": "cd tools && python -m unittest test_release_reports -v", "acceptanceCriteria": ["exactly changelog.md, diff.html, coverage.html written", "content equals the generators' generate() output for examples/lists", "out_dir created with parents"], "modelTier": "mechanical"}
```

---

### Task 3: CHANGELOG.md skeleton insertion

**Goal:** `parse_counts`, `render_entry`, and `insert_entry` produce the spec §5 skeleton and splice it into a `CHANGELOG.md` idempotently.

**Files:**
- Modify: `tools/release_reports.py`
- Modify: `tools/test_release_reports.py`

**Acceptance Criteria:**
- [ ] `parse_counts` returns `{"Added": 41, "Removed": 20, "Updated": 69}` from a generator changelog; raises `ValueError` if any of the three is missing.
- [ ] `render_entry("1.6.0", counts, "https://x.github.io/r/", has_loadorder=False)` equals the exact block below (Pages URLs on the two `.html` links, no Load order line); with `pages_url=""` the `.html` links are `changelog/v1.6.0/diff.html`; with `has_loadorder=True` the Load order line is appended; a pages URL without trailing slash gets one.
- [ ] `insert_entry` on the nordic-souls-shaped fixture puts `- [Version 1.7.0](#version-170)` first in Contents and the new section immediately after the Contents list, before `## Version 1.6.0`, with exactly one blank line on each side; anchor drops the dots.
- [ ] `insert_entry` returns `None` when `## Version <ver>` already exists.
- [ ] `insert_entry("", …)` yields `## Contents\n\n- [Version …]\n\n## Version …` (fresh file); a file with no `## Contents` gets one prepended.

**Verify:** `cd tools && python -m unittest test_release_reports.ChangelogTests -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing tests** — append to `tools/test_release_reports.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools && python -m unittest test_release_reports.ChangelogTests -v`
Expected: `AttributeError` on `parse_counts`

- [ ] **Step 3: Implement** — add to `tools/release_reports.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd tools && python -m unittest test_release_reports -v`
Expected: 21 tests, `OK`. If `test_insert_into_existing_changelog` fails on blank-line placement, print `repr(out)` and adjust the `insert` padding — the target is exactly one blank line before `## Version 1.7.0` and one between the entry's last line and `## Version 1.6.0`.

- [ ] **Step 5: Commit**

```bash
git add tools/release_reports.py tools/test_release_reports.py
git commit -m "feat(release-reports): CHANGELOG.md entry skeleton insertion"
```

```json:metadata
{"files": ["tools/release_reports.py", "tools/test_release_reports.py"], "verifyCommand": "cd tools && python -m unittest test_release_reports -v", "acceptanceCriteria": ["parse_counts extracts the three counts and errors when one is missing", "render_entry matches the spec block exactly, Pages vs relative links, optional Load order line", "insert_entry places Contents line first and section right after Contents; None if section exists; handles empty/no-Contents files"], "modelTier": "mechanical"}
```

---

### Task 4: CLI `main()` and end-to-end script behaviour

**Goal:** `python tools/release_reports.py` wires discovery → skip check → reports → CHANGELOG → `GITHUB_OUTPUT`, with the exit-0 notice paths from the spec's error table.

**Files:**
- Modify: `tools/release_reports.py`
- Modify: `tools/test_release_reports.py`

**Acceptance Criteria:**
- [ ] In a temp repo with `lists/` = copies of the two example lists, `main(["--repo", repo, "--pages-url", "https://x/"])` returns 0, creates `changelog/v1.1/{changelog.md,diff.html,coverage.html}`, creates `CHANGELOG.md` containing `## Version 1.1` and `https://x/changelog/v1.1/diff.html`, and appends `version=1.1` to the file named by `GITHUB_OUTPUT`.
- [ ] Running `main` again returns 0, changes nothing, and appends `version=` (empty).
- [ ] `--force` regenerates the reports but leaves the existing `## Version 1.1` section untouched (the CHANGELOG file is byte-identical).
- [ ] With one list, `main` returns 0, creates nothing, and writes `version=`.
- [ ] A `loadorder/v1.1/` directory present before the run adds the Load order line.
- [ ] `--lists` and `--changelog-file` resolve relative to `--repo`; absolute paths are used as-is.

**Verify:** `cd tools && python -m unittest test_release_reports -v` → all pass; `python tools/release_reports.py --repo <tmp>` prints what it wrote.

**Steps:**

- [ ] **Step 1: Write the failing tests** — append to `tools/test_release_reports.py`:

```python
import shutil  # add to the imports at the top


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

    def test_custom_lists_and_changelog_paths(self):
        os.rename(os.path.join(self.repo, "lists"), os.path.join(self.repo, "exports"))
        rc = rr.main(["--repo", self.repo, "--lists", "exports", "--changelog-file", "HISTORY.md"])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "HISTORY.md")))
        self.assertIn("[Diff report](changelog/v1.1/diff.html)",
                      _read(os.path.join(self.repo, "HISTORY.md")))
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools && python -m unittest test_release_reports.MainTests -v`
Expected: `AttributeError: module 'release_reports' has no attribute 'main'`

- [ ] **Step 3: Implement** — add to `tools/release_reports.py` (`argparse`, `sys` to imports; functions at the end):

```python
import argparse
import sys


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
        with open(changelog_path, "r", encoding="utf-8", newline="") as f:
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd tools && python -m unittest test_release_reports -v`
Expected: 27 tests, `OK`

- [ ] **Step 5: Manual CLI check**

```bash
python tools/release_reports.py --repo "$TMP/demo"   # after copying examples/lists into $TMP/demo/lists
```
Expected output: `Comparing Example List 1.0.json -> Example List 1.1.json`, three `Wrote …` lines, `Inserted 'Version 1.1' skeleton into …/CHANGELOG.md`.

- [ ] **Step 6: Commit**

```bash
git add tools/release_reports.py tools/test_release_reports.py
git commit -m "feat(release-reports): CLI main with skip/force/GITHUB_OUTPUT"
```

```json:metadata
{"files": ["tools/release_reports.py", "tools/test_release_reports.py"], "verifyCommand": "cd tools && python -m unittest test_release_reports -v", "acceptanceCriteria": ["first run writes reports + CHANGELOG + version output", "second run is a no-op with empty version output", "--force regenerates reports only", "single list is a no-op", "loadorder line when folder exists", "--lists/--changelog-file resolve against --repo"], "modelTier": "mechanical"}
```

---

### Task 5: `action.yml` composite action

**Goal:** A root-level composite action that runs the script and, when it produced a version, pushes a branch and opens a PR.

**Files:**
- Create: `action.yml`

**Acceptance Criteria:**
- [ ] Inputs `lists` (default `lists`), `pages-url` (default `""`), `changelog-file` (default `CHANGELOG.md`), `token` (default `${{ github.token }}`); outputs `version`, `pr-url`.
- [ ] Step `generate` runs `python3 "${{ github.action_path }}/tools/release_reports.py"` with the inputs; no checkout of this repo (composite actions are already checked out at `github.action_path`).
- [ ] Step `pr` runs only when `steps.generate.outputs.version != ''`; commits as `github-actions[bot]`, pushes `modlist-reports/v<ver>` without `--force`, opens the PR against `github.event.repository.default_branch` with `gh`, and writes `pr-url`.
- [ ] The `pr` step's shell block passes `bash -n`; YAML validity and behaviour are proven by the live run in Task 8 (no PyYAML in the stdlib to lint locally).

**Verify:** extract the `run:` block of the `pr` step into a file and run `bash -n` on it → no syntax errors; end-to-end verification is Task 8.

**Steps:**

- [ ] **Step 1: Write `action.yml`**

```yaml
name: Modlist release reports
description: >-
  Generate changelog, diff and coverage reports for the newest modlist export in
  lists/ and open a pull request with them plus a CHANGELOG.md entry skeleton.
author: imightbemeteor

inputs:
  lists:
    description: Directory of versioned modlist JSON exports, relative to the repo root.
    default: lists
  pages-url:
    description: >-
      GitHub Pages base URL (e.g. https://user.github.io/repo/) used for the
      .html report links in CHANGELOG.md. Leave empty for relative links.
    default: ""
  changelog-file:
    description: Changelog file to insert the entry skeleton into.
    default: CHANGELOG.md
  token:
    description: >-
      Token used to push the branch and open the PR. Defaults to the run's
      GITHUB_TOKEN; pass a PAT if the PR should trigger other workflows.
    default: ${{ github.token }}

outputs:
  version:
    description: The release version reports were generated for; empty when nothing was generated.
    value: ${{ steps.generate.outputs.version }}
  pr-url:
    description: URL of the opened pull request; empty when nothing was generated.
    value: ${{ steps.pr.outputs.pr-url }}

runs:
  using: composite
  steps:
    - id: generate
      shell: bash
      run: |
        python3 "${{ github.action_path }}/tools/release_reports.py" \
          --repo . \
          --lists "${{ inputs.lists }}" \
          --pages-url "${{ inputs.pages-url }}" \
          --changelog-file "${{ inputs.changelog-file }}"

    - id: pr
      if: steps.generate.outputs.version != ''
      shell: bash
      env:
        GH_TOKEN: ${{ inputs.token }}
        VERSION: ${{ steps.generate.outputs.version }}
        CHANGELOG_FILE: ${{ inputs.changelog-file }}
        BASE_BRANCH: ${{ github.event.repository.default_branch }}
      run: |
        set -euo pipefail
        branch="modlist-reports/v$VERSION"
        git config user.name "github-actions[bot]"
        git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
        git switch -c "$branch"
        git add "changelog/v$VERSION" "$CHANGELOG_FILE"
        git commit -m "Add v$VERSION detailed reports and CHANGELOG entry"
        git push -u origin "$branch"
        url=$(gh pr create \
          --base "$BASE_BRANCH" \
          --head "$branch" \
          --title "v$VERSION changelog: detailed reports + CHANGELOG entry" \
          --body "$(cat <<EOF
        Generated by [meteoric-modlist-tools](https://github.com/imightbemeteor/meteoric-modlist-tools).

        Adds \`changelog/v$VERSION/\`:
        - \`changelog.md\` — full added/removed/updated lists
        - \`diff.html\` — side-by-side modlist diff (renders via GitHub Pages)
        - \`coverage.html\` — coverage report (renders via GitHub Pages)

        \`$CHANGELOG_FILE\` has a new **Version $VERSION** section. Before merging, fill in:
        - [ ] the save-safety line (\`<!-- TODO: save-safe … -->\`)
        - [ ] the highlight sections (\`<!-- TODO: write highlights … -->\`)
        EOF
        )")
        echo "pr-url=$url" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 2: Syntax-check the shell block**

```bash
python3 - <<'PY' > "$TMP/pr.sh"
import re
text = open("action.yml", encoding="utf-8").read()
block = text.split("    - id: pr", 1)[1].split("run: |", 1)[1]
print("
".join(line[8:] for line in block.split("
")))
PY
bash -n "$TMP/pr.sh"
```
Expected: no output (exit 0). Note the heredoc body is indented to the `run:` block level and the closing `EOF` must sit at the same indentation as `--body` for bash to see it after YAML strips the block indent — if `bash -n` reports `unexpected EOF`, re-align `EOF`.

- [ ] **Step 3: Commit**

```bash
git add action.yml
git commit -m "feat: composite GitHub Action wrapping release_reports.py"
```

```json:metadata
{"files": ["action.yml"], "verifyCommand": "bash -n on the extracted pr-step script", "acceptanceCriteria": ["inputs/outputs as spec", "generate step runs the script from github.action_path", "pr step gated on non-empty version, no force-push, PR against default branch"], "modelTier": "standard"}
```

---

### Task 6: Documentation (README, CLAUDE.md, test command)

**Goal:** Consumers can install the action from the README; the assistant guide and test commands know about the new files.

**Files:**
- Modify: `README.md` (new `## GitHub Action` section before `## Claude Code slash commands`; test command in `## Testing`)
- Modify: `CLAUDE.md` (tool list bullet; test command)

**Acceptance Criteria:**
- [ ] README has a `## GitHub Action` section containing: the consumer layout, the filename/version table, the starter workflow, the inputs table, prerequisites (Pages from branch; Actions "Read and write" + "Allow GitHub Actions to create and approve pull requests"), what the PR contains, and the "one modlist per `lists/`" constraint.
- [ ] Both test commands (README + CLAUDE.md) include `test_release_reports`.
- [ ] CLAUDE.md's tool list has a `tools/release_reports.py` bullet naming `action.yml` and linking the spec.

**Verify:** `grep -n "test_release_reports" README.md CLAUDE.md` → 2 hits; `grep -n "^## GitHub Action" README.md` → 1 hit; the full suite command in CLAUDE.md runs green.

**Steps:**

- [ ] **Step 1: Add the README section** (insert before `## Claude Code slash commands`):

````markdown
## GitHub Action

Modlist repos can run the three generators automatically: commit a new export to `lists/`
and a pull request appears with the reports and a `CHANGELOG.md` entry skeleton.

```
<your modlist repo>/
├── lists/                  # one modlist, one export per release (see naming below)
├── changelog/v<ver>/       # written by the action: changelog.md, diff.html, coverage.html
├── loadorder/v<ver>/       # optional, maintained by hand; linked from the entry when present
└── CHANGELOG.md            # "## Contents" list + one "## Version X.Y.Z" section per release
```

**Naming.** The version is the trailing token before `.json`; everything before it is ignored, so
the list's display name can change between releases. `lists/` must hold only one modlist's exports.

| Filename | Version |
|---|---|
| `Meteoric 0.1.0.json` | 0.1.0 |
| `NORDIC SOULS v3.2.0 - PBR Edition 1.6.0.json` | 1.6.0 |
| `v2.0.2.json`, `2.0.2.json` | 2.0.2 |
| `my-list_1.10.json` | 1.10 (sorts after 1.9) |
| `My List.json` | ignored |

The two newest versions are compared (older → newer); coverage runs with the older list as
source. Nothing happens if `changelog/v<ver>/` already exists, so re-runs are safe.

**Install** — `.github/workflows/release-reports.yml` in your repo:

```yaml
name: Release reports
on:
  push:
    branches: [main]
    paths: ['lists/*.json']
  workflow_dispatch:
permissions:
  contents: write
  pull-requests: write
jobs:
  reports:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: imightbemeteor/meteoric-modlist-tools@v1
        with:
          pages-url: https://<user>.github.io/<repo>/
```

| Input | Default | Purpose |
|---|---|---|
| `lists` | `lists` | Export directory, relative to the repo root |
| `pages-url` | *(empty)* | Base URL for the `.html` report links; empty = relative links |
| `changelog-file` | `CHANGELOG.md` | File that receives the entry skeleton |
| `token` | `${{ github.token }}` | Token for the push and PR; a PAT lets the PR trigger other workflows |

**Prerequisites.** GitHub doesn't render `.html` in the repo browser, so enable Pages
(*Settings → Pages → Deploy from a branch*, `main`, `/ (root)`) and pass the site URL as
`pages-url`. Under *Settings → Actions → General → Workflow permissions*, choose **Read and
write** and tick **Allow GitHub Actions to create and approve pull requests**, or `gh pr create`
fails with 403.

**The PR** (branch `modlist-reports/v<ver>`) adds the three reports and a `## Version <ver>`
section with the Added/Removed/Updated counts, links to the reports, and two `<!-- TODO -->`
markers — the save-safety call and the highlight prose are yours to write before merging.
````

- [ ] **Step 2: Update the test commands** in README `## Testing` and CLAUDE.md `## Testing`: append `test_release_reports` after `test_nexus_description` in the `python -m unittest …` line.

- [ ] **Step 3: Add the CLAUDE.md tool bullet** after the `tools/regenerate.py` bullet:

```markdown
- **`tools/release_reports.py`** — the GitHub Action's engine: pairs the two newest versioned exports in a consumer repo's `lists/`, writes `changelog/v<ver>/{changelog.md,diff.html,coverage.html}`, and splices a `## Version <ver>` skeleton into `CHANGELOG.md`. Wrapped by the root `action.yml` (composite; branch + PR via the runner's `git`/`gh`). Design: [docs/superpowers/specs/2026-08-25-release-reports-action-design.md](docs/superpowers/specs/2026-08-25-release-reports-action-design.md); the consumer-side conventions came from [docs/design/2026-08-25-nordic-souls-release-workflow.md](docs/design/2026-08-25-nordic-souls-release-workflow.md).
```

- [ ] **Step 4: Run the full suite**

Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin test_nexus_description test_release_reports -v`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: GitHub Action section, release_reports in tool list and test command"
```

```json:metadata
{"files": ["README.md", "CLAUDE.md"], "verifyCommand": "grep -n test_release_reports README.md CLAUDE.md && grep -n '^## GitHub Action' README.md", "acceptanceCriteria": ["README GitHub Action section with layout, naming table, starter workflow, inputs, prerequisites, PR contents", "test commands include test_release_reports", "CLAUDE.md tool bullet"], "modelTier": "mechanical"}
```

---

### Task 7: Publish `v1` (user gate — outward-facing)

**Goal:** The action is reachable as `imightbemeteor/meteoric-modlist-tools@v1`.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none (git tags only)

**Acceptance Criteria:**
- [ ] The user has confirmed pushing to `origin main` and creating the tags.
- [ ] `git ls-remote --tags origin` lists `v1.0.0` and `v1`, both pointing at the commit from Task 6.

**Verify:** `git ls-remote --tags origin | grep -E 'refs/tags/v1(\.0\.0)?$'` → two lines with the same SHA.

**Steps:**

- [ ] **Step 1: Ask the user** (this pushes to GitHub — irreversible/outward): "Ready to push `main` and tag `v1.0.0` + moving `v1`?" Do not proceed without a yes.
- [ ] **Step 2: Push and tag**

```bash
git push origin main
git tag -a v1.0.0 -m "release-reports action v1.0.0"
git tag -f v1 v1.0.0
git push origin v1.0.0
git push -f origin v1
```

- [ ] **Step 3: Verify**

```bash
git ls-remote --tags origin | grep -E 'refs/tags/v1(\.0\.0)?$'
```
Expected: two lines, same SHA.

```json:metadata
{"files": [], "verifyCommand": "git ls-remote --tags origin | grep -E 'refs/tags/v1(\\.0\\.0)?$'", "acceptanceCriteria": ["user confirmed the push", "v1.0.0 and v1 tags exist on origin at the same SHA"], "modelTier": "mechanical", "userGate": true, "tags": ["user-gate"], "gateScope": "outward-facing push"}
```

---

### Task 8: End-to-end verification in nordic-souls-PBR (user gate)

**Goal:** The starter workflow installed in `SkrubbySkrubInAShrub/nordic-souls-PBR` opens a PR whose reports match the published `changelog/v1.6.0/` modulo the refreshed 1.6.0 export.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files (in the consumer repo, not this one):**
- Create: `nordic-souls-PBR/.github/workflows/release-reports.yml` (the README starter, `pages-url: https://skrubbyskrubinashrub.github.io/nordic-souls-PBR/`)
- Create: `nordic-souls-PBR/lists/NORDIC SOULS v3.1.1 - PBR Edition 1.5.0.json`, `… v3.2.0 - PBR Edition 1.6.0.json` (from this workspace's `lists/`)

**Acceptance Criteria:**
- [ ] Because `changelog/v1.6.0/` already exists there, the first run must be a no-op: the workflow log shows `already exists; nothing to do` and no PR is opened. (This is the idempotency check on a real repo.)
- [ ] Then, on a branch, delete `changelog/v1.6.0/` and the `## Version 1.6.0` section's Contents line + section from `CHANGELOG.md`, push, and trigger `workflow_dispatch` on that branch: a PR `modlist-reports/v1.6.0` opens against the default branch.
- [ ] In that PR, `changelog/v1.6.0/changelog.md` differs from the published one only in the three refreshed mods (CommunityShaders_AIO date, DynDOLOD DLL NG, Simple Follower Framework) and the `Updated` count (71 vs 69); `diff.html`/`coverage.html` likewise.
- [ ] The PR's `CHANGELOG.md` diff adds `- [Version 1.6.0](#version-160)` first in Contents and a `## Version 1.6.0` section with the two TODO markers and Pages URLs.
- [ ] Captured output: the workflow run URL, the PR URL, and the `diff` between the PR's `changelog.md` and the published one.

**Verify:** `gh pr view <pr-url> --json files` lists exactly `changelog/v1.6.0/changelog.md`, `changelog/v1.6.0/coverage.html`, `changelog/v1.6.0/diff.html`, `CHANGELOG.md`; `gh pr diff <pr-url> -- changelog/v1.6.0/changelog.md` shows only the refreshed-mod lines.

**Steps:**

- [ ] **Step 1: Ask the user** to confirm pushing the workflow + list JSONs to nordic-souls-PBR and enabling the Actions PR setting (outward-facing; their repo).
- [ ] **Step 2: Install** the starter workflow and the two JSONs on `main` (or a PR they merge). Run `workflow_dispatch`; capture the run URL and confirm the no-op log line.
- [ ] **Step 3: Exercise the generate path** on a branch as described in the acceptance criteria; capture the PR URL.
- [ ] **Step 4: Compare** `gh pr diff <pr-url> -- changelog/v1.6.0/changelog.md` against expectations; paste the diff into the task close message.
- [ ] **Step 5: Clean up** per the user's choice: close the exercise PR and delete the branch, or merge it if they prefer the refreshed reports.

```json:metadata
{"files": [], "verifyCommand": "gh pr view <pr-url> --json files && gh pr diff <pr-url> -- changelog/v1.6.0/changelog.md", "acceptanceCriteria": ["first run on the live repo is a logged no-op with no PR", "branch run opens modlist-reports/v1.6.0 PR with exactly the four files", "changelog.md diff vs published limited to the three refreshed mods and the Updated count", "CHANGELOG.md diff adds Contents line + skeleton with TODOs and Pages URLs", "run URL, PR URL and diff captured"], "modelTier": "frontier", "userGate": true, "tags": ["user-gate"], "requireEvidenceTokens": [["nothing to do", "no-op"], ["modlist-reports/v1.6.0", "pr-url"]], "gateScope": "live consumer repo"}
```
