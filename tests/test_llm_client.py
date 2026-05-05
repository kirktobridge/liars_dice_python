import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import requests
from llm_client import query_llm


class TestQueryLlm(unittest.TestCase):

    def _mock_response(self, json_data: dict, status_code: int = 200) -> MagicMock:
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = json_data
        mock.raise_for_status.return_value = None
        return mock

    @patch.dict(os.environ, {'OLLAMA_URL': 'http://localhost:11434/api/generate'})
    @patch('llm_client.requests.post')
    def test_successful_response(self, mock_post):
        mock_post.return_value = self._mock_response({'response': 'Hello there!'})
        result = query_llm('gemma3:4b', 'Say hello.')
        self.assertEqual(result, 'Hello there!')
        mock_post.assert_called_once_with(
            'http://localhost:11434/api/generate',
            json={
                'model': 'gemma3:4b',
                'prompt': 'Say hello.',
                'stream': False,
                'options': {'temperature': 0.7},
            },
            timeout=15,
        )

    @patch('llm_client.requests.post')
    def test_timeout_returns_none(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout('timed out')
        result = query_llm('gemma3:4b', 'Say hello.', timeout=1)
        self.assertIsNone(result)

    @patch('llm_client.requests.post')
    def test_request_exception_returns_none(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError('refused')
        result = query_llm('gemma3:4b', 'Say hello.')
        self.assertIsNone(result)

    @patch('llm_client.requests.post')
    def test_missing_response_key_returns_none(self, mock_post):
        mock_post.return_value = self._mock_response({'model': 'gemma3:4b'})
        result = query_llm('gemma3:4b', 'Say hello.')
        self.assertIsNone(result)

    @patch('llm_client.requests.post')
    def test_malformed_json_returns_none(self, mock_post):
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        mock.json.side_effect = ValueError('No JSON object')
        mock_post.return_value = mock
        result = query_llm('gemma3:4b', 'Say hello.')
        self.assertIsNone(result)
