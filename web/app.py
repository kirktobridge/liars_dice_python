import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.game_session import GameSession
from models import Action, Bid, InputResponse
import constants as Constants

BASE = Path(__file__).parent

app = FastAPI()
app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')

_sessions: dict[str, GameSession] = {}
_jobs: dict[str, dict] = {}  # {job_id: {status, progress, result, error}}


# ── existing routes ──────────────────────────────────────────────────────────

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


# ── tournament routes ─────────────────────────────────────────────────────────

@app.get('/tournament', response_class=HTMLResponse)
async def tournament_page():
    return FileResponse(str(BASE / 'templates' / 'tournament.html'))


class _TournamentRunBody(BaseModel):
    n: int
    num_players: int


@app.post('/tournament/run')
async def tournament_run(body: _TournamentRunBody, background_tasks: BackgroundTasks):
    if not (1 <= body.n <= 10000):
        raise HTTPException(status_code=422, detail='n must be between 1 and 10000')
    if not (2 <= body.num_players <= Constants.MAX_PLAYERS):
        raise HTTPException(
            status_code=422,
            detail=f'num_players must be between 2 and {Constants.MAX_PLAYERS}',
        )
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {'status': 'running', 'progress': 0.0, 'result': None, 'error': None}
    background_tasks.add_task(_tournament_worker, job_id, body.n, body.num_players)
    return {'job_id': job_id}


@app.get('/tournament/status/{job_id}')
async def tournament_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    return {'status': job['status'], 'progress': job['progress']}


@app.get('/tournament/results/{job_id}')
async def tournament_results(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    if job['status'] != 'complete':
        raise HTTPException(status_code=404, detail='Results not yet available')
    return job['result']


def _numpy_default(o):
    if hasattr(o, 'item'):
        return o.item()
    if hasattr(o, 'tolist'):
        return o.tolist()
    raise TypeError(f'Not JSON serializable: {type(o)}')


def _tournament_worker(job_id: str, n: int, num_players: int) -> None:
    try:
        from tournament import run_tournament
        from charts import compute_tournament_stats

        df, df_rounds, df_elim = run_tournament(n, num_players, parallel=False)
        stats = compute_tournament_stats(df, df_rounds, df_elim)
        sanitized = json.loads(json.dumps(stats, default=_numpy_default))
        _jobs[job_id].update(status='complete', progress=1.0, result=sanitized)
    except Exception as exc:
        _jobs[job_id].update(status='error', progress=0.0, error=str(exc))
