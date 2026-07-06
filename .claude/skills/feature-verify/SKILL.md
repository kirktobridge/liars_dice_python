---
name: feature-verify
description: Final gate before a feature is done — drive the real app end-to-end, confirm acceptance criteria by observation, sync docs, close the backlog item. Use after /feature-test passes, or when the user says "verify this works".
---

# Feature Verification

Input: implemented + tested work for `docs/plans/<id>-<slug>.md`.
Principle: **tests prove the code does what the tests say; verify proves the product does
what the user asked.** This stage observes the running application — it never concludes
from test output alone, and it is never skipped for being "trivial".

## Steps

1. **Run the plan's verification script** (the plan wrote one; if it didn't, derive it from
   the Goal section). Exercise the feature the way a user would:
   - **Web**: start `.venv/bin/uvicorn web.app:app --port 8765`, drive the flow with a
     Playwright script (headless is fine; screenshot the key state) or raw HTTP/WebSocket
     calls for API-only changes. Watch the newest `logs/web/*.log` for errors while driving.
   - **CLI**: run `.venv/bin/python src/main.py --fast` and drive the changed flow with
     scripted stdin; confirm the pirate voice is intact if output paths were touched.
   - **Engine/analysis-only**: run the smallest real consumer (a short `run_tournament`, a
     1-game `gemma_analysis.py` smoke run) — not a synthetic snippet that re-tests the unit.
2. **Check acceptance criteria one by one** against the plan's Goal / Non-goals. Each gets
   an explicit observed-result line: what you did, what you saw. "Should work" is not an
   observation.
3. **Regression sweep of adjacent flows**: load the pages / run the flows that share code
   with the change (e.g. a bidding change → play a CPU-only round, open `/explainer`,
   run a small `/tournament`). Watch logs for new warnings.
4. **Docs sync**: if commands, architecture, routes, or conventions changed — update
   CLAUDE.md (architecture map, test commands) and README. If the change affects the LLM
   prompt or analysis pipeline, check `analysis/gemma/` docs for statements it invalidates.
5. **Close out** (only if 1–4 all passed):
   - Move the backlog item to Done in `docs/BACKLOG.md` with date + final commit SHA
     (per `/backlog` conventions).
   - Mark the plan doc completed (one status line at the top; keep the file — plans are
     the project's decision log).
   - Final commit of docs/backlog changes; then summarize for the user: what was verified,
     how, and any follow-up items filed.

## Failure handling

Any acceptance criterion not observed working → the work goes back to
`/feature-implement` with a precise description of the gap. Do not close the backlog item,
do not soften the criterion to match the behavior, and report the failure plainly.

## Exit criteria

Every acceptance criterion observed working in the running app; no regressions or new log
errors in adjacent flows; docs synced; backlog item in Done; everything committed.
