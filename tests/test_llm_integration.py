"""Live integration tests: hit a running Ollama daemon with the configured Gemma model.

Skipped by default. Run with:
    .venv/bin/pytest tests/test_llm_integration.py -m integration -v

The session-scoped fixture will:
1. Use an already-running Ollama daemon if reachable.
2. Otherwise, spawn `ollama serve` as a subprocess (skipping if the binary
   is not on PATH) and tear it down at session end.
3. Pull the configured model via `ollama pull` if missing.
"""
import logging
import os
import shutil
import signal
import subprocess
import time
from collections import deque
from urllib.parse import urlparse

import pytest
import requests

import constants as Constants
from llm_client import query_llm, _ollama_url
from models import Action, Bid, TurnResult
from strategy import LLMStrategy
from Player import Player
from LiarsDiceGame import LiarsDiceGame

pytestmark = pytest.mark.integration

LLM_TEMPERATURE = 1.0  # Google's official guidance for Gemma
LLM_TIMEOUT = 60.0     # generous: cold starts + first-token latency


# ---------------------------------------------------------------------------
# Session fixture: ensure Ollama is up and the model is available
# ---------------------------------------------------------------------------

def _ollama_base() -> str:
    parsed = urlparse(_ollama_url())
    return f"{parsed.scheme}://{parsed.netloc}"


def _ollama_reachable() -> bool:
    try:
        r = requests.get(_ollama_base() + "/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _model_present(model: str) -> bool:
    try:
        r = requests.get(_ollama_base() + "/api/tags", timeout=5)
        r.raise_for_status()
        names = {m.get("name", "") for m in r.json().get("models", [])}
        # Ollama may report the model with or without a ":latest" suffix.
        return model in names or any(n.split(":")[0] == model.split(":")[0]
                                      and n.split(":", 1)[-1] == model.split(":", 1)[-1]
                                      for n in names)
    except Exception:
        return False


def _pull_model(model: str) -> bool:
    """Attempt to pull the model. Prefer the HTTP API; fall back to the CLI."""
    try:
        r = requests.post(
            _ollama_base() + "/api/pull",
            json={"name": model, "stream": False},
            timeout=600,
        )
        if r.status_code == 200:
            return True
    except Exception as exc:
        logging.warning("HTTP pull failed: %s", exc)

    if shutil.which("ollama") is None:
        return False
    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True,
            text=True,
            timeout=600,
        )
        return result.returncode == 0
    except Exception as exc:
        logging.warning("CLI pull failed: %s", exc)
        return False


