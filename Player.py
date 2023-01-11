# class for Player object
# move to Constants file
from statistics import mode
from collections import deque
import time
import random
import Constants
import colorama
from colorama import Fore, Back, Style
from scipy.stats import binom


class Player:

    def __init__(self, name, spot='CPU', eliminated=False, num_dice=Constants.MAX_NUM_DICE):
        '''Constructor for the Player object. Initializes key variables.'''
        self.name = name
        if Constants.DEBUG == True:
            if spot == 'CPU':
                print(Fore.CYAN + Style.DIM +
                      f'<i> Player {self.name} has been created.')
            elif spot == 'HUMAN':
                print(Fore.BLUE + f'<i> Player {self.name} has been created.')
        self.num_dice = num_dice
        self.eliminated = eliminated
        self.dice = [-1] * self.num_dice
        self.rolls_mode = 0
        self.wild_count = 0
        self.mode_count = 0
        self.spot = spot
        self.addl_guessed_cnt = 0
        self.bid = []

    def lose_die(self):
        '''Removes virtual die from the Player object, and updates Player's dice 
        count variable.'''
        self.dice[self.num_dice-1] = -1
        self.num_dice -= 1
        if Constants.DEBUG == True:
            print(Fore.MAGENTA + Style.DIM + f'{self.name} lost a die!')

    def add_die(self):
        '''Adds virtual die to Player's dice inventory.'''
        self.num_dice += 1

    def roll(self):
        '''Generates random values for the Player's held dice between 1 and 6, 
        simulating rolls of a six-sided dice.'''
        for d in range(0, self.num_dice):
            self.dice[d] = random.randint(1, 6)

    @staticmethod
    def grade(p):
        '''Provides a classification for a probability by comparing a percentage to a 
        predetermined set of thresholds found in the Constants file.'''
        grade = 'VERY LOW'
        for k, v in sorted(Constants.PROB_THRESHOLDS.items(), key=lambda x: x[1]):
            if p < v:
                break
            else:
                grade = k
        # further down the line: could make grading dependent on a 'personality' attribute
        # ie each Player will have slightly different risk tolerance levels
        return grade

    def bid(self, bid=[], raise_bid_amt=0):
        '''Takes two optional parameters: the bid, a size 2 array containing the count 
        of dice (size of bid) and the numeric value of the face being bid on; 
        the second parameter raise_bid indicates if the bid should be raised, 
        and if so, by what amount. These parameters are required for CPU players,
        but not needed for human players, as humans will enter their own bids using this
        function. Returns a bid array [count, denomination]'''
        if self.spot == 'CPU':
            if raise_bid_amt != 0:
                bid_count = bid[0]
                bid_face = bid[1]
                new_bid = [bid_count + raise_bid_amt, bid_face]
            else:
                cnt_bid_safe = self.rolls_mode + self.wild_count
                '''best bid is a function of how large count of mode is plus count of ones
                TODO but the bid's count must be higher than the previous,
                OR the bidded face value must be not previously used in the round
                TODO how to determine additional guessed count?'''
                new_bid = [cnt_bid_safe + self.addl_guessed_cnt,
                           self.rolls_mode]  # ex. two 1's, two 3's: bid 4 3's
        elif self.spot == 'HUMAN':  # TODO Human-controlled behavior
            bid_count = input(
                Fore.BLUE + f'<?> {self.name}, please enter bid size: ')
            bid_face = input(
                Fore.BLUE + f'<?> {self.name}, please enter the number of the face you are bidding on: ')
            new_bid = [bid_count, bid_face]
            # TODO should this bidding behavior be moved into take_turn()?
            # TODO input will require exception handling
        return new_bid

    def take_turn(self, prev_events, tot_other_dice):
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
        prev_event = prev_events[0]
        # pulls value of new_action from previous turn
        prev_action = prev_event[1]
        # tot_other_dice = tot_num_dice-self.num_dice
        # (2) Statistical Analysis: Find the mode of our roll and our count of ones.
        # Use this information, along with the number of other players' dice,
        # to calculate the probability of the previous bid being true. This can be done
        # using a scipy function to calculate the binomial cumulative probability.
        #
        # TODO how do we know if we are the first player in the round?
        # check prev_action
        new_action = Constants.ACTIONS[5]
        self.rolls_mode = mode(self.dice)  # what is our most common roll?
        self.mode_count = self.dice.count(self.rolls_mode) + self.count_ones()
        # If previous player bid
        if prev_action == (Constants.ACTIONS[1] or Constants.ACTIONS[2]):
            model = binom(n=tot_other_dice, p=2/6)  # set up binomial model
            # ns and 1s count as ns
            prev_bid = prev_event[0]  # pulls previous turn's bid
            prev_bid_cnt = prev_bid[0]
            prev_bid_face = prev_bid[1]
            face_self_match_cnt = self.dice.count(
                prev_bid_face) + self.count_ones()
            needed_cnt = prev_bid_cnt - face_self_match_cnt
            # needed count is how many dice with the desired face we need for the previous bid
            # to be true, factoring in the roll we already know the outcome for (ours)
            if needed_cnt == 0:

                cumulative_probability = 1
                # TODO evaluate spot on conditions?
            elif needed_cnt < 0:
                # negative number means we can safely raise this bid
                # current philosophy for raising is that we don't want to
                # raise the inherent bid risk for all players (and thus ourselves)
                # more than is necessary,
                # so we only raise by one. However, this behavior could be changed
                # to raise by the maximum safest amount, or the maximum safest amount
                # plus a few risked dice. This risk addition could be a personality
                # attribute of the Player object, perhaps something to randomize (or
                # create a distribution of across the playerset for a game)
                spot_on_probability = 0
                output = self.bid(prev_bid, raise_bid_amt=1)
                new_action = Constants.ACTION[2]

            elif needed_cnt > 0 and face_self_match_cnt > 0:
                # p(x >= y) = 1 - p(x =< y-1)
                cumulative_probability = 1 - model.cdf(needed_cnt-1)
                spot_on_probability = model.pmf(needed_cnt)
                # TODO compare these probabilities and decide if we should 'spot on'
                # TODO compare these probabilities to probability of each possible raised bid
                # may need to pass all previous events instead of just the one previous event...
                # TODO what do we do when nothing we want to say or can say is likely?

        #
        # (3) Decision Making: Evaluate stats and make decision
        #
        # TODO: bid new face, raise bid, challenge, or spot on
            # if previous bid unlikely, challenge
            if Player.grade(cumulative_probability) == 'LOW':
                new_action = Constants.ACTIONS[3]
                output = [-1, -1]

        elif prev_action == Constants.ACTIONS[0]:
            output = [-1, -1]
            # TODO what behavior should we instigate if we are the first player?
            # we have to bid, can't challenge or spot on
            # self.bid()
            new_action = Constants.ACTIONS[1] + \
                ' TODO START BEHAVIOR NOT IMPLEMENTED '
            #
        else:
            output = [-1, -1]
            new_action = Constants.ACTIONS[5] + \
                ' TODO CATCHALL BEHAVIOR NOT IMPLEMENTED'
            # TODO catch-all behavior
            # raise Exception(
            #     Fore.MAGENTA + f'Player Exception Raised, prev_action behavior missing. Previous Action: {prev_action}')
        #
        # (4) Execute Decision
        #
        return [output, new_action, self.name]

    def challenge(self, p):
        if self.spot == 'CPU':
            pass  # TODO AI behavior
        elif self.spot == 'HUMAN':
            pass  # TODO Human behavior

    def count_ones(self):
        self.wild_count = self.dice.count(1)
        return self.wild_count
