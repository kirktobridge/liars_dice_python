from statistics import mode
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
from llm_client import query_llm, query_llm_stream

logger = logging.getLogger('liars_dice.strategy')

_BLIND_AGGRESSION_THRESHOLD = 1.4
_CHALLENGE_BOOST_MAX = 0.15
_PRESSURE_OPP_THRESHOLD = 0.30
# Always-on cunning factor (replaces the positional_cunning trait gate).
_CUNNING_FACTOR = 0.5


def _clamp_trait(value: int) -> int:
    return max(1, min(100, value))


@dataclass
class Personality:
    risk_appetite: int
    attentiveness_score: int
    bluff_frequency: int
    spot_on_ev_bias: float
    challenge_threshold: float
    archetype_label: 'str | None' = None

    @classmethod
    def from_traits(
        cls,
        *,
        risk_appetite: int,
        attentiveness_score: int,
        bluff_frequency: int,
        spot_on_jitter: float = 0.0,
        challenge_jitter: float = 0.0,
        archetype_label: 'str | None' = None,
    ) -> 'Personality':
        risk_fraction = risk_appetite / Constants.MAX_RISK_SCORE
        # Risk-seeking players accept slightly worse spot-on EVs; cautious players require margin.
        spot_on_ev_bias = (risk_fraction - 0.5) * 0.4 + spot_on_jitter
        # Floor at break-even (0.50). Risk only narrows the safety margin above 0.50.
        challenge_threshold = max(0.50, 0.65 - risk_fraction * 0.15 + challenge_jitter)
        return cls(
            risk_appetite=risk_appetite,
            attentiveness_score=attentiveness_score,
            bluff_frequency=bluff_frequency,
            spot_on_ev_bias=spot_on_ev_bias,
            challenge_threshold=challenge_threshold,
            archetype_label=archetype_label,
        )

    @classmethod
    def from_archetype(cls, label: str, rng: random.Random) -> 'Personality':
        spec = next((a for a in Constants.ARCHETYPES if a['label'] == label), None)
        if spec is None:
            raise ValueError(f'Unknown archetype: {label!r}')
        j = Constants.TRAIT_JITTER
        return cls.from_traits(
            risk_appetite=_clamp_trait(spec['risk'] + rng.randint(-j, j)),
            attentiveness_score=_clamp_trait(spec['att'] + rng.randint(-j, j)),
            bluff_frequency=_clamp_trait(spec['bluff'] + rng.randint(-j, j)),
            spot_on_jitter=rng.uniform(-0.03, 0.03),
            challenge_jitter=rng.uniform(-0.03, 0.03),
            archetype_label=label,
        )

    @classmethod
    def random(cls, rng: random.Random) -> 'Personality':
        weights = [a['weight'] for a in Constants.ARCHETYPES]
        spec = rng.choices(Constants.ARCHETYPES, weights=weights, k=1)[0]
        return cls.from_archetype(spec['label'], rng)


