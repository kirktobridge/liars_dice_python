import unittest
from unittest.mock import patch, mock_open, MagicMock
from collections import deque
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import constants as Constants
from Player import Player
from LiarsDiceGame import LiarsDiceGame
from models import Action, Bid, GameState, PlayerState, TurnResult
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
        self.assertEqual(game.start_index, 0)

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

        # Seat order is preserved; start_index now points at p3 (index 2)
        self.assertEqual(game.players, [p1, p2, p3])
        self.assertEqual(game.start_index, 2)
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

    def test_parallel_false_does_not_spawn_processes(self):
        from unittest.mock import patch
        with patch('tournament.ProcessPoolExecutor') as mock_executor:
            df, _, _ = run_tournament(n=5, num_players=3, parallel=False)
        mock_executor.assert_not_called()
        self.assertEqual(len(df), 5)


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



class TestSnapshot(unittest.TestCase):
    def _make_two_player_game(self):
        game = make_game(2)
        game.add_player(make_player("Alice", num_dice=4))
        game.add_player(make_player("Bob", num_dice=3))
        return game

    def test_snapshot_initial_state(self):
        game = self._make_two_player_game()
        snap = game.snapshot()
        self.assertEqual(snap.round_num, 0)
        self.assertIsNone(snap.prev_bid)
        self.assertIsNone(snap.prev_bidder)
        self.assertIsNone(snap.current_player)
        self.assertFalse(snap.game_over)
        self.assertIsNone(snap.winner)
        self.assertEqual(len(snap.active_players), 2)

    def test_snapshot_active_players_fields(self):
        game = self._make_two_player_game()
        snap = game.snapshot()
        alice = next(p for p in snap.active_players if p.name == "Alice")
        self.assertEqual(alice.num_dice, 4)
        self.assertEqual(alice.player_type, "CPU")
        self.assertFalse(alice.is_eliminated)

    def test_snapshot_mid_round_prev_bid(self):
        game = self._make_two_player_game()
        game.round_num = 1
        game.log_event(TurnResult(Bid(3, 5), Action.BID, "Alice"))
        snap = game.snapshot()
        self.assertEqual(snap.prev_bid, Bid(3, 5))
        self.assertEqual(snap.prev_bidder, "Alice")
        self.assertEqual(snap.current_player, "Alice")
        self.assertFalse(snap.game_over)

    def test_snapshot_mid_round_raise_overwrites_bid(self):
        game = self._make_two_player_game()
        game.round_num = 1
        game.log_event(TurnResult(Bid(3, 5), Action.BID, "Alice"))
        game.log_event(TurnResult(Bid(4, 5), Action.RAISE, "Bob"))
        snap = game.snapshot()
        self.assertEqual(snap.prev_bid, Bid(4, 5))
        self.assertEqual(snap.prev_bidder, "Bob")
        self.assertEqual(snap.current_player, "Bob")

    def test_snapshot_post_game(self):
        game = make_game(2)
        game.add_player(make_player("Winner", num_dice=3))
        game.game_status = False
        snap = game.snapshot()
        self.assertTrue(snap.game_over)
        self.assertEqual(snap.winner, "Winner")

    def test_snapshot_game_not_over_no_winner(self):
        game = self._make_two_player_game()
        snap = game.snapshot()
        self.assertFalse(snap.game_over)
        self.assertIsNone(snap.winner)

    def test_snapshot_to_dict_json_serializable(self):
        import json
        game = self._make_two_player_game()
        game.round_num = 2
        game.log_event(TurnResult(Bid(2, 4), Action.BID, "Alice"))
        snap = game.snapshot()
        d = snap.to_dict()
        self.assertIsInstance(d, dict)
        json_str = json.dumps(d)
        restored = json.loads(json_str)
        self.assertEqual(restored['round_num'], 2)
        self.assertEqual(restored['prev_bid'], {'count': 2, 'face': 4})
        self.assertEqual(len(restored['active_players']), 2)

    def test_snapshot_to_dict_no_bid_json_serializable(self):
        import json
        game = self._make_two_player_game()
        snap = game.snapshot()
        json_str = json.dumps(snap.to_dict())
        restored = json.loads(json_str)
        self.assertIsNone(restored['prev_bid'])
        self.assertIsNone(restored['winner'])

    def test_snapshot_integration_after_process_round(self):
        events = []
        game = make_game(2)
        game._on_event = events.append
        p1 = make_player("P1", num_dice=5, dice=[3, 3, 3, 3, 3])
        p2 = make_player("P2", num_dice=5, dice=[6, 6, 6, 6, 6])
        game.add_player(p1)
        game.add_player(p2)
        with patch.object(p1, 'roll'), patch.object(p2, 'roll'), \
             patch.object(p1, 'take_turn', return_value=TurnResult(Bid(2, 3), Action.BID, 'P1')), \
             patch.object(p2, 'take_turn', return_value=TurnResult(None, Action.CHALLENGE, 'P2')):
            game.process_round()
        snap = game.snapshot()
        self.assertEqual(snap.round_num, 1)
        self.assertFalse(snap.game_over)
        self.assertEqual(len(snap.active_players), 2)
        names = [p.name for p in snap.active_players]
        self.assertIn('P1', names)
        self.assertIn('P2', names)


