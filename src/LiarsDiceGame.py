import logging
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import constants as Constants
from Player import Player
from collections import deque
from models import Action, Bid, GameState, PlayerState, TurnResult

logger = logging.getLogger('liars_dice.game')

_CLI_LOGS_DIR = Path(__file__).parent.parent / 'logs' / 'cli'
_MAX_CLI_LOGS = 10


@dataclass
class _TurnState:
    player_idx: int
    player: 'Player'
    prev_bidder_name: 'str | None'
    prev_bid: 'Bid | None'
    cur_event: TurnResult


def _cli_log_path() -> Path:
    _CLI_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logs = sorted(_CLI_LOGS_DIR.glob('*_LiarsDiceGame_Log.log'), key=lambda p: p.stat().st_mtime)
    for old in logs[:max(0, len(logs) - (_MAX_CLI_LOGS - 1))]:
        old.unlink()
    return _CLI_LOGS_DIR / f'{datetime.now().strftime("%Y-%m-%d_%H_%M_%S")}_LiarsDiceGame_Log.log'


class LiarsDiceGame:

    def __init__(self, num_players, max_rounds=Constants.MAX_ROUNDS, on_event=None, rng: random.Random | None = None, log: bool = False):
        self._on_event = on_event or (lambda e: None)
        self._rng = rng if rng is not None else random.Random()
        if num_players < 2:
            raise ValueError(f"LiarsDiceGame requires at least 2 players, got {num_players}.")
        logger.debug('Game object initialized, num_players=%d', num_players)
        self.num_players = num_players
        self.max_rounds = max_rounds
        self.round_num = 0
        self.players = []
        self.prev_action = ''
        self.game_status = True
        self.round_rolls = []
        self._logging = log
        self._log_path = _cli_log_path() if log else None
        self._file_handler = None
        self._game_event_logger = None
        self.tot_num_dice = 0
        self.event_counter = 0
        self.round_events = deque()
        self.round_loser = None
        self._round_loser_idx = None
        self.start_index = 0

    def _emit(self, event_type: str, **data) -> None:
        self._on_event({'type': event_type, **data})

    @property
    def log_path(self) -> 'Path | None':
        return self._log_path

    def add_player(self, p):
        self.players.append(p)
        logger.debug('Player %s appended to game player list', p.name)

    def count_dice(self):
        self.tot_num_dice = sum(p.num_dice for p in self.players)
        return self.tot_num_dice

    def process_round(self) -> bool:
        self._open_round()
        tot_dice = self.count_dice()
        while True:
            ended = False
            for i in range(self.num_players):
                p_idx = (self.start_index + i) % self.num_players
                ts = self._run_turn(p_idx, tot_dice)
                if ts is None:
                    continue
                action = ts.cur_event.action
                if action == Action.CHALLENGE:
                    self._handle_challenge(ts)
                    ended = True
                    break
                if action == Action.SPOT_ON:
                    self._handle_spot_on(ts)
                    ended = True
                    break
                self._emit_bid_or_raise(ts)
            logger.debug('End of for loop in process_round')
            if ended:
                break
        logger.debug('Broke out of round_cont loop')
        self._close_round()
        return self.game_status

    def _open_round(self) -> None:
        self.round_num += 1
        self._emit('round_started', round_num=self.round_num)
        self.round_events.clear()
        self.log_event([[-1, -1], f'RND{self.round_num}', 'SYS'])
        self._emit('dice_rolling')
        self.round_rolls.clear()
        for p in self.players:
            p.roll()
            self.round_rolls.extend(p.dice[:p.num_dice])
        self.log_event(TurnResult(None, Action.DICE_ROLL, 'SYS'))
        self._emit('dice_rolled')

    def _run_turn(self, player_idx: int, tot_dice: int) -> '_TurnState | None':
        player = self.players[player_idx]
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('turn start | %s | hands: %s', player.name, self._dice_snapshot())
        self._emit('turn_started',
                   player_name=player.name,
                   num_dice=player.num_dice,
                   round_num=self.round_num)

        try:
            prev_bidder_name, prev_bid = self._read_prev_for_turn()
        except Exception as e:
            logger.exception('Exception in process_round: prev_event assignment')
            self._emit('error', func_name='process_round: prev_event assignment', message=str(e))
            return None

        try:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug('calling take_turn | player=%s | prev_action=%s | prev_bid=%s | hands: %s',
                             player.name, self.round_events[0].action,
                             getattr(self.round_events[0], 'bid', None),
                             self._dice_snapshot())
            bidder_num_dice = self.players[player_idx - 1].num_dice
            next_player_num_dice = self.players[(player_idx + 1) % self.num_players].num_dice
            if player.player_type == 'HUMAN':
                if not self._emit_human_turn_start(player, prev_bidder_name):
                    return None
            cur_event = player.take_turn(
                self.round_events, tot_dice - player.num_dice,
                bidder_num_dice, next_player_num_dice)
            self.log_event(cur_event)
            for observer in self.players:
                if observer is not player:
                    observer.observe_action(cur_event.player_name, cur_event.action, cur_event.bid, tot_dice)
            if cur_event.action == Action.NONE:
                raise Exception("Blank new_action")
        except Exception as e:
            logger.exception('Exception in process_round: take_turn call')
            self._emit('error', func_name='process_round: take_turn call', message=str(e))
            self.log_event(TurnResult(None, Action.NONE, player.name))
            self.log_events(self.round_events)
            return None

        return _TurnState(
            player_idx=player_idx,
            player=player,
            prev_bidder_name=prev_bidder_name,
            prev_bid=prev_bid,
            cur_event=cur_event,
        )

    def _read_prev_for_turn(self) -> 'tuple[str | None, Bid | None]':
        """Inspect round_events[0]; insert START marker on round opening; return (prev_bidder_name, prev_bid)."""
        prev_event = self.round_events[0]
        if prev_event.action == Action.DICE_ROLL:
            self.log_event(TurnResult(None, Action.START, 'SYS'))
            return None, None
        if prev_event.action in (Action.BID, Action.RAISE):
            return prev_event.player_name, prev_event.bid
        return prev_event.player_name, None

    def _emit_human_turn_start(self, player: 'Player', prev_bidder_name: 'str | None') -> bool:
        active = [pl for pl in self.players if pl.num_dice > 0]
        idx = next((i for i, pl in enumerate(active) if pl is player), None)
        if idx is None:
            logger.error('Human player %s not found in active list', player.name)
            return False
        ordered = active[idx:] + active[:idx]
        self._emit('human_turn_start',
                   player_dice=[{'name': pl.name, 'num_dice': pl.num_dice} for pl in ordered],
                   current_player=player.name,
                   prev_bidder=prev_bidder_name)
        return True

    def _emit_bid_or_raise(self, ts: '_TurnState') -> None:
        bid = ts.cur_event.bid
        if ts.cur_event.action == Action.BID:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug('BID | %s bids %dx%d | hands: %s',
                             ts.player.name, bid.count, bid.face, self._dice_snapshot())
            self._emit('bid_made', player_name=ts.player.name, count=bid.count, face=bid.face)
        elif ts.cur_event.action == Action.RAISE:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug('RAISE | %s raises to %dx%d | hands: %s',
                             ts.player.name, bid.count, bid.face, self._dice_snapshot())
            self._emit('raise_made', player_name=ts.player.name, count=bid.count, face=bid.face)

    def _handle_challenge(self, ts: '_TurnState') -> None:
        challenger = ts.player
        bidder = self.players[ts.player_idx - 1]
        bid_cnt, bid_face = ts.prev_bid.count, ts.prev_bid.face

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('CHALLENGE | %s challenges %s bid %dx%d | hands: %s',
                         challenger.name, ts.prev_bidder_name, bid_cnt, bid_face,
                         self._dice_snapshot())
        self._emit('challenge_called',
                   challenger_name=challenger.name,
                   bidder_name=ts.prev_bidder_name,
                   bid_count=bid_cnt,
                   bid_face=bid_face,
                   tot_num_dice=self.tot_num_dice,
                   bidder_num_dice=bidder.num_dice)
        self._emit('rolls_revealed',
                   player_rolls=[{'name': pl.name, 'dice': pl.dice[:pl.num_dice]} for pl in self.players],
                   bid_face=bid_face,
                   bid_count=bid_cnt,
                   bidder_name=ts.prev_bidder_name)

        succeeded, loser = self._resolve_challenge(ts.prev_bid, challenger, bidder)
        actual_cnt = self.round_rolls.count(bid_face)
        ones_cnt = self.round_rolls.count(1)
        logger.debug('CHALLENGE result | succeeded=%s | bid=%dx%d actual=%d (ones=%d) | loser=%s',
                     succeeded, bid_cnt, bid_face, actual_cnt, ones_cnt, loser.name)
        self._emit('challenge_resolved',
                   succeeded=succeeded,
                   challenger_name=challenger.name,
                   bid_count=bid_cnt,
                   bid_face=bid_face,
                   actual_count=actual_cnt,
                   ones_count=ones_cnt,
                   loser_name=loser.name)
        for observer in self.players:
            observer.observe_outcome(ts.prev_bidder_name, succeeded)
        self.log_event(['SUCCESS' if succeeded else 'FAILURE', Action.CHALLENGE, challenger.name])
        self.round_loser = loser
        self._round_loser_idx = self.players.index(loser)
        loser.lose_die()

    def _handle_spot_on(self, ts: '_TurnState') -> None:
        caller = ts.player
        bid_cnt, bid_face = ts.prev_bid.count, ts.prev_bid.face

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('SPOT-ON | %s calls spot-on on %s bid %dx%d | hands: %s',
                         caller.name, ts.prev_bidder_name, bid_cnt, bid_face,
                         self._dice_snapshot())
        self._emit('spot_on_called',
                   caller_name=caller.name,
                   bidder_name=ts.prev_bidder_name,
                   bid_count=bid_cnt,
                   bid_face=bid_face,
                   tot_num_dice=self.tot_num_dice)
        self._emit('rolls_revealed',
                   player_rolls=[{'name': pl.name, 'dice': pl.dice[:pl.num_dice]} for pl in self.players],
                   bid_face=bid_face,
                   bid_count=bid_cnt,
                   bidder_name=ts.prev_bidder_name)

        succeeded, losers = self._resolve_spot_on(ts.prev_bid, caller)
        actual_cnt = self.round_rolls.count(bid_face)
        ones_cnt = self.round_rolls.count(1)
        logger.debug('SPOT-ON result | succeeded=%s | bid=%dx%d actual=%d | losers=%s',
                     succeeded, bid_cnt, bid_face, actual_cnt, [l.name for l in losers])
        self._emit('spot_on_resolved',
                   succeeded=succeeded,
                   caller_name=caller.name,
                   caller_player_type=caller.player_type,
                   bid_count=bid_cnt,
                   bid_face=bid_face,
                   actual_count=actual_cnt,
                   ones_count=ones_cnt,
                   loser_names=[l.name for l in losers])

        if succeeded:
            self.log_event(['SUCCESS', Action.SPOT_ON, caller.name])
            for loser in losers:
                loser.lose_die()
        else:
            self.log_event(['FAILURE', Action.SPOT_ON, caller.name])
            losers[0].lose_die()
            self.round_loser = losers[0]
            self._round_loser_idx = self.players.index(losers[0])

    def _close_round(self) -> None:
        for player in self.players:
            logger.debug('%s has %d dice', player.name, player.num_dice)
        removed_players = self._eliminate_players()
        for player in removed_players:
            self._emit('player_eliminated',
                       player_name=player.name,
                       player_type=player.player_type,
                       round_num=self.round_num)
        self.count_dice()
        if self.num_players < 2:
            self._emit('game_won', winner_name=self.players[0].name)
            self.game_status = False
        else:
            self._emit('round_summary',
                       num_players=self.num_players,
                       tot_num_dice=self.tot_num_dice,
                       player_dice=[{'name': pl.name, 'dice': pl.dice[:pl.num_dice]} for pl in self.players])
        if self.round_num > self.max_rounds:
            logger.debug('Max rounds reached, ending game')
            self.game_status = False
        self._reorder_for_next_round()

    def _dice_snapshot(self) -> str:
        return '  '.join(
            f'{p.name}({p.num_dice}):{p.dice[:p.num_dice]}' for p in self.players
        )

    def log_events(self, events):
        '''log_event for multiple events.'''
        try:
            log_stop = len(events)
            if len(events) < 1:
                raise Exception(
                    f'event log failure: no events for round {self.round_num}')
            for event in range(0, log_stop):
                self.log_event(events.popleft())
        except Exception as e:
            logger.exception('Exception in log_events')

    def log_event(self, event):
        '''Adds entry to game log for analysis by developer.'''
        self.round_events.appendleft(event)
        self.event_counter += 1
        if not self._logging:
            return
        try:
            snap = self._dice_snapshot()
            if isinstance(event, TurnResult):
                msg = f'#{self.event_counter} | {event.action} | {event.player_name} | bid={event.bid} | {snap}'
            elif isinstance(event, list):
                data, etype, actor = event[0], event[1], event[2]
                msg = f'#{self.event_counter} | {etype} | {actor} | {data} | {snap}'
            elif isinstance(event, str):
                msg = f'#{self.event_counter} | ERROR | SYS | {event} | {snap}'
            else:
                return
            self._game_event_logger.info(msg)
        except Exception as e:
            logger.exception('Exception in log_event')

    def close(self) -> None:
        """Remove the file handler and close the log file if one was opened."""
        if self._logging and self._file_handler:
            self._game_event_logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

    def __enter__(self) -> 'LiarsDiceGame':
        if self._logging:
            try:
                self._game_event_logger = logging.getLogger('liars_dice.game_events')
                handler = logging.FileHandler(self._log_path, mode='w')
                handler.setFormatter(logging.Formatter('%(message)s'))
                self._game_event_logger.addHandler(handler)
                self._game_event_logger.setLevel(logging.INFO)
                self._game_event_logger.propagate = False
                self._file_handler = handler
            except OSError as e:
                logger.warning('Failed to open game log %s: %s — file logging disabled', self._log_path, e)
                self._logging = False
                self._game_event_logger = None
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _resolve_challenge(
        self, prev_bid: Bid, challenger: 'Player', bidder: 'Player'
    ) -> tuple[bool, 'Player']:
        """Returns (challenge_succeeded, loser). No print/sleep/side effects."""
        actual_cnt = self.round_rolls.count(prev_bid.face)
        ones_cnt   = self.round_rolls.count(1)
        checked    = actual_cnt + ones_cnt if prev_bid.face != 1 else actual_cnt
        succeeded  = checked < prev_bid.count
        return (succeeded, bidder if succeeded else challenger)

    def _resolve_spot_on(
        self, prev_bid: Bid, caller: 'Player'
    ) -> tuple[bool, list]:
        """Returns (spot_on_succeeded, list_of_players_who_lose_a_die). No print/sleep/side effects."""
        actual_cnt = self.round_rolls.count(prev_bid.face)
        ones_cnt   = self.round_rolls.count(1)
        actual     = actual_cnt + ones_cnt if prev_bid.face != 1 else actual_cnt
        succeeded  = (actual == prev_bid.count)
        if succeeded:
            return (True, [p for p in self.players if p is not caller])
        return (False, [caller])

    def _eliminate_players(self) -> list:
        """Removes zero-dice players from self.players; marks eliminated; updates num_players.
        Returns removed list (caller handles printing and game_status)."""
        to_remove = [p for p in self.players if p.num_dice == 0]
        for player in to_remove:
            player.eliminated = True
            logger.debug('%s being removed from player array', player.name)
            self.players.remove(player)
        self.num_players = len(self.players)
        return to_remove

    def snapshot(self) -> GameState:
        """Return a serializable snapshot of current game state."""
        prev_bid: Bid | None = None
        prev_bidder: str | None = None
        current_player: str | None = None
        _system_actions = (Action.DICE_ROLL, Action.START, Action.NONE)

        for event in self.round_events:
            if isinstance(event, TurnResult):
                if current_player is None and event.action not in _system_actions:
                    current_player = event.player_name
                if prev_bid is None and event.action in (Action.BID, Action.RAISE):
                    prev_bid = event.bid
                    prev_bidder = event.player_name
            if current_player is not None and prev_bid is not None:
                break

        game_over = not self.game_status
        winner = self.players[0].name if game_over and len(self.players) == 1 else None

        return GameState(
            round_num=self.round_num,
            active_players=[
                PlayerState(
                    name=p.name,
                    player_type=p.player_type,
                    num_dice=p.num_dice,
                    is_eliminated=p.eliminated,
                )
                for p in self.players
            ],
            prev_bid=prev_bid,
            prev_bidder=prev_bidder,
            current_player=current_player,
            game_over=game_over,
            winner=winner,
        )

    def _reorder_for_next_round(self) -> None:
        """Rotates start_index so the round loser goes first next round, preserving seat order."""
        if self.round_loser is not None:
            if self.round_loser in self.players:
                self.start_index = self.players.index(self.round_loser)
            elif self._round_loser_idx is not None and self.num_players > 0:
                # loser was eliminated; next player in seat order starts
                self.start_index = self._round_loser_idx % self.num_players
        self.round_loser = None
        self._round_loser_idx = None
