"""Tests for LLM player wiring in Player.__init__ and related delegation."""
import unittest
from collections import deque
from unittest.mock import patch

import constants as Constants
from Player import Player
from strategy import CPUStrategy, LLMStrategy
from models import Action, Bid, TurnResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _start_events():
    return deque([TurnResult(None, Action.START, "dealer")])


def _bid_events(count=2, face=3, bidder="other"):
    return deque([TurnResult(Bid(count, face), Action.BID, bidder)])


# ---------------------------------------------------------------------------
# Constructor wiring
# ---------------------------------------------------------------------------

class TestLLMPlayerConstructor(unittest.TestCase):

    def test_player_type_attribute_is_LLM(self):
        p = Player("Bot", player_type="LLM")
        self.assertEqual(p.player_type, "LLM")

    def test_strategy_is_LLMStrategy_instance(self):
        # minimal internal check — only to assert wiring, not strategy internals
        p = Player("Bot", player_type="LLM")
        self.assertIsInstance(p._strategy, LLMStrategy)

    def test_default_llm_model_is_gemma(self):
        p = Player("Bot", player_type="LLM")
        self.assertEqual(p._strategy._model, Constants.LLM_MODEL)

    def test_custom_llm_model_is_forwarded(self):
        p = Player("Bot", player_type="LLM", llm_model="llama3:8b")
        self.assertEqual(p._strategy._model, "llama3:8b")

    def test_llm_model_none_falls_back_to_default(self):
        p = Player("Bot", player_type="LLM", llm_model=None)
        self.assertEqual(p._strategy._model, Constants.LLM_MODEL)


# ---------------------------------------------------------------------------
# Default (CPU) and HUMAN behavior unchanged
# ---------------------------------------------------------------------------

class TestExistingPlayerTypesUnchanged(unittest.TestCase):

    def test_default_player_type_is_CPU(self):
        p = Player("Alice")
        self.assertEqual(p.player_type, "CPU")

    def test_default_player_uses_CPUStrategy(self):
        p = Player("Alice")
        self.assertIsInstance(p._strategy, CPUStrategy)

    def test_explicit_CPU_player_type(self):
        p = Player("Alice", player_type="CPU")
        self.assertEqual(p.player_type, "CPU")

    def test_human_player_type_attribute(self):
        p = Player("Human", player_type="HUMAN", input_handler=lambda req: {})
        self.assertEqual(p.player_type, "HUMAN")

    def test_human_does_not_use_LLMStrategy(self):
        p = Player("Human", player_type="HUMAN", input_handler=lambda req: {})
        self.assertNotIsInstance(p._strategy, LLMStrategy)


# ---------------------------------------------------------------------------
# take_turn delegation
# ---------------------------------------------------------------------------

class TestLLMTakeTurn(unittest.TestCase):
    """take_turn must delegate to LLMStrategy.decide and return a TurnResult."""

    def _make_llm_player(self, model="gemma3:4b"):
        p = Player("Bot", player_type="LLM", llm_model=model)
        p.dice = [2, 4, 3, 1, 5]
        p.num_dice = 5
        return p

    def test_take_turn_returns_TurnResult_on_start(self):
        p = self._make_llm_player()
        llm_json = '{"action": "bid", "count": 2, "face": 3}'
        with patch("strategy.query_llm", return_value=llm_json):
            result = p.take_turn(_start_events(), tot_other_dice=10)
        self.assertIsInstance(result, TurnResult)

    def test_take_turn_bid_action_parsed(self):
        p = self._make_llm_player()
        llm_json = '{"action": "bid", "count": 3, "face": 4}'
        with patch("strategy.query_llm", return_value=llm_json):
            result = p.take_turn(_bid_events(2, 3), tot_other_dice=10)
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(3, 4))

    def test_take_turn_challenge_action_parsed(self):
        p = self._make_llm_player()
        llm_json = '{"action": "challenge"}'
        with patch("strategy.query_llm", return_value=llm_json):
            result = p.take_turn(_bid_events(5, 6), tot_other_dice=10)
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)

    def test_take_turn_player_name_in_result(self):
        p = self._make_llm_player()
        llm_json = '{"action": "bid", "count": 2, "face": 2}'
        with patch("strategy.query_llm", return_value=llm_json):
            result = p.take_turn(_start_events(), tot_other_dice=5)
        self.assertEqual(result.player_name, "Bot")

    def test_take_turn_falls_back_on_llm_failure(self):
        # If query_llm returns None, LLMStrategy falls back to a safe default
        p = self._make_llm_player()
        with patch("strategy.query_llm", return_value=None):
            result = p.take_turn(_start_events(), tot_other_dice=5)
        self.assertIsInstance(result, TurnResult)
        self.assertIn(result.action, (Action.BID, Action.CHALLENGE))

    def test_take_turn_falls_back_on_unparseable_json(self):
        p = self._make_llm_player()
        with patch("strategy.query_llm", return_value="not valid json at all"):
            result = p.take_turn(_bid_events(), tot_other_dice=5)
        self.assertIsInstance(result, TurnResult)
        self.assertIn(result.action, (Action.BID, Action.RAISE, Action.CHALLENGE, Action.SPOT_ON))


# ---------------------------------------------------------------------------
# Personality is None for non-CPU strategies
# ---------------------------------------------------------------------------

class TestLLMNoPersonality(unittest.TestCase):
    def test_personality_is_none(self):
        p = Player("Bot", player_type="LLM")
        self.assertIsNone(p.personality)

    def test_opponent_profiles_is_empty_dict(self):
        p = Player("Bot", player_type="LLM")
        self.assertEqual(p.opponent_profiles, {})


if __name__ == "__main__":
    unittest.main()
