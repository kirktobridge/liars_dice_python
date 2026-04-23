"""Smoke test: run a full 2-player game through GameSession with auto-responses."""
from game_session import GameSession
from models import Action, Bid


def _auto_respond(request: dict) -> dict:
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


def test_game_session_completes():
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
            response = _auto_respond(msg['event']['request'])
            session.send_action(response)

        steps += 1
        assert steps < 50_000, 'Smoke test exceeded step limit — likely deadlock'

    assert last_snap.get('game_over')
    assert last_snap.get('winner')
