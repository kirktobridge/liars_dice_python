from __future__ import annotations
from typing import TypedDict
from scipy.stats import binom
from models import Bid

_binom_cache: dict[int, binom] = {}


def _get_binom(n: int) -> binom:
    if n not in _binom_cache:
        _binom_cache[n] = binom(n=n, p=2/6)
    return _binom_cache[n]


def _needed_cnt(human_dice: list[int], bid: Bid) -> int:
    if bid.face == 1:
        own = human_dice.count(1)
    else:
        own = human_dice.count(bid.face) + human_dice.count(1)
    return bid.count - own


class AdvisorData(TypedDict):
    challenge_prob: float | None   # None on opening bid (no prev_bid)
    spot_on_prob:   float | None
    bid_probs:      dict[int, dict[int, float]]  # {face: {count: prob}}


def advisor_probs(
    human_dice: list[int],
    tot_other_dice: int,
    prev_bid: Bid | None,
    valid_bids: list[Bid],
) -> AdvisorData:
    model = _get_binom(tot_other_dice)

    if prev_bid is None:
        challenge_prob = None
        spot_on_prob   = None
    else:
        needed = _needed_cnt(human_dice, prev_bid)
        challenge_prob = float(model.cdf(needed - 1)) if needed > 0 else 0.0
        spot_on_prob   = float(model.pmf(needed))

    bid_probs: dict[int, dict[int, float]] = {}
    for bid in valid_bids:
        needed = _needed_cnt(human_dice, bid)
        prob = 1.0 if needed <= 0 else 1.0 - float(model.cdf(needed - 1))
        bid_probs.setdefault(bid.face, {})[bid.count] = prob

    return AdvisorData(
        challenge_prob=challenge_prob,
        spot_on_prob=spot_on_prob,
        bid_probs=bid_probs,
    )
