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
        if Constants.DEBUG == True:
            print(Fore.MAGENTA + Style.DIM + '<i> Game Object Intitalized')
        self.num_players = num_players
        self.max_rounds = max_rounds
        self.round_num = 1
        self.players = []
        self.round_events = deque()
        self.prev_action = ''
        self.game_status = True
        self.round_rolls = []
        # TODO
        # you can't bid the same face and count in a round
        # usually (or always?) safest: bid without raising. is raising always more risky? perhaps
        # then maybe don't raise unless you there are no face-count combinations left to play at the current count
        self.game_log = []
        self.tot_num_dice = 0

    @staticmethod
    def print_error(func_name):
        print(Fore.MAGENTA + Style.DIM +
              f'Exception caught in {func_name}!')
        fname = os.path.split(sys.exc_info()[2].tb_frame.f_code.co_filename)[1]
        print(Fore.MAGENTA + Style.DIM + str(sys.exc_info()
              [1]), fname, sys.exc_info()[2].tb_lineno)

    def add_player(self, p):
        try:
            self.players.append(p)
            if Constants.DEBUG == True:
                print(Fore.MAGENTA + Style.DIM +
                      f'Player {p.name} appended to game player list.')
        except Exception as e:
            LiarsDiceGame.print_error('add_player')

    def count_dice(self):
        try:
            self.tot_num_dice = 0  # reset count
            for p in self.players:
                self.tot_num_dice += p.num_dice
            return self.tot_num_dice
        except Exception as e:
            LiarsDiceGame.print_error('count_dice')
            return -1

    def process_round(self):
        print(Fore.WHITE + f'<!> Round {self.round_num} Begin')
        if self.round_num == 1:
            self.round_events.append([[0, 0], 'RND1', [], 'SYS'])
        time.sleep(Constants.PAUSE)
        self.log_event(f'<!> Round {self.round_num} Begin')

        self.log_event('Dice Roll')
        print(Fore.CYAN + '<i> Rolling Dice...')
        time.sleep(Constants.PAUSE)
        for p in self.players:
            p.roll()
            # record round rolls for spot-ons and challenges
            self.round_rolls.extend(p.dice)

        print(Fore.CYAN + '<i> Dice Rolled')
        for p in range(0, self.num_players):
            print(
                f'<*> Round {self.round_num}: {self.players[p].name}\'s Turn')
            time.sleep(Constants.PAUSE)
            try:
                if len(self.round_events) == 0:
                    prev_event = None
                else:
                    prev_event = self.round_events[0]
                    prev_action = prev_event[1]
                    prev_player_nm = prev_event[2]
                    if prev_action == Constants.ACTIONS[1] or prev_action == Constants.ACTIONS[2]:
                        prev_bid = prev_action[0]
                        prev_bid_cnt = prev_bid[0]
                        prev_bid_face = prev_bid[1]
            except Exception as e:
                LiarsDiceGame.print_error(
                    'process_round: prev_event assignment')
            # player takes turn, output (bid, if any) and action are recorded
            cur_event = [None, None, None]
            try:
                # Provide player list of round's events so far, and the number
                # of other dice remaining
                cur_event = self.players[p].take_turn(
                    self.round_events, self.count_dice()-self.players[p].num_dice)
                # bid stored in cur_event[0]
                # action stored in cur_event[1]
                if cur_event[1] == Constants.ACTIONS[5]:
                    raise Exception("Blank new_action")
                
                # player name stored in cur_event[2]

            except Exception as e:
                cur_event[0] = 'EXCEPTION'
                cur_event.extend(self.players[p].name)
                LiarsDiceGame.print_error('process_round: take_turn call')

            # TODO process challenge action
            if cur_event[1] == Constants.ACTIONS[3]:
                print(
                    Fore.WHITE + f'<!> Player {self.players[p]} has challenged the previous bid of {prev_bid_cnt} {prev_bid_face}s made by Player {prev_player_nm}!')

                round_rolls_freq = self.report_rolls()

            # TODO process spot-on action

            self.round_events.append(cur_event)

            if self.players[p].num_dice == 0:
                print(
                    f'<X> Player {self.players[p].name} has been eliminated from the game!')
                try:
                    self.players.pop(p)
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
        log_stop = len(self.round_events)
        for event in range(0, log_stop):
            self.log_event(self.round_events.popleft())
        self.round_events.clear()
        self.round_num += 1
        if self.round_num > self.max_rounds:
            print(Fore.CYAN + '<!> Max rounds reached. Ending game...')
            self.game_status = False
        return self.game_status

    def log_event(self, event):
        try:
            self.game_log.append(event)
        except Exception as e:
            LiarsDiceGame.print_error('log_event')

    def report_rolls(self):
        print(Fore.CYAN + '<i> Lifting cups:\n')
        try:
            roll_freq = Counter(self.round_rolls)
            for p in self.players:
                die_freq = Counter(p.dice)
                output = Fore.CYAN + f'<i> {p.name}\'s rolls: '
                player_roll_freq = Counter(p.dice)
                for d in player_roll_freq:
                    output += f'{player_roll_freq[d]} {d}\'s'
                    # TODO: fix punctuation behavior
                    # if d == p.num_dice-1:
                    #     output += "."
                    # elif d == p.num_dice-2:
                    #     output += ", and "
                    # else:
                    #     output += ", "
                print(output)
            return roll_freq
        except Exception as e:
            LiarsDiceGame.print_error('report_rolls')
            return None
