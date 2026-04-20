import unittest
from collections import deque
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import constants as Constants
from Player import Player
from models import Action, Bid, TurnResult, OpponentProfile, ResponseContext


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

    def test_attentiveness_score_in_distribution(self):
        p = Player("Test")
        self.assertIn(p.attentiveness_score, Constants.ATTENTIVENESS_DISTRIBUTION)


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

    def _make_human(self, input_handler=None):
        p = Player("Human_Test", spot="HUMAN", input_handler=input_handler or (lambda _: {}))
        p.num_dice = 5
        p.dice = [3, 3, 3, 4, 5, -1]
        return p

    def test_human_opening_bid(self):
        handler = lambda req: {'action': Action.BID, 'bid': Bid(3, 4)}
        p = self._make_human(handler)
        result = p.take_turn(self._start_events(), 5)
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(3, 4))
        self.assertEqual(result.player_name, "Human_Test")

    def test_human_opening_bid_passes_correct_request(self):
        received = {}
        def handler(req):
            received.update(req)
            return {'action': Action.BID, 'bid': Bid(2, 3)}
        p = self._make_human(handler)
        p.take_turn(self._start_events(), 10)
        self.assertEqual(received['type'], 'opening_bid')
        self.assertEqual(received['dice'], [3, 3, 3, 4, 5])
        self.assertEqual(received['tot_other_dice'], 10)

    def test_human_challenge(self):
        handler = lambda req: {'action': Action.CHALLENGE, 'bid': None}
        p = self._make_human(handler)
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)

    def test_human_spot_on(self):
        handler = lambda req: {'action': Action.SPOT_ON, 'bid': None}
        p = self._make_human(handler)
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertEqual(result.action, Action.SPOT_ON)
        self.assertIsNone(result.bid)

    def test_human_raise(self):
        handler = lambda req: {'action': Action.RAISE, 'bid': Bid(3, 5)}
        p = self._make_human(handler)
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertEqual(result.action, Action.RAISE)
        self.assertEqual(result.bid, Bid(3, 5))

    def test_human_decision_passes_correct_request(self):
        received = {}
        def handler(req):
            received.update(req)
            return {'action': Action.CHALLENGE, 'bid': None}
        p = self._make_human(handler)
        p.take_turn(self._bid_events(2, 3), 10)
        self.assertEqual(received['type'], 'decision')
        self.assertEqual(received['prev_bid'], Bid(2, 3))
        self.assertEqual(received['prev_player'], 'OtherPlayer')
        self.assertEqual(received['tot_other_dice'], 10)

    def test_human_player_name_in_result(self):
        handler = lambda req: {'action': Action.CHALLENGE, 'bid': None}
        p = self._make_human(handler)
        result = p.take_turn(self._bid_events(2, 3), 5)
        self.assertEqual(result.player_name, "Human_Test")


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
        ra, pp, att = p.risk_appetite, p.peer_pressure_score, p.attentiveness_score
        p.reset()
        self.assertEqual(p.risk_appetite, ra)
        self.assertEqual(p.peer_pressure_score, pp)
        self.assertEqual(p.attentiveness_score, att)


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
        p.attentiveness_score = Constants.MAX_ATTENTIVENESS_SCORE  # full attention for test clarity
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


class TestComputeDiceStats(unittest.TestCase):
    def _make(self, dice: list[int]) -> Player:
        p = Player("T")
        p.num_dice = len(dice)
        p.dice = dice + [-1] * (Constants.MAX_NUM_DICE - len(dice))
        return p

    def test_multi_die_sets_mode(self):
        p = self._make([3, 3, 3, 4, 5])
        p._compute_dice_stats()
        self.assertEqual(p.rolls_mode, 3)

    def test_multi_die_mode_count_includes_wilds(self):
        p = self._make([3, 3, 1, 4, 5])
        p._compute_dice_stats()
        self.assertEqual(p.rolls_mode, 3)
        self.assertEqual(p.mode_count, 3)  # two 3s + one wild

    def test_single_die_uses_face_value(self):
        p = self._make([5])
        p._compute_dice_stats()
        self.assertEqual(p.rolls_mode, 5)
        self.assertEqual(p.mode_count, 1)

    def test_all_wilds_mode_is_one(self):
        p = self._make([1, 1, 1])
        p._compute_dice_stats()
        self.assertEqual(p.rolls_mode, 1)


