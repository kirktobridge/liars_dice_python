import os
import sys
import random
from datetime import datetime
import constants as Constants
from Player import Player
from collections import deque
from models import Action, Bid, TurnResult

class LiarsDiceGame:

    def __init__(self, num_players, max_rounds=Constants.MAX_ROUNDS, on_event=None, rng: random.Random | None = None, log: bool = False):
        self._on_event = on_event or (lambda e: None)
        self._rng = rng if rng is not None else random.Random()
        if Constants.DEBUG:
            self._emit('debug', msg='Game Object Initialized')
        self.num_players = num_players
        self.max_rounds = max_rounds
        self.round_num = 0
        self.players = []
        self.prev_action = ''
        self.game_status = True
        self.round_rolls = []
        self._logging = log
        if self._logging:
            self._log_path = f'{datetime.now().strftime("%H_%M_%S")}_LiarsDiceGame_Log.txt'
            self.game_log_file = open(self._log_path, 'w+')
        else:
            self._log_path = None
            self.game_log_file = None
        self.tot_num_dice = 0
        self.event_counter = 0
        self.round_events = deque()
        self.round_loser = None

    def _emit(self, event_type: str, **data) -> None:
        self._on_event({'type': event_type, **data})

    def print_error(self, func_name, e=None):
        log_string = f'Exception caught in {func_name}! - {e}'
        try:
            fname = os.path.split(sys.exc_info()[2].tb_frame.f_code.co_filename)[1]
            log_string2 = str(sys.exc_info()[1]) + str(fname) + str(sys.exc_info()[2].tb_lineno)
            message = log_string + log_string2
        except Exception:
            message = log_string
        self._emit('error', func_name=func_name, message=message)
        self.log_event(message)

    def add_player(self, p):
        try:
            self.players.append(p)
            if Constants.DEBUG:
                self._emit('debug', msg=f'Player {p.name} appended to game player list.')
        except Exception as e:
            self.print_error('add_player')

    def count_dice(self):
        try:
            self.tot_num_dice = 0
            for p in self.players:
                self.tot_num_dice += p.num_dice
            return self.tot_num_dice
        except Exception as e:
            self.print_error('count_dice')
            return -1

    def process_round(self):
        self.round_num += 1
        self._emit('round_started', round_num=self.round_num)
        self.round_events.clear()
        self.log_event([[-1, -1], f'RND{self.round_num}', 'SYS'])
        self._emit('dice_rolling')
        self.round_rolls.clear()
        for p0 in self.players:
            p0.roll()
            self.round_rolls.extend(p0.dice[:p0.num_dice])
        self.log_event(TurnResult(None, Action.DICE_ROLL, 'SYS'))
        self._emit('dice_rolled')
        round_cont = True
        tot_dice = self.count_dice()
        while round_cont:
            for p in range(0, self.num_players):
                if Constants.DEBUG:
                    self._emit('debug', msg=f'{self.players[p].name}: {self.players[p].dice[:self.players[p].num_dice]}')
                self._emit('turn_started',
                           player_name=self.players[p].name,
                           num_dice=self.players[p].num_dice,
                           round_num=self.round_num)
                prev_event = self.round_events[0]
                prev_player_nm = None
                prev_bid_cnt = None
                prev_bid_face = None
                try:
                    if prev_event.action == Action.DICE_ROLL:
                        self.log_event(TurnResult(None, Action.START, 'SYS'))
                    else:
                        prev_player_nm = prev_event.player_name
                        if prev_event.action in (Action.BID, Action.RAISE):
                            prev_bid = prev_event.bid
                            prev_bid_cnt = prev_bid.count
                            prev_bid_face = prev_bid.face
                except Exception as e:
                    self.print_error(
                        'process_round: prev_event assignment', e)
                    continue
                cur_event = TurnResult(None, Action.NONE, '')
                try:
                    if Constants.DEBUG and self._logging:
                        self.game_log_file.write(
                            f'Passing prev_event {self.round_events[0]} and action {self.round_events[0].action} to {self.players[p].name}. \nThey have dice: {self.players[p].dice[:self.players[p].num_dice]}.\n')
                    bidder_num_dice = self.players[p - 1].num_dice
                    if self.players[p].spot == 'HUMAN':
                        active = [pl for pl in self.players if pl.num_dice > 0]
                        idx = next(i for i, pl in enumerate(active) if pl is self.players[p])
                        ordered = active[idx:] + active[:idx]
                        self._emit('human_turn_start',
                                   player_dice=[{'name': pl.name, 'num_dice': pl.num_dice}
                                                for pl in ordered],
                                   current_player=self.players[p].name,
                                   prev_bidder=prev_player_nm if prev_player_nm else None)
                    cur_event = self.players[p].take_turn(
                        self.round_events, tot_dice-self.players[p].num_dice, bidder_num_dice)
                    self.log_event(cur_event)
                    for observer in self.players:
                        if observer is not self.players[p]:
                            observer.observe_action(cur_event.player_name, cur_event.action, cur_event.bid, tot_dice)
                    if cur_event.action == Action.NONE:
                        raise Exception("Blank new_action")
                except Exception as e:
                    self.print_error('process_round: take_turn call', e)
                    cur_event = TurnResult(None, Action.NONE, self.players[p].name)
                    self.log_event(cur_event)
                    self.log_events(self.round_events)
                    continue

                if cur_event.action == Action.BID:
                    self._emit('bid_made',
                               player_name=self.players[p].name,
                               count=cur_event.bid.count,
                               face=cur_event.bid.face)
                elif cur_event.action == Action.RAISE:
                    self._emit('raise_made',
                               player_name=self.players[p].name,
                               count=cur_event.bid.count,
                               face=cur_event.bid.face)
                elif cur_event.action == Action.CHALLENGE:
                    self._emit('challenge_called',
                               challenger_name=self.players[p].name,
                               bidder_name=prev_player_nm,
                               bid_count=prev_bid_cnt,
                               bid_face=prev_bid_face,
                               tot_num_dice=self.tot_num_dice,
                               bidder_num_dice=self.players[p-1].num_dice)
                    self._emit('rolls_revealed', player_rolls=[
                        {'name': pl.name, 'dice': pl.dice[:pl.num_dice]}
                        for pl in self.players], bid_face=prev_bid_face)
                    round_cont = False
                    prev_bid_obj = Bid(prev_bid_cnt, prev_bid_face)
                    succeeded, loser = self._resolve_challenge(prev_bid_obj, self.players[p], self.players[p-1])
                    prev_bid_actual_cnt = self.round_rolls.count(prev_bid_face)
                    actual_ones_cnt = self.round_rolls.count(1)
                    self._emit('challenge_resolved',
                               succeeded=succeeded,
                               challenger_name=self.players[p].name,
                               bid_count=prev_bid_cnt,
                               bid_face=prev_bid_face,
                               actual_count=prev_bid_actual_cnt,
                               ones_count=actual_ones_cnt)
                    for observer in self.players:
                        observer.observe_outcome(prev_player_nm, succeeded)
                    inner_event = ['SUCCESS' if succeeded else 'FAILURE', Action.CHALLENGE, self.players[p].name]
                    self.log_event(inner_event)
                    self.round_loser = loser
                    loser.lose_die()
                    break

                if cur_event.action == Action.SPOT_ON:
                    self._emit('spot_on_called',
                               caller_name=self.players[p].name,
                               bidder_name=prev_player_nm,
                               bid_count=prev_bid_cnt,
                               bid_face=prev_bid_face,
                               tot_num_dice=self.tot_num_dice)
                    self._emit('rolls_revealed', player_rolls=[
                        {'name': pl.name, 'dice': pl.dice[:pl.num_dice]}
                        for pl in self.players], bid_face=prev_bid_face)
                    prev_bid_obj = Bid(prev_bid_cnt, prev_bid_face)
                    succeeded, losers = self._resolve_spot_on(prev_bid_obj, self.players[p])
                    self._emit('spot_on_resolved',
                               succeeded=succeeded,
                               caller_name=self.players[p].name,
                               caller_spot=self.players[p].spot)
                    if succeeded:
                        inner_event = ['SUCCESS', Action.SPOT_ON, self.players[p].name]
                        self.log_event(inner_event)
                        for loser in losers:
                            loser.lose_die()
                        round_cont = False
                        break
                    else:  # Spot-on FAILURE
                        inner_event = ['FAILURE', Action.SPOT_ON, self.players[p].name]
                        self.log_event(inner_event)
                        losers[0].lose_die()
                        self.round_loser = losers[0]
                        round_cont = False
                        break
            if Constants.DEBUG and self._logging:
                self.game_log_file.write('End of for loop\n')

        if self._logging:
            self.game_log_file.write('Broke out of while round_cont loop\n')
        if Constants.DEBUG:
            for player in self.players:
                self._emit('debug', msg=f'{player.name} has {player.num_dice} dice')
        removed_players = self._eliminate_players()
        for player in removed_players:
            self._emit('player_eliminated', player_name=player.name, spot=player.spot)

        self.count_dice()

        if self.num_players < 2:
            self._emit('game_won', winner_name=self.players[0].name)
            self.game_status = False
        else:
            self._emit('round_summary', num_players=self.num_players, tot_num_dice=self.tot_num_dice)

        if Constants.DEBUG and self.round_num > self.max_rounds:
            self._emit('debug', msg='Max rounds reached. Ending game...')
            self.game_status = False

        self._reorder_for_next_round()

        return self.game_status

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
            self.print_error('log_events', e)

    def log_event(self, event):
        '''Adds entry to game log for analysis by developer.'''
        self.round_events.appendleft(event)
        self.event_counter += 1
        if not self._logging:
            return
        try:
            if isinstance(event, TurnResult):
                event_w_cnt = ["#" + str(self.event_counter), str(event.bid), str(event.action), event.player_name]
                self.game_log_file.write(str(event_w_cnt) + '\n')
            elif isinstance(event, list):
                event_w_cnt = ["#" + str(self.event_counter)] + event
                self.game_log_file.write(str(event_w_cnt) + '\n')
            elif isinstance(event, str):
                event_string = '#' + str(self.event_counter) + ' ' + event
                self.game_log_file.write(event_string + '\n')
        except Exception as e:
            self.print_error('log_event')

    def close(self) -> None:
        """Close the log file if one was opened."""
        if self._logging and self.game_log_file:
            self.game_log_file.close()
            self.game_log_file = None

    def __enter__(self) -> 'LiarsDiceGame':
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
            return (True, [p for p in self.players if p.name != caller.name])
        return (False, [caller])

    def _eliminate_players(self) -> list:
        """Removes zero-dice players from self.players; marks eliminated; updates num_players.
        Returns removed list (caller handles printing and game_status)."""
        to_remove = [p for p in self.players if p.num_dice == 0]
        for player in to_remove:
            player.eliminated = True
            if Constants.DEBUG and self._logging:
                self.game_log_file.write(
                    f'{player.name} is being removed from the player array')
            self.players.remove(player)
        self.num_players = len(self.players)
        return to_remove

    def _reorder_for_next_round(self) -> None:
        """Moves self.round_loser to front of self.players if they are still in the game."""
        if self.round_loser is not None and self.round_loser in self.players:
            self.players.remove(self.round_loser)
            self.players.insert(0, self.round_loser)
            self.round_loser = None
