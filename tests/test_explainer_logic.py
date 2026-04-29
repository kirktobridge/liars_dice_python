import json
import random
from dataclasses import asdict

import pytest

from explainer_logic import (
    SCENARIOS,
    ExplainerStep,
    list_scenarios,
    run_scenario,
)
from dice_math import needed_cnt
from models import Action
from strategy import CPUStrategy


CANONICAL_STEP_IDS = ['roll', 'stats', 'evaluate-bid', 'context', 'personality', 'decision']


@pytest.mark.parametrize(
    'scenario_id, expected_action',
    [
        ('confident-bid', Action.RAISE),
        ('challenge-aggressor', Action.CHALLENGE),
        ('spot-on-spike', Action.SPOT_ON),
        ('blind-aggression-trigger', Action.CHALLENGE),
        ('pressure-opportunity', Action.RAISE),
    ],
)
def test_scenario_final_action(scenario_id: str, expected_action: Action) -> None:
    result = run_scenario(scenario_id)
    assert result.final_decision.action is expected_action


@pytest.mark.parametrize('scenario_id', list(SCENARIOS.keys()))
def test_scenario_step_count_and_ids(scenario_id: str) -> None:
    result = run_scenario(scenario_id)
    assert len(result.steps) == 6
    assert [s.step_id for s in result.steps] == CANONICAL_STEP_IDS


@pytest.mark.parametrize('scenario_id', list(SCENARIOS.keys()))
def test_scenario_needed_cnt_non_negative(scenario_id: str) -> None:
    """All scenarios must avoid the auto-RAISE short-circuit at strategy.py:106."""
    scenario = SCENARIOS[scenario_id]
    nc = needed_cnt(scenario.dice[:scenario.num_dice], scenario.prev_bid)
    assert nc >= 0, f'{scenario_id} would short-circuit to auto-RAISE'


@pytest.mark.parametrize('scenario_id', list(SCENARIOS.keys()))
def test_step_data_is_json_serializable(scenario_id: str) -> None:
    result = run_scenario(scenario_id)
    for step in result.steps:
        json.dumps(asdict(step))


def test_blind_aggression_branch_tagged() -> None:
    result = run_scenario('blind-aggression-trigger')
    decision_step = result.steps[-1]
    assert decision_step.data['branch'] == 'challenge_ev'
    personality_step = result.steps[4]
    assert personality_step.data['blind_aggression_active'] is True
    assert personality_step.data['boost_magnitude'] > 0


def test_pressure_opportunity_picks_higher_count() -> None:
    """Without cunning, CPU picks Bid(3,3); with cunning=100, pressure path picks Bid(4,4)."""
    result = run_scenario('pressure-opportunity')
    decision = result.final_decision
    assert decision.action is Action.RAISE
    assert decision.bid is not None
    assert decision.bid.count == 4


def test_spot_on_spike_branch_tagged() -> None:
    result = run_scenario('spot-on-spike')
    decision_step = result.steps[-1]
    assert decision_step.data['branch'] == 'spot_on_ev'


def test_confident_bid_is_raise() -> None:
    result = run_scenario('confident-bid')
    decision = result.final_decision
    assert decision.action is Action.RAISE
    assert decision.bid is not None
    assert decision.bid.count > SCENARIOS['confident-bid'].prev_bid.count


def test_challenge_aggressor_uses_opponent_profile() -> None:
    result = run_scenario('challenge-aggressor')
    decision_step = result.steps[-1]
    assert decision_step.data['branch'] == 'challenge_ev'


def test_scenario_ids_unique() -> None:
    ids = [s.id for s in SCENARIOS.values()]
    assert len(ids) == len(set(ids))


def test_list_scenarios_shape() -> None:
    listed = list_scenarios()
    assert len(listed) == len(SCENARIOS)
    for entry in listed:
        assert set(entry.keys()) == {'id', 'title', 'summary'}


def test_personality_override_matches_constructor_thresholds() -> None:
    """`_set_personality` with explicit jitter must produce the same thresholds the
    constructor would for the same trait values."""
    rng_constructor = random.Random(7)
    s_ctor = CPUStrategy(rng_constructor)

    risk_fraction = s_ctor.risk_appetite / 100
    spot_on_jitter = s_ctor.spot_on_ev_bias - (risk_fraction - 0.5) * 0.4
    challenge_jitter = s_ctor.challenge_threshold - max(0.50, 0.65 - risk_fraction * 0.15)

    s_override = CPUStrategy(random.Random(99))
    s_override._set_personality(
        risk_appetite=s_ctor.risk_appetite,
        attentiveness_score=s_ctor.attentiveness_score,
        bluff_frequency=s_ctor.bluff_frequency,
        spot_on_jitter=spot_on_jitter,
        challenge_jitter=challenge_jitter,
        archetype_label=s_ctor.archetype_label,
    )
    assert s_override.risk_appetite == s_ctor.risk_appetite
    assert s_override.attentiveness_score == s_ctor.attentiveness_score
    assert s_override.bluff_frequency == s_ctor.bluff_frequency
    assert s_override.archetype_label == s_ctor.archetype_label
    assert s_override.spot_on_ev_bias == pytest.approx(s_ctor.spot_on_ev_bias, abs=1e-9)
    assert s_override.challenge_threshold == pytest.approx(s_ctor.challenge_threshold, abs=1e-9)


def test_unknown_scenario_raises() -> None:
    with pytest.raises(KeyError):
        run_scenario('nonexistent-id')
