import asyncio
import dataclasses
import json
import os
import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.game_session import GameSession
from web.timing import EVENT_DELAYS
from web.web_logging import setup_web_logging, get_logger
from web.llm_debug import broadcaster as llm_debug_broadcaster
from models import Action, Bid, InputResponse
import constants as Constants

BASE = Path(__file__).parent

setup_web_logging()
_log = get_logger('app')

app = FastAPI()
app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')

_sessions: dict[str, GameSession] = {}
_MAX_JOBS = 20
_jobs: dict[str, dict] = {}  # {job_id: {status, progress, result, error}}


def _register_job(job_id: str) -> None:
    """Insert a new job, evicting the oldest entry if over capacity."""
    if len(_jobs) >= _MAX_JOBS:
        oldest = next(iter(_jobs))
        del _jobs[oldest]
    _jobs[job_id] = {'status': 'running', 'progress': 0.0, 'result': None, 'error': None}


def _default(o):
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    if hasattr(o, 'value'):
        return o.value
    raise TypeError(f'Not JSON serializable: {type(o)}')


# ── existing routes ──────────────────────────────────────────────────────────

@app.on_event('startup')
async def _start_llm_debug() -> None:
    await llm_debug_broadcaster.start()


@app.get('/health')
async def health() -> dict:
    return {'status': 'ok'}


@app.get('/llm-debug', response_class=HTMLResponse)
async def llm_debug_page():
    return FileResponse(str(BASE / 'templates' / 'llm_debug.html'))


@app.websocket('/ws/llm-debug')
async def llm_debug_ws(websocket: WebSocket):
    await llm_debug_broadcaster.attach(websocket)
    try:
        while True:
            await websocket.receive_text()  # we don't expect input; loop just keeps connection open
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        llm_debug_broadcaster.detach(websocket)


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
            _log.warning('session=%s bad handshake: %s', session_id[:8], join_raw.get('type'))
            await websocket.close(code=1008)
            return

        human_name: str = join_raw['human_name']
        num_players: int = int(join_raw['num_players'])
        session = GameSession(num_players=num_players, human_name=human_name,
                              session_id=session_id)
        _sessions[session_id] = session
        _log.info('SESSION_CREATE session=%s player=%r num_players=%d',
                  session_id[:8], human_name, num_players)

        loop = asyncio.get_event_loop()

        while True:
            msg = await loop.run_in_executor(None, session.get_next_message)
            delay = EVENT_DELAYS.get(msg['event'].get('type', ''), 0.0)
            if delay:
                await asyncio.sleep(delay)
            await websocket.send_text(json.dumps(msg, default=_default))

            snap = msg.get('snapshot', {})
            if snap.get('game_over'):
                winner = snap.get('winner', 'unknown')
                _log.info('GAME_OVER session=%s winner=%r', session_id[:8], winner)
                break

            if msg['event'].get('type') == 'input_request':
                raw = await websocket.receive_json()
                session.send_action(_parse_response(raw))

            if msg['event'].get('type') in ('challenge_resolved', 'spot_on_resolved'):
                await websocket.receive_json()  # wait for rolls_revealed_ack

    except WebSocketDisconnect:
        _log.info('SESSION_DISCONNECT session=%s', session_id[:8])
    except Exception:
        _log.exception('SESSION_ERROR session=%s', session_id[:8])
        raise
    finally:
        _sessions.pop(session_id, None)
        _log.debug('SESSION_CLEANUP session=%s active_sessions=%d',
                   session_id[:8], len(_sessions))


def _parse_response(raw: dict) -> InputResponse:
    action = Action(raw['action'])
    bid_data = raw.get('bid')
    bid = Bid(count=bid_data['count'], face=bid_data['face']) if bid_data else None
    return InputResponse(action=action, bid=bid)


# ── tournament routes ─────────────────────────────────────────────────────────

@app.get('/tournament', response_class=HTMLResponse)
async def tournament_page():
    return FileResponse(str(BASE / 'templates' / 'tournament.html'))


@app.get('/tournament/player-names')
async def tournament_player_names():
    return {'names': Constants.PLAYER_NAMES}


class _TournamentRunBody(BaseModel):
    n: int
    num_players: int


class _PlayerConfig(BaseModel):
    name: str
    risk_appetite: int
    attentiveness_score: int
    bluff_frequency: int
    archetype: str | None = None

    model_config = {'extra': 'forbid'}


class _CustomTournamentRunBody(BaseModel):
    n: int
    players: list[_PlayerConfig]


