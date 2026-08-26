# Meteoric Modlist Tools - Claude Assistant Guide

What the assistant needs to act correctly in this repo: invariants, commands, and pointers. User-facing documentation is the [README](README.md) — tool arguments, coverage states, the `% covered` formula, serve mode, base-update mode, the matching waterfall, and slash-command root resolution are all documented there and not restated here. **Read the relevant README section before changing that behavior.**

## Project Purpose

A small toolkit for **comparing Mod Organizer 2 (MO2) modlists**. Given two JSON exports of a modlist, it generates human-readable changelogs, side-by-side diffs, and "coverage" reports so you can see how lists differ and what one list could pull from another. The lists are exported from MO2 with the bundled exporter plugin, then fed to the standalone Python scripts in `tools/`.

## Guiding Principle

The principle "Everything should be made as simple as possible, but not simpler" guides all decisions in this codebase. When weighing options:

- **Prefer the simpler solution** that fully solves the problem
- **Resist adding complexity** for hypothetical future needs
- **Stop when it works** — don't polish beyond what's needed
- **But don't oversimplify** — essential complexity exists for good reasons

## Conversational Style

Say more with less. Concise means dense, not short: communicate all the information, spend no words performing it. Cut by omitting non-information — never by omitting content. Depth, reasoning, caveats, and evidence are content; sentences that announce, restate, or dramatize them are not.

### Answer shape

- Lead with the answer. The first sentence gives what the reader would ask for as "just the TLDR"; reasoning and detail follow for those who want them.
- Fit the form to the content. Enumerable content gets bullets; multi-part answers get headers; a simple answer is a paragraph. Structure exists to aid scanning — use it when it does, skip it when a header would sit over a single short paragraph.
- Every bullet earns its line. No one-item lists, no sub-bullets restating their parent, no padding a list so it looks complete.
- End when the content ends. On task turns, close with the concrete next step if one exists — a next step is information, not a closer.

### No preamble, no recap, no closers

Named filler patterns, banned. Each entry shows the inflated form and the fix — when about to write the pattern on the left, write the fix instead:

- **Announcement** — ✗ "Here's the thing:" / "Let's break this down." ✓ Start with the content.
- **Emphasis coda** — ✗ "The cache is stale — and that's the real problem." ✓ End at the fact: "The cache is stale."
- **Not-X-but-Y reframe** — ✗ "It's not just a bug — it's an architecture smell." ✓ State Y once, plainly.
- **Importance adverbs** — ✗ "Crucially, the migration drops the column." ✓ Show importance by its consequence, or drop the adverb.
- **Echo restatement** — ✗ "In other words, …" ✓ Trust the first sentence; delete the second.
- **Closing recap** — ✗ "So, to summarize…" ✓ The opening already was the summary. Stop.
- **Validation** — ✗ "Great question!" / "You're absolutely right." ✓ Answer.
- **Hedging stack** — ✗ "generally, in most cases, it typically…" ✓ One qualifier, chosen deliberately.
- **Significance narration** — ✗ "…which matters because correctness matters." ✓ Concrete consequence or nothing.
- **Tangent** — ✗ "While I was in there, I noticed…" (when it changes nothing for the reader) ✓ Mention a side observation only if it changes what the reader does next; give it one clause, or drop it.

### Decisions

Recommend, don't survey. One recommendation with the reason; name an alternative only when the tradeoff is real and close. Settled decisions stay settled — don't re-litigate them.

### Reporting

Report faithfully. State failures plainly with the evidence; name skipped steps as skipped. "Done" means verified — no hedging, no "should work."

### What the reader can actually see

The reader sees the message that ends your turn — not your thinking, raw tool results, or (in the VS Code extension) text written before a tool call. Everything that matters goes in the final message: the answer, findings, caveats, anything that surfaced only mid-turn. Text between tool calls stays to short status notes.

## Project Structure

The three generators and `modlist_utils.py` live together in `tools/` so the scripts can import the shared module as a sibling (`from modlist_utils import ...`); `tools/` also holds `nexus_bbcode_editor.html`, the standalone editor page for the plugin's Nexus description, which nothing imports and you open directly in a browser. `lists/` (your inputs) and `output/` (your reports) are shared by all three tools and are gitignored — only their `.gitkeep` placeholders are tracked. `examples/` ships the synthetic fixtures and their committed sample output instead, so the toolkit is runnable and testable without any real modlist data.

## JSON Format

All modlist files follow the format documented in [FORMAT_SPECIFICATION.md](mo2-plugins/modlist_compare/FORMAT_SPECIFICATION.md).

## The Tools

All three report generators import shared logic from [modlist_utils.py](tools/modlist_utils.py) (data loading, mod matching, version cleaning, name normalization). No third-party dependencies — standard library only.

