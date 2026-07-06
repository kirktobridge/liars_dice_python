# Backlog & Implementation Plans

Output of the 2026-07-06 codebase audit. Items are grouped by theme; each has an ID,
priority, and enough context to pick up cold. Implementation plans and ordering are at
the bottom.

**Lifecycle conventions** (maintained by the `/feature-*` and `/backlog` skills in
`.claude/skills/`):

- IDs are `<group letter><number>`, assigned once, never reused.
- An item with no status line is open. When work starts, a `**Status:** in progress
  (YYYY-MM-DD, plan: docs/plans/<id>-<slug>.md)` line is added under its heading.
- Completed items move to the **Done** section at the bottom of this file, with completion
  date and commit SHA.
- New work discovered mid-implementation becomes a new item — scope is never silently
  expanded on an existing one.

Test-suite status at audit time: **435 passed, 4 deselected (live Ollama)** — the codebase
is healthy; this backlog is about gaps, latent bugs, and next-level work, not firefighting.

---

## A. Correctness & Rules Integrity

### A1 — Unify raise-legality rules across all four decision paths — **High**
Each path enforces a *different* rule for what beats the standing bid:
- CPU (`strategy.py _get_permissible_bids`): same count with **any** face not previously bid
  (including a *lower* face), or count+1.
- Human CLI (`main.py human_input_handler`): forbids only the *identical* bid — same count
  with a lower face is accepted.
- Web (`game_session.py _compute_valid_bids`): same count requires a **higher** face.
- LLM (`strategy.py _query_and_validate`): strict escalation (count up, or same count + face up).

So a CPU can legally (by its own rules) make a bid the web UI would never offer a human, and
the CLI accepts bids the LLM validator would reject. Pick one canonical rule (strict
escalation is the standard variant and what the LLM/web already use) and enforce it in
**one place** (see A2).

### A2 — Move bid validation into the engine — **High**
`LiarsDiceGame` never validates any bid. `MINIMUM_BID = 2` is enforced only in the LLM
validator; the CLI's `_prompt_bid_count` accepts 0 and 1, and the web's opening-bid list
starts at count 1. An illegal bid from any strategy silently corrupts the round (a count-0
bid is unchallengeable). Add a single `is_legal_bid(prev_bid, new_bid, total_dice)` check in
the engine (rejecting via the existing error-event path), and make the per-strategy checks
callers of the same function.

### A3 — Max-rounds game end has no winner — **Medium**
When `round_num > max_rounds`, `game_status` flips false with no `game_won` event.
`tournament.run_game` then crowns `game.players[0]` arbitrarily; `snapshot()` reports
`winner=None`; a web session ends with a winner-less `game_over`. Define the tie-break
(most dice remaining, seat order as final tie-break), emit a proper terminal event, and
cover it with a test.

### A4 — `num_players` constructor arg vs actual roster never validated — **Medium**
`LiarsDiceGame(num_players=4)` with 3 `add_player` calls raises IndexError mid-round
(`process_round` iterates `range(self.num_players)`); with 5 it silently skips a player.
Validate at first `process_round`, or drop the constructor arg and derive from
`len(self.players)`.

### A5 — CPU raise cap uses the wrong dice total — **Low**
`_get_permissible_bids` gates raises on `prev_bid_cnt + 1 <= tot_other_dice`, excluding the
CPU's own dice from the ceiling, so CPUs stop raising earlier than legal in endgames. Also,
raise candidates only ever consider `count + 1` — jump-raises are unrepresentable. Fix the
cap; consider whether multi-step raises are worth ranking.

### A6 — Silent turn-skip on strategy exception — **Low**
`_run_turn` catches any exception from `take_turn`, emits an error event, and skips the
player. If a strategy fails deterministically, the round loop spins with no progress and no
bound. Count consecutive failures per round and abort the round (or game) past a threshold.

### A7 — Abandoned web sessions leak their game thread — **Medium**
On WebSocket disconnect, `GameSession`'s daemon thread stays blocked forever on
`self._action_queue.get()` (waiting for human input that will never come), holding the game
and queues alive. Add a shutdown signal: on disconnect, put a sentinel/poison action into the
handler queue and have the thread exit cleanly.

---

## B. Architecture & Packaging

