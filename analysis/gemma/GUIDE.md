# Gemma Analysis — Guide

Conceptual companion to [README.md](README.md) (operations) and [v1_vs_v2.md](v1_vs_v2.md) (latest results). What we're testing, why, and what would need to change to extend this beyond `gemma4:e4b`.

## What we've tried

| Run | Intervention | Result | Headline finding |
|---|---|---|---|
| [v1 baseline](runs/2026-05-03_v1_baseline/report.md) | Plain prompt: rules, dice, history, JSON shape. No anchors, no validation. | **0/180 wins** | 22.5% of bids were `count=1` (illegal, instant loss). Challenge rate ~50%, accuracy 1–9%. Eliminated first in essentially every game. |
| [v2 prompt-anchors](runs/2026-05-03_v2_prompt-anchors/report.md) | (1) explicit legality constraints, (2) precomputed sizing anchor, (3) precomputed plausibility cue, (4) one-shot legality-retry loop. See [src/strategy.py:582-681](../../src/strategy.py#L582-L681). | **38/180 wins (21.1%)** | All three v1 failure modes closed. Lift concentrated on chaotic opponents (Reckless 47%, Wild Card 40%); disciplined archetypes (Salty, Stoic) still win every game-or-two. Retry loop fired only 9/2,755 times — prompt structure did the work, not validation. |

The next logical interventions identified in [v1_vs_v2.md](v1_vs_v2.md): per-opponent aggression cues drawn from `OpponentProfile`, and choice-list prompting (enumerate legal options with precomputed probabilities; LLM picks an index). Both are pure prompt-engineering. Neither is built.

## Testing philosophy

The fixed scaffold across all runs:

- **Same model, seeds, matchups, archetypes, engine.** v1→v2 differ only in `src/strategy.py`. `run_metadata.json` records `strategy_module_sha256` and the git SHA so any run is reproducible by checkout.
- **Six matchups × 30 games × 5 seats = 180 games / run.** Five matchups are 4× a single CPU archetype (so one trait dominates); the sixth is one of each. The point isn't to find the absolute win rate — it's to see *which opponent shapes* the LLM can and can't handle.
- **Wilson 95% CIs reported, not point estimates.** 30 games per matchup gives a noise floor wide enough that ±5% differences are not signal. Cross-run comparisons live in their own file (`v1_vs_v2.md`); each per-run report carries its own Limitations section.
- **Every prompt + every response captured to `traces.jsonl`** (gitignored, ~5 MB / run). The JSONL is the source of truth for behavioural metrics; aggregates in `results.json` are derived. If a future analysis wants a metric we didn't compute, the trace is still there.
- **Latency is reported as a behavioural metric, not a perf KPI.** Median latency dropped 6× in v2 despite a longer prompt — that's a fact about Ollama's prefix cache hitting more often, not about the model getting smarter.

## What Gemma sees right now

Per [src/strategy.py:582-621](../../src/strategy.py#L582-L621), every decision prompt contains:

1. **Rules paragraph** — what a bid/raise/challenge/spot-on means, that 1s are wild.
2. **Legality constraints** — `count >= MINIMUM_BID`, `face ∈ 1..6`, opening turn must bid, raise must strictly escalate.
3. **Her own dice** as a list, plus the total dice on the table split her-vs-others.
4. **Sizing guide** (response *and* opening turns) — precomputed `best_face`, `best_matches`, `expected_others = tot_other_dice // 3`, and a `suggested = best_matches + expected_others − 1` printed verbatim into the prompt: *"A safe opening bid is around N <face>s — bidding at the expected count is ~50% true, so leave a small safety margin."*
5. **Plausibility cue** (response turns only) — precomputed `claim_ratio = bid_count / total_dice` with a verbal verdict: below 0.30 → "very likely true; challenge is rarely correct"; 0.30–0.45 → "around the truthful baseline"; ≥0.45 → "well above baseline; challenge becomes plausible".
6. **Recent history** — last 10 actions in natural-language form (`"Reckless raised to 6 fours"`).
7. **Previous action** in the current round.
8. **JSON shape** — `{"action": ..., "count": ..., "face": ...}`, plus an instruction not to emit markdown or explanation.

## What Gemma does *not* see

- Other players' actual dice (correctly hidden).
- Per-opponent profiles. `CPUStrategy` maintains an `OpponentProfile` for every other seat (recent challenge rate, recent bid intensity, observed bluff frequency from `observe_outcome` callbacks). None of it is in the LLM prompt — the LLM gets only the surface action history.
- Round-context counters: which round of the game, how many dice each opponent currently holds (only the *total* "other dice" count is given, not the per-seat breakdown), turn order around the table.
- Probability values for the candidate actions (truth probability of the standing bid, expected value of `challenge` vs `raise to N`, spot-on probability). All of these are computable cheaply — `dice_math.needed_cnt` and `get_binom` already exist — and `CPUStrategy` consults them, but they are not in the prompt.
- Personality / risk-appetite framing for itself. Gemma is told the rules, not asked to play with any disposition.
- The other players' archetype labels. Even the matchup name (`vs 4× Reckless Buccaneer`) never reaches the prompt.

## The opinionation tension

The concern is real and load-bearing for what this analysis is *for*. v2's sizing anchor is `best_matches + tot_other_dice//3 − 1` — the same expression `CPUStrategy` uses for its truthful-opening EV bid. The plausibility cue collapses challenge into three verbal buckets keyed on the same `1/3` baseline that `CPUStrategy.decide()` checks. If we keep pushing in this direction (per-opponent aggression cues, choice-list prompting with precomputed probabilities), the asymptote is exactly what you flagged: **the LLM becomes an input handler that picks among precomputed CPU-strategy outputs**, and the win rate is just measuring how reliably it copies the suggestion.

What we'd actually be measuring shades along a spectrum:

- **v1 baseline** — pure capability test. Can the model derive Liar's Dice play from rules + state alone? Answer: no, not at this size.
- **v2 anchors** — capability test of *deviation from a hint*. Does it use the suggestion? Outperform it against bluffy opponents? Underperform when the hint is wrong (e.g. against disciplined opponents, where the hint stays static but the right move depends on read)? The data shows it *does* deviate (raise rate 42–51% in mid-history, not just echoing the suggested count) — but how much of that is reasoning vs. sampling temperature is not separable from this run alone.
- **Choice-list prompting** — explicitly an input-handler test. Useful for product (we want a working LLM player at this size), uninteresting for cognition (the model is just classifying among options the CPU already enumerated).

A cleaner cognition test, if that's what we want to optimize for, would invert the v2 design: keep the legality constraints (those are about output format, not strategy) but **drop the sizing anchor and plausibility cue**, and instead vary one informational axis at a time — e.g. (a) rules + dice + minimal history, (b) +per-opponent action profile but no probability, (c) +probability for the standing bid only, (d) full v2 anchors. The win-rate gradient across (a)–(d) tells us where the LLM's own reasoning is or isn't picking up signal.

That's not what v2 set out to do. v2 was binding-constraint removal: three specific failure modes were eating every game, and the cheapest fix was to print the right answer into the prompt. The next run should declare which question it's asking — capability, deviation, or input-handler — and design accordingly.

## What it'd take to test other local LLMs

The plumbing is mostly model-agnostic; only a few touchpoints assume Gemma. In rough order of effort:

1. **Model selection.** [src/constants.py:1](../../src/constants.py#L1) hard-codes `LLM_MODEL = "gemma4:e4b"`. `LLMStrategy.__init__` already takes `model` as a parameter, but `_gemma_config()` in [scripts/gemma_analysis.py:80-81](../../scripts/gemma_analysis.py#L80-L81) reads `Constants.LLM_MODEL` and `OllamaSession(model=Constants.LLM_MODEL)` at [scripts/gemma_analysis.py:864](../../scripts/gemma_analysis.py#L864) does too. Add `--model` to the CLI, thread it through `_gemma_config`, the `OllamaSession` context manager, and the metadata dict that already records `model` to `run_metadata.json`. Anywhere `Constants.LLM_MODEL` is read in the script becomes `args.model`.
2. **Per-model decoding params.** `LLM_TEMPERATURE = 1.0` was chosen on Google's Gemma guidance — that's wrong for, say, Qwen or Phi. The CLI already accepts `--temperature` and `--timeout`; just don't keep `1.0` as the default once the script is multi-model. Either ship a small dict (`MODEL_DEFAULTS = {"gemma4:e4b": {"temp": 1.0}, ...}`) or require `--temperature` explicitly when `--model` is non-default.
3. **Player name + report copy.** `GEMMA_NAME = "Gemma"` is the seat label; ~10 sites in `gemma_analysis.py` filter DataFrames on `player_name == GEMMA_NAME` and the report templates hard-code "Gemma" in prose. Replace with a derived name (e.g. the model tag minus the `:` suffix) and parameterize the report copy. The schema fields (`action_caller`, `round_loser`, `winner`) are already by-name and don't care which model is in that seat.
4. **Output directory layout.** `analysis/gemma/runs/<run-name>/` is hard-coded as `--runs-root`. For multi-model work, the natural shape is `analysis/llm/runs/<model-slug>/<run-name>/` so a model's runs cluster, and cross-model comparisons (the analogue of `v1_vs_v2.md`) live one level up. README's "How to run" snippet needs to follow.
5. **Prompt portability.** The v2 prompt was written for Gemma. Some models want a system role separate from the user role; some want explicit `<json>` tags; some get visibly worse on long preludes. `query_llm` in [src/llm_client.py](../../src/llm_client.py) currently sends the whole thing as a single string to Ollama's `/api/generate`. To compare cleanly across models we'd want either (a) a tiny per-model adapter that wraps the same logical prompt for that model's preferred chat template, or (b) a deliberate decision to use the same raw prompt for all models and report cross-model diffs as part of the comparison. Option (b) is cheaper and arguably more honest.
6. **Reproducibility metadata.** `run_metadata.json` already records `strategy_module_sha256`. For multi-model runs add the resolved Ollama model digest (`ollama show <model> --modelfile` exposes it) so a re-run on a re-pulled model is detectable as a different artifact, not silently the same.

What does **not** need to change: the engine, archetype definitions, matchup composition, trace capture, results aggregation, or the report schema. Those are all model-agnostic.

A reasonable first multi-model run: pick three models around the 4–8B range (e.g. `gemma4:e4b`, `qwen3:8b`, `phi4:14b`), keep the v2 prompt verbatim, run the same six matchups, and compare. That's a capability landscape, not a cognition study — but it's the prerequisite for deciding whether the cognition study is worth doing per-model or only on the most capable one.
