"""Live integration tests: hit a running Ollama daemon with the configured Gemma model.

Skipped by default. Run with:
    .venv/bin/pytest tests/test_llm_integration.py -m integration -v

The session-scoped fixture will:
1. Use an already-running Ollama daemon if reachable.
2. Otherwise, spawn `ollama serve` as a subprocess (skipping if the binary
   is not on PATH) and tear it down at session end.
3. Pull the configured model via `ollama pull` if missing.

Set LLM_DEBUG_WINDOW=1 to spawn a local FastAPI server on $LLM_DEBUG_PORT
(default 8766) and open http://localhost:<port>/llm-debug in your default
browser. Each prompt sent to Gemma and every streamed response token will
appear live in the page while tests run.
"""
import logging
import os
import socket
import time
import webbrowser
from collections import deque

import pytest
import requests

import constants as Constants
from llm_client import query_llm
from models import Action, Bid, TurnResult
from ollama_lifecycle import (
    model_present,
    ollama_reachable,
    pull_model,
    spawn_ollama_serve,
    teardown_spawned,
    wait_until_reachable,
)
from strategy import LLMStrategy
from Player import Player
from LiarsDiceGame import LiarsDiceGame

pytestmark = pytest.mark.integration

LLM_TEMPERATURE = 1.0  # Google's official guidance for Gemma
LLM_TIMEOUT = 60.0     # generous: cold starts + first-token latency


# ---------------------------------------------------------------------------
# Session fixture: ensure Ollama is up and the model is available
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ollama_with_model():
    spawned = None
    if not ollama_reachable():
        spawned = spawn_ollama_serve("/tmp/ollama_serve_test.log")
        if spawned is None:
            pytest.skip("Ollama not reachable and `ollama` binary not found on PATH.")
        if not wait_until_reachable(timeout_s=30.0):
            teardown_spawned(spawned)
            pytest.skip("Spawned `ollama serve` but daemon never became reachable.")

    model = Constants.LLM_MODEL
    if not model_present(model):
        if not pull_model(model):
            teardown_spawned(spawned)
            pytest.skip(f"Model {model} not present and could not be pulled.")

    yield model

    teardown_spawned(spawned)


# ---------------------------------------------------------------------------
# Optional live debug window: streams every prompt + response to a browser tab
# ---------------------------------------------------------------------------

def _debug_window_enabled() -> bool:
    return os.environ.get("LLM_DEBUG_WINDOW", "").lower() in ("1", "true", "yes", "on")


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


@pytest.fixture(scope="session", autouse=True)
def llm_debug_window():
    """If LLM_DEBUG_WINDOW=1, run the FastAPI app on LLM_DEBUG_PORT (default 8766)
    in a background thread (same process as the tests, so the in-memory broadcaster
    sees prompt/token events from `llm_client`), then open /llm-debug in the
    default browser."""
    if not _debug_window_enabled():
        yield None
        return

    port = int(os.environ.get("LLM_DEBUG_PORT", "8766"))
    if not _port_is_free(port):
        print(f"\n[llm-debug] port {port} in use — assuming server already running\n", flush=True)
        url = f"http://localhost:{port}/llm-debug"
        try:
            webbrowser.open(url)
        except Exception:
            pass
        time.sleep(1.0)
        yield port
        return

    import threading
    import uvicorn
    from web.app import app as fastapi_app

    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for the server to come up.
    deadline = time.monotonic() + 15.0
    ready = False
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.2)

    if not ready:
        logging.warning("debug uvicorn never became ready; window disabled")
        server.should_exit = True
        thread.join(timeout=5)
        yield None
        return

    url = f"http://localhost:{port}/llm-debug"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"\n[llm-debug] live window: {url}\n", flush=True)

    # Give the browser a moment to connect before the first prompt fires.
    time.sleep(1.5)

    yield port

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session", autouse=True)
def llm_streaming_when_debug():
    """When the debug window is on, force LLMStrategy default `stream=True`
    so every token reaches the browser. No-op otherwise."""
    if not _debug_window_enabled():
        yield
        return
    original = LLMStrategy.__init__

    def patched(self, *args, **kwargs):
        kwargs.setdefault("stream", True)
        original(self, *args, **kwargs)

    LLMStrategy.__init__ = patched
    try:
        yield
    finally:
        LLMStrategy.__init__ = original


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