### B1 — Proper Python packaging; kill the sys.path hacks — **High**
There is no `pyproject.toml`. `src/` modules use bare intra-package imports
(`import constants`), forcing `sys.path.insert` hacks in `conftest.py`, `web/app.py`,
`web/game_session.py`, and `scripts/gemma_analysis.py`, and blocking any editor/typechecker
from resolving imports normally. Plan: add `pyproject.toml`, make `src/` an installable
package (e.g. `liars_dice`), convert to absolute imports, `pip install -e .`, delete the
path hacks. Rename `LiarsDiceGame.py` → `game.py` and `Player.py` → `player.py` (PEP 8
module names) as part of the same churn.

### B2 — Split `strategy.py` (878 lines, three unrelated strategies) — **Medium**
`CPUStrategy`, `LLMStrategy` (plus its prompt-variant machinery), `HumanStrategy`, and
`Personality` all live in one file. Split into a `strategies/` package: `personality.py`,
`cpu.py`, `llm.py`, `human.py`, with `Strategy` Protocol in `base.py`. Note:
`analysis/gemma` run metadata hashes `strategy.py` (`strategy_module_sha256`) — the analysis
script must switch to hashing the LLM strategy module (record the change in run metadata so
old hashes stay interpretable).

### B3 — Deduplicate `advisor.py`'s private binomial helpers — **Medium**
`advisor.py` re-implements `_get_binom` and `_needed_cnt` even though `dice_math.py` was
extracted for exactly this. Two caches of the same scipy objects; two places for the wilds
rule to drift. Replace with imports from `dice_math`.

### B4 — Remove dead code on `Player` — **Low**
`rolls_mode`, `wild_count`, `mode_count`, `grade()`, `count_ones()` are unused outside
`Player` and its tests (the strategy layer computes its own stats). Delete, prune tests.

### B5 — Replace deprecated FastAPI `@app.on_event('startup')` — **Medium**
Deprecated since FastAPI 0.93; use a lifespan context manager. Currently used only to start
the LLM debug broadcaster.

### B6 — Tournament job store lifecycle — **Low**
`_jobs` evicts the oldest entry (even if still running) at 20 jobs, and results are deleted
on first GET (a page refresh loses them). Move to timestamped entries with TTL cleanup;
keep results until expiry.

---

## C. Testing, DX & Tooling

### C1 — requirements.txt is missing the entire web/E2E stack — **High**
Not listed but required: `fastapi`, `uvicorn`, `pydantic`, `websockets`, `playwright`,
`pytest-playwright`, `pytest-timeout`. A fresh clone cannot run the documented test command
or the web server. Regenerate a complete, pinned requirements file (or fold into
`pyproject.toml` with a `[dev]` extra alongside B1).

### C2 — No CI — **Medium**
No `.github/`. Add a GitHub Actions workflow: install deps + playwright browsers, start
uvicorn, run `pytest tests/ web/`, plus the lint/type checks from C3. The repo's test
discipline is excellent; CI makes it enforceable.

### C3 — No lint/format/typecheck config — **Medium**
No ruff/flake8/mypy config anywhere. Type hints are already pervasive — mypy would be cheap
to adopt. Add `ruff` (lint + format) and `mypy` with a permissive baseline, wire into CI.

### C4 — Multiprocessing fork-in-thread deprecation — **Low**
`test_tournament_llm` emits 16 `DeprecationWarning: use of fork() may lead to deadlocks`
(ProcessPoolExecutor forking from a threaded context — exactly how `web/app.py` calls
`run_tournament`). Pass an explicit spawn context (`mp_context=multiprocessing.get_context("spawn")`)
to `ProcessPoolExecutor`; verify Personality pickling still works.

### C5 — Commit the shareable half of `.claude/` — **Low**
`.gitignore` excludes all of `.claude/`, but `settings.json` and the two hooks
(`enforce-venv.py`, `safe-uvicorn.py`) encode real project conventions any agent/contributor
benefits from. Ignore only `settings.local.json`, commit the rest.

### C6 — E2E server port is hard-coded — **Low**
Port 8765 is baked into docs, tests, and the safe-uvicorn hook. Read from an env var with
8765 as default so CI and parallel checkouts don't collide.

---

## D. Web & UX

### D1 — Session resilience: refresh loses the game — **Medium**
`_sessions` state is discarded on disconnect (and the thread leaks — A7). Support rejoining:
keep the session alive for a grace period keyed by session id, replay the latest snapshot on
reconnect.

