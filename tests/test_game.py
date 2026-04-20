import unittest
from unittest.mock import patch, mock_open, MagicMock
from collections import deque
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import constants as Constants
from Player import Player
from LiarsDiceGame import LiarsDiceGame
from models import Action, Bid, TurnResult
from tournament import run_game, run_tournament


def make_game(num_players=3):
    """Create a LiarsDiceGame with no logging and no on_event renderer."""
    return LiarsDiceGame(num_players)


def make_player(name, num_dice=5, player_type='CPU', dice=None):
    p = Player(name, player_type=player_type)
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
        game = make_game(2)
        game.add_player(make_player("Alice", num_dice=4))
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
        game = LiarsDiceGame(2, on_event=lambda e: None)
        game.log_event("test event")
        self.assertEqual(game.event_counter, 1)
        self.assertEqual(len(game.round_events), 1)

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
        """Challenge succeeds: fewer dice than bid → _resolve_challenge returns bidder as loser."""
        game, challenger, bidder = self._setup_game_at_challenge(
            actual_dice=[1, 2, 3, 4, 5, 6],  # count(6)+count(1) = 1+1 = 2 < 3
            bid_cnt=3, bid_face=6
        )
        succeeded, loser = game._resolve_challenge(Bid(3, 6), challenger, bidder)
        self.assertTrue(succeeded)
        self.assertIs(loser, bidder)

    def test_challenge_failure_challenger_loses_die(self):
        """Challenge fails: enough dice match bid → _resolve_challenge returns challenger as loser."""
        game, challenger, bidder = self._setup_game_at_challenge(
            actual_dice=[6, 6, 6, 4, 5, 2],  # count(6)+count(1) = 3+0 = 3 >= 3
            bid_cnt=3, bid_face=6
        )
        succeeded, loser = game._resolve_challenge(Bid(3, 6), challenger, bidder)
        self.assertFalse(succeeded)
        self.assertIs(loser, challenger)


class TestEliminationLogic(unittest.TestCase):
    """Test the collect-then-remove elimination pattern."""

    def test_zero_dice_player_is_eliminated(self):
        game = make_game(3)
        p1 = make_player("Alice", num_dice=3)
        p2 = make_player("Bob", num_dice=0)  # should be eliminated
        p3 = make_player("Carol", num_dice=2)
        for p in [p1, p2, p3]:
            game.add_player(p)

        removed = game._eliminate_players()

        self.assertEqual(game.num_players, 2)
        self.assertNotIn(p2, game.players)
        self.assertTrue(p2.eliminated)
        self.assertIn(p2, removed)

    def test_multiple_zero_dice_removed_without_skipping(self):
        """_eliminate_players removes all zero-dice players in one pass."""
        game = make_game(4)
        p1 = make_player("Alice", num_dice=3)
        p2 = make_player("Bob", num_dice=0)
        p3 = make_player("Carol", num_dice=0)
        p4 = make_player("Dave", num_dice=2)
        for p in [p1, p2, p3, p4]:
            game.add_player(p)

        removed = game._eliminate_players()

        self.assertEqual(game.num_players, 2)
        self.assertNotIn(p2, game.players)
        self.assertNotIn(p3, game.players)
        self.assertEqual(len(removed), 2)


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
        game._reorder_for_next_round()

        self.assertEqual(game.players[0], p3)
        self.assertIsNone(game.round_loser)

    def test_eliminated_loser_not_reinserted(self):
        """If loser was eliminated, _reorder_for_next_round should not re-add them."""
        game = make_game(2)
        p1 = make_player("Alice")
        p2 = make_player("Bob", num_dice=0)
        game.add_player(p1)
        # p2 was eliminated and already removed — NOT in game.players

        game.round_loser = p2
        game._reorder_for_next_round()

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


class TestFullRoundIntegration(unittest.TestCase):
    def test_round_increments_state_no_renderer(self):
        """process_round() mutates game state AND fires _emit() correctly."""
        events = []
        game = make_game(2)
        game._on_event = events.append  # collect emitted events
        p1 = make_player("P1", num_dice=5, dice=[3, 3, 3, 3, 3])
        p2 = make_player("P2", num_dice=5, dice=[6, 6, 6, 6, 6])
        game.add_player(p1)
        game.add_player(p2)

        with patch.object(p1, 'roll'), \
             patch.object(p2, 'roll'), \
             patch.object(p1, 'take_turn',
                          return_value=TurnResult(Bid(2, 3), Action.BID, 'P1')), \
             patch.object(p2, 'take_turn',
                          return_value=TurnResult(None, Action.CHALLENGE, 'P2')):
            status = game.process_round()

        # round_rolls: [3,3,3,3,3,6,6,6,6,6] → count(3)=5, count(1)=0, checked=5 >= bid=2
        # → challenge FAILS → P2 loses a die (5→4)
        self.assertEqual(game.round_num, 1)
        self.assertEqual(p1.num_dice, 5)
        self.assertEqual(p2.num_dice, 4)
        self.assertEqual(game.tot_num_dice, 9)
        self.assertTrue(status)   # game still running, 2 players remain

        # Smoke-test that the dispatcher is actually wired, not just state
        event_types = [e['type'] for e in events]
        self.assertIn('round_started', event_types)
        self.assertIn('bid_made', event_types)
        self.assertIn('challenge_called', event_types)
        self.assertIn('challenge_resolved', event_types)
        self.assertIn('round_summary', event_types)

        # New schema fields
        cr = next(e for e in events if e['type'] == 'challenge_resolved')
        self.assertIn('loser_name', cr)
        self.assertEqual(cr['loser_name'], 'P2')  # challenge failed → P2 loses

        rs = next(e for e in events if e['type'] == 'round_summary')
        self.assertIn('player_dice', rs)
        self.assertIsInstance(rs['player_dice'], list)
        self.assertTrue(all('name' in entry and 'dice' in entry for entry in rs['player_dice']))


