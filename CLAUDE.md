# everyday-screen — Claude context

See `README.md` for full project documentation: architecture, modules, design patterns, config, and deployment.

## This is a public repo

`epuronta/everyday-screen` is public on GitHub. Location and personal specifics never go into tracked files, commit messages or PR text: the home district, stop names, weather station names, anything that pins down where the user lives. Write generically instead. "The configured place", "a neighbouring name that resolves".

Real values live in `app/settings_local.py` (gitignored), as does `latest_display.png`, which renders calendar event titles. Keep both out of git.

Scan the staged diff *and* the drafted commit message before committing. Technical substance survives generic phrasing intact, so there is never a tradeoff to weigh here.

## Development process

Use `/feature "<requirement>"` to handle any new feature or significant change end-to-end. It runs requirements → design → implement → review → present.

## Best practices

**UI verification**
- After every UI change, run `make screenshot` and read the PNG yourself before saying anything to the user
- Never declare a UI task done without having seen the screenshot

**Layout changes**
- Before touching CSS layout, model the height budget: SVG dimensions, font sizes, padding, number of rows — do the arithmetic first
- This display has fixed dimensions (default 1200×825). Content that doesn't fit gets clipped silently

**Dead code**
- Never assert a cause that hasn't been tested. Reproduce against the real effective config, not the parameters an issue reports
- When a failing code path feeds a value nothing consumes, delete the producer. Don't harden it, don't make it optional. Hardening keeps the failure mode and adds maintenance
- Before choosing a fix shape, grep for consumers of the failing value. Zero consumers is the diagnosis, and it outranks wherever the traceback points
- `git log -S<symbol>` on the way in. An orphaned field usually means an incomplete refactor, and the commit that orphaned it explains the why

**Scope you don't need to ask about**
- Deleting a public symbol that has no consumers
- Updating `README.md` when a change makes it stale
- Adding a `TODO.md` entry for work that actually needs doing

**Bail-out rule**
- If a UI issue is not resolved after 2 attempts: `git restore .`, notify the user, and rethink — don't keep patching
- If a plan turns out to require major rework of something already working: stop and tell the user before implementing

**Commits**
- Follow the commit style guide in the global `CLAUDE.md`
- Multi-commit work goes in a feature branch
- Merge feature branches to main with squash+rebase to keep linear history: `git rebase main` on the branch, then `git merge --squash` into main

**TODO.md**
- When working on a feature, note any out-of-scope findings in `TODO.md` — things noticed but intentionally left alone
- Do this at the end of each feature, before closing the branch
- Only for work that actually needs doing. Never a note on how to re-add something being deliberately removed: git holds that, and an "in case we want it back" entry is the same mistake as leaving the dead code in
