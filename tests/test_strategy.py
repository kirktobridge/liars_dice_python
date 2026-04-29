import unittest
import random

import constants as Constants
from models import Action, Bid, TurnResult, OpponentProfile, ResponseContext
from strategy import CPUStrategy, Personality


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
        s.risk_appetite = 1  # avoid wild-tactic randomness
        result = s._make_opening_bid("T", dice, num_dice, tot_other_dice=15)
        self.assertEqual(result.action, Action.BID)

    def test_bid_face_in_valid_range(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        s.risk_appetite = 1
        result = s._make_opening_bid("T", dice, num_dice, tot_other_dice=15)
        self.assertIn(result.bid.face, range(1, 7))

    def test_bid_count_at_least_minimum(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        s.risk_appetite = 1
        result = s._make_opening_bid("T", dice, num_dice, tot_other_dice=0)
        self.assertGreaterEqual(result.bid.count, Constants.MINIMUM_BID)

    def test_uses_mode_when_mode_count_sufficient(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        s.risk_appetite = 1  # disables wild tactic; uses mode path
        result = s._make_opening_bid("T", dice, num_dice, tot_other_dice=15)
        self.assertEqual(result.bid.face, 3)

    def test_opening_bid_scales_with_other_dice(self):
        """Opener with mode_count=3 in a 30-other-dice game expects ~3 + 30/3 = 13 dice."""
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        s.risk_appetite = 1
        result = s._make_opening_bid("T", dice, num_dice, tot_other_dice=30)
        self.assertGreaterEqual(result.bid.count, 8)

    def test_low_risk_opens_below_expected(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        s.risk_appetite = 1  # safety ≈ 1.0 → underbid by ~1
        result = s._make_opening_bid("T", dice, num_dice, tot_other_dice=15)
        # mode_count=3, expected_others=5, safety≈1.0 → target≈7
        self.assertLessEqual(result.bid.count, 8)

    def test_high_risk_opens_at_expected(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        s.risk_appetite = 100  # safety ≈ 0
        # Run many trials to dodge the wild-tactic path (no 1s held → never taken).
        result = s._make_opening_bid("T", dice, num_dice, tot_other_dice=15)
        self.assertGreaterEqual(result.bid.count, 7)

    def test_player_name_in_result(self):
        s, dice, num_dice = self._make([3, 3, 3, 4, 5])
        s.risk_appetite = 1
        result = s._make_opening_bid("T", dice, num_dice, tot_other_dice=15)
        self.assertEqual(result.player_name, "T")


class TestComputeChallengeProb(unittest.TestCase):
    def _make(self) -> CPUStrategy:
        s = make_cpu_strategy()
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
        # Start at 0.65 so the bluff adjustment can still move; floor is 0.50.
        s = self._make(0.65)
        s.opponent_profiles["Liar"] = OpponentProfile(
            bids_challenged=4, challenge_successes=4)  # bluff_rate=1.0
        effective = s._effective_challenge_threshold("Liar")
        self.assertLess(effective, 0.65)
        self.assertGreaterEqual(effective, 0.50)

    def test_honest_bidder_raises_threshold(self):
        s = self._make(0.55)
        s.opponent_profiles["Honest"] = OpponentProfile(
            bids_challenged=4, challenge_successes=0)  # bluff_rate=0.0
        effective = s._effective_challenge_threshold("Honest")
        self.assertGreater(effective, 0.55)

    def test_threshold_clamped_at_break_even(self):
        s = self._make(0.51)
        s.opponent_profiles["Bluffer"] = OpponentProfile(
            bids_challenged=4, challenge_successes=4)
        effective = s._effective_challenge_threshold("Bluffer")
        # Floor at 0.50 — challenging below 50% is mathematically -EV.
        self.assertGreaterEqual(effective, 0.50)

    def test_single_sample_uses_smoothed_rate(self):
        """With Beta(2,2) smoothing, a single observation moves the rate gradually
        rather than jumping to 0 or 1."""
        s = self._make(0.55)
        s.opponent_profiles["First"] = OpponentProfile(
            bids_challenged=1, challenge_successes=1)
        # Smoothed bluff_rate = (1+1)/(1+2) = 0.667 (not 1.0).
        # bluff_adjustment = (0.667 - 0.5) * 0.4 * 1.0 = 0.0667
        # effective = max(0.50, 0.55 - 0.0667) = 0.4833 → floored at 0.50
        effective = s._effective_challenge_threshold("First")
        self.assertGreaterEqual(effective, 0.50)
        self.assertLess(effective, 0.55)


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
        s.spot_on_ev_bias = 0.0
        s.risk_appetite = 1
        s.challenge_threshold = 0.50
        return s

    def _ctx(self, challenge_prob=0.0, effective_threshold=0.50, spot_on_prob=0.0,
             spot_on_ev=-1.0, best_bid=None, best_bid_prob=0.0, prev_bid=Bid(2, 3)):
        return ResponseContext(
            prev_bid=prev_bid,
            challenge_prob=challenge_prob,
            effective_threshold=effective_threshold,
            spot_on_prob=spot_on_prob,
            spot_on_ev=spot_on_ev,
            best_bid=best_bid,
            best_bid_prob=best_bid_prob,
        )

    def test_challenge_when_ev_is_positive_and_dominates(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.90, effective_threshold=0.50,
            spot_on_prob=0.05, spot_on_ev=-0.5,
            best_bid=Bid(3, 4), best_bid_prob=0.40))
        self.assertEqual(result.action, Action.CHALLENGE)
        self.assertIsNone(result.bid)

    def test_spot_on_when_spot_on_ev_is_positive_and_dominates(self):
        s = self._make()
        # 4-player table, P(exact)=0.30 → EV = 0.30*3 - 0.70 = +0.20
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.30, effective_threshold=0.50,
            spot_on_prob=0.30, spot_on_ev=0.20,
            best_bid=Bid(3, 4), best_bid_prob=0.40))
        self.assertEqual(result.action, Action.SPOT_ON)
        self.assertIsNone(result.bid)

    def test_bid_action_when_count_equals_prev(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.10, effective_threshold=0.50,
            spot_on_prob=0.01, spot_on_ev=-0.95,
            best_bid=Bid(2, 5), best_bid_prob=0.80,
            prev_bid=Bid(2, 3)))
        self.assertEqual(result.action, Action.BID)
        self.assertEqual(result.bid, Bid(2, 5))

    def test_raise_action_when_count_exceeds_prev(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.10, effective_threshold=0.50,
            spot_on_prob=0.01, spot_on_ev=-0.95,
            best_bid=Bid(3, 5), best_bid_prob=0.80,
            prev_bid=Bid(2, 3)))
        self.assertEqual(result.action, Action.RAISE)
        self.assertEqual(result.bid, Bid(3, 5))

    def test_challenge_below_threshold_not_taken(self):
        s = self._make()
        # P(succ)=0.40 < 0.50 floor, so challenge gated off; falls back to bid.
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.40, effective_threshold=0.50,
            spot_on_prob=0.01, spot_on_ev=-0.95,
            best_bid=Bid(2, 4), best_bid_prob=0.70))
        self.assertNotEqual(result.action, Action.CHALLENGE)

    def test_spot_on_skipped_when_ev_negative(self):
        s = self._make()
        # 2-player table, P(exact)=0.30 → EV = 0.30*1 - 0.70 = -0.40 (skip)
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.30, effective_threshold=0.50,
            spot_on_prob=0.30, spot_on_ev=-0.40,
            best_bid=Bid(2, 4), best_bid_prob=0.50,
            prev_bid=Bid(2, 3)))
        self.assertNotEqual(result.action, Action.SPOT_ON)

    def test_spot_on_taken_when_ev_strongly_positive_at_8_players(self):
        s = self._make()
        # 8-player table, P(exact)=0.34 → EV = 0.34*7 - 0.66 = +1.72
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.20, effective_threshold=0.50,
            spot_on_prob=0.34, spot_on_ev=1.72,
            best_bid=Bid(3, 5), best_bid_prob=0.60,
            prev_bid=Bid(2, 3)))
        self.assertEqual(result.action, Action.SPOT_ON)

    def test_fallback_to_challenge_when_all_zero_no_bid(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.0, effective_threshold=0.50,
            spot_on_prob=0.0, spot_on_ev=-1.0,
            best_bid=None, best_bid_prob=0.0))
        self.assertEqual(result.action, Action.CHALLENGE)

    def test_fallback_to_bid_when_all_zero_but_have_bid(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.0, effective_threshold=0.50,
            spot_on_prob=0.0, spot_on_ev=-1.0,
            best_bid=Bid(3, 2), best_bid_prob=0.0,
            prev_bid=Bid(2, 3)))
        self.assertIn(result.action, (Action.BID, Action.RAISE))
        self.assertEqual(result.bid, Bid(3, 2))

    def test_player_name_always_in_result(self):
        s = self._make()
        result = s._decide_action("T", self._ctx(
            challenge_prob=0.90, effective_threshold=0.50,
            spot_on_prob=0.05, spot_on_ev=-0.5,
            best_bid=Bid(3, 4), best_bid_prob=0.40))
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
            spot_on_ev=-0.95,
            best_bid=Bid(4, 4),
            best_bid_prob=0.40,
            blind_aggression_score=score,
            pressure_opportunity_score=0.0,
        )

    def test_high_aggression_boosts_challenge_above_threshold(self):
        """With always-on cunning factor 0.5, a high blind-aggression score still
        boosts a near-threshold challenge prob enough to fire."""
        s = make_cpu_strategy()
        s.challenge_threshold = 0.65
        # score=3.0 → boost = min(0.15, (3.0-1.4)*0.1*0.5) = 0.08
        # effective_challenge_prob = 0.55+0.08=0.63, effective_threshold = max(0.50, 0.65-0.04)=0.61
        # ev_challenge = 2*0.63 - 1 = 0.26 > 0 and beats spot-on/bid baseline.
        ctx = self._ctx_with_aggression(score=3.0, challenge_prob=0.55, effective_threshold=0.65)
        result = s._decide_action("T", ctx)
        self.assertEqual(result.action, Action.CHALLENGE)

    def test_low_aggression_no_boost_challenge_suppressed(self):
        """At score barely above threshold, the boost is tiny and challenge stays gated."""
        s = make_cpu_strategy()
        s.challenge_threshold = 0.65
        # score=1.5 → boost = min(0.15, (1.5-1.4)*0.1*0.5) = 0.005
        # effective_prob = 0.555, effective_threshold ≈ 0.6475 → gated off
        ctx = self._ctx_with_aggression(score=1.5, challenge_prob=0.55, effective_threshold=0.65)
        result = s._decide_action("T", ctx)
        self.assertNotEqual(result.action, Action.CHALLENGE)


class TestPressureOpportunityBidSelection(unittest.TestCase):
    """High pressure_opportunity_score (× the always-on cunning factor) shifts bid
    selection toward higher counts."""

    def test_high_pressure_picks_higher_count_bid(self):
        from scipy.stats import binom as _binom
        s = make_cpu_strategy()
        dice = [3, 3, 3, -1, -1, -1]
        num_dice = 3
        model = _binom(n=5, p=2 / 6)
        # Both Bid(2,3) and Bid(3,3) have prob=1.0 since player holds 3 threes.
        # pressure_hint > threshold should break the tie in favour of Bid(3,3).
        pressure_hint = 1.0  # well above _PRESSURE_OPP_THRESHOLD
        bid, _ = s._rank_and_select_bid(dice, num_dice, [Bid(2, 3), Bid(3, 3)], model, set(),
                                        pressure_hint=pressure_hint)
        self.assertEqual(bid, Bid(3, 3))

    def test_no_pressure_picks_lower_count_bid(self):
        from scipy.stats import binom as _binom
        s = make_cpu_strategy()
        dice = [3, 3, 3, -1, -1, -1]
        num_dice = 3
        model = _binom(n=5, p=2 / 6)
        # pressure_hint = 0 → no pressure path → insertion order wins (Bid(2,3) first).
        bid, _ = s._rank_and_select_bid(dice, num_dice, [Bid(2, 3), Bid(3, 3)], model, set(),
                                        pressure_hint=0.0)
        self.assertEqual(bid, Bid(2, 3))


