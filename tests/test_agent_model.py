import json
import unittest

import httpx

from journal.agent_model import AgentModel, validate_ollama_endpoint
from journal.obsidian import JournalError


class AgentModelTests(unittest.TestCase):
    def test_endpoint_is_restricted_to_authorized_server(self):
        self.assertEqual(validate_ollama_endpoint('http://127.0.0.1:11434/'),
                         'http://127.0.0.1:11434')
        for endpoint in ['http://localhost:1234/v1', 'http://example.com:11434',
                         'http://127.0.0.1:11434?secret=x']:
            with self.assertRaises(JournalError):
                validate_ollama_endpoint(endpoint)

    def test_tool_history_is_translated_without_exposing_reasoning(self):
        def handler(request):
            self.assertEqual(request.url.path, '/api/chat')
            payload = json.loads(request.content)
            self.assertEqual(payload['model'], 'gemma4:e4b')
            self.assertFalse(payload['think'])
            self.assertFalse(payload['stream'])
            self.assertEqual(payload['messages'][1]['tool_name'], 'chunk_file')
            self.assertEqual(payload['messages'][0]['tool_calls'][0]['function']['arguments'],
                             {'file_path': 'input.md'})
            return httpx.Response(200, json={'done': True, 'done_reason': 'stop',
                                            'message': {'content': 'Synthetic', 'thinking': 'PRIVATE_SENTINEL'}})
        messages = [
            {'role': 'assistant', 'tool_calls': [{'id': 'safe', 'function': {
                'name': 'chunk_file', 'arguments': '{"file_path":"input.md"}'}}]},
            {'role': 'tool', 'tool_call_id': 'safe', 'content': '{"chunk_count":1}'},
        ]
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = AgentModel(client=client).request('POST', '/chat/completions',
                                                      json={'model': 'gemma4:e4b', 'messages': messages})
        self.assertEqual(result['choices'][0]['finish_reason'], 'stop')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_cloud_routing_is_rejected(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
                200, json={'capabilities': ['completion'], 'remote_host': 'https://cloud.example'}))) as client:
            with self.assertRaisesRegex(JournalError, 'model_configuration'):
                AgentModel(client=client).ready()

    def test_redirect_is_rejected(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(302))) as client:
            with self.assertRaisesRegex(JournalError, 'model_redirect'):
                AgentModel(client=client).ready()