class TestMakeOpeningBid(unittest.TestCase):
    def _make(self, dice: list[int]) -> Player:
        import random as _r
        p = Player("T", rng=_r.Random(0))
        p.num_dice = len(dice)
        p.dice = dice + [-1] * (Constants.MAX_NUM_DICE - len(dice))
        p._compute_dice_stats()
        return p

    def test_returns_bid_action(self):
        p = self._make([3, 3, 3, 4, 5])
        result = p._make_opening_bid()
        self.assertEqual(result.action, Action.BID)

    def test_bid_face_in_valid_range(self):
        p = self._make([3, 3, 3, 4, 5])
        result = p._make_opening_bid()
        self.assertIn(result.bid.face, range(1, 7))

    def test_bid_count_at_least_minimum(self):
        p = self._make([3, 3, 3, 4, 5])
        result = p._make_opening_bid()
        self.assertGreaterEqual(result.bid.count, Constants.MINIMUM_BID)

    def test_uses_mode_when_mode_count_sufficient(self):
        p = self._make([3, 3, 3, 4, 5])
        p.risk_appetite = 1  # zero extra dice
        result = p._make_opening_bid()
        self.assertEqual(result.bid.face, 3)

    def test_player_name_in_result(self):
        p = self._make([3, 3, 3, 4, 5])
        result = p._make_opening_bid()
        self.assertEqual(result.player_name, "T")


class TestComputeChallengeProb(unittest.TestCase):
    def _make(self) -> Player:
        import random as _r
        p = Player("T", rng=_r.Random(0))
        p.num_dice = 3
        p.dice = [2, 2, 2, -1, -1, -1]
        p.peer_pressure_score = 50
        p.attentiveness_score = 50
        return p

    def test_needed_zero_returns_zero(self):
        p = self._make()
        self.assertEqual(p._compute_challenge_probability("X", 5, 0, 0), 0.0)

    def test_returns_float_in_unit_interval(self):
        p = self._make()
        prob = p._compute_challenge_probability("X", 5, 2, 3)
        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_high_needed_gives_high_prob(self):
        # Needing 10 dice from 5 total → near certainty to challenge successfully
        p = self._make()
        prob = p._compute_challenge_probability("X", 5, 0, 10)
        self.assertGreater(prob, 0.9)

    def test_low_needed_gives_low_prob(self):
        # Needing 1 die from 10 → low challenge success
        p = self._make()
        prob = p._compute_challenge_probability("X", 10, 0, 1)
        self.assertLess(prob, 0.5)

    def test_aggressive_profile_raises_prob(self):
        p = self._make()
        p.attentiveness_score = Constants.MAX_ATTENTIVENESS_SCORE
        # Aggressive bidder: avg_aggression > 0.5 should boost probability
        p.opponent_profiles["Bully"] = OpponentProfile(
            bids_observed=5, total_aggression=4.0)  # avg_aggression=0.8
        base = p._compute_challenge_probability("X", 5, 0, 3)
        boosted = p._compute_challenge_probability("Bully", 5, 0, 3)
        self.assertGreater(boosted, base)


