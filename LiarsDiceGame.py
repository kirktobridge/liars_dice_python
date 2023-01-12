import time
import os
import sys
import random
import Constants
from Player import Player
from collections import deque, Counter
import colorama
from colorama import Fore, Back, Style

# class for the game object
# 5 dice to start


class LiarsDiceGame:

    def __init__(self, num_players, max_rounds=Constants.MAX_ROUNDS):
        if Constants.DEBUG:
            print(Fore.MAGENTA + Style.DIM + '<i> Game Object Intitalized')
        self.num_players = num_players
        self.max_rounds = max_rounds
        self.round_num = 1
        self.players = []
        self.prev_action = ''
        self.game_status = True
        self.round_rolls = []
        # TODO
        # you can't bid the same face and count in a round
        # usually (or always?) safest: bid without raising. is raising always more risky? perhaps
        # then maybe don't raise unless you there are no face-count combinations left to play at the current count
        self.game_log = []
        self.tot_num_dice = 0
        self.event_counter = 0
        self.round_events = deque()

    def print_error(self, func_name, e=None):
        log_string = (Fore.MAGENTA +
                      f'Exception caught in {func_name}! - ') + str(e)
        print(Style.DIM + log_string)
        self.log_event(log_string)
        fname = os.path.split(sys.exc_info()[2].tb_frame.f_code.co_filename)[1]
        print(Fore.MAGENTA + Style.DIM + str(sys.exc_info()
              [1]), fname, sys.exc_info()[2].tb_lineno)

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
            self.round_rolls.extend(p0.dice)
        self.log_event([[-1, -1], 'DICE ROLL', 'SYS'])
        # TODO
        print(Fore.CYAN + '<i> Dice Rolled')
        # TODO we are gonna have to change this entire loop
        # the players do go in order, but the round doesn't end until there is a bid or a challenge
        # also the order can change
        # solution- wrap for in while True, rearrange player array when we break out of for loop
        round_cont = True
        loser_index = -99
        while round_cont:
            for p in range(0, self.num_players):
                print(
                    f'<*> Round {self.round_num}: {self.players[p].name}\'s Turn')
                time.sleep(Constants.PAUSE)
                # create references to previous event in the round (previous turn actions)
                prev_event = self.round_events[0]
                prev_action = prev_event[1]
                try:
                    if prev_action == 'DICE ROLL':
                        self.log_event(
                            [[-1, -1], Constants.ACTIONS[0], 'SYS'])
                    else:
                        prev_player_nm = prev_event[2]
                        if prev_action == Constants.ACTIONS[1] or prev_action == Constants.ACTIONS[2]:
                            prev_bid = prev_event[0]
                            prev_bid_cnt = prev_bid[0]
                            prev_bid_face = prev_bid[1]
                except Exception as e:
                    self.print_error(
                        'process_round: prev_event assignment', e)
                    continue
                # player takes turn, output (bid, if any) and action are recorded
                cur_event = [None] * 3
                try:
                    # Provide player list of round's events so far, and the number
                    # of other dice remaining
                    cur_event = self.players[p].take_turn(
                        self.round_events, self.count_dice()-self.players[p].num_dice)
                    self.log_event(cur_event)
                    # bid stored in cur_event[0]
                    # action stored in cur_event[1]
                    if cur_event[1] == Constants.ACTIONS[5]:
                        raise Exception("Blank new_action")

                    # player name stored in cur_event[2]

                except Exception as e:
                    self.print_error('process_round: take_turn call', e)
                    cur_event[0] = [-1, -1]
                    cur_event[1] = 'EXCEPTION'
                    cur_event[2] = self.players[p].name
                    self.log_event(cur_event)
                    self.log_events(self.round_events)
                    continue

                # TODO for spot on and challenge:
                # if someone loses a die, they go first in the next round?

                # Process CHALLENGE action
                if cur_event[1] == Constants.ACTIONS[3]:
                    print(
                        Fore.WHITE + f'<!> Player {self.players[p]} has challenged the previous bid of {prev_bid_cnt} {prev_bid_face}s made by Player {prev_player_nm}!')
                    self.report_rolls()
                    # Challenge SUCCESS
                    if self.round_rolls.count(prev_bid_face) + self.round_rolls.count(1) < prev_bid_cnt:
                        print(Fore.WHITE)  # TODO print chlg successs
                        inner_event = [True, Constants.ACTIONS[3],
                                       self.players[p].name]
                        self.log_event(inner_event)
                        loser_index = p-1
                        self.players[loser_index].lose_die()
                        round_cont = False
                        # refactor this later: process_challenge()
                        break
                    # Challenge FAILURE
                    elif self.round_rolls.count(prev_bid_face) >= prev_bid_cnt:
                        # TODO print chlg fail
                        inner_event = [False, Constants.ACTIONS[3],
                                       self.players[p].name]
                        self.log_event(inner_event)
                        self.players[p].lose_die()
                        loser_index = p
                        round_cont = False
                        break

                # Process SPOT ON action
                if cur_event[1] == Constants.ACTIONS[4]:
                    print(
                        Fore.WHITE +
                        f'<!> {self.players[p]} has called \'SPOT ON\' on the previous bid of {prev_bid_cnt} {prev_bid_face}s made by Player {prev_player_nm}!'
                    )
                    # Spot-on SUCCESS
                    if self.round_rolls.count(prev_bid_face) + self.round_rolls.count(1) == prev_bid_cnt:
                        print(Fore.CYAN +
                              '<!> SPOT ON! Everyone else loses a die!')
                        for p1 in self.players:
                            if p1.name != self.players[p].name:
                                p1.lose_die()
                        round_cont = False
                        # TODO loser_index?
                        break

                    else:  # Spot-on FAILURE
                        if self.players[p].spot == 'HUMAN':
                            print(
                                Fore.BLUE + '<!> Sorry, that bid wasn\'t spot on.\n<i> You will lose a die.')

                        elif self.players[p].spot == 'CPU':
                            print(Fore.CYAN +
                                  f'{self.players[p].name} lost their spot on call!')

                        self.players[p].lose_die()
                        loser_index = p
                        round_cont = False
                        break
                    '''END OF WHILE ROUND_CONT LOOP'''

        ''' POST-ROUND TASKS
        - Process eliminations
        - Rearrange player array TODO
        - Cap rounds if debugging '''

        # Eliminate players who now have zero dice remaining
        if self.players[p].num_dice == 0:
            if self.players[p].spot == 'HUMAN':
                print(Fore.BLUE + Style.BRIGHT +
                      f'<X> {self.players[p].name}, you have been eliminated from the game!')
                if Constants.MULTIPLAYER_ON:
                    self.game_status = False  # game over, human eliminated
            else:
                print(Fore.WHITE +
                      f'<X> {self.players[p].name} has been eliminated from the game!')
            try:
                self.players.pop(p)
                if loser_index == p:
                    loser_index = -99
            except Exception as e:
                print(e)
            self.num_players -= 1
            self.count_dice()
            if self._num_players < 2:
                print(
                    f'<!> There is only one player remaining. {self.players[p].name} has won the game!')
                self.game_status = False
            else:
                print(
                    f'<!> There are {self.num_players} players and a total of {self.tot_num_dice} dice remaining.')

        # Impose max rounds
        if Constants.DEBUG and self.round_num > self.max_rounds:
            print(Fore.CYAN + '<!> Max rounds reached. Ending game...')
            self.game_status = False

        # TODO rearrange Player array
        # well, we don't actually have to rearrange it.
        # we need to get the for loop to start there, though

        return self.game_status

    def log_events(self, events):
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
        # NEW NEW TODO
        self.round_events.appendleft(event)
        self.event_counter += 1
        try:
            if isinstance(event, list):
                event_w_cnt = []
                event_w_cnt.insert(0, "#" + str(self.event_counter))
                event_w_cnt.extend(event)
                self.game_log.append(event_w_cnt)
            elif isinstance(event, str):
                self.game_log.append(
                    '#' + str(self.event_counter) + ' ' + event)
            # if Constants.DEBUG:
            #     print(Fore.MAGENTA + Style.DIM + '<!> Event Logged')
        except Exception as e:
            self.print_error('log_event')

    def report_rolls(self):
        print(Fore.CYAN + '<i> Lifting cups:\n')
        try:
            # TODO roll_freq = Counter(self.round_rolls)
            for p in self.players:
                output = Fore.CYAN + f'<i> {p.name}\'s rolls: '
                player_roll_freq = Counter(p.dice)
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
            # TODO return roll_freq
        except Exception as e:
            self.print_error('report_rolls')
            # TODO return None
