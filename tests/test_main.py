import unittest
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from main import pirate_renderer, human_input_handler, _prompt_bid_count, _prompt_bid_face
from models import Action, Bid
import constants as Constants


def _renderer_event(etype, **kwargs):
    """Build a minimal event dict for pirate_renderer smoke tests."""
    return {'type': etype, **kwargs}


class TestPirateRenderer(unittest.TestCase):
    """Smoke-test every event branch: valid dict → no exception."""

    def setUp(self):
        main._fast = True

    def tearDown(self):
        main._fast = False

    def _render(self, etype, **kwargs):
        with patch('builtins.print'):
            pirate_renderer(_renderer_event(etype, **kwargs))

    def test_round_started(self):
        self._render('round_started', round_num=1)

    def test_dice_rolling(self):
        self._render('dice_rolling')

    def test_dice_rolled(self):
        self._render('dice_rolled')

    def test_turn_started_nodebug(self):
        with patch.object(Constants, 'DEBUG', False):
            self._render('turn_started', round_num=1, player_name='Alice', num_dice=5)

    def test_turn_started_debug(self):
        with patch.object(Constants, 'DEBUG', True):
            self._render('turn_started', round_num=1, player_name='Alice', num_dice=5)

    def test_bid_made(self):
        self._render('bid_made', player_name='Alice', count=3, face=4)

    def test_raise_made(self):
        self._render('raise_made', player_name='Alice', count=4, face=4)

    def test_challenge_called(self):
        self._render('challenge_called', challenger_name='Bob', bid_count=3,
                     bid_face=4, bidder_name='Alice')

    def test_human_turn_start_no_prev_bidder(self):
        players = [{'name': 'You', 'num_dice': 5}, {'name': 'Bob', 'num_dice': 3}]
        self._render('human_turn_start', player_dice=players, current_player='You', prev_bidder=None)

    def test_human_turn_start_with_prev_bidder(self):
        players = [{'name': 'You', 'num_dice': 5}, {'name': 'Bob', 'num_dice': 3}]
        self._render('human_turn_start', player_dice=players, current_player='You', prev_bidder='Bob')

    def test_rolls_revealed(self):
        rolls = [
            {'name': 'Alice', 'dice': [1, 2, 3, 4, 5]},
            {'name': 'Bob',   'dice': [6, 6, 1, 2, 3]},
        ]
        self._render('rolls_revealed', player_rolls=rolls, bid_face=5)

    def test_rolls_revealed_no_bid_face(self):
        rolls = [
            {'name': 'Alice', 'dice': [1, 2, 3, 4, 5]},
            {'name': 'Bob',   'dice': [6, 6, 1, 2, 3]},
        ]
        self._render('rolls_revealed', player_rolls=rolls)

    def test_challenge_resolved_success_with_ones(self):
        self._render('challenge_resolved', succeeded=True, challenger_name='Bob',
                     actual_count=2, bid_face=5, ones_count=1)

    def test_challenge_resolved_success_no_ones(self):
        self._render('challenge_resolved', succeeded=True, challenger_name='Bob',
                     actual_count=2, bid_face=5, ones_count=0)

    def test_challenge_resolved_failure_with_ones(self):
        self._render('challenge_resolved', succeeded=False, challenger_name='Bob',
                     actual_count=4, bid_face=5, ones_count=2)

    def test_challenge_resolved_failure_no_ones(self):
        self._render('challenge_resolved', succeeded=False, challenger_name='Bob',
                     actual_count=4, bid_face=5, ones_count=0)

    def test_spot_on_called(self):
        self._render('spot_on_called', caller_name='Alice', bid_count=3,
                     bid_face=4, bidder_name='Bob')

    def test_spot_on_resolved_success(self):
        self._render('spot_on_resolved', succeeded=True, caller_name='Alice',
                     caller_spot='CPU')

    def test_spot_on_resolved_failure_human(self):
        self._render('spot_on_resolved', succeeded=False, caller_name='You',
                     caller_spot='HUMAN')

    def test_spot_on_resolved_failure_cpu(self):
        self._render('spot_on_resolved', succeeded=False, caller_name='Bob',
                     caller_spot='CPU')

    def test_player_eliminated_human(self):
        self._render('player_eliminated', player_name='You', spot='HUMAN')

    def test_player_eliminated_cpu(self):
        self._render('player_eliminated', player_name='Bob', spot='CPU')

    def test_game_won(self):
        self._render('game_won', winner_name='Alice')

    def test_round_summary(self):
        self._render('round_summary', num_players=3, tot_num_dice=12)

    def test_error(self):
        self._render('error', message='something went wrong')

    def test_debug(self):
        self._render('debug', msg='internal state')

    def test_unknown_event_is_noop(self):
        # Should not raise even for unrecognised event types.
        self._render('totally_unknown_event')


