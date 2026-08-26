# Nordic Souls PBR — Release Changelog Publishing Workflow

This describes how detailed per-release reports (changelog / diff / coverage / load order) are published to the
`SkrubbySkrubInAShrub/nordic-souls-PBR` GitHub repo and linked from `CHANGELOG.md`, so the process can be scripted
or turned into a GitHub Action from the generator project.

Repo: https://github.com/SkrubbySkrubInAShrub/nordic-souls-PBR
Default branch: `main`
GitHub Pages: **enabled**, source = "Deploy from a branch", branch `main`, folder `/ (root)`
Pages base URL: `https://skrubbyskrubinashrub.github.io/nordic-souls-PBR/`

---

## 1. Repo layout

```
nordic-souls-PBR/
├── CHANGELOG.md                      # human-facing changelog, one section per release
├── changelog/
│   └── v<X.Y.Z>/                     # one folder per release, "v" prefix REQUIRED
│       ├── changelog.md              # generator output: full added/removed/updated lists
│       ├── coverage.html             # generator output: coverage report
│       └── diff.html                 # generator output: modlist diff
└── loadorder/
    └── v<X.Y.Z>/                     # one folder per release, "v" prefix REQUIRED
        ├── loadorder.txt             # MO2 profile files, copied verbatim
        ├── modlist.txt
        ├── plugingroups.txt
        └── plugins.txt
```

Published so far: `changelog/v1.5.0`, `changelog/v1.6.0`, `loadorder/v1.5.0`.

### Why this structure
- GitHub **does not render `.html` files** in the repo browser (shows source). GitHub Pages does. So HTML reports get
  linked via the Pages URL; markdown/txt get linked via normal relative repo links (GitHub renders those natively).
- Fixed filenames + versioned folder = predictable, stable URLs. No spaces (avoids `%20` in URLs).
- Pages deploys the whole `main` branch from root, so **any file committed to `main` is immediately a Pages URL**.

---

## 2. File naming / renaming rules

The generator's native output convention is:

```
<folder named for the version being compared against>/
    <source list name>.changelog.md
    <source list name>.coverage.html
    <source list name>.diff.html
```

e.g. `1.6.0/NORDIC SOULS v3.0.1 - PBR Edition 1.5.0.diff.html`

On publish, this is mapped to:

| Generator output                          | Published path                          |
|-------------------------------------------|-----------------------------------------|
| `<ver>/`  (no prefix)                     | `changelog/v<ver>/`                     |
| `<anything>.changelog.md`                 | `changelog/v<ver>/changelog.md`         |
| `<anything>.coverage.html`                | `changelog/v<ver>/coverage.html`        |
| `<anything>.diff.html`                    | `changelog/v<ver>/diff.html`            |
| MO2 profile `loadorder.txt` etc.          | `loadorder/v<ver>/<same name>`          |

Rule of thumb for a script: strip everything before the final `.<kind>.<ext>` suffix; prefix the folder with `v` if
it isn't already. `<ver>` is the **new release version** (the folder name), not the source list name.

---

## 3. Generator `changelog.md` format (what a script can parse)

Observed structure of the generated `changelog.md`:

```markdown
# Modlist Changelog

## Summary                       # v1.5.0 used "## Summary", v1.6.0 used "### Summary" — handle both

- **Not Save Safe!**             # OPTIONAL free-text highlight bullets, if present
- **Updated to NS 3.1.1** - ...  # OPTIONAL
- **Added:** 182 mods            # ALWAYS present
- **Removed:** 58 mods           # ALWAYS present
- **Updated:** 157 mods          # ALWAYS present

## Added Mods
### <Category>                   # category = MO2 separator name
- Mod Name
...

## Removed Mods
### <Category>                   # (v1.3.x output had no categories here; v1.5.0+ does)
- Mod Name
...

## Updated Mods
- Mod Name: <old> → <new>        # U+2192 arrow
...
```

