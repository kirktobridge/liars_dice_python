from dataclasses import dataclass, field
from enum import Enum


class Action(str, Enum):
    START     = 'START'
    DICE_ROLL = 'DICE ROLL'
    BID       = 'BID'
    RAISE     = 'RAISE'
    CHALLENGE = 'CHALLENGE'
    SPOT_ON   = 'SPOT ON'
    NONE      = 'NONE'


@dataclass(frozen=True)
class Bid:
    count: int
    face: int


@dataclass
class OpponentProfile:
    bids_observed: int = 0
    total_aggression: float = 0.0
    bids_challenged: int = 0
    challenge_successes: int = 0

    @property
    def bluff_rate(self) -> float:
        return self.challenge_successes / self.bids_challenged if self.bids_challenged else 0.5

    @property
    def avg_aggression(self) -> float:
        return self.total_aggression / self.bids_observed if self.bids_observed else 0.5


@dataclass(frozen=True)
class TurnResult:
    bid: 'Bid | None'
    action: Action
    player_name: str


@dataclass(frozen=True)
class ResponseContext:
    prev_bid: Bid
    challenge_prob: float
    effective_threshold: float
    spot_on_prob: float
    best_bid: 'Bid | None'
    best_bid_prob: float