### D2 — LLM seat in web custom tournaments — **Medium**
`run_tournament` supports LLM players serially, but the web custom-tournament endpoint
neither accepts `player_type` nor can use it (worker always sets `parallel=True`, which
raises on LLM). Add `player_type` to `_PlayerConfig`, route LLM-containing configs to the
serial path, surface it in `tournament.js`.

### D3 — `POST /explainer/custom` — user-defined scenarios — **Low**
Documented future work in CLAUDE.md: Pydantic validation mirroring `_PlayerConfig` trait
ranges, arbitrary dice/bid inputs, same `run_scenario` machinery.

### D4 — Difficulty selector backed by prompt variants — **Low**
`PROMPT_VARIANTS` already produces a measured skill ladder (1.1% → 28.3% win rate). Expose it
in the lobby as an LLM difficulty knob (Easy = minimal … Hard = anchors). Cheap feature,
directly monetizes the research.

---

## E. Documentation

### E1 — Rewrite the root README — **High**
13 lines, two of which are font-swap trivia; no mention of the web UI, LLM opponent,
explainer, analysis harness, setup steps, or tests. Write a real README: feature overview,
quickstart (venv → install → CLI / web / tournament), test instructions, pointer to
`analysis/gemma/` and `docs/`. Fold the font/tailwind notes into a web section or
`docs/`.

### E2 — CLAUDE.md corrections & additions — **Medium**
See the audit notes; headline items: document `scripts/gemma_analysis.py` + the
`analysis/gemma` workflow, the CLI entry points (`src/main.py` flags `--fast`/`--debug`;
`src/tournament.py -n/-p/-w`), the `prompt_variant` knob on `LLMStrategy`, the WSL
gateway fallback in `llm_client`, the requirements caveat (until C1 lands), and the
`logs/` convention.

### E3 — Event schema reference — **Low**
The `on_event` payloads are the contract binding engine ↔ pirate renderer ↔ stats collector ↔
web session, but the schema exists only implicitly across four consumers. Write
`docs/events.md`: one table per event type with fields and emitters.

### E4 — Refresh stale analysis docs — **Medium**
`analysis/gemma/GUIDE.md` predates v3: "What Gemma sees / doesn't see" describes the v2
prompt as current (profile and standing-prob info *are* now prompt variants; `anchors` is the
default), and it calls `v1_vs_v2.md` the "latest results." The README's "How to run" example
hardcodes a machine-specific `OLLAMA_URL` IP. Also `tournament_stats.html` is referenced by
the analysis README as if durable, but it's gitignored — clarify it's a locally generated
artifact.

---

## F. LLM Research Platform

### F1 — Multi-model analysis harness — **Medium**
Already fully specified in `analysis/gemma/GUIDE.md` §"What it'd take": `--model` CLI flag,
per-model decoding defaults, parameterized seat name/report copy, `analysis/llm/runs/<model>/`
layout, Ollama model digest in run metadata. Execute that spec.

### F2 — v3e: fix the spot-on misread — **Low**
v3c's standing-prob cue triggered 839 spot-on calls at 7.4% accuracy (Gemma reads "high truth
probability" as "count is exactly right"). One-line prompt clarification + a piece-sized run
to confirm, per the v3 report's caveats.

### F3 — Live LLM telemetry for web games — **Low**
The analysis pipeline is offline-only by design. Reuse the `TraceRecord` schema to optionally
log live web-game LLM decisions (prompt, response, thinking, latency, fallback) under
`logs/llm/`, giving production data the same shape as research data.

---

## G. Product Vision

Expansive directions from the Phase 5 audit. These are larger bets, not incremental fixes;
each would start with a scoping pass via `/feature-plan` before any commitment.

### G1 — "LiarsBench": standardized bluffing benchmark for local LLMs — **Medium**
Builds directly on F1 (multi-model harness). Run 5–10 models in the 4–14B range through the
fixed matchup grid and publish a reproducible leaderboard: win rate with Wilson CIs, challenge
accuracy, bid aggression, fallback rate — per model, per prompt-scaffolding level. The
prompt-variant ladder gives a second axis nobody else measures: *scaffolding elasticity* —
how much precomputed help a model needs before it plays competently (Gemma: 1.1% → 28.3%).
Deliverable: `analysis/llm/LEADERBOARD.md` + methodology doc; the existing run-metadata
discipline (seeds, SHAs, model digests) is already publication-grade.

