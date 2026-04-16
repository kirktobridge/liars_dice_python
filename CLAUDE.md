# Liar's Dice Python — Project Context

## Architecture
- `LiarsDiceGame.py` — game engine: round orchestration, challenge/spot-on resolution, elimination, logging
- `Player.py` — player agent: dice ops, probability model (scipy binomial), turn decision logic
- `main.py` — CLI entry point: setup, human I/O, pirate-flavored output
- `Constants.py` — game constants: ACTIONS enum list, thresholds, distributions
- `test_game.py` / `test_player.py` — unittest suite with mock_open and @patch(builtins.input)

## Test Commands
- Run all tests: `.venv/bin/pytest tests/test_game.py tests/test_player.py -v`
- Run single file: `.venv/bin/pytest tests/test_player.py -v`
- Run single test: `.venv/bin/pytest tests/test_player.py::TestGetNeededCnt::test_bid_on_ones_no_double_count -v`

## Code Style
- Python 3.10+. Use dataclasses and Enum from stdlib. Type hints on all new functions.
- No `print()`, `input()`, or `time.sleep()` inside LiarsDiceGame or Player — CLI only belongs in main.py
- Colorama is CLI-only; never import it in engine or model files
- All new tests go in the existing test files. Keep make_game() / make_player() helpers in test_game.py

## Important Constraints
- DO NOT break the existing pirate-voice CLI experience in main.py
- ALWAYS run the full test suite before committing. All tests must pass green.