import logging
import random
import constants as Constants
from dice_math import needed_cnt
from models import Action, Bid, TurnResult, InputHandler
from strategy import Strategy, CPUStrategy, HumanStrategy, LLMStrategy

logger = logging.getLogger('liars_dice.player')


class Player:

    def __init__(
        self,
        name: str,
        player_type: str = 'CPU',
        eliminated: bool = False,
        num_dice: int = Constants.MAX_NUM_DICE,
        rng: 'random.Random | None' = None,
        input_handler: 'InputHandler | None' = None,
        llm_model: str | None = None,
    ):
        self.name = name
        self.num_dice = num_dice
        self.eliminated = eliminated
        self.dice: list[int] = [-1] * num_dice
        self.rolls_mode: int = 0
        self.wild_count: int = 0
        self.mode_count: int = 0
        self._rng_ref: random.Random = rng if rng is not None else random.Random()
        if player_type == 'HUMAN':
            self._strategy: Strategy = HumanStrategy(input_handler)
        elif player_type == 'LLM':
            self._strategy = LLMStrategy(model=llm_model or "gemma3:4b")
        else:
            self._strategy = CPUStrategy(self._rng_ref)
        self.player_type: str = self._strategy.player_type
        logger.debug('Player %s created (player_type=%s)', name, player_type)

    @property
    def _rng(self) -> random.Random:
        return self._rng_ref

    @_rng.setter
    def _rng(self, value: random.Random) -> None:
        self._rng_ref = value
        if isinstance(self._strategy, CPUStrategy):
            self._strategy._rng = value

    def reset(self) -> None:
        """Reset per-game state; personality traits are preserved."""
        self.num_dice = Constants.MAX_NUM_DICE
        self.dice = [-1] * self.num_dice
        self.rolls_mode = 0
        self.wild_count = 0
        self.mode_count = 0
        self.eliminated = False
        self._strategy.reset()

    def lose_die(self) -> None:
        self.dice[self.num_dice - 1] = -1
        logger.debug('%s: dice count %d -> %d', self.name, self.num_dice, self.num_dice - 1)
        self.num_dice -= 1

    def add_die(self) -> None:
        self.num_dice += 1

    def roll(self) -> None:
        for d in range(0, self.num_dice):
            self.dice[d] = self._rng.randint(1, 6)

    @staticmethod
    def grade(p: float) -> str:
        grade = Constants.LOWEST_THRESHOLD
        for k, v in Constants.PROB_THRESHOLDS.items():
            if p < v:
                break
            else:
                grade = k
        return grade

    def observe_action(self, player_name: str, action: Action, bid: 'Bid | None', total_dice: int) -> None:
        self._strategy.observe_action(player_name, action, bid, total_dice)

    def observe_outcome(self, bidder_name: str, challenge_succeeded: bool) -> None:
        self._strategy.observe_outcome(bidder_name, challenge_succeeded)

    def take_turn(self, prev_events, tot_other_dice: int, bidder_num_dice: int = 0, next_player_num_dice: int = 0) -> TurnResult:
        return self._strategy.decide(
            self.name, self.dice, self.num_dice,
            prev_events, tot_other_dice, bidder_num_dice, next_player_num_dice,
        )

    def get_needed_cnt(self, bid: Bid) -> int:
        return needed_cnt(self.dice[:self.num_dice], bid)

    def count_ones(self) -> int:
        self.wild_count = self.dice.count(1)
        return self.wild_count

    # ── Personality trait forwarding (tournament.py backward compat) ──────────

    @property
    def risk_appetite(self) -> int:
        return self._strategy.risk_appetite if isinstance(self._strategy, CPUStrategy) else 0

    @risk_appetite.setter
    def risk_appetite(self, value: int) -> None:
        if isinstance(self._strategy, CPUStrategy):
            self._strategy.risk_appetite = value

    @property
    def peer_pressure_score(self) -> int:
        return self._strategy.peer_pressure_score if isinstance(self._strategy, CPUStrategy) else 0

    @peer_pressure_score.setter
    def peer_pressure_score(self, value: int) -> None:
        if isinstance(self._strategy, CPUStrategy):
            self._strategy.peer_pressure_score = value

    @property
    def attentiveness_score(self) -> int:
        return self._strategy.attentiveness_score if isinstance(self._strategy, CPUStrategy) else 0

    @attentiveness_score.setter
    def attentiveness_score(self, value: int) -> None:
        if isinstance(self._strategy, CPUStrategy):
            self._strategy.attentiveness_score = value

    @property
    def challenge_threshold(self) -> float:
        return self._strategy.challenge_threshold if isinstance(self._strategy, CPUStrategy) else 0.5

    @challenge_threshold.setter
    def challenge_threshold(self, value: float) -> None:
        if isinstance(self._strategy, CPUStrategy):
            self._strategy.challenge_threshold = value

    @property
    def spot_on_threshold(self) -> float:
        return self._strategy.spot_on_threshold if isinstance(self._strategy, CPUStrategy) else 0.6

    @spot_on_threshold.setter
    def spot_on_threshold(self, value: float) -> None:
        if isinstance(self._strategy, CPUStrategy):
            self._strategy.spot_on_threshold = value

    @property
    def opponent_profiles(self) -> dict:
        return self._strategy.opponent_profiles if isinstance(self._strategy, CPUStrategy) else {}

    @opponent_profiles.setter
    def opponent_profiles(self, value: dict) -> None:
        if isinstance(self._strategy, CPUStrategy):
            self._strategy.opponent_profiles = value

    @property
    def positional_cunning(self) -> int:
        return self._strategy.positional_cunning if isinstance(self._strategy, CPUStrategy) else 0

    @positional_cunning.setter
    def positional_cunning(self, value: int) -> None:
        if isinstance(self._strategy, CPUStrategy):
            self._strategy.positional_cunning = value

