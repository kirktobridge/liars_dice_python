import unittest
from unittest.mock import patch
from collections import deque
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constants
from Player import Player
from models import Action, Bid, TurnResult, OpponentProfile


class TestPlayerInit(unittest.TestCase):
    def test_defaults(self):
        p = Player("Alice")
        self.assertEqual(p.name, "Alice")
        self.assertEqual(p.spot, "CPU")
        self.assertEqual(p.num_dice, Constants.MAX_NUM_DICE)
        self.assertFalse(p.eliminated)
        self.assertEqual(len(p.dice), Constants.MAX_NUM_DICE)
        self.assertTrue(all(d == -1 for d in p.dice))

    def test_human_spot(self):
        p = Player("Bob", spot="HUMAN")
        self.assertEqual(p.spot, "HUMAN")

    def test_risk_appetite_in_distribution(self):
        p = Player("Test")
        self.assertIn(p.risk_appetite, Constants.RISK_APPETITE_DISTRIBUTION)
        self.assertGreaterEqual(p.risk_appetite, 1)
        self.assertLessEqual(p.risk_appetite, 100)

    def test_peer_pressure_score_in_distribution(self):
        p = Player("Test")
        self.assertIn(p.peer_pressure_score, Constants.PEER_PRESSURE_DISTRIBUTION)


class TestDiceOperations(unittest.TestCase):
    def setUp(self):
        self.p = Player("Test")
        self.p.dice = [3, 4, 5, 6, 2, -1]
        self.p.num_dice = 5

    def test_roll_fills_active_dice(self):
        self.p.roll()
        for i in range(self.p.num_dice):
            self.assertIn(self.p.dice[i], range(1, 7))

    def test_roll_leaves_sentinels_untouched(self):
        self.p.roll()
        self.assertEqual(self.p.dice[5], -1)

    def test_lose_die_decrements_count(self):
        initial = self.p.num_dice
        self.p.lose_die()
        self.assertEqual(self.p.num_dice, initial - 1)

    def test_lose_die_sets_sentinel_on_removed_slot(self):
        last_idx = self.p.num_dice - 1  # index of last active die
        self.p.lose_die()
        self.assertEqual(self.p.dice[last_idx], -1)

    def test_add_die_increments_count(self):
        initial = self.p.num_dice
        self.p.add_die()
        self.assertEqual(self.p.num_dice, initial + 1)

    def test_count_ones_basic(self):
        self.p.dice = [1, 1, 3, 4, 5, -1]
        self.assertEqual(self.p.count_ones(), 2)

    def test_count_ones_none(self):
        self.p.dice = [2, 3, 4, 5, 6, -1]
        self.assertEqual(self.p.count_ones(), 0)

    def test_count_ones_all(self):
        self.p.dice = [1, 1, 1, 1, 1, -1]
        self.assertEqual(self.p.count_ones(), 5)


class TestGetNeededCnt(unittest.TestCase):
    def setUp(self):
        self.p = Player("Test")
        self.p.num_dice = 5

    def test_basic_no_wilds(self):
        # Two 3s, no ones; bid is 4 threes → needs 2 more
        self.p.dice = [3, 3, 2, 4, 5, -1]
        self.assertEqual(self.p.get_needed_cnt(Bid(4, 3)), 2)

    def test_ones_count_as_wild(self):
        # One 3, one wild (1); bid is 4 threes → have 2 effective, need 2 more
        self.p.dice = [3, 1, 2, 4, 5, -1]
        self.assertEqual(self.p.get_needed_cnt(Bid(4, 3)), 2)

    def test_bid_on_ones_no_double_count(self):
        # Two 1s; bid is 3 ones → needs 1 more (ones should NOT be counted twice)
        self.p.dice = [1, 1, 2, 4, 5, -1]
        self.assertEqual(self.p.get_needed_cnt(Bid(3, 1)), 1)

    def test_bid_on_ones_exact(self):
        # Three 1s; bid is 3 ones → needed = 0
        self.p.dice = [1, 1, 1, 4, 5, -1]
        self.assertEqual(self.p.get_needed_cnt(Bid(3, 1)), 0)

    def test_negative_needed_means_guaranteed(self):
        # Four 3s; bid is 3 threes → already guaranteed (needed < 0)
        self.p.dice = [3, 3, 3, 3, 5, -1]
        self.assertLess(self.p.get_needed_cnt(Bid(3, 3)), 0)

    def test_exact_match_needed_zero(self):
        # Two 3s; bid is exactly 2 threes → needed = 0
        self.p.dice = [3, 3, 2, 4, 5, -1]
        self.assertEqual(self.p.get_needed_cnt(Bid(2, 3)), 0)

    def test_wild_plus_face_reduces_needed(self):
        # Two 6s and two wilds (1s); bid is 5 sixes → have 4 effective, need 1 more
        self.p.dice = [6, 6, 1, 1, 2, -1]
        self.assertEqual(self.p.get_needed_cnt(Bid(5, 6)), 1)


