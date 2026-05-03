"""Ollama daemon lifecycle helpers.

Used by the live integration test fixture and by ad-hoc analysis scripts.
Pure utility module — no game logic, no test framework dependency.
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import time
from urllib.parse import urlparse

import requests

import constants as Constants
from llm_client import _ollama_url

logger = logging.getLogger('liars_dice.ollama_lifecycle')


def ollama_base() -> str:
    parsed = urlparse(_ollama_url())
    return f"{parsed.scheme}://{parsed.netloc}"


def ollama_reachable() -> bool:
    try:
        r = requests.get(ollama_base() + "/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def model_present(model: str) -> bool:
    try:
        r = requests.get(ollama_base() + "/api/tags", timeout=5)
        r.raise_for_status()
        names = {m.get("name", "") for m in r.json().get("models", [])}
        return model in names or any(
            n.split(":")[0] == model.split(":")[0]
            and n.split(":", 1)[-1] == model.split(":", 1)[-1]
            for n in names
        )
    except Exception:
        return False


def pull_model(model: str) -> bool:
    try:
        r = requests.post(
            ollama_base() + "/api/pull",
            json={"name": model, "stream": False},
            timeout=600,
        )
        if r.status_code == 200:
            return True
    except Exception as exc:
        logger.warning("HTTP pull failed: %s", exc)

    if shutil.which("ollama") is None:
        return False
    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True,
            text=True,
            timeout=600,
        )
        return result.returncode == 0
    except Exception as exc:
        logger.warning("CLI pull failed: %s", exc)
        return False


def wait_until_reachable(timeout_s: float = 30.0, interval_s: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if ollama_reachable():
            return True
        time.sleep(interval_s)
    return False


def spawn_ollama_serve(log_path: str = "/tmp/ollama_serve.log") -> 'subprocess.Popen | None':
    if shutil.which("ollama") is None:
        return None
    log = open(log_path, "ab", buffering=0)
    try:
        proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as exc:
        logger.warning("failed to spawn ollama serve: %s", exc)
        log.close()
        return None
    return proc


def teardown_spawned(proc: 'subprocess.Popen | None') -> None:
    if proc is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception as exc:
        logger.warning("error tearing down ollama serve: %s", exc)


class OllamaSession:
    """Context manager that ensures a reachable Ollama daemon with the given model.

    On enter: reuses an existing daemon if reachable; otherwise spawns one.
    Pulls the model if missing. Raises RuntimeError on failure.
    On exit: only tears down what it spawned.
    """

    def __init__(self, model: str = Constants.LLM_MODEL, log_path: str = "/tmp/ollama_serve.log") -> None:
        self.model = model
        self.log_path = log_path
        self._spawned: 'subprocess.Popen | None' = None

    def __enter__(self) -> str:
        if not ollama_reachable():
            self._spawned = spawn_ollama_serve(self.log_path)
            if self._spawned is None:
                raise RuntimeError("Ollama not reachable and `ollama` binary not found on PATH.")
            if not wait_until_reachable(timeout_s=30.0):
                teardown_spawned(self._spawned)
                self._spawned = None
                raise RuntimeError("Spawned `ollama serve` but daemon never became reachable.")
        if not model_present(self.model):
            if not pull_model(self.model):
                teardown_spawned(self._spawned)
                self._spawned = None
                raise RuntimeError(f"Model {self.model} not present and could not be pulled.")
        return self.model

    def __exit__(self, exc_type, exc, tb) -> None:
        teardown_spawned(self._spawned)
        self._spawned = None