class TestRunGame(unittest.TestCase):
    def test_returns_expected_keys(self):
        result = run_game(seed=0, num_players=3)
        base_keys = {'seed', 'winner', 'rounds', 'num_players', 'winner_risk_appetite', 'winner_peer_pressure', 'winner_attentiveness',
                     '_round_rows', '_elim_rows'}
        player_keys = {f'p_{n.replace(" ", "_")}_{attr}' for n in Constants.PLAYER_NAMES[:3] for attr in ('risk', 'peer', 'att')}
        self.assertSetEqual(set(result.keys()), base_keys | player_keys)

    def test_seed_echoed_in_result(self):
        result = run_game(seed=42, num_players=3)
        self.assertEqual(result['seed'], 42)

    def test_num_players_echoed_in_result(self):
        result = run_game(seed=0, num_players=3)
        self.assertEqual(result['num_players'], 3)

    def test_winner_is_a_known_player_name(self):
        result = run_game(seed=0, num_players=3)
        self.assertIn(result['winner'], Constants.PLAYER_NAMES)

    def test_rounds_is_positive_integer(self):
        result = run_game(seed=0, num_players=3)
        self.assertIsInstance(result['rounds'], int)
        self.assertGreater(result['rounds'], 0)

    def test_same_seed_is_deterministic(self):
        r1 = run_game(seed=7, num_players=4)
        r2 = run_game(seed=7, num_players=4)
        self.assertEqual(r1, r2)

    def test_different_seeds_may_differ(self):
        results = {run_game(seed=s, num_players=4)['winner'] for s in range(20)}
        self.assertGreater(len(results), 1)


class TestRunTournament(unittest.TestCase):
    def test_returns_dataframe(self):
        import pandas as pd
        df, df_rounds, df_eliminations = run_tournament(n=5, num_players=3)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertIsInstance(df_rounds, pd.DataFrame)
        self.assertIsInstance(df_eliminations, pd.DataFrame)

    def test_row_count_matches_n(self):
        df, _, _ = run_tournament(n=10, num_players=3)
        self.assertEqual(len(df), 10)

    def test_columns_present(self):
        df, _, _ = run_tournament(n=5, num_players=3)
        base_cols = {'seed', 'winner', 'rounds', 'num_players', 'winner_risk_appetite', 'winner_peer_pressure', 'winner_attentiveness'}
        player_cols = {f'p_{n.replace(" ", "_")}_{attr}' for n in Constants.PLAYER_NAMES[:3] for attr in ('risk', 'peer', 'att')}
        self.assertSetEqual(set(df.columns), base_cols | player_cols)

    def test_seeds_are_range_n(self):
        n = 8
        df, _, _ = run_tournament(n=n, num_players=3)
        self.assertListEqual(sorted(df['seed'].tolist()), list(range(n)))


class TestSpotOnResolution(unittest.TestCase):
    def _setup(self, actual_dice, bid_cnt, bid_face):
        game = make_game(2)
        caller = make_player("Caller", num_dice=3)
        other  = make_player("Other",  num_dice=3)
        game.add_player(caller)
        game.add_player(other)
        game.round_rolls = actual_dice
        return game, caller, other

    def test_spot_on_success_others_lose(self):
        # 2 sixes + 1 one = 3 effective, bid 3 sixes → exact match
        game, caller, other = self._setup([6, 6, 1, 2, 3, 4], 3, 6)
        succeeded, losers = game._resolve_spot_on(Bid(3, 6), caller)
        self.assertTrue(succeeded)
        self.assertNotIn(caller, losers)
        self.assertIn(other, losers)

    def test_spot_on_failure_caller_loses(self):
        # 2 sixes, bid 3 sixes → 2 ≠ 3 → failure
        game, caller, other = self._setup([6, 6, 2, 3, 4, 5], 3, 6)
        succeeded, losers = game._resolve_spot_on(Bid(3, 6), caller)
        self.assertFalse(succeeded)
        self.assertEqual(losers, [caller])

    def test_spot_on_ones_bid_no_wild_bonus(self):
        # bid 2 ones; actual ones=2 → exact (ones don't get wild bonus)
        game, caller, _ = self._setup([1, 1, 2, 3, 4, 5], 2, 1)
        succeeded, _ = game._resolve_spot_on(Bid(2, 1), caller)
        self.assertTrue(succeeded)


