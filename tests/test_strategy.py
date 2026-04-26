import unittest
import random

import constants as Constants
from models import Action, Bid, TurnResult, OpponentProfile, ResponseContext
from strategy import CPUStrategy


def make_cpu_strategy(seed: int = 0) -> CPUStrategy:
    return CPUStrategy(random.Random(seed))


class TestComputeDiceStats(unittest.TestCase):
    def _make(self, dice: list[int]) -> tuple[CPUStrategy, list[int], int]:
        s = make_cpu_strategy()
        num_dice = len(dice)
        padded = dice + [-1] * (Constants.MAX_NUM_DICE - num_dice)
        return s, padded, num_dice

    def test_multi_die_sets_mode(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        s._compute_dice_stats(dice, num_dice)
        self.assertEqual(s._rolls_mode, 3)

    def test_multi_die_mode_count_includes_wilds(self):
        s, dice, num_dice = self._make([3, 3, 1, 4, 5])
        s._compute_dice_stats(dice, num_dice)
        self.assertEqual(s._rolls_mode, 3)
        self.assertEqual(s._mode_count, 3)  # two 3s + one wild

    def test_single_die_uses_face_value(self):
        s, dice, num_dice = self._make([5])
        s._compute_dice_stats(dice, num_dice)
        self.assertEqual(s._rolls_mode, 5)
        self.assertEqual(s._mode_count, 1)

    def test_all_wilds_mode_is_one(self):
        s, dice, num_dice = self._make([1, 1, 1])
        s._compute_dice_stats(dice, num_dice)
        self.assertEqual(s._rolls_mode, 1)


class TestMakeOpeningBid(unittest.TestCase):
    def _make(self, dice: list[int]) -> tuple[CPUStrategy, list[int], int]:
        s = make_cpu_strategy()
        num_dice = len(dice)
        padded = dice + [-1] * (Constants.MAX_NUM_DICE - num_dice)
        s._compute_dice_stats(padded, num_dice)
        return s, padded, num_dice

    def test_returns_bid_action(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        result = s._make_opening_bid("T", dice, num_dice)
        self.assertEqual(result.action, Action.BID)

    def test_bid_face_in_valid_range(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        result = s._make_opening_bid("T", dice, num_dice)
        self.assertIn(result.bid.face, range(1, 7))

    def test_bid_count_at_least_minimum(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        result = s._make_opening_bid("T", dice, num_dice)
        self.assertGreaterEqual(result.bid.count, Constants.MINIMUM_BID)

    def test_uses_mode_when_mode_count_sufficient(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        s.risk_appetite = 1  # zero extra dice
        result = s._make_opening_bid("T", dice, num_dice)
        self.assertEqual(result.bid.face, 3)

    def test_player_name_in_result(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        result = s._make_opening_bid("T", dice, num_dice)
        self.assertEqual(result.player_name, "T")


class TestComputeChallengeProb(unittest.TestCase):
    def _make(self) -> CPUStrategy:
        s = make_cpu_strategy()
        s.peer_pressure_score = 50
        s.attentiveness_score = 50
        return s

    def test_needed_zero_returns_zero(self):
        s = self._make()
        self.assertEqual(s._compute_challenge_probability("X", 5, 0, 0), 0.0)

    def test_returns_float_in_unit_interval(self):
        s = self._make()
        prob = s._compute_challenge_probability("X", 5, 2, 3)
        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_high_needed_gives_high_prob(self):
        s = self._make()
        prob = s._compute_challenge_probability("X", 5, 0, 10)
        self.assertGreater(prob, 0.9)

    def test_low_needed_gives_low_prob(self):
        s = self._make()
        prob = s._compute_challenge_probability("X", 10, 0, 1)
        self.assertLess(prob, 0.5)

    def test_aggressive_profile_raises_prob(self):
        s = self._make()
        s.attentiveness_score = Constants.MAX_ATTENTIVENESS_SCORE
        s.opponent_profiles["Bully"] = OpponentProfile(
            bids_observed=5, total_aggression=4.0)  # avg_aggression=0.8
        base = s._compute_challenge_probability("X", 5, 0, 3)
        boosted = s._compute_challenge_probability("Bully", 5, 0, 3)
        self.assertGreater(boosted, base)


class TestEffectiveChallengeThreshold(unittest.TestCase):
    def _make(self, threshold: float = 0.50) -> CPUStrategy:
        s = make_cpu_strategy()
        s.challenge_threshold = threshold
        s.attentiveness_score = Constants.MAX_ATTENTIVENESS_SCORE
        return s

    def test_unknown_bidder_returns_base_threshold(self):
        s = self._make(0.50)
        self.assertAlmostEqual(s._effective_challenge_threshold("Unknown"), 0.50)

    def test_known_bluffer_lowers_threshold(self):
        s = self._make(0.50)
        s.opponent_profiles["Liar"] = OpponentProfile(
            bids_challenged=4, challenge_successes=4)  # bluff_rate=1.0
        effective = s._effective_challenge_threshold("Liar")
        self.assertLess(effective, 0.50)

    def test_honest_bidder_raises_threshold(self):
        s = self._make(0.50)
        s.opponent_profiles["Honest"] = OpponentProfile(
            bids_challenged=4, challenge_successes=0)  # bluff_rate=0.0
        effective = s._effective_challenge_threshold("Honest")
        self.assertGreater(effective, 0.50)

    def test_threshold_clamped_at_minimum(self):
        s = self._make(0.11)
        s.opponent_profiles["Bluffer"] = OpponentProfile(
            bids_challenged=4, challenge_successes=4)
        effective = s._effective_challenge_threshold("Bluffer")
        self.assertGreaterEqual(effective, 0.10)

    def test_fewer_than_min_samples_returns_base(self):
        s = self._make(0.50)
        s.opponent_profiles["New"] = OpponentProfile(
            bids_challenged=1, challenge_successes=1)  # only 1 sample
        self.assertAlmostEqual(s._effective_challenge_threshold("New"), 0.50)


class TestGetPermissibleBids(unittest.TestCase):
    def test_no_prior_bids_returns_six_same_count(self):
        s = make_cpu_strategy()
        bids = s._get_permissible_bids(2, 10, set())
        same_count = [b for b in bids if b.count == 2]
        self.assertEqual(len(same_count), 6)

    def test_raises_excluded_when_count_exceeds_dice(self):
        s = make_cpu_strategy()
        bids = s._get_permissible_bids(2, 2, set())
        raising = [b for b in bids if b.count == 3]
        self.assertEqual(len(raising), 0)

    def test_raises_included_when_count_within_limit(self):
        s = make_cpu_strategy()
        bids = s._get_permissible_bids(2, 10, set())
        raising = [b for b in bids if b.count == 3]
        self.assertEqual(len(raising), 6)

    def test_already_made_same_count_bid_excluded(self):
        s = make_cpu_strategy()
        prev = {Bid(2, 3), Bid(2, 5)}
        bids = s._get_permissible_bids(2, 10, prev)
        self.assertNotIn(Bid(2, 3), bids)
        self.assertNotIn(Bid(2, 5), bids)

    def test_all_same_count_bids_made_leaves_only_raises(self):
        s = make_cpu_strategy()
        prev = {Bid(2, f) for f in range(1, 7)}
        bids = s._get_permissible_bids(2, 10, prev)
        self.assertTrue(all(b.count == 3 for b in bids))


class TestRankAndSelectBid(unittest.TestCase):
    def _make(self) -> tuple[CPUStrategy, list[int], int]:
        s = make_cpu_strategy()
        s.peer_pressure_score = 1  # suppress crowd-following
        dice = [3, 3, 3, -1, -1, -1]
        return s, dice, 3

    def test_empty_permissible_returns_none_zero(self):
        from scipy.stats import binom as _binom
        s, dice, num_dice = self._make()
        model = _binom(n=5, p=2/6)
        result = s._rank_and_select_bid(dice, num_dice, [], model, set())
        self.assertEqual(result, (None, 0.0))

    def test_single_bid_returned(self):
        from scipy.stats import binom as _binom
        s, dice, num_dice = self._make()
        model = _binom(n=5, p=2/6)
        bid, prob = s._rank_and_select_bid(dice, num_dice, [Bid(2, 3)], model, set())
        self.assertEqual(bid, Bid(2, 3))
        self.assertGreater(prob, 0.0)

    def test_guaranteed_bid_gets_probability_one(self):
        from scipy.stats import binom as _binom
        s, dice, num_dice = self._make()
        model = _binom(n=5, p=2/6)
        # Player has three 3s; Bid(2,3) needs ≤0 more → prob=1.0
        _, prob = s._rank_and_select_bid(dice, num_dice, [Bid(2, 3)], model, set())
        self.assertAlmostEqual(prob, 1.0)

    def test_higher_probability_bid_wins(self):
        from scipy.stats import binom as _binom
        s, dice, num_dice = self._make()
        model = _binom(n=5, p=2/6)
        bid, _ = s._rank_and_select_bid(dice, num_dice, [Bid(5, 6), Bid(2, 3)], model, set())
        self.assertEqual(bid, Bid(2, 3))


class TestDecideAction(unittest.TestCase):
    def _make(self) -> CPUStrategy:
        s = make_cpu_strategy()
        s.spot_on_threshold = 0.05
        s.risk_appetite = 1  # low — won't gamble on spot-on
        s.challenge_threshold = 0.50
        return s

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
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.90, effective_threshold=0.50,
            spot_on_prob=0.05, best_bid=Bid(3, 4), best_bid_prob=0.40))
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)

    def test_spot_on_when_spot_on_is_best(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.30, effective_threshold=0.50,
            spot_on_prob=0.80, best_bid=Bid(3, 4), best_bid_prob=0.40))
        self.assertEqual(result.action, Action.SPOT_ON)
        self.assertIsNone(result.bid)

    def test_bid_action_when_count_equals_prev(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.10, effective_threshold=0.50,
            spot_on_prob=0.01, best_bid=Bid(2, 5), best_bid_prob=0.80,
            prev_bid=Bid(2, 3)))
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(2, 5))

    def test_raise_action_when_count_exceeds_prev(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.10, effective_threshold=0.50,
            spot_on_prob=0.01, best_bid=Bid(3, 5), best_bid_prob=0.80,
            prev_bid=Bid(2, 3)))
        self.assertEqual(result.action, Action.RAISE)
        self.assertEqual(result.bid, Bid(3, 5))

    def test_challenge_below_threshold_not_taken(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.40, effective_threshold=0.50,
            spot_on_prob=0.01, best_bid=Bid(2, 4), best_bid_prob=0.70))
        self.assertNotEqual(result.action, Action.CHALLENGE)

    def test_fallback_to_challenge_when_all_zero_no_bid(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.0, effective_threshold=0.50,
            spot_on_prob=0.0, best_bid=None, best_bid_prob=0.0))
        self.assertEqual(result.action, Action.CHALLENGE)

    def test_fallback_to_bid_when_all_zero_but_have_bid(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.0, effective_threshold=0.50,
            spot_on_prob=0.0, best_bid=Bid(3, 2), best_bid_prob=0.0,
            prev_bid=Bid(2, 3)))
        self.assertIn(result.action, (Action.BID, Action.RAISE))
        self.assertEqual(result.bid, Bid(3, 2))

    def test_player_name_always_in_result(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.90, effective_threshold=0.50,
            spot_on_prob=0.05, best_bid=Bid(3, 4), best_bid_prob=0.40))
        self.assertEqual(result.player_name, "T")


