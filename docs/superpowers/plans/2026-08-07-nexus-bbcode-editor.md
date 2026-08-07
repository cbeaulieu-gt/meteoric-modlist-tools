# Nexus BBCode Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repo-maintained Nexus Mods description for the modlist_compare plugin: two BBCode/text source files, a self-contained local editor page with live preview, and a small unittest guarding the 350-char limit.

**Architecture:** Raw Nexus BBCode is the source of truth — no conversion step; the files are pasted into Nexus as-is. A single committed HTML page (`tools/nexus_bbcode_editor.html`, inline CSS/JS, opens via `file://`) provides load/edit/preview/copy. The preview renderer is deliberately approximate: unknown tags stay visible as literal text, and Nexus's own preview is the final authority.

**Tech Stack:** Hand-rolled inline JavaScript (no libraries, no build step); Python `unittest` for the file checks.

**Global Constraints:**

- Spec is authoritative: [docs/superpowers/specs/2026-08-07-nexus-bbcode-editor-design.md](../specs/2026-08-07-nexus-bbcode-editor-design.md). Read it before each task.
- The editor page is one file, inline CSS/JS only, no external asset requests (the only external URLs it may *reference* are ones the user's own content generates, e.g. `[img]`/`[youtube]` previews).
- The renderer never errors and never strips: unknown/malformed tags remain visible as literal text.
- `package_plugin.py` is NOT modified; the two source files shipping inside the plugin zip is accepted.
- Unit tests run from inside `tools/` like the rest of the suite.

**User decisions (already made):**

- Maintain native BBCode, no markdown↔BBCode conversion (pivot away from an earlier converter design, whose spec/plan were deleted in commit 6c1bfb6).
- Hand-rolled editor page — explicitly not vendored SCEditor/BBob.
- Full editor (textarea + live preview + copy), not a render-only preview page.
- GitHub rendering of the description file as plain text is an accepted trade.
- Drafted description content for modlist_compare is in scope; author edits prose later.

---

## File Structure

- Create: `tools/nexus_bbcode_editor.html` — the whole editor: layout, styles, BBCode renderer, load/copy/autosave wiring.
- Create: `mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.bbcode` — full description, raw Nexus BBCode.
- Create: `mo2-plugins/modlist_compare/NEXUS_SHORT_DESCRIPTION.txt` — mod-card blurb, one line ≤350 chars.
- Create: `tools/test_nexus_description.py` — existence/limit checks on the two source files.
- Modify: `CLAUDE.md` — add `test_nexus_description` to the tools test command.
- Modify: `mo2-plugins/modlist_compare/README.md` — Development-section paragraph.

---

### Task 1: Editor page

**Goal:** The complete self-contained editor page: short-description field with live counter, BBCode textarea with live preview, load-file and copy buttons, localStorage autosave with reset.

**Files:**

- Create: `tools/nexus_bbcode_editor.html`

**Acceptance Criteria:**

- [ ] Opening the file directly in a browser (`file://`) shows the short-description field with a `0 / 350` counter and the BBCode editor beside an empty preview pane; no console errors.
- [ ] Typing in the BBCode textarea re-renders the preview on every keystroke; the counter updates on every short-field keystroke and turns red past 350.
- [ ] The renderer handles `[b] [i] [u] [s] [size=1-6] [color] [font] [url=X]text[/url] [url]link[/url] [img] [list] [list=1] [*] [center] [quote] [spoiler] [youtube] [line]`; input is HTML-escaped before tag transforms; unknown tags (e.g. `[weird]x[/weird]`) render as literal text.
- [ ] Load file… buttons open a picker and fill the matching field; Copy buttons put the field's exact text on the clipboard and flash "Copied!".
- [ ] Both fields survive closing and reopening the page (localStorage); Reset draft clears fields and storage after a confirm.
- [ ] The page makes no external requests of its own (all CSS/JS inline; no `<link>`/`<script src>`/webfont).

**Verify:** Open `tools/nexus_bbcode_editor.html` in a browser, paste the sample below into the BBCode pane, and check the listed expectations. This is a visual check — the user confirms at the review checkpoint; the implementing agent verifies the file is created exactly as specified and self-contained (`grep -E '<(link|script) [^>]*(href|src)=' tools/nexus_bbcode_editor.html` → no matches).

Sample to paste:

```text
[size=4][b]Title[/b][/size]
[b]Bold intro with a [url=https://example.com]link[/url] and [color=#1e84cc]blue text[/color].[/b]
[line]
[list]
[*][b]Item one[/b] - detail[/*]
[*]Item two[/*]
[/list]
[list=1]
[*]Step one[/*]
[*]Step two[/*]
[/list]
[quote]a quote[/quote]
[spoiler]hidden text[/spoiler]
[center]centered[/center]
[weird]unknown tag stays literal[/weird]
```

Expected: large bold title; bold line with working link and blue span; horizontal rule; a bulleted then a numbered list; an indented quote block; a collapsed "Spoiler" disclosure that opens on click; centered text; `[weird]unknown tag stays literal[/weird]` shown verbatim.

**Steps:**

- [ ] **Step 1: Write the page**

Create `tools/nexus_bbcode_editor.html` with exactly this content:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Nexus BBCode Editor</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: "Segoe UI", system-ui, sans-serif;
    margin: 0; padding: 1rem 1.5rem;
    background: #16181c; color: #d6d8db;
  }
  h1 { font-size: 1.2rem; margin: 0 0 1rem; }
  section { margin-bottom: 1.25rem; }
  .field-header {
    display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.4rem;
  }
  .field-header label { font-weight: 600; }
  .field-header .spacer { flex: 1; }
  button {
    background: #2c313a; color: #d6d8db; border: 1px solid #454c58;
    border-radius: 4px; padding: 0.25rem 0.7rem; cursor: pointer;
    font-size: 0.85rem;
  }
  button:hover { background: #3a4150; }
  #short-count { font-variant-numeric: tabular-nums; font-size: 0.85rem; color: #8b929c; }
  #short-count.over { color: #ff5c5c; font-weight: 700; }
  input[type="text"], textarea {
    width: 100%; background: #0f1114; color: #e6e8eb;
    border: 1px solid #454c58; border-radius: 4px; padding: 0.5rem 0.6rem;
    font-family: Consolas, monospace; font-size: 0.9rem;
  }
  .panes { display: flex; gap: 1rem; align-items: stretch; height: 70vh; }
  .panes > * { flex: 1 1 50%; min-width: 0; }
  #bbcode-input { resize: none; height: 100%; }
  #preview {
    overflow: auto; border: 1px solid #454c58; border-radius: 4px;
    padding: 0.8rem 1rem; background: #1b1e24; line-height: 1.45;
  }
  #preview .center { text-align: center; }
  #preview blockquote {
    border-left: 3px solid #454c58; margin: 0.5em 0; padding: 0.3em 0.8em;
    background: #22262d;
  }
  #preview img { max-width: 100%; }
  #preview a { color: #57a8e2; }
  #preview hr { border: none; border-top: 1px solid #454c58; }
  #preview ul, #preview ol { margin: 0.4em 0; }
  #preview details { margin: 0.4em 0; }
  #preview details summary { cursor: pointer; color: #8b929c; }
  .hint { color: #8b929c; font-size: 0.8rem; margin-top: 0.3rem; }
</style>
</head>
<body>
<h1>Nexus BBCode Editor</h1>

<section>
  <div class="field-header">
    <label for="short-input">Short description</label>
    <span id="short-count">0 / 350</span>
    <span class="spacer"></span>
    <button id="short-load">Load file&hellip;</button>
    <button id="short-copy">Copy</button>
  </div>
  <input type="text" id="short-input" spellcheck="true"
         placeholder="One line, plain text, max 350 characters">
</section>

<section>
  <div class="field-header">
    <label for="bbcode-input">Full description (BBCode)</label>
    <span class="spacer"></span>
    <button id="bbcode-load">Load file&hellip;</button>
    <button id="bbcode-copy">Copy</button>
    <button id="reset-draft">Reset draft</button>
  </div>
  <div class="panes">
    <textarea id="bbcode-input" spellcheck="false"
              placeholder="[size=4][b]Title[/b][/size] &hellip;"></textarea>
    <div id="preview"></div>
  </div>
  <p class="hint">Preview is an approximation &mdash; Nexus's own preview is the
  final authority. Unknown tags are shown literally. Copy the result back into
  NEXUS_DESCRIPTION.bbcode and into Nexus's raw-BBCode editor view.</p>
</section>

<input type="file" id="file-picker" hidden>

<script>
"use strict";

const SHORT_LIMIT = 350;
const STORE_SHORT = "nexus-bbcode-short";
const STORE_DESC = "nexus-bbcode-desc";

const shortInput = document.getElementById("short-input");
const shortCount = document.getElementById("short-count");
const bbcodeInput = document.getElementById("bbcode-input");
const preview = document.getElementById("preview");
const filePicker = document.getElementById("file-picker");

/* ---- BBCode -> HTML (approximate; Nexus is the authority) ---- */

const SIZE_PX = { 1: 10, 2: 12, 3: 16, 4: 20, 5: 24, 6: 30 };

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
          .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const INLINE_RULES = [
  [/\[b\]([\s\S]*?)\[\/b\]/gi, "<strong>$1</strong>"],
  [/\[i\]([\s\S]*?)\[\/i\]/gi, "<em>$1</em>"],
  [/\[u\]([\s\S]*?)\[\/u\]/gi, "<u>$1</u>"],
  [/\[s\]([\s\S]*?)\[\/s\]/gi, "<s>$1</s>"],
  [/\[size=([1-6])\]([\s\S]*?)\[\/size\]/gi,
    (m, n, inner) => '<span style="font-size:' + SIZE_PX[n] + 'px">' + inner + "</span>"],
  [/\[color=(#[0-9a-f]{3,8}|[a-z]+)\]([\s\S]*?)\[\/color\]/gi,
    '<span style="color:$1">$2</span>'],
  [/\[font=([a-z0-9 ,-]+)\]([\s\S]*?)\[\/font\]/gi,
    '<span style="font-family:$1">$2</span>'],
  [/\[url=([^\]\s]+)\]([\s\S]*?)\[\/url\]/gi, '<a href="$1">$2</a>'],
  [/\[url\]([^\[\s]+)\[\/url\]/gi, '<a href="$1">$1</a>'],
  [/\[img\]([^\[\s]+)\[\/img\]/gi, '<img src="$1" alt="">'],
  [/\[youtube\]([^\[\s]+)\[\/youtube\]/gi,
    '<a href="https://www.youtube.com/watch?v=$1">&#9654; YouTube: $1</a>'],
  [/\[center\]([\s\S]*?)\[\/center\]/gi, '<div class="center">$1</div>'],
  [/\[quote\]([\s\S]*?)\[\/quote\]/gi, "<blockquote>$1</blockquote>"],
  [/\[spoiler\]([\s\S]*?)\[\/spoiler\]/gi,
    "<details><summary>Spoiler</summary>$1</details>"],
];

function listItems(inner) {
  return inner.split(/\[\*\]/).slice(1)
    .map(item => "<li>" + item.replace(/\[\/\*\]/gi, "").trim() + "</li>")
    .join("");
}

function renderBBCode(raw) {
  let html = escapeHtml(raw);
  /* Repeat the paired-tag pass so nested same-name tags (quote in quote)
     resolve; bail as soon as a pass changes nothing. */
  for (let pass = 0; pass < 5; pass++) {
    const before = html;
    for (const [pattern, replacement] of INLINE_RULES) {
      html = html.replace(pattern, replacement);
    }
    if (html === before) break;
  }
  html = html.replace(/\[list=1\]([\s\S]*?)\[\/list\]/gi,
    (m, inner) => "<ol>" + listItems(inner) + "</ol>");
  html = html.replace(/\[list\]([\s\S]*?)\[\/list\]/gi,
    (m, inner) => "<ul>" + listItems(inner) + "</ul>");
  html = html.replace(/\[line\]/gi, "<hr>");
  /* Newlines to <br>, but not straight after a block closer (double gap). */
  html = html.replace(/(<\/(?:ul|ol|blockquote|details|div)>|<hr>)\n/g, "$1");
  html = html.replace(/\n/g, "<br>");
  return html;
}

/* ---- wiring ---- */

function updateShort() {
  const len = shortInput.value.length;
  shortCount.textContent = len + " / " + SHORT_LIMIT;
  shortCount.classList.toggle("over", len > SHORT_LIMIT);
  localStorage.setItem(STORE_SHORT, shortInput.value);
}

function updateDesc() {
  preview.innerHTML = renderBBCode(bbcodeInput.value);
  localStorage.setItem(STORE_DESC, bbcodeInput.value);
}

shortInput.addEventListener("input", updateShort);
bbcodeInput.addEventListener("input", updateDesc);

function loadInto(target, after) {
  filePicker.onchange = () => {
    const file = filePicker.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      target.value = reader.result.replace(/\r\n/g, "\n").replace(/\n$/, "");
      after();
    };
    reader.readAsText(file);
    filePicker.value = "";
  };
  filePicker.click();
}

document.getElementById("short-load").addEventListener("click",
  () => loadInto(shortInput, updateShort));
document.getElementById("bbcode-load").addEventListener("click",
  () => loadInto(bbcodeInput, updateDesc));

function copyText(text, button) {
  const done = () => {
    const old = button.textContent;
    button.textContent = "Copied!";
    setTimeout(() => { button.textContent = old; }, 1200);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done);
  } else {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    done();
  }
}

document.getElementById("short-copy").addEventListener("click",
  e => copyText(shortInput.value, e.target));
document.getElementById("bbcode-copy").addEventListener("click",
  e => copyText(bbcodeInput.value, e.target));

document.getElementById("reset-draft").addEventListener("click", () => {
  if (!confirm("Clear both fields and the saved draft?")) return;
  localStorage.removeItem(STORE_SHORT);
  localStorage.removeItem(STORE_DESC);
  shortInput.value = "";
  bbcodeInput.value = "";
  updateShort();
  updateDesc();
});

/* Restore draft on open. */
shortInput.value = localStorage.getItem(STORE_SHORT) || "";
bbcodeInput.value = localStorage.getItem(STORE_DESC) || "";
updateShort();
updateDesc();
</script>
</body>
</html>
```

- [ ] **Step 2: Static self-containment check**

Run: `grep -E '<(link|script) [^>]*(href|src)=' tools/nexus_bbcode_editor.html`
Expected: no output (exit 1) — no external stylesheet or script references.

- [ ] **Step 3: Commit**

```bash
git add tools/nexus_bbcode_editor.html
git commit -m "feat: self-contained BBCode editor page with live Nexus-style preview"
```

The full visual pass (sample paste, load/copy buttons, autosave, counter) happens at the user review checkpoint — record it as pending in the task report, not as done.

```json:metadata
{"files": ["tools/nexus_bbcode_editor.html"], "verifyCommand": "grep -E '<(link|script) [^>]*(href|src)=' tools/nexus_bbcode_editor.html; test $? -eq 1", "acceptanceCriteria": ["page opens via file:// with counter, editor, empty preview, no console errors", "live re-render on keystroke; counter red past 350", "all spec tags render; input HTML-escaped; unknown tags literal", "load buttons fill fields; copy buttons flash Copied!", "localStorage autosave with confirm-guarded reset", "no external asset requests"], "modelTier": "mechanical"}
```

---

### Task 2: Drafted source files + unittest

**Goal:** The two committed source files with first-pass content, and the unittest that guards their invariants.

**Files:**

- Create: `mo2-plugins/modlist_compare/NEXUS_SHORT_DESCRIPTION.txt`
- Create: `mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.bbcode`
- Test: `tools/test_nexus_description.py`

**Acceptance Criteria:**

- [ ] `NEXUS_SHORT_DESCRIPTION.txt` holds the one-line blurb below (≤350 chars).
- [ ] `NEXUS_DESCRIPTION.bbcode` holds the drafted BBCode below.
- [ ] `test_nexus_description.py` fails if either file is missing/empty, if the short description contains a newline, or if it exceeds 350 characters (message includes the actual count).
- [ ] Full tools suite still green.

**Verify:** `cd tools && python -m unittest test_nexus_description -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `tools/test_nexus_description.py`:

```python
"""Checks on the committed Nexus description source files."""
import os
import unittest

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.join(
    os.path.dirname(TOOLS_DIR), "mo2-plugins", "modlist_compare"
)
SHORT_PATH = os.path.join(PLUGIN_DIR, "NEXUS_SHORT_DESCRIPTION.txt")
BBCODE_PATH = os.path.join(PLUGIN_DIR, "NEXUS_DESCRIPTION.bbcode")
SHORT_LIMIT = 350


class TestNexusDescriptionFiles(unittest.TestCase):
    def test_bbcode_description_exists_and_non_empty(self):
        with open(BBCODE_PATH, encoding="utf-8") as f:
            self.assertTrue(f.read().strip())

    def test_short_description_is_one_line_within_limit(self):
        with open(SHORT_PATH, encoding="utf-8") as f:
            short = f.read().strip()
        self.assertTrue(short)
        self.assertNotIn("\n", short)
        self.assertLessEqual(
            len(short), SHORT_LIMIT,
            f"short description is {len(short)} characters (limit {SHORT_LIMIT})",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd tools && python -m unittest test_nexus_description -v`
Expected: both tests ERROR with `FileNotFoundError` (files don't exist yet)

- [ ] **Step 3: Write the short description**

Create `mo2-plugins/modlist_compare/NEXUS_SHORT_DESCRIPTION.txt` — a single line (one trailing newline is fine):

```text
Compare Mod Organizer 2 modlists without leaving MO2. Export any profile to JSON, then generate coverage, diff, and changelog reports between two lists - see what a list is missing, how load orders differ, and what changed between versions. Same reports and file naming as the meteoric-modlist-tools CLI.
```

- [ ] **Step 4: Write the full description**

Create `mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.bbcode` with exactly this content (prose is a first pass for the author to edit):

```text
[size=4][b]Modlist Compare[/b][/size]

[b]An MO2 plugin for comparing modlists - see what another list has that yours doesn't, side by side, without leaving Mod Organizer 2.[/b]

[size=3][b]What It Does[/b][/size]
Adds a [b]Modlist Compare[/b] submenu to MO2's Tools menu with two entries: one exports the active profile's modlist to JSON, and one generates reports comparing any two lists - an exported JSON file, your current profile, or one of each. The reports are the same ones the [url=https://github.com/imightbemeteor/meteoric-modlist-tools]meteoric-modlist-tools[/url] command-line tools produce, from the same code, with the same file naming, so plugin output and CLI output are interchangeable.

[size=3][b]Key Features[/b][/size]
[list]
[*][b]Coverage report[/b] - What a target list is missing or behind on compared to a source list, with per-mod states and a percent-covered badge (HTML)[/*]
[*][b]Diff report[/b] - Both lists' full ordering side by side, colour-coded, including moves (HTML)[/*]
[*][b]Changelog[/b] - Added, removed, and updated mods between two versions of a list (markdown)[/*]
[*][b]Live profile support[/b] - Compare against your current profile directly, no export step needed[/*]
[*][b]Smart matching[/b] - Mods are matched across lists by Nexus IDs, plugin files, and names, so renames and merges are handled[/*]
[*][b]Responsive UI[/b] - Generation runs behind a progress dialog with live percent and cancel; MO2 stays usable throughout[/*]
[/list]

[size=3][b]How to Use[/b][/size]
[list=1]
[*][b]Export a list[/b] - Tools, Modlist Compare, Export Modlist to JSON saves the active profile[/*]
[*][b]Open Generate Reports[/b] - Pick List 1 (source/old) and List 2 (target/new): a JSON file or the current profile[/*]
[*][b]Choose reports[/b] - Any combination of Coverage, Diff, and Changelog, plus a destination folder[/*]
[*][b]Generate[/b] - Reports are written to the destination; Open Folder takes you straight there[/*]
[/list]

[size=3][b]Requirements[/b][/size]
[list]
[*]Mod Organizer 2 [b]2.5.0 or newer[/b] (the PyQt6-based Python runtime)[/*]
[*]Nothing else - no third-party Python packages[/*]
[/list]

[size=3][b]Known Limitations[/b][/size]
[list]
[*]The coverage ignore list is read but not edited from the plugin; use the CLI's serve mode or a text editor to change it[/*]
[*]Report generation vendors its modules under plain names (modlist_utils and friends); another Python plugin shipping a same-named top-level module could collide - none known[/*]
[/list]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd tools && python -m unittest test_nexus_description -v`
Expected: both tests PASS

- [ ] **Step 6: Run the full tools suite**

Run: `cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin test_nexus_description -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.bbcode mo2-plugins/modlist_compare/NEXUS_SHORT_DESCRIPTION.txt tools/test_nexus_description.py
git commit -m "feat: drafted Nexus description source files with limit test"
```

```json:metadata
{"files": ["mo2-plugins/modlist_compare/NEXUS_DESCRIPTION.bbcode", "mo2-plugins/modlist_compare/NEXUS_SHORT_DESCRIPTION.txt", "tools/test_nexus_description.py"], "verifyCommand": "cd tools && python -m unittest test_nexus_description -v", "acceptanceCriteria": ["both source files exist with drafted content", "test fails on missing/empty file, embedded newline, or >350 chars with count in message", "full tools suite green"], "modelTier": "mechanical"}
```

---

### Task 3: Documentation updates

**Goal:** CLAUDE.md's test command includes the new module; the plugin README's Development section documents the description workflow.

**Files:**

- Modify: `CLAUDE.md` (the Testing section's `python -m unittest ...` command)
- Modify: `mo2-plugins/modlist_compare/README.md` (Development section, between the packaging paragraph and the test-running paragraph)

**Acceptance Criteria:**

- [ ] CLAUDE.md's tools test command lists `test_nexus_description`.
- [ ] Plugin README Development section has one paragraph naming both source files, the editor page, and the copy-back workflow.

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
The plugin's Nexus Mods page is maintained in the repo:
[NEXUS_SHORT_DESCRIPTION.txt](NEXUS_SHORT_DESCRIPTION.txt) (the mod-card
blurb — one line, max 350 characters, enforced by `test_nexus_description`)
and [NEXUS_DESCRIPTION.bbcode](NEXUS_DESCRIPTION.bbcode) (the full
description, raw Nexus BBCode). Open `tools/nexus_bbcode_editor.html` in a
browser to edit with a live preview — load or paste the files, tweak, then
copy each field back to its file and into the matching Nexus form field.
The preview is an approximation; Nexus's own preview is the final authority.
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
{"files": ["CLAUDE.md", "mo2-plugins/modlist_compare/README.md"], "verifyCommand": "cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin test_nexus_description -v", "acceptanceCriteria": ["CLAUDE.md test command includes test_nexus_description", "plugin README Development section documents both files, the editor page, and the copy-back workflow"], "modelTier": "mechanical"}
```
