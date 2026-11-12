"""Gemma agent inference through the user's Ollama server."""
import json
import os
from urllib.parse import urlsplit

import httpx

from journal.model import LocalModel
from journal.obsidian import JournalError

MODEL = 'gemma4:e4b'
OLLAMA_ENDPOINT = 'http://127.0.0.1:11434'


def validate_ollama_endpoint(endpoint):
    try:
        parsed = urlsplit(endpoint)
        valid = (parsed.scheme in ('http', 'https') and parsed.hostname == '127.0.0.1'
                 and parsed.port is not None and not parsed.username and not parsed.password
                 and parsed.path in ('', '/') and not parsed.query and not parsed.fragment)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise JournalError('invalid_model_endpoint')
    return endpoint.rstrip('/')


class AgentModel(LocalModel):
    def __init__(self, endpoint=None, client=None, context_budget=12000):
        self.endpoint = validate_ollama_endpoint(endpoint or os.getenv('OLLAMA_BASE_URL', OLLAMA_ENDPOINT))
        self.client = client or httpx.Client(timeout=120, follow_redirects=False, trust_env=False)
        self.context_budget = context_budget

    def native_request(self, method, path, **kwargs):
        return super().request(method, path, **kwargs)

    def ready(self):
        data = self.native_request('POST', '/api/show', json={'model': MODEL})
        if (not isinstance(data, dict) or not isinstance(data.get('capabilities'), list)
                or 'completion' not in data['capabilities']
                or data.get('remote_host') or data.get('remote_model')):
            raise JournalError('model_configuration')

    def request(self, method, path, **kwargs):
        """Adapt the planner/tool protocol to Ollama's native non-streaming API."""
        if method != 'POST' or path != '/chat/completions':
            raise JournalError('model_configuration')
        try:
            payload = kwargs['json']
            if payload['model'] != MODEL:
                raise JournalError('model_configuration')
            messages = []
            tool_names = {}
            for message in payload['messages']:
                native = {'role': message['role'], 'content': message.get('content') or ''}
                if message.get('tool_calls'):
                    native['tool_calls'] = []
                    for call in message['tool_calls']:
                        function = call['function']
                        arguments = function['arguments']
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments)
                        native['tool_calls'].append({'function': {'name': function['name'], 'arguments': arguments}})
                        tool_names[call['id']] = function['name']
                if native['role'] == 'tool':
                    native['tool_name'] = tool_names[message['tool_call_id']]
                messages.append(native)
            body = {'model': MODEL, 'messages': messages, 'stream': False, 'think': False}
            if 'tools' in payload:
                body['tools'] = payload['tools']
            if 'response_format' in payload:
                body['format'] = payload['response_format']['json_schema']['schema']
        except (KeyError, TypeError, ValueError):
            raise JournalError('model_invalid_request') from None
        data = self.native_request('POST', '/api/chat', json=body)
        try:
            message = data['message']
            result = {'content': message.get('content', '')}
            calls = message.get('tool_calls', [])
            if calls:
                result['tool_calls'] = [
                    {'id': f'call_{index}', 'type': 'function', 'function': {
                        'name': call['function']['name'],
                        'arguments': json.dumps(call['function']['arguments']),
                    }} for index, call in enumerate(calls)
                ]
            reason = data.get('done_reason', 'incomplete') if data.get('done') is True else 'incomplete'
            if calls and reason == 'stop':
                reason = 'tool_calls'
            return {'choices': [{'finish_reason': reason, 'message': result}]}
        except (KeyError, TypeError, AttributeError):
            raise JournalError('model_invalid_response_schema') from None
