from statistics import mode, StatisticsError
from collections import deque
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
import json
import logging
import random
import re
import constants as Constants
from dice_math import get_binom, needed_cnt
from models import Action, Bid, TurnResult, OpponentProfile, ResponseContext, InputHandler
from llm_client import query_llm

logger = logging.getLogger('liars_dice.strategy')

_BLIND_AGGRESSION_THRESHOLD = 1.4
_CHALLENGE_BOOST_MAX = 0.15
_PRESSURE_OPP_THRESHOLD = 0.45


@dataclass
class Personality:
    risk_appetite: int
    peer_pressure_score: int
    attentiveness_score: int
    positional_cunning: int
    spot_on_threshold: float
    challenge_threshold: float

    @classmethod
    def from_traits(
        cls,
        *,
        risk_appetite: int,
        peer_pressure_score: int,
        attentiveness_score: int,
        positional_cunning: int,
        spot_on_jitter: float = 0.0,
        challenge_jitter: float = 0.0,
    ) -> 'Personality':
        risk_fraction = risk_appetite / Constants.MAX_RISK_SCORE
        spot_on_threshold = max(0.01, Constants.MIN_SPOT_ON_RISK - risk_fraction * 0.06 + spot_on_jitter)
        challenge_threshold = max(0.20, 0.65 - risk_fraction * 0.30 + challenge_jitter)
        return cls(
            risk_appetite=risk_appetite,
            peer_pressure_score=peer_pressure_score,
            attentiveness_score=attentiveness_score,
            positional_cunning=positional_cunning,
            spot_on_threshold=spot_on_threshold,
            challenge_threshold=challenge_threshold,
        )

    @classmethod
    def random(cls, rng: random.Random) -> 'Personality':
        risk_appetite = rng.choice(Constants.RISK_APPETITE_DISTRIBUTION)
        spot_on_jitter = rng.uniform(-0.03, 0.03)
        challenge_jitter = rng.uniform(-0.03, 0.03)
        peer_pressure_score = rng.choice(Constants.PEER_PRESSURE_DISTRIBUTION)
        attentiveness_score = rng.choice(Constants.ATTENTIVENESS_DISTRIBUTION)
        positional_cunning = rng.choice(Constants.POSITIONAL_CUNNING_DISTRIBUTION)
        return cls.from_traits(
            risk_appetite=risk_appetite,
            peer_pressure_score=peer_pressure_score,
            attentiveness_score=attentiveness_score,
            positional_cunning=positional_cunning,
            spot_on_jitter=spot_on_jitter,
            challenge_jitter=challenge_jitter,
        )


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
        next_player_num_dice: int,
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

    def __init__(self, rng: random.Random, personality: 'Personality | None' = None) -> None:
        self._rng = rng
        self.personality: Personality = personality if personality is not None else Personality.random(rng)
        self.opponent_profiles: dict[str, OpponentProfile] = {}
        self._rolls_mode: int = 0
        self._mode_count: int = 0

    @property
    def risk_appetite(self) -> int:
        return self.personality.risk_appetite

    @risk_appetite.setter
    def risk_appetite(self, value: int) -> None:
        self.personality.risk_appetite = value

    @property
    def peer_pressure_score(self) -> int:
        return self.personality.peer_pressure_score

    @peer_pressure_score.setter
    def peer_pressure_score(self, value: int) -> None:
        self.personality.peer_pressure_score = value

    @property
    def attentiveness_score(self) -> int:
        return self.personality.attentiveness_score

    @attentiveness_score.setter
    def attentiveness_score(self, value: int) -> None:
        self.personality.attentiveness_score = value

    @property
    def positional_cunning(self) -> int:
        return self.personality.positional_cunning

    @positional_cunning.setter
    def positional_cunning(self, value: int) -> None:
        self.personality.positional_cunning = value

    @property
    def spot_on_threshold(self) -> float:
        return self.personality.spot_on_threshold

    @spot_on_threshold.setter
    def spot_on_threshold(self, value: float) -> None:
        self.personality.spot_on_threshold = value

    @property
    def challenge_threshold(self) -> float:
        return self.personality.challenge_threshold

    @challenge_threshold.setter
    def challenge_threshold(self, value: float) -> None:
        self.personality.challenge_threshold = value

    def _set_personality(
        self,
        risk_appetite: int,
        peer_pressure_score: int,
        attentiveness_score: int,
        positional_cunning: int,
        spot_on_jitter: float = 0.0,
        challenge_jitter: float = 0.0,
    ) -> None:
        self.personality = Personality.from_traits(
            risk_appetite=risk_appetite,
            peer_pressure_score=peer_pressure_score,
            attentiveness_score=attentiveness_score,
            positional_cunning=positional_cunning,
            spot_on_jitter=spot_on_jitter,
            challenge_jitter=challenge_jitter,
        )

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
        next_player_num_dice: int = 0,
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
            ctx = self._build_response_context(
                dice, num_dice, prev_event, tot_other_dice, bidder_num_dice,
                all_prev_bids, next_player_num_dice)
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
        next_player_num_dice: int = 0,
    ) -> ResponseContext:
        prev_bid = prev_event.bid
        nc = needed_cnt(dice[:num_dice], prev_bid)
        model = get_binom(tot_other_dice)
        total_dice = num_dice + tot_other_dice
        bas = self._blind_aggression_score(bidder_num_dice, total_dice, prev_bid.count)
        pos = self._pressure_opportunity_score(next_player_num_dice, total_dice, prev_bid.count)
        cunning = self.positional_cunning / Constants.MAX_POSITIONAL_CUNNING_SCORE
        permissible = self._get_permissible_bids(prev_bid.count, tot_other_dice, all_prev_bids)
        best_bid, best_bid_prob = self._rank_and_select_bid(
            dice, num_dice, permissible, model, all_prev_bids,
            pressure_hint=pos * cunning)
        return ResponseContext(
            prev_bid=prev_bid,
            challenge_prob=self._compute_challenge_probability(
                prev_event.player_name, tot_other_dice, bidder_num_dice, nc),
            effective_threshold=self._effective_challenge_threshold(prev_event.player_name),
            spot_on_prob=float(model.pmf(nc)),
            best_bid=best_bid,
            best_bid_prob=best_bid_prob,
            blind_aggression_score=bas,
            pressure_opportunity_score=pos,
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

    def _blind_aggression_score(
        self,
        bidder_num_dice: int,
        total_dice: int,
        bid_count: int,
    ) -> float:
        """Returns the ratio of the bid's claim (as a fraction of total dice) to the
        bidder's information window (their dice / total dice). A score > 1.0 means
        the bidder claimed more than their window justifies. Higher = more likely
        they are bluffing or estimating blindly."""
        info_ratio = bidder_num_dice / total_dice if total_dice > 0 else 0.01
        bid_ratio = bid_count / total_dice if total_dice > 0 else 0.0
        return bid_ratio / max(info_ratio, 0.01)

    def _pressure_opportunity_score(
        self,
        next_player_num_dice: int,
        total_dice: int,
        current_bid_count: int,
    ) -> float:
        """Returns a score 0.0–1.0 representing how much pressure can be applied to
        the next player. High when: next player has few dice (low info window, high
        personal stakes) AND there is room to escalate the current bid count."""
        if total_dice == 0:
            return 0.0
        next_info_ratio = next_player_num_dice / total_dice
        next_blind_stake = 1.0 - next_info_ratio
        room_to_escalate = 1.0 - (current_bid_count / total_dice)
        return next_blind_stake * room_to_escalate

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
        pressure_hint: float = 0.0,
    ) -> 'tuple[Bid | None, float]':
        if not permissible:
            return None, 0.0
        risk_ranking: list[list] = []
        for legal_bid in permissible:
            nc = needed_cnt(dice[:num_dice], legal_bid)
            bid_probability = 1.0 if nc <= 0 else 1.0 - model.cdf(nc - 1)
            risk_ranking.append([bid_probability, legal_bid])
        risk_ranking.sort(key=lambda x: x[0], reverse=True)
        if pressure_hint > _PRESSURE_OPP_THRESHOLD:
            best_prob = risk_ranking[0][0]
            near_best = [row for row in risk_ranking if row[0] >= best_prob - 0.05]
            near_best.sort(key=lambda x: (x[0], x[1].count), reverse=True)
            best_bid_probability = near_best[0][0]
            best_bids = [row[1] for row in near_best if row[0] == best_bid_probability]
            crowd_pick = self._apply_crowd_preference(best_bids, all_prev_bids)
            if crowd_pick is not None:
                return crowd_pick, best_bid_probability
            return near_best[0][1], best_bid_probability
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
        cunning = self.positional_cunning / Constants.MAX_POSITIONAL_CUNNING_SCORE
        if ctx.blind_aggression_score > _BLIND_AGGRESSION_THRESHOLD:
            boost_magnitude = min(
                _CHALLENGE_BOOST_MAX,
                (ctx.blind_aggression_score - _BLIND_AGGRESSION_THRESHOLD) * 0.1 * cunning,
            )
            effective_challenge_prob = min(1.0, ctx.challenge_prob + boost_magnitude)
            effective_threshold = max(0.10, ctx.effective_threshold - boost_magnitude * 0.5)
        else:
            effective_challenge_prob = ctx.challenge_prob
            effective_threshold = ctx.effective_threshold
        effective_challenge_prob = effective_challenge_prob if effective_challenge_prob >= effective_threshold else 0.0
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


