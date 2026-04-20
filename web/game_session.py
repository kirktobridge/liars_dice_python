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
        self._out.put({
            'event': {'type': 'input_request', 'request': _serialise_request(request)},
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


class GameSession:
    def __init__(self, num_players: int, human_name: str) -> None:
        self._out: queue.Queue[dict] = queue.Queue()
        self._handler = WebInputHandler()
        self._num_players = num_players
        self._human_name = human_name
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        rng = random.Random()
        available = [n for n in Constants.PLAYER_NAMES if n != self._human_name]
        cpu_names = rng.sample(available, self._num_players - 1)

        def on_event(event: dict) -> None:
            snap = game.snapshot().to_dict()
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
        self._out.put({'event': {'type': 'session_ended'}, 'snapshot': snap})

    def send_action(self, response: InputResponse) -> None:
        self._handler.put_action(response)

    def get_next_message(self) -> dict:
        return self._out.get()
