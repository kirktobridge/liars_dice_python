import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stats_collector import GameStatsCollector
from stats_schema import RoundRow, EliminationRow


def _make_collector(seed=0, num_players=3):
    return GameStatsCollector(seed=seed, num_players=num_players)


def _round_started(round_num=1):
    return {'type': 'round_started', 'round_num': round_num}


def _bid_made():
    return {'type': 'bid_made'}


def _raise_made():
    return {'type': 'raise_made'}


def _challenge_called(challenger='Bob', bidder='Alice', tot=10, bid_count=3, bid_face=4, bidder_num_dice=5):
    return {
        'type': 'challenge_called',
        'challenger_name': challenger,
        'bidder_name': bidder,
        'tot_num_dice': tot,
        'bid_count': bid_count,
        'bid_face': bid_face,
        'bidder_num_dice': bidder_num_dice,
    }


def _challenge_resolved(succeeded, actual=3, ones=1, bid_face=4):
    return {
        'type': 'challenge_resolved',
        'succeeded': succeeded,
        'actual_count': actual,
        'ones_count': ones,
        'bid_face': bid_face,
    }


def _spot_on_called(caller='Bob', tot=10, bid_count=3, bid_face=4):
    return {
        'type': 'spot_on_called',
        'caller_name': caller,
        'tot_num_dice': tot,
        'bid_count': bid_count,
        'bid_face': bid_face,
    }


def _spot_on_resolved(succeeded):
    return {'type': 'spot_on_resolved', 'succeeded': succeeded}


def _player_eliminated(name='Alice'):
    return {'type': 'player_eliminated', 'player_name': name}


def _game_won(winner='Carol'):
    return {'type': 'game_won', 'winner_name': winner}


class TestStatsCollectorInit(unittest.TestCase):
    def test_initial_state(self):
        c = _make_collector(seed=7, num_players=4)
        self.assertEqual(c.seed, 7)
        self.assertEqual(c.num_players, 4)
        self.assertEqual(c._cur_round, 0)
        self.assertEqual(c._bid_count, 0)
        self.assertEqual(len(c.round_rows), 0)
        self.assertEqual(len(c.elimination_rows), 0)


