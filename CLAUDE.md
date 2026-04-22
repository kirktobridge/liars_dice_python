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

## Logging

Log files are written to `logs/`:

- `logs/web/` — web server session logs (up to 10 kept, oldest pruned). Each file covers one server run. Logger hierarchy: `liars_dice` (root) → `liars_dice.game` (`LiarsDiceGame.py`) → `liars_dice.player` (`Player.py`) → `liars_dice.game_events` (per-turn event file, CLI only). Format: `HH:MM:SS | LEVEL | logger | message`.
- `logs/cli/` — per-game event log written when `LiarsDiceGame(log=True)` is used from the CLI.

Every log line from `liars_dice.game` includes a full dice snapshot: `Name(n):[d1,d2,...]` for all active players. Key events and what they record:

| Log token | What it tells you |
|---|---|
| `turn start \| <player>` | Which player's turn is starting; full hands at that moment |
| `calling take_turn \| prev_action=... \| prev_bid=...` | What state was handed to the player's decision logic |
| `BID \| <player> bids NxF` | Player made a bid; hands at the moment of the bid |
| `RAISE \| <player> raises to NxF` | Player raised; hands at that moment |
| `CHALLENGE \| <challenger> challenges <bidder> bid NxF` | Challenge called; full hands visible |
| `CHALLENGE result \| succeeded=... \| bid=NxF actual=A (ones=O) \| loser=...` | Outcome: whether the bid held, real count of the face, ones count, who loses a die |
| `SPOT-ON \| <caller> calls spot-on on <bidder> bid NxF` | Spot-on called; full hands visible |
| `SPOT-ON result \| succeeded=... \| bid=NxF actual=A \| losers=[...]` | Outcome: exact count vs bid, who loses |

### Using logs for RCA

**Bad AI decision (e.g. called challenge when bid was safe):** Find the `CHALLENGE` line, note the hands snapshot, then look one line up at `calling take_turn | prev_bid=...` to confirm what the player saw. Cross-check `CHALLENGE result actual=` — if the actual count was well above the bid, the player's probability model misjudged. Check `Player.py` `_get_challenge_prob` with those dice counts.

**Spot-on called at wrong time:** Find `SPOT-ON` line and read the hands. Check whether any player's dice could plausibly have produced the exact bid count — if the hands make it obvious the spot-on was a long shot, trace back through `calling take_turn` lines to see what prior bids led to that decision.

**Player stuck / round didn't end:** Search for `NONE` actions (logged as `Action.NONE`). A run of NONE events for the same player means `take_turn` raised an exception; the preceding `calling take_turn` line shows the game state that triggered it.

**Dice counts not adding up after elimination:** Compare `turn start` snapshots at the start of consecutive rounds. The `(n)` count beside each name is the authoritative die count at that moment.

**Quick grep recipes:**
```bash
# All decisions for one player in the latest web log
grep "Alice" logs/web/*.log | grep -E "BID|RAISE|CHALLENGE|SPOT-ON"

# Every challenge outcome in a session
grep "CHALLENGE result" logs/web/*.log

# Rounds where spot-on succeeded
grep "SPOT-ON result.*succeeded=True" logs/web/*.log
```

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