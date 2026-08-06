---
description: Regenerate every report related to <list name> — its own folder plus source/base references in other folders.
argument-hint: [list name]  — e.g. "Example List 1.1"; omit to list available folders
allowed-tools: Bash(python:*)
---

Regenerate every modlist comparison report **related to** the list named in `$ARGUMENTS`.

## Resolve the toolkit root first

The scripts and the data live in different places. Resolve `TOOLS` in this order and stop at the
first hit:

1. `$MODLIST_TOOLS_ROOT`, if set — the user pointing at a checkout from elsewhere.
2. `$CLAUDE_PLUGIN_ROOT`, if set — this command running as an installed Claude Code plugin.
3. The current directory, if `tools/generate_coverage.py` exists under it.

If none resolve, stop and tell the user to set `$MODLIST_TOOLS_ROOT` to the directory where this
toolkit is checked out. Do not guess.

Quote the path when you use it — it can contain spaces.

## Run it

```bash
python "$TOOLS/tools/regenerate.py" "$ARGUMENTS"
```

`--lists` and `--output` default to `lists/` and `output/` **relative to the current directory**,
which is the user's modlist workspace — not the toolkit. Leave them alone unless the user asks
otherwise.

Notes:
- `$ARGUMENTS` is the list name. It may contain spaces, so keep it quoted as a single argument.
- If `$ARGUMENTS` is empty, the command prints the available report folders instead — use that to
  discover valid names.
- **Scope: everything related to the list.** That's its own `output/<list name>/` folder (reports
  where it is the target) **plus** reports in other lists' folders where it is the *source* or the
  *rebase base*.
- Reports run **in parallel** by default (rolling pool, capped at `min(report count, CPU count)`);
  progress lines arrive in completion order. Cross-folder jobs show as `<source>  ->  <target>`.
  Add `-j N` to change the cap or `-j 1` to run sequentially.
- Add `--dry-run` to preview the plan without writing anything.
- `allowed-tools` is `Bash(python:*)` rather than a literal script path because the toolkit root is
  resolved at runtime.

Relay the tool's per-report `+` (success) / `x` (failure) summary back to me, and surface any `!` warnings or a non-zero exit.
