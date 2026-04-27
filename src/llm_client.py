import logging
import requests

logger = logging.getLogger('liars_dice.llm_client')

_OLLAMA_URL = 'http://localhost:11434/api/generate'


def query_llm(model: str, prompt: str, timeout: int = 15, temperature: float = 0.7) -> str | None:
    try:
        response = requests.post(
            _OLLAMA_URL,
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'options': {'temperature': temperature},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()['response']
    except Exception as exc:
        logger.warning('query_llm failed: %s', exc)
        return None


if __name__ == '__main__':
    print(query_llm('gemma3:4b', 'Say hello.'))
