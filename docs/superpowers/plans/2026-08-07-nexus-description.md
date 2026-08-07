# Nexus Description Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A markdown source file for the modlist_compare plugin's Nexus Mods description, plus a stdlib-only converter that emits the two Nexus fields (350-char short description, BBCode full description).

**Architecture:** One markdown file (`NEXUS_DESCRIPTION.md`) next to the plugin is the source of truth. A standalone line-based converter in `tools/` parses exactly the supported subset (headings, bold, italic, links, images, flat lists, a 3-tag HTML allowlist) and raises `ConversionError` with a line number on anything else. A pure `generate(text) → (short, bbcode)` function carries all logic; `main()` only does file I/O — mirroring the repo's generator pattern.

**Tech Stack:** Python standard library only (`re`, `os`, `unittest`). No third-party dependencies — repo rule.

**Global Constraints:**

- Spec is authoritative: [docs/superpowers/specs/2026-08-07-nexus-description-design.md](../specs/2026-08-07-nexus-description-design.md). Read it before each task.
- No silent mangling: every unsupported construct raises `ConversionError` with a line number.
- Path resolution follows `tools/package_plugin.py`: constants derived from `os.path.dirname(os.path.abspath(__file__))`, so the script works from any cwd.
- Output goes under `dist/nexus/` (`dist/` is already gitignored — do not touch `.gitignore`).
- `package_plugin.py` is NOT modified.
- Unit tests run from inside `tools/` like the rest of the suite.

**User decisions (already made):**

- Source format: markdown + converter script (not hand-written BBCode, not generated from README).
- Short description maintained in the same file as the full description.
- Converter is standalone — explicitly NOT wired into `package_plugin.py`.
- Scope includes drafting the actual modlist_compare description content.
- HTML allowlist escape hatch: `<font color>`, `<u>`, `<center>` only.
- Images supported: `![alt](url)` → `[img]url[/img]`, alt text dropped.

---

## File Structure

- Create: `tools/generate_nexus_description.py` — converter (pure `generate()` + `main()`).
- Create: `tools/test_nexus_description.py` — unit tests.
- Create: `mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.md` — drafted description source.
- Modify: `CLAUDE.md` — add `test_nexus_description` to the tools test command.
- Modify: `mo2-plugins/modlist_compare/README.md` — Development section paragraph.

---

### Task 1: Converter core (`generate()`) with tests

**Goal:** The pure conversion function: section splitting, markdown→BBCode subset, HTML allowlist, short-description validation, loud errors — fully unit-tested.

**Files:**

- Create: `tools/generate_nexus_description.py`
- Test: `tools/test_nexus_description.py`

**Acceptance Criteria:**

- [ ] `generate(markdown_text)` returns `(short_text, bbcode_text)` for a valid document with `# Short description` and `# Description` sections in that order.
- [ ] Every mapping row in the spec's two tables converts as specified (headings, bold, italic, links, images, both list kinds, `<font color>`, `<u>`, `<center>`).
- [ ] Inline transforms compose (bold inside list items, links inside bold).
- [ ] Short description: hard-wrapped lines join with single spaces; >350 chars raises `ConversionError` containing the actual count; any markdown/HTML formatting in it raises.
- [ ] Loud `ConversionError` with a line number for: tables, code fences, inline backticks, `####`+ headings, extra `#` headings, `*`/`+` bullets, nested lists, non-allowlisted HTML tags, missing/misordered sections, content before the first section heading.
- [ ] Plain asterisks with spaces around them (e.g. `a * b`) are NOT treated as italic (italic requires non-space characters adjacent to the markers).

**Verify:** `cd tools && python -m unittest test_nexus_description -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tools/test_nexus_description.py`:

