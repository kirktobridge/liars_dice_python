---
name: feature-plan
description: Plan a feature request or backlog item before any code is written — clarify scope, explore the code, produce an approved implementation plan in docs/plans/. Use when the user requests a new feature/fix, names a backlog ID to start, or says "plan this".
---

# Feature Planning

Input: a feature request (free text) or a backlog ID from `docs/BACKLOG.md`.
Output: an approved plan at `docs/plans/<id>-<slug>.md` and a backlog item that references it.
**No implementation happens in this stage.**

## Steps

1. **Anchor to the backlog.** Search `docs/BACKLOG.md` for an existing item covering the
   request. If none exists, create one now (follow `/backlog` conventions). Every plan needs
   an ID — a feature without a backlog item is untracked work.

2. **Restate and bound.** Write one paragraph: what the user gets when this is done, and
   what is explicitly out of scope. If a genuinely user-owned decision blocks the design
   (not something the code or conventions already answer), ask now with AskUserQuestion —
   never mid-implementation.

3. **Explore before designing.** Read the modules the change touches (the architecture map
   in `CLAUDE.md` is the index), their tests, and any adjacent helper that might already do
   the job — reuse beats new code. List what you read in the plan. A plan written without
   reading the code is a guess.

4. **Write the plan** to `docs/plans/<id>-<slug>.md`:
   - **Goal / Non-goals** — from step 2.
   - **Affected files** — every file expected to change, with one line on how.
   - **Design decisions** — each choice made and the alternative rejected, briefly.
   - **Steps** — ordered checklist. Each step is independently testable and ends the tree
     green; pair each behavior change with the test that proves it. Prefer many small steps
     over few large ones.
   - **Test plan** — new unit tests (which existing `tests/test_*.py` file they extend, per
     CLAUDE.md), E2E impact (which `web/test_*_e2e.py` if web-visible), edge cases.
   - **Verification script** — how `/feature-verify` will observe the feature working in the
     real app (CLI flow, web flow, or endpoint calls). Written now so "verifiable" shapes
     the design.
   - **Docs impact** — README / CLAUDE.md / analysis docs touched.
   - **Risks** — what could break; CLAUDE.md constraints in play (pirate CLI untouched, no
     I/O in engine, no game logic in web/app.py).

5. **Get approval.** Summarize the plan in a few sentences and the step list. Wait for the
   user's go-ahead. On approval, hand off to `/feature-implement`. Do not start implementing
   in this stage even if the change looks trivial — trivial changes get trivial plans, not
   no plan.

## Exit criteria

Plan file exists; backlog item exists and is still open (status flips to in-progress when
implementation starts, not now); user has approved or amended the plan.
