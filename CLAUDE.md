# Liar's Dice Python — Project Context

## Architecture

All source files live under `src/`:

- `src/models.py` — core dataclasses/enums: `Action`, `Bid`, `TurnResult`
- `src/constants.py` — game constants: thresholds, player counts, debug flag
- `src/presentation.py` — pirate flavor strings (`INSULTS`, `GAME_RULES`, `TITLE_CARD`), pause durations; imported by `main.py`
- `src/LiarsDiceGame.py` — game engine: round orchestration, challenge/spot-on resolution, elimination, event emission. Supports context manager. Decoupled from output via `on_event(event_type, **data)` callback.
- `src/Player.py` — player agent: dice ops, probability model (scipy binomial), turn decision logic, personality traits (`risk_appetite`, `peer_pressure_score`)
- `src/main.py` — CLI entry point: setup, human I/O, pirate-flavored output via `pirate_renderer(event)` event handler
- `src/tournament.py` — runs individual games (`run_game`) and parallel tournament batches (`run_tournament`)
- `src/stats_collector.py` — `GameStatsCollector` class: accumulates per-game results into stats
- `src/charts.py` — `show_tournament_stats()`: renders plotly charts from tournament data

## Web Layer

A Flask web interface lives under `web/`:

- `web/app.py` — Flask application: HTTP routes, SSE event streaming, game lifecycle endpoints
- `web/game_session.py` — `GameSession` class: bridges the game engine to the web layer, manages per-session state
- `web/templates/` — Jinja2 HTML templates
- `web/static/` — CSS, JS, and static assets
- `web/test_smoke.py` — smoke tests for the Flask app routes

Run the web server: .venv/bin/uvicorn web.app:app

## Test Commands

- Run all tests: `.venv/bin/pytest tests/ -v`
- Run web smoke tests: `.venv/bin/pytest web/test_smoke.py -v`
- Run single file: `.venv/bin/pytest tests/test_player.py -v`
- Run single test: `.venv/bin/pytest tests/test_player.py::TestGetNeededCnt::test_bid_on_ones_no_double_count -v`

## Code Style

- Python 3.10+. Use dataclasses and Enum from stdlib. Type hints on all new functions.
- No `print()`, `input()`, or `time.sleep()` inside `LiarsDiceGame` or `Player` — CLI only belongs in `main.py`
- Colorama is allowed in `src/presentation.py` (pirate flavor strings) and in `src/Player.py` (debug-only output, guarded by debug flag); avoid it in game-logic paths
- All new tests go in the existing test files. `make_game()` helper lives in `tests/test_game.py`; `make_player()` helper lives in `tests/test_player.py`

## Important Constraints

- DO NOT break the existing pirate-voice CLI experience in `main.py`
- DO NOT add game logic or I/O to `web/app.py` — delegate to `GameSession` and the game engine
- ALWAYS run the full test suite after changes to `.py` files. All tests must pass green.
- After completing a logically coherent change and getting all tests green, create a commit summarizing that change.