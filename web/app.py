import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from web.game_session import GameSession
from models import Action, Bid, InputResponse

BASE = Path(__file__).parent

app = FastAPI()
app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')

_sessions: dict[str, GameSession] = {}


@app.get('/health')
async def health() -> dict:
    return {'status': 'ok'}


@app.get('/', response_class=HTMLResponse)
async def index():
    return FileResponse(str(BASE / 'templates' / 'index.html'))


@app.websocket('/ws/{session_id}')
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session: GameSession | None = None
    try:
        join_raw = await websocket.receive_json()
        if join_raw.get('type') != 'join':
            await websocket.close(code=1008)
            return

        human_name: str = join_raw['human_name']
        num_players: int = int(join_raw['num_players'])
        session = GameSession(num_players=num_players, human_name=human_name)
        _sessions[session_id] = session

        import asyncio
        loop = asyncio.get_event_loop()

        while True:
            msg = await loop.run_in_executor(None, session.get_next_message)
            await websocket.send_json(_to_json_safe(msg))

            snap = msg.get('snapshot', {})
            if snap.get('game_over'):
                break

            if msg['event'].get('type') == 'input_request':
                raw = await websocket.receive_json()
                session.send_action(_parse_response(raw))

    except WebSocketDisconnect:
        pass
    finally:
        _sessions.pop(session_id, None)


def _to_json_safe(obj) -> dict:
    import dataclasses

    def default(o):
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        if hasattr(o, 'value'):
            return o.value
        raise TypeError(f'Not JSON serializable: {type(o)}')

    return json.loads(json.dumps(obj, default=default))


def _parse_response(raw: dict) -> InputResponse:
    action = Action(raw['action'])
    bid_data = raw.get('bid')
    bid = Bid(count=bid_data['count'], face=bid_data['face']) if bid_data else None
    return InputResponse(action=action, bid=bid)
