import time
import os
import sys
from datetime import datetime
import random
import Constants
from Player import Player
from collections import deque, Counter
import colorama
from colorama import Fore, Back, Style
from models import Action, Bid, TurnResult

# class for the game object
# 5 dice to start


class LiarsDiceGame:

    def __init__(self, num_players, max_rounds=Constants.MAX_ROUNDS):
        if Constants.DEBUG:
            print(Fore.MAGENTA + Style.DIM + '<i> Game Object Intitalized')
        self.num_players = num_players
        self.max_rounds = max_rounds
        self.round_num = 0
        self.players = []
        self.prev_action = ''
        self.game_status = True
        self.round_rolls = []
        self.game_log = []
        self.game_log_file = open(
            f'{datetime.now().strftime("%H_%M_%S")}_LiarsDiceGame_Log.txt', 'w+')
        self.tot_num_dice = 0
        self.event_counter = 0
        self.round_events = deque()
        self.round_loser = None

    def print_error(self, func_name, e=None):
        log_string = (Fore.MAGENTA +
                      f'Exception caught in {func_name}! - ') + str(e)
        print(Style.DIM + log_string)

        fname = os.path.split(sys.exc_info()[2].tb_frame.f_code.co_filename)[1]
        log_string2 = str(sys.exc_info()
                          [1]) + str(fname) + str(sys.exc_info()[2].tb_lineno)
        print(Fore.MAGENTA + Style.DIM + log_string2)

        self.log_event(log_string + log_string2)

    def add_player(self, p):
        try:
            self.players.append(p)
            if Constants.DEBUG:
                print(Fore.MAGENTA + Style.DIM +
                      f'<i> Player {p.name} appended to game player list.')
        except Exception as e:
            self.print_error('add_player')

    def count_dice(self):
        try:
            self.tot_num_dice = 0  # reset count
            for p in self.players:
                self.tot_num_dice += p.num_dice
                # TODO map()?
            return self.tot_num_dice
        except Exception as e:
            self.print_error('count_dice')
            return -1

    def process_round(self):
        '''PRE-ROUND TASKS
        - Increment Round Counter
        - Notify User
        - Log events
        - Roll dice'''
        # Increment round counter
        self.round_num += 1
        print(Fore.WHITE + f'<!> Round {self.round_num} Begin')
        self.round_events.clear()
        self.log_event([[-1, -1], f'RND{self.round_num}', 'SYS'])
        time.sleep(Constants.PAUSE)
        print(Fore.CYAN + '<i> Rolling Dice...')
        time.sleep(Constants.PAUSE)
        self.round_rolls.clear()
        # Roll and record players' dice
        for p0 in self.players:
            p0.roll()
            self.round_rolls.extend(p0.dice[:p0.num_dice])
        # DICE ROLL is intentionally kept as a raw list sentinel (not a TurnResult) because
        # it has no Action enum equivalent and is only ever compared here before being
        # replaced by TurnResult(Action.START). Phase 2/3 should convert this if DICE ROLL
        # needs to become a first-class event type.
        self.log_event([[-1, -1], 'DICE ROLL', 'SYS'])
        print(Fore.CYAN + '<i> Dice Rolled')
        round_cont = True
        tot_dice = self.count_dice()
        while round_cont:
            for p in range(0, self.num_players):
                round_msg = ''
                if Constants.DEBUG == True:
                    print(self.players[p].name)
                    print(self.players[p].dice[:self.players[p].num_dice])
                    round_msg = str(self.players[p].num_dice) + 'dice '
                round_msg += f'<*> Round {self.round_num}: {self.players[p].name}\'s Turn'
                print(round_msg)
                time.sleep(Constants.PAUSE)
                # create references to previous event in the round (previous turn actions)
                prev_event = self.round_events[0]
                try:
                    if isinstance(prev_event, list) and prev_event[1] == 'DICE ROLL':
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
                # player takes turn, output (bid, if any) and action are recorded
                cur_event = TurnResult(None, Action.NONE, '')
                try:
                    if Constants.DEBUG:
                        self.game_log_file.write(
                            f'Passing prev_event {self.round_events[0]} and action {self.round_events[0].action} to {self.players[p].name}. \nThey have dice: {self.players[p].dice[:self.players[p].num_dice]}.\n')
                    cur_event = self.players[p].take_turn(
                        self.round_events, tot_dice-self.players[p].num_dice)
                    self.log_event(cur_event)
                    if cur_event.action == Action.NONE:
                        raise Exception("Blank new_action")
                except Exception as e:
                    self.print_error('process_round: take_turn call', e)
                    cur_event = TurnResult(None, Action.NONE, self.players[p].name)
                    self.log_event(cur_event)
                    self.log_events(self.round_events)
                    continue

                # Process BID/RAISE action
                if cur_event.action == Action.BID:
                    print(
                        Fore.WHITE + f'<!> {self.players[p].name} bids {cur_event.bid.count} {cur_event.bid.face}\'s.')
                    time.sleep(Constants.PAUSE)
                # Process RAISE action
                elif cur_event.action == Action.RAISE:
                    print(
                        Fore.WHITE + f'<!> {self.players[p].name} raises the bid to {cur_event.bid.count} {cur_event.bid.face}\'s.')
                    time.sleep(Constants.PAUSE)
                # Process CHALLENGE action
                elif cur_event.action == Action.CHALLENGE:
                    print(
                        Fore.WHITE + f'<!> {self.players[p].name} has challenged the previous bid of {prev_bid_cnt} {prev_bid_face}s made by {prev_player_nm}!')
                    self.report_rolls()
                    time.sleep(Constants.PAUSE)
                    round_cont = False
                    prev_bid_obj = Bid(prev_bid_cnt, prev_bid_face)
                    succeeded, loser = self._resolve_challenge(prev_bid_obj, self.players[p], self.players[p-1])
                    prev_bid_actual_cnt = self.round_rolls.count(prev_bid_face)
                    actual_ones_cnt = self.round_rolls.count(1)
                    if succeeded:
                        output = f'{self.players[p].name}\'s challenge succeeds- there are only {prev_bid_actual_cnt} {prev_bid_face}\'s'
                        if actual_ones_cnt > 0 and prev_bid_face != 1:
                            output += f' and {actual_ones_cnt} 1\'s!'
                        else:
                            output += '!'
                        print(Fore.WHITE + output)
                        time.sleep(Constants.PAUSE)
                        inner_event = ['SUCCESS', Action.CHALLENGE, self.players[p].name]
                        self.log_event(inner_event)
                    else:
                        output = Fore.WHITE + \
                            f'{self.players[p].name}\'s challenge fails- there are actually {prev_bid_actual_cnt} {prev_bid_face}\'s'
                        if actual_ones_cnt > 0:
                            output += f' and {actual_ones_cnt} 1\'s!'
                        else:
                            output += '!'
                        print(output)
                        time.sleep(Constants.PAUSE)
                        inner_event = ['FAILURE', Action.CHALLENGE, self.players[p].name]
                        self.log_event(inner_event)
                    self.round_loser = loser
                    loser.lose_die()
                    break
                # TODO appears players are not being eliminated

                # Process SPOT ON action
                if cur_event.action == Action.SPOT_ON:
                    print(
                        Fore.WHITE +
                        f'<!> {self.players[p].name} has called \'SPOT ON\' on the previous bid of {prev_bid_cnt} {prev_bid_face}s made by Player {prev_player_nm}!'
                    )
                    time.sleep(Constants.PAUSE)
                    prev_bid_obj = Bid(prev_bid_cnt, prev_bid_face)
                    succeeded, losers = self._resolve_spot_on(prev_bid_obj, self.players[p])
                    if succeeded:
                        print(Fore.CYAN + '<!> SPOT ON! Everyone else loses a die!')
                        inner_event = ['SUCCESS', Action.SPOT_ON, self.players[p].name]
                        self.log_event(inner_event)
                        time.sleep(Constants.PAUSE)
                        for loser in losers:
                            loser.lose_die()
                        round_cont = False
                        break
                    else:  # Spot-on FAILURE
                        if self.players[p].spot == 'HUMAN':
                            print(
                                Fore.BLUE + '<!> Sorry, that bid wasn\'t spot on.\n<i> You will lose a die.')
                        elif self.players[p].spot == 'CPU':
                            print(Fore.CYAN +
                                  f'<!> {self.players[p].name} lost their spot on call!')
                        time.sleep(Constants.PAUSE)
                        inner_event = ['FAILURE', Action.SPOT_ON, self.players[p].name]
                        self.log_event(inner_event)
                        losers[0].lose_die()
                        self.round_loser = losers[0]
                        round_cont = False
                        break
            ''' END OF FOR-PLAYER LOOP'''
            if Constants.DEBUG:
                self.game_log_file.write('End of for loop\n')

        self.game_log_file.write('Broke out of while round_cont loop\n')
        ''' END OF WHILE ROUND_CONT LOOP'''
        ''' POST-ROUND TASKS
        - Process eliminations
        - Rearrange player array
        - Cap rounds if debugging '''

        # Eliminate players who now have zero dice remaining
        if Constants.DEBUG == True:
                for player in self.players:
                    print(f'{player.name} has {player.num_dice} dice')
        removed_players = self._eliminate_players()
        for player in removed_players:
            if player.spot == 'HUMAN':
                print(Fore.BLUE + Style.BRIGHT +
                      f'<X> {player.name}, you have been eliminated from the game!')
                time.sleep(Constants.PAUSE)
                if not Constants.MULTIPLAYER_ON:
                    self.game_status = False  # game over, human eliminated if in single-human mode
            else:
                print(Fore.WHITE +
                      f'<X> {player.name} has been eliminated from the game!')
                time.sleep(Constants.PAUSE)

        self.count_dice()

        # Report state of game or end it
        if self.num_players < 2:
            print(
                f'<!> There is only one player remaining. {self.players[0].name} has won the game!')
            time.sleep(Constants.PAUSE)
            self.game_status = False
        else:
            print(
                f'<!> There are {self.num_players} players and a total of {self.tot_num_dice} dice remaining.')
            time.sleep(Constants.PAUSE)

        # Impose max rounds
        if Constants.DEBUG and self.round_num > self.max_rounds:
            print(Fore.CYAN + '<!> Max rounds reached. Ending game...')
            self.game_status = False

        # Rearrange Player array so loser goes first next round
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
        try:
            if isinstance(event, TurnResult):
                event_w_cnt = ["#" + str(self.event_counter), str(event.bid), str(event.action), event.player_name]
                self.game_log.append(event_w_cnt)
                self.game_log_file.write(str(event_w_cnt) + '\n')
            elif isinstance(event, list):
                event_w_cnt = []
                event_w_cnt.insert(0, "#" + str(self.event_counter))
                event_w_cnt.extend(event)
                self.game_log.append(event_w_cnt)
                self.game_log_file.write(str(event_w_cnt) + '\n')
            elif isinstance(event, str):
                event_string = '#' + str(self.event_counter) + ' ' + event
                self.game_log.append(event_string)
                self.game_log_file.write(event_string + '\n')

            # if Constants.DEBUG:
            #     print(Fore.MAGENTA + Style.DIM + '<!> Event Logged')
        except Exception as e:
            self.print_error('log_event')

    def report_rolls(self):
        print(Fore.CYAN + '<i> Lifting cups:\n')
        try:
            for p in self.players:
                output = Fore.CYAN + f'<i> {p.name}\'s rolls: '
                player_roll_freq = Counter(p.dice[:p.num_dice])
                loop_cnt = 0
                for d in sorted(player_roll_freq, key=player_roll_freq.get):
                    output += str(player_roll_freq[d]) + ' ' + str(d)
                    if player_roll_freq[d] > 1:
                        output += '\'s'
                    loop_cnt += 1
                    if loop_cnt == len(player_roll_freq):
                        output += "."
                    elif loop_cnt == p.num_dice-1:
                        output += ", and "
                    else:
                        output += ", "
                print(output)
        except Exception as e:
            self.print_error('report_rolls')

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
            if Constants.DEBUG:
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
