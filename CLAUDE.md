# everyday-screen — Claude context

See `README.md` for full project documentation: architecture, modules, design patterns, config, and deployment.

## Development process

Use `/feature "<requirement>"` to handle any new feature or significant change end-to-end. It runs requirements → design → implement → review → present.

## Best practices

**UI verification**
- After every UI change, run `make screenshot` and read the PNG yourself before saying anything to the user
- Never declare a UI task done without having seen the screenshot

**Layout changes**
- Before touching CSS layout, model the height budget: SVG dimensions, font sizes, padding, number of rows — do the arithmetic first
- This display has fixed dimensions (default 1200×825). Content that doesn't fit gets clipped silently

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
