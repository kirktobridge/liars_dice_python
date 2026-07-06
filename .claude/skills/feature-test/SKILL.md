---
name: feature-test
description: Adversarial testing pass after implementation — coverage against the plan's test plan, edge cases, full unit + E2E suite. Use after /feature-implement completes, or when the user says "test this feature properly".
---

# Feature Testing

Input: a completed implementation for `docs/plans/<id>-<slug>.md`.
Mindset shift: implementation wrote tests to make the feature work; this pass tries to make
it **break**. Same code, hostile reviewer.

## Steps

1. **Coverage audit against the plan.** Read the plan's test-plan section. For every listed
   test and edge case, point to the test that now covers it (file + test name). Anything
   unlisted-but-obvious counts too:
   - Boundary values: 2 players, `MAX_PLAYERS`, 1 die left, count at the table maximum,
     face 1 (wilds) — most historical bugs here live on the wilds and escalation rules.
   - Error paths: invalid input, LLM fallback, disconnects (for web-facing work).
   - Interaction with all four decision paths (CPU / human CLI / web / LLM) if the change
     touches bidding or challenge rules — they have drifted before.
2. **Write the missing tests.** Unit tests go in the most relevant *existing*
   `tests/test_*.py` file (helpers: `make_game()` in `test_game.py`, `make_player()` in
   `test_player.py`). Web-visible behavior gets E2E coverage in the matching
   `web/test_*_e2e.py`. New test files need a reason.
3. **Run the full combined suite** exactly as CLAUDE.md specifies (server on port 8765 +
   `pytest tests/ web/`). First check nothing stale is bound to port 8765 — a stale server
   makes E2E pass against the wrong code.
4. **Stability check for touched E2E**: if you added or modified Playwright tests, run that
   file a second time. A test that passes once is not yet a test.
5. **Report**: pass/fail counts verbatim, tests added (file + name), and any gap you chose
   not to cover, with the reason. Red tests are fixed here or the work goes back to
   `/feature-implement` — never forwarded to verify.

## Rules

- The full suite is the bar — "the tests I wrote pass" is not a result.
- Deselected live-Ollama tests (`test_llm_integration`) stay deselected unless the change
  touches the LLM client/lifecycle path; then run them with an `OllamaSession` available.
- Commit new tests at green (conventional commit, backlog ID in body).

## Exit criteria

Full suite green including new tests; coverage audit written up; committed. Hand off to
`/feature-verify`.
