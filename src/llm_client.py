import json
import logging
import os
from typing import Callable, Iterator

import requests

import constants as Constants

logger = logging.getLogger('liars_dice.llm_client')

_DEFAULT_OLLAMA_URL = 'http://localhost:11434/api/generate'


def _wsl_default_gateway() -> 'str | None':
    """Return the WSL default-route gateway (Windows host IP) if running under WSL."""
    try:
        with open('/proc/version') as fh:
            if 'microsoft' not in fh.read().lower():
                return None
    except OSError:
        return None
    try:
        with open('/proc/net/route') as fh:
            for line in fh.readlines()[1:]:
                fields = line.split()
                if len(fields) >= 3 and fields[1] == '00000000':
                    gw_hex = fields[2]
                    octets = [str(int(gw_hex[i:i + 2], 16)) for i in (6, 4, 2, 0)]
                    return '.'.join(octets)
    except OSError:
        pass
    return None


def _ollama_url() -> str:
    env = os.environ.get('OLLAMA_URL')
    if env:
        return env
    gw = _wsl_default_gateway()
    if gw:
        return f'http://{gw}:11434/api/generate'
    return _DEFAULT_OLLAMA_URL


# ─────────────────────────────────────────────────────────────────────────────
# Debug listener: when set, every prompt and every streamed chunk is forwarded.
# Used by the live LLM debug window in the web layer. Production code is
# unaffected when no listener is registered.
# ─────────────────────────────────────────────────────────────────────────────

DebugEvent = tuple[str, dict]  # (kind, payload); kinds: prompt, token, done, error
DebugListener = Callable[[str, dict], None]

_debug_listener: DebugListener | None = None


def set_llm_debug_listener(listener: DebugListener | None) -> None:
    global _debug_listener
    _debug_listener = listener


def _emit_debug(kind: str, **payload) -> None:
    listener = _debug_listener
    if listener is None:
        return
    try:
        listener(kind, payload)
    except Exception as exc:
        logger.warning('debug listener raised: %s', exc)


def query_llm(model: str, prompt: str, timeout: float = 15, temperature: float = 0.7) -> str | None:
    _emit_debug('prompt', model=model, prompt=prompt, temperature=temperature, streaming=False)
    try:
        response = requests.post(
            _ollama_url(),
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'options': {'temperature': temperature},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        text = response.json()['response']
    except Exception as exc:
        logger.warning('query_llm failed: %s', exc)
        _emit_debug('error', message=str(exc))
        return None
    _emit_debug('token', text=text)
    _emit_debug('done')
    return text


def query_llm_stream(
    model: str,
    prompt: str,
    timeout: float = 60,
    temperature: float = 0.7,
    on_token: Callable[[str], None] | None = None,
) -> str | None:
    """Stream the response token-by-token. Returns the full accumulated text,
    or None on failure. Each chunk is forwarded to `on_token` (if provided)
    and to the debug listener as a 'token' event."""
    _emit_debug('prompt', model=model, prompt=prompt, temperature=temperature, streaming=True)
    chunks: list[str] = []
    try:
        with requests.post(
            _ollama_url(),
            json={
                'model': model,
                'prompt': prompt,
                'stream': True,
                'options': {'temperature': temperature},
            },
            timeout=timeout,
            stream=True,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = obj.get('response', '')
                if chunk:
                    chunks.append(chunk)
                    _emit_debug('token', text=chunk)
                    if on_token is not None:
                        try:
                            on_token(chunk)
                        except Exception as exc:
                            logger.warning('on_token raised: %s', exc)
                if obj.get('done'):
                    break
    except Exception as exc:
        logger.warning('query_llm_stream failed: %s', exc)
        _emit_debug('error', message=str(exc))
        return None
    _emit_debug('done')
    return ''.join(chunks)


if __name__ == '__main__':
    print(query_llm(Constants.LLM_MODEL, 'Say hello.'))
