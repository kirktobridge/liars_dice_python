from scipy.stats import binom
from models import Bid

_binom_cache: dict[int, binom] = {}


def get_binom(n: int) -> binom:
    if n not in _binom_cache:
        _binom_cache[n] = binom(n=n, p=2/6)
    return _binom_cache[n]


def needed_cnt(dice: list[int], bid: Bid) -> int:
    if bid.face == 1:
        face_match = dice.count(1)
    else:
        face_match = dice.count(bid.face) + dice.count(1)
    return bid.count - face_match
