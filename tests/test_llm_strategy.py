import unittest
from collections import deque
from unittest.mock import patch

from models import Action, Bid, TurnResult
from strategy import LLMStrategy

PLAYER = 'pirate_pete'


def _start_events() -> deque:
    return deque([TurnResult(None, Action.START, 'dealer')])


def _bid_events(bid: Bid = Bid(2, 4)) -> deque:
    return deque([TurnResult(bid, Action.BID, 'opponent')])


def _decide(strategy: LLMStrategy, prev_events: deque) -> TurnResult:
    return strategy.decide(
        player_name=PLAYER,
        dice=[3, 5, 2, 1, 4],
        num_dice=3,
        prev_events=prev_events,
        tot_other_dice=10,
        bidder_num_dice=3,
    )


class TestLLMStrategyOpeningBid(unittest.TestCase):

    def setUp(self):
        self.strategy = LLMStrategy()

    @patch('strategy.query_llm')
    def test_valid_bid_json_returns_bid_action(self, mock_query):
        mock_query.return_value = '{"action": "bid", "count": 3, "face": 4}'
        result = _decide(self.strategy, _start_events())
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(3, 4))
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_none_response_falls_back_to_opening_bid(self, mock_query):
        mock_query.return_value = None
        result = _decide(self.strategy, _start_events())
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(2, 3))
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_malformed_json_falls_back_to_opening_bid(self, mock_query):
        mock_query.return_value = 'not json at all'
        result = _decide(self.strategy, _start_events())
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(2, 3))
        self.assertEqual(result.player_name, PLAYER)


class TestLLMStrategyNormalTurn(unittest.TestCase):

    def setUp(self):
        self.strategy = LLMStrategy()

    @patch('strategy.query_llm')
    def test_challenge_json_returns_challenge(self, mock_query):
        mock_query.return_value = '{"action": "challenge"}'
        result = _decide(self.strategy, _bid_events())
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_bid_json_returns_correct_bid(self, mock_query):
        mock_query.return_value = '{"action": "bid", "count": 4, "face": 5}'
        result = _decide(self.strategy, _bid_events())
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(4, 5))
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_raise_json_returns_correct_raise(self, mock_query):
        mock_query.return_value = '{"action": "raise", "count": 3, "face": 6}'
        result = _decide(self.strategy, _bid_events())
        self.assertEqual(result.action, Action.RAISE)
        self.assertEqual(result.bid, Bid(3, 6))
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_spot_on_json_returns_spot_on_no_bid(self, mock_query):
        mock_query.return_value = '{"action": "spot_on"}'
        result = _decide(self.strategy, _bid_events())
        self.assertEqual(result.action, Action.SPOT_ON)
        self.assertIsNone(result.bid)
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_none_response_falls_back_to_challenge(self, mock_query):
        mock_query.return_value = None
        result = _decide(self.strategy, _bid_events())
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_malformed_json_falls_back_to_challenge(self, mock_query):
        mock_query.return_value = 'definitely not json'
        result = _decide(self.strategy, _bid_events())
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_invalid_action_string_falls_back_to_challenge(self, mock_query):
        mock_query.return_value = '{"action": "surrender", "count": 2, "face": 3}'
        result = _decide(self.strategy, _bid_events())
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_json_embedded_in_prose_is_parsed(self, mock_query):
        mock_query.return_value = 'Let me think... {"action": "challenge"} that is my move.'
        result = _decide(self.strategy, _bid_events())
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)


class TestLLMStrategyNoOps(unittest.TestCase):

    def setUp(self):
        self.strategy = LLMStrategy()

    def test_reset_is_safe_noop(self):
        self.strategy.reset()

    def test_observe_action_is_safe_noop(self):
        self.strategy.observe_action(PLAYER, Action.BID, Bid(2, 4), 10)
        self.strategy.observe_action(PLAYER, Action.CHALLENGE, None, 10)

    def test_observe_outcome_is_safe_noop(self):
        self.strategy.observe_outcome(PLAYER, True)
        self.strategy.observe_outcome(PLAYER, False)

    def test_player_type_is_llm(self):
        self.assertEqual(self.strategy.player_type, 'LLM')

    def test_default_model_is_gemma(self):
        self.assertEqual(self.strategy._model, 'gemma3:4b')

    def test_custom_model_stored(self):
        s = LLMStrategy(model='llama3.2:3b')
        self.assertEqual(s._model, 'llama3.2:3b')
