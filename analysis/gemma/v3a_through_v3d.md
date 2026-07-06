# v3a → v3d — Where Does the Lift Actually Come From?

**Four prompt conditions, same model (`gemma4:e4b`), same matchups, same engine, same `strategy.py` SHA (`533cdc64`), `think=true` throughout. 360 games per condition, 1,440 games and ~27,500 LLM decisions in total.** The interventions are nested — each condition adds one informational layer on top of the previous — so the win-rate curve isolates *which* layer is doing the work.

Per-condition reports: [v3a minimal](runs/2026-05-05_v3a_minimal/report.md) · v3b profile ([p1](runs/2026-05-05_v3b_profile_p1/report.md) [p2](runs/2026-05-05_v3b_profile_p2/report.md) [p3](runs/2026-05-05_v3b_profile_p3/report.md) [p4](runs/2026-05-05_v3b_profile_p4/report.md)) · v3c standing-prob ([p1](runs/2026-05-05_v3c_standing-prob_p1/report.md) [p2](runs/2026-05-05_v3c_standing-prob_p2/report.md) [p3](runs/2026-05-05_v3c_standing-prob_p3/report.md) [p4](runs/2026-05-05_v3c_standing-prob_p4/report.md)) · v3d anchors ([p1](runs/2026-05-05_v3d_anchors_p1/report.md) [p2](runs/2026-05-05_v3d_anchors_p2/report.md) [p3](runs/2026-05-05_v3d_anchors_p3/report.md) [p4](runs/2026-05-05_v3d_anchors_p4/report.md)).

## TL;DR

```
  win rate
    30% ┤                                   ●  28.3%  (anchors)
    25% ┤
    20% ┤                                              (v2 anchors: 21.1%)
    15% ┤
    10% ┤
     5% ┤                       ●  6.1%
        ┤        ●  3.6%               (standing-prob)
     0% ┤●  1.1%        (profile)
        └─────────────────────────────────────────
         minimal  profile  std-prob   anchors
```

The gradient is monotonic and large: **1.1% → 3.6% → 6.1% → 28.3%**. The big step happens between standing-prob and anchors (+22pp), but every layer adds signal. The Wilson 95% CIs don't overlap between any adjacent pair, even with the conservative effective sample sizes from the seed reuse (see Caveats).

## Headline numbers

| Condition | Games | Wins | Win rate | 95% Wilson CI |
|---|---:|---:|---:|---:|
| **(a) minimal** — rules + dice + history + legality | 360 | 4 | **1.1%** | 0.4 – 2.8% |
| **(b) profile** — (a) + per-opponent aggression & challenge rate | 360 | 13 | **3.6%** | 2.1 – 6.1% |
| **(c) standing-prob** — (b) + truth probability of standing bid | 360 | 22 | **6.1%** | 4.1 – 9.1% |
| **(d) anchors** — (c) + v2 sizing & plausibility cues | 360 | 102 | **28.3%** | 23.9 – 33.2% |
| _v2 reference (no thinking)_ | _180_ | _38_ | _21.1%_ | _15.7 – 28.0%_ |

v3d at 28.3% is meaningfully above v2's 21.1%, with confidence intervals just touching. The full v3d prompt differs from v2 in two ways: `think=true` (the model emits a separate reasoning channel) and the format instruction is rephrased ("the response field must contain only valid JSON" instead of "no explanation"). The bulk of the lift is most likely the thinking channel itself — Gemma can reason at length without polluting the answer.

## Per-matchup win rate

| Matchup | minimal | profile | standing-prob | anchors |
|---|---:|---:|---:|---:|
| vs 4× Salty Veteran | 0/60 (0%) | 0/60 (0%) | 3/60 (5%) | 10/60 (**17%**) |
| vs 4× Reckless Buccaneer | 1/60 (2%) | 5/60 (8%) | 7/60 (12%) | 26/60 (**43%**) |
| vs 4× Crafty Captain | 0/60 (0%) | 2/60 (3%) | 3/60 (5%) | 16/60 (**27%**) |
| vs 4× Stoic Quartermaster | 0/60 (0%) | 0/60 (0%) | 1/60 (2%) | 7/60 (**12%**) |
| vs 4× Wild Card | 2/60 (3%) | 5/60 (8%) | 6/60 (10%) | 28/60 (**47%**) |
| vs 1 of each archetype | 1/60 (2%) | 1/60 (2%) | 2/60 (3%) | 15/60 (**25%**) |