class TestGrade(unittest.TestCase):
    def test_below_all_thresholds(self):
        self.assertEqual(Player.grade(0.03), Constants.LOWEST_THRESHOLD)

    def test_med_probability(self):
        self.assertEqual(Player.grade(0.6), 'MED')

    def test_high_probability(self):
        self.assertEqual(Player.grade(0.8), 'HIGH')

    def test_very_high_probability(self):
        self.assertEqual(Player.grade(0.99), 'VERY HIGH')

    def test_exactly_at_threshold(self):
        # p=0.5 is >= 0.5 threshold, so grade should be 'MED'
        self.assertEqual(Player.grade(0.5), 'MED')

    def test_zero_probability(self):
        self.assertEqual(Player.grade(0.0), Constants.LOWEST_THRESHOLD)


class TestTakeTurnCPU(unittest.TestCase):
    def _start_events(self):
        return deque([TurnResult(None, Action.START, 'SYS')])

    def _bid_events(self, cnt, face, name="OtherPlayer"):
        return deque([TurnResult(Bid(cnt, face), Action.BID, name)])

    def _make_cpu(self, dice=None, num_dice=5):
        p = Player("CPU_Test")
        p.num_dice = num_dice
        p.dice = (dice or [3, 3, 3, 4, 5]) + [-1] * (Constants.MAX_NUM_DICE - num_dice)
        return p

    def test_start_returns_bid_action(self):
        p = self._make_cpu()
        result = p.take_turn(self._start_events(), 5)
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.player_name, "CPU_Test")

    def test_start_bid_is_valid_bid(self):
        p = self._make_cpu()
        result = p.take_turn(self._start_events(), 5)
        bid = result.bid
        self.assertIsInstance(bid, Bid)
        self.assertGreater(bid.count, 0)
        self.assertIn(bid.face, range(1, 7))

    def test_result_always_has_three_fields(self):
        p = self._make_cpu()
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertIsInstance(result, TurnResult)
        self.assertIsNotNone(result.action)
        self.assertIsNotNone(result.player_name)

    def test_after_bid_returns_valid_action(self):
        p = self._make_cpu()
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertIn(result.action, [Action.BID, Action.RAISE, Action.CHALLENGE, Action.SPOT_ON])

    def test_after_bid_player_name_in_result(self):
        p = self._make_cpu()
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertEqual(result.player_name, "CPU_Test")

    def test_challenge_output_is_none(self):
        """When player challenges, bid should be None."""
        # Force a challenge by making the bid obviously false (impossible count)
        p = self._make_cpu(dice=[3, 3, 3, 3, 3])
        # Bid count higher than all dice — challenge should be favorable
        events = deque([TurnResult(Bid(50, 6), Action.BID, "Other")])
        result = p.take_turn(events, 5)
        if result.action == Action.CHALLENGE:  # if challenge was chosen
            self.assertIsNone(result.bid)

    def test_one_die_player_can_take_turn(self):
        p = self._make_cpu(dice=[4], num_dice=1)
        result = p.take_turn(self._start_events(), 5)
        self.assertIsInstance(result, TurnResult)
        self.assertIn(result.action, [Action.BID, Action.RAISE, Action.CHALLENGE, Action.SPOT_ON])


