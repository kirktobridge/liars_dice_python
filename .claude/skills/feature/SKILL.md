---
name: feature
description: End-to-end feature pipeline — plan, implement, test, verify, backlog upkeep — for a feature request or backlog ID. Use when the user asks to "build", "add", or "ship" a feature and wants the whole lifecycle handled, e.g. "/feature A2" or "/feature add a rematch button".
---

# Feature Pipeline (orchestrator)

Runs the four stage skills in order for one feature request or backlog ID:

```
/feature-plan  →  [user approval]  →  /feature-implement  →  /feature-test  →  /feature-verify
```

## How to run it

1. Create a TodoWrite list with the four stages; keep exactly one in progress.
2. Invoke each stage skill and follow it fully — the stage skills own the detail; this
   skill owns sequencing and the gates between them.
3. **Gates are hard:**
   - Plan → Implement requires explicit user approval of the plan. This is the one
     mandatory pause in the pipeline; everything after it runs without check-ins unless a
     stage hits a user-owned decision.
   - Implement → Test requires all plan steps ticked and the full suite green.
   - Test → Verify requires the adversarial pass green including new tests.
   - Verify failing sends work **back to Implement** (update the todo list to show the
     loop), not forward with caveats.
4. Backlog bookkeeping happens inside the stages (`/backlog` conventions): item created or
   claimed during plan, in-progress at implement start, Done only at verify close-out.
5. Finish with one summary: what shipped (commits), how it was verified, and any new
   backlog items filed along the way.

## Scope notes

- Multiple loosely-related requests in one message → one pipeline per backlog item; plan
  them together if the user wants, but implement/verify separately so each lands green.
- A request that turns out to be a question or an investigation, not a change → answer it;
  don't force it through the pipeline.
- Tiny fixes still take the pipeline, just proportionally: a three-line plan is a plan;
  a 30-second CLI drive is a verification. The stages scale down — they don't switch off.
