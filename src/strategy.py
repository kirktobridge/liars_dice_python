from statistics import mode, StatisticsError
from collections import deque
from typing import Protocol, runtime_checkable
import logging
import random
import constants as Constants
from dice_math import get_binom, needed_cnt
from models import Action, Bid, TurnResult, OpponentProfile, ResponseContext, InputHandler

logger = logging.getLogger('liars_dice.strategy')


@runtime_checkable
class Strategy(Protocol):
    player_type: str

    def decide(
        self,
        player_name: str,
        dice: list[int],
        num_dice: int,
        prev_events: deque,
        tot_other_dice: int,
        bidder_num_dice: int,
    ) -> TurnResult: ...

    def observe_action(
        self,
        player_name: str,
        action: Action,
        bid: 'Bid | None',
        total_dice: int,
    ) -> None: ...

    def observe_outcome(self, bidder_name: str, challenge_succeeded: bool) -> None: ...

    def reset(self) -> None: ...


class CPUStrategy:
    player_type: str = 'CPU'

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self.risk_appetite: int = rng.choice(Constants.RISK_APPETITE_DISTRIBUTION)
        jitter = rng.uniform(-0.03, 0.03)
        risk_shift = (self.risk_appetite / Constants.MAX_RISK_SCORE) * 0.06
        self.spot_on_threshold: float = max(0.01, Constants.MIN_SPOT_ON_RISK - risk_shift + jitter)
        risk_fraction = self.risk_appetite / Constants.MAX_RISK_SCORE
        challenge_jitter = rng.uniform(-0.03, 0.03)
        self.challenge_threshold: float = max(0.20, 0.65 - risk_fraction * 0.30 + challenge_jitter)
        self.peer_pressure_score: int = rng.choice(Constants.PEER_PRESSURE_DISTRIBUTION)
        self.attentiveness_score: int = rng.choice(Constants.ATTENTIVENESS_DISTRIBUTION)
        self.opponent_profiles: dict[str, OpponentProfile] = {}
        self._rolls_mode: int = 0
        self._mode_count: int = 0

    def reset(self) -> None:
        self.opponent_profiles = {}

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

    def decide(
        self,
        player_name: str,
        dice: list[int],
        num_dice: int,
        prev_events: deque,
        tot_other_dice: int,
        bidder_num_dice: int,
    ) -> TurnResult:
        prev_event = prev_events[0]
        prev_action = prev_event.action
        self._compute_dice_stats(dice, num_dice)

        if prev_action == Action.START:
            return self._make_opening_bid(player_name, dice, num_dice)

        if prev_action == Action.BID or prev_action == Action.RAISE:
            prev_bid = prev_event.bid
            if needed_cnt(dice[:num_dice], prev_bid) < 0:
                return TurnResult(Bid(prev_bid.count + 1, prev_bid.face), Action.RAISE, player_name)

            all_prev_bids: set[Bid] = {
                event.bid
                for event in prev_events
                if isinstance(event, TurnResult) and event.action in (Action.BID, Action.RAISE)
            }
            ctx = self._build_response_context(dice, num_dice, prev_event, tot_other_dice, bidder_num_dice, all_prev_bids)
            return self._decide_action(player_name, ctx)

        logger.error('prev_action behavior missing. Previous Event: %s', prev_event)
        raise Exception(f'CPUStrategy: prev_action behavior missing. Previous Event: {prev_event}')

    def _compute_dice_stats(self, dice: list[int], num_dice: int) -> None:
        active = dice[:num_dice]
        if num_dice > 1:
            self._rolls_mode = mode(active)
            self._mode_count = active.count(self._rolls_mode) + active.count(1)
        else:
            self._rolls_mode = active[0]
            self._mode_count = 1

    def _make_opening_bid(self, player_name: str, dice: list[int], num_dice: int) -> TurnResult:
        logger.debug('START received by %s', player_name)
        risk_factor = self.risk_appetite / Constants.MAX_RISK_SCORE
        extra = sum(1 for _ in range(2) if self._rng.random() < risk_factor)
        if self._mode_count >= Constants.MINIMUM_BID:
            output = Bid(Constants.MINIMUM_BID + extra, self._rolls_mode)
        else:
            output = Bid(Constants.MINIMUM_BID + extra,
                         dice[self._rng.randint(0, num_dice - 1)])
        return TurnResult(output, Action.BID, player_name)

    def _build_response_context(
        self,
        dice: list[int],
        num_dice: int,
        prev_event: TurnResult,
        tot_other_dice: int,
        bidder_num_dice: int,
        all_prev_bids: set[Bid],
    ) -> ResponseContext:
        prev_bid = prev_event.bid
        nc = needed_cnt(dice[:num_dice], prev_bid)
        model = get_binom(tot_other_dice)
        permissible = self._get_permissible_bids(prev_bid.count, tot_other_dice, all_prev_bids)
        best_bid, best_bid_prob = self._rank_and_select_bid(dice, num_dice, permissible, model, all_prev_bids)
        return ResponseContext(
            prev_bid=prev_bid,
            challenge_prob=self._compute_challenge_probability(
                prev_event.player_name, tot_other_dice, bidder_num_dice, nc),
            effective_threshold=self._effective_challenge_threshold(prev_event.player_name),
            spot_on_prob=float(model.pmf(nc)),
            best_bid=best_bid,
            best_bid_prob=best_bid_prob,
        )

    def _compute_challenge_probability(
        self,
        bidder_name: str,
        tot_other_dice: int,
        bidder_num_dice: int,
        needed: int,
    ) -> float:
        if needed == 0:
            return 0.0
        remaining_dice = tot_other_dice - bidder_num_dice
        bidder_model = get_binom(bidder_num_dice)
        remaining_model = get_binom(remaining_dice)
        bayesian_prob = 0.0
        for j in range(bidder_num_dice + 1):
            needed_from_remaining = needed - j
            if needed_from_remaining <= 0:
                continue
            bayesian_prob += bidder_model.pmf(j) * remaining_model.cdf(needed_from_remaining - 1)
        flat_prob = get_binom(tot_other_dice).cdf(needed - 1)
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

    def _rank_and_select_bid(
        self,
        dice: list[int],
        num_dice: int,
        permissible: list[Bid],
        model,
        all_prev_bids: set[Bid],
    ) -> 'tuple[Bid | None, float]':
        if not permissible:
            return None, 0.0
        risk_ranking: list[list] = []
        for legal_bid in permissible:
            nc = needed_cnt(dice[:num_dice], legal_bid)
            bid_probability = 1.0 if nc <= 0 else 1.0 - model.cdf(nc - 1)
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
        try:
            prev_bids_face_mode = mode([b.face for b in all_prev_bids])
        except StatisticsError:
            return None
        for bid in best_bids:
            if bid.face == prev_bids_face_mode:
                return bid
        return None

    def _decide_action(self, player_name: str, ctx: ResponseContext) -> TurnResult:
        effective_challenge_prob = ctx.challenge_prob if ctx.challenge_prob >= ctx.effective_threshold else 0.0
        best_probability = max(effective_challenge_prob, ctx.spot_on_prob, ctx.best_bid_prob)

        if best_probability == 0:
            if ctx.best_bid is not None:
                action = Action.RAISE if ctx.best_bid.count > ctx.prev_bid.count else Action.BID
                return TurnResult(ctx.best_bid, action, player_name)
            return TurnResult(None, Action.CHALLENGE, player_name)

        if ctx.spot_on_prob == best_probability:
            return TurnResult(None, Action.SPOT_ON, player_name)

        if effective_challenge_prob == best_probability:
            return TurnResult(None, Action.CHALLENGE, player_name)

        if ctx.spot_on_prob > self.spot_on_threshold and self._rng.random() < self.risk_appetite / Constants.MAX_RISK_SCORE:
            return TurnResult(None, Action.SPOT_ON, player_name)

        action = Action.RAISE if ctx.best_bid.count > ctx.prev_bid.count else Action.BID
        return TurnResult(ctx.best_bid, action, player_name)


class HumanStrategy:
    player_type: str = 'HUMAN'

    def __init__(self, input_handler: 'InputHandler') -> None:
        self._input_handler = input_handler

    def reset(self) -> None:
        pass

    def observe_action(self, *args, **kwargs) -> None:
        pass

    def observe_outcome(self, *args, **kwargs) -> None:
        pass

    def decide(
        self,
        player_name: str,
        dice: list[int],
        num_dice: int,
        prev_events: deque,
        tot_other_dice: int,
        bidder_num_dice: int,
    ) -> TurnResult:
        prev_event = prev_events[0]
        if prev_event.action == Action.START:
            resp = self._input_handler({
                'type': 'opening_bid',
                'dice': dice[:num_dice],
                'tot_other_dice': tot_other_dice,
            })
        else:
            resp = self._input_handler({
                'type': 'decision',
                'dice': dice[:num_dice],
                'tot_other_dice': tot_other_dice,
                'prev_bid': prev_event.bid,
                'prev_player': prev_event.player_name,
            })
        return TurnResult(resp.get('bid'), resp['action'], player_name)