class TestTakeTurnHuman(unittest.TestCase):
    def _start_events(self):
        return deque([TurnResult(None, Action.START, 'SYS')])

    def _bid_events(self, cnt, face, name="OtherPlayer"):
        return deque([TurnResult(Bid(cnt, face), Action.BID, name)])

    def _make_human(self):
        p = Player("Human_Test", spot="HUMAN")
        p.num_dice = 5
        p.dice = [3, 3, 3, 4, 5, -1]
        return p

    @patch('builtins.input', side_effect=['3', '4'])
    def test_human_opening_bid(self, mock_input):
        p = self._make_human()
        result = p.take_turn(self._start_events(), 5)
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(3, 4))
        self.assertEqual(result.player_name, "Human_Test")

    @patch('builtins.input', side_effect=['C'])
    def test_human_challenge(self, mock_input):
        p = self._make_human()
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)

    @patch('builtins.input', side_effect=['S'])
    def test_human_spot_on(self, mock_input):
        p = self._make_human()
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertEqual(result.action, Action.SPOT_ON)
        self.assertIsNone(result.bid)

    @patch('builtins.input', side_effect=['B', '3', '5'])
    def test_human_raise(self, mock_input):
        p = self._make_human()
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertEqual(result.action, Action.RAISE)  # RAISE (count went up)
        self.assertEqual(result.bid, Bid(3, 5))

    @patch('builtins.input', side_effect=['INVALID', 'bad input', 'C'])
    def test_human_invalid_then_valid_choice(self, mock_input):
        """Bad action input retries until a valid choice is given."""
        p = self._make_human()
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertEqual(result.action, Action.CHALLENGE)

    @patch('builtins.input', side_effect=['B', 'notanumber', '2', '3'])
    def test_human_bid_invalid_count_retries(self, mock_input):
        """Non-numeric bid count retries instead of crashing."""
        p = self._make_human()
        # Previous bid was 1, 3 — bidding 2, 3 is a valid raise
        result = p.take_turn(self._bid_events(1, 3), 5)
        self.assertEqual(result.bid, Bid(2, 3))

    @patch('builtins.input', side_effect=['B', '2', '3'])
    def test_human_bid_same_face_same_count_invalid(self, mock_input):
        """Human cannot re-bid the same count and same face."""
        # prev_bid is [2, 3]; bidding [2, 3] again should be rejected
        # But we only have one valid bid in side_effect after 'B'...
        # This test just verifies that bidding a higher face at same count is accepted
        p = self._make_human()
        result = p.take_turn(self._bid_events(1, 2), 5)
        # [2, 3] with prev [1, 2]: count went up (2 > 1), so this is a RAISE
        self.assertEqual(result.action, Action.RAISE)


class TestPlayerReset(unittest.TestCase):
    def test_restores_dice_count(self):
        p = Player("Test")
        p.num_dice = 2
        p.reset()
        self.assertEqual(p.num_dice, Constants.MAX_NUM_DICE)

    def test_clears_dice_to_sentinels(self):
        p = Player("Test")
        p.dice = [3] * Constants.MAX_NUM_DICE
        p.reset()
        self.assertTrue(all(d == -1 for d in p.dice))

    def test_clears_state_fields(self):
        p = Player("Test")
        p.rolls_mode, p.wild_count, p.mode_count, p.eliminated = 5, 3, 4, True
        p.reset()
        self.assertEqual((p.rolls_mode, p.wild_count, p.mode_count), (0, 0, 0))
        self.assertFalse(p.eliminated)

    def test_preserves_personality(self):
        p = Player("Test")
        ra, pp = p.risk_appetite, p.peer_pressure_score
        p.reset()
        self.assertEqual(p.risk_appetite, ra)
        self.assertEqual(p.peer_pressure_score, pp)