- **`generate_changelog.py`** — markdown changelog: added/removed mods (grouped by section) and version updates. It does not report moves — that's the diff tool.
- **`generate_coverage.py`** — what a **target** list is missing or behind on versus a **source**: per-mod states with glyphs, a `% covered` badge, interactive `--serve` mode (click-to-ignore), and `--base` update mode for derived lists. Design: [docs/design/2026-07-03-base-update-coverage-design.md](docs/design/2026-07-03-base-update-coverage-design.md).
- **`generate_diff.py`** — side-by-side HTML of both lists' full ordering; the only tool that reports moves. Section matching waterfall: exact name → content-based (≥50% of an old section's matched mods landed in one new section) → fuzzy name (SequenceMatcher ≥ 0.70), all case-insensitive (see [Name Case](#name-case)).
- **`tools/regenerate.py`** — re-runs every *existing* report that references a list (as target, source, or rebase base) by parsing report filenames back into generator arguments; reports run as parallel subprocesses (`-j/--jobs` to cap). It never creates new report combinations. Design: [docs/design/2026-06-17-regenerate-reports-design.md](docs/design/2026-06-17-regenerate-reports-design.md).
- **`tools/release_reports.py`** — the GitHub Action's engine: pairs the two newest versioned exports in a consumer repo's `lists/`, writes `changelog/v<ver>/{changelog.md,diff.html,coverage.html}`, and splices a `## Version <ver>` skeleton into `CHANGELOG.md`. Wrapped by the root `action.yml` (composite; branch + PR via the runner's `git`/`gh`). Design: [docs/superpowers/specs/2026-08-25-release-reports-action-design.md](docs/superpowers/specs/2026-08-25-release-reports-action-design.md); the consumer-side conventions came from [docs/design/2026-08-25-nordic-souls-release-workflow.md](docs/design/2026-08-25-nordic-souls-release-workflow.md).

Cross-cutting facts to know before editing:

- **Output naming** (`<dir>/<second-list>/<first-list>.<type>.<ext>`) is produced by `modlist_utils.resolve_output_path` and *parsed back* by `regenerate.py`; the MO2 plugin writes through the same function. Changing the convention touches all three.
- **Ignore file** (`output/<target>/.coverage-ignore.txt`, keyed by normalized name): static runs and `/regenerate` only **read** it; only `--serve` **writes** it.
- **Major separators** (dash-wrapped names like `---------- BASE ----------`) render as full-width divider bands in both HTML reports; `is_major_separator` / `major_display_name` live in [modlist_utils.py](tools/modlist_utils.py) and are shared by both generators.
- **Slash commands** `/regenerate` and `/serve-coverage` are defined in `.claude/commands/*.md`. Each resolves the toolkit root itself (`$MODLIST_TOOLS_ROOT` → `$CLAUDE_PLUGIN_ROOT` → the current directory), while `lists/` and `output/` always resolve against the current directory (the user's modlist workspace), never the toolkit root. If a command misbehaves, start there.

### Modlist Compare plugin — `mo2-plugins/modlist_compare/`

The MO2 plugin that both produces the JSON exports and runs the same three generators from inside MO2 (requires MO2 2.5.0+, PyQt6). User docs: [the plugin README](mo2-plugins/modlist_compare/README.md); architecture: [docs/design/2026-08-06-modlist-compare-plugin-design.md](docs/design/2026-08-06-modlist-compare-plugin-design.md). Use the `mo2-api` skill for any plugin work.

- [`exporter_core.py`](mo2-plugins/modlist_compare/exporter_core.py) and [`report_runner.py`](mo2-plugins/modlist_compare/report_runner.py) are Qt-free, and `mobase` is only imported lazily inside `export_modlist` — so both are unit-tested outside MO2.
- `report_runner.py` calls each generator's pure `generate(...) → str` entry function (the same one `main()` uses) and writes through `resolve_output_path`, so plugin and CLI output naming can never drift.
- **Generate Reports…** ([`dialog.py`](mo2-plugins/modlist_compare/dialog.py)) runs generation on a worker thread behind a modal progress dialog (live percent, per-report label), so MO2 stays responsive; cancel (button, Esc, or the window's X) stops at the next checkpoint — already-written reports stay, the in-progress one is discarded, remaining live-profile exports are skipped. The dialog carries inline hints and per-control tooltips.
- **Packaging:** run `python tools/package_plugin.py` **before testing or shipping the plugin** — it vendors the five generator modules into `_vendor/` and builds `dist/modlist-compare-<version>.zip`. `_vendor/` (except its `__init__.py`) and `dist/` are gitignored; `report_runner` imports the vendored copies, and `_vendor/__init__.py` raises a loud `ImportError` when the folder is unpopulated.

## The `examples/` smoke test

`examples/lists/` holds two small synthetic fixtures (no real modlist data); `examples/reports/` holds their committed changelog/diff/coverage output, including a `.coverage-ignore.txt` that deliberately ignores one mod (`Sky Idles`) to demonstrate the Ignored state — see the README's worked example for the numbers.

That committed output must stay reproducible: regenerating it from the fixtures must be a no-op.

```bash
python tools/regenerate.py "Example List 1.1" --lists examples/lists --output examples/reports
git diff --exit-code examples/reports
```

The regenerate run should print no changes and the `git diff` should exit `0`. If it doesn't, either a generator's output changed and `examples/reports/` needs to be re-committed deliberately, or something regressed. `tools/test_examples.py` also locks in the comparison cases these fixtures cover (added/removed/updated/moved mods, merges, renames, case-only differences) as unit tests, independent of the committed HTML/markdown.

## Mod Matching Logic

`modlist_utils.py` matches the same mod across lists with a **waterfall** (priority order):

1. **Per-page assignment** — a Nexus `id` identifies a *page* that can host many distinct mods, so mods sharing an `id` are matched as a group, every source/target pair scored and assigned **best-first** so a weaker signal can never steal a target that a stronger pairing wants. Signal priority: shared `(modid, fileid)` from `installed.files` → **exact strict name** → an identical `installationFile` archive (compared whole — never parsed — after lowercasing and stripping a leading `1_`-style rename prefix) → fuzzy name ≥ `--min-confidence`. A page hosting a single mod in each list matches **blindly**, so a plain rename is still caught. Exact name deliberately outranks the archive match: a mod whose archive happens to be another file on the page can't beat a clean name-to-name pairing.
2. **Plugin-based** — compare `plugins` arrays as sets (exact, or ≥50% overlap). Handles merged mods.
3. **Strict normalized name** — strip all non-alphanumeric, case-insensitive.
4. **Fuzzy name** — `difflib.SequenceMatcher` with the configurable `--min-confidence` threshold.

Pure-waterfall matching only — there are no ignore/alias/compendium config files.

## Name Case

**MO2 is case-insensitive about mod, separator, and plugin names** — one list cannot hold both `Core` and `CORE`, and the same separator can be spelled differently in two exports. So **every name equality test in this repo is case-insensitive**; a recapitalized name must never read as one added plus one removed.

- `modlist_utils.name_key(name)` — the identity key: `strip().casefold()`, nothing else. Use it for any dict key, set member, or `==` between two names (`same_name(a, b)` is the shorthand). Distinct from `normalize_name` / `normalize_name_strict`, which *also* strip version and edition suffixes — those are for fuzzy matching, `name_key` for identity.
- Separator names go through `name_key` everywhere sections are keyed, grouped, or matched, in all three generators; mod names, plugin filenames, and `installationFile` are lowercased by their own normalizers.
- Where names are only *displayed*, keep the source list's own spelling — key on `name_key`, but show the raw name. Case variants collapsing onto one entry keep the first spelling seen.

## Version Cleaning

Raw `meta.ini` version strings are normalized to MO2 display format by `modlist_utils.clean_version` (see its tests for the full case list). Empty/missing versions become `Unknown` and are excluded from "Updated" sections, since `Unknown → X.Y` isn't a meaningful version change.

## Testing

Run the unit tests from inside `tools/`:

```bash
cd tools && python -m unittest test_modlist_utils test_generate_coverage test_generate_diff test_generate_changelog test_coverage_ignore test_coverage_server test_regenerate test_examples test_package_plugin test_nexus_description test_release_reports -v
```

The plugin's own tests (`exporter_core`, `report_runner`) run outside MO2 — no `mobase`, no Qt — from the repo root:

```bash
python -m unittest discover -s mo2-plugins/modlist_compare -t mo2-plugins -p "test_*.py" -v
```

When changing matching or version logic in `modlist_utils.py`, keep these green and add cases for new behavior. `test_examples.py` runs against the fixtures in `examples/lists/` — if you change those fixtures, re-run the [smoke test](#the-examples-smoke-test) above and re-commit `examples/reports/` deliberately.

## Superpowers driving rules

Project-local amendments to the superpowers plan workflow live in [docs/superpowers/driving-rules.md](docs/superpowers/driving-rules.md) — read it before coordinating a plan run. Its core rule: a subagent question that a seasoned engineer would just handle goes to the `jarl` agent (delegated arbitration, [.claude/agents/jarl.md](.claude/agents/jarl.md)) before interrupting the user; only irreversible actions, scope changes, and plan-marked user gates go straight to the human.

## Working Notes

- **Always read** the relevant JSON exports before reasoning about a comparison.
- **Flag ambiguous matches** — name-based matches can be wrong; explain confidence.
- `general.version` is the installed version; `general.newestVersion` may be stale.
- `active: false` mods are installed but disabled.
- Keep generated reports in `output/` and inputs in `lists/` — both gitignored; only `examples/lists/` and `examples/reports/` are tracked.
