# Release Reports GitHub Action — Design

A composite GitHub Action, published from this repo, that a modlist repo installs so that committing a new
modlist JSON export automatically produces the per-release reports and a `CHANGELOG.md` entry skeleton, delivered
as a pull request. Reference consumer: `SkrubbySkrubInAShrub/nordic-souls-PBR`. The manual process it replaces is
described in [docs/design/2026-08-25-nordic-souls-release-workflow.md](../../design/2026-08-25-nordic-souls-release-workflow.md).

## Goals

- A consumer repo commits `lists/<name> <ver>.json`; a PR appears with `changelog/v<ver>/{changelog.md,
  coverage.html, diff.html}` and a `CHANGELOG.md` entry containing the counts, report links, and clearly marked
  TODOs for the human-written parts (save-safety call, highlight prose).
- Output is byte-identical to what the three generators produce from the CLI — the action is packaging, not a
  fourth generator. Verified: regenerating nordic-souls-PBR's published v1.6.0 reports from the 1.5.0/1.6.0 exports
  reproduces them exactly (differences observed were only in mods that changed in a later re-export).
- No third-party actions; runner-provided `python3`, `git`, `gh` only. The toolkit is stdlib-only, so there is no
  install step.

## Non-goals

- Copying MO2 profile files into `loadorder/v<ver>/` — they are not in the export or the repo.
- Writing highlight prose or deciding save-safety — always a human; the skeleton carries `<!-- TODO -->` markers.
- Multi-list repos. `lists/` holds exactly one modlist's exports (see Pairing).
- Pages deployment. Consumers use "Deploy from a branch" (`main`, `/`), so merging the PR *is* the deploy.
- A "commit directly to main" mode. PR only.

## Consumer contract

```
<consumer repo>/
├── lists/                     # one modlist, one file per release; trailing version token before .json
│   ├── NORDIC SOULS v3.1.1 - PBR Edition 1.5.0.json
│   └── NORDIC SOULS v3.2.0 - PBR Edition 1.6.0.json
├── changelog/v<ver>/          # written by the action: changelog.md, coverage.html, diff.html
├── loadorder/v<ver>/          # optional, maintained by hand; linked only when present
└── CHANGELOG.md               # ## Contents list + one ## Version X.Y.Z section per release, newest first
```

