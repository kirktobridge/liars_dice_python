"""Smoke test: run a full 2-player game through GameSession with auto-responses."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from game_session import GameSession
from models import Action, Bid


def _auto_respond(request: dict) -> dict:
    """Return a valid action for any InputRequest dict."""
    if request['type'] == 'opening_bid':
        dice = request['dice']
        face = dice[0] if dice else 1
        return {'action': Action.BID, 'bid': Bid(count=2, face=face)}
    else:
        prev_bid = request['prev_bid']
        count = prev_bid['count']
        face = prev_bid['face']
        new_face = (face % 6) + 1
        return {'action': Action.BID, 'bid': Bid(count=count, face=new_face)}


def run_smoke_test():
    session = GameSession(num_players=2, human_name='Tester')
    last_snap = {}
    steps = 0

    while True:
        msg = session.get_next_message()
        last_snap = msg.get('snapshot', {})
        event_type = msg['event'].get('type')

        if last_snap.get('game_over'):
            break

        if event_type == 'input_request':
            request = msg['event']['request']
            response = _auto_respond(request)
            session.send_action(response)

        steps += 1
        assert steps < 50_000, 'Smoke test exceeded step limit — likely deadlock'

    assert last_snap.get('game_over'), f'Expected game_over=True, got: {last_snap}'
    print(f'Smoke test passed. Winner: {last_snap.get("winner")}  (steps={steps})')


if __name__ == '__main__':
    run_smoke_test()