def _wait_until_reachable(timeout_s: float = 30.0, interval_s: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _ollama_reachable():
            return True
        time.sleep(interval_s)
    return False


def _spawn_ollama_serve() -> subprocess.Popen | None:
    if shutil.which("ollama") is None:
        return None
    log = open("/tmp/ollama_serve_test.log", "ab", buffering=0)
    try:
        # start_new_session so we can kill the whole process group on teardown.
        proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as exc:
        logging.warning("failed to spawn ollama serve: %s", exc)
        log.close()
        return None
    return proc


@pytest.fixture(scope="session")
def ollama_with_model():
    spawned: subprocess.Popen | None = None
    if not _ollama_reachable():
        spawned = _spawn_ollama_serve()
        if spawned is None:
            pytest.skip("Ollama not reachable and `ollama` binary not found on PATH.")
        if not _wait_until_reachable(timeout_s=30.0):
            try:
                os.killpg(spawned.pid, signal.SIGTERM)
            except Exception:
                pass
            pytest.skip("Spawned `ollama serve` but daemon never became reachable.")

    model = Constants.LLM_MODEL
    if not _model_present(model):
        if not _pull_model(model):
            if spawned is not None:
                try:
                    os.killpg(spawned.pid, signal.SIGTERM)
                except Exception:
                    pass
            pytest.skip(f"Model {model} not present and could not be pulled.")

    yield model

    if spawned is not None:
        try:
            os.killpg(spawned.pid, signal.SIGTERM)
            try:
                spawned.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(spawned.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception as exc:
            logging.warning("error tearing down ollama serve: %s", exc)


# ---------------------------------------------------------------------------
# Test 1: query_llm round-trips a non-empty string
# ---------------------------------------------------------------------------

def test_query_llm_returns_nonempty_response(ollama_with_model):
    result = query_llm(
        ollama_with_model,
        "Reply with the single word: pong.",
        timeout=LLM_TIMEOUT,
        temperature=LLM_TEMPERATURE,
    )
    assert result is not None, "query_llm returned None — Ollama call failed"
    assert isinstance(result, str)
    assert len(result.strip()) > 0


# ---------------------------------------------------------------------------
# Test 2: LLMStrategy.decide produces a valid TurnResult
# ---------------------------------------------------------------------------

VALID_ACTIONS = {Action.BID, Action.RAISE, Action.CHALLENGE, Action.SPOT_ON}


def test_llm_strategy_decide_returns_valid_action(ollama_with_model):
    strategy = LLMStrategy(
        model=ollama_with_model,
        temperature=LLM_TEMPERATURE,
        timeout=LLM_TIMEOUT,
    )
    prev = TurnResult(Bid(2, 4), Action.BID, "opponent")
    recent = deque([prev])
    result = strategy.decide(
        player_name="Gemma",
        dice=[2, 4, 4, 1, 5],
        num_dice=5,
        recent_events=recent,
        tot_other_dice=10,
        bidder_num_dice=5,
        next_player_num_dice=5,
        num_active_players=3,
    )
    assert isinstance(result, TurnResult)
    assert result.player_name == "Gemma"
    assert result.action in VALID_ACTIONS
    if result.action in (Action.BID, Action.RAISE):
        assert result.bid is not None
        assert 1 <= result.bid.face <= 6
        assert result.bid.count >= Constants.MINIMUM_BID


# ---------------------------------------------------------------------------
# Test 3: end-to-end game with one LLM player vs CPUs runs to completion
# ---------------------------------------------------------------------------

def test_full_game_with_llm_player(ollama_with_model):
    events: list[dict] = []

    def collect(event: dict) -> None:
        events.append(event)

    llm_player = Player("Gemma", player_type="LLM", llm_model=ollama_with_model, num_dice=3)
    llm_player._strategy = LLMStrategy(
        model=ollama_with_model,
        temperature=LLM_TEMPERATURE,
        timeout=LLM_TIMEOUT,
    )
    cpu_a = Player("CpuA", player_type="CPU", num_dice=3)
    cpu_b = Player("CpuB", player_type="CPU", num_dice=3)

    game = LiarsDiceGame(3, max_rounds=15, on_event=collect)
    game.add_player(llm_player)
    game.add_player(cpu_a)
    game.add_player(cpu_b)

    # Run rounds until the engine declares the game over or the round cap is hit.
    while game.game_status and game.round_num < game.max_rounds:
        game.process_round()

    types = {e["type"] for e in events}
    assert "round_started" in types
    assert "dice_rolled" in types
    # Engine must have actually run turns: at least one bid or challenge resolved.
    assert any(t in types for t in ("bid_made", "challenge_resolved", "spot_on_resolved"))
    # Either a winner was declared, or we hit the round cap without crashing.
    assert (not game.game_status) or game.round_num >= game.max_rounds


# ---------------------------------------------------------------------------
# Test 4: fallback rate across N decisions stays below threshold
# ---------------------------------------------------------------------------

def test_llm_fallback_rate_below_threshold(ollama_with_model):
    """Sanity check: across several decisions, the LLM should produce parseable
    output most of the time. If fallback rate is high, prompt or model is broken."""
    n_trials = 5
    max_fallback_rate = 0.6  # tolerate some non-determinism; flag broken prompts
    strategy = LLMStrategy(
        model=ollama_with_model,
        temperature=LLM_TEMPERATURE,
        timeout=LLM_TIMEOUT,
    )
    fallbacks = 0
    for i in range(n_trials):
        prev = TurnResult(Bid(2 + (i % 2), (i % 6) + 1), Action.BID, "opponent")
        recent = deque([prev])
        result = strategy.decide(
            player_name="Gemma",
            dice=[1, 2, 3, 4, 5],
            num_dice=5,
            recent_events=recent,
            tot_other_dice=10,
            bidder_num_dice=5,
            next_player_num_dice=5,
            num_active_players=3,
        )
        if result.fallback:
            fallbacks += 1

    rate = fallbacks / n_trials
    assert rate <= max_fallback_rate, (
        f"LLM fell back {fallbacks}/{n_trials} times (rate={rate:.2f}); "
        f"prompt or model may be broken."
    )