The matchup ordering is stable across conditions — chaotic opponents (Reckless, Wild Card) are easiest, disciplined opponents (Salty, Stoic, Mixed-with-Crafty) hardest. Anchors close the gap on the hard matchups (vs Salty: 0% → 17%, vs Stoic: 0% → 12%) but don't reverse it.

## Mean finish position (1 = eliminated first, 5 = winner)

| Matchup | minimal | profile | standing-prob | anchors |
|---|---:|---:|---:|---:|
| vs Salty | 1.15 | 1.18 | 1.55 | **2.93** |
| vs Reckless | 1.52 | 1.80 | 2.27 | **3.63** |
| vs Crafty | 1.25 | 1.22 | 1.62 | **3.25** |
| vs Stoic | 1.02 | 1.02 | 1.32 | **2.43** |
| vs Wild Card | 1.50 | 1.88 | 2.35 | **3.62** |
| vs Mixed | 1.33 | 1.33 | 1.82 | **3.57** |

In (a) and (b) Gemma is eliminated essentially first in every game. By (c) she's lasting longer. By (d) she's mid-table or winning outright. The standing-prob cue alone (c) gets her off the elimination floor; the sizing anchor (d) is what makes her competitive.

## Behavioural fingerprints

| Metric | minimal | profile | standing-prob | anchors |
|---|---:|---:|---:|---:|
| Challenge rate | 26.1% | 27.7% | 17.1% | **17.9%** |
| Challenge accuracy | 12.3% | 14.6% | 35.2% | **54.3%** |
| Mean bid aggression (claim / total dice) | 0.20 | 0.22 | 0.24 | **0.36** |
| Median bid aggression | 0.19 | 0.21 | 0.23 | **0.34** |
| Spot-on calls | 100 | 89 | **839** | 294 |
| Fallback rate | 0.07% | 0.06% | 0.09% | 0.04% |
| Mean LLM latency | 22.5s | 27.3s | 24.9s | 23.2s |
| Wall-clock total | 44.7h | 51.7h | 48.8h | 36.2h |

Three signals stand out:

