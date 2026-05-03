"""Live debug pipeline: forwards llm_client debug events to connected browsers.

A single process-wide broadcaster owns the set of WebSocket connections
and a thread-safe queue. The llm_client debug listener (called from
worker threads or test fixtures) drops events on the queue; an asyncio
task drains the queue and fans events out to all connected sockets.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from typing import Any

from fastapi import WebSocket

from llm_client import set_llm_debug_listener


class LLMDebugBroadcaster:
    def __init__(self) -> None:
        self._queue: queue.Queue[dict] = queue.Queue(maxsize=10_000)
        self._clients: set[WebSocket] = set()
        self._clients_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._drain_task: asyncio.Task | None = None
        # Recent event ring buffer so newly-connected clients see context.
        self._recent: list[dict] = []
        self._recent_max = 500

    # called from any thread (llm_client debug listener)
    def emit(self, kind: str, payload: dict) -> None:
        event = {'kind': kind, 'ts': time.time(), **payload}
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass  # drop oldest semantics aren't worth the lock here

    async def attach(self, websocket: WebSocket) -> None:
        await websocket.accept()
        # Replay recent history first so the user sees context on connect.
        for event in list(self._recent):
            try:
                await websocket.send_text(json.dumps(event))
            except Exception:
                return
        with self._clients_lock:
            self._clients.add(websocket)

    def detach(self, websocket: WebSocket) -> None:
        with self._clients_lock:
            self._clients.discard(websocket)

    async def start(self) -> None:
        if self._drain_task is not None:
            return
        self._loop = asyncio.get_running_loop()
        set_llm_debug_listener(self.emit)
        self._drain_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        while True:
            try:
                event = await asyncio.to_thread(self._queue.get, True, 1.0)
            except queue.Empty:
                continue
            self._recent.append(event)
            if len(self._recent) > self._recent_max:
                del self._recent[: len(self._recent) - self._recent_max]
            await self._fanout(event)

    async def _fanout(self, event: dict) -> None:
        with self._clients_lock:
            sockets = list(self._clients)
        if not sockets:
            return
        msg = json.dumps(event)
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        if dead:
            with self._clients_lock:
                for ws in dead:
                    self._clients.discard(ws)


broadcaster = LLMDebugBroadcaster()