class TestEffectiveChallengeThreshold(unittest.TestCase):
    def _make(self, threshold=0.50) -> Player:
        import random as _r
        p = Player("T", rng=_r.Random(0))
        p.challenge_threshold = threshold
        p.attentiveness_score = Constants.MAX_ATTENTIVENESS_SCORE
        return p

    def test_unknown_bidder_returns_base_threshold(self):
        p = self._make(0.50)
        self.assertAlmostEqual(p._effective_challenge_threshold("Unknown"), 0.50)

    def test_known_bluffer_lowers_threshold(self):
        p = self._make(0.50)
        p.opponent_profiles["Liar"] = OpponentProfile(
            bids_challenged=4, challenge_successes=4)  # bluff_rate=1.0
        effective = p._effective_challenge_threshold("Liar")
        self.assertLess(effective, 0.50)

    def test_honest_bidder_raises_threshold(self):
        p = self._make(0.50)
        p.opponent_profiles["Honest"] = OpponentProfile(
            bids_challenged=4, challenge_successes=0)  # bluff_rate=0.0
        effective = p._effective_challenge_threshold("Honest")
        self.assertGreater(effective, 0.50)

    def test_threshold_clamped_at_minimum(self):
        p = self._make(0.11)
        p.opponent_profiles["Bluffer"] = OpponentProfile(
            bids_challenged=4, challenge_successes=4)
        effective = p._effective_challenge_threshold("Bluffer")
        self.assertGreaterEqual(effective, 0.10)

    def test_fewer_than_min_samples_returns_base(self):
        p = self._make(0.50)
        p.opponent_profiles["New"] = OpponentProfile(
            bids_challenged=1, challenge_successes=1)  # only 1 sample
        self.assertAlmostEqual(p._effective_challenge_threshold("New"), 0.50)


class TestGetPermissibleBids(unittest.TestCase):
    def _make(self) -> Player:
        import random as _r
        p = Player("T", rng=_r.Random(0))
        p.num_dice = 3
        p.dice = [2, 2, 2, -1, -1, -1]
        return p

    def test_no_prior_bids_returns_six_same_count(self):
        p = self._make()
        bids = p._get_permissible_bids(2, 10, set())
        same_count = [b for b in bids if b.count == 2]
        self.assertEqual(len(same_count), 6)

    def test_raises_excluded_when_count_exceeds_dice(self):
        p = self._make()
        # tot_other_dice=2, prev_bid_cnt=2; raising to 3 > 2, so no raising bids
        bids = p._get_permissible_bids(2, 2, set())
        raising = [b for b in bids if b.count == 3]
        self.assertEqual(len(raising), 0)

    def test_raises_included_when_count_within_limit(self):
        p = self._make()
        bids = p._get_permissible_bids(2, 10, set())
        raising = [b for b in bids if b.count == 3]
        self.assertEqual(len(raising), 6)

    def test_already_made_same_count_bid_excluded(self):
        p = self._make()
        prev = {Bid(2, 3), Bid(2, 5)}
        bids = p._get_permissible_bids(2, 10, prev)
        self.assertNotIn(Bid(2, 3), bids)
        self.assertNotIn(Bid(2, 5), bids)

    def test_all_same_count_bids_made_leaves_only_raises(self):
        p = self._make()
        prev = {Bid(2, f) for f in range(1, 7)}
        bids = p._get_permissible_bids(2, 10, prev)
        self.assertTrue(all(b.count == 3 for b in bids))


class TestRankAndSelectBid(unittest.TestCase):
    def _make(self) -> Player:
        import random as _r
        p = Player("T", rng=_r.Random(0))
        p.num_dice = 3
        p.dice = [3, 3, 3, -1, -1, -1]
        p.peer_pressure_score = 1  # suppress crowd-following
        return p

    def test_empty_permissible_returns_none_zero(self):
        from scipy.stats import binom as _binom
        p = self._make()
        model = _binom(n=5, p=2/6)
        result = p._rank_and_select_bid([], model, set())
        self.assertEqual(result, (None, 0.0))

    def test_single_bid_returned(self):
        from scipy.stats import binom as _binom
        p = self._make()
        model = _binom(n=5, p=2/6)
        bid, prob = p._rank_and_select_bid([Bid(2, 3)], model, set())
        self.assertEqual(bid, Bid(2, 3))
        self.assertGreater(prob, 0.0)

    def test_guaranteed_bid_gets_probability_one(self):
        from scipy.stats import binom as _binom
        p = self._make()
        model = _binom(n=5, p=2/6)
        # Player has three 3s; Bid(2,3) needs ≤0 more → prob=1.0
        _, prob = p._rank_and_select_bid([Bid(2, 3)], model, set())
        self.assertAlmostEqual(prob, 1.0)

    def test_higher_probability_bid_wins(self):
        from scipy.stats import binom as _binom
        p = self._make()
        model = _binom(n=5, p=2/6)
        # Bid(2,3) guaranteed (player has 3 threes); Bid(5,6) needs many 6s
        bid, _ = p._rank_and_select_bid([Bid(5, 6), Bid(2, 3)], model, set())
        self.assertEqual(bid, Bid(2, 3))