Machine-extractable fields:
- `added`, `removed`, `updated` counts → regex `\*\*(Added|Removed|Updated):\*\* (\d+) mods`
- Save-safety → presence of a bullet matching `/save.?safe/i` in Summary. If absent, the CHANGELOG entry
  still needs a save-safety line — a human must decide (see §5).
- Any other bold bullets in Summary are author-written highlights and can be carried straight into the entry.

---

## 4. `CHANGELOG.md` entry format

`CHANGELOG.md` has a banner + nav header, then a `## Contents` list, then one `## Version X.Y.Z` section per
release, **newest first**. A new release requires two edits:

### 4a. Contents list — prepend a line

```markdown
## Contents

- [Version 1.6.0](#version-160)      # <-- new line, anchor = "version-" + version with dots removed
- [Version 1.5.0](#version-150)
- [Version 1.3.1](#version-131) a.k.a. 1.4.0
- [Version 1.3.0](#version-130)
```

### 4b. New section — insert immediately after the Contents list, before the previous newest `## Version`

Template (`{{ }}` = fill in):

```markdown
## Version {{VERSION}}

**This update is {{not save-safe | probably not save-safe | save-safe}}.**

### {{Highlight Category 1}}
- {{human-written highlight}}
- {{human-written highlight}}

### {{Highlight Category 2}}
- {{...}}

### Summary
- **Added:** {{ADDED}} mods
- **Removed:** {{REMOVED}} mods
- **Updated:** {{UPDATED}} mods

### Detailed Reports
- [Full changelog](changelog/v{{VERSION}}/changelog.md) — complete added/removed/updated mod lists
- [Diff report](https://skrubbyskrubinashrub.github.io/nordic-souls-PBR/changelog/v{{VERSION}}/diff.html) — full modlist diff
- [Coverage report](https://skrubbyskrubinashrub.github.io/nordic-souls-PBR/changelog/v{{VERSION}}/coverage.html) — coverage details
- [Load order](loadorder/v{{VERSION}}/) — load order, modlist, plugin groups, and plugins files
```

Style notes (match the existing file, don't "fix" it):
- Headings are immediately followed by their list — **no blank line** between `### Heading` and the first `- item`.
  markdownlint complains (MD022/MD032/MD024); that's the established style, ignore it.
- Bullets have no trailing periods (mostly).
- Highlight category names used so far: Core, Community Shaders, Faster Load Times, Characters, PBR Updates,
  Quests and Content, Gameplay, Gameplay Overhauls, Horses and Followers, Animations, Weapons and Armors, Fixes,
  Removals. Pick whatever fits; 3–7 sections is typical.
- Links: `.md` and folders use **relative repo paths**; `.html` uses the **absolute Pages URL**.
- Omit the Load order line if `loadorder/v{{VERSION}}/` doesn't exist yet (v1.6.0 currently omits it).
- Older entries (≤1.3.1) embedded the full mod lists in a `<details>` block. That's superseded by the linked
  `changelog.md` — don't embed the lists anymore.

---

## 5. What is mechanical vs. needs a human

| Step                                                  | Automatable? |
|-------------------------------------------------------|--------------|
| Rename/copy generator output into `changelog/vX.Y.Z/` | Yes          |
| Copy MO2 profile files into `loadorder/vX.Y.Z/`       | Yes          |
| Add Contents line                                     | Yes          |
| Insert section skeleton with Summary counts + links   | Yes          |
| Save-safety line                                      | Only if the generator Summary states it; otherwise human |
| Highlight sections (the "what actually changed" prose)| **Human** (or LLM-assisted, then reviewed). The v1.5.0 CS/ENB + CRDW blurbs came from the list author, not from the diff. |
| Commit / push / PR                                    | Yes          |
| Verify Pages URLs resolve                             | Yes          |

A good split: the script does everything in the "Yes" rows and leaves a clearly marked
`<!-- TODO: write highlights -->` placeholder (or a stub with the generator's Summary bullets) for the human.

---

## 6. Git workflow used

Either of these has been used; both are fine:

**A. Branch + PR** (used for v1.5.0, the first time the structure was introduced)
```
git checkout -b ns-pbr-<ver-no-dots>-update      # e.g. ns-pbr-150-update
# add files, edit CHANGELOG.md
git add changelog/v<ver> loadorder/v<ver> CHANGELOG.md
git commit -m "Add v<ver> detailed reports and CHANGELOG entry"
git push -u origin ns-pbr-<ver-no-dots>-update
gh pr create --base main --head ns-pbr-<ver-no-dots>-update --title "v<ver> changelog: detailed reports + CHANGELOG entry"
# merge, then: git checkout main && git pull
```

**B. Direct to main** (used for v1.5.0 load order and for v1.6.0 — routine additions)
```
git pull
# add files, edit CHANGELOG.md
git add changelog/v<ver> CHANGELOG.md
git commit -m "Add v<ver> detailed reports and CHANGELOG entry"
git push
```

Commit messages used:
- `Add detailed v<ver> changelog reports (changelog, coverage, diff)`
- `Add v<ver> entry to CHANGELOG.md with links to detailed reports`
- `Add v<ver> load order files and link them from the changelog`
- `Add v<ver> detailed reports and CHANGELOG entry` (combined)

---

## 7. Verification

After push, Pages rebuilds automatically (typically < 2 minutes). Check:

```sh
for f in diff coverage; do
  curl -s -o /dev/null -w "$f: %{http_code}\n" \
    "https://skrubbyskrubinashrub.github.io/nordic-souls-PBR/changelog/v<ver>/$f.html"
done
```

Expect `200`. A `404` immediately after push just means the build hasn't finished; retry. The relative
`changelog.md` / `loadorder/` links work the instant the commit is on `main`.

---

## 8. Automation ideas

**Option 1 — script in the generator project (simplest).**
After generating reports, the generator (or a post-step) does:
1. Clone/pull `nordic-souls-PBR`.
2. Copy + rename outputs per §2 into `changelog/v<ver>/` and `loadorder/v<ver>/`.
3. Parse counts from `changelog.md` (§3).
4. Inject the Contents line and section skeleton (§4) into `CHANGELOG.md` with a highlights placeholder.
5. Commit to a branch `ns-pbr-<ver>-update`, push, open a PR with `gh pr create`.
6. Human fills in highlights on the PR branch and merges.

**Option 2 — GitHub Action in `nordic-souls-PBR`.**
Trigger on `push` to `main` with paths `changelog/v*/changelog.md`. The action:
- Extracts `<ver>` from the path.
- If `CHANGELOG.md` has no `## Version <ver>` section, inserts the Contents line + skeleton (§4) with a
  `<!-- TODO: highlights -->` marker and commits back (or opens a PR).
- Optionally waits for the Pages deployment (`actions/deploy-pages` isn't used here — it's branch-deploy —
  so poll the URL from §7 instead) and fails loudly if `diff.html`/`coverage.html` don't return 200.

Either way, the only content that genuinely can't be generated from the diff is the highlight prose and the
save-safety call (when the generator doesn't state it). Everything else is deterministic string work.

---

## 9. Gotchas

- Folder **must** be `v`-prefixed. v1.6.0 was initially dropped as `changelog/1.6.0/` and had to be renamed.
- Don't leave spaces in published filenames — the generator's default names contain them.
- Anchors in the Contents list are `#version-<digits only>` (`1.6.0` → `#version-160`).
- Pages serves the **entire** repo from root; anything committed to `main` is publicly fetchable at the Pages URL.
  Fine for this repo (it's all public modlist docs), but don't commit anything you wouldn't want served.
- The `Load order` link line should only be present when the folder exists, or it'll 404 on GitHub.
- `<details>`-embedded mod lists in old entries are legacy; new entries link out instead.