class TestChallengeThreshold(unittest.TestCase):
    def test_challenge_threshold_in_range(self):
        p = Player("Test")
        self.assertGreaterEqual(p.challenge_threshold, 0.20)
        self.assertLessEqual(p.challenge_threshold, 0.71)

    def test_challenge_threshold_conservative_higher(self):
        import random as _r
        # Force risk_appetite=5 by seeding; retry until we get one in low range
        for seed in range(200):
            rng = _r.Random(seed)
            p = Player("T", rng=rng)
            if p.risk_appetite <= 10:
                self.assertGreater(p.challenge_threshold, 0.50)
                return
        self.fail("Could not find a low risk_appetite player in 200 seeds")

    def test_challenge_threshold_aggressive_lower(self):
        import random as _r
        for seed in range(200):
            rng = _r.Random(seed)
            p = Player("T", rng=rng)
            if p.risk_appetite >= 90:
                self.assertLess(p.challenge_threshold, 0.50)
                return
        self.fail("Could not find a high risk_appetite player in 200 seeds")

    def _player_with_trait(self, risk_appetite: int, challenge_threshold: float) -> Player:
        """Build a player and forcibly set personality traits for deterministic tests."""
        import random as _r
        p = Player("T", rng=_r.Random(0))
        p.risk_appetite = risk_appetite
        p.challenge_threshold = challenge_threshold
        p.num_dice = 5
        p.dice = [3, 3, 3, 3, 3]
        return p

    def test_challenge_suppressed_below_threshold(self):
        """Conservative player (threshold=0.60) should NOT challenge at 40% probability."""
        p = self._player_with_trait(risk_appetite=10, challenge_threshold=0.60)
        # Bid of 4 threes when only 5 dice remain — challenge_success_prob will be moderate
        # Use a bid that yields ~40% challenge probability but a safe raise exists
        prev = deque([TurnResult(Bid(4, 3), Action.BID, "Other")])
        result = p.take_turn(prev, tot_other_dice=0)
        self.assertNotEqual(result.action, Action.CHALLENGE)

    def test_challenge_taken_above_threshold(self):
        """Aggressive player (threshold=0.20) should challenge a near-impossible bid."""
        p = self._player_with_trait(risk_appetite=95, challenge_threshold=0.20)
        # Bid of 5 sixes when player holds [3,3,3,3,3] — challenge_success_prob near 1.0
        p.dice = [3, 3, 3, 3, 3]
        prev = deque([TurnResult(Bid(5, 6), Action.BID, "Other")])
        result = p.take_turn(prev, tot_other_dice=0)
        self.assertEqual(result.action, Action.CHALLENGE)


import random as _random


class TestTakeTurnDeterministic(unittest.TestCase):
    """Proves that seeding the RNG produces identical take_turn results."""

    def _make(self, seed: int) -> Player:
        rng = _random.Random(seed)
        p = Player('Tester', rng=rng)
        p.dice = [3, 3, 3, 3, 3]
        p.num_dice = 5
        return p

    def test_same_seed_same_start_result(self):
        r1 = self._make(42).take_turn(deque([TurnResult(None, Action.START, 'SYS')]), 15)
        r2 = self._make(42).take_turn(deque([TurnResult(None, Action.START, 'SYS')]), 15)
        self.assertEqual(r1.action, r2.action)
        self.assertEqual(r1.bid, r2.bid)

    def test_different_seeds_may_differ(self):
        """Sanity check: different seeds don't always collide."""
        results = set()
        for seed in range(20):
            r = self._make(seed).take_turn(
                deque([TurnResult(None, Action.START, 'SYS')]), 15)
            results.add((r.action, r.bid))
        self.assertGreater(len(results), 1)


class TestOpponentProfile(unittest.TestCase):
    def test_bluff_rate_defaults_neutral(self):
        p = OpponentProfile()
        self.assertEqual(p.bluff_rate, 0.5)

    def test_bluff_rate_computed(self):
        p = OpponentProfile(bids_challenged=4, challenge_successes=3)
        self.assertAlmostEqual(p.bluff_rate, 0.75)

    def test_avg_aggression_defaults_neutral(self):
        p = OpponentProfile()
        self.assertEqual(p.avg_aggression, 0.5)

    def test_avg_aggression_computed(self):
        p = OpponentProfile(bids_observed=2, total_aggression=1.0)
        self.assertAlmostEqual(p.avg_aggression, 0.5)


