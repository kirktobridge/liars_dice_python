from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pandas as pd


@dataclass
class RoundRow:
    seed: int
    round_num: int
    total_dice_on_table: int | None
    bid_count: int
    action_type: str
    bid_count_claimed: int | None
    effective_actual_count: int | None
    challenge_succeeded: bool | None
    round_loser: str | None
    action_caller: str | None
    bidder_num_dice: int | None


@dataclass
class EliminationRow:
    seed: int
    player_name: str
    finishing_position: int


@dataclass
class GameRow:
    seed: int
    winner: str
    rounds: int
    num_players: int
    winner_risk_appetite: int
    winner_attentiveness: int
    winner_bluff_frequency: int
    winner_archetype: str | None


_ROUND_NULLABLE_INT_COLS = ('total_dice_on_table', 'bid_count_claimed', 'effective_actual_count', 'bidder_num_dice')
_ROUND_DTYPES = {col: 'Int64' for col in _ROUND_NULLABLE_INT_COLS}
_ROUND_DTYPES['challenge_succeeded'] = 'boolean'


def rounds_to_df(rows: list[RoundRow]) -> pd.DataFrame:
    if not rows:
        df = pd.DataFrame(columns=[f.name for f in dataclasses.fields(RoundRow)])
        return df.astype(_ROUND_DTYPES)
    df = pd.DataFrame([dataclasses.asdict(r) for r in rows])
    return df.astype(_ROUND_DTYPES)


def eliminations_to_df(rows: list[EliminationRow]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=[f.name for f in dataclasses.fields(EliminationRow)])
    return pd.DataFrame([dataclasses.asdict(r) for r in rows])
