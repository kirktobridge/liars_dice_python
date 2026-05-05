"""Empirical Gemma performance analysis vs CPU archetypes.

Runs N games per matchup (1 LLM player + 4 CPU players), captures every Gemma
prompt/response via the LLM debug listener, aggregates win rates and behavioral
metrics from the tournament DataFrames, and emits a self-contained run directory
under analysis/gemma/runs/<run-name>/ containing report.md, results.json,
traces.jsonl (gitignored), run.log, and run_metadata.json.

Usage:
    # Default: timestamped run name like 2026-05-03_143015
    .venv/bin/python scripts/gemma_analysis.py

    # Recommended: name the run after the intervention being tested
    .venv/bin/python scripts/gemma_analysis.py --run-name 2026-05-03_v2_prompt-anchors

    # Smoke run
    .venv/bin/python scripts/gemma_analysis.py --run-name smoke-test --games-per-matchup 1

    # Subset of matchups
    .venv/bin/python scripts/gemma_analysis.py --matchups vs_salty,vs_crafty
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import random as _random  # noqa: E402

import pandas as pd  # noqa: E402

import llm_client  # noqa: E402
from llm_client import set_llm_debug_listener  # noqa: E402
import constants as Constants  # noqa: E402
from ollama_lifecycle import OllamaSession  # noqa: E402
from Player import Player  # noqa: E402
from stats_schema import rounds_to_df, eliminations_to_df  # noqa: E402
from strategy import LLMStrategy, Personality  # noqa: E402
from tournament import run_game  # noqa: E402

logger = logging.getLogger("gemma_analysis")

GEMMA_NAME = "Gemma"
LLM_TEMPERATURE = 1.0   # Google guidance for Gemma
LLM_TIMEOUT = 60.0

# ---------------------------------------------------------------------------
# Matchup definitions
# ---------------------------------------------------------------------------

ARCHETYPE_BY_LABEL = {a["label"]: a for a in Constants.ARCHETYPES}


def _cpu_config(name: str, archetype_label: str) -> dict:
    spec = ARCHETYPE_BY_LABEL[archetype_label]
    return {
        "name": name,
        "player_type": "CPU",
        "risk_appetite": spec["risk"],
        "attentiveness_score": spec["att"],
        "bluff_frequency": spec["bluff"],
        "archetype": archetype_label,
    }


def _gemma_config() -> dict:
    return {"name": GEMMA_NAME, "player_type": "LLM", "llm_model": Constants.LLM_MODEL}


def _homogeneous(label: str) -> list[dict]:
    return [
        _gemma_config(),
        _cpu_config(f"{label} 1", label),
        _cpu_config(f"{label} 2", label),
        _cpu_config(f"{label} 3", label),
        _cpu_config(f"{label} 4", label),
    ]


def _mixed() -> list[dict]:
    return [
        _gemma_config(),
        _cpu_config("Salty", "Salty Veteran"),
        _cpu_config("Reckless", "Reckless Buccaneer"),
        _cpu_config("Crafty", "Crafty Captain"),
        _cpu_config("Stoic", "Stoic Quartermaster"),
    ]


MATCHUPS: dict[str, dict] = {
    "vs_salty":     {"label": "vs 4× Salty Veteran",       "configs": _homogeneous("Salty Veteran")},
    "vs_reckless":  {"label": "vs 4× Reckless Buccaneer",  "configs": _homogeneous("Reckless Buccaneer")},
    "vs_crafty":    {"label": "vs 4× Crafty Captain",      "configs": _homogeneous("Crafty Captain")},
    "vs_stoic":     {"label": "vs 4× Stoic Quartermaster", "configs": _homogeneous("Stoic Quartermaster")},
    "vs_wildcard":  {"label": "vs 4× Wild Card",           "configs": _homogeneous("Wild Card")},
    "vs_mixed":     {"label": "vs 1 of each archetype",    "configs": _mixed()},
}

# ---------------------------------------------------------------------------
# Trace capture: hook into llm_client debug events
# ---------------------------------------------------------------------------


@dataclass
class _PendingDecision:
    prompt: str = ""
    chunks: list[str] = field(default_factory=list)
    thinking_chunks: list[str] = field(default_factory=list)
    started_at: float = 0.0
    error: str | None = None


@dataclass
class TraceRecord:
    matchup: str
    seed: int
    prompt: str
    response: str
    thinking: str
    parsed_action: str | None
    parsed_count: int | None
    parsed_face: int | None
    fallback: bool
    latency_s: float
    error: str | None


class TraceCapture:
    """Listens to llm_client debug events and pairs prompt/done into TraceRecord rows."""

    def __init__(self, jsonl_path: Path) -> None:
        self.jsonl_path = jsonl_path
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.jsonl_path.open("a", encoding="utf-8")
        self._pending = _PendingDecision()
        self._matchup: str = ""
        self._seed: int = -1
        self.records: list[TraceRecord] = []
        # Tracks whether a decision is currently in flight (between 'prompt' and 'done').
        self._in_flight = False

    def set_context(self, matchup: str, seed: int) -> None:
        self._matchup = matchup
        self._seed = seed

    def __call__(self, kind: str, payload: dict) -> None:
        if kind == "prompt":
            # Start a new decision. If a previous one was never closed, drop it.
            self._pending = _PendingDecision(
                prompt=payload.get("prompt", ""),
                started_at=time.monotonic(),
            )
            self._in_flight = True
        elif kind == "token":
            if self._in_flight:
                self._pending.chunks.append(payload.get("text", ""))
        elif kind == "thinking":
            if self._in_flight:
                self._pending.thinking_chunks.append(payload.get("text", ""))
        elif kind == "error":
            if self._in_flight:
                self._pending.error = payload.get("message", "unknown")
                self._finalize()
        elif kind == "done":
            if self._in_flight:
                self._finalize()

    def _finalize(self) -> None:
        elapsed = time.monotonic() - self._pending.started_at
        response_text = "".join(self._pending.chunks)
        action, count, face = _parse_response(response_text)
        # Fallback iff the LLM strategy would have fallen back: error, no JSON, unknown
        # action, OR an illegal action (CHALLENGE / SPOT_ON on round open).
        is_round_open = "Previous action: action=start" in self._pending.prompt.lower()
        illegal_on_open = is_round_open and action in ("challenge", "spot_on")
        fallback = bool(self._pending.error) or action is None or illegal_on_open
        rec = TraceRecord(
            matchup=self._matchup,
            seed=self._seed,
            prompt=self._pending.prompt,
            response=response_text,
            thinking="".join(self._pending.thinking_chunks),
            parsed_action=action,
            parsed_count=count,
            parsed_face=face,
            fallback=fallback,
            latency_s=elapsed,
            error=self._pending.error,
        )
        self.records.append(rec)
        self._fp.write(json.dumps(rec.__dict__, ensure_ascii=False) + "\n")
        self._fp.flush()
        self._pending = _PendingDecision()
        self._in_flight = False

    def close(self) -> None:
        self._fp.close()


_ACTION_KEYS = {"bid", "raise", "challenge", "spot_on"}


def _parse_response(text: str) -> tuple[str | None, int | None, int | None]:
    """Mirror LLMStrategy._parse_response. Returns (action, count, face) or (None, None, None)."""
    if not text:
        return None, None, None
    stripped = text.strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not m:
            return None, None, None
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return None, None, None
    if not isinstance(data, dict):
        return None, None, None
    raw_action = str(data.get("action", "")).lower().replace(" ", "_")
    if raw_action not in _ACTION_KEYS:
        return None, None, None
    count = data.get("count")
    face = data.get("face")
    try:
        count = int(count) if count is not None else None
    except (TypeError, ValueError):
        count = None
    try:
        face = int(face) if face is not None else None
    except (TypeError, ValueError):
        face = None
    return raw_action, count, face


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return 0.0, 0.0
    phat = successes / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _safe_mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


# ---------------------------------------------------------------------------
# Per-matchup analysis
# ---------------------------------------------------------------------------


@dataclass
class MatchupStats:
    key: str
    label: str
    n_games: int
    win_count: int
    win_rate: float
    win_ci_lo: float
    win_ci_hi: float
    mean_finish: float | None
    mean_rounds: float
    fallback_rate: float
    n_decisions: int
    action_dist: dict[str, float]
    mean_aggression: float | None
    challenges_called: int
    challenge_success_rate: float | None
    spot_on_called: int
    spot_on_success_rate: float | None
    times_caught_bluffing: int
    bids_against_gemma: int
    caught_rate: float | None
    mean_latency_s: float
    sample_traces: list[dict]


def analyze_matchup(
    key: str,
    matchup: dict,
    df_games,
    df_rounds,
    df_elims,
    traces: list[TraceRecord],
) -> MatchupStats:
    n_games = len(df_games)
    win_mask = df_games["winner"] == GEMMA_NAME
    win_count = int(win_mask.sum())
    win_rate = win_count / n_games if n_games else 0.0
    lo, hi = wilson_ci(win_count, n_games)

    elims_g = df_elims[df_elims["player_name"] == GEMMA_NAME]
    mean_finish = float(elims_g["finishing_position"].mean()) if len(elims_g) else None

    mean_rounds = float(df_games["rounds"].mean()) if n_games else 0.0

    # --- Trace-derived metrics
    mt = [t for t in traces if t.matchup == key]
    n_decisions = len(mt)
    fallbacks = sum(1 for t in mt if t.fallback)
    fallback_rate = fallbacks / n_decisions if n_decisions else 0.0

    valid = [t for t in mt if not t.fallback and t.parsed_action]
    action_counter = Counter(t.parsed_action for t in valid)
    total_valid = sum(action_counter.values())
    action_dist = (
        {a: action_counter.get(a, 0) / total_valid for a in ("bid", "raise", "challenge", "spot_on")}
        if total_valid
        else {a: 0.0 for a in ("bid", "raise", "challenge", "spot_on")}
    )

    # Aggression: claimed_count / (total dice on table). We don't directly know table size
    # at decision time from the trace; approximate using the prompt ("Total dice held by
    # other players: N") + the dice list length.
    aggressions: list[float] = []
    for t in valid:
        if t.parsed_action not in ("bid", "raise") or t.parsed_count is None:
            continue
        total_dice = _extract_total_dice_from_prompt(t.prompt)
        if total_dice and total_dice > 0:
            aggressions.append(t.parsed_count / total_dice)
    mean_aggression = _safe_mean(aggressions)

    mean_latency = _safe_mean([t.latency_s for t in mt]) or 0.0

    # --- Round-level metrics: Gemma as challenger / spot-on caller
    g_caller = df_rounds[df_rounds["action_caller"] == GEMMA_NAME]
    g_chal = g_caller[g_caller["action_type"] == "challenge"]
    g_spot = g_caller[g_caller["action_type"] == "spot_on"]
    challenge_success_rate = (
        float(g_chal["challenge_succeeded"].astype(float).mean()) if len(g_chal) else None
    )
    spot_on_success_rate = (
        float(g_spot["challenge_succeeded"].astype(float).mean()) if len(g_spot) else None
    )

    # --- Times Gemma got caught bluffing (was the bidder when a challenge succeeded)
    # round_loser column holds the bidder iff challenge succeeded; the (challenge_called event)
    # logged the bidder under self._bidder_name. We approximate: round_loser==Gemma AND
    # action_type=='challenge' AND challenge_succeeded==True.
    caught = df_rounds[
        (df_rounds["round_loser"] == GEMMA_NAME)
        & (df_rounds["action_type"] == "challenge")
        & (df_rounds["challenge_succeeded"] == True)  # noqa: E712
    ]
    times_caught_bluffing = int(len(caught))
    # Total challenges resolved against Gemma: the bidder loses when succeeded=True; the
    # challenger loses when succeeded=False. So bids-against-Gemma = caught + (Gemma was
    # bidder, challenger lost). The bidder isn't directly in df_rounds; infer: when a
    # challenge resolves, the bidder is whoever isn't the action_caller. Since we only
    # store action_caller (challenger), we can only count rows where challenge happened
    # AND (round_loser==Gemma OR action_caller!=Gemma) — but that's noisy. Skip the
    # denominator for non-caught case; report just times-caught and any clean rate when
    # we can compute it.
    chal_against_gemma = df_rounds[
        (df_rounds["action_type"] == "challenge")
        & (df_rounds["challenge_succeeded"] == False)  # Gemma was bidder, won
        & (df_rounds["action_caller"] != GEMMA_NAME)
    ]
    # Cannot fully attribute survives without per-round bidder column → leave as None.
    bids_against_gemma = times_caught_bluffing  # only the caught half is reliably attributable
    caught_rate = None

    # --- Sample traces: pick up to 3 representative ones (1 valid action, 1 fallback if any, 1 random)
    sample_traces: list[dict] = []
    valid_sample = next((t for t in mt if not t.fallback), None)
    if valid_sample is not None:
        sample_traces.append(_trace_to_dict(valid_sample))
    fallback_sample = next((t for t in mt if t.fallback), None)
    if fallback_sample is not None:
        sample_traces.append(_trace_to_dict(fallback_sample))
    if len(sample_traces) < 3 and len(mt) > len(sample_traces):
        # Pick a longer/more interesting prompt
        candidates = [t for t in mt if t not in (valid_sample, fallback_sample)]
        if candidates:
            picked = max(candidates, key=lambda t: len(t.prompt))
            sample_traces.append(_trace_to_dict(picked))

    return MatchupStats(
        key=key,
        label=matchup["label"],
        n_games=n_games,
        win_count=win_count,
        win_rate=win_rate,
        win_ci_lo=lo,
        win_ci_hi=hi,
        mean_finish=mean_finish,
        mean_rounds=mean_rounds,
        fallback_rate=fallback_rate,
        n_decisions=n_decisions,
        action_dist=action_dist,
        mean_aggression=mean_aggression,
        challenges_called=int(len(g_chal)),
        challenge_success_rate=challenge_success_rate,
        spot_on_called=int(len(g_spot)),
        spot_on_success_rate=spot_on_success_rate,
        times_caught_bluffing=times_caught_bluffing,
        bids_against_gemma=bids_against_gemma,
        caught_rate=caught_rate,
        mean_latency_s=mean_latency,
        sample_traces=sample_traces,
    )


_TOTAL_DICE_RE = re.compile(r"Total dice held by other players:\s*(\d+)")


def _extract_total_dice_from_prompt(prompt: str) -> int | None:
    m = _TOTAL_DICE_RE.search(prompt)
    if not m:
        return None
    others = int(m.group(1))
    # Gemma's own dice list is on a "Your dice: [...]" line; count items.
    md = re.search(r"Your dice:\s*\[([^\]]*)\]", prompt)
    own = 0
    if md:
        own = len([x for x in md.group(1).split(",") if x.strip()])
    return others + own


def _trace_to_dict(t: TraceRecord) -> dict:
    return {
        "matchup": t.matchup,
        "seed": t.seed,
        "prompt": t.prompt,
        "response": t.response,
        "parsed_action": t.parsed_action,
        "parsed_count": t.parsed_count,
        "parsed_face": t.parsed_face,
        "fallback": t.fallback,
        "latency_s": round(t.latency_s, 3),
        "error": t.error,
    }


# ---------------------------------------------------------------------------
# Report emission
# ---------------------------------------------------------------------------


def write_report(
    out_path: Path,
    stats: list[MatchupStats],
    n_games_per_matchup: int,
    started_at: float,
    finished_at: float,
) -> None:
    duration_min = (finished_at - started_at) / 60.0
    lines: list[str] = []
    lines.append("# Gemma vs CPU Archetypes — Empirical Performance Report")
    lines.append("")
    lines.append(
        f"_Generated by [scripts/gemma_analysis.py](scripts/gemma_analysis.py) "
        f"on {time.strftime('%Y-%m-%d', time.localtime(finished_at))}._"
    )
    lines.append("")

    # ---- Summary ----
    lines.append("## Summary")
    lines.append("")
    overall_games = sum(s.n_games for s in stats)
    overall_wins = sum(s.win_count for s in stats)
    overall_decisions = sum(s.n_decisions for s in stats)
    overall_fallback = (
        sum(s.fallback_rate * s.n_decisions for s in stats) / overall_decisions
        if overall_decisions
        else 0.0
    )
    lines.append(
        f"- **Overall win rate**: {overall_wins}/{overall_games} = "
        f"**{overall_wins / overall_games:.1%}** (random baseline for a 5-player table = 20%)"
    )
    lines.append(f"- **Total decisions logged**: {overall_decisions}")
    lines.append(f"- **Overall fallback rate** (Gemma produced unparseable output): {overall_fallback:.1%}")
    lines.append(f"- **Wall-clock**: {duration_min:.1f} min for {overall_games} games")
    lines.append("")

    best = max(stats, key=lambda s: s.win_rate)
    worst = min(stats, key=lambda s: s.win_rate)
    lines.append(
        f"Gemma's strongest matchup is **{best.label}** ({best.win_rate:.1%}); "
        f"weakest is **{worst.label}** ({worst.win_rate:.1%})."
    )
    lines.append("")

    # ---- Methodology ----
    lines.append("## Methodology")
    lines.append("")
    lines.append(f"- **Model**: `{Constants.LLM_MODEL}` via Ollama, temperature {LLM_TEMPERATURE}, timeout {LLM_TIMEOUT}s")
    lines.append(f"- **Sample size**: {n_games_per_matchup} games per matchup × {len(stats)} matchups = {overall_games} games")
    lines.append("- **Table size**: 5 players (1 Gemma + 4 CPUs); 6 dice per player at start")
    lines.append("- **Seeds**: deterministic 0..N-1 per matchup; same dice rolls across matchups for matched seeds")
    lines.append("- **Win-rate confidence**: Wilson 95% interval")
    lines.append(
        "- **Decision capture**: every `query_llm` / `query_llm_stream` call is intercepted "
        "via `set_llm_debug_listener` ([src/llm_client.py](src/llm_client.py)) and written to "
        "`scripts/gemma_traces.jsonl` (gitignored)."
    )
    lines.append("")

    # ---- Aggregate table ----
    lines.append("## Aggregate Results")
    lines.append("")
    lines.append("| Matchup | Games | Win rate (95% CI) | Mean finish | Mean rounds | Fallback | Mean latency |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for s in stats:
        finish_str = f"{s.mean_finish:.2f}" if s.mean_finish is not None else "—"
        lines.append(
            f"| {s.label} | {s.n_games} "
            f"| {s.win_rate:.1%} ({s.win_ci_lo:.1%}–{s.win_ci_hi:.1%}) "
            f"| {finish_str}/5 | {s.mean_rounds:.1f} | {s.fallback_rate:.1%} | {s.mean_latency_s:.2f}s |"
        )
    lines.append("")
    lines.append(
        "_Mean finish: 1 = first eliminated, 5 = winner. Higher is better._"
    )
    lines.append("")

    # ---- Behavioral table ----
    lines.append("## Behavioral Profile")
    lines.append("")
    lines.append("| Matchup | %bid | %raise | %challenge | %spot_on | Aggression | Chal acc | SpotOn acc | Caught bluffing |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in stats:
        a = s.action_dist
        agg = f"{s.mean_aggression:.2f}" if s.mean_aggression is not None else "—"
        chacc = (
            f"{s.challenge_success_rate:.0%} ({s.challenges_called})"
            if s.challenge_success_rate is not None
            else "— (0)"
        )
        soacc = (
            f"{s.spot_on_success_rate:.0%} ({s.spot_on_called})"
            if s.spot_on_success_rate is not None
            else "— (0)"
        )
        lines.append(
            f"| {s.label} | {a['bid']:.0%} | {a['raise']:.0%} "
            f"| {a['challenge']:.0%} | {a['spot_on']:.0%} | {agg} "
            f"| {chacc} | {soacc} | {s.times_caught_bluffing} |"
        )
    lines.append("")
    lines.append(
        "_Aggression = mean(claimed count / total dice on table) on Gemma's bids and raises. "
        "0.33 = matches expected count of any non-1 face; >0.33 = over-claiming. "
        "Chal acc / SpotOn acc parenthetical: number of times Gemma called that action._"
    )
    lines.append("")

    # ---- Per-matchup deep dives ----
    lines.append("## Per-Matchup Deep Dives")
    lines.append("")
    for s in stats:
        lines.append(f"### {s.label}")
        lines.append("")
        lines.append(
            f"Win rate **{s.win_rate:.1%}** ({s.win_count}/{s.n_games}, 95% CI "
            f"{s.win_ci_lo:.1%}–{s.win_ci_hi:.1%})."
        )
        lines.append("")
        lines.append(_per_matchup_prose(s))
        lines.append("")

        if s.sample_traces:
            lines.append("**Sample decision trace:**")
            lines.append("")
            t = s.sample_traces[0]
            lines.append(_trace_block(t))
            lines.append("")

            fb = next((tr for tr in s.sample_traces if tr["fallback"]), None)
            if fb is not None:
                lines.append("**Fallback example (Gemma produced unparseable output):**")
                lines.append("")
                lines.append(_trace_block(fb))
                lines.append("")

    # ---- Cross-cutting observations ----
    lines.append("## Cross-Cutting Observations")
    lines.append("")
    lines.append(_cross_observations(stats))
    lines.append("")

    # ---- Limitations ----
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        f"- **Sample size**: {n_games_per_matchup} games per matchup — confidence intervals "
        "on win rate are wide. Treat ordinal comparisons (best vs worst archetype matchup) as "
        "directional, not significant."
    )
    lines.append(
        "- **Single seed family**: seeds 0..N-1 share dice rolls across matchups. This helps "
        "isolate archetype effects but may bias against rare unlucky seeds."
    )
    lines.append(
        "- **Per-bid attribution**: the round-level collector only stores the *terminal* bidder "
        "and challenger. We can count when Gemma was caught bluffing (challenge succeeded against "
        "her), but not the full denominator of bids she made that survived without challenge. "
        "Aggression is therefore reported per-decision via the trace, not per-round."
    )
    lines.append(
        f"- **Latency variance**: mean {sum(s.mean_latency_s * s.n_decisions for s in stats) / overall_decisions:.2f}s "
        "depends on Ollama's batching and host CPU; cold-start calls are slower."
    )
    lines.append("- **Model drift**: if `gemma4:e4b` is updated upstream, results will not be reproducible.")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def _per_matchup_prose(s: MatchupStats) -> str:
    a = s.action_dist
    parts: list[str] = []
    # Aggressiveness vs baseline 0.33
    if s.mean_aggression is not None:
        if s.mean_aggression > 0.40:
            parts.append(
                f"Aggression {s.mean_aggression:.2f} is well above the no-info baseline (0.33), "
                f"so Gemma is consistently over-claiming against this archetype."
            )
        elif s.mean_aggression < 0.28:
            parts.append(
                f"Aggression {s.mean_aggression:.2f} sits below the no-info baseline (0.33) — "
                f"Gemma plays unusually conservatively here."
            )
        else:
            parts.append(
                f"Aggression {s.mean_aggression:.2f} is close to the no-info baseline (0.33)."
            )
    # Action mix
    if a["challenge"] > 0.20:
        parts.append(f"Challenges fire {a['challenge']:.0%} of decisions — quite trigger-happy.")
    elif a["challenge"] < 0.05:
        parts.append(f"Challenges are rare ({a['challenge']:.0%}) — Gemma rarely calls bluffs.")
    if a["spot_on"] > 0.10:
        parts.append(f"Spot-on calls are unusually frequent ({a['spot_on']:.0%}).")
    if s.fallback_rate > 0.20:
        parts.append(
            f"Fallback rate {s.fallback_rate:.0%} is high — Gemma frequently produced unparseable "
            f"output and the CPU fallback strategy played for her."
        )
    if s.times_caught_bluffing > 0:
        parts.append(
            f"Caught bluffing **{s.times_caught_bluffing}** time(s) — opponents successfully "
            f"challenged her bid."
        )
    return " ".join(parts) if parts else "No notable behavioral deviations from baseline."


def _trace_block(t: dict) -> str:
    prompt = t["prompt"].rstrip()
    response = (t["response"] or "").rstrip()
    parsed = (
        f"`{t['parsed_action']}` "
        + (f"count={t['parsed_count']} face={t['parsed_face']}" if t["parsed_action"] in ("bid", "raise") else "")
    ).strip()
    fb = " (FALLBACK)" if t["fallback"] else ""
    return (
        f"```text\n--- PROMPT (seed {t['seed']}) ---\n{prompt}\n\n"
        f"--- RESPONSE{fb} ({t['latency_s']}s) ---\n{response}\n\n"
        f"--- PARSED ---\n{parsed or 'unparseable'}\n```"
    )


def _cross_observations(stats: list[MatchupStats]) -> str:
    parts: list[str] = []
    # Best vs worst
    best = max(stats, key=lambda s: s.win_rate)
    worst = min(stats, key=lambda s: s.win_rate)
    parts.append(
        f"- Win-rate spread: **{best.win_rate:.1%}** (vs {best.label.split('vs ')[-1]}) "
        f"down to **{worst.win_rate:.1%}** (vs {worst.label.split('vs ')[-1]}). "
        f"Across all matchups Gemma's mean finish is "
        f"{_safe_mean([s.mean_finish for s in stats]):.2f}/5."
    )
    # Aggression spread
    aggs = [s.mean_aggression for s in stats if s.mean_aggression is not None]
    if aggs:
        parts.append(
            f"- Aggression range: {min(aggs):.2f}–{max(aggs):.2f}. "
            "Gemma's bidding intensity is fairly consistent across opponents — she does not "
            "appear to adapt aggression to opponent archetype within the prompt window."
        )
    # Challenge tendency
    avg_chal = _safe_mean([s.action_dist["challenge"] for s in stats])
    parts.append(f"- Mean challenge frequency across matchups: {avg_chal:.0%}.")
    # Fallback patterns
    high_fb = [s for s in stats if s.fallback_rate > 0.15]
    if high_fb:
        parts.append(
            "- Matchups with elevated fallback rate (>15%): "
            + ", ".join(f"{s.label} ({s.fallback_rate:.0%})" for s in high_fb)
            + ". This usually reflects malformed JSON, not bad strategy."
        )
    else:
        parts.append("- Fallback rate stays under 15% in every matchup — JSON formatting is reliable.")
    # Caught bluffing
    total_caught = sum(s.times_caught_bluffing for s in stats)
    parts.append(f"- Times caught bluffing across all games: **{total_caught}**.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _default_run_name() -> str:
    return time.strftime("%Y-%m-%d_%H%M%S", time.localtime())


def _git_sha() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return None


def _strategy_module_sha256() -> str:
    """SHA-256 of src/strategy.py — lets a comparison report tell whether the prompt actually
    changed between runs without having to diff git history manually."""
    p = REPO_ROOT / "src" / "strategy.py"
    return hashlib.sha256(p.read_bytes()).hexdigest()


class _TeeLogHandler(logging.Handler):
    """Logging handler that mirrors records to both an in-memory list and a file path,
    flushing each record immediately so a tail -f works."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = path.open("a", encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._fp.write(msg + "\n")
            self._fp.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            self._fp.close()
        finally:
            super().close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-per-matchup", type=int, default=30)
    parser.add_argument(
        "--matchups",
        type=str,
        default=",".join(MATCHUPS.keys()),
        help="Comma-separated subset of matchup keys to run.",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default=_default_run_name(),
        help="Name of this run. Output goes to analysis/gemma/runs/<run-name>/. "
        "Recommended: YYYY-MM-DD_v<N>_<slug>, e.g. 2026-05-03_v2_prompt-anchors. "
        "Default: timestamped slug (never collides).",
    )
    parser.add_argument(
        "--runs-root",
        type=str,
        default=str(REPO_ROOT / "analysis" / "gemma" / "runs"),
        help="Parent directory under which the run directory is created.",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Permit writing into a run directory that already contains files. "
        "Off by default to protect prior runs.",
    )
    parser.add_argument("--temperature", type=float, default=LLM_TEMPERATURE)
    parser.add_argument("--timeout", type=float, default=LLM_TIMEOUT)
    parser.add_argument(
        "--think",
        action="store_true",
        help="Request the model's reasoning trace (Ollama think=true). Captured into "
        "traces.jsonl as the 'thinking' field. Only useful with reasoning-capable models.",
    )
    parser.add_argument(
        "--intervention",
        type=str,
        default="",
        help="One-line description of what this run is testing (stored in run_metadata.json).",
    )
    args = parser.parse_args()

    selected = [m.strip() for m in args.matchups.split(",") if m.strip()]
    unknown = [m for m in selected if m not in MATCHUPS]
    if unknown:
        print(f"unknown matchups: {unknown}; valid: {list(MATCHUPS)}", file=sys.stderr)
        return 2

    run_dir = Path(args.runs_root) / args.run_name
    if run_dir.exists() and any(run_dir.iterdir()) and not args.allow_overwrite:
        print(
            f"run directory {run_dir} already contains files. "
            f"Pass --allow-overwrite to write anyway, or pick a different --run-name.",
            file=sys.stderr,
        )
        return 2
    run_dir.mkdir(parents=True, exist_ok=True)

    report_path = run_dir / "report.md"
    traces_path = run_dir / "traces.jsonl"
    results_path = run_dir / "results.json"
    metadata_path = run_dir / "run_metadata.json"
    log_path = run_dir / "run.log"

    log_handler = _TeeLogHandler(log_path)
    log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger().addHandler(log_handler)

    logger.info("run name: %s", args.run_name)
    logger.info("output dir: %s", run_dir)

    # Apply LLM tuning to all LLMStrategy instances spawned by run_tournament:
    # monkey-patch __init__ to inject our temperature + timeout.
    _orig_init = LLMStrategy.__init__

    def _patched_init(self, *a, **kw):
        kw.setdefault("temperature", args.temperature)
        kw.setdefault("timeout", args.timeout)
        kw.setdefault("think", args.think)
        _orig_init(self, *a, **kw)

    LLMStrategy.__init__ = _patched_init  # type: ignore[assignment]

    if traces_path.exists():
        traces_path.unlink()
    capture = TraceCapture(traces_path)
    set_llm_debug_listener(capture)

    started = time.monotonic()
    started_wall = time.time()
    matchup_stats: list[MatchupStats] = []

    try:
        with OllamaSession(model=Constants.LLM_MODEL):
            for key in selected:
                m = MATCHUPS[key]
                logger.info("matchup %s — %d games", key, args.games_per_matchup)
                m_started = time.monotonic()

                # Build persistent players ONCE per matchup so personality state is
                # consistent across games (mirrors run_tournament's behavior). Seeded
                # RNG per game inside run_game.
                players = _build_persistent_players(m["configs"])

                game_results = []
                for seed in range(args.games_per_matchup):
                    capture.set_context(matchup=key, seed=seed)
                    result = run_game(seed=seed, num_players=len(players), players=players)
                    game_results.append(result)
                    logger.info(
                        "  seed=%d winner=%s rounds=%d",
                        seed, result["winner"], result["rounds"],
                    )

                df_games, df_rounds, df_elims = _results_to_dfs(game_results)
                stats = analyze_matchup(key, m, df_games, df_rounds, df_elims, capture.records)
                matchup_stats.append(stats)
                elapsed = (time.monotonic() - m_started) / 60.0
                logger.info(
                    "matchup %s done in %.1f min — Gemma %d/%d (%.1f%%)",
                    key, elapsed, stats.win_count, stats.n_games, stats.win_rate * 100,
                )
    finally:
        set_llm_debug_listener(None)
        capture.close()
        LLMStrategy.__init__ = _orig_init  # type: ignore[assignment]

    finished = time.monotonic()
    finished_wall = time.time()
    write_report(report_path, matchup_stats, args.games_per_matchup, started_wall, finished_wall)

    overall_decisions = sum(s.n_decisions for s in matchup_stats)
    overall_wins = sum(s.win_count for s in matchup_stats)
    overall_games = sum(s.n_games for s in matchup_stats)

    results_path.write_text(
        json.dumps(
            {
                "run_name": args.run_name,
                "model": Constants.LLM_MODEL,
                "games_per_matchup": args.games_per_matchup,
                "duration_min": (finished - started) / 60.0,
                "matchups": [_stats_to_dict(s) for s in matchup_stats],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    metadata_path.write_text(
        json.dumps(
            {
                "run_name": args.run_name,
                "intervention": args.intervention,
                "date": time.strftime("%Y-%m-%d", time.localtime(started_wall)),
                "model": Constants.LLM_MODEL,
                "ollama_url": os.environ.get("OLLAMA_URL", "<default>"),
                "temperature": args.temperature,
                "timeout_s": args.timeout,
                "think": args.think,
                "games_per_matchup": args.games_per_matchup,
                "matchups": selected,
                "total_games": overall_games,
                "total_wins": overall_wins,
                "total_decisions_logged": overall_decisions,
                "duration_min": (finished - started) / 60.0,
                "code_sha_at_run_time": _git_sha(),
                "strategy_module_sha256": _strategy_module_sha256(),
                "command_line": " ".join(sys.argv),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    logger.info(
        "run %s complete — Gemma %d/%d wins (%.1f min total)",
        args.run_name, overall_wins, overall_games, (finished - started) / 60.0,
    )
    logger.info("artifacts: %s", run_dir)
    log_handler.close()
    return 0


def _build_persistent_players(configs: list[dict]) -> dict[str, Player]:
    """Build the players dict once per matchup, mirroring run_tournament's logic."""
    dummy_rng = _random.Random()
    players: dict[str, Player] = {}
    for c in configs:
        ptype = c.get("player_type", "CPU")
        personality = None
        if ptype == "CPU":
            personality = Personality.from_traits(
                risk_appetite=c["risk_appetite"],
                attentiveness_score=c["attentiveness_score"],
                bluff_frequency=c["bluff_frequency"],
                archetype_label=c.get("archetype"),
            )
        players[c["name"]] = Player(
            c["name"],
            player_type=ptype,
            rng=dummy_rng,
            llm_model=c.get("llm_model"),
            personality=personality,
        )
    return players


def _results_to_dfs(results: list[dict]):
    """Convert run_game's result dicts into the same three DataFrames run_tournament emits."""
    round_rows = [row for r in results for row in r.get("_round_rows", [])]
    elim_rows = [row for r in results for row in r.get("_elim_rows", [])]
    # Strip the hidden lists before building games DataFrame.
    games_records = []
    for r in results:
        clean = {k: v for k, v in r.items() if not k.startswith("_")}
        games_records.append(clean)
    df_games = pd.DataFrame(games_records)
    df_rounds = rounds_to_df(round_rows)
    df_elims = eliminations_to_df(elim_rows)
    return df_games, df_rounds, df_elims


def _stats_to_dict(s: MatchupStats) -> dict[str, Any]:
    d = s.__dict__.copy()
    # sample_traces already serializable
    return d


if __name__ == "__main__":
    raise SystemExit(main())
