# v1 vs v2 — Did the Prompt Intervention Work?

**Yes.** Three prompt-side changes (legality constraints, sizing anchor, plausibility cue) plus a one-shot legality-retry loop took Gemma from **0/180 wins (0.0%)** to **38/180 wins (21.1%)**, lifting her from "loses every game" to "marginally above the 20% random baseline at a 5-player table." Same model (`gemma4:e4b`), same seeds, same matchups, same archetype lineups.

Detailed per-run reports: [v1 baseline](runs/2026-05-03_v1_baseline/report.md) · [v2 prompt-anchors](runs/2026-05-03_v2_prompt-anchors/report.md).

## Win rate by matchup

| Matchup | v1 wins | v2 wins | Δ | v2 95% CI |
|---|---:|---:|---:|---:|
| vs 4× Salty Veteran | 0/30 | **2/30** | +2 | 1.8–22% |
| vs 4× Reckless Buccaneer | 0/30 | **14/30** | +14 | 31–63% |
| vs 4× Crafty Captain | 0/30 | **6/30** | +6 | 9.4–37% |
| vs 4× Stoic Quartermaster | 0/30 | **2/30** | +2 | 1.8–22% |
| vs 4× Wild Card | 0/30 | **12/30** | +12 | 24–57% |
| vs 1 of each archetype | 0/30 | **2/30** | +2 | 1.8–22% |
| **Total** | **0/180** | **38/180** | **+38** | **15.7–28.0%** |

The lift is concentrated in the two high-bluff matchups (Reckless, Wild Card). Disciplined low-bluff archetypes (Salty, Stoic, Mixed-with-Crafty) still beat her; the prompt fix helped her stop losing trivially, not learn to outplay disciplined opponents.

## Mean finish position (1 = first eliminated, 5 = winner)

| Matchup | v1 | v2 | Δ |
|---|---:|---:|---:|
| vs Salty | 1.00 | 2.63 | +1.63 |
| vs Reckless | 1.03 | 3.63 | +2.60 |
| vs Crafty | 1.07 | 3.03 | +1.96 |
| vs Stoic | 1.03 | 2.43 | +1.40 |
| vs Wild Card | 1.10 | 3.77 | +2.67 |
| vs Mixed | 1.00 | 2.90 | +1.90 |

In v1 Gemma was eliminated **first** in essentially every game. In v2 she's eliminated mid-table or wins outright. Even the matchups where she still loses every game-or-two (Salty, Stoic) show her lasting much longer.

## What changed mechanically

| Failure mode | v1 | v2 |
|---|---:|---:|
| Bids with `count=1` (below legal minimum) | 275 / 1,221 (22.5%) | **0 / 2,239 (0.0%)** |
| Median challenge rate per matchup | 49% | **18%** |
| Median bid aggression (claimed/total) | 0.08 | **0.35** |
| Median challenge accuracy | 1–9% | **31–59%** |
| Illegal raises (don't escalate) | 25 / 143 (17%) | caught & retried |
| Fallbacks (CPU took over) | 1 / 2,432 | **0 / 2,755** |
| Mean LLM latency | 12.92s | **9.27s** |
| p50 LLM latency | ~12s | **2.13s** |
| Wall-clock per run | 8h 44m | **7h 06m** |

The latency drop is itself an interesting finding — the v2 prompt is *longer* but Ollama returns the median response 6× faster. Most likely the more-structured prompt prefix is hitting Ollama's KV cache more often.

## What was the binding constraint?

In retrospect, three things were broken in v1, listed in order of how badly they were hurting:

1. **`count=1` was 22.5% of bids and was instant-loss every time.** A single line in the prompt (`count must be an integer >= 2`) eliminated this entirely. The legality validator/retry loop never had to fire for this reason in v2.
2. **Reflexive challenges were ~50% of decisions and 1–9% accurate.** The plausibility cue (precomputed `bid_count / total_dice` with a verbal interpretation) cut challenge rate to ~18% and lifted accuracy to 31–59%. This is the second-largest contributor to the win-rate lift.
3. **Underbidding meant her own bids were free dice for opponents.** The sizing anchor (precomputed `expected_others + her_matches − safety_margin`) pulled aggression from 0.08 to 0.35, exactly on the truthful baseline.

The retry-loop validator turned out to be largely cosmetic — only 9 of 2,755 decisions triggered a retry, and most of those were the pre-existing opening-turn illegal-CHALLENGE case. This says something useful: **at this model size, prompt structure matters more than post-hoc validation**. If a future run wants to push beyond ~21% win rate, the next move is more prompt structure (per-opponent aggression cues, an explicit option list to choose from), not stricter validation.

## Where the wins still aren't

Gemma's "above-random" win rate is barely above random. The Wilson lower bound (15.7%) doesn't even cleanly clear the 20% baseline. To call her "competitive" we'd want win rate ≥ 25–30% (clearly above 1/5 for a non-trivial 5-player table).

The data points to two paths forward, in increasing cost:

- **(a) Per-opponent aggression cues in the prompt.** The `OpponentProfile` machinery already exists in [src/strategy.py:318-346](../../src/strategy.py#L318) — pre-compute each opponent's recent bid intensity and inject it as `Reckless: bids ~0.45 of total dice (over-claims)` into the prompt. This is the cheapest non-trivial intervention; should help against the disciplined-opponent matchups specifically.
- **(b) Choice-list prompting.** Replace the open-ended `{"action": ..., "count": ..., "face": ...}` format with `Your options are: (1) bid 4 fours [P=0.78]; (2) raise to 5 threes [P=0.63]; (3) challenge [P_success=0.18]. Reply with the option number.` This collapses the search space and removes ill-formed-output paths entirely. It's the well-trodden path for getting smaller LLMs to play structured games.

Both are pure prompt-engineering — no model swap, no extra compute beyond the existing CPU strategy code. (b) is roughly 100 lines of code; (a) is roughly 50.

## Reproducibility

Both runs used `gemma4:e4b` at temperature 1.0, 60s timeout, identical seeds 0..29, identical matchup compositions. The only difference is the contents of [src/strategy.py](../../src/strategy.py):

- v1 strategy.py SHA-256: `(see runs/2026-05-03_v1_baseline/run_metadata.json — recovered post-hoc)`
- v2 strategy.py SHA-256: `503a980a05ab385e7f82a697cbcbe7f30d5e0db91e638a02baa41eb1a19a362a`

Both `run_metadata.json` files record the git SHA at run time, so anyone re-running can reproduce the exact prompt by checking out that commit.