class TestSeatOrderPreservation(unittest.TestCase):
    """
    Verify that self.players is never reordered; only start_index shifts.

    Scenarios covered:
    - _reorder_for_next_round sets start_index, leaves list unchanged
    - no loser → start_index unchanged
    - loser/idx fields cleared after reorder
    - eliminated loser: start_index advances to next surviving seat
    - eliminated loser at last index: wraps to 0
    - players list order is stable across multiple real rounds
    - actual call order in process_round matches start_index (incl. wrap-around)
    """

    def _three_player_game(self):
        game = make_game(3)
        p1 = make_player("P1", num_dice=5, dice=[3] * 5)
        p2 = make_player("P2", num_dice=5, dice=[3] * 5)
        p3 = make_player("P3", num_dice=5, dice=[3] * 5)
        for p in [p1, p2, p3]:
            game.add_player(p)
        return game, p1, p2, p3

    # --- _reorder_for_next_round unit tests ---

    def test_reorder_sets_start_index_not_list_position(self):
        """Loser at index 1: start_index becomes 1; players list is unchanged."""
        game, p1, p2, p3 = self._three_player_game()
        game.round_loser = p2
        game._reorder_for_next_round()
        self.assertEqual(game.players, [p1, p2, p3])
        self.assertEqual(game.start_index, 1)

    def test_reorder_last_player_as_loser(self):
        game, p1, p2, p3 = self._three_player_game()
        game.round_loser = p3
        game._reorder_for_next_round()
        self.assertEqual(game.players, [p1, p2, p3])
        self.assertEqual(game.start_index, 2)

    def test_reorder_first_player_as_loser_resets_to_zero(self):
        game, p1, p2, p3 = self._three_player_game()
        game.start_index = 2  # previously non-zero
        game.round_loser = p1
        game._reorder_for_next_round()
        self.assertEqual(game.start_index, 0)

    def test_no_loser_leaves_start_index_unchanged(self):
        game, p1, p2, p3 = self._three_player_game()
        game.start_index = 2
        game.round_loser = None
        game._reorder_for_next_round()
        self.assertEqual(game.start_index, 2)

    def test_round_loser_and_idx_cleared_after_reorder(self):
        game, p1, p2, p3 = self._three_player_game()
        game.round_loser = p2
        game._round_loser_idx = 1
        game._reorder_for_next_round()
        self.assertIsNone(game.round_loser)
        self.assertIsNone(game._round_loser_idx)

    # --- eliminated-loser edge cases ---

    def test_eliminated_loser_advances_to_next_seat(self):
        """Eliminated loser was at idx 1 in a 3-player list → survivors [p1, p3].
        Next seat after idx 1 is now idx 1 in the 2-player list (p3)."""
        game = make_game(2)
        p1 = make_player("P1")
        p3 = make_player("P3")
        game.add_player(p1)   # idx 0
        game.add_player(p3)   # idx 1 (p2 already removed by _eliminate_players)
        p2 = make_player("P2", num_dice=0)   # eliminated, not in players
        game.round_loser = p2
        game._round_loser_idx = 1
        game._reorder_for_next_round()   # 1 % 2 = 1 → p3
        self.assertEqual(game.start_index, 1)

    def test_eliminated_loser_at_last_seat_wraps_to_zero(self):
        """Eliminated loser was the last player (idx 2 in 3-player list).
        After removal, survivors = [p1, p2]; idx 2 % 2 = 0 → p1 starts."""
        game = make_game(2)
        p1 = make_player("P1")
        p2 = make_player("P2")
        game.add_player(p1)
        game.add_player(p2)
        p3 = make_player("P3", num_dice=0)
        game.round_loser = p3
        game._round_loser_idx = 2
        game._reorder_for_next_round()   # 2 % 2 = 0 → p1
        self.assertEqual(game.start_index, 0)

    # --- integration: players list never mutated across real rounds ---

    def test_players_list_never_mutated_across_rounds(self):
        """Running multiple rounds with different losers must not change
        the relative order of surviving players in self.players."""
        game, p1, p2, p3 = self._three_player_game()
        original_order = list(game.players)

        # P2 repeatedly overbids; P3 challenges each round → P2 loses a die
        # round_rolls = [3]*15; bid=(16,3); 15<16 → challenge succeeds
        for _ in range(3):
            if not game.game_status:
                break
            with patch.object(p1, 'roll'), patch.object(p2, 'roll'), patch.object(p3, 'roll'), \
                 patch.object(p1, 'take_turn', return_value=TurnResult(Bid(1, 3), Action.BID, 'P1')), \
                 patch.object(p2, 'take_turn', return_value=TurnResult(Bid(16, 3), Action.RAISE, 'P2')), \
                 patch.object(p3, 'take_turn', return_value=TurnResult(None, Action.CHALLENGE, 'P3')):
                game.process_round()

        surviving_in_original_order = [p for p in original_order if not p.eliminated]
        self.assertEqual(game.players, surviving_in_original_order)

    # --- integration: actual turn-call order follows start_index ---

    def test_round_starts_from_start_index(self):
        """After round 1 makes P2 the loser (start_index=1), round 2's
        first take_turn call goes to P2, then P3 in seat order."""
        game, p1, p2, p3 = self._three_player_game()

        # Round 1: P1 bids (1,3), P2 raises to (16,3), P3 challenges.
        # actual 3s = 15 < 16 → challenge succeeds → P2 (bidder) loses.
        with patch.object(p1, 'roll'), patch.object(p2, 'roll'), patch.object(p3, 'roll'), \
             patch.object(p1, 'take_turn', return_value=TurnResult(Bid(1, 3), Action.BID, 'P1')), \
             patch.object(p2, 'take_turn', return_value=TurnResult(Bid(16, 3), Action.RAISE, 'P2')), \
             patch.object(p3, 'take_turn', return_value=TurnResult(None, Action.CHALLENGE, 'P3')):
            game.process_round()

        self.assertEqual(game.start_index, 1)   # P2 is at index 1

        call_order = []

        def make_recorder(player_obj):
            def _take_turn(*args, **kwargs):
                call_order.append(player_obj.name)
                if len(call_order) == 1:
                    return TurnResult(Bid(1, 6), Action.BID, player_obj.name)
                return TurnResult(None, Action.CHALLENGE, player_obj.name)
            return _take_turn

        with patch.object(p1, 'roll'), patch.object(p2, 'roll'), patch.object(p3, 'roll'), \
             patch.object(p1, 'take_turn', side_effect=make_recorder(p1)), \
             patch.object(p2, 'take_turn', side_effect=make_recorder(p2)), \
             patch.object(p3, 'take_turn', side_effect=make_recorder(p3)):
            game.process_round()

        # P2 must be first; P3 second (challenges and ends the round)
        self.assertEqual(call_order[0], 'P2')
        self.assertEqual(call_order[1], 'P3')

    def test_start_index_wraps_around_end_of_list(self):
        """With start_index=2, P3 goes first, then P1 (wrap-around), not P1 first."""
        game, p1, p2, p3 = self._three_player_game()
        game.start_index = 2

        call_order = []

        def make_recorder(player_obj):
            def _take_turn(*args, **kwargs):
                call_order.append(player_obj.name)
                if len(call_order) == 1:
                    return TurnResult(Bid(1, 6), Action.BID, player_obj.name)
                return TurnResult(None, Action.CHALLENGE, player_obj.name)
            return _take_turn

        with patch.object(p1, 'roll'), patch.object(p2, 'roll'), patch.object(p3, 'roll'), \
             patch.object(p1, 'take_turn', side_effect=make_recorder(p1)), \
             patch.object(p2, 'take_turn', side_effect=make_recorder(p2)), \
             patch.object(p3, 'take_turn', side_effect=make_recorder(p3)):
            game.process_round()

        # start_index=2 → P3 (idx 2) first, then P1 (idx 0, wrap), then P2 (idx 1)
        self.assertEqual(call_order[0], 'P3')
        self.assertEqual(call_order[1], 'P1')   # wraps around


if __name__ == '__main__':
    unittest.main()
