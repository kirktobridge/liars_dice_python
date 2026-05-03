# Liar's Dice Python — Project Context

## Architecture

All source files live under `src/`:

- `src/models.py` — core dataclasses/enums: `Action`, `Bid`, `TurnResult`, `OpponentProfile`, `ResponseContext`, `PlayerState`, `GameState`, `InputHandler`/`InputRequest`/`InputResponse`
- `src/constants.py` — game constants: thresholds, player counts, debug flag
- `src/presentation.py` — pirate flavor strings (`INSULTS`, `GAME_RULES`, `TITLE_CARD`), pause durations; imported by `main.py`
- `src/LiarsDiceGame.py` — game engine: round orchestration, challenge/spot-on resolution, elimination, event emission. Supports context manager. Decoupled from output via `on_event(event_type, **data)` callback.
- `src/dice_math.py` — shared binomial math utilities: `get_binom()` (cached scipy binom), `needed_cnt()`; extracted from Player/advisor
- `src/advisor.py` — probability advisor for the human player: `AdvisorData` TypedDict, `advisor_probs()` function used by the web UI
- `src/strategy.py` — AI strategy layer: `Strategy` Protocol, `CPUStrategy` (opponent modelling + personality traits), and `LLMStrategy` (Ollama-backed; legality validation, sizing anchor, plausibility cue); imports from `dice_math` and `models`
- `src/llm_client.py` — Ollama HTTP client: `query_llm()`, `query_llm_stream()`, plus `set_llm_debug_listener()` hook used by the web debug window. Reads `OLLAMA_URL` env var (default `http://localhost:11434/api/generate`)
- `src/ollama_lifecycle.py` — Ollama daemon helpers: `ollama_reachable()`, `model_present()`, `pull_model()`, `spawn_ollama_serve()`, `OllamaSession` context manager. Used by the live integration test fixture and analysis scripts
- `src/Player.py` — player agent: dice ops, turn decision logic; delegates probability math to `dice_math` and strategy to `strategy.py`
- `src/main.py` — CLI entry point: setup, human I/O, pirate-flavored output via `pirate_renderer(event)` event handler
- `src/tournament.py` — runs individual games (`run_game`) and parallel tournament batches (`run_tournament`)
- `src/stats_collector.py` — `GameStatsCollector` class: accumulates per-game results into stats
- `src/stats_schema.py` — structured stats dataclasses: `RoundRow`, `EliminationRow`, `GameRow`; DataFrame converters used by charts
- `src/tournament_stats.py` — `compute_tournament_stats()`: pure aggregation of tournament DataFrames into a JSON-safe dict (no Plotly dependency); used by `web/app.py` and `charts.py`
- `src/charts.py` — `show_tournament_stats()`: renders plotly charts from tournament data; delegates aggregation to `tournament_stats`

## Web Layer

A FastAPI web interface lives under `web/`:

- `web/app.py` — FastAPI application: HTTP routes, WebSocket game streaming, tournament + explainer endpoints
- `web/game_session.py` — `GameSession` class: bridges the game engine to the web layer, manages per-session state
- `web/timing.py` — `EVENT_DELAYS` dict controlling SSE pacing (seconds to pause before forwarding each event type to the browser)
- `web/web_logging.py` — `setup_web_logging()`, `get_logger()`: rotating file-based logging for the web layer; call once at app startup
- `web/llm_debug.py` — `LLMDebugBroadcaster`: process-wide WebSocket fan-out of `llm_client` debug events (prompt/token/done/error) to the live LLM debug browser window
- `web/explainer_logic.py` — CPU Logic Explainer scenario engine: `ExplainerScenario`, `ExplainerStep`, `ExplainerResult` dataclasses; `SCENARIOS` dict; `run_scenario()` and `list_scenarios()`. Re-walks `CPUStrategy.decide()` phases to capture intermediate state for the `/explainer` UI. Response-to-bid scenarios only (opening bids out of scope for v1). Future: `POST /explainer/custom` for user-defined scenarios; Pydantic validation should mirror the trait range checks in `_PlayerConfig`. Not built in v1.
- `web/templates/` — HTML templates served via `FileResponse` (not Jinja-rendered)
- `web/static/` — CSS, JS, and static assets. `dice.js` defines the shared `makeDieSVG()` and `PIP_POSITIONS`; load it before `game.js` or `explainer.js`.
- `web/test_overlay_e2e.py` — Playwright E2E tests for the cups-lifted overlay
- `web/test_game_e2e.py` — Playwright E2E tests for lobby, bidding, game-over, and tournament flows
- `web/test_explainer_e2e.py` — Playwright E2E tests for the CPU Logic Explainer

Run the web server: .venv/bin/uvicorn web.app:app

## Test Commands

- **Run full test suite (unit + E2E) — always use this:**
  ```bash
  .venv/bin/uvicorn web.app:app --port 8765 & SERVER_PID=$!; sleep 2; .venv/bin/pytest tests/ web/ -v; kill $SERVER_PID 2>/dev/null
  ```
- Run unit tests only: `.venv/bin/pytest tests/ -v`
- Run single file: `.venv/bin/pytest tests/test_player.py -v`
- Run single test: `.venv/bin/pytest tests/test_player.py::TestGetNeededCnt::test_bid_on_ones_no_double_count -v`
- Run E2E tests only (requires server already running on port 8765): `.venv/bin/pytest web/ -v`
  - E2E tests live in `web/` (not `tests/`) because they depend on a running server

## Code Style

- Python 3.10+. Use dataclasses and Enum from stdlib. Type hints on all new functions.
- No `print()`, `input()`, or `time.sleep()` inside `LiarsDiceGame` or `Player` — CLI only belongs in `main.py`
- Colorama is allowed in `src/presentation.py` (pirate flavor strings) and in `src/Player.py` (debug-only output, guarded by debug flag); avoid it in game-logic paths
- Add new tests to the most relevant existing file in `tests/`. `make_game()` helper lives in `tests/test_game.py`; `make_player()` helper lives in `tests/test_player.py`. Current test files: `test_game`, `test_player`, `test_advisor`, `test_strategy`, `test_stats_collector`, `test_charts`, `test_main`, `test_smoke`, `test_explainer_logic`, `test_llm_client`, `test_llm_strategy`, `test_player_llm`, `test_tournament_llm`, `test_llm_integration` (live; spawns its own `ollama serve` via `OllamaSession`)

## Important Constraints

- DO NOT break the existing pirate-voice CLI experience in `main.py`
- DO NOT add game logic or I/O to `web/app.py` — delegate to `GameSession` and the game engine
- ALWAYS run the full test suite (unit + E2E, using the combined command above) after changes to `.py` files. All tests must pass green.
- After completing a logically coherent change and getting all tests green, create a commit summarizing that change.