```python
"""Tests for generate_nexus_description.py (markdown -> Nexus BBCode)."""
import unittest

from generate_nexus_description import ConversionError, generate

SHORT = "A one-line blurb."


def doc(body, short=SHORT):
    """Build a minimal valid source document around a Description body."""
    return f"# Short description\n\n{short}\n\n# Description\n\n{body}\n"


class TestSections(unittest.TestCase):
    def test_valid_document_returns_short_and_bbcode(self):
        short, bbcode = generate(doc("Hello."))
        self.assertEqual(short, SHORT)
        self.assertEqual(bbcode, "Hello.\n")

    def test_missing_description_section_raises(self):
        with self.assertRaises(ConversionError):
            generate("# Short description\n\nBlurb.\n")

    def test_sections_out_of_order_raises(self):
        with self.assertRaises(ConversionError):
            generate("# Description\n\nBody.\n\n# Short description\n\nBlurb.\n")

    def test_content_before_first_heading_raises(self):
        with self.assertRaises(ConversionError):
            generate("stray text\n" + doc("Hello."))

    def test_extra_top_level_heading_raises(self):
        with self.assertRaisesRegex(ConversionError, "line"):
            generate(doc("Hello.\n\n# Another section\n"))


class TestHeadings(unittest.TestCase):
    def test_h2_becomes_size4(self):
        _, bbcode = generate(doc("## Title"))
        self.assertEqual(bbcode, "[size=4][b]Title[/b][/size]\n")

    def test_h3_becomes_size3(self):
        _, bbcode = generate(doc("### Section"))
        self.assertEqual(bbcode, "[size=3][b]Section[/b][/size]\n")

    def test_h4_raises(self):
        with self.assertRaisesRegex(ConversionError, "line"):
            generate(doc("#### Too deep"))


class TestInline(unittest.TestCase):
    def test_bold(self):
        _, bbcode = generate(doc("**bold** text"))
        self.assertEqual(bbcode, "[b]bold[/b] text\n")

    def test_italic(self):
        _, bbcode = generate(doc("*italic* text"))
        self.assertEqual(bbcode, "[i]italic[/i] text\n")

    def test_spaced_asterisks_are_not_italic(self):
        _, bbcode = generate(doc("a * b * c"))
        self.assertEqual(bbcode, "a * b * c\n")

    def test_link(self):
        _, bbcode = generate(doc("[site](https://example.com)"))
        self.assertEqual(bbcode, "[url=https://example.com]site[/url]\n")

    def test_image_drops_alt_text(self):
        _, bbcode = generate(doc("![screenshot](https://example.com/a.png)"))
        self.assertEqual(bbcode, "[img]https://example.com/a.png[/img]\n")

    def test_link_inside_bold(self):
        _, bbcode = generate(doc("**see [docs](https://example.com)**"))
        self.assertEqual(bbcode, "[b]see [url=https://example.com]docs[/url][/b]\n")

    def test_underscores_pass_through(self):
        _, bbcode = generate(doc("modlist_utils and _not_ emphasis"))
        self.assertEqual(bbcode, "modlist_utils and _not_ emphasis\n")


class TestHtmlAllowlist(unittest.TestCase):
    def test_font_color(self):
        _, bbcode = generate(doc('<font color="#1e84cc">blue</font>'))
        self.assertEqual(bbcode, "[color=#1e84cc]blue[/color]\n")

    def test_underline(self):
        _, bbcode = generate(doc("<u>under</u>"))
        self.assertEqual(bbcode, "[u]under[/u]\n")

    def test_center(self):
        _, bbcode = generate(doc("<center>mid</center>"))
        self.assertEqual(bbcode, "[center]mid[/center]\n")

    def test_unknown_tag_raises(self):
        with self.assertRaisesRegex(ConversionError, "div"):
            generate(doc("<div>nope</div>"))


class TestLists(unittest.TestCase):
    def test_bullet_list(self):
        _, bbcode = generate(doc("- one\n- two"))
        self.assertEqual(bbcode, "[list]\n[*]one[/*]\n[*]two[/*]\n[/list]\n")

    def test_numbered_list(self):
        _, bbcode = generate(doc("1. one\n2. two"))
        self.assertEqual(bbcode, "[list=1]\n[*]one[/*]\n[*]two[/*]\n[/list]\n")

    def test_bold_inside_list_item(self):
        _, bbcode = generate(doc("- **Key** - value"))
        self.assertEqual(bbcode, "[list]\n[*][b]Key[/b] - value[/*]\n[/list]\n")

    def test_blank_line_closes_list(self):
        _, bbcode = generate(doc("- one\n\nafter"))
        self.assertEqual(bbcode, "[list]\n[*]one[/*]\n[/list]\n\nafter\n")

    def test_star_bullet_raises(self):
        with self.assertRaisesRegex(ConversionError, "line"):
            generate(doc("* item"))

    def test_nested_list_raises(self):
        with self.assertRaisesRegex(ConversionError, "line"):
            generate(doc("- one\n  - nested"))


class TestUnsupported(unittest.TestCase):
    def test_table_raises(self):
        with self.assertRaisesRegex(ConversionError, "line"):
            generate(doc("| a | b |"))

    def test_code_fence_raises(self):
        with self.assertRaisesRegex(ConversionError, "line"):
            generate(doc("```\ncode\n```"))

    def test_inline_backtick_raises(self):
        with self.assertRaisesRegex(ConversionError, "line"):
            generate(doc("run `this`"))


class TestShortDescription(unittest.TestCase):
    def test_wrapped_lines_join_with_spaces(self):
        short, _ = generate(doc("Body.", short="First line\nsecond line"))
        self.assertEqual(short, "First line second line")

    def test_over_limit_raises_with_count(self):
        with self.assertRaisesRegex(ConversionError, "351"):
            generate(doc("Body.", short="x" * 351))

    def test_at_limit_passes(self):
        short, _ = generate(doc("Body.", short="x" * 350))
        self.assertEqual(len(short), 350)

    def test_markdown_in_short_raises(self):
        with self.assertRaises(ConversionError):
            generate(doc("Body.", short="**bold** blurb"))

    def test_html_in_short_raises(self):
        with self.assertRaises(ConversionError):
            generate(doc("Body.", short="<u>blurb</u>"))

    def test_empty_short_raises(self):
        with self.assertRaises(ConversionError):
            generate(doc("Body.", short=""))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m unittest test_nexus_description -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'generate_nexus_description'`

