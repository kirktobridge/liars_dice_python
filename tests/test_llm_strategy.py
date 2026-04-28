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


def _decide(strategy: LLMStrategy, recent_events: deque) -> TurnResult:
    return strategy.decide(
        player_name=PLAYER,
        dice=[3, 5, 2, 1, 4],
        num_dice=3,
        recent_events=recent_events,
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
    def test_none_response_falls_back_to_cpu_strategy(self, mock_query):
        mock_query.return_value = None
        result = _decide(self.strategy, _start_events())
        # CPU fallback always produces a bid on the opening turn (no prior bid to challenge)
        self.assertEqual(result.action, Action.BID)
        self.assertIsNotNone(result.bid)
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_malformed_json_falls_back_to_cpu_strategy(self, mock_query):
        mock_query.return_value = 'not json at all'
        result = _decide(self.strategy, _start_events())
        self.assertEqual(result.action, Action.BID)
        self.assertIsNotNone(result.bid)
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
    def test_none_response_falls_back_to_cpu_strategy(self, mock_query):
        mock_query.return_value = None
        result = _decide(self.strategy, _bid_events())
        self.assertIn(result.action, (Action.BID, Action.RAISE, Action.CHALLENGE, Action.SPOT_ON))
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_malformed_json_falls_back_to_cpu_strategy(self, mock_query):
        mock_query.return_value = 'definitely not json'
        result = _decide(self.strategy, _bid_events())
        self.assertIn(result.action, (Action.BID, Action.RAISE, Action.CHALLENGE, Action.SPOT_ON))
        self.assertEqual(result.player_name, PLAYER)

    @patch('strategy.query_llm')
    def test_invalid_action_string_falls_back_to_cpu_strategy(self, mock_query):
        mock_query.return_value = '{"action": "surrender", "count": 2, "face": 3}'
        result = _decide(self.strategy, _bid_events())
        self.assertIn(result.action, (Action.BID, Action.RAISE, Action.CHALLENGE, Action.SPOT_ON))
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

    def test_reset_does_not_crash(self):
        self.strategy.reset()

    def test_observe_action_does_not_crash(self):
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


# ---------------------------------------------------------------------------
# Phase 6: history, prompt content, temperature
# ---------------------------------------------------------------------------


class TestLLMStrategyHistory(unittest.TestCase):

    def setUp(self):
        self.strategy = LLMStrategy()

    def test_observe_bid_appends_readable_entry(self):
        self.strategy.observe_action('Alice', Action.BID, Bid(3, 4), 10)
        self.assertEqual(len(self.strategy._history), 1)
        entry = self.strategy._history[0]
        self.assertIn('Alice', entry)
        self.assertIn('3', entry)
        self.assertIn('four', entry)

    def test_observe_challenge_appends_readable_entry(self):
        self.strategy.observe_action('Bob', Action.CHALLENGE, None, 10)
        self.assertEqual(len(self.strategy._history), 1)
        entry = self.strategy._history[0]
        self.assertIn('Bob', entry)
        self.assertIn('challenge', entry.lower())

    def test_history_capped_at_ten_evicts_oldest(self):
        for i in range(11):
            self.strategy.observe_action(f'P{i}', Action.BID, Bid(2, 3), 10)
        self.assertEqual(len(self.strategy._history), 10)
        joined = '\n'.join(self.strategy._history)
        self.assertNotIn('P0 ', joined)
        self.assertIn('P10', joined)

    def test_reset_clears_history(self):
        self.strategy.observe_action('Alice', Action.BID, Bid(3, 4), 10)
        self.strategy.observe_action('Bob', Action.CHALLENGE, None, 10)
        self.strategy.reset()
        self.assertEqual(self.strategy._history, [])


class TestLLMStrategyPromptContent(unittest.TestCase):

    def setUp(self):
        self.strategy = LLMStrategy()
        self.prev = TurnResult(Bid(2, 4), Action.BID, 'opponent')

    def test_prompt_includes_history_section_when_history_present(self):
        self.strategy.observe_action('Alice', Action.BID, Bid(3, 4), 10)
        prompt = self.strategy._build_prompt([1, 2, 3], 10, self.prev)
        self.assertIn('Alice', prompt)
        self.assertRegex(prompt.lower(), r'history|recent')

    def test_prompt_omits_history_section_when_history_empty(self):
        prompt = self.strategy._build_prompt([1, 2, 3], 10, self.prev)
        self.assertNotIn('Recent history:', prompt)

    def test_prompt_includes_rules_reminder(self):
        prompt = self.strategy._build_prompt([1, 2, 3], 10, self.prev).lower()
        self.assertTrue('wild' in prompt or 'challenge' in prompt)

    def test_prompt_includes_json_only_instruction(self):
        prompt = self.strategy._build_prompt([1, 2, 3], 10, self.prev).lower()
        self.assertIn('no markdown', prompt)


class TestLLMStrategyTemperature(unittest.TestCase):

    def _start_prev(self) -> deque:
        return deque([TurnResult(None, Action.START, 'dealer')])

    @patch('strategy.query_llm')
    def test_custom_temperature_forwarded_to_query_llm(self, mock_query):
        mock_query.return_value = '{"action": "bid", "count": 2, "face": 3}'
        strategy = LLMStrategy(temperature=0.1)
        strategy.decide(
            player_name=PLAYER,
            dice=[1, 2, 3, 4, 5],
            num_dice=3,
            recent_events=self._start_prev(),
            tot_other_dice=10,
            bidder_num_dice=3,
        )
        _, kwargs = mock_query.call_args
        self.assertEqual(kwargs.get('temperature'), 0.1)

    def test_default_temperature_is_sensible_float(self):
        strategy = LLMStrategy()
        self.assertIsInstance(strategy._temperature, float)
        self.assertGreaterEqual(strategy._temperature, 0.0)
        self.assertLessEqual(strategy._temperature, 1.0)

    @patch('llm_client.requests.post')
    def test_query_llm_includes_temperature_in_payload(self, mock_post):
        from llm_client import query_llm
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {'response': 'ok'}
        query_llm('gemma3:4b', 'hi', temperature=0.42)
        _, kwargs = mock_post.call_args
        payload = kwargs['json']
        self.assertIn('options', payload)
        self.assertEqual(payload['options']['temperature'], 0.42)