@runtime_checkable
class Strategy(Protocol):
    player_type: str

    def decide(
        self,
        player_name: str,
        dice: list[int],
        num_dice: int,
        recent_events: 'deque[TurnResult]',
        tot_other_dice: int,
        bidder_num_dice: int,
        next_player_num_dice: int,
        num_active_players: int,
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
    def attentiveness_score(self) -> int:
        return self.personality.attentiveness_score

    @attentiveness_score.setter
    def attentiveness_score(self, value: int) -> None:
        self.personality.attentiveness_score = value

    @property
    def bluff_frequency(self) -> int:
        return self.personality.bluff_frequency

    @bluff_frequency.setter
    def bluff_frequency(self, value: int) -> None:
        self.personality.bluff_frequency = value

    @property
    def archetype_label(self) -> 'str | None':
        return self.personality.archetype_label

    @property
    def spot_on_ev_bias(self) -> float:
        return self.personality.spot_on_ev_bias

    @spot_on_ev_bias.setter
    def spot_on_ev_bias(self, value: float) -> None:
        self.personality.spot_on_ev_bias = value

    @property
    def challenge_threshold(self) -> float:
        return self.personality.challenge_threshold

    @challenge_threshold.setter
    def challenge_threshold(self, value: float) -> None:
        self.personality.challenge_threshold = value

    def _set_personality(
        self,
        risk_appetite: int,
        attentiveness_score: int,
        bluff_frequency: int,
        spot_on_jitter: float = 0.0,
        challenge_jitter: float = 0.0,
        archetype_label: 'str | None' = None,
    ) -> None:
        self.personality = Personality.from_traits(
            risk_appetite=risk_appetite,
            attentiveness_score=attentiveness_score,
            bluff_frequency=bluff_frequency,
            spot_on_jitter=spot_on_jitter,
            challenge_jitter=challenge_jitter,
            archetype_label=archetype_label,
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
        recent_events: 'deque[TurnResult]',
        tot_other_dice: int,
        bidder_num_dice: int,
        next_player_num_dice: int = 0,
        num_active_players: int = 2,
    ) -> TurnResult:
        last = recent_events[0]
        last_action = last.action
        self._compute_dice_stats(dice, num_dice)

        if last_action == Action.START:
            return self._make_opening_bid(player_name, dice, num_dice, tot_other_dice)

        if last_action == Action.BID or last_action == Action.RAISE:
            prev_bid = last.bid
            if needed_cnt(dice[:num_dice], prev_bid) < 0:
                return TurnResult(Bid(prev_bid.count + 1, prev_bid.face), Action.RAISE, player_name)

            all_prev_bids: set[Bid] = {
                ev.bid for ev in recent_events
                if ev.action in (Action.BID, Action.RAISE)
            }
            ctx = self._build_response_context(
                dice, num_dice, last, tot_other_dice, bidder_num_dice,
                all_prev_bids, next_player_num_dice, num_active_players)
            return self._decide_action(player_name, ctx)

        logger.error('last_action behavior missing. Last event: %s', last)
        raise Exception(f'CPUStrategy: last_action behavior missing. Last event: {last}')

    def _compute_dice_stats(self, dice: list[int], num_dice: int) -> None:
        active = dice[:num_dice]
        if num_dice > 1:
            self._rolls_mode = mode(active)
            self._mode_count = active.count(self._rolls_mode) + active.count(1)
        else:
            self._rolls_mode = active[0]
            self._mode_count = 1

    def _make_opening_bid(self, player_name: str, dice: list[int], num_dice: int,
                          tot_other_dice: int = 0) -> TurnResult:
        logger.debug('START received by %s', player_name)
        risk_fraction = self.risk_appetite / Constants.MAX_RISK_SCORE

        # Wilds-driven opening: cautious players never take it; bold players
        # sometimes open on 1s (no wild double-counting, but their hand alone covers a lot).
        wild_count = dice[:num_dice].count(1)
        if wild_count >= 2 and self._rng.random() < risk_fraction:
            count = max(Constants.MINIMUM_BID, wild_count + round(tot_other_dice / 6))
            return TurnResult(Bid(count, 1), Action.BID, player_name)

        # Expected count of any non-1 face among others = tot_other_dice / 3 (face hits + wilds).
        # Risk-averse openers underbid by ~1; risk-seeking match expected.
        expected_others = tot_other_dice / 3
        safety = 1.0 - risk_fraction
        if self._mode_count >= Constants.MINIMUM_BID:
            target = self._mode_count + expected_others - safety
            face = self._rolls_mode
        else:
            # No strong face in hand — pick a held face but bid more conservatively.
            target = expected_others - safety
            face = dice[self._rng.randint(0, num_dice - 1)]
        count = max(Constants.MINIMUM_BID, round(target))
        # Bluff tactic: with probability bluff_frequency/100, claim one more than EV justifies.
        if self._rng.random() < self.bluff_frequency / Constants.MAX_BLUFF_SCORE:
            count += 1
        # Cap the count so we never claim more than the table can hold.
        max_count = num_dice + tot_other_dice
        if max_count > 0:
            count = min(count, max_count)
        return TurnResult(Bid(count, face), Action.BID, player_name)

    def _build_response_context(
        self,
        dice: list[int],
        num_dice: int,
        prev_event: TurnResult,
        tot_other_dice: int,
        bidder_num_dice: int,
        all_prev_bids: set[Bid],
        next_player_num_dice: int = 0,
        num_active_players: int = 2,
    ) -> ResponseContext:
        prev_bid = prev_event.bid
        nc = needed_cnt(dice[:num_dice], prev_bid)
        model = get_binom(tot_other_dice)
        total_dice = num_dice + tot_other_dice
        bas = self._blind_aggression_score(bidder_num_dice, total_dice, prev_bid.count)
        pos = self._pressure_opportunity_score(next_player_num_dice, total_dice, prev_bid.count)
        permissible = self._get_permissible_bids(prev_bid.count, tot_other_dice, all_prev_bids)
        best_bid, best_bid_prob = self._rank_and_select_bid(
            dice, num_dice, permissible, model, all_prev_bids,
            pressure_hint=pos * _CUNNING_FACTOR)
        spot_on_prob = float(model.pmf(nc))
        n_others = max(0, num_active_players - 1)
        spot_on_ev = spot_on_prob * n_others - (1 - spot_on_prob) * 1
        return ResponseContext(
            prev_bid=prev_bid,
            challenge_prob=self._compute_challenge_probability(
                prev_event.player_name, tot_other_dice, bidder_num_dice, nc),
            effective_threshold=self._effective_challenge_threshold(prev_event.player_name),
            spot_on_prob=spot_on_prob,
            spot_on_ev=spot_on_ev,
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
        # Bayesian model: marginalize over the bidder's hidden hand. Always on —
        # this is strictly better math than the flat-tail estimate.
        prob = 0.0
        for j in range(bidder_num_dice + 1):
            needed_from_remaining = needed - j
            if needed_from_remaining <= 0:
                continue
            prob += bidder_model.pmf(j) * remaining_model.cdf(needed_from_remaining - 1)

        # With Beta(2,2) smoothing on OpponentProfile, even one observation is informative.
        _MIN_SAMPLES = 1
        _profile = self.opponent_profiles.get(bidder_name)
        _attention = self.attentiveness_score / Constants.MAX_ATTENTIVENESS_SCORE
        if _profile and _profile.bids_observed >= _MIN_SAMPLES:
            aggression_boost = 1.0 + (_profile.avg_aggression - 0.5) * 0.3 * _attention
            prob = min(1.0, prob * aggression_boost)
        return prob

    def _effective_challenge_threshold(self, bidder_name: str) -> float:
        _MIN_SAMPLES = 1
        effective_threshold = self.challenge_threshold
        _profile = self.opponent_profiles.get(bidder_name)
        _attention = self.attentiveness_score / Constants.MAX_ATTENTIVENESS_SCORE
        if _profile and _profile.bids_challenged >= _MIN_SAMPLES:
            bluff_adjustment = (_profile.bluff_rate - 0.5) * 0.4 * _attention
            # Floor at break-even — challenging below 0.50 P(success) is mathematically -EV.
            effective_threshold = max(0.50, self.challenge_threshold - bluff_adjustment)
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
        ranking: list[tuple[float, Bid]] = []
        for legal_bid in permissible:
            nc = needed_cnt(dice[:num_dice], legal_bid)
            bid_probability = 1.0 if nc <= 0 else 1.0 - model.cdf(nc - 1)
            ranking.append((bid_probability, legal_bid))
        ranking.sort(key=lambda row: row[0], reverse=True)

        if pressure_hint > _PRESSURE_OPP_THRESHOLD:
            # Pressure-driven CPUs widen the candidate window and prefer the highest count.
            best_prob = ranking[0][0]
            near_best = [row for row in ranking if row[0] >= best_prob - 0.05]
            near_best.sort(key=lambda row: (row[0], row[1].count), reverse=True)
            return near_best[0][1], near_best[0][0]

        return ranking[0][1], ranking[0][0]

    def _decide_action(self, player_name: str, ctx: ResponseContext) -> TurnResult:
        if ctx.blind_aggression_score > _BLIND_AGGRESSION_THRESHOLD:
            boost_magnitude = min(
                _CHALLENGE_BOOST_MAX,
                (ctx.blind_aggression_score - _BLIND_AGGRESSION_THRESHOLD) * 0.1 * _CUNNING_FACTOR,
            )
            effective_challenge_prob = min(1.0, ctx.challenge_prob + boost_magnitude)
            effective_threshold = max(0.50, ctx.effective_threshold - boost_magnitude * 0.5)
        else:
            effective_challenge_prob = ctx.challenge_prob
            effective_threshold = ctx.effective_threshold

        # EVs in dice units. Challenge & spot-on each cost or gain whole dice;
        # bidding is the baseline (no immediate die change).
        ev_challenge = (2 * effective_challenge_prob - 1) if effective_challenge_prob >= effective_threshold else float('-inf')
        ev_spot_on = ctx.spot_on_ev + self.spot_on_ev_bias
        ev_bid = 0.0

        # Prefer challenge if it's the highest +EV move.
        if ev_challenge >= 0 and ev_challenge >= ev_spot_on and ev_challenge >= ev_bid:
            return TurnResult(None, Action.CHALLENGE, player_name)

        # Spot-on if it strictly beats the bid baseline.
        if ev_spot_on > ev_bid and ev_spot_on >= ev_challenge:
            return TurnResult(None, Action.SPOT_ON, player_name)

        if ctx.best_bid is not None:
            action = Action.RAISE if ctx.best_bid.count > ctx.prev_bid.count else Action.BID
            return TurnResult(ctx.best_bid, action, player_name)

        # No legal bid available — fall back to challenge.
        return TurnResult(None, Action.CHALLENGE, player_name)


_FACE_WORDS = {1: 'ones', 2: 'twos', 3: 'threes', 4: 'fours', 5: 'fives', 6: 'sixes'}
_HISTORY_MAX = 10


class LLMStrategy:
    player_type: str = 'LLM'

    def __init__(
        self,
        model: str = Constants.LLM_MODEL,
        temperature: float = 0.3,
        timeout: float = 30.0,
        stream: bool = False,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._stream = stream
        self._history: list[str] = []
        self._fallback = CPUStrategy(random.Random())

    def reset(self) -> None:
        self._history = []
        self._fallback.reset()

    def observe_action(self, player_name: str, action: Action, bid: 'Bid | None', total_dice: int) -> None:
        self._fallback.observe_action(player_name, action, bid, total_dice)
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
        self._fallback.observe_outcome(bidder_name, challenge_succeeded)

    def decide(
        self,
        player_name: str,
        dice: list[int],
        num_dice: int,
        recent_events: 'deque[TurnResult]',
        tot_other_dice: int,
        bidder_num_dice: int,
        next_player_num_dice: int = 0,
        num_active_players: int = 2,
    ) -> TurnResult:
        last = recent_events[0]
        own = dice[:num_dice]
        prompt = self._build_prompt(own, tot_other_dice, last)
        result, illegality = self._query_and_validate(prompt, player_name, last)
        if result is None and illegality is not None:
            # One retry with the specific illegality fed back. Cheap insurance vs CPU fallback.
            retry_prompt = prompt + (
                f"\n\nYour previous response was rejected: {illegality}. "
                f"Reply again with corrected JSON."
            )
            result, _ = self._query_and_validate(retry_prompt, player_name, last)
        if result is not None:
            return result
        fallback_result = self._fallback.decide(
            player_name=player_name,
            dice=dice,
            num_dice=num_dice,
            recent_events=recent_events,
            tot_other_dice=tot_other_dice,
            bidder_num_dice=bidder_num_dice,
            next_player_num_dice=next_player_num_dice,
            num_active_players=num_active_players,
        )
        return TurnResult(
            bid=fallback_result.bid,
            action=fallback_result.action,
            player_name=fallback_result.player_name,
            fallback=True,
        )

    def _query_and_validate(
        self, prompt: str, player_name: str, last: TurnResult,
    ) -> 'tuple[TurnResult | None, str | None]':
        if self._stream:
            raw = query_llm_stream(self._model, prompt, timeout=self._timeout, temperature=self._temperature)
        else:
            raw = query_llm(self._model, prompt, timeout=self._timeout, temperature=self._temperature)
        result = self._parse_response(raw, player_name)
        if result is None:
            return None, 'response was not valid JSON in the requested format'
        # CHALLENGE / SPOT_ON are illegal on round open (no prior bid); the engine
        # would crash on `prev_bid.count`.
        if last.action == Action.START and result.action in (Action.CHALLENGE, Action.SPOT_ON):
            return None, (
                f'{result.action.value} is illegal on the opening turn (no previous bid); you must bid'
            )
        if result.action in (Action.BID, Action.RAISE):
            assert result.bid is not None
            if result.bid.count < Constants.MINIMUM_BID:
                return None, (
                    f'count {result.bid.count} is below the legal minimum of {Constants.MINIMUM_BID}'
                )
            if not (1 <= result.bid.face <= 6):
                return None, f'face {result.bid.face} is not a valid die face (must be 1-6)'
            if result.action == Action.RAISE and last.bid is not None:
                # Raise must strictly escalate: higher count, or same count + higher face.
                prev = last.bid
                escalates = (
                    result.bid.count > prev.count
                    or (result.bid.count == prev.count and result.bid.face > prev.face)
                )
                if not escalates:
                    return None, (
                        f'raise to {result.bid.count} {result.bid.face}s does not escalate '
                        f'previous bid of {prev.count} {prev.face}s '
                        f'(must increase count, or keep count and increase face)'
                    )
        return result, None

    def _build_prompt(self, dice: list[int], tot_other_dice: int, last: TurnResult) -> str:
        prev_desc = (
            f"action={last.action.value}, bid={last.bid}"
            if last.bid
            else f"action={last.action.value}"
        )
        total_dice = len(dice) + tot_other_dice
        rules = (
            "Rules: A bid claims AT LEAST <count> dice across the whole table show <face>. "
            "Challenge accuses the previous bidder of lying. Spot-on claims the bid count is exactly correct. "
            "Ones (1s) are wild and count as any face."
        )
        legality = (
            f"Constraints: count must be an integer >= {Constants.MINIMUM_BID}. "
            f"face must be an integer 1-6. "
            f"On the opening turn (action=start) you MUST bid -- challenge and spot_on are illegal. "
            f"A raise must strictly escalate the previous bid: either count goes up, or count stays "
            f"the same and face goes up."
        )
        sizing = self._sizing_hint(dice, tot_other_dice)
        challenge_guidance = self._challenge_guidance(dice, last, total_dice)
        history_section = ""
        if self._history:
            recent = self._history[-_HISTORY_MAX:]
            history_section = "Recent history:\n" + "\n".join(f"  - {line}" for line in recent) + "\n"
        return (
            f"You are playing Liar's Dice.\n"
            f"{rules}\n"
            f"{legality}\n"
            f"Your dice: {dice}\n"
            f"Total dice on the table: {total_dice} ({len(dice)} yours + {tot_other_dice} opponents')\n"
            f"{sizing}"
            f"{history_section}"
            f"Previous action: {prev_desc}\n"
            f"{challenge_guidance}"
            f"Respond with only valid JSON, no markdown, no explanation.\n"
            f"Use this exact format:\n"
            f'  {{"action": "bid|raise|challenge|spot_on", "count": <int>, "face": <int>}}\n'
            f"count and face are only required when action is bid or raise."
        )

    @staticmethod
    def _sizing_hint(dice: list[int], tot_other_dice: int) -> str:
        """Pre-computed bid suggestion. Anchors Gemma to a sensible count rather than letting
        her default to 1 or 2. Mirrors the math CPUStrategy uses for opening bids:
        expected count of any non-1 face among opponent dice = tot_other_dice / 3.
        """
        if not dice:
            return ""
        # Find the most-held face (excluding wilds), tie-break by face value.
        wilds = dice.count(1)
        non_wild = [d for d in dice if d != 1]
        if non_wild:
            best_face = max(set(non_wild), key=lambda f: (non_wild.count(f), f))
            best_matches = non_wild.count(best_face) + wilds
        else:
            best_face = 1
            best_matches = wilds
        expected_others = tot_other_dice // 3
        # Subtract a small safety margin so the suggestion lands below the EV truth-line.
        # Bidding at the expected count is ~50% to be true; bidding 1-2 below pushes
        # truth probability into the 65-80% range (mirrors CPUStrategy's safety term).
        safety = 1
        suggested = max(Constants.MINIMUM_BID, best_matches + expected_others - safety)
        return (
            f"Sizing guide: you hold {best_matches} dice toward face {best_face} (counting wilds). "
            f"Across {tot_other_dice} opponent dice, ~{expected_others} more of any non-1 face are expected. "
            f"A safe opening bid is around {suggested} {best_face}s -- bidding at the expected count is ~50% true, "
            f"so leave a small safety margin. Adjust based on history.\n"
        )

    @staticmethod
    def _challenge_guidance(dice: list[int], last: TurnResult, total_dice: int) -> str:
        """Anti-reflexive-challenge nudge. Most legal bids are truthful; only challenge when
        the standing claim is implausibly large vs. what's likely on the table.
        """
        if last.action != Action.BID and last.action != Action.RAISE:
            return ""
        if last.bid is None or total_dice <= 0:
            return ""
        # Rough plausibility: claim_ratio = bid_count / total_dice. Baseline P(any face) ≈ 1/3
        # including wilds, so ratios up to ~0.33 are routinely true.
        claim_ratio = last.bid.count / total_dice
        if claim_ratio < 0.30:
            posture = (
                f"The previous bid claims {last.bid.count}/{total_dice} = {claim_ratio:.0%} "
                f"of dice show face {last.bid.face}. This is below the ~33% baseline and is "
                f"very likely true; challenge is rarely correct here."
            )
        elif claim_ratio < 0.45:
            posture = (
                f"The previous bid claims {last.bid.count}/{total_dice} = {claim_ratio:.0%} "
                f"of dice. Around the truthful baseline; challenge only with strong reason."
            )
        else:
            posture = (
                f"The previous bid claims {last.bid.count}/{total_dice} = {claim_ratio:.0%} "
                f"of dice -- well above baseline; challenge becomes plausible."
            )
        return f"Plausibility cue: {posture}\n"

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
        recent_events: 'deque[TurnResult]',
        tot_other_dice: int,
        bidder_num_dice: int,
        next_player_num_dice: int = 0,
        num_active_players: int = 2,
    ) -> TurnResult:
        last = recent_events[0]
        if last.action == Action.START:
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
                'prev_bid': last.bid,
                'prev_player': last.player_name,
            })
        return TurnResult(resp.get('bid'), resp['action'], player_name)
