import queue
import random
import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from LiarsDiceGame import LiarsDiceGame
from Player import Player
import constants as Constants
from models import Action, Bid, InputRequest, InputResponse
from advisor import advisor_probs
from web.web_logging import get_logger


class WebInputHandler:
    """Implements the InputHandler Protocol; blocks until the WebSocket delivers an action."""

    def __init__(self) -> None:
        self._action_queue: queue.Queue[InputResponse] = queue.Queue()
        self._out: 'queue.Queue | None' = None
        self._game: 'LiarsDiceGame | None' = None

    def bind(self, out_queue: queue.Queue, game: LiarsDiceGame) -> None:
        self._out = out_queue
        self._game = game

    def __call__(self, request: InputRequest) -> InputResponse:
        snap = self._game.snapshot().to_dict() if self._game else {}
        assert self._out is not None, 'WebInputHandler.bind() must be called before use'
        valid_bids = _compute_valid_bids(request)
        prev_bid_obj = request.get('prev_bid')  # Bid dataclass (before serialisation)
        advisor = advisor_probs(
            human_dice=request['dice'],
            tot_other_dice=request['tot_other_dice'],
            prev_bid=prev_bid_obj,
            valid_bids=valid_bids,
        )
        self._out.put({
            'event': {
                'type': 'input_request',
                'request': _serialise_request(request),
                'advisor': _serialise_advisor(advisor),
            },
            'snapshot': snap,
        })
        return self._action_queue.get()

    def put_action(self, response: InputResponse) -> None:
        self._action_queue.put(response)


def _serialise_request(req: InputRequest) -> dict:
    out = dict(req)
    if 'prev_bid' in out and out['prev_bid'] is not None:
        b = out['prev_bid']
        out['prev_bid'] = {'count': b.count, 'face': b.face}
    return out


def _compute_valid_bids(request: InputRequest) -> list[Bid]:
    dice = request['dice']
    tot_other = request['tot_other_dice']
    max_count = tot_other + len(dice)
    if request['type'] == 'opening_bid':
        return [Bid(c, f) for c in range(1, max_count + 1) for f in range(1, 7)]
    prev = request['prev_bid']  # Bid dataclass (before serialisation)
    result = []
    for c in range(prev.count, max_count + 1):
        for f in range(1, 7):
            if c > prev.count or (c == prev.count and f > prev.face):
                result.append(Bid(c, f))
    return result


def _serialise_advisor(data: dict) -> dict:
    bid_probs_serial = {
        str(face): {str(count): round(prob, 4) for count, prob in counts.items()}
        for face, counts in data['bid_probs'].items()
    }
    return {
        'challenge_prob': data['challenge_prob'],
        'spot_on_prob':   data['spot_on_prob'],
        'bid_probs':      bid_probs_serial,
    }


class GameSession:
    def __init__(self, num_players: int, human_name: str, session_id: str = '') -> None:
        self._out: queue.Queue[dict] = queue.Queue()
        self._handler = WebInputHandler()
        self._num_players = num_players
        self._human_name = human_name
        self._session_id = session_id[:8] or 'unknown'
        self._log = get_logger(f'session.{self._session_id}')
        self._event_seq = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        rng = random.Random()
        available = [n for n in Constants.PLAYER_NAMES if n != self._human_name]
        cpu_names = rng.sample(available, self._num_players - 1)

        def on_event(event: dict) -> None:
            self._event_seq += 1
            snap = game.snapshot().to_dict()
            self._log.debug('#%d | %s | %s | %s',
                            self._event_seq,
                            event.get('type', '?'),
                            event.get('player', 'SYS'),
                            event.get('bid') or event.get('data', ''))
            self._out.put({'event': event, 'snapshot': snap})

        game = LiarsDiceGame(self._num_players, on_event=on_event)
        self._handler.bind(self._out, game)

        human = Player(self._human_name, player_type='HUMAN', input_handler=self._handler)
        game.add_player(human)
        for name in cpu_names:
            game.add_player(Player(name, player_type='CPU'))

        with game:
            while game.game_status:
                game.process_round()

        # Sentinel with game_over=True snapshot
        snap = game.snapshot().to_dict()
        self._log.info('SESSION_ENDED after %d events', self._event_seq)
        self._out.put({'event': {'type': 'session_ended'}, 'snapshot': snap})

    def send_action(self, response: InputResponse) -> None:
        self._handler.put_action(response)

    def get_next_message(self) -> dict:
        return self._out.get()
