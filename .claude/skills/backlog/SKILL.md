---
name: backlog
description: Maintain docs/BACKLOG.md — add, update, complete, or groom backlog items. Use whenever work is proposed, started, finished, or discovered mid-task, and when the user says "add to backlog", "backlog this", or asks what's next.
---

# Backlog Manager

Single source of truth: `docs/BACKLOG.md`. Every non-trivial change to the codebase should
trace to an item in it. Read the file's intro block first — it states the lifecycle
conventions; this skill is the enforcement mechanism.

## Conventions (must hold after every edit)

- **IDs**: `<group letter><number>` (A1, G4, …). Assigned once, never reused, never renumbered.
  New items take the next free number in their group.
- **Groups**: A Correctness · B Architecture · C Testing/DX · D Web/UX · E Documentation ·
  F LLM Research · G Product Vision. Add a new group only if an item genuinely fits nowhere;
  prefer the closest existing group.
- **Item shape**: `### <ID> — <title> — **<High|Medium|Low>**` followed by 2–8 lines of
  context: what's wrong or wanted, where in the code, and what "done" means. Enough to pick
  up cold — write for a reader who wasn't in this conversation.
- **Status**: no status line = open. In-progress items carry
  `**Status:** in progress (YYYY-MM-DD, plan: docs/plans/<id>-<slug>.md)` directly under the
  heading. Nothing else is a valid status — there is no "blocked" or "someday" marker;
  deprioritize with priority instead.
- **Done**: completed items move (entire item, not a copy) to the `## Done` section at the
  bottom, heading amended to `### <ID> — <title> — done YYYY-MM-DD (<short commit SHA>)`.
- **Cross-references** between related items by ID (e.g. "builds on F1").

## Operations

**Add**: confirm no existing item covers it (search titles *and* bodies — near-duplicates
get merged, not added). Choose group, next ID, priority. If it belongs to an existing
implementation plan at the bottom of the file, add it there; otherwise leave plans untouched.

**Start**: add the status line. If there is no plan doc yet, that's a signal to run
`/feature-plan` first — say so rather than inventing a plan path.

**Complete**: only after `/feature-verify` has passed (or the user explicitly waives it —
note the waiver in the Done entry). Move to Done with date + the SHA of the final commit.

**Discovered work**: mid-implementation findings become *new* items immediately — never
widen the scope of the in-progress item. One sentence of context is enough; capture and
return to the task.

**Groom** (when asked, or when you notice rot): stale in-progress lines whose plan doc or
branch no longer exists → revert to open and flag to the user; priorities that events have
overtaken → propose changes, don't silently reprioritize High↔Low.

## Rules

- Never delete an item; Done or explicit user instruction are the only exits.
- Never change another item's text while editing yours, except to add a cross-reference.
- Keep edits minimal and mechanical; this file is read by humans and cold-start agents alike.
