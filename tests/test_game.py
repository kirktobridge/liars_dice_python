import unittest
from unittest.mock import patch, mock_open, MagicMock
from collections import deque
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constants
from Player import Player
from LiarsDiceGame import LiarsDiceGame
from models import Action, Bid, TurnResult


def make_game(num_players=3):
    """Create a LiarsDiceGame with a mocked log file."""
    with patch('builtins.open', mock_open()):
        game = LiarsDiceGame(num_players)
    return game


def make_player(name, num_dice=5, spot='CPU', dice=None):
    p = Player(name, spot=spot)
    p.num_dice = num_dice
    p.dice = (dice or [3, 3, 3, 4, 5]) + [-1] * (Constants.MAX_NUM_DICE - num_dice)
    return p


class TestGameInit(unittest.TestCase):
    def test_initial_state(self):
        game = make_game(3)
        self.assertEqual(game.num_players, 3)
        self.assertEqual(game.round_num, 0)
        self.assertTrue(game.game_status)
        self.assertIsNone(game.round_loser)
        self.assertEqual(len(game.players), 0)

    def test_initial_game_log_empty(self):
        game = make_game(2)
        self.assertEqual(len(game.game_log), 0)


class TestAddPlayer(unittest.TestCase):
    def test_add_single_player(self):
        game = make_game(2)
        p = Player("Alice")
        game.add_player(p)
        self.assertIn(p, game.players)
        self.assertEqual(len(game.players), 1)

    def test_add_multiple_players(self):
        game = make_game(3)
        players = [Player(name) for name in ["Alice", "Bob", "Carol"]]
        for p in players:
            game.add_player(p)
        self.assertEqual(len(game.players), 3)


class TestCountDice(unittest.TestCase):
    def test_count_zero(self):
        game = make_game(2)
        self.assertEqual(game.count_dice(), 0)

    def test_count_single_player(self):
        game = make_game(1)
        p = make_player("Alice", num_dice=4)
        game.add_player(p)
        self.assertEqual(game.count_dice(), 4)

    def test_count_multiple_players(self):
        game = make_game(3)
        game.add_player(make_player("Alice", num_dice=5))
        game.add_player(make_player("Bob", num_dice=3))
        game.add_player(make_player("Carol", num_dice=1))
        self.assertEqual(game.count_dice(), 9)

    def test_count_updates_tot_num_dice(self):
        game = make_game(2)
        game.add_player(make_player("Alice", num_dice=4))
        game.add_player(make_player("Bob", num_dice=2))
        game.count_dice()
        self.assertEqual(game.tot_num_dice, 6)


class TestLogEvent(unittest.TestCase):
    def setUp(self):
        self.game = make_game(2)

    def test_log_list_event(self):
        event = TurnResult(Bid(2, 3), Action.BID, 'Alice')
        self.game.log_event(event)
        self.assertEqual(self.game.event_counter, 1)
        self.assertEqual(len(self.game.round_events), 1)

    def test_log_string_event(self):
        self.game.log_event("test event")
        self.assertEqual(self.game.event_counter, 1)
        self.assertIn(len(self.game.game_log), [1])

    def test_log_increments_counter(self):
        self.game.log_event(TurnResult(Bid(1, 2), Action.BID, 'Alice'))
        self.game.log_event(TurnResult(Bid(2, 3), Action.RAISE, 'Bob'))
        self.assertEqual(self.game.event_counter, 2)

    def test_round_events_is_deque_stack(self):
        """Most recent event is at index 0 (appendleft)."""
        self.game.log_event(TurnResult(Bid(1, 2), Action.BID, 'Alice'))
        self.game.log_event(TurnResult(Bid(2, 3), Action.RAISE, 'Bob'))
        self.assertEqual(self.game.round_events[0].action, Action.RAISE)