- [ ] **Step 3: Write the converter**

Create `tools/generate_nexus_description.py`:

```python
"""Convert NEXUS_DESCRIPTION.md into Nexus Mods description fields.

Reads the markdown source next to the modlist_compare plugin and writes the
two Nexus fields: dist/nexus/short-description.txt (plain text, one line,
<= 350 chars) and dist/nexus/description.bbcode. The supported markdown
subset and the HTML allowlist are documented in
docs/superpowers/specs/2026-08-07-nexus-description-design.md; anything else
raises ConversionError with a line number rather than degrading silently.
"""
import os
import re

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
SOURCE_PATH = os.path.join(
    REPO_ROOT, "mo2-plugins", "modlist_compare", "NEXUS_DESCRIPTION.md"
)
OUTPUT_DIR = os.path.join(REPO_ROOT, "dist", "nexus")
SHORT_LIMIT = 350

_HTML_ALLOWED = [
    (re.compile(r'<font color="([^"]+)">'), r"[color=\1]"),
    (re.compile(r"</font>"), "[/color]"),
    (re.compile(r"<u>"), "[u]"),
    (re.compile(r"</u>"), "[/u]"),
    (re.compile(r"<center>"), "[center]"),
    (re.compile(r"</center>"), "[/center]"),
]
_HTML_ANY = re.compile(r"</?[a-zA-Z][^>]*>")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
# Italic requires non-space characters just inside the markers, so prose
# asterisks ("a * b") are left alone instead of silently italicised.
_ITALIC = re.compile(r"\*(\S(?:.*?\S)?)\*")


class ConversionError(ValueError):
    """The source uses a construct the converter does not support."""


def _fail(lineno, message):
    raise ConversionError(f"line {lineno}: {message}")


def _check_unsupported(line, lineno):
    if "`" in line:
        _fail(lineno, "backticks (code) are not supported")
    if line.lstrip().startswith("|"):
        _fail(lineno, "tables are not supported")
    if re.match(r"\s+[-*+] ", line) or re.match(r"\s+\d+\. ", line):
        _fail(lineno, "nested lists are not supported")
    if re.match(r"[*+] ", line):
        _fail(lineno, "bullets must use '- '")
    if re.match(r"#{4,} ", line):
        _fail(lineno, "headings deeper than ### are not supported")


def _convert_inline(text, lineno):
    text = _IMAGE.sub(r"[img]\2[/img]", text)
    text = _LINK.sub(r"[url=\2]\1[/url]", text)
    text = _BOLD.sub(r"[b]\1[/b]", text)
    text = _ITALIC.sub(r"[i]\1[/i]", text)
    for pattern, replacement in _HTML_ALLOWED:
        text = pattern.sub(replacement, text)
    leftover = _HTML_ANY.search(text)
    if leftover:
        _fail(lineno, f"HTML tag not in allowlist: {leftover.group(0)}")
    return text