class TestPromptBidCount(unittest.TestCase):
    def setUp(self):
        main._fast = True

    def tearDown(self):
        main._fast = False

    def test_valid_first_try(self):
        with patch('builtins.input', return_value='3'), patch('builtins.print'):
            self.assertEqual(_prompt_bid_count(10), 3)

    def test_zero_is_valid(self):
        with patch('builtins.input', return_value='0'), patch('builtins.print'):
            self.assertEqual(_prompt_bid_count(10), 0)

    def test_max_count_accepted(self):
        with patch('builtins.input', return_value='10'), patch('builtins.print'):
            self.assertEqual(_prompt_bid_count(10), 10)

    def test_negative_retries(self):
        with patch('builtins.input', side_effect=['-1', '4']), patch('builtins.print'):
            self.assertEqual(_prompt_bid_count(10), 4)

    def test_exceeds_max_retries(self):
        with patch('builtins.input', side_effect=['99', '5']), patch('builtins.print'):
            self.assertEqual(_prompt_bid_count(10), 5)

    def test_non_integer_retries(self):
        with patch('builtins.input', side_effect=['abc', '2']), patch('builtins.print'):
            self.assertEqual(_prompt_bid_count(10), 2)

    def test_empty_string_retries(self):
        with patch('builtins.input', side_effect=['', '1']), patch('builtins.print'):
            self.assertEqual(_prompt_bid_count(10), 1)


class TestPromptBidFace(unittest.TestCase):
    def setUp(self):
        main._fast = True

    def tearDown(self):
        main._fast = False

    def test_valid_faces(self):
        for face in range(1, 7):
            with patch('builtins.input', return_value=str(face)), patch('builtins.print'):
                self.assertEqual(_prompt_bid_face(), face)

    def test_zero_retries(self):
        with patch('builtins.input', side_effect=['0', '3']), patch('builtins.print'):
            self.assertEqual(_prompt_bid_face(), 3)

    def test_seven_retries(self):
        with patch('builtins.input', side_effect=['7', '6']), patch('builtins.print'):
            self.assertEqual(_prompt_bid_face(), 6)

    def test_non_integer_retries(self):
        with patch('builtins.input', side_effect=['five', '5']), patch('builtins.print'):
            self.assertEqual(_prompt_bid_face(), 5)

    def test_negative_retries(self):
        with patch('builtins.input', side_effect=['-1', '4']), patch('builtins.print'):
            self.assertEqual(_prompt_bid_face(), 4)