### G2 — CFR near-optimal policy player (absolute skill ceiling) — **Medium**
Liar's Dice is small enough for counterfactual regret minimization to yield a near-optimal
policy. Train one offline, ship it as a new `Strategy` (`player_type='CFR'`). Every existing
win rate — CPU archetypes, LLM variants, humans — becomes measurable against *optimal*
instead of against each other. Also the honest difficulty ceiling for D4's ladder.

### G3 — Table talk: a second deception channel — **Low**
Let the LLM emit an optional `say` field alongside its action; render it in the web UI and
pirate CLI. Research angle: does cheap talk shift human/CPU challenge rates, and does the
LLM's talk correlate with its actual hand (is it a *good* liar)? Product angle: the table
finally talks back. Needs a trace-schema extension so talk is captured like decisions.

### G4 — Post-round coach: decision review for the human player — **Medium**
Merge `advisor_probs` (already computed every human turn) with the explainer's step-through
machinery into a post-round "here's what your challenge odds actually were" review. Rate each
human decision against the math, accumulate a per-game report card. Probability literacy
taught through gameplay; most product-shaped item in this group. (The live-difficulty knob
that pairs with this is D4.)

---

## Implementation plans & ordering

Recommended order: **Plan 1 → Plan 2 → Plan 3 → Plan 4/5 (parallel) → Plan 6.**
Rationale: tooling first (cheap, protects everything after), correctness second (small
high-value diffs on a green tree), the big packaging churn third (with CI as the safety
net), then web/docs/research work which are independent of each other.

### Plan 1 — Foundations (C1, C2, C3, C4, C6, C5)
1. C1: freeze the venv into a complete pinned requirements set; verify on a clean venv.
2. C3: add ruff + mypy configs, fix or baseline existing findings.
3. C2: GitHub Actions running lint + unit + E2E (C6 makes the port configurable for CI).
4. C4: spawn context for the process pool.
Exit: fresh clone → green CI.

### Plan 2 — Rules integrity (A2, A1, A3, A4, A5, A6, A7)
1. A2 first: introduce engine-level `is_legal_bid` — this creates the single enforcement
   point A1's unified rule lives in.
2. A1: adopt strict escalation everywhere; update CPU permissible-bid generation, CLI
   prompts, and tests (some CPU behavioural tests will shift).
3. A3 + A4: terminal-state and roster-validation edge cases, each with a regression test.
4. A5, A6, A7: individually small; A7 touches `web/game_session.py` only.
Exit: all four decision paths share one rulebook, enforced by the engine.

### Plan 3 — Packaging & structure (B1, B2, B3, B4, B5, B6)
1. B1 in one commit: pyproject + package rename + absolute imports + editable install +
   delete path hacks. Run the full suite; CI from Plan 1 guards the long tail
   (scripts, hooks, docs referencing old paths).
2. B2: split strategies package; update `gemma_analysis.py`'s module hashing and note the
   hash-basis change in run metadata.
3. B3, B4: dedupe + dead code removal.
4. B5, B6: web-layer modernization (lifespan, job TTL).
Exit: `pip install -e .` works; no module >500 lines except explainer narratives.

### Plan 4 — Web & UX (A7 prereq, D1, D2, D4, D3)
1. D1 builds on A7's clean shutdown: grace-period session registry + snapshot replay.
2. D2: LLM seat in custom tournaments (serial path).
3. D4: difficulty selector from prompt variants (small, high-delight).
4. D3: custom explainer scenarios last (largest surface, least demand).

### Plan 5 — Documentation (E1, E2, E4, E3)
E1 and E2 immediately (E2 gets simpler after Plans 1/3 land — do a first pass now, final
pass after). E4 alongside any next analysis run. E3 when convenient; it pays off most just
before Plan 4's web work.

### Plan 6 — Research platform (F1, F2, F3)
F2 is a cheap standalone run. F1 is the gateway to everything in the product-vision
"benchmark" direction. F3 after F1 so live traces share the multi-model schema.

### Plan 7 — Vision bets (G1, G2, G3, G4)
Not scheduled; each starts with its own `/feature-plan` scoping pass. Dependencies:
G1 requires F1. G2 is standalone (offline training + a new Strategy). G3 touches
prompt + trace schema + both UIs. G4 builds on the advisor and explainer as they are today.

---

## Done

_Completed items move here with completion date and commit SHA._
