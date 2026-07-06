# Gemma Performance Analysis

Empirical research on how `gemma4:e4b` plays Liar's Dice, what fails, and which interventions move the needle. Each subdirectory under [runs/](runs/) is one self-contained experiment: report, raw aggregate JSON, run metadata, and (gitignored) raw decision-by-decision trace JSONL.

## Run index

| Run | Date | Intervention | Headline | Win rate |
|---|---|---|---|---|
| [2026-05-03_v1_baseline](runs/2026-05-03_v1_baseline/report.md) | 2026-05-03 | No changes — first measurement | 22.5% bids count=1, ~50% reflexive challenges, no archetype adaptation | 0/180 |
| [2026-05-03_v2_prompt-anchors](runs/2026-05-03_v2_prompt-anchors/report.md) | 2026-05-04 | Legality constraints + sizing anchor + plausibility cue + retry loop | All three v1 failure modes essentially closed; lifts above 20% random baseline | **38/180 (21.1%)** |
| [2026-05-05_v3a_minimal](runs/2026-05-05_v3a_minimal/report.md) | 2026-05-05 | Strip all anchors; rules + dice + history + legality only; `think=true` | At gemma4:e4b she cannot derive Liar's Dice play from rules + dice; thinks but inefficiently | 4/360 (1.1%) |
| 2026-05-08 v3b_profile ([p1](runs/2026-05-05_v3b_profile_p1/report.md) [p2](runs/2026-05-05_v3b_profile_p2/report.md) [p3](runs/2026-05-05_v3b_profile_p3/report.md) [p4](runs/2026-05-05_v3b_profile_p4/report.md)) | 2026-05-08…12 | (a) + per-opponent aggression label + observed challenge rate | Profile info alone barely helps; challenge accuracy still 14% | 13/360 (3.6%) |
| 2026-05-16 v3c_standing-prob ([p1](runs/2026-05-05_v3c_standing-prob_p1/report.md) [p2](runs/2026-05-05_v3c_standing-prob_p2/report.md) [p3](runs/2026-05-05_v3c_standing-prob_p3/report.md) [p4](runs/2026-05-05_v3c_standing-prob_p4/report.md)) | 2026-05-16…20 | (b) + truth probability of standing bid only (no sizing/plausibility) | Challenge accuracy ~3× to 35%; bid aggression still under-claims; 839 spot-on misreads | 22/360 (6.1%) |
| 2026-05-22 v3d_anchors ([p1](runs/2026-05-05_v3d_anchors_p1/report.md) [p2](runs/2026-05-05_v3d_anchors_p2/report.md) [p3](runs/2026-05-05_v3d_anchors_p3/report.md) [p4](runs/2026-05-05_v3d_anchors_p4/report.md)) | 2026-05-22…26 | Full v2 sizing + plausibility anchors + think=true | Challenge accuracy 54%, aggression onto 1/3 baseline, thinking literally cites anchors 50% of the time | **102/360 (28.3%)** |

## Cross-run comparisons

- [v1_vs_v2.md](v1_vs_v2.md) — Did the prompt intervention work? (Yes: 0/180 → 38/180.)
- [v3a_through_v3d.md](v3a_through_v3d.md) — Four-condition prompt ablation. Where does the lift actually come from? Monotonic gradient 1.1% → 3.6% → 6.1% → 28.3%. With `think=true` we can see Gemma cite the anchors directly in her reasoning ~50% of the time — she uses them, doesn't just echo them.

## Conceptual guide

- [GUIDE.md](GUIDE.md) — what we test and why, what Gemma sees / doesn't see, the opinionation-vs-cognition tension, and what it'd take to extend this to other local LLMs.

## How to run a new experiment

```bash
OLLAMA_URL=http://172.19.176.1:11434/api/generate \
  .venv/bin/python scripts/gemma_analysis.py \
  --run-name 2026-05-03_v2_prompt-anchors \
  --intervention "legality validation + sizing anchor + plausibility cue"
```

The driver creates `analysis/gemma/runs/<run-name>/` and writes:

- **report.md** — readable behavioural report (committed)
- **results.json** — aggregate stats per matchup (committed)
- **run_metadata.json** — model, temperature, command line, git SHA, strategy.py SHA-256, total decisions, duration (committed)
- **traces.jsonl** — every prompt + response + parse outcome (gitignored; ~2.6 MB per 180-game run)
- **run.log** — tee'd stdout (committed; useful for crash forensics)

Naming convention: `YYYY-MM-DD_v<N>_<slug>` — date first so they sort chronologically; `vN` matches what we'd cite in a comparison report; slug describes the *intervention*, not the date.

The script refuses to write into a non-empty run directory unless `--allow-overwrite` is passed, so prior runs are protected.

## Comparing runs

`run_metadata.json` records `strategy_module_sha256` for `src/strategy.py`. Two runs with the same SHA tested the same prompt; differences in their results are noise. Two runs with different SHAs tested different prompts; differences are signal (modulo the small-sample noise floor reported in each `report.md`'s Limitations section).

## What's *not* in here

- **Production telemetry** — this is offline analysis only. Live web-game LLM telemetry, if/when added, belongs under `web/` or wherever the live logging system lands, not here.
- **CPU-vs-CPU tournament data** — covered by `tournament_stats.html` at the repo root and the `/tournament` web endpoint; this folder is specifically about the LLM player.