class TestHumanInputHandler(unittest.TestCase):
    def setUp(self):
        main._fast = True

    def tearDown(self):
        main._fast = False

    def _opening_bid_request(self, dice=None, tot_other_dice=10):
        return {
            'type': 'opening_bid',
            'dice': dice or [3, 3, 3, 4, 5],
            'tot_other_dice': tot_other_dice,
        }

    def _decision_request(self, dice=None, tot_other_dice=10,
                          prev_bid=None, prev_player='Bob'):
        return {
            'type': 'decision',
            'dice': dice or [3, 3, 3, 4, 5],
            'tot_other_dice': tot_other_dice,
            'prev_bid': prev_bid or Bid(2, 4),
            'prev_player': prev_player,
        }

    # --- opening bid ---

    def test_opening_bid_returns_bid_action(self):
        with patch('builtins.input', side_effect=['3', '4']), patch('builtins.print'):
            result = human_input_handler(self._opening_bid_request())
        self.assertEqual(result['action'], Action.BID)
        self.assertEqual(result['bid'], Bid(3, 4))

    def test_opening_bid_uses_all_dice_for_max(self):
        # Max count = tot_other_dice + len(dice) = 5 + 5 = 10; entering 10 should be accepted.
        with patch('builtins.input', side_effect=['10', '1']), patch('builtins.print'):
            result = human_input_handler(self._opening_bid_request(tot_other_dice=5))
        self.assertEqual(result['bid'].count, 10)

    # --- decision: challenge ---

    def test_decision_challenge(self):
        with patch('builtins.input', side_effect=['C']), patch('builtins.print'):
            result = human_input_handler(self._decision_request())
        self.assertEqual(result['action'], Action.CHALLENGE)
        self.assertIsNone(result['bid'])

    def test_decision_challenge_full_word(self):
        with patch('builtins.input', side_effect=['CHALLENGE']), patch('builtins.print'):
            result = human_input_handler(self._decision_request())
        self.assertEqual(result['action'], Action.CHALLENGE)

    # --- decision: spot on ---

    def test_decision_spot_on(self):
        with patch('builtins.input', side_effect=['S']), patch('builtins.print'):
            result = human_input_handler(self._decision_request())
        self.assertEqual(result['action'], Action.SPOT_ON)
        self.assertIsNone(result['bid'])

    def test_decision_spot_on_full_word(self):
        with patch('builtins.input', side_effect=['SPOT']), patch('builtins.print'):
            result = human_input_handler(self._decision_request())
        self.assertEqual(result['action'], Action.SPOT_ON)

    # --- decision: bid / raise ---

    def test_decision_raise_higher_count(self):
        # prev_bid = Bid(2, 4); bid count=4 > 2 → RAISE
        with patch('builtins.input', side_effect=['B', '4', '4']), patch('builtins.print'):
            result = human_input_handler(self._decision_request(prev_bid=Bid(2, 4)))
        self.assertEqual(result['action'], Action.RAISE)
        self.assertEqual(result['bid'], Bid(4, 4))

    def test_decision_bid_same_count_different_face(self):
        # prev_bid = Bid(3, 4); same count, different face → BID
        with patch('builtins.input', side_effect=['B', '3', '6']), patch('builtins.print'):
            result = human_input_handler(self._decision_request(prev_bid=Bid(3, 4)))
        self.assertEqual(result['action'], Action.BID)
        self.assertEqual(result['bid'], Bid(3, 6))

    def test_decision_raise_keyword(self):
        with patch('builtins.input', side_effect=['R', '5', '3']), patch('builtins.print'):
            result = human_input_handler(self._decision_request(prev_bid=Bid(2, 4)))
        self.assertEqual(result['action'], Action.RAISE)

    # --- decision: bid validation retry ---

    def test_decision_bid_retries_when_count_too_low(self):
        # First attempt: count=1 < prev_bid.count=3 → rejected; second: count=4 → accepted
        with patch('builtins.input', side_effect=['B', '1', '4', '4', '5']), patch('builtins.print'):
            result = human_input_handler(self._decision_request(prev_bid=Bid(3, 4)))
        self.assertEqual(result['bid'].count, 4)

    def test_decision_bid_retries_when_same_count_and_same_face(self):
        # Same count AND same face is disallowed; must retry
        with patch('builtins.input', side_effect=['B', '3', '4', '3', '5']), patch('builtins.print'):
            result = human_input_handler(self._decision_request(prev_bid=Bid(3, 4)))
        self.assertEqual(result['bid'], Bid(3, 5))

    # --- decision: invalid action choice retry ---

    def test_decision_invalid_choice_retries(self):
        with patch('builtins.input', side_effect=['X', 'C']), patch('builtins.print'):
            result = human_input_handler(self._decision_request())
        self.assertEqual(result['action'], Action.CHALLENGE)

    def test_decision_lowercase_rejected_then_valid(self):
        with patch('builtins.input', side_effect=['c', 'C']), patch('builtins.print'):
            result = human_input_handler(self._decision_request())
        self.assertEqual(result['action'], Action.CHALLENGE)


if __name__ == '__main__':
    unittest.main()