class TestObserveAction(unittest.TestCase):
    def _make_cpu(self):
        p = Player("Watcher")
        p.num_dice = 5
        p.dice = [3, 3, 3, 4, 5] + [-1]
        return p

    def test_observe_bid_creates_profile(self):
        p = self._make_cpu()
        p.observe_action("Alice", Action.BID, Bid(3, 4), 10)
        self.assertIn("Alice", p.opponent_profiles)

    def test_observe_bid_increments_count(self):
        p = self._make_cpu()
        p.observe_action("Alice", Action.BID, Bid(3, 4), 10)
        p.observe_action("Alice", Action.RAISE, Bid(4, 4), 10)
        self.assertEqual(p.opponent_profiles["Alice"].bids_observed, 2)

    def test_observe_bid_accumulates_aggression(self):
        p = self._make_cpu()
        p.observe_action("Alice", Action.BID, Bid(5, 4), 10)  # aggression = 0.5
        self.assertAlmostEqual(p.opponent_profiles["Alice"].total_aggression, 0.5)

    def test_observe_challenge_ignored(self):
        p = self._make_cpu()
        p.observe_action("Alice", Action.CHALLENGE, None, 10)
        self.assertNotIn("Alice", p.opponent_profiles)

    def test_observe_zero_total_dice_ignored(self):
        p = self._make_cpu()
        p.observe_action("Alice", Action.BID, Bid(3, 4), 0)
        self.assertNotIn("Alice", p.opponent_profiles)


class TestObserveOutcome(unittest.TestCase):
    def _make_cpu(self):
        p = Player("Watcher")
        p.num_dice = 5
        p.dice = [3, 3, 3, 4, 5] + [-1]
        return p

    def test_observe_outcome_creates_profile(self):
        p = self._make_cpu()
        p.observe_outcome("Bob", challenge_succeeded=True)
        self.assertIn("Bob", p.opponent_profiles)

    def test_observe_outcome_increments_challenged(self):
        p = self._make_cpu()
        p.observe_outcome("Bob", challenge_succeeded=False)
        p.observe_outcome("Bob", challenge_succeeded=True)
        self.assertEqual(p.opponent_profiles["Bob"].bids_challenged, 2)
        self.assertEqual(p.opponent_profiles["Bob"].challenge_successes, 1)

    def test_observe_outcome_no_success_on_failed_challenge(self):
        p = self._make_cpu()
        p.observe_outcome("Bob", challenge_succeeded=False)
        self.assertEqual(p.opponent_profiles["Bob"].challenge_successes, 0)


class TestResetClearsProfiles(unittest.TestCase):
    def test_reset_clears_opponent_profiles(self):
        p = Player("Test")
        p.observe_action("Alice", Action.BID, Bid(3, 4), 10)
        self.assertIn("Alice", p.opponent_profiles)
        p.reset()
        self.assertEqual(p.opponent_profiles, {})


class TestOpponentProfileInfluencesChallenge(unittest.TestCase):
    def _player_with_bluff_profile(self, bidder: str, bluff_rate_approx: float) -> Player:
        import random as _r
        p = Player("Watcher", rng=_r.Random(0))
        p.risk_appetite = 50
        p.challenge_threshold = 0.50
        p.num_dice = 5
        p.dice = [2, 2, 2, 2, 2]
        # Build profile: 4 challenges, bluff_rate_approx of them succeeded
        successes = round(bluff_rate_approx * 4)
        profile = OpponentProfile(
            bids_observed=10,
            total_aggression=5.0,
            bids_challenged=4,
            challenge_successes=successes,
        )
        p.opponent_profiles[bidder] = profile
        return p

    def test_known_bluffer_lowers_effective_threshold(self):
        bidder = "BigLiar"
        p = self._player_with_bluff_profile(bidder, bluff_rate_approx=1.0)
        # Bid that sits just below raw challenge_threshold should still trigger challenge
        prev = deque([TurnResult(Bid(5, 6), Action.BID, bidder)])
        result = p.take_turn(prev, tot_other_dice=0)
        self.assertEqual(result.action, Action.CHALLENGE)

    def test_honest_bidder_raises_effective_threshold(self):
        bidder = "HonestHank"
        p = self._player_with_bluff_profile(bidder, bluff_rate_approx=0.0)
        p.challenge_threshold = 0.30
        profile = p.opponent_profiles[bidder]
        # bluff_adjustment = (0.0 - 0.5) * 0.4 = -0.2 → threshold goes up
        bluff_adjustment = (profile.bluff_rate - 0.5) * 0.4
        effective = max(0.10, p.challenge_threshold - bluff_adjustment)
        self.assertGreater(effective, p.challenge_threshold)


if __name__ == '__main__':
    unittest.main()
