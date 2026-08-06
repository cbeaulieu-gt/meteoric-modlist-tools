---
description: Launch the interactive coverage server (click-to-ignore) for a SOURCE list vs a TARGET list.
argument-hint: <source> <target> [<base>]  — partial names ok (newest wins); base = the OLD base list for a base-update worklist
allowed-tools: Bash(python:*), Glob
---

Launch the live coverage server so I can review `<source>` against my target list and click mods to
mark them "ignore". `$ARGUMENTS` holds the list names (source first, target second, and an optional
third — the OLD base list, for a base-update worklist).

## Resolve the toolkit root first

The scripts and the data live in different places. Resolve `TOOLS` in this order and stop at the
first hit:

1. `$MODLIST_TOOLS_ROOT`, if set — the user pointing at a checkout from elsewhere.
2. `$CLAUDE_PLUGIN_ROOT`, if set — this command running as an installed Claude Code plugin.
3. The current directory, if `tools/generate_coverage.py` exists under it.

If none resolve, stop and tell the user to set `$MODLIST_TOOLS_ROOT` to the directory where this
toolkit is checked out. Do not guess. Quote the path when you use it — it can contain spaces.

Lists are always resolved from `lists/` **relative to the current directory**, which is the user's
modlist workspace, not the toolkit.

## Then

1. **Parse two or three list tokens** from `$ARGUMENTS`. Split on whitespace, honoring quotes — so
   `1.1 1.0` is two tokens, and `"Example List 1.1" "Example List 1.0"` is two tokens. The first
   token is the **source**, the second is the **target**, and an optional third token is the
   **base** (the OLD base list, for `--base` mode). If there are fewer than two tokens, stop and
   show the usage (`<source> <target> [<base>]`), then Glob `lists/*.json` and list the available
   lists so I can pick.

2. **Resolve each token to a file** in `lists/`. Glob `lists/*.json` and, for each token,
   case-insensitively substring-match the token against the file's base name. Within a single
   matching *family* (same name minus the trailing version, e.g. `Example List 1.0` vs
   `Example List 1.1`), pick the **newest version**. Resolve the optional base token the same way.
   Then:
   - If a token matches **nothing**, stop and report it (and list the available lists).
   - If a token matches **genuinely different lists** (e.g. the token `example` could match both
     `Example List 1.1` and, if your `lists/` folder also had a spinoff like
     `Example List 1.1 - PBR Edition`, that list too), don't guess — ask me which one.
   - Otherwise report the resolved files so I can see exactly what was chosen, e.g.
     `source -> lists/Example List 1.1.json`, `target -> lists/Example List 1.0.json`, and, if a
     base was given, `base -> lists/Example List 0.9.json` (a hypothetical older export, used for
     a rebase run).

3. **Launch the server in the background** (it blocks until stopped, so it must NOT run in the
   foreground):

   ```bash
   python "$TOOLS/tools/generate_coverage.py" "lists/<source>.json" "lists/<target>.json" -o output/ --serve
   ```

   If a base was resolved, append `--base "lists/<base>.json"` to that command:

   ```bash
   python "$TOOLS/tools/generate_coverage.py" "lists/<source>.json" "lists/<target>.json" -o output/ --serve --base "lists/<base>.json"
   ```

   Run it as a background process. The server prints
   `Coverage server running at http://127.0.0.1:<port>/` to stderr and auto-opens the browser.

4. **Report back:** the URL (read the actual port from the server's output — it auto-increments from
   8000 if busy), that the browser should have opened, and that:
   - Clicking any mod row toggles it as *ignored*; the change is written immediately to
     `output/<target>/.coverage-ignore.txt` and persists for next time.
   - With a base, the page is the **Base Update Coverage** worklist (only mods changed in the base
     update); re-exporting the target and refreshing shrinks it toward done.
   - When I'm done, I can say **"stop the coverage server"** and you'll terminate the background
     process.

Notes:
- The target's ignore file is per-target and global: marks made here also grey that mod in every
  other coverage report against the same target.
- If I pass only one token, treat it as an error (both source and target are required) — don't
  assume a default target.
- `allowed-tools` is `Bash(python:*)` rather than a literal script path because the toolkit root is
  resolved at runtime.
