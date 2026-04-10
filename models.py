from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    START     = 'START'
    BID       = 'BID'
    RAISE     = 'RAISE'
    CHALLENGE = 'CHALLENGE'
    SPOT_ON   = 'SPOT ON'
    NONE      = 'NONE'


@dataclass(frozen=True)
class Bid:
    count: int
    face: int


@dataclass(frozen=True)
class TurnResult:
    bid: 'Bid | None'
    action: Action
    player_name: str
