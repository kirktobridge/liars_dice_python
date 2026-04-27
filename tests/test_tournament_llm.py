"""Tournament-level tests for LLM player support.

Monkeypatches strategy.query_llm so no live Ollama server is required.
n is kept deliberately tiny (1-2 games) for speed.
"""
import unittest
from unittest.mock import patch

from tournament import run_tournament

# ---------------------------------------------------------------------------
# Player config fixtures
# ---------------------------------------------------------------------------

_LLM_CFG = {'name': 'Gemma', 'player_type': 'LLM'}

_CPU_A = {
    'name': 'Alice',
    'player_type': 'CPU',
    'risk_appetite': 3,
    'peer_pressure_score': 3,
    'attentiveness_score': 3,
}
_CPU_B = {
    'name': 'Bob',
    'player_type': 'CPU',
    'risk_appetite': 2,
    'peer_pressure_score': 2,
    'attentiveness_score': 2,
}

# ---------------------------------------------------------------------------
# Deterministic LLM stub: opens with a bid, challenges everything else.
# 'action=START' appears in the prompt when the previous action is START.
# ---------------------------------------------------------------------------

def _fake_query_llm(model: str, prompt: str) -> str:
    if 'action=START' in prompt:
        return '{"action": "bid", "count": 2, "face": 3}'
    return '{"action": "challenge"}'


_LLM_PATCH = patch('strategy.query_llm', side_effect=_fake_query_llm)


# ---------------------------------------------------------------------------
# Serial mode with LLM configs
# ---------------------------------------------------------------------------

class TestLLMSerialTournament(unittest.TestCase):

    def test_llm_plus_cpu_serial_completes(self):
        configs = [_LLM_CFG, _CPU_A]
        with _LLM_PATCH:
            df_games, df_rounds, df_elims = run_tournament(
                2, player_configs=configs, parallel=False, show_progress=False
            )
        self.assertEqual(len(df_games), 2)
        self.assertIn('winner', df_games.columns)

    def test_llm_serial_returns_correct_player_count(self):
        configs = [_LLM_CFG, _CPU_A]
        with _LLM_PATCH:
            df_games, _, _ = run_tournament(
                1, player_configs=configs, parallel=False, show_progress=False
            )
        self.assertEqual(df_games.iloc[0]['num_players'], 2)

    def test_mixed_cpu_llm_serial_three_players(self):
        configs = [_LLM_CFG, _CPU_A, _CPU_B]
        with _LLM_PATCH:
            df_games, _, _ = run_tournament(
                2, player_configs=configs, parallel=False, show_progress=False
            )
        self.assertEqual(len(df_games), 2)
        self.assertTrue(df_games['winner'].isin(['Gemma', 'Alice', 'Bob']).all())


# ---------------------------------------------------------------------------
# parallel=True guard
# ---------------------------------------------------------------------------

class TestLLMParallelGuard(unittest.TestCase):

    def test_llm_parallel_raises_valueerror(self):
        configs = [_LLM_CFG, _CPU_A]
        with self.assertRaises(ValueError):
            run_tournament(
                2, player_configs=configs, parallel=True, show_progress=False
            )

    def test_error_raised_before_any_game_runs(self):
        """ValueError must fire before game execution, so no LLM calls happen."""
        configs = [_LLM_CFG, _CPU_A]
        with _LLM_PATCH as mock_llm:
            with self.assertRaises(ValueError):
                run_tournament(
                    2, player_configs=configs, parallel=True, show_progress=False
                )
            mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# CPU-only configs (regression — existing behaviour must be preserved)
# ---------------------------------------------------------------------------

class TestCPUOnlyConfigs(unittest.TestCase):

    def test_cpu_only_serial_works(self):
        configs = [_CPU_A, _CPU_B]
        df_games, _, _ = run_tournament(
            2, player_configs=configs, parallel=False, show_progress=False
        )
        self.assertEqual(len(df_games), 2)

    def test_cpu_only_personalities_preserved(self):
        configs = [_CPU_A, _CPU_B]
        df_games, _, _ = run_tournament(
            1, player_configs=configs, parallel=False, show_progress=False
        )
        self.assertIn('p_Alice_risk', df_games.columns)
        self.assertEqual(df_games.iloc[0]['p_Alice_risk'], 3)

    def test_cpu_only_parallel_does_not_raise(self):
        configs = [_CPU_A, _CPU_B]
        df_games, _, _ = run_tournament(
            2, player_configs=configs, parallel=True, show_progress=False
        )
        self.assertEqual(len(df_games), 2)


# ---------------------------------------------------------------------------
# LLM config without CPU personality fields
# ---------------------------------------------------------------------------

class TestLLMConfigMinimal(unittest.TestCase):

    def test_llm_config_name_and_type_only(self):
        """LLM config with only name + player_type must not crash."""
        configs = [{'name': 'Gemma', 'player_type': 'LLM'}, _CPU_A]
        with _LLM_PATCH:
            df_games, _, _ = run_tournament(
                1, player_configs=configs, parallel=False, show_progress=False
            )
        self.assertEqual(len(df_games), 1)

    def test_llm_trait_columns_are_zero(self):
        """LLM player personality columns should read as 0 in results."""
        configs = [_LLM_CFG, _CPU_A]
        with _LLM_PATCH:
            df_games, _, _ = run_tournament(
                1, player_configs=configs, parallel=False, show_progress=False
            )
        self.assertEqual(df_games.iloc[0]['p_Gemma_risk'], 0)
        self.assertEqual(df_games.iloc[0]['p_Gemma_peer'], 0)