@app.post('/tournament/run')
async def tournament_run(body: _TournamentRunBody):
    if not (1 <= body.n <= 10000):
        raise HTTPException(status_code=422, detail='n must be between 1 and 10000')
    if not (2 <= body.num_players <= Constants.MAX_PLAYERS):
        raise HTTPException(
            status_code=422,
            detail=f'num_players must be between 2 and {Constants.MAX_PLAYERS}',
        )
    job_id = str(uuid.uuid4())
    _register_job(job_id)
    threading.Thread(
        target=_tournament_worker, args=(job_id, body.n, body.num_players), daemon=True
    ).start()
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
    result = job['result']
    _jobs.pop(job_id, None)
    return result


@app.post('/tournament/run-custom')
async def tournament_run_custom(body: _CustomTournamentRunBody):
    if not (1 <= body.n <= 10000):
        raise HTTPException(status_code=422, detail='n must be between 1 and 10000')
    if not (2 <= len(body.players) <= Constants.MAX_PLAYERS):
        raise HTTPException(
            status_code=422,
            detail=f'Number of players must be between 2 and {Constants.MAX_PLAYERS}',
        )
    valid_names = set(Constants.PLAYER_NAMES)
    names_seen = set()
    for pc in body.players:
        if pc.name not in valid_names:
            raise HTTPException(status_code=422, detail=f'Unknown player name: {pc.name}')
        if pc.name in names_seen:
            raise HTTPException(status_code=422, detail=f'Duplicate player name: {pc.name}')
        names_seen.add(pc.name)
        if not (1 <= pc.risk_appetite <= 100):
            raise HTTPException(status_code=422, detail=f'risk_appetite out of range for {pc.name}')
        if not (1 <= pc.attentiveness_score <= 100):
            raise HTTPException(status_code=422, detail=f'attentiveness_score out of range for {pc.name}')
        if not (1 <= pc.bluff_frequency <= 100):
            raise HTTPException(status_code=422, detail=f'bluff_frequency out of range for {pc.name}')
        if pc.archetype is not None and pc.archetype not in Constants.ARCHETYPE_LABELS:
            raise HTTPException(status_code=422, detail=f'Unknown archetype for {pc.name}: {pc.archetype}')
    job_id = str(uuid.uuid4())
    _register_job(job_id)
    player_configs = [pc.model_dump() for pc in body.players]
    threading.Thread(
        target=_custom_tournament_worker, args=(job_id, body.n, player_configs), daemon=True
    ).start()
    return {'job_id': job_id}


def _tournament_worker(job_id: str, n: int, num_players: int) -> None:
    _log.info('TOURNAMENT_START job=%s n=%d num_players=%d', job_id[:8], n, num_players)
    try:
        from tournament import run_tournament
        from tournament_stats import compute_tournament_stats

        def _progress_cb(frac: float) -> None:
            _jobs[job_id]['progress'] = frac

        df, df_rounds, df_elim = run_tournament(n, num_players, parallel=True, on_progress=_progress_cb, show_progress=False)
        stats = compute_tournament_stats(df, df_rounds, df_elim)
        _jobs[job_id].update(status='complete', progress=1.0, result=stats)
        _log.info('TOURNAMENT_COMPLETE job=%s', job_id[:8])
    except Exception as exc:
        _jobs[job_id].update(status='error', progress=0.0, error=str(exc))
        _log.exception('TOURNAMENT_ERROR job=%s', job_id[:8])


# ── explainer routes ──────────────────────────────────────────────────────────

@app.get('/explainer', response_class=HTMLResponse)
async def explainer_page():
    return FileResponse(str(BASE / 'templates' / 'explainer.html'))


@app.get('/explainer/scenarios')
async def explainer_scenarios():
    from web.explainer_logic import list_scenarios
    return {'scenarios': list_scenarios()}


@app.get('/explainer/scenario/{scenario_id}')
async def explainer_scenario(scenario_id: str):
    from web.explainer_logic import SCENARIOS, run_scenario
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=404, detail='Unknown scenario')
    result = run_scenario(scenario_id)
    return json.loads(json.dumps(result, default=_default))


def _custom_tournament_worker(job_id: str, n: int, player_configs: list[dict]) -> None:
    _log.info('CUSTOM_TOURNAMENT_START job=%s n=%d num_players=%d', job_id[:8], n, len(player_configs))
    try:
        from tournament import run_tournament
        from tournament_stats import compute_tournament_stats

        def _progress_cb(frac: float) -> None:
            _jobs[job_id]['progress'] = frac

        df, df_rounds, df_elim = run_tournament(
            n, parallel=True, on_progress=_progress_cb, player_configs=player_configs, show_progress=False
        )
        stats = compute_tournament_stats(df, df_rounds, df_elim)
        _jobs[job_id].update(status='complete', progress=1.0, result=stats)
        _log.info('CUSTOM_TOURNAMENT_COMPLETE job=%s', job_id[:8])
    except Exception as exc:
        _jobs[job_id].update(status='error', progress=0.0, error=str(exc))
        _log.exception('CUSTOM_TOURNAMENT_ERROR job=%s', job_id[:8])
