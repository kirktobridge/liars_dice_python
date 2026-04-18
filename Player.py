# class for Player object
# move to Constants file
from statistics import mode
from collections import deque
import random
import Constants
from colorama import Fore, Style
from scipy.stats import binom
from models import Action, Bid, TurnResult, OpponentProfile

_binom_cache: dict[int, binom] = {}

# TODO refactorings for readability (bidding, getting probability, etc)
# TODO behavior for human bidding/raising/challenging
# TODO add behavior for raising by more than 1


class Player:

    def __init__(self, name: str, spot='CPU', eliminated=False, num_dice=Constants.MAX_NUM_DICE, rng: random.Random | None = None):
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
        self._rng = rng if rng is not None else random.Random()
        self.risk_appetite = self._rng.choice(
            Constants.RISK_APPETITE_DISTRIBUTION)
        jitter = self._rng.uniform(-0.03, 0.03)
        risk_shift = (self.risk_appetite / Constants.MAX_RISK_SCORE) * 0.06
        self.spot_on_threshold = max(0.01, Constants.MIN_SPOT_ON_RISK - risk_shift + jitter)
        risk_fraction = self.risk_appetite / Constants.MAX_RISK_SCORE
        challenge_jitter = self._rng.uniform(-0.03, 0.03)
        self.challenge_threshold = max(0.20, 0.65 - risk_fraction * 0.30 + challenge_jitter)
        self.peer_pressure_score = self._rng.choice(
            Constants.PEER_PRESSURE_DISTRIBUTION)
        self.attentiveness_score = self._rng.choice(
            Constants.ATTENTIVENESS_DISTRIBUTION)
        self.opponent_profiles: dict[str, OpponentProfile] = {}

    def reset(self) -> None:
        """Reset per-game state; personality traits (risk_appetite, spot_on_threshold, challenge_threshold, peer_pressure_score, attentiveness_score) are preserved."""
        self.num_dice = Constants.MAX_NUM_DICE
        self.dice = [-1] * self.num_dice
        self.rolls_mode = 0
        self.wild_count = 0
        self.mode_count = 0
        self.eliminated = False
        self.opponent_profiles = {}

    def lose_die(self):
        '''Removes virtual die from the Player object, and updates Player's dice
        count variable.'''
        self.dice[self.num_dice-1] = -1
        if Constants.DEBUG:
            print(Fore.MAGENTA + Style.DIM +
                  f'{self.name} had {self.num_dice} dice')
        self.num_dice -= 1
        if Constants.DEBUG:
            print(Fore.MAGENTA + Style.DIM +
                  f'{self.name} now has {self.num_dice} dice')
        if Constants.DEBUG:
            print(Fore.MAGENTA + Style.DIM + f'{self.name} lost a die!')

    def add_die(self):
        '''Adds virtual die to Player's dice inventory.'''
        self.num_dice += 1

    def roll(self):
        '''Generates random values for the Player's held dice between 1 and 6,
        simulating rolls of a six-sided dice.'''
        for d in range(0, self.num_dice):
            self.dice[d] = self._rng.randint(1, 6)

    @staticmethod
    def grade(p: float):
        '''Provides a classification for a probability by comparing a percentage to a
        predetermined set of thresholds found in the Constants file.'''
        grade = Constants.LOWEST_THRESHOLD
        # sorted(Constants.PROB_THRESHOLDS.items(), key=lambda x: x[1]):
        for k, v in Constants.PROB_THRESHOLDS.items():
            if p < v:
                break
            else:
                grade = k
        # further down the line: could make grading dependent on a 'personality' attribute
        # ie each Player will have slightly different risk tolerance levels
        return grade

    def bid(self, tot_other_dice: int) -> Bid:
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

                except ValueError:
                    print(Fore.RED + Style.DIM +
                          '<!> Arrrgh, ye must provide an integer, matey!')
                    continue
                except Exception as e:
                    print(Fore.RED + Style.DIM + str(e))
                    continue

            while True:
                try:
                    bid_face = int(input(
                        Fore.BLUE + f'<?> {self.name}, please enter the number of the face you are bidding on: '))
                    if bid_face < 1 or bid_face > 6:
                        raise Exception('<!> Ye\' cannot do that, matey.')
                    return Bid(bid_count, bid_face)

                except ValueError:
                    print(Fore.RED + Style.DIM +
                          '<!> Arrrgh, ye must provide an integer, matey!')
                    continue
                except Exception as e:
                    print(Fore.RED + Style.DIM + str(e))
                    continue
        else:
            raise Exception('CPUs should not be using bid() function')

    def observe_action(self, player_name: str, action: Action, bid: 'Bid | None', total_dice: int) -> None:
        if action not in (Action.BID, Action.RAISE) or bid is None or total_dice == 0:
            return
        if player_name not in self.opponent_profiles:
            self.opponent_profiles[player_name] = OpponentProfile()
        profile = self.opponent_profiles[player_name]
        profile.bids_observed += 1
        profile.total_aggression += bid.count / total_dice

    def observe_outcome(self, bidder_name: str, challenge_succeeded: bool) -> None:
        if bidder_name not in self.opponent_profiles:
            self.opponent_profiles[bidder_name] = OpponentProfile()
        profile = self.opponent_profiles[bidder_name]
        profile.bids_challenged += 1
        if challenge_succeeded:
            profile.challenge_successes += 1

    def take_turn(self, prev_events: deque, tot_other_dice: int, bidder_num_dice: int = 0) -> TurnResult:
        '''Process turn for a player by analyzing previous moves in the round and probabilities of success on various actions.
        Returns a TurnResult with bid, action, and player name.'''
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
        # (I) Read Previous Player's Action: from stack (prev_events) given by LiarsDiceGame
        #
        prev_event = prev_events[0]
        prev_action = prev_event.action
        # pulls value of new_action from previous turn

        # (II) Statistical Analysis: Find the mode of our roll and our count of ones.
        # Use this information, along with the number of other players' dice,
        # to calculate the probability of the previous bid being true. This can be done
        # using a scipy function to calculate the binomial cumulative probability.
        new_action = Action.NONE
        output: 'Bid | None' = None

        # Human player decision
        if self.spot == 'HUMAN':
            print(Fore.BLUE + f'<i> Your dice: {self.dice[:self.num_dice]}')
            if prev_action == Action.START:  # START - must bid
                print(Fore.BLUE + '<i> You go first — make the opening bid.')
                output = self.bid(tot_other_dice)
                new_action = Action.BID
            elif prev_action in (Action.BID, Action.RAISE):
                prev_bid = prev_event.bid
                prev_bid_cnt, prev_bid_face = prev_bid.count, prev_bid.face
                prev_player = prev_event.player_name
                print(Fore.BLUE + f'<i> {prev_player} bid {prev_bid_cnt} {prev_bid_face}\'s.')
                while True:
                    try:
                        choice = input(Fore.BLUE + '<?> Your action — [B]id/Raise, [C]hallenge, [S]pot On: ').strip().upper()
                        if choice not in ('B', 'BID', 'R', 'RAISE', 'C', 'CHALLENGE', 'S', 'SPOT'):
                            raise ValueError('<!> Say B, C, or S, matey!')
                        break
                    except ValueError as e:
                        print(Fore.RED + Style.DIM + str(e))
                if choice in ('B', 'BID', 'R', 'RAISE'):
                    while True:
                        output = self.bid(tot_other_dice)
                        if output.count < prev_bid_cnt or (output.count == prev_bid_cnt and output.face == prev_bid_face):
                            print(Fore.RED + Style.DIM +
                                  f'<!> Yarrr, that\'s not allowed, matey, yer bid must raise th\' count above {prev_bid_cnt}, or bid a diff\'rent face at count {prev_bid_cnt}.')
                            continue
                        break
                    new_action = Action.RAISE if output.count > prev_bid_cnt else Action.BID
                elif choice in ('C', 'CHALLENGE'):
                    output = None
                    new_action = Action.CHALLENGE
                else:  # SPOT
                    output = None
                    new_action = Action.SPOT_ON
            return TurnResult(output, new_action, self.name)

        # what is our most common roll?
        if self.num_dice > 1:
            self.rolls_mode = mode(self.dice[:self.num_dice])
            self.mode_count = self.dice.count(
                self.rolls_mode) + self.count_ones()
        else:
            self.rolls_mode = self.dice[0]
            self.mode_count = 1

        # If we are the first player, we must bid
        if prev_action == Action.START:
            if Constants.DEBUG == True:
                print('START RECIEVED BY ' + self.name)
            risk_factor = self.risk_appetite / Constants.MAX_RISK_SCORE
            extra = sum(1 for _ in range(2) if self._rng.random() < risk_factor)
            if self.mode_count >= Constants.MINIMUM_BID:
                output = Bid(Constants.MINIMUM_BID + extra, self.rolls_mode)
            else:
                output = Bid(Constants.MINIMUM_BID + extra,
                             self.dice[self._rng.randint(0, self.num_dice-1)])
            new_action = Action.BID

        # If the previous player made a bid
        elif prev_action == Action.BID or prev_action == Action.RAISE:
            if tot_other_dice not in _binom_cache:
                _binom_cache[tot_other_dice] = binom(n=tot_other_dice, p=2/6)
            model = _binom_cache[tot_other_dice]  # set up binomial model
            # ns and 1s count as ns
            prev_bid = prev_event.bid  # pulls previous turn's bid
            prev_bid_cnt = prev_bid.count
            prev_bid_face = prev_bid.face
            prev_bid_needed_cnt = self.get_needed_cnt(prev_bid)
            # needed count is how many dice with the desired face we need for the previous bid
            # to be true, factoring in the roll we already know the outcome for (ours)

            # if we know this bid is true, don't challenge
            if prev_bid_needed_cnt < 0:
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
                output = Bid(prev_bid_cnt + 1, prev_bid_face)
                new_action = Action.RAISE

            elif prev_bid_needed_cnt >= 0:
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
                if prev_bid_needed_cnt == 0:
                    challenge_success_probability = 0.0
                else:
                    remaining_dice = tot_other_dice - bidder_num_dice
                    for n in (bidder_num_dice, remaining_dice, tot_other_dice):
                        if n not in _binom_cache:
                            _binom_cache[n] = binom(n=n, p=2/6)
                    bidder_model    = _binom_cache[bidder_num_dice]
                    remaining_model = _binom_cache[remaining_dice]
                    bayesian_prob = 0.0
                    for j in range(bidder_num_dice + 1):
                        needed_from_remaining = prev_bid_needed_cnt - j
                        if needed_from_remaining <= 0:
                            continue
                        bayesian_prob += bidder_model.pmf(j) * remaining_model.cdf(needed_from_remaining - 1)
                    flat_prob = _binom_cache[tot_other_dice].cdf(prev_bid_needed_cnt - 1)
                    blend = self.peer_pressure_score / Constants.MAX_PEER_PRESSURE_SCORE
                    challenge_success_probability = blend * bayesian_prob + (1 - blend) * flat_prob

                _MIN_SAMPLES = 2
                _bidder_name = prev_event.player_name
                _profile = self.opponent_profiles.get(_bidder_name)
                _attention = self.attentiveness_score / Constants.MAX_ATTENTIVENESS_SCORE
                if _profile and _profile.bids_observed >= _MIN_SAMPLES:
                    aggression_boost = 1.0 + (_profile.avg_aggression - 0.5) * 0.3 * _attention
                    challenge_success_probability = min(1.0, challenge_success_probability * aggression_boost)
                effective_threshold = self.challenge_threshold
                if _profile and _profile.bids_challenged >= _MIN_SAMPLES:
                    bluff_adjustment = (_profile.bluff_rate - 0.5) * 0.4 * _attention
                    effective_threshold = max(0.10, self.challenge_threshold - bluff_adjustment)
                # (2) GET PROBABILITY OF PREVIOUS BID - SPOT ON
                #   Higher score means we may consider calling 'spot on.'
                spot_on_probability = model.pmf(prev_bid_needed_cnt)
                # (3) GET PROBABILITY OF BEST BID
                #   (3.1) GET PROBABILITY OF ALL LEGAL BIDS
                #       produce most probable bid, this will be compared to (1) and (2)
                #       get list of previous bids to check legality of potential bids
                all_prev_bids: set[Bid] = {
                    event.bid
                    for event in prev_events
                    if isinstance(event, TurnResult)
                    and event.action in (Action.BID, Action.RAISE)
                }

                #       (3.1.1) BUILD LIST OF PERMISSIBLE BIDS:
                #           (3.1.1.1) include all count-matching bids not already made this round
                permissible_bids = [Bid(prev_bid_cnt, face)
                                    for face in range(1, 7)
                                    if Bid(prev_bid_cnt, face) not in all_prev_bids]
                #           (3.1.1.2) include all raising bids
                for raise_face in range(1, 7):
                    if prev_bid_cnt + 1 <= tot_other_dice:
                        permissible_bids.append(Bid(prev_bid_cnt + 1, raise_face))
                risk_ranking = []
                #   (3.2) GET BEST BID
                #       (tiebreaker: favor most commonly bid face in round so far,
                #       tiebreaker #2: favor highest face)
                #       compare probability for every legal option
                best_bid: 'Bid | None' = None  # None means no permissible bids — the else branch below should raise or challenge
                if len(permissible_bids) >= 1:
                    # if there is at least one bid available
                    for legal_bid in permissible_bids:
                        needed_cnt = self.get_needed_cnt(legal_bid)
                        if needed_cnt > 0:
                            bid_probability = 1.0 - model.cdf(needed_cnt-1)
                        elif needed_cnt <= 0:
                            bid_probability = 1.0
                        risk_ranking.append([bid_probability, legal_bid])
                    risk_ranking.sort(key=lambda x: x[0], reverse=True)
                    # get list of best (equally best) bids
                    best_bid_probability = risk_ranking[0][0]
                    best_bids: list[Bid] = [
                        prob[1] for prob in risk_ranking if prob[0] == best_bid_probability]
                    if len(best_bids) > 1:
                        follow_crowd_prob = self.peer_pressure_score / Constants.MAX_PEER_PRESSURE_SCORE
                        if all_prev_bids and self._rng.random() < follow_crowd_prob:
                            all_prev_bids_faces = [b.face for b in all_prev_bids]
                            prev_bids_face_mode = mode(all_prev_bids_faces)
                            for bid0 in best_bids:
                                if bid0.face == prev_bids_face_mode:
                                    best_bid = bid0
                                    break
                            if best_bid is None:
                                best_bid = best_bids[0]
                        else:
                            best_bid = best_bids[0]
                    else:
                        best_bid = best_bids[0]
                # if there are no permissible bids, don't bid
                else:
                    best_bid_probability = 0
                    best_bid = None  # no permissible bids — should never be used as a bid output

                effective_challenge_prob = (
                    challenge_success_probability
                    if challenge_success_probability >= effective_threshold
                    else 0.0
                )
                best_probability = max(
                    [effective_challenge_prob, spot_on_probability, best_bid_probability])
                if best_probability > 0:
                    # if calling spot on is our best bet
                    if spot_on_probability == best_probability:
                        output = None
                        new_action = Action.SPOT_ON
                    # if it's only 1/3 likely, but we like risk anyway, then call spot on
                    elif spot_on_probability > self.spot_on_threshold and self._rng.random() < self.risk_appetite / Constants.MAX_RISK_SCORE:
                        output = None
                        new_action = Action.SPOT_ON
                    elif effective_challenge_prob == best_probability and effective_challenge_prob > 0:
                        output = None
                        new_action = Action.CHALLENGE
                    elif best_bid_probability == best_probability:
                        output = best_bid
                        if best_bid.count > prev_bid_cnt:
                            new_action = Action.RAISE
                        else:
                            new_action = Action.BID
                else:  # all probabilities are zero — never spot on (pure gamble)
                    if best_bid is not None:
                        output = best_bid
                        new_action = Action.RAISE if best_bid.count > prev_bid_cnt else Action.BID
                    else:
                        output = None
                        new_action = Action.CHALLENGE
        else:
            output = None
            new_action = Action.NONE
            # TODO catch-all behavior
            raise Exception(
                Fore.MAGENTA + f'Player Exception Raised, prev_action behavior missing. Previous Event: {prev_event}')
        #
        # (4) Execute Decision
        #
        return TurnResult(output, new_action, self.name)

    def get_needed_cnt(self, bid: Bid) -> int:
        '''Produces the number of rolled faces needed for a bid to be true,
        after including the ones we have.'''
        bid_cnt = bid.count
        bid_face = bid.face
        if bid_face == 1:
            face_self_match_cnt = self.dice.count(bid_face)
        else:
            face_self_match_cnt = self.dice.count(bid_face) + self.count_ones()
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