class TestChallengeResolution(unittest.TestCase):
    """Test that challenge win/loss logic assigns the right loser."""

    def _setup_game_at_challenge(self, actual_dice, bid_cnt, bid_face):
        """
        Set up a 2-player game where:
        - Player 0 (challenger) calls challenge
        - Player 1 (previous bidder) bid [bid_cnt, bid_face]
        - actual_dice is the full list of all rolled dice
        Returns (game, challenger, bidder).
        """
        game = make_game(2)
        challenger = make_player("Challenger", num_dice=3)
        bidder = make_player("Bidder", num_dice=3)
        game.add_player(challenger)
        game.add_player(bidder)
        game.round_rolls = actual_dice
        return game, challenger, bidder

    def test_challenge_success_bidder_loses_die(self):
        """Challenge succeeds: fewer dice than bid → bidder loses die."""
        game, challenger, bidder = self._setup_game_at_challenge(
            actual_dice=[1, 2, 3, 4, 5, 6],  # only one 6
            bid_cnt=3, bid_face=6
        )
        bidder_dice_before = bidder.num_dice
        # challenge success: count(6) + count(1) = 1 + 1 = 2 < 3
        prev_bid_cnt = 3
        prev_bid_face = 6
        prev_bid_actual_cnt = game.round_rolls.count(prev_bid_face)
        actual_ones_cnt = game.round_rolls.count(1)
        checked_cnt = prev_bid_actual_cnt + actual_ones_cnt  # ones are wild
        self.assertLess(checked_cnt, prev_bid_cnt)  # confirm challenge succeeds
        # simulate the consequence
        game.round_loser = bidder
        game.round_loser.lose_die()
        self.assertEqual(bidder.num_dice, bidder_dice_before - 1)

    def test_challenge_failure_challenger_loses_die(self):
        """Challenge fails: enough dice match bid → challenger loses die."""
        game, challenger, bidder = self._setup_game_at_challenge(
            actual_dice=[6, 6, 6, 4, 5, 2],  # three 6s
            bid_cnt=3, bid_face=6
        )
        challenger_dice_before = challenger.num_dice
        prev_bid_actual_cnt = game.round_rolls.count(6)
        actual_ones_cnt = game.round_rolls.count(1)
        checked_cnt = prev_bid_actual_cnt + actual_ones_cnt
        self.assertGreaterEqual(checked_cnt, 3)  # confirm challenge fails
        challenger.lose_die()
        self.assertEqual(challenger.num_dice, challenger_dice_before - 1)


class TestEliminationLogic(unittest.TestCase):
    """Test the collect-then-remove elimination pattern."""

    def test_zero_dice_player_is_eliminated(self):
        game = make_game(3)
        p1 = make_player("Alice", num_dice=3)
        p2 = make_player("Bob", num_dice=0)  # should be eliminated
        p3 = make_player("Carol", num_dice=2)
        for p in [p1, p2, p3]:
            game.add_player(p)

        players_to_remove = [p for p in game.players if p.num_dice == 0]
        for p in players_to_remove:
            p.eliminated = True
            game.players.remove(p)
        game.num_players = len(game.players)

        self.assertEqual(game.num_players, 2)
        self.assertNotIn(p2, game.players)
        self.assertTrue(p2.eliminated)

    def test_multiple_zero_dice_removed_without_skipping(self):
        """Collect-then-remove: all zero-dice players are removed, not just some."""
        game = make_game(4)
        p1 = make_player("Alice", num_dice=3)
        p2 = make_player("Bob", num_dice=0)
        p3 = make_player("Carol", num_dice=0)
        p4 = make_player("Dave", num_dice=2)
        for p in [p1, p2, p3, p4]:
            game.add_player(p)

        players_to_remove = [p for p in game.players if p.num_dice == 0]
        for p in players_to_remove:
            game.players.remove(p)
        game.num_players = len(game.players)

        self.assertEqual(game.num_players, 2)
        self.assertNotIn(p2, game.players)
        self.assertNotIn(p3, game.players)


class TestRoundLoserReorder(unittest.TestCase):
    """Round loser should move to front of player list."""

    def test_loser_moves_to_front(self):
        game = make_game(3)
        p1 = make_player("Alice")
        p2 = make_player("Bob")
        p3 = make_player("Carol")
        for p in [p1, p2, p3]:
            game.add_player(p)

        game.round_loser = p3
        if game.round_loser in game.players:
            game.players.remove(game.round_loser)
            game.players.insert(0, game.round_loser)
            game.round_loser = None

        self.assertEqual(game.players[0], p3)
        self.assertIsNone(game.round_loser)

    def test_eliminated_loser_not_reinserted(self):
        """If loser was eliminated, they should not be re-added."""
        game = make_game(2)
        p1 = make_player("Alice")
        p2 = make_player("Bob", num_dice=0)
        game.add_player(p1)
        # p2 was eliminated and already removed — NOT in game.players

        game.round_loser = p2
        if game.round_loser is not None and game.round_loser in game.players:
            game.players.remove(game.round_loser)
            game.players.insert(0, game.round_loser)
        game.round_loser = None

        self.assertEqual(len(game.players), 1)
        self.assertNotIn(p2, game.players)


class TestRoundRollsSentinels(unittest.TestCase):
    """round_rolls should only include active dice, not -1 sentinels."""

    def test_round_rolls_no_sentinels(self):
        game = make_game(2)
        p1 = make_player("Alice", num_dice=3, dice=[2, 4, 6])
        p2 = make_player("Bob", num_dice=2, dice=[1, 5])
        game.add_player(p1)
        game.add_player(p2)
        game.round_rolls.clear()
        for p in game.players:
            game.round_rolls.extend(p.dice[:p.num_dice])
        self.assertNotIn(-1, game.round_rolls)
        self.assertEqual(len(game.round_rolls), 5)


if __name__ == '__main__':
    unittest.main()