class TestBlindAggressionBoost(unittest.TestCase):
    """High blind_aggression_score boosts challenge prob for cunning CPUs, not for zero-cunning ones."""

    def _ctx_with_aggression(self, score: float, challenge_prob: float = 0.55,
                             effective_threshold: float = 0.50) -> ResponseContext:
        return ResponseContext(
            prev_bid=Bid(3, 4),
            challenge_prob=challenge_prob,
            effective_threshold=effective_threshold,
            spot_on_prob=0.01,
            best_bid=Bid(4, 4),
            best_bid_prob=0.40,
            blind_aggression_score=score,
            pressure_opportunity_score=0.0,
        )

    def test_high_cunning_boosts_challenge_above_threshold(self):
        s = make_cpu_strategy()
        s.positional_cunning = Constants.MAX_POSITIONAL_CUNNING_SCORE
        s.challenge_threshold = 0.70  # raw prob (0.55) is below this threshold
        # score=3.0 → boost = min(0.15, (3.0-1.4)*0.1*1.0) = 0.15
        # effective_challenge_prob = 0.70, effective_threshold = 0.625 → challenge fires
        ctx = self._ctx_with_aggression(score=3.0, challenge_prob=0.55, effective_threshold=0.70)
        result = s._decide_action("T", ctx)
        self.assertEqual(result.action, Action.CHALLENGE)

    def test_zero_cunning_no_boost_challenge_suppressed(self):
        s = make_cpu_strategy()
        s.positional_cunning = 1  # near-zero cunning: boost ≈ 0.0016, insufficient
        s.challenge_threshold = 0.70
        ctx = self._ctx_with_aggression(score=3.0, challenge_prob=0.55, effective_threshold=0.70)
        result = s._decide_action("T", ctx)
        self.assertNotEqual(result.action, Action.CHALLENGE)


