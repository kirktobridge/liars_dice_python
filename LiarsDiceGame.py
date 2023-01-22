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
        self.loser_index = -99

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
        print(Fore.CYAN + '<i> Dice Rolled')
        round_cont = True
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
                    if Constants.DEBUG:
                        self.game_log_file.write(
                            f'Passing prev_event {self.round_events[0]} and action {self.round_events[0][1]} to {self.players[p].name}. \nThey have dice: {self.players[p].dice}.\n')
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

                # Process CHALLENGE action
                if cur_event[1] == Constants.ACTIONS[3]:
                    print(
                        Fore.WHITE + f'<!> Player {self.players[p].name} has challenged the previous bid of {prev_bid_cnt} {prev_bid_face}s made by Player {prev_player_nm}!')
                    self.report_rolls()
                    # Challenge SUCCESS
                    prev_bid_actual_cnt = self.round_rolls.count(prev_bid_face)
                    actual_ones_cnt = self.round_rolls.count(1)
                    if prev_bid_actual_cnt + actual_ones_cnt < prev_bid_cnt:
                        output = Fore.WHITE + \
                            self.players[p].name + \
                            f'/\'s challenge succeeds- there are only {prev_bid_actual_cnt} {prev_bid_face}\'s)'
                        if actual_ones_cnt > 0:
                            output += f' and {actual_ones_cnt} 1\'s!'
                        else:
                            output += '!'
                        print(output)
                        inner_event = ['SUCCESS', Constants.ACTIONS[3],
                                       self.players[p].name]
                        self.log_event(inner_event)
                        loser_index = p-1
                        self.players[loser_index].lose_die()
                        round_cont = False
                        # refactor this later: process_challenge()
                        break
                    # Challenge FAILURE
                    elif self.round_rolls.count(prev_bid_face) >= prev_bid_cnt:
                        output = Fore.WHITE + \
                            self.players[p].name + \
                            f'/\'s challenge fails- there are actually {prev_bid_actual_cnt} {prev_bid_face}\'s)'
                        if actual_ones_cnt > 0:
                            output += f' and {actual_ones_cnt} 1\'s!'
                        else:
                            output += '!'
                        inner_event = ['FAILURE', Constants.ACTIONS[3],
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
                        inner_event = ['SUCCESS', Constants.ACTIONS[4],
                                       self.players[p].name]
                        self.log_event(inner_event)
                        for p1 in self.players:
                            if p1.name != self.players[p].name:
                                p1.lose_die()
                        round_cont = False
                        break

                    else:  # Spot-on FAILURE
                        if self.players[p].spot == 'HUMAN':
                            print(
                                Fore.BLUE + '<!> Sorry, that bid wasn\'t spot on.\n<i> You will lose a die.')

                        elif self.players[p].spot == 'CPU':
                            print(Fore.CYAN +
                                  f'{self.players[p].name} lost their spot on call!')

                        inner_event = ['FAILURE', Constants.ACTIONS[4],
                                       self.players[p].name]
                        self.log_event(inner_event)
                        self.players[p].lose_die()
                        loser_index = p
                        round_cont = False
                        break
                    '''END OF WHILE ROUND_CONT LOOP'''

        ''' POST-ROUND TASKS
        - Process eliminations
        - Rearrange player array
        - Cap rounds if debugging '''

        # Eliminate players who now have zero dice remaining
        for p1 in range(0, self.num_players):

            if self.players[p1].num_dice == 0:

                if self.players[p1].spot == 'HUMAN':
                    print(Fore.BLUE + Style.BRIGHT +
                          f'<X> {self.players[p1].name}, you have been eliminated from the game!')
                    if Constants.MULTIPLAYER_ON:
                        self.game_status = False  # game over, human eliminated
                else:
                    print(Fore.WHITE +
                          f'<X> {self.players[p1].name} has been eliminated from the game!')
                try:
                    self.players.pop(p)
                    if loser_index == p:
                        loser_index = -99
                except Exception as e:
                    print(e)
                self.num_players -= 1
                self.count_dice()
            # end of for loop

        # Report state of game or end it
        if self._num_players < 2:
            print(
                f'<!> There is only one player remaining. {self.players[p1].name} has won the game!')
            self.game_status = False
        else:
            print(
                f'<!> There are {self.num_players} players and a total of {self.tot_num_dice} dice remaining.')

        # Impose max rounds
        if Constants.DEBUG and self.round_num > self.max_rounds:
            print(Fore.CYAN + '<!> Max rounds reached. Ending game...')
            self.game_status = False

        # Rearrange Player array
        if loser_index != -99:
            self.players.insert(0, self.players.pop[loser_index])
            loser_index = -99

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
        '''Adds entry to game log for analysis by developer.'''
        self.round_events.appendleft(event)
        self.event_counter += 1
        try:
            if isinstance(event, list):
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
        except Exception as e:
            self.print_error('report_rolls')
