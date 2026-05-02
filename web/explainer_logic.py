"""CPU Logic Explainer — scenario engine.

Walks `CPUStrategy.decide()` step by step for a curated scenario, capturing
intermediate state into an `ExplainerResult` for the web UI to render. The
explainer reuses the strategy's actual private methods so the math shown is
always the math the CPU runs in production — if `strategy.py` changes, only
the narrative templates here need updating.

Scope: response-to-bid path only (opening-bid path excluded in v1).
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, asdict, replace
from typing import Any

import constants as Constants
from dice_math import needed_cnt
from models import Action, Bid, OpponentProfile, ResponseContext, TurnResult
from strategy import CPUStrategy, _BLIND_AGGRESSION_THRESHOLD, _CHALLENGE_BOOST_MAX, _CUNNING_FACTOR


@dataclass(frozen=True)
class ExplainerScenario:
    id: str
    title: str
    summary: str
    narrative_intro: str
    dice: list[int]
    num_dice: int
    prev_bid: Bid
    prev_bidder: str
    tot_other_dice: int
    bidder_num_dice: int
    next_player_num_dice: int
    risk_appetite: int
    attentiveness_score: int
    bluff_frequency: int
    rng_seed: int
    num_active_players: int = 4
    archetype_label: 'str | None' = None
    opponent_profile: OpponentProfile | None = None


@dataclass(frozen=True)
class ExplainerStep:
    step_id: str
    title: str
    narrative: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ExplainerResult:
    scenario: ExplainerScenario
    steps: list[ExplainerStep]
    final_decision: TurnResult


_FACE_NAMES = {1: 'ones', 2: 'twos', 3: 'threes', 4: 'fours', 5: 'fives', 6: 'sixes'}


def _round(x: float, dp: int = 4) -> float:
    return round(float(x), dp)


def _build_strategy(scenario: ExplainerScenario) -> CPUStrategy:
    """Construct a deterministic CPUStrategy with scenario personality + profiles.

    Reseeds `_rng` after `__init__` so decide-time RNG is independent of how
    many cycles trait sampling consumed during construction.
    """
    strategy = CPUStrategy(random.Random(scenario.rng_seed))
    strategy._set_personality(
        risk_appetite=scenario.risk_appetite,
        attentiveness_score=scenario.attentiveness_score,
        bluff_frequency=scenario.bluff_frequency,
        archetype_label=scenario.archetype_label,
    )
    if scenario.opponent_profile is not None:
        strategy.opponent_profiles[scenario.prev_bidder] = replace(scenario.opponent_profile)
    strategy._rng = random.Random(scenario.rng_seed + 1)
    return strategy


def _step_roll(scenario: ExplainerScenario) -> ExplainerStep:
    total = scenario.num_dice + scenario.tot_other_dice
    narrative = (
        f"The CPU rolls {scenario.num_dice} dice in a game with {total} dice in play "
        f"({scenario.tot_other_dice} held by other players). It can see only its own "
        f"hand — every other die is hidden behind a cup."
    )
    return ExplainerStep(
        step_id='roll',
        title='1. The Roll',
        narrative=narrative,
        data={
            'dice': scenario.dice[:scenario.num_dice],
            'num_dice': scenario.num_dice,
            'tot_other_dice': scenario.tot_other_dice,
            'total_dice': total,
        },
    )


def _step_stats(strategy: CPUStrategy, scenario: ExplainerScenario) -> ExplainerStep:
    strategy._compute_dice_stats(scenario.dice, scenario.num_dice)
    mode_face = strategy._rolls_mode
    mode_count = strategy._mode_count
    narrative = (
        f"Most common face in hand: {mode_face} ({_FACE_NAMES[mode_face]}). "
        f"Counting wilds (1s also count as any face), the CPU effectively holds "
        f"{mode_count} {_FACE_NAMES[mode_face]} — the strongest face in its own hand."
    )
    return ExplainerStep(
        step_id='stats',
        title='2. Read the Hand',
        narrative=narrative,
        data={
            'mode_face': mode_face,
            'mode_count': mode_count,
        },
    )


def _step_evaluate_bid(scenario: ExplainerScenario) -> ExplainerStep:
    nc = needed_cnt(scenario.dice[:scenario.num_dice], scenario.prev_bid)
    bid = scenario.prev_bid
    narrative = (
        f"Previous bid: {bid.count} {_FACE_NAMES[bid.face]} (by {scenario.prev_bidder}). "
        f"The CPU computes how many MORE {_FACE_NAMES[bid.face]} would have to come from "
        f"the other players for the bid to be true: {nc}. "
        f"If this number were negative the CPU would auto-raise (its hand alone covers the bid). "
        f"Here it's {nc}, so the CPU evaluates the full set of options."
    )
    return ExplainerStep(
        step_id='evaluate-bid',
        title='3. Evaluate the Bid',
        narrative=narrative,
        data={
            'prev_bid_count': bid.count,
            'prev_bid_face': bid.face,
            'prev_bidder': scenario.prev_bidder,
            'needed_cnt': nc,
            'auto_raise_short_circuit': nc < 0,
        },
    )


def _step_context(strategy: CPUStrategy, scenario: ExplainerScenario,
                  ctx: ResponseContext) -> ExplainerStep:
    bid = scenario.prev_bid
    n_others = max(0, scenario.num_active_players - 1)
    total_dice = scenario.num_dice + scenario.tot_other_dice
    info_ratio = scenario.bidder_num_dice / total_dice if total_dice > 0 else 0.0
    bid_ratio = bid.count / total_dice if total_dice > 0 else 0.0

    bas_breakdown = (
        f"{scenario.prev_bidder} holds {scenario.bidder_num_dice} of {total_dice} dice "
        f"({info_ratio * 100:.1f}% information window) but claimed {bid.count} {_FACE_NAMES[bid.face]} "
        f"— {bid_ratio * 100:.1f}% of all dice. "
        f"BAS = {bid_ratio * 100:.1f}% ÷ {info_ratio * 100:.1f}% = {_round(ctx.blind_aggression_score):.2f} "
        f"({'above' if ctx.blind_aggression_score > _BLIND_AGGRESSION_THRESHOLD else 'below'} "
        f"the {_BLIND_AGGRESSION_THRESHOLD} threshold)."
    )

    profile = strategy.opponent_profiles.get(scenario.prev_bidder)
    if profile and profile.bids_observed >= 1:
        profile_narrative = (
            f"The CPU has also built a profile of {scenario.prev_bidder} through `observe_action()` "
            f"— every bid the CPU witnesses is recorded. Over {profile.bids_observed} observed bid(s), "
            f"this player has averaged {_round(profile.avg_aggression):.2f} aggression "
            f"(fraction of table dice claimed per bid; >0.5 is aggressive). "
        )
        if profile.bids_challenged >= 1:
            profile_narrative += (
                f"Of {profile.bids_challenged} challenge(s) against them, "
                f"{profile.challenge_successes} succeeded — a {_round(profile.bluff_rate * 100, 1):.0f}% bluff rate "
                f"(smoothed). This record feeds both the challenge-probability boost and the "
                f"threshold adjustment in the next step."
            )
        else:
            profile_narrative += (
                f"No challenge history on this player yet, so only the aggression boost applies."
            )
    else:
        profile_narrative = (
            f"No prior observations of {scenario.prev_bidder} — opponent profile effects are absent."
        )

    narrative = (
        f"The CPU evaluates probabilities and situational scores. "
        f"Challenge probability ({_round(ctx.challenge_prob):.2f}) estimates the chance the previous bid is a lie. "
        f"Spot-on probability ({_round(ctx.spot_on_prob):.2f}) is the chance the bid is exactly correct; "
        f"with {n_others} other player(s) on the table that translates to a spot-on EV of "
        f"{_round(ctx.spot_on_ev):+.2f} dice. "
        f"Best-bid probability ({_round(ctx.best_bid_prob):.2f}) is the chance the CPU's strongest legal bid would be true. "
        f"Blind aggression score ({_round(ctx.blind_aggression_score):.2f}) measures how much "
        f"the bidder claimed beyond their own information window — values above "
        f"{_BLIND_AGGRESSION_THRESHOLD} suggest they are bluffing or guessing blindly. "
        f"{bas_breakdown} "
        f"Pressure-opportunity score ({_round(ctx.pressure_opportunity_score):.2f}) measures how much "
        f"the next player can be squeezed (low information + room to escalate). "
        f"{profile_narrative}"
    )
    best_bid_desc = (
        f"{ctx.best_bid.count} {_FACE_NAMES[ctx.best_bid.face]}"
        if ctx.best_bid is not None else 'none'
    )
    return ExplainerStep(
        step_id='context',
        title='4. Build Response Context',
        narrative=narrative,
        data={
            'prev_bid_count': bid.count,
            'prev_bid_face': bid.face,
            'challenge_prob': _round(ctx.challenge_prob),
            'effective_threshold': _round(ctx.effective_threshold),
            'spot_on_prob': _round(ctx.spot_on_prob),
            'spot_on_ev': _round(ctx.spot_on_ev),
            'num_active_players': scenario.num_active_players,
            'best_bid_count': ctx.best_bid.count if ctx.best_bid else None,
            'best_bid_face': ctx.best_bid.face if ctx.best_bid else None,
            'best_bid_desc': best_bid_desc,
            'best_bid_prob': _round(ctx.best_bid_prob),
            'blind_aggression_score': _round(ctx.blind_aggression_score),
            'blind_aggression_threshold': _BLIND_AGGRESSION_THRESHOLD,
            'bidder_num_dice': scenario.bidder_num_dice,
            'total_dice': total_dice,
            'bidder_info_ratio': _round(info_ratio, 4),
            'bid_count_ratio': _round(bid_ratio, 4),
            'pressure_opportunity_score': _round(ctx.pressure_opportunity_score),
            'opponent_bids_observed': profile.bids_observed if profile else 0,
            'opponent_avg_aggression': _round(profile.avg_aggression) if profile else None,
            'opponent_bids_challenged': profile.bids_challenged if profile else 0,
            'opponent_challenge_successes': profile.challenge_successes if profile else 0,
            'opponent_bluff_rate': _round(profile.bluff_rate) if profile and profile.bids_challenged >= 1 else None,
        },
    )


def _step_personality(strategy: CPUStrategy, ctx: ResponseContext) -> ExplainerStep:
    bas_above = ctx.blind_aggression_score > _BLIND_AGGRESSION_THRESHOLD
    if bas_above:
        boost_magnitude = min(
            _CHALLENGE_BOOST_MAX,
            (ctx.blind_aggression_score - _BLIND_AGGRESSION_THRESHOLD) * 0.1 * _CUNNING_FACTOR,
        )
        boosted_prob = min(1.0, ctx.challenge_prob + boost_magnitude)
        boosted_threshold = max(0.50, ctx.effective_threshold - boost_magnitude * 0.5)
    else:
        boost_magnitude = 0.0
        boosted_prob = ctx.challenge_prob
        boosted_threshold = ctx.effective_threshold

    archetype_phrase = (
        f"as a {strategy.archetype_label}, " if strategy.archetype_label else ''
    )
    if bas_above and boost_magnitude > 0:
        narrative = (
            f"{archetype_phrase.capitalize()}risk appetite ({strategy.risk_appetite}/100), "
            f"attentiveness ({strategy.attentiveness_score}/100), and bluff frequency "
            f"({strategy.bluff_frequency}/100) tune the thresholds. "
            f"This bidder is over-claiming (blind aggression "
            f"{_round(ctx.blind_aggression_score):.2f} > {_BLIND_AGGRESSION_THRESHOLD}), so cunning amplifies suspicion: "
            f"the challenge probability gets boosted by {_round(boost_magnitude):.3f} "
            f"({_round(ctx.challenge_prob):.2f} → {_round(boosted_prob):.2f}) "
            f"and the effective threshold drops to {_round(boosted_threshold):.2f}."
        )
    else:
        narrative = (
            f"{archetype_phrase.capitalize()}risk appetite ({strategy.risk_appetite}/100), "
            f"attentiveness ({strategy.attentiveness_score}/100), and bluff frequency "
            f"({strategy.bluff_frequency}/100) tune the thresholds. "
            f"Blind aggression score ({_round(ctx.blind_aggression_score):.2f}) is at or below "
            f"{_BLIND_AGGRESSION_THRESHOLD}, so no challenge boost applies."
        )
    return ExplainerStep(
        step_id='personality',
        title='5. Apply Personality',
        narrative=narrative,
        data={
            'risk_appetite': strategy.risk_appetite,
            'attentiveness_score': strategy.attentiveness_score,
            'bluff_frequency': strategy.bluff_frequency,
            'archetype_label': strategy.archetype_label,
            'spot_on_ev_bias': _round(strategy.spot_on_ev_bias),
            'challenge_threshold': _round(strategy.challenge_threshold),
            'cunning_factor': _CUNNING_FACTOR,
            'blind_aggression_active': bas_above,
            'boost_magnitude': _round(boost_magnitude),
            'effective_challenge_prob': _round(boosted_prob),
            'effective_challenge_threshold': _round(boosted_threshold),
        },
    )


def _step_decision(strategy: CPUStrategy, scenario: ExplainerScenario,
                   ctx: ResponseContext, decision: TurnResult) -> ExplainerStep:
    if ctx.blind_aggression_score > _BLIND_AGGRESSION_THRESHOLD:
        boost_magnitude = min(
            _CHALLENGE_BOOST_MAX,
            (ctx.blind_aggression_score - _BLIND_AGGRESSION_THRESHOLD) * 0.1 * _CUNNING_FACTOR,
        )
        eff_prob = min(1.0, ctx.challenge_prob + boost_magnitude)
        eff_threshold = max(0.50, ctx.effective_threshold - boost_magnitude * 0.5)
    else:
        eff_prob = ctx.challenge_prob
        eff_threshold = ctx.effective_threshold
    challenge_passes = eff_prob >= eff_threshold
    ev_challenge_raw = 2 * eff_prob - 1
    ev_challenge_gated = ev_challenge_raw if challenge_passes else float('-inf')
    ev_spot_on = ctx.spot_on_ev + strategy.spot_on_ev_bias
    ev_bid = 0.0

    action_label = decision.action.value
    bid_desc = (f" — {decision.bid.count} {_FACE_NAMES[decision.bid.face]}"
                if decision.bid is not None else "")

    if decision.action == Action.CHALLENGE and decision.bid is None and ctx.best_bid is None and not challenge_passes:
        reason = (
            "No legal bid was available and no other +EV action existed, so the CPU "
            "falls back to CHALLENGE."
        )
        branch = 'fallback_zero'
    elif decision.action == Action.CHALLENGE:
        if ctx.blind_aggression_score > _BLIND_AGGRESSION_THRESHOLD:
            reason = (
                f"After the blind-aggression boost, challenge probability "
                f"({_round(eff_prob):.2f}) cleared the {_round(eff_threshold):.2f} threshold; "
                f"its EV ({_round(ev_challenge_raw):+.2f} dice) beats spot-on "
                f"({_round(ev_spot_on):+.2f}) and the bid baseline (0.00)."
            )
        else:
            reason = (
                f"Challenge probability ({_round(eff_prob):.2f}) cleared the "
                f"{_round(eff_threshold):.2f} break-even threshold; its EV "
                f"({_round(ev_challenge_raw):+.2f} dice) beats spot-on "
                f"({_round(ev_spot_on):+.2f}) and the bid baseline (0.00)."
            )
        branch = 'challenge_ev'
    elif decision.action == Action.SPOT_ON:
        reason = (
            f"Spot-on EV ({_round(ev_spot_on):+.2f} dice) is positive and beats both "
            f"the bid baseline (0.00) and challenge ({_round(ev_challenge_raw):+.2f}). "
            f"With {scenario.num_active_players} players on the table the exact-count "
            f"payoff outweighs the cost of being wrong."
        )
        branch = 'spot_on_ev'
    elif decision.action == Action.RAISE:
        reason = (
            f"Neither challenge nor spot-on cleared the bid baseline (0.00). "
            f"Best legal bid ({_round(ctx.best_bid_prob):.2f} P(true)) wins, and its "
            f"count exceeds the previous bid, so this is a RAISE."
        )
        branch = 'raise'
    else:
        reason = (
            f"Neither challenge nor spot-on cleared the bid baseline (0.00). "
            f"Best legal bid ({_round(ctx.best_bid_prob):.2f} P(true)) wins; its count "
            f"matches the previous bid, so this is a same-count BID on a different face."
        )
        branch = 'bid'

    narrative = f"Decision: {action_label}{bid_desc}. {reason}"
    return ExplainerStep(
        step_id='decision',
        title='6. The Decision',
        narrative=narrative,
        data={
            'action': decision.action.value,
            'bid_count': decision.bid.count if decision.bid else None,
            'bid_face': decision.bid.face if decision.bid else None,
            'effective_challenge_prob': _round(eff_prob if challenge_passes else 0.0),
            'effective_challenge_threshold': _round(eff_threshold),
            'ev_challenge': _round(ev_challenge_raw if challenge_passes else 0.0),
            'ev_spot_on': _round(ev_spot_on),
            'ev_bid_baseline': _round(ev_bid),
            'branch': branch,
            'reason': reason,
        },
    )


def run_scenario(scenario_id: str) -> ExplainerResult:
    """Walk CPUStrategy.decide() phase by phase for the named scenario."""
    if scenario_id not in SCENARIOS:
        raise KeyError(f'Unknown scenario: {scenario_id!r}')
    scenario = SCENARIOS[scenario_id]
    strategy = _build_strategy(scenario)

    steps: list[ExplainerStep] = []
    steps.append(_step_roll(scenario))
    steps.append(_step_stats(strategy, scenario))
    steps.append(_step_evaluate_bid(scenario))

    prev_event = TurnResult(scenario.prev_bid, Action.BID, scenario.prev_bidder)
    all_prev_bids = {scenario.prev_bid}
    ctx = strategy._build_response_context(
        scenario.dice,
        scenario.num_dice,
        prev_event,
        scenario.tot_other_dice,
        scenario.bidder_num_dice,
        all_prev_bids,
        scenario.next_player_num_dice,
        scenario.num_active_players,
    )
    steps.append(_step_context(strategy, scenario, ctx))
    steps.append(_step_personality(strategy, ctx))

    decision = strategy._decide_action('CPU', ctx)
    steps.append(_step_decision(strategy, scenario, ctx, decision))

    return ExplainerResult(scenario=scenario, steps=steps, final_decision=decision)


def list_scenarios() -> list[dict[str, str]]:
    return [
        {'id': s.id, 'title': s.title, 'summary': s.summary}
        for s in SCENARIOS.values()
    ]


SCENARIOS: dict[str, ExplainerScenario] = {
    'confident-bid': ExplainerScenario(
        id='confident-bid',
        title='The Confident Raise',
        summary='Strong hand, modest standing bid — the CPU raises with high confidence.',
        narrative_intro=(
            "The CPU holds three twos against a low-count bid. With a strong hand and "
            "plenty of room above the current count, it backs itself to escalate."
        ),
        dice=[2, 2, 2, 3, 4],
        num_dice=5,
        prev_bid=Bid(count=4, face=2),
        prev_bidder='Bootstrap Bill Turner',
        tot_other_dice=10,
        bidder_num_dice=4,
        next_player_num_dice=4,
        risk_appetite=70,
        attentiveness_score=50,
        bluff_frequency=20,
        rng_seed=101,
        num_active_players=4,
        archetype_label='Reckless Buccaneer',
    ),
    'challenge-aggressor': ExplainerScenario(
        id='challenge-aggressor',
        title='Calling the Bluff',
        summary='Bid just above table average from a known over-claimer — opponent history tips a borderline challenge.',
        narrative_intro=(
            "The bidder has six dice and claimed seven threes — just a hair above the table's expected count. "
            "The raw math gives a 56% challenge probability, just below the CPU's 57.5% break-even threshold: "
            "not enough to challenge on numbers alone. But the CPU has been watching: this player has a 67% "
            "bluff success rate when challenged. That history lowers the threshold below 56%, turning a "
            "'probably not' into a confident 'call'."
        ),
        dice=[3, 3, 3, 5, 6],
        num_dice=5,
        prev_bid=Bid(count=7, face=3),
        prev_bidder='Captain Blackbeard',
        tot_other_dice=10,
        bidder_num_dice=6,
        next_player_num_dice=2,
        risk_appetite=50,
        attentiveness_score=80,
        bluff_frequency=20,
        rng_seed=202,
        num_active_players=4,
        archetype_label='Crafty Captain',
        opponent_profile=OpponentProfile(
            bids_observed=4,
            total_aggression=2.6,
            bids_challenged=3,
            challenge_successes=2,
        ),
    ),
    'spot-on-spike': ExplainerScenario(
        id='spot-on-spike',
        title='The Spot-On Spike',
        summary='Bid count maxes the table — the exact-count probability beats every legal alternative.',
        narrative_intro=(
            "The bid is at the absolute ceiling — there are exactly six dice held by other players "
            "and the bidder claimed six fours total. With four fours of its own, the CPU only needs "
            "two more fours from the others. The exact-count probability lands at the binomial peak "
            "and beats every same-count alternative (raises are blocked because the bid already maxes the table)."
        ),
        dice=[4, 4, 4, 4, 5],
        num_dice=5,
        prev_bid=Bid(count=6, face=4),
        prev_bidder='Calypso',
        tot_other_dice=6,
        bidder_num_dice=5,
        next_player_num_dice=1,
        risk_appetite=40,
        attentiveness_score=40,
        bluff_frequency=10,
        rng_seed=303,
        num_active_players=4,
        archetype_label='Salty Veteran',
    ),
    'blind-aggression-trigger': ExplainerScenario(
        id='blind-aggression-trigger',
        title='Cunning Sees the Bluff',
        summary='Bidder claimed far beyond their information window — high cunning amplifies suspicion into a challenge.',
        narrative_intro=(
            "The bidder has only one die but claimed nine fours in a 15-dice game. "
            "The CPU is already 5/9 of the way there from its own hand; its high "
            "positional cunning spots how blind the over-claim is and pushes the boosted "
            "challenge probability above the break-even threshold."
        ),
        dice=[4, 4, 4, 4, 4],
        num_dice=5,
        prev_bid=Bid(count=9, face=4),
        prev_bidder='Lord Cutler Beckett',
        tot_other_dice=10,
        bidder_num_dice=1,
        next_player_num_dice=4,
        risk_appetite=80,
        attentiveness_score=90,
        bluff_frequency=30,
        rng_seed=404,
        num_active_players=4,
        archetype_label='Crafty Captain',
    ),
    'pressure-opportunity': ExplainerScenario(
        id='pressure-opportunity',
        title='Pressure the Short Stack',
        summary='Next player is down to one die — pressure-opportunity tilts the CPU toward the higher-count raise.',
        narrative_intro=(
            "Two equally-strong bids are on the table: a same-count bid on a new face, "
            "or a raise on the standing face. The next player has only one die and limited "
            "info, so the CPU's positional cunning picks the higher-count raise to squeeze them."
        ),
        dice=[4, 4, 3],
        num_dice=3,
        prev_bid=Bid(count=3, face=4),
        prev_bidder='Sao Feng',
        tot_other_dice=10,
        bidder_num_dice=3,
        next_player_num_dice=1,
        risk_appetite=50,
        attentiveness_score=70,
        bluff_frequency=40,
        rng_seed=505,
        num_active_players=4,
        archetype_label='Crafty Captain',
    ),
}