_FACE_WORDS = {1: 'ones', 2: 'twos', 3: 'threes', 4: 'fours', 5: 'fives', 6: 'sixes'}
_HISTORY_MAX = 10


class LLMStrategy:
    player_type: str = 'LLM'

    def __init__(self, model: str = "gemma3:4b", temperature: float = 0.3) -> None:
        self._model = model
        self._temperature = temperature
        self._history: list[str] = []

    def reset(self) -> None:
        self._history = []

    def observe_action(self, player_name: str, action: Action, bid: 'Bid | None', total_dice: int) -> None:
        if action == Action.BID and bid is not None:
            entry = f"{player_name} bid {bid.count} {_FACE_WORDS.get(bid.face, bid.face)}"
        elif action == Action.RAISE and bid is not None:
            entry = f"{player_name} raised to {bid.count} {_FACE_WORDS.get(bid.face, bid.face)}"
        elif action == Action.CHALLENGE:
            entry = f"{player_name} challenged"
        elif action == Action.SPOT_ON:
            entry = f"{player_name} called spot on"
        else:
            return
        self._history.append(entry)
        if len(self._history) > _HISTORY_MAX:
            del self._history[: len(self._history) - _HISTORY_MAX]

    def observe_outcome(self, bidder_name: str, challenge_succeeded: bool) -> None:
        pass

    def decide(
        self,
        player_name: str,
        dice: list[int],
        num_dice: int,
        prev_events: deque,
        tot_other_dice: int,
        bidder_num_dice: int,
        next_player_num_dice: int = 0,
    ) -> TurnResult:
        prev_event = prev_events[0]
        prompt = self._build_prompt(dice[:num_dice], tot_other_dice, prev_event)
        raw = query_llm(self._model, prompt, temperature=self._temperature)
        result = self._parse_response(raw, player_name)
        if prev_event.action == Action.START:
            return result if result is not None else TurnResult(Bid(2, 3), Action.BID, player_name)
        return result if result is not None else TurnResult(None, Action.CHALLENGE, player_name)

    def _build_prompt(self, dice: list[int], tot_other_dice: int, prev_event: TurnResult) -> str:
        prev_desc = (
            f"action={prev_event.action.value}, bid={prev_event.bid}"
            if prev_event.bid
            else f"action={prev_event.action.value}"
        )
        rules = (
            "Rules: A bid claims that AT LEAST <count> dice across all players show <face>. "
            "Challenge accuses the previous bidder of lying; spot-on claims the bid count is exactly correct. "
            "Ones (1s) are wild and count as any face."
        )
        history_section = ""
        if self._history:
            recent = self._history[-_HISTORY_MAX:]
            history_section = "Recent history:\n" + "\n".join(f"  - {line}" for line in recent) + "\n"
        return (
            f"You are playing Liar's Dice.\n"
            f"{rules}\n"
            f"Your dice: {dice}\n"
            f"Total dice held by other players: {tot_other_dice}\n"
            f"{history_section}"
            f"Previous action: {prev_desc}\n"
            f"Respond with only valid JSON, no markdown, no explanation.\n"
            f"Use this exact format:\n"
            f'  {{"action": "bid|raise|challenge|spot_on", "count": <int>, "face": <int>}}\n'
            f"count and face are only required when action is bid or raise."
        )

    def _parse_response(self, raw: 'str | None', player_name: str) -> 'TurnResult | None':
        if raw is None:
            logger.warning('LLMStrategy: received None response from LLM')
            return None
        try:
            stripped = raw.strip()
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', stripped, re.DOTALL)
                if not match:
                    raise ValueError('no JSON object found in response')
                data = json.loads(match.group())
            action_str = data['action'].lower().replace(' ', '_')
            action_map = {
                'bid': Action.BID,
                'raise': Action.RAISE,
                'challenge': Action.CHALLENGE,
                'spot_on': Action.SPOT_ON,
            }
            action = action_map[action_str]
            bid = None
            if action in (Action.BID, Action.RAISE):
                bid = Bid(int(data['count']), int(data['face']))
            return TurnResult(bid, action, player_name)
        except Exception as exc:
            logger.warning('LLMStrategy: failed to parse LLM response %r: %s', raw, exc)
            return None


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
        next_player_num_dice: int = 0,
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