def _split_sections(markdown_text):
    """Split into the two structural sections; returns two (lineno, line) lists."""
    short_lines = body_lines = current = None
    for lineno, raw in enumerate(markdown_text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("# "):
            key = stripped[2:].strip().casefold()
            if key == "short description" and short_lines is None and body_lines is None:
                current = short_lines = []
            elif key == "description" and short_lines is not None and body_lines is None:
                current = body_lines = []
            else:
                _fail(lineno, "unexpected '# ' heading — the only top-level headings "
                              "are '# Short description' then '# Description'")
        elif current is not None:
            current.append((lineno, raw))
        elif stripped:
            _fail(lineno, "content before '# Short description'")
    if short_lines is None or body_lines is None:
        raise ConversionError(
            "source must contain '# Short description' followed by '# Description'"
        )
    return short_lines, body_lines


def _convert_short(short_lines):
    parts = []
    for lineno, raw in short_lines:
        line = raw.strip()
        _check_unsupported(raw, lineno)
        if re.match(r"#{1,6} ", line) or re.match(r"- ", line) or re.match(r"\d+\. ", line):
            _fail(lineno, "the short description must be a plain paragraph")
        if (_IMAGE.search(line) or _LINK.search(line) or _BOLD.search(line)
                or _ITALIC.search(line) or _HTML_ANY.search(line)):
            _fail(lineno, "no markdown/HTML formatting in the short description "
                          "— the Nexus mod card renders plain text")
        if line:
            parts.append(line)
    short = " ".join(parts)
    if not short:
        raise ConversionError("short description is empty")
    if len(short) > SHORT_LIMIT:
        raise ConversionError(
            f"short description is {len(short)} characters (limit {SHORT_LIMIT})"
        )
    return short


def _convert_body(body_lines):
    out = []
    open_list = None  # None, "[list]", or "[list=1]"

    def close_list():
        nonlocal open_list
        if open_list:
            out.append("[/list]")
            open_list = None

    def open_or_continue(kind):
        nonlocal open_list
        if open_list != kind:
            close_list()
            out.append(kind)
            open_list = kind

    for lineno, raw in body_lines:
        line = raw.rstrip()
        _check_unsupported(line, lineno)
        if not line.strip():
            close_list()
            out.append("")
        elif line.startswith("### "):
            close_list()
            out.append(f"[size=3][b]{_convert_inline(line[4:].strip(), lineno)}[/b][/size]")
        elif line.startswith("## "):
            close_list()
            out.append(f"[size=4][b]{_convert_inline(line[3:].strip(), lineno)}[/b][/size]")
        elif line.startswith("- "):
            open_or_continue("[list]")
            out.append(f"[*]{_convert_inline(line[2:].strip(), lineno)}[/*]")
        elif re.match(r"\d+\. ", line):
            open_or_continue("[list=1]")
            item = re.sub(r"^\d+\. ", "", line).strip()
            out.append(f"[*]{_convert_inline(item, lineno)}[/*]")
        else:
            close_list()
            out.append(_convert_inline(line, lineno))
    close_list()
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    if not out:
        raise ConversionError("description body is empty")
    return "\n".join(out) + "\n"


def generate(markdown_text):
    """Convert the source document; returns (short_text, bbcode_text)."""
    short_lines, body_lines = _split_sections(markdown_text)
    return _convert_short(short_lines), _convert_body(body_lines)


def main():
    with open(SOURCE_PATH, encoding="utf-8") as f:
        short, bbcode = generate(f.read())
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    short_path = os.path.join(OUTPUT_DIR, "short-description.txt")
    bbcode_path = os.path.join(OUTPUT_DIR, "description.bbcode")
    with open(short_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(short + "\n")
    with open(bbcode_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(bbcode)
    print(f"Wrote {short_path} ({len(short)}/{SHORT_LIMIT} chars)")
    print(f"Wrote {bbcode_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools && python -m unittest test_nexus_description -v`
Expected: all tests PASS

- [ ] **Step 5: Run the full tools suite to check nothing broke**

Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin test_nexus_description -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add tools/generate_nexus_description.py tools/test_nexus_description.py
git commit -m "feat: markdown-to-BBCode converter for the Nexus description"
```

```json:metadata
{"files": ["tools/generate_nexus_description.py", "tools/test_nexus_description.py"], "verifyCommand": "cd tools && python -m unittest test_nexus_description -v", "acceptanceCriteria": ["generate() returns (short, bbcode) for a valid two-section document", "all spec mapping rows convert as specified", "inline transforms compose", "short description joins wrapped lines, errors over 350 chars with count, errors on formatting", "ConversionError with line number for every unsupported construct", "spaced asterisks are not italicised"], "modelTier": "mechanical"}
```

---

### Task 2: Drafted `NEXUS_DESCRIPTION.md` + `main()` round-trip

**Goal:** The real description content for modlist_compare, verified end-to-end: the script runs, writes both output files, and the round-trip is locked in by tests.

**Files:**

- Create: `mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.md`
- Modify: `tools/test_nexus_description.py` (append two test classes)

**Acceptance Criteria:**

- [ ] `NEXUS_DESCRIPTION.md` exists with the drafted content below (author edits prose later).
- [ ] `python tools/generate_nexus_description.py` (from repo root) exits 0 and writes `dist/nexus/short-description.txt` and `dist/nexus/description.bbcode`.
- [ ] A test converts the real file without error and asserts the short description is within 350 chars.
- [ ] A test exercises `main()` end-to-end against a temp copy (patched paths), checking both files' contents.

**Verify:** `cd tools && python -m unittest test_nexus_description -v` → all pass, then `python tools/generate_nexus_description.py` from repo root → prints both paths and the char count

**Steps:**

- [ ] **Step 1: Write the source document**

Create `mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.md` with exactly this content (prose is a first pass for the author to edit; the structure deliberately exercises headings, bold, a link, and both hint styles):

```markdown
# Short description

Compare Mod Organizer 2 modlists without leaving MO2. Export any profile to
JSON, then generate coverage, diff, and changelog reports between two lists -
see what a list is missing, how load orders differ, and what changed between
versions. Same reports and file naming as the meteoric-modlist-tools CLI.

# Description

## Modlist Compare

**An MO2 plugin for comparing modlists - see what another list has that yours doesn't, side by side, without leaving Mod Organizer 2.**

### What It Does

Adds a **Modlist Compare** submenu to MO2's Tools menu with two entries: one exports the active profile's modlist to JSON, and one generates reports comparing any two lists - an exported JSON file, your current profile, or one of each. The reports are the same ones the [meteoric-modlist-tools](https://github.com/imightbemeteor/meteoric-modlist-tools) command-line tools produce, from the same code, with the same file naming, so plugin output and CLI output are interchangeable.

### Key Features

- **Coverage report** - What a target list is missing or behind on compared to a source list, with per-mod states and a percent-covered badge (HTML)
- **Diff report** - Both lists' full ordering side by side, colour-coded, including moves (HTML)
- **Changelog** - Added, removed, and updated mods between two versions of a list (markdown)
- **Live profile support** - Compare against your current profile directly, no export step needed
- **Smart matching** - Mods are matched across lists by Nexus IDs, plugin files, and names, so renames and merges are handled
- **Responsive UI** - Generation runs behind a progress dialog with live percent and cancel; MO2 stays usable throughout

### How to Use

1. **Export a list** - Tools, Modlist Compare, Export Modlist to JSON saves the active profile
2. **Open Generate Reports** - Pick List 1 (source/old) and List 2 (target/new): a JSON file or the current profile
3. **Choose reports** - Any combination of Coverage, Diff, and Changelog, plus a destination folder
4. **Generate** - Reports are written to the destination; Open Folder takes you straight there

### Requirements

- Mod Organizer 2 **2.5.0 or newer** (the PyQt6-based Python runtime)
- Nothing else - no third-party Python packages

### Known Limitations

- The coverage ignore list is read but not edited from the plugin; use the CLI's serve mode or a text editor to change it
- Report generation vendors its modules under plain names (modlist_utils and friends); another Python plugin shipping a same-named top-level module could collide - none known
```

- [ ] **Step 2: Append the failing round-trip and main() tests**

Append to `tools/test_nexus_description.py`, extending the imports at the top to `import os`, `import tempfile`, `import unittest`, `from unittest import mock`, and `import generate_nexus_description` alongside the existing `from generate_nexus_description import ConversionError, generate`:

```python
class TestRealDocument(unittest.TestCase):
    def test_real_source_converts_within_limit(self):
        with open(generate_nexus_description.SOURCE_PATH, encoding="utf-8") as f:
            short, bbcode = generate(f.read())
        self.assertLessEqual(len(short), generate_nexus_description.SHORT_LIMIT)
        self.assertIn("[size=4][b]Modlist Compare[/b][/size]", bbcode)
        self.assertIn("[list]", bbcode)
        self.assertIn("[list=1]", bbcode)


class TestMain(unittest.TestCase):
    def test_main_writes_both_files(self):
        source = (
            "# Short description\n\nBlurb.\n\n"
            "# Description\n\n## Title\n\nBody **bold**.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "NEXUS_DESCRIPTION.md")
            out_dir = os.path.join(tmp, "nexus")
            with open(src, "w", encoding="utf-8") as f:
                f.write(source)
            with mock.patch.object(generate_nexus_description, "SOURCE_PATH", src), \
                 mock.patch.object(generate_nexus_description, "OUTPUT_DIR", out_dir):
                generate_nexus_description.main()
            with open(os.path.join(out_dir, "short-description.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "Blurb.\n")
            with open(os.path.join(out_dir, "description.bbcode"), encoding="utf-8") as f:
                self.assertEqual(
                    f.read(), "[size=4][b]Title[/b][/size]\n\nBody [b]bold[/b].\n"
                )
```

- [ ] **Step 3: Run tests**

Run: `cd tools && python -m unittest test_nexus_description -v`
Expected: all PASS (if `TestRealDocument` fails, the drafted document violates the supported subset — fix the document, not the converter)

- [ ] **Step 4: Run the script for real**

Run from repo root: `python tools/generate_nexus_description.py`
Expected: prints `Wrote .../dist/nexus/short-description.txt (NNN/350 chars)` and `Wrote .../dist/nexus/description.bbcode`. Open `dist/nexus/description.bbcode` and eyeball that it resembles the user's sample BBCode (sizes, bold, `[list]` blocks).

- [ ] **Step 5: Commit**

```bash
git add mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.md tools/test_nexus_description.py
git commit -m "feat: drafted Nexus description for modlist_compare"
```

```json:metadata
{"files": ["mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.md", "tools/test_nexus_description.py"], "verifyCommand": "cd tools && python -m unittest test_nexus_description -v && cd .. && python tools/generate_nexus_description.py", "acceptanceCriteria": ["NEXUS_DESCRIPTION.md exists with drafted content", "script runs from repo root and writes both dist/nexus/ files", "round-trip test converts the real file within the 350-char limit", "main() end-to-end test with patched paths passes"], "modelTier": "mechanical"}
```

---

### Task 3: Documentation updates

**Goal:** CLAUDE.md's test command includes the new module; the plugin README's Development section documents the description workflow.

**Files:**

- Modify: `CLAUDE.md` (the Testing section's `python -m unittest ...` command)
- Modify: `mo2-plugins/modlist_compare/README.md` (Development section, after the packaging paragraph)

**Acceptance Criteria:**

- [ ] CLAUDE.md's tools test command lists `test_nexus_description`.
- [ ] Plugin README Development section has one paragraph naming the source file, the script, the two output files, and the paste workflow.

**Verify:** `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin test_nexus_description -v` → all pass (the exact command now documented in CLAUDE.md)

**Steps:**

- [ ] **Step 1: Update CLAUDE.md**

In the Testing section, change:

```bash
cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin -v
```

to:

```bash
cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin test_nexus_description -v
```

- [ ] **Step 2: Update the plugin README**

In `mo2-plugins/modlist_compare/README.md`, in the Development section, insert this paragraph between the packaging paragraph (ends "Both `_vendor/` and `dist/` are gitignored.") and the "Run the plugin's tests" paragraph:

```markdown
The plugin's Nexus Mods page description is maintained in
[NEXUS_DESCRIPTION.md](NEXUS_DESCRIPTION.md) — markdown, converted to the two
Nexus fields by `python tools/generate_nexus_description.py`, which writes
`dist/nexus/short-description.txt` (the mod-card blurb, checked against
Nexus's 350-character limit) and `dist/nexus/description.bbcode` (paste into
the full-description editor via its raw-BBCode view). The converter supports
a deliberate markdown subset and fails loudly on anything else; see
`docs/superpowers/specs/2026-08-07-nexus-description-design.md`.
```

- [ ] **Step 3: Run the newly documented command verbatim**

Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin test_nexus_description -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md mo2-plugins/modlist_compare/README.md
git commit -m "docs: Nexus description workflow in CLAUDE.md and plugin README"
```

```json:metadata
{"files": ["CLAUDE.md", "mo2-plugins/modlist_compare/README.md"], "verifyCommand": "cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin test_nexus_description -v", "acceptanceCriteria": ["CLAUDE.md test command includes test_nexus_description", "plugin README Development section documents source file, script, outputs, paste workflow"], "modelTier": "mechanical"}
```
