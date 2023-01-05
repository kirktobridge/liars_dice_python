# class for Player object
# move to Constants file
from statistics import mode
from collections import deque
import random
import Constants
import colorama
from colorama import Fore, Back, Style
from scipy import binom

class Player:

    def __init__(self, name, spot='CPU', eliminated=False, num_dice = Constants.MAX_NUM_DICE):
        self.name = name
        if spot == 'CPU':
            print(Fore.GREEN + Style.DIM + f'<i> Player {self.name} has been created.')
        elif spot == 'HUMAN':
            print(Fore.BLUE + f'<i> Player {self.name} has been created.')
        self.num_dice = num_dice
        self.eliminated = eliminated
        self.dice = [0,0,0,0,0]
        self.rolls_mode = 0
        self.wild_count = 0
        self.spot = spot
        self.addl_guessed_cnt = 0
        self.bid = []

    def lose_die(self):
        self.dice[self.num_dice-1] = 0
        self.num_dice -= 1

    def add_die(self):
        self.num_dice += 1

    def roll(self):
        for d in range(0,self.num_dice):
            self.dice[d] = random.randint(1,6)
           

    def bid(self, raise_bid=False, prev_bids=None): # will return an array containing: number of dice, denomination

        if self.spot == 'CPU':
            if raise_bid == True: # copies previous bid, raises count by 1
                prev_bid = prev_bids[len(prev_bids)-1]
                prev_bid_count = prev_bid[0]
                prev_bid_face = prev_bid[1]
                new_bid = [prev_bid_count + 1, prev_bid_face]
            else:
                cnt_bid_safe = self.rolls_mode + self.wild_count
                # best bid is a function of how large count of mode is plus count of ones
                # TODO but the bid's count must be higher than the previous, 
                # OR the bidded face value must be not previously used in the round
                # TODO how to determine additional guessed count?
                new_bid = [cnt_bid_safe + self.addl_guessed_cnt, self.rolls_mode] # ex. two 1's, two 3's: bid 4 3's
        elif self.spot == 'HUMAN': # TODO Human-controlled behavior
            bid_count = input(Fore.BLUE + f'<?> {self.name}, please enter bid size: ')
            bid_face = input(Fore.BLUE + f'<?> {self.name}, please enter the number of the face you are bidding on: ')
            new_bid = [bid_count,bid_face]   
        return new_bid

    def take_turn(self, prev_event, tot_other_dice):
        # TODO form and react to impressions of other players (trust score, expected bids, expected count of ones based on bids)
        # for each turn record

        # i: compile stats of other bids this round
        # ii: add in player's stats, then calculate key statistical values
        # iii: return action and any output array (like a bid)
        # ----------------------------------------------------------------
        # 
        # (0) HANDLED BY GAME CLASS - ROLL DICE (should happen at beginning of round with other 
        # players, not on turn)
        #  
        # (1) Read Previous Player's Action: from stack (prev_events) given by LiarsDiceGame
        #
        prev_action = prev_event[1] # pulls value of new_action from previous turn
        #
        # (2) Statistical Analysis: Find the mode of our roll and our count of ones.
        # Use this information, along with the number of other players' dice,
        # to calculate the probability of the previous bid being true. This can be done
        # using a scipy function to calculate the binomial cumulative probability.
        #
        self.rolls_mode = mode(self.dice) # what is our most common roll?
        
        # 
        if prev_action == Constants.ACTIONS[2]: # If previous player bid
            model = binom(n=tot_other_dice, p=2/6) # set up binomial model
            # ns and 1s count as ns
            prev_bid_cnt = prev_action[0][0]
            needed_cnt = prev_bid_cnt - self.dice.count(prev_bid_cnt) - self.count_ones()
            # needed count is how many dice with the desired face we need for the previous bid
            # to be true, factoring in the roll we already know the outcome for (ours)
            if needed_cnt <= 0:
                # negative number means we already have this bid
                cumulative_probability = 1
                # TODO evaluate spot on conditions?
            else:
                cumulative_probability = 1 - model.cdf(needed_cnt-1) # p(x >= y) = 1 - p(x =< y-1)
                spot_on_probability = model.pmf(prev_bid_cnt)
                # TODO compare these probabilities and decide if we should 'spot on'
                # TODO compare these probabilities to probability of each possible raised bid
                # may need to pass all previous events instead of just the one previous event...
                # TODO what do we do when nothing we want to say or can say is likely?
            
            # TODO calculate probability of bid

            # TODO: bid new face, raise bid, challenge, or spot on
            new_action = None # TODO

        elif prev_action == None:
            pass # TODO what behavior should we instigate if we are the first player?
        # we have to bid, can't challenge or spot on
        output = None # TODO
        return [output, new_action, self.dice] # TODO bid or challenge previous bid
        

    def challenge(self, p):
        if self.spot == 'CPU':
            pass # TODO AI behavior
        elif self.spot == 'HUMAN':
            pass # TODO Human behavior
    
    def count_ones(self):
        self.wild_count = self.dice.count(1)
        return self.wild_count