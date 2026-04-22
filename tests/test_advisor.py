import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from advisor import advisor_probs, _needed_cnt
from models import Bid


def _all_bids(max_count: int) -> list[Bid]:
    return [Bid(c, f) for c in range(1, max_count + 1) for f in range(1, 7)]


class TestNeededCnt(unittest.TestCase):
    def test_non_one_face_counts_ones_as_wildcards(self):
        # hand: [1, 3, 3], bid: 4×3 — own = 2 threes + 1 wildcard = 3, needs 4-3=1 more
        self.assertEqual(_needed_cnt([1, 3, 3], Bid(4, 3)), 1)

    def test_face_one_does_not_double_count(self):
        # hand: [1, 1, 3], bid: 3×1 — needs 3-2=1 more from others (ones only)
        self.assertEqual(_needed_cnt([1, 1, 3], Bid(3, 1)), 1)

    def test_negative_when_hand_covers(self):
        self.assertLessEqual(_needed_cnt([2, 2, 2], Bid(2, 2)), 0)


class TestAdvisorProbs(unittest.TestCase):

    def test_opening_bid_returns_none_probs(self):
        data = advisor_probs(
            human_dice=[3, 4, 5],
            tot_other_dice=10,
            prev_bid=None,
            valid_bids=_all_bids(13),
        )
        self.assertIsNone(data['challenge_prob'])
        self.assertIsNone(data['spot_on_prob'])

    def test_challenge_prob_zero_when_needed_is_zero(self):
        # human has all needed dice — bid trivially true, challenge should fail
        data = advisor_probs(
            human_dice=[2, 2, 2],
            tot_other_dice=10,
            prev_bid=Bid(2, 2),   # needed = 2-3 = -1 → capped to 0
            valid_bids=[],
        )
        self.assertEqual(data['challenge_prob'], 0.0)

    def test_bid_prob_one_when_hand_covers(self):
        # human holds enough — bid probability must be 1.0
        valid = [Bid(2, 2)]
        data = advisor_probs(
            human_dice=[2, 2, 2],
            tot_other_dice=10,
            prev_bid=None,
            valid_bids=valid,
        )
        self.assertEqual(data['bid_probs'][2][2], 1.0)

    def test_all_probs_in_range(self):
        valid = _all_bids(15)
        data = advisor_probs(
            human_dice=[1, 3, 4, 5, 6],
            tot_other_dice=10,
            prev_bid=Bid(3, 4),
            valid_bids=valid,
        )
        self.assertGreaterEqual(data['challenge_prob'], 0.0)
        self.assertLessEqual(data['challenge_prob'], 1.0)
        self.assertGreaterEqual(data['spot_on_prob'], 0.0)
        self.assertLessEqual(data['spot_on_prob'], 1.0)
        for face_map in data['bid_probs'].values():
            for p in face_map.values():
                self.assertGreaterEqual(p, 0.0)
                self.assertLessEqual(p, 1.0)

    def test_all_valid_bids_present_in_bid_probs(self):
        valid = [Bid(4, 2), Bid(4, 3), Bid(5, 1)]
        data = advisor_probs(
            human_dice=[2, 3],
            tot_other_dice=8,
            prev_bid=None,
            valid_bids=valid,
        )
        for bid in valid:
            self.assertIn(bid.count, data['bid_probs'].get(bid.face, {}))

    def test_challenge_prob_increases_with_needed(self):
        # Higher needed count → harder bid → higher challenge success prob
        dice = [6, 6, 6]
        tot = 10
        low = advisor_probs(dice, tot, Bid(1, 2), [])['challenge_prob']
        high = advisor_probs(dice, tot, Bid(8, 2), [])['challenge_prob']
        self.assertLess(low, high)

    def test_empty_valid_bids_returns_empty_bid_probs(self):
        data = advisor_probs([1, 2], 8, None, [])
        self.assertEqual(data['bid_probs'], {})


if __name__ == '__main__':
    unittest.main()