class TestPressureOpportunityBidSelection(unittest.TestCase):
    """High pressure_opportunity_score shifts bid selection toward higher counts when cunning is high."""

    def _make_with_cunning(self, cunning: int) -> CPUStrategy:
        s = make_cpu_strategy()
        s.peer_pressure_score = 1  # suppress crowd-following
        s.positional_cunning = cunning
        return s

    def test_high_cunning_picks_higher_count_bid(self):
        from scipy.stats import binom as _binom
        s = self._make_with_cunning(Constants.MAX_POSITIONAL_CUNNING_SCORE)
        dice = [3, 3, 3, -1, -1, -1]
        num_dice = 3
        model = _binom(n=5, p=2 / 6)
        # Both Bid(2,3) and Bid(3,3) have prob=1.0 since player holds 3 threes.
        # pressure_hint > threshold should break the tie in favour of Bid(3,3).
        pressure_hint = 1.0  # well above _PRESSURE_OPP_THRESHOLD
        bid, _ = s._rank_and_select_bid(dice, num_dice, [Bid(2, 3), Bid(3, 3)], model, set(),
                                        pressure_hint=pressure_hint)
        self.assertEqual(bid, Bid(3, 3))

    def test_zero_cunning_picks_lower_count_bid(self):
        from scipy.stats import binom as _binom
        s = self._make_with_cunning(1)
        dice = [3, 3, 3, -1, -1, -1]
        num_dice = 3
        model = _binom(n=5, p=2 / 6)
        # pressure_hint = 0 (zero cunning × score) → normal path → first bid wins
        bid, _ = s._rank_and_select_bid(dice, num_dice, [Bid(2, 3), Bid(3, 3)], model, set(),
                                        pressure_hint=0.0)
        self.assertEqual(bid, Bid(2, 3))


if __name__ == '__main__':
    unittest.main()