1. **Challenge accuracy more than triples between (b) and (c)** — 14.6% → 35.2%. The probability cue is the single biggest contributor to better challenge decisions. Profile information (opponent's aggression label, observed challenge rate) didn't help her decide when to call; a number for the standing bid's truth probability did.
2. **Bid aggression only moves between (c) and (d)** — 0.24 → 0.36. Without the explicit sizing anchor she under-bids by ~40%, leaving easy gimmes for opponents. The sizing anchor pulls her right onto the 1/3 baseline.
3. **Standing-prob over-uses spot-on** — 839 calls vs ~100–300 in the other conditions, with only 7.4% accuracy. The truth probability number plausibly looks to Gemma like a spot-on cue ("if probability is high, the count is exactly right"). v3d's plausibility-cue framing (verbal, not numeric) doesn't trigger this and spot-on calls fall back to 294 with 14% accuracy. This is a hint that the *form* of the probability information matters as much as the content.

The fallback rate is essentially zero across all four conditions — JSON output integrity was never the issue at this model size.

Latency is high across the board (~22–27s) because thinking adds 2,200–2,800 chars of reasoning to every decision. Anchors is the *fastest* condition despite having the longest prompt, because Gemma wins more often and games end in fewer rounds.

## Does Gemma actually use the anchors, or just pattern-match them?

This is the core question the GUIDE flagged: when we hand Gemma the answer, does she still think, or does she just copy the suggestion? With `think=true` captured we can finally check.

**Anchor-citation rates in the v3d thinking channel** (n=5,088 traces with non-empty thinking):

| Phrase quoted in Gemma's thinking | Trace fraction |
|---|---:|
| `truth probability` | **49.7%** |
| `baseline` | 46.9% |
| `plausibility cue` | 31.4% |
| `sizing guide` | 26.0% |
| `over-claim` | 20.5% |
| `safe opening bid is around` | 17.5% |
| `under-claim` | 0.4% |

Roughly half of all v3d decisions show Gemma *literally citing* the truth-probability number in her reasoning. About a third explicitly cite the plausibility cue. This isn't an input-handler — she's reading the anchor, restating it, and reasoning around it. Representative excerpts:

- **(d) anchors** — _"Given the high plausibility (0.92 truth probability mentioned in the history, and the structural plausibility cue), challenging is a risky move. I should avoid challenging unless I have strong counter-evidence."_
- **(c) standing-prob** — _"Given the 0.98 probability that the bid is true, challenging is risky. I should only challenge if I believe the bid is significantly false, which is not the case here."_
- **(b) profile** — _"R4's bid (4 sixes) is strong but potentially high bluffing. … I am playing against 'Reckless Buccaneers' who are generally unpredictable (33% challenge rate)."_
- **(a) minimal** — _"Challenge: I can challenge RB 4's bid (4 sixes). This is viable. Spot-on: I can spot-on RB 4's bid (4 sixes). This is viable. Bid/Raise: I must raise or bid."_ Reasoning about *which legal options exist*, not which is best.

The (a)→(d) trajectory in the thinking content is just as clean as the win-rate trajectory: she goes from enumerating legal moves to citing probability numbers to integrating multiple anchors into a coherent decision.

A genuine input-handler test would have shown her win-rate climb with the anchors *and* her thinking length collapse (no need to think when the answer is given). It didn't — thinking stays ~2,300 chars across all four conditions. She thinks just as much when given anchors; she just thinks *about* them rather than from first principles.

## What this says about the cognition-vs-input-handler concern

The GUIDE.md from earlier this run flagged a worry: as anchors get more opinionated, the LLM asymptotes to "input handler for CPUStrategy." That concern was fair as a hypothesis, but the v3 data argues against it being the operating regime at this model size:

- If she were just pattern-matching the anchor output, (a) would not be at 1.1% — she could derive the same play from rules + dice. She can't. Without the anchors she barely scores.
- If she were just copying the suggestion, anchor-citation rate in thinking would be near 100% and reasoning length would shrink. Citation is 50% (truth-prob) / 31% (plausibility) and length is unchanged.
- The (c)→(d) gap (6.1% → 28.3%) is real signal about her ability to *combine* information she's given. (c) had the standing-bid probability but no sizing; she fixed her challenge decisions (12.3% → 35.2% accuracy) but not her bid sizing (still 0.24 mean aggression). (d) added the sizing anchor and she immediately moved to 0.36 — using both pieces.

The honest framing: at `gemma4:e4b` she **cannot derive Liar's Dice play from first principles**, but given structured probability/plausibility cues she **does reason with them**, not just echo them. A larger model might compute the same anchors on its own. We can't test that here.

## Caveats

- **Seed reuse in pieces.** v3b/c/d each ran as 4 pieces of 15 games-per-matchup; **all 4 pieces used the same seeds 0..14**. The 4× replication exposes Gemma's per-decision variance at fixed opponent dice, not 360 truly independent game contexts. Wilson CIs above treat trials as independent, which is approximately right for LLM variance (temp=1.0) but somewhat optimistic. v3a (one full 60-game run, seeds 0..59) is the only condition with 60 distinct dice realizations per matchup. The headline gradient is robust to even a 4× effective-n shrink, but tighter cross-condition CIs would require matched seed coverage.
- **v3d ≠ v2.** Strategy SHA differs (think-aware prompt) so v3d's +7pp over v2 mixes the thinking lift with the format-line rewording. They are not strictly comparable.
- **Latency caveat.** All four runs averaged 22–27s/decision; v2 was 9.27s. Thinking is expensive. The wall-clock for a full v3 condition (~40h) makes this a not-cheap experiment to repeat.
- **Spot-on anomaly in (c).** The 839 spot-on calls in standing-prob are likely a misread of the probability cue; the prompt should clarify that high-probability bids are not the same as spot-on opportunities. Worth a follow-up — both a v3e prompt tweak and digging into the thinking traces where spot-on was called to see what reasoning chain produced them.

## Reproducibility

- All four conditions used: `gemma4:e4b`, temperature 1.0, timeout 60s, think=true, strategy SHA `533cdc645ed3daa61e90e256cf773fecbbf8920ea08b85d911723e768e539bb4`, code SHA `6dd685ca41a07acdda433b24d2fa8bb8878822e6`.
- Six matchups identical to v1/v2.
- Each `run_metadata.json` carries `prompt_condition`, `think`, `strategy_module_sha256`, `code_sha_at_run_time`, and the full command line. Re-running with the same `--prompt-condition` and the same git SHA reproduces the prompt verbatim.
- `traces.jsonl` for all 14 run directories carries the full prompt, response, and thinking per decision (~5–7 MB per piece, ~26 MB for the single v3a run). Gitignored.