class TestFlushRound(unittest.TestCase):
    def test_flush_skips_when_cur_round_is_zero(self):
        c = _make_collector()
        c._flush_round()
        self.assertEqual(len(c.round_rows), 0)

    def test_flush_appends_round_row(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_challenge_called())
        c.on_event(_challenge_resolved(True))
        c._flush_round()
        self.assertEqual(len(c.round_rows), 1)
        self.assertIsInstance(c.round_rows[0], RoundRow)

    def test_flush_round_action_caller_is_none_when_no_action(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c._flush_round()
        row = c.round_rows[0]
        self.assertIsNone(row.action_caller)
        self.assertEqual(row.action_type, 'none')


class TestRoundStarted(unittest.TestCase):
    def test_resets_round_level_state(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_bid_made())
        c.on_event(_bid_made())
        self.assertEqual(c._bid_count, 2)

        c.on_event(_round_started(2))
        self.assertEqual(c._cur_round, 2)
        self.assertEqual(c._bid_count, 0)
        self.assertIsNone(c._challenger_name)
        self.assertIsNone(c._bidder_name)
        self.assertIsNone(c._round_loser)
        self.assertIsNone(c._bid_face)

    def test_round_started_flushes_previous_round(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_challenge_called())
        c.on_event(_challenge_resolved(True))
        c.on_event(_round_started(2))
        self.assertEqual(len(c.round_rows), 1)
        self.assertEqual(c.round_rows[0].round_num, 1)


class TestBidCounting(unittest.TestCase):
    def test_bid_made_increments_count(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_bid_made())
        c.on_event(_bid_made())
        self.assertEqual(c._bid_count, 2)

    def test_raise_made_increments_count(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_bid_made())
        c.on_event(_raise_made())
        self.assertEqual(c._bid_count, 2)

    def test_mixed_bids_and_raises(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        for _ in range(3):
            c.on_event(_bid_made())
        for _ in range(2):
            c.on_event(_raise_made())
        self.assertEqual(c._bid_count, 5)


class TestChallengeCalled(unittest.TestCase):
    def test_captures_all_challenge_fields(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_challenge_called(
            challenger='Bob', bidder='Alice',
            tot=12, bid_count=4, bid_face=5, bidder_num_dice=3,
        ))
        self.assertEqual(c._action_type, 'challenge')
        self.assertEqual(c._challenger_name, 'Bob')
        self.assertEqual(c._bidder_name, 'Alice')
        self.assertEqual(c._tot_num_dice, 12)
        self.assertEqual(c._bid_count_claimed, 4)
        self.assertEqual(c._bid_face, 5)
        self.assertEqual(c._bidder_num_dice, 3)


class TestChallengeResolved(unittest.TestCase):
    def test_success_sets_bidder_as_loser(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_challenge_called(challenger='Bob', bidder='Alice'))
        c.on_event(_challenge_resolved(succeeded=True))
        self.assertTrue(c._challenge_succeeded)
        self.assertEqual(c._round_loser, 'Alice')

    def test_failure_sets_challenger_as_loser(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_challenge_called(challenger='Bob', bidder='Alice'))
        c.on_event(_challenge_resolved(succeeded=False))
        self.assertFalse(c._challenge_succeeded)
        self.assertEqual(c._round_loser, 'Bob')

    def test_effective_count_adds_ones_for_non_one_face(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_challenge_called(bid_face=4))
        c.on_event(_challenge_resolved(succeeded=True, actual=2, ones=1, bid_face=4))
        self.assertEqual(c._effective_actual_count, 3)

    def test_effective_count_no_ones_bonus_when_face_is_one(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_challenge_called(bid_face=1))
        c.on_event(_challenge_resolved(succeeded=True, actual=2, ones=2, bid_face=1))
        self.assertEqual(c._effective_actual_count, 2)

    def test_round_row_action_caller_is_challenger(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_challenge_called(challenger='Bob'))
        c.on_event(_challenge_resolved(succeeded=True))
        c.on_event(_game_won('Bob'))
        row = c.round_rows[0]
        self.assertEqual(row.action_caller, 'Bob')
        self.assertEqual(row.action_type, 'challenge')


class TestSpotOnCalled(unittest.TestCase):
    def test_captures_all_spot_on_fields(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_spot_on_called(caller='Carol', tot=8, bid_count=3, bid_face=6))
        self.assertEqual(c._action_type, 'spot_on')
        self.assertEqual(c._caller_name, 'Carol')
        self.assertEqual(c._tot_num_dice, 8)
        self.assertEqual(c._bid_count_claimed, 3)
        self.assertEqual(c._bid_face, 6)


class TestSpotOnResolved(unittest.TestCase):
    def test_success_sets_round_loser_to_multiple(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_spot_on_called(caller='Carol'))
        c.on_event(_spot_on_resolved(succeeded=True))
        self.assertTrue(c._challenge_succeeded)
        self.assertEqual(c._round_loser, 'multiple')

    def test_failure_sets_caller_as_loser(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_spot_on_called(caller='Carol'))
        c.on_event(_spot_on_resolved(succeeded=False))
        self.assertFalse(c._challenge_succeeded)
        self.assertEqual(c._round_loser, 'Carol')

    def test_round_row_action_caller_is_caller_name(self):
        c = _make_collector()
        c.on_event(_round_started(1))
        c.on_event(_spot_on_called(caller='Dave'))
        c.on_event(_spot_on_resolved(succeeded=False))
        c.on_event(_game_won('Alice'))
        row = c.round_rows[0]
        self.assertEqual(row.action_caller, 'Dave')
        self.assertEqual(row.action_type, 'spot_on')


class TestPlayerEliminated(unittest.TestCase):
    def test_first_elimination_gets_position_one(self):
        c = _make_collector(num_players=3)
        c.on_event(_player_eliminated('Alice'))
        self.assertEqual(len(c.elimination_rows), 1)
        row = c.elimination_rows[0]
        self.assertEqual(row.player_name, 'Alice')
        self.assertEqual(row.finishing_position, 1)
        self.assertEqual(row.seed, 0)

    def test_second_elimination_gets_position_two(self):
        c = _make_collector(num_players=3)
        c.on_event(_player_eliminated('Alice'))
        c.on_event(_player_eliminated('Bob'))
        self.assertEqual(c.elimination_rows[1].finishing_position, 2)


class TestGameWon(unittest.TestCase):
    def test_game_won_flushes_last_round(self):
        c = _make_collector(num_players=2)
        c.on_event(_round_started(1))
        c.on_event(_challenge_called())
        c.on_event(_challenge_resolved(succeeded=True))
        self.assertEqual(len(c.round_rows), 0)
        c.on_event(_game_won('Alice'))
        self.assertEqual(len(c.round_rows), 1)

    def test_game_won_appends_winner_elimination_row(self):
        c = _make_collector(num_players=2)
        c.on_event(_round_started(1))
        c.on_event(_challenge_called())
        c.on_event(_challenge_resolved(succeeded=True))
        c.on_event(_game_won('Alice'))
        winner_row = c.elimination_rows[-1]
        self.assertEqual(winner_row.player_name, 'Alice')
        self.assertEqual(winner_row.finishing_position, c.num_players)

    def test_winner_position_equals_num_players(self):
        c = _make_collector(num_players=4)
        c.on_event(_game_won('Winner'))
        self.assertEqual(c.elimination_rows[-1].finishing_position, 4)


class TestFullHappyPath(unittest.TestCase):
    def test_challenge_sequence_produces_correct_round_row(self):
        c = _make_collector(seed=42, num_players=3)

        c.on_event(_round_started(1))
        c.on_event(_bid_made())
        c.on_event(_bid_made())
        c.on_event(_raise_made())
        c.on_event(_challenge_called(
            challenger='Bob', bidder='Alice',
            tot=15, bid_count=4, bid_face=3, bidder_num_dice=5,
        ))
        c.on_event(_challenge_resolved(succeeded=True, actual=3, ones=2, bid_face=3))
        c.on_event(_game_won('Bob'))

        self.assertEqual(len(c.round_rows), 1)
        row = c.round_rows[0]
        self.assertEqual(row.seed, 42)
        self.assertEqual(row.round_num, 1)
        self.assertEqual(row.bid_count, 3)
        self.assertEqual(row.action_type, 'challenge')
        self.assertEqual(row.action_caller, 'Bob')
        self.assertEqual(row.bid_count_claimed, 4)
        self.assertEqual(row.total_dice_on_table, 15)
        self.assertEqual(row.bidder_num_dice, 5)
        self.assertTrue(row.challenge_succeeded)
        self.assertEqual(row.round_loser, 'Alice')
        self.assertEqual(row.effective_actual_count, 5)

    def test_two_round_game_produces_two_rows(self):
        c = _make_collector(seed=1, num_players=2)

        for rnd in [1, 2]:
            c.on_event(_round_started(rnd))
            c.on_event(_bid_made())
            c.on_event(_challenge_called(challenger='Bob', bidder='Alice'))
            c.on_event(_challenge_resolved(succeeded=True))

        c.on_event(_game_won('Bob'))

        self.assertEqual(len(c.round_rows), 2)
        self.assertEqual(c.round_rows[0].round_num, 1)
        self.assertEqual(c.round_rows[1].round_num, 2)


if __name__ == '__main__':
    unittest.main()