Starter workflow (documented in this repo's README under a new **GitHub Action** section):

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
          pages-url: https://skrubbyskrubinashrub.github.io/nordic-souls-PBR/
```

## Components

### `tools/release_reports.py` (new; stdlib only; unit-tested)

```
release_reports.py [--lists lists] [--repo .] [--pages-url URL] [--changelog-file CHANGELOG.md] [--force]
```

Behavior, in order:

1. **Discover versions.** Every `*.json` directly in `--lists`. The version is the trailing token matching
   `v?(\d+(?:\.\d+)*)` immediately before `.json`, compared as a tuple of ints. Files without a trailing version are
   ignored with a notice. Earlier tokens in the name (e.g. the `v3.2.0` in `NORDIC SOULS v3.2.0 - PBR Edition
   1.6.0`) are not considered — the base name changes between releases, so only the trailing token identifies the
   release. Expected forms (all may coexist): `Meteoric 0.1.0.json` → 0.1.0; `NORDIC SOULS v3.2.0 - PBR Edition
   1.6.0.json` → 1.6.0; `v2.0.2.json` / `2.0.2.json` → 2.0.2; `my-list_1.10.json` → 1.10 (sorts after 1.9);
   `My List.json` → ignored.
2. **Pair.** Newest file = new list, second-newest = old list. Fewer than two versioned files → print a notice, exit 0.
3. **Skip if done.** If `changelog/v<ver>/` exists and `--force` is not given → print a notice, exit 0. This makes
   the script idempotent, so the trigger can be `push`, `workflow_dispatch`, or a re-run.
4. **Generate.** Call the generators' `generate(...)` entry functions (same ones `report_runner.py` and each
   `main()` use) and write:
   - `changelog/v<ver>/changelog.md` — `generate_changelog(old, new)`
   - `changelog/v<ver>/diff.html` — `generate_diff(old, new)`
   - `changelog/v<ver>/coverage.html` — `generate_coverage(source=old, target=new)` (what the new release dropped
     or is behind on, relative to the previous one — matching the published reports)
   Default `--min-confidence`. Fixed filenames, no spaces, `v`-prefixed folder.
5. **CHANGELOG.md skeleton.** If the file lacks a `## Version <ver>` heading:
   - Insert `- [Version <ver>](#version-<digits>)` as the first item of the `## Contents` list (`<digits>` = version
     with dots removed).
   - Insert the section below immediately after the Contents list (before the first existing `## Version`).
   - If the file has no `## Contents` list, prepend one.
   - If `## Version <ver>` already exists, leave the file untouched (even with `--force`; the reports regenerate,
     the hand-edited entry does not).
   Counts come from the generated `changelog.md` (`\*\*(Added|Removed|Updated):\*\* (\d+) mods`). HTML links use
   `--pages-url` + `changelog/v<ver>/<file>`; with no `--pages-url` they fall back to relative paths. The Load order
   line is emitted only when `loadorder/v<ver>/` exists. Style matches the existing file: no blank line between a
   heading and its list.

   ```markdown
   ## Version {ver}

   **This update is <!-- TODO: save-safe / probably not save-safe / not save-safe -->.**

   <!-- TODO: write highlights (### Category / - bullet sections) -->

   ### Summary
   - **Added:** {added} mods
   - **Removed:** {removed} mods
   - **Updated:** {updated} mods

   ### Detailed Reports
   - [Full changelog](changelog/v{ver}/changelog.md) — complete added/removed/updated mod lists
   - [Diff report]({pages}changelog/v{ver}/diff.html) — full modlist diff
   - [Coverage report]({pages}changelog/v{ver}/coverage.html) — coverage details
   - [Load order](loadorder/v{ver}/) — load order, modlist, plugin groups, and plugins files   (only if present)
   ```
6. **Report.** Print what was written. If `GITHUB_OUTPUT` is set, append `version=<ver>` (empty when nothing was
   generated) so the action can branch on it.

Exit non-zero only on real failures (unreadable JSON, generator exception, unwritable output).

### `action.yml` (new; composite; repo root)

Inputs: `lists` (default `lists`), `pages-url` (default empty), `changelog-file` (default `CHANGELOG.md`),
`token` (default `${{ github.token }}` — the run's own `GITHUB_TOKEN`; a PAT may be substituted if the PR should
trigger other workflows). Outputs: `version`, `pr-url`.

Steps:

1. `actions/checkout` of **this** repo at `${{ github.action_ref }}` into `${{ runner.temp }}/modlist-tools`
   (the consumer has already checked out its own repo into the workspace).
2. `python3 <tools>/release_reports.py --lists <lists> --repo . --pages-url <url> --changelog-file <file>`.
3. If `version` is non-empty: `git switch -c modlist-reports/v<ver>`, `git add changelog/v<ver> <changelog-file>`,
   commit as `github-actions[bot]` with message `Add v<ver> detailed reports and CHANGELOG entry`, push, then
   `gh pr create --base <default branch> --title "v<ver> changelog: detailed reports + CHANGELOG entry"` with a body
   listing the three reports and the two TODOs to fill in. If the branch already exists remotely, the step fails
   loudly rather than force-pushing.

`token` is exported as `GH_TOKEN` for `gh`; `actions/checkout` has already configured `git push` to use it. PRs
opened with `GITHUB_TOKEN` do not trigger other workflows, which is fine here. The consumer must grant
`permissions: contents: write, pull-requests: write` in the workflow **and** enable *Settings → Actions → General →
Workflow permissions → Read and write* plus *Allow GitHub Actions to create and approve pull requests*, or
`gh pr create` fails with 403.

### README section (new)

"GitHub Action": the consumer contract above, the filename/version table, the starter workflow, the inputs, the
prerequisites (Pages from branch; Actions workflow-permissions settings), and what the PR contains. Also a line in CLAUDE.md's tool list pointing at `release_reports.py` and `action.yml`.

## Error handling

| Situation | Behavior |
|---|---|
| < 2 versioned JSONs | notice, exit 0, no PR |
| `changelog/v<ver>/` exists, no `--force` | notice, exit 0, no PR |
| `## Version <ver>` already in CHANGELOG.md | reports written, CHANGELOG untouched, PR still opened |
| No `CHANGELOG.md` | created with a Contents list and the one section |
| Malformed JSON / generator error | traceback, non-zero exit, workflow fails |
| Remote branch `modlist-reports/v<ver>` exists | push fails, workflow fails (no force-push) |

## Testing

`tools/test_release_reports.py`, run with the rest of the suite from `tools/`:

- version token parsing (`1.6.0`, `v1.6.0`, `1.10`, no token, token only in the base name), int-tuple ordering
  (`1.10.0 > 1.9.0`)
- pairing picks newest/second-newest across three files; single-file and zero-file notices
- skip-if-exists and `--force`
- generation writes the three fixed filenames from `examples/lists/` and the `changelog.md` matches
  `generate_changelog` output exactly
- CHANGELOG insertion: fresh file, existing Contents + sections (new entry lands first and before the previous
  newest section), existing `## Version` untouched, anchor digits, Pages vs relative links, load-order line
  present/absent, count parsing
- `GITHUB_OUTPUT` line written when the env var is set

`action.yml` is verified end-to-end by installing the starter workflow in nordic-souls-PBR with the 1.5.0 and
1.6.0 exports and confirming the PR's reports match the published `changelog/v1.6.0/` (modulo the refreshed
export) — a user gate, since it touches another repo.
