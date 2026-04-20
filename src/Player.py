from statistics import mode
from collections import deque
import random
import constants as Constants
from colorama import Fore, Style
from scipy.stats import binom
from models import Action, Bid, TurnResult, OpponentProfile, ResponseContext

_binom_cache: dict[int, binom] = {}


def _get_binom(n: int) -> binom:
    if n not in _binom_cache:
        _binom_cache[n] = binom(n=n, p=2/6)
    return _binom_cache[n]


class Player:

    def __init__(self, name: str, spot='CPU', eliminated=False, num_dice=Constants.MAX_NUM_DICE, rng: random.Random | None = None, input_handler=None):
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
        self.rolls_mode = 0
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
        self._input_handler = input_handler

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
        for k, v in Constants.PROB_THRESHOLDS.items():
            if p < v:
                break
            else:
                grade = k
        return grade

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
        '''Process turn for a player. Returns a TurnResult with bid, action, and player name.'''
        prev_event = prev_events[0]
        prev_action = prev_event.action

        if self.spot == 'HUMAN':
            return self._handle_human_turn(prev_event, tot_other_dice)

        self._compute_dice_stats()

        if prev_action == Action.START:
            return self._make_opening_bid()

        if prev_action == Action.BID or prev_action == Action.RAISE:
            prev_bid = prev_event.bid
            if self.get_needed_cnt(prev_bid) < 0:
                return TurnResult(Bid(prev_bid.count + 1, prev_bid.face), Action.RAISE, self.name)

            all_prev_bids: set[Bid] = {
                event.bid
                for event in prev_events
                if isinstance(event, TurnResult) and event.action in (Action.BID, Action.RAISE)
            }
            ctx = self._build_response_context(prev_event, tot_other_dice, bidder_num_dice, all_prev_bids)
            return self._decide_action(ctx)

        raise Exception(
            Fore.MAGENTA + f'Player Exception Raised, prev_action behavior missing. Previous Event: {prev_event}')

    def _handle_human_turn(self, prev_event: TurnResult, tot_other_dice: int) -> TurnResult:
        if prev_event.action == Action.START:
            resp = self._input_handler({
                'type': 'opening_bid',
                'dice': self.dice[:self.num_dice],
                'tot_other_dice': tot_other_dice,
            })
        else:
            resp = self._input_handler({
                'type': 'decision',
                'dice': self.dice[:self.num_dice],
                'tot_other_dice': tot_other_dice,
                'prev_bid': prev_event.bid,
                'prev_player': prev_event.player_name,
            })
        return TurnResult(resp.get('bid'), resp['action'], self.name)

    def _compute_dice_stats(self) -> None:
        if self.num_dice > 1:
            self.rolls_mode = mode(self.dice[:self.num_dice])
            self.mode_count = self.dice.count(self.rolls_mode) + self.count_ones()
        else:
            self.rolls_mode = self.dice[0]
            self.mode_count = 1

    def _make_opening_bid(self) -> TurnResult:
        if Constants.DEBUG:
            print('START RECIEVED BY ' + self.name)
        risk_factor = self.risk_appetite / Constants.MAX_RISK_SCORE
        extra = sum(1 for _ in range(2) if self._rng.random() < risk_factor)
        if self.mode_count >= Constants.MINIMUM_BID:
            output = Bid(Constants.MINIMUM_BID + extra, self.rolls_mode)
        else:
            output = Bid(Constants.MINIMUM_BID + extra,
                         self.dice[self._rng.randint(0, self.num_dice - 1)])
        return TurnResult(output, Action.BID, self.name)

    def _build_response_context(
            self, prev_event: TurnResult, tot_other_dice: int,
            bidder_num_dice: int, all_prev_bids: set[Bid]) -> ResponseContext:
        prev_bid = prev_event.bid
        needed = self.get_needed_cnt(prev_bid)
        model = _get_binom(tot_other_dice)
        permissible = self._get_permissible_bids(prev_bid.count, tot_other_dice, all_prev_bids)
        best_bid, best_bid_prob = self._rank_and_select_bid(permissible, model, all_prev_bids)
        return ResponseContext(
            prev_bid=prev_bid,
            challenge_prob=self._compute_challenge_probability(
                prev_event.player_name, tot_other_dice, bidder_num_dice, needed),
            effective_threshold=self._effective_challenge_threshold(prev_event.player_name),
            spot_on_prob=float(model.pmf(needed)),
            best_bid=best_bid,
            best_bid_prob=best_bid_prob,
        )

    def _compute_challenge_probability(
            self, bidder_name: str, tot_other_dice: int, bidder_num_dice: int, needed: int) -> float:
        if needed == 0:
            return 0.0
        remaining_dice = tot_other_dice - bidder_num_dice
        bidder_model = _get_binom(bidder_num_dice)
        remaining_model = _get_binom(remaining_dice)
        bayesian_prob = 0.0
        for j in range(bidder_num_dice + 1):
            needed_from_remaining = needed - j
            if needed_from_remaining <= 0:
                continue
            bayesian_prob += bidder_model.pmf(j) * remaining_model.cdf(needed_from_remaining - 1)
        flat_prob = _get_binom(tot_other_dice).cdf(needed - 1)
        blend = self.peer_pressure_score / Constants.MAX_PEER_PRESSURE_SCORE
        prob = blend * bayesian_prob + (1 - blend) * flat_prob

        _MIN_SAMPLES = 2
        _profile = self.opponent_profiles.get(bidder_name)
        _attention = self.attentiveness_score / Constants.MAX_ATTENTIVENESS_SCORE
        if _profile and _profile.bids_observed >= _MIN_SAMPLES:
            aggression_boost = 1.0 + (_profile.avg_aggression - 0.5) * 0.3 * _attention
            prob = min(1.0, prob * aggression_boost)
        return prob

    def _effective_challenge_threshold(self, bidder_name: str) -> float:
        _MIN_SAMPLES = 2
        effective_threshold = self.challenge_threshold
        _profile = self.opponent_profiles.get(bidder_name)
        _attention = self.attentiveness_score / Constants.MAX_ATTENTIVENESS_SCORE
        if _profile and _profile.bids_challenged >= _MIN_SAMPLES:
            bluff_adjustment = (_profile.bluff_rate - 0.5) * 0.4 * _attention
            effective_threshold = max(0.10, self.challenge_threshold - bluff_adjustment)
        return effective_threshold

    def _get_permissible_bids(self, prev_bid_cnt: int, tot_other_dice: int, all_prev_bids: set[Bid]) -> list[Bid]:
        permissible = [Bid(prev_bid_cnt, face) for face in range(1, 7)
                       if Bid(prev_bid_cnt, face) not in all_prev_bids]
        for raise_face in range(1, 7):
            if prev_bid_cnt + 1 <= tot_other_dice:
                permissible.append(Bid(prev_bid_cnt + 1, raise_face))
        return permissible

    def _rank_and_select_bid(self, permissible: list[Bid], model, all_prev_bids: set[Bid]) -> 'tuple[Bid | None, float]':
        if not permissible:
            return None, 0.0
        risk_ranking: list[list] = []
        for legal_bid in permissible:
            needed_cnt = self.get_needed_cnt(legal_bid)
            bid_probability = 1.0 if needed_cnt <= 0 else 1.0 - model.cdf(needed_cnt - 1)
            risk_ranking.append([bid_probability, legal_bid])
        risk_ranking.sort(key=lambda x: x[0], reverse=True)
        best_bid_probability = risk_ranking[0][0]
        best_bids: list[Bid] = [row[1] for row in risk_ranking if row[0] == best_bid_probability]
        crowd_pick = self._apply_crowd_preference(best_bids, all_prev_bids)
        if crowd_pick is not None:
            return crowd_pick, best_bid_probability
        return best_bids[0], best_bid_probability

    def _apply_crowd_preference(self, best_bids: list[Bid], all_prev_bids: set[Bid]) -> 'Bid | None':
        if len(best_bids) <= 1 or not all_prev_bids:
            return None
        follow_crowd_prob = self.peer_pressure_score / Constants.MAX_PEER_PRESSURE_SCORE
        if self._rng.random() >= follow_crowd_prob:
            return None
        prev_bids_face_mode = mode([b.face for b in all_prev_bids])
        for bid in best_bids:
            if bid.face == prev_bids_face_mode:
                return bid
        return None

    def _decide_action(self, ctx: ResponseContext) -> TurnResult:
        effective_challenge_prob = ctx.challenge_prob if ctx.challenge_prob >= ctx.effective_threshold else 0.0
        best_probability = max(effective_challenge_prob, ctx.spot_on_prob, ctx.best_bid_prob)

        if best_probability == 0:
            if ctx.best_bid is not None:
                action = Action.RAISE if ctx.best_bid.count > ctx.prev_bid.count else Action.BID
                return TurnResult(ctx.best_bid, action, self.name)
            return TurnResult(None, Action.CHALLENGE, self.name)

        # Priority 1: SPOT_ON if dominant
        if ctx.spot_on_prob == best_probability:
            return TurnResult(None, Action.SPOT_ON, self.name)

        # Priority 2: Stochastic SPOT_ON override — risk appetite can override the dominant play
        if ctx.spot_on_prob > self.spot_on_threshold and self._rng.random() < self.risk_appetite / Constants.MAX_RISK_SCORE:
            return TurnResult(None, Action.SPOT_ON, self.name)

        # Priority 3: CHALLENGE if dominant
        if effective_challenge_prob == best_probability:
            return TurnResult(None, Action.CHALLENGE, self.name)

        # Priority 4: BID or RAISE
        action = Action.RAISE if ctx.best_bid.count > ctx.prev_bid.count else Action.BID
        return TurnResult(ctx.best_bid, action, self.name)

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

    def count_ones(self):
        self.wild_count = self.dice.count(1)
        return self.wild_count
