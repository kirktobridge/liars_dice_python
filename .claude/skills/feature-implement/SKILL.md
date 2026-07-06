---
name: feature-implement
description: Execute an approved implementation plan from docs/plans/ in small, test-backed, committed increments. Use after /feature-plan approval, or when the user says "implement <backlog ID>" for an item that already has a plan.
---

# Feature Implementation

Input: an approved plan at `docs/plans/<id>-<slug>.md`.
Precondition: the plan exists and was approved. If either fails, stop and route to
`/feature-plan` — do not improvise a plan here.

## Setup

1. Re-read the plan and the backlog item. Then mark the item in progress in
   `docs/BACKLOG.md` (per `/backlog` conventions).
2. Confirm you are on a working branch, not `main`. If on `main`, create
   `feature/<id>-<slug>`.
3. Confirm the tree is green before writing anything: run the full suite (the combined
   unit + E2E command in CLAUDE.md). Never build on a red tree — fix or flag first.

## The loop — one plan step at a time

For each step in the plan's checklist:

1. **Test first when the step changes behavior**: write the failing test, watch it fail for
   the expected reason, then make it pass. Skip test-first only for pure refactors already
   covered by existing tests — those must stay green throughout.
2. **Implement minimally.** Match the surrounding code's style, naming, and comment density.
   Reuse existing helpers (`dice_math`, `models`, existing fixtures) before writing new ones.
   Honor the CLAUDE.md constraints: no `print`/`input`/`sleep` in `LiarsDiceGame` or
   `Player`; no game logic or I/O in `web/app.py`; the pirate CLI experience is untouchable.
3. **Run the full suite** (unit + E2E, combined command) — not just the tests you touched.
4. **Commit at green.** Conventional-commit style matching the repo's history
   (`feat(web): …`, `fix(engine): …`), body referencing the backlog ID. One coherent change
   per commit.
5. **Tick the step's checkbox** in the plan doc (commit the tick with the step).

## Rules

- **Scope is frozen.** Anything discovered that the plan doesn't cover — a latent bug, a
  tempting refactor, a missing test elsewhere — goes into `docs/BACKLOG.md` as a new item
  (one `/backlog` add), then back to work. The only exception: a defect that blocks the
  current step, which you fix as part of the step and note in the commit body.
- **Deviating from the plan** (a design decision turns out wrong) is allowed but explicit:
  update the plan doc's design-decisions section with what changed and why, in the same
  commit as the deviation. If the deviation changes what the user will get, stop and ask.
- Report test failures verbatim — never paper over a red test by weakening the assertion.
- Do not delete or skip existing tests to get to green without user sign-off.

## Exit criteria

All plan steps ticked, full suite green, every change committed. Hand off to
`/feature-test`. Do not mark the backlog item done — that is `/feature-verify`'s call.
