# Feature Development Process

The user has requested: **$ARGUMENTS**

Follow this process in order. Do not skip phases.

---

## Phase 1: Requirements

1. Read `CLAUDE.md` and `README.md` for project context if not already fresh in context
2. Ask the user targeted questions to resolve anything ambiguous — don't guess
3. Confirm your understanding before moving on

Do not write any code until the requirement is clear and confirmed.

---

## Phase 2: Design

1. Use the **Explore** subagent to research relevant parts of the codebase
2. Design the implementation approach
3. For UI/layout changes: model the height and space budget before touching any CSS — know what fits before you start (look at SVG dimensions, font sizes, padding; do rough arithmetic)
4. If the design requires major rework of something that already works: **STOP**, explain the scope to the user, and ask how to proceed — don't just start reworking
5. Present the design briefly; proceed unless the user objects

---

## Phase 3: Implementation

1. If the work spans more than one commit, create a feature branch: `git checkout -b feature/<name>`
2. Implement in logical steps and commit as you go
3. **After every UI change without exception**: run `make screenshot`, read the PNG yourself, describe what you see — only then continue
4. If a UI problem is not resolved after **2 attempts**: run `git restore .`, notify the user, and rethink the approach — do not keep patching

---

## Phase 4: Review

1. Run `make lint` and fix any issues
2. Spawn the `/review` or `/simplify` skill on changed files
3. Take a final screenshot and confirm it looks correct
4. Check for regressions in sections you didn't intentionally touch

---

## Phase 5: Present

1. Show the final screenshot and describe what you see
2. Summarize what was built and any tradeoffs
3. Note open questions or suggested follow-ups
4. Wait for the user's sign-off before merging or closing the branch
