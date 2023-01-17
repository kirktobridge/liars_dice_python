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

    def __init__(self, name: str, spot='CPU', eliminated=False, num_dice=Constants.MAX_NUM_DICE):
        '''Constructor for the Player object. Initializes key variables.'''
        self.name = name
        if Constants.DEBUG:
            if spot == 'CPU':
                print(Fore.CYAN + Style.DIM +
                      f'<i> Player {self.name} has been created.')
            elif spot == 'HUMAN':
                print(Fore.BLUE + f'<i> Player {self.name} has been created.')
        self.num_dice = num_dice
        self.eliminated = eliminated
        self.dice = [-1] * self.num_dice
        self.rolls_mode = 0  # most common roll
        self.wild_count = 0
        self.mode_count = 0
        self.spot = spot
        self.risk_appetite = random.choice(
            Constants.RISK_APPETITE_DISTRIBUTION)
        self.peer_pressure_score = random.choice(
            Constants.PEER_PRESSURE_DISTRIBUTION)
        self.bid = []

    def lose_die(self):
        '''Removes virtual die from the Player object, and updates Player's dice
        count variable.'''
        self.dice[self.num_dice-1] = -1
        self.num_dice -= 1
        if Constants.DEBUG:
            print(Fore.MAGENTA + Style.DIM + f'{self.name} lost a die!')

    def add_die(self):
        '''Adds virtual die to Player's dice inventory.'''
        self.num_dice += 1

    def roll(self):
        '''Generates random values for the Player's held dice between 1 and 6,
        simulating rolls of a six-sided dice.'''
        for d in range(0, self.num_dice):
            self.dice[d] = random.randint(1, 6)

    @ staticmethod
    def grade(p):
        '''Provides a classification for a probability by comparing a percentage to a
        predetermined set of thresholds found in the Constants file.'''
        grade = Constants.LOWEST_THRESHOLD
        # sorted(Constants.PROB_THRESHOLDS.items(), key=lambda x: x[1]):
        for k, v in Constants.PROB_THRESHOLDS:
            if p < v:
                break
            else:
                grade = k
        # further down the line: could make grading dependent on a 'personality' attribute
        # ie each Player will have slightly different risk tolerance levels
        return grade

    def bid(self, tot_other_dice: int):
        '''Allows human user to bid.'''
        bid_count = None
        bid_face = None
        if self.spot == 'HUMAN':  # TODO Human-controlled behavior
            while True:
                try:
                    bid_count = int(input(
                        Fore.BLUE + f'<?> {self.name}, please enter bid size: '))
                    if bid_count < 0:
                        raise Exception('<!> Ye\' cannot do that, matey.')
                    if bid_count > (tot_other_dice + self.num_dice):
                        raise Exception(
                            '<!> Are ye\' daft? Yer\' bettin\' more dice than are possible.')
                    # TODO prevent from betting count higher than possible
                    break

                except TypeError:
                    print(Fore.RED + Style.DIM +
                          '<!> Arrrgh, ye must provide an integer, matey!')
                    continue
                except Exception as e:
                    print(Fore.RED + Style.DIM + e)
                    continue

            while True:
                try:
                    bid_face = int(input(
                        Fore.BLUE + f'<?> {self.name}, please enter the number of the face you are bidding on: '))
                    if bid_face < 1 or bid_face > 6:
                        raise Exception('<!> Ye\' cannot do that, matey.')
                    new_bid = [bid_count, bid_face]
                    return new_bid

                except TypeError:
                    print(Fore.RED + Style.DIM +
                          '<!> Arrrgh, ye must provide an integer, matey!')
                    continue
                except Exception as e:
                    print(Fore.RED + Style.DIM + e)
                    continue
        else:
            raise Exception('CPUs should not be using bid() function')

    def take_turn(self, prev_events: deque, tot_other_dice: int):
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
        prev_action = prev_event[1]
        # pulls value of new_action from previous turn

        # (2) Statistical Analysis: Find the mode of our roll and our count of ones.
        # Use this information, along with the number of other players' dice,
        # to calculate the probability of the previous bid being true. This can be done
        # using a scipy function to calculate the binomial cumulative probability.
        new_action = Constants.ACTIONS[5]
        self.rolls_mode = mode(self.dice)  # what is our most common roll?
        self.mode_count = self.dice.count(self.rolls_mode) + self.count_ones()

        # If we are the first player
        if prev_action == Constants.ACTIONS[0]:
            # if we have a safe bid (mode)
            if self.mode_count >= Constants.MINIMUM_BID:
                output = [Constants.MINIMUM_BID +
                          self.risk_appetite, self.rolls_mode]
            else:  # we have no mode assuming constant is 2
                output = [Constants.MINIMUM_BID + self.risk_appetite-1,
                          self.dice[random.randint(0, self.num_dice-1)]]
            new_action = Constants.ACTIONS[1]

        # If the previous player made a bid
        elif prev_action == (Constants.ACTIONS[1] or Constants.ACTIONS[2]):
            # return [[-1, -1], Constants.ACTIONS[5] + ' TODO BID/RAISE/CHALLENGE DECISION', self.name]
            model = binom(n=tot_other_dice, p=2/6)  # set up binomial model
            # ns and 1s count as ns
            prev_bid = prev_event[0]  # pulls previous turn's bid
            prev_bid_cnt = prev_bid[0]
            prev_bid_face = prev_bid[1]
            prev_bid_needed_cnt = self.get_needed_cnt(
                prev_bid)
            # needed count is how many dice with the desired face we need for the previous bid
            # to be true, factoring in the roll we already know the outcome for (ours)
            if prev_bid_needed_cnt == 0:
                challenge_success_probability = 0
                # if we know this bid is true, don't challenge
            elif prev_bid_needed_cnt < 0:
                # negative number means we can safely raise this bid
                # current philosophy for raising is that we don't want to
                # raise the inherent bid risk for all players (and thus ourselves)
                # more than is necessary,
                # so we only raise by one. However, this behavior could be changed
                # to raise by the maximum safest amount, or the maximum safest amount
                # plus a few risked dice. This risk addition could be a personality
                # attribute of the Player object, perhaps something to randomize (or
                # create a distribution of across the playerset for a game)
                challenge_success_probability = 0.0
                spot_on_probability = 0.0
                output = [prev_bid_cnt+1, prev_bid_face]
                new_action = Constants.ACTION[2]

            elif prev_bid_needed_cnt > 0:  # do I need this? > and face_self_match_cnt > 0:
                # THREE CHOICES: BID, CHALLENGE, SPOT ON
                # COMPARE:
                # P(CHALLENGE FAILS):
                #   PROBABILITY that the previous bid is true (there are least a b's)
                #   p(x >= y) = 1 - p(x < y-1)
                # P(SPOT ON SUCCEEDS):
                #   PROBABILITY that the previous bid is exactly true
                # P(BEST NEW BID):
                #   used for RAISING OR MATCHING previous BID

                # (1) GET PROBABILITY OF PREVIOUS BID - CHALLENGE
                #   Lower score means we may consider challenge.
                challenge_success_probability = model.cdf(
                    prev_bid_needed_cnt-1)
                # TODO are we using the right function?
                # (2) GET PROBABILITY OF PREVIOUS BID - SPOT ON
                #   Higher score means we may consider calling 'spot on.'
                spot_on_probability = model.pmf(prev_bid_needed_cnt)
                # (3) GET PROBABILITY OF BEST BID
                #   (3.1) GET PROBABILITY OF ALL LEGAL BIDS
                #       produce most probable bid, this will be compared to (1) and (2)
                #       get list of previous bids to check legality of potential bids
                all_prev_bids = []
                for event in prev_events:
                    if not isinstance(event, str) and \
                            (event[1] == Constants.ACTIONS[1] or event[1] == Constants.ACTIONS[2]):
                        all_prev_bids.append(event[0])

                #       (3.1.1) BUILD LIST OF PERMISSIBLE BIDS:
                #           (3.1.1.1) include all count-matching bids not already made this round
                permissible_bids = [[prev_bid_cnt, face]
                                    for face in range(1, 7)
                                    if [prev_bid_cnt, face] not in all_prev_bids]  # if face != prev_bid_face]
                #           (3.1.1.2) include all raising bids
                for raise_face in range(1, 7):
                    permissible_bids.append([prev_bid_cnt+1, raise_face])
                risk_ranking = []
                #   (3.2) GET BEST BID
                #       (tiebreaker: favor most commonly bid face in round so far,
                #       tiebreaker #2: favor highest face)
                #       compare probability for every legal option
                # TODO do we need: best_bid_probability = 0.0
                for legal_bid in permissible_bids:
                    needed_cnt = self.get_needed_cnt(legal_bid)
                    if needed_cnt > 0:
                        bid_probability = 1.0 - model.cdf(needed_cnt-1)
                        # TODO is this the right function?
                    elif needed_cnt <= 0:
                        bid_probability = 1.0
                    risk_ranking.append([bid_probability, legal_bid])
                risk_ranking.sort(key=lambda x: x[0], reverse=True)
                # favor popular faces? persuadability randomized personality attribute??
                # get list of best (equally best) bids
                best_bid_probability = risk_ranking[0][0]
                best_bids = [
                    prob for prob in risk_ranking if prob[0] == best_bid_probability]
                if len(best_bids) > 1:
                    # if we are peer pressure sensitive, pick most common
                    if self.peer_pressure_score >= 5:
                        all_prev_bids_faces = [bid[1]
                                               for all_prev_bid in all_prev_bids]
                        prev_bids_face_mode = mode(all_prev_bids_faces)
                        best_bid_candidate = 0
                        for bid in best_bids:
                            if bid[1] == prev_bids_face_mode:
                                best_bid = bid
                                break
                            else:
                                continue
                    # otherwise just take the top bid
                    else:
                        best_bid = best_bids[0]
                else:
                    best_bid = best_bids[0]
                # TODO compare these probabilities and decide if we should 'spot on', raise/match,
                #  or challenge
                # TODO what do we do when nothing we want to say or can say is likely? randomize choice, but:
                # get list of previous bids' faces from prev_events array (where action = bid/raise)
                # may need to search risk_ranking to see how may other bids have the best probability
                # favor bidding on these faces if we can
                # and perhaps favor actions with riskier consequences (challenge, spot on) based on a
                # risk personality attribute

                # should the player guess if the previous player was lying/taking bad risk
                #  based on how many dice they have and how many dice they bet on?
                #
                # (3) Decision Making: Evaluate stats and make decision
                #
                # TODO: bid new face, raise bid, challenge, or spot on
                # if previous bid unlikely, challenge

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

    def get_needed_cnt(self, bid: list[int]):
        '''Produces the number of rolled faces needed for a bid to be true,
        after including the ones we have.'''
        bid_cnt = bid[0]
        bid_face = bid[1]
        face_self_match_cnt = self.dice.count(
            bid_face) + self.count_ones()
        needed_cnt = bid_cnt - face_self_match_cnt
        return needed_cnt

    def challenge(self):
        if self.spot == 'CPU':
            pass  # TODO AI behavior
        elif self.spot == 'HUMAN':
            pass  # TODO Human behavior

    def count_ones(self):
        self.wild_count = self.dice.count(1)
        return self.wild_count
