# Nordic Souls PBR — Release Changelog Publishing Workflow

Notes on the consumer-side conventions of `SkrubbySkrubInAShrub/nordic-souls-PBR` that
`tools/release_reports.py` / `action.yml` implement (spec: `docs/superpowers/specs/2026-08-25-release-reports-action-design.md`).
Kept for the repo layout, the hand-written `CHANGELOG.md` entry format, and the gotchas; the manual process it describes is retired.

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

## 2. `CHANGELOG.md` entry format

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

## 3. Gotchas

- Folder **must** be `v`-prefixed. v1.6.0 was initially dropped as `changelog/1.6.0/` and had to be renamed.
- Don't leave spaces in published filenames — the generator's default names contain them.
- Anchors in the Contents list are `#version-<digits only>` (`1.6.0` → `#version-160`).
- Pages serves the **entire** repo from root; anything committed to `main` is publicly fetchable at the Pages URL.
  Fine for this repo (it's all public modlist docs), but don't commit anything you wouldn't want served.
- The `Load order` link line should only be present when the folder exists, or it'll 404 on GitHub.
- `<details>`-embedded mod lists in old entries are legacy; new entries link out instead.
