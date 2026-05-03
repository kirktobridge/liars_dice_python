# Gemma Performance Analysis

Empirical research on how `gemma4:e4b` plays Liar's Dice, what fails, and which interventions move the needle. Each subdirectory under [runs/](runs/) is one self-contained experiment: report, raw aggregate JSON, run metadata, and (gitignored) raw decision-by-decision trace JSONL.

## Run index

| Run | Date | Intervention | Headline | Win rate |
|---|---|---|---|---|
| [2026-05-03_v1_baseline](runs/2026-05-03_v1_baseline/report.md) | 2026-05-03 | No changes — first measurement | 22.5% bids count=1, ~50% reflexive challenges, no archetype adaptation | 0/180 |

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