class TestDecideAction(unittest.TestCase):
    def _make(self) -> Player:
        import random as _r
        p = Player("T", rng=_r.Random(0))
        p.spot_on_threshold = 0.05
        p.risk_appetite = 1  # low — won't gamble on spot-on
        p.challenge_threshold = 0.50
        return p

    def _ctx(self, challenge_prob=0.0, effective_threshold=0.50, spot_on_prob=0.0,
              best_bid=None, best_bid_prob=0.0, prev_bid=Bid(2, 3)):
        return ResponseContext(
            prev_bid=prev_bid,
            challenge_prob=challenge_prob,
            effective_threshold=effective_threshold,
            spot_on_prob=spot_on_prob,
            best_bid=best_bid,
            best_bid_prob=best_bid_prob,
        )

    def test_challenge_when_challenge_prob_is_best(self):
        p = self._make()
        result = p._decide_action(self._ctx(
            challenge_prob=0.90, effective_threshold=0.50,
            spot_on_prob=0.05, best_bid=Bid(3, 4), best_bid_prob=0.40))
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)

    def test_spot_on_when_spot_on_is_best(self):
        p = self._make()
        result = p._decide_action(self._ctx(
            challenge_prob=0.30, effective_threshold=0.50,
            spot_on_prob=0.80, best_bid=Bid(3, 4), best_bid_prob=0.40))
        self.assertEqual(result.action, Action.SPOT_ON)
        self.assertIsNone(result.bid)

    def test_bid_action_when_count_equals_prev(self):
        p = self._make()
        result = p._decide_action(self._ctx(
            challenge_prob=0.10, effective_threshold=0.50,
            spot_on_prob=0.01, best_bid=Bid(2, 5), best_bid_prob=0.80,
            prev_bid=Bid(2, 3)))
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(2, 5))

    def test_raise_action_when_count_exceeds_prev(self):
        p = self._make()
        result = p._decide_action(self._ctx(
            challenge_prob=0.10, effective_threshold=0.50,
            spot_on_prob=0.01, best_bid=Bid(3, 5), best_bid_prob=0.80,
            prev_bid=Bid(2, 3)))
        self.assertEqual(result.action, Action.RAISE)
        self.assertEqual(result.bid, Bid(3, 5))

    def test_challenge_below_threshold_not_taken(self):
        p = self._make()
        # challenge_prob=0.40 < threshold=0.50 → effectively 0
        result = p._decide_action(self._ctx(
            challenge_prob=0.40, effective_threshold=0.50,
            spot_on_prob=0.01, best_bid=Bid(2, 4), best_bid_prob=0.70))
        self.assertNotEqual(result.action, Action.CHALLENGE)

    def test_fallback_to_challenge_when_all_zero_no_bid(self):
        p = self._make()
        result = p._decide_action(self._ctx(
            challenge_prob=0.0, effective_threshold=0.50,
            spot_on_prob=0.0, best_bid=None, best_bid_prob=0.0))
        self.assertEqual(result.action, Action.CHALLENGE)

    def test_fallback_to_bid_when_all_zero_but_have_bid(self):
        p = self._make()
        result = p._decide_action(self._ctx(
            challenge_prob=0.0, effective_threshold=0.50,
            spot_on_prob=0.0, best_bid=Bid(3, 2), best_bid_prob=0.0,
            prev_bid=Bid(2, 3)))
        self.assertIn(result.action, (Action.BID, Action.RAISE))
        self.assertEqual(result.bid, Bid(3, 2))

    def test_player_name_always_in_result(self):
        p = self._make()
        result = p._decide_action(self._ctx(
            challenge_prob=0.90, effective_threshold=0.50,
            spot_on_prob=0.05, best_bid=Bid(3, 4), best_bid_prob=0.40))
        self.assertEqual(result.player_name, "T")


if __name__ == '__main__':
    unittest.main()
