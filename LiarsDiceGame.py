import random
import Constants
from Player import Player
from collections import deque, Counter
import colorama
from colorama import Fore, Back, Style

# class for the game object
# 5 dice to start

class LiarsDiceGame:
    
    def __init__(self, num_players, max_rounds = 1000):
        print(Fore.GREEN + Style.DIM + '<i> Game Object Intitalized')
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
    
    def add_player(self, p):
        self.players.append(p)

    def count_dice(self):
        self.tot_num_dice = 0 # reset count
        for p in self.players:
            self.tot_num_dice += p.num_dice
        return self.tot_num_dice

    def process_round(self):
        print(Fore.WHITE + f'<!> Round {self.round_num} Begin')
        self.log_event(Fore.WHITE + f'<!> Round {self.round_num} Begin')
        self.log_event('Dice Roll')
        print(Fore.CYAN + '<!> Rolling Dice...')
        for p in range(0,self.num_players):
            p.roll()
        print(Fore.CYAN + '<i> Dice Rolled')
        for p in range(0,self.num_players):
            print(f'<*> Round {self.round_num}: {self.players[p].name}\'s Turn')
            prev_event = self.round_events.peek()
            # player takes turn, output (bid, if any) and action are recorded
            try:
                cur_event = self.players[p].take_turn(self.round_events, self.count_dice())
                # bid stored in cur_event[0]
                # action stored in cur_event[1]
                # dice rolls stored in cur_event[2]
            except Exception as e:
                print(e)
            cur_event.extend(self.players[p].name) # player name stored in cur_event[3]
            self.round_rolls.extend(cur_event[2]) # record round rolls for spot-ons and challenges

            # TODO process challenge action
            if cur_event[1] == Constants.ACTIONS[3]:
                print(Fore.WHITE + f'<!> Player {self.players[p]} has challenged the previous bid of {prev_event[0][1]} {prev_event[0][1]}s made by Player {prev_event[3]}!')
                print(Fore.CYAN + '<!> Lifting cups: \n')
                for p in self.players:
                    die_freq = Counter(p.dice)
                    print(f'Player {p.name}: ')
                    # TODO print player dice freq counts

            # TODO process spot-on action


            self.round_events.append(cur_event)

            if self.players[p].num_dice == 0:
                print(f'<X> Player {self.players[p].name} has been eliminated from the game!')
                self.num_players -= 1
                self.count_dice()
                print (f'<X> There are {self.num_players} players and a total of {self.tot_num_dice} dice remaining.')
                self.players.pop(p)

        self.log_event(self.round_events)
        self.round_events = []
        return self.game_status
    
    def log_event(self, event):
        self.game_log.append(event)