class TestPersonalityArchetype(unittest.TestCase):
    def test_from_archetype_explicit(self):
        rng = random.Random(0)
        p = Personality.from_archetype('Salty Veteran', rng)
        self.assertEqual(p.archetype_label, 'Salty Veteran')
        self.assertGreaterEqual(p.risk_appetite, 1)
        self.assertLessEqual(p.risk_appetite, 100)
        # Salty Veteran spec: risk=30 ± 8 → [22, 38].
        self.assertGreaterEqual(p.risk_appetite, 22)
        self.assertLessEqual(p.risk_appetite, 38)

    def test_from_archetype_unknown_raises(self):
        with self.assertRaises(ValueError):
            Personality.from_archetype('Captain Crunch', random.Random(0))

    def test_archetype_random_picks_by_weight(self):
        rng = random.Random(1)
        labels = [Personality.random(rng).archetype_label for _ in range(2000)]
        from collections import Counter
        counts = Counter(labels)
        # Weights: Salty=3, Reckless=2, Crafty=2, Stoic=2, Wild Card=1 (sum=10)
        # Salty Veteran should be the most common archetype.
        most_common = counts.most_common(1)[0][0]
        self.assertEqual(most_common, 'Salty Veteran')
        # Wild Card is rarest (weight=1) — should be ~10% of samples.
        self.assertLess(counts['Wild Card'] / 2000, 0.20)

    def test_archetype_jitter_in_bounds(self):
        rng = random.Random(42)
        for _ in range(500):
            p = Personality.random(rng)
            self.assertGreaterEqual(p.risk_appetite, 1)
            self.assertLessEqual(p.risk_appetite, 100)
            self.assertGreaterEqual(p.attentiveness_score, 1)
            self.assertLessEqual(p.attentiveness_score, 100)
            self.assertGreaterEqual(p.bluff_frequency, 1)
            self.assertLessEqual(p.bluff_frequency, 100)


if __name__ == '__main__':
    unittest.main()