class TestFullRoundSpotOn(unittest.TestCase):
    def _make_two_player_game(self, p1_dice, p2_dice):
        events = []
        game = make_game(2)
        game._on_event = events.append
        p1 = make_player("P1", num_dice=5, dice=p1_dice)
        p2 = make_player("P2", num_dice=5, dice=p2_dice)
        game.add_player(p1)
        game.add_player(p2)
        return game, p1, p2, events

    def test_spot_on_success_fires_events_and_others_lose_die(self):
        # round_rolls = [3]*10, bid (10, 3) → exact → P1 (other) loses die
        game, p1, p2, events = self._make_two_player_game([3] * 5, [3] * 5)
        with patch.object(p1, 'roll'), patch.object(p2, 'roll'), \
             patch.object(p1, 'take_turn', return_value=TurnResult(Bid(10, 3), Action.BID, 'P1')), \
             patch.object(p2, 'take_turn', return_value=TurnResult(None, Action.SPOT_ON, 'P2')):
            game.process_round()
        event_types = [e['type'] for e in events]
        self.assertIn('spot_on_called', event_types)
        self.assertIn('spot_on_resolved', event_types)
        self.assertEqual(p1.num_dice, 4)
        self.assertEqual(p2.num_dice, 5)

        sor = next(e for e in events if e['type'] == 'spot_on_resolved')
        self.assertIn('loser_names', sor)
        self.assertEqual(sor['loser_names'], ['P1'])  # P2 called spot-on, P1 is the other player

    def test_spot_on_failure_caller_loses_die(self):
        # round_rolls = [3]*10, bid (5, 3) → 10 ≠ 5 → caller P2 loses die
        game, p1, p2, events = self._make_two_player_game([3] * 5, [3] * 5)
        with patch.object(p1, 'roll'), patch.object(p2, 'roll'), \
             patch.object(p1, 'take_turn', return_value=TurnResult(Bid(5, 3), Action.BID, 'P1')), \
             patch.object(p2, 'take_turn', return_value=TurnResult(None, Action.SPOT_ON, 'P2')):
            game.process_round()
        self.assertEqual(p2.num_dice, 4)
        self.assertEqual(p1.num_dice, 5)

        sor = next(e for e in events if e['type'] == 'spot_on_resolved')
        self.assertIn('loser_names', sor)
        self.assertEqual(sor['loser_names'], ['P2'])  # caller loses on failure


class TestGameWon(unittest.TestCase):
    def test_game_won_emitted_and_status_false(self):
        events = []
        game = make_game(2)
        game._on_event = events.append
        p1 = make_player("P1", num_dice=1, dice=[3])
        p2 = make_player("P2", num_dice=5, dice=[6, 6, 6, 6, 6])
        game.add_player(p1)
        game.add_player(p2)
        # round_rolls=[3,6,6,6,6,6]; bid(2,3): count(3)=1 < 2 → challenge succeeds → P1 loses die → eliminated
        with patch.object(p1, 'roll'), patch.object(p2, 'roll'), \
             patch.object(p1, 'take_turn', return_value=TurnResult(Bid(2, 3), Action.BID, 'P1')), \
             patch.object(p2, 'take_turn', return_value=TurnResult(None, Action.CHALLENGE, 'P2')):
            status = game.process_round()
        self.assertFalse(status)
        self.assertEqual(game.num_players, 1)
        self.assertTrue(p1.eliminated)
        event_types = [e['type'] for e in events]
        self.assertIn('player_eliminated', event_types)
        self.assertIn('game_won', event_types)

        pe = next(e for e in events if e['type'] == 'player_eliminated')
        self.assertIn('round_num', pe)
        self.assertEqual(pe['round_num'], 1)


class TestLogEvents(unittest.TestCase):
    def test_processes_all_events(self):
        game = make_game(2)
        evts = deque([
            TurnResult(Bid(1, 2), Action.BID,  'Alice'),
            TurnResult(Bid(2, 3), Action.RAISE, 'Bob'),
        ])
        game.log_events(evts)
        self.assertEqual(game.event_counter, 2)
        self.assertEqual(len(game.round_events), 2)

    def test_empty_deque_does_not_raise(self):
        game = make_game(2)
        game.log_events(deque())  # empty deque raises internally — must not propagate


class TestCloseAndContextManager(unittest.TestCase):
    def test_close_with_logging_closes_file(self):
        with patch('logging.FileHandler') as mock_handler_cls:
            mock_handler = mock_handler_cls.return_value
            with LiarsDiceGame(2, log=True) as game:
                pass
            mock_handler.close.assert_called_once()
            self.assertIsNone(game._file_handler)

    def test_close_without_logging_is_noop(self):
        game = make_game(2)
        game.close()  # must not raise

    def test_context_manager_closes_file_on_exit(self):
        with patch('logging.FileHandler') as mock_handler_cls:
            mock_handler = mock_handler_cls.return_value
            with LiarsDiceGame(2, log=True) as game:
                pass
        mock_handler.close.assert_called_once()



if __name__ == '__main__':
    unittest.main()
