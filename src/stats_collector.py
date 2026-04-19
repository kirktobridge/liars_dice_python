from __future__ import annotations


class GameStatsCollector:
    """Collects per-round and per-elimination statistics from LiarsDiceGame _emit events."""

    def __init__(self, seed: int, num_players: int) -> None:
        self.seed = seed
        self.num_players = num_players
        self.round_rows: list[dict] = []
        self.elimination_rows: list[dict] = []

        self._cur_round = 0
        self._bid_count = 0
        self._action_type = 'none'
        self._tot_num_dice: int | None = None
        self._bid_count_claimed: int | None = None
        self._bid_face: int | None = None
        self._challenge_succeeded: bool | None = None
        self._effective_actual_count: int | None = None
        self._round_loser: str | None = None
        self._challenger_name: str | None = None
        self._bidder_name: str | None = None
        self._caller_name: str | None = None
        self._bidder_num_dice: int | None = None

        self._elim_counter = 0

    def on_event(self, event: dict) -> None:
        t = event.get('type')

        if t == 'round_started':
            self._flush_round()
            self._cur_round = event['round_num']
            self._bid_count = 0
            self._action_type = 'none'
            self._tot_num_dice = None
            self._bid_count_claimed = None
            self._bid_face = None
            self._challenge_succeeded = None
            self._effective_actual_count = None
            self._round_loser = None
            self._challenger_name = None
            self._bidder_name = None
            self._caller_name = None
            self._bidder_num_dice = None

        elif t in ('bid_made', 'raise_made'):
            self._bid_count += 1

        elif t == 'challenge_called':
            self._action_type = 'challenge'
            self._tot_num_dice = event.get('tot_num_dice')
            self._bid_count_claimed = event.get('bid_count')
            self._bid_face = event.get('bid_face')
            self._challenger_name = event.get('challenger_name')
            self._bidder_name = event.get('bidder_name')
            self._bidder_num_dice = event.get('bidder_num_dice')

        elif t == 'spot_on_called':
            self._action_type = 'spot_on'
            self._tot_num_dice = event.get('tot_num_dice')
            self._bid_count_claimed = event.get('bid_count')
            self._bid_face = event.get('bid_face')
            self._caller_name = event.get('caller_name')

        elif t == 'challenge_resolved':
            succeeded = event.get('succeeded', False)
            self._challenge_succeeded = succeeded
            actual = event.get('actual_count', 0)
            ones = event.get('ones_count', 0)
            face = self._bid_face
            self._effective_actual_count = actual + ones if face != 1 else actual
            if succeeded:
                self._round_loser = self._bidder_name
            else:
                self._round_loser = self._challenger_name

        elif t == 'spot_on_resolved':
            succeeded = event.get('succeeded', False)
            self._challenge_succeeded = succeeded
            if succeeded:
                self._round_loser = 'multiple'
            else:
                self._round_loser = self._caller_name

        elif t == 'player_eliminated':
            self._elim_counter += 1
            self.elimination_rows.append({
                'seed': self.seed,
                'player_name': event.get('player_name'),
                'finishing_position': self._elim_counter,
            })

        elif t == 'game_won':
            self._flush_round()
            winner = event.get('winner_name')
            self.elimination_rows.append({
                'seed': self.seed,
                'player_name': winner,
                'finishing_position': self.num_players,
            })

    def _flush_round(self) -> None:
        if self._cur_round == 0:
            return
        if self._action_type == 'challenge':
            action_caller = self._challenger_name
        elif self._action_type == 'spot_on':
            action_caller = self._caller_name
        else:
            action_caller = None
        self.round_rows.append({
            'seed': self.seed,
            'round_num': self._cur_round,
            'total_dice_on_table': self._tot_num_dice,
            'bid_count': self._bid_count,
            'action_type': self._action_type,
            'bid_count_claimed': self._bid_count_claimed,
            'effective_actual_count': self._effective_actual_count,
            'challenge_succeeded': self._challenge_succeeded,
            'round_loser': self._round_loser,
            'action_caller': action_caller,
            'bidder_num_dice': self._bidder_num_dice,
        })
