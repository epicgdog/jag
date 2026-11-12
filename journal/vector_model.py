"""Gemma coordination and EmbeddingGemma through the user's Ollama server."""
import math

import httpx

from journal.agent_model import AgentModel, OLLAMA_ENDPOINT, validate_ollama_endpoint
from journal.obsidian import JournalError

DIMENSIONS = 768
EMBEDDING_MODEL = 'embeddinggemma-2'


def validate_vector(value):
    if not isinstance(value, list) or len(value) != DIMENSIONS:
        raise JournalError('invalid_embedding')
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in value):
        raise JournalError('invalid_embedding')
    norm = math.hypot(*value)
    if not math.isfinite(norm) or norm == 0:
        raise JournalError('invalid_embedding')
    return [x / norm for x in value]


class EmbeddingModel(AgentModel):
    def __init__(self, *args, embedding_endpoint=OLLAMA_ENDPOINT,
                 embedding_model=EMBEDDING_MODEL, embedding_client=None, **kwargs):
        try:
            endpoint = validate_ollama_endpoint(embedding_endpoint)
        except JournalError:
            raise JournalError('invalid_embedding_endpoint') from None
        if not isinstance(embedding_model, str) or not embedding_model.strip() or any(c.isspace() for c in embedding_model):
            raise JournalError('embedding_configuration')
        super().__init__(*args, **kwargs)
        self.embedding_endpoint = endpoint
        self.model_id = embedding_model
        self.context_length = None
        self.embedding_client = embedding_client or httpx.Client(
            timeout=120, follow_redirects=False, trust_env=False)

    def embedding_request(self, path, payload):
        for attempt in range(3):
            try:
                response = self.embedding_client.post(self.embedding_endpoint + path, json=payload)
            except httpx.TransportError:
                if attempt < 2:
                    continue
                raise JournalError('embedding_unavailable') from None
            if 300 <= response.status_code < 400:
                raise JournalError('embedding_redirect')
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                continue
            if response.status_code >= 400:
                code = 'embedding_model_not_loaded' if response.status_code == 404 else 'embedding_unavailable'
                raise JournalError(code)
            try:
                return response.json()
            except ValueError:
                raise JournalError('embedding_invalid_response') from None
        raise JournalError('embedding_unavailable')

    def ready(self):
        super().ready()  # Both models are served by the authorized Ollama host.
        data = self.embedding_request('/api/show', {'model': self.model_id})
        try:
            if data.get('remote_host') or data.get('remote_model'):
                raise JournalError('embedding_configuration')
            if 'embedding' not in data['capabilities']:
                raise JournalError('embedding_configuration')
            info = data['model_info']
            architecture = info['general.architecture']
            context = info[architecture + '.context_length']
            dimensions = info[architecture + '.embedding_length']
            if type(context) is not int or context < 32:
                raise JournalError('embedding_context_invalid')
            if type(dimensions) is not int or dimensions != DIMENSIONS:
                raise JournalError('invalid_embedding')
            self.context_length = context
        except (KeyError, TypeError, AttributeError):
            raise JournalError('embedding_configuration') from None

    def count_tokens(self, text):
        """Conservative UTF-8 byte bound, not an Ollama tokenizer measurement."""
        return len(text.encode('utf-8'))

    def embed(self, texts):
        if not self.context_length or not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise JournalError('invalid_embedding_input')
        for text in texts:
            if self.count_tokens(text) > self.context_length - 16:
                raise JournalError('embedding_input_too_large')
        data = self.embedding_request('/api/embed', {
            'model': self.model_id, 'input': texts, 'truncate': False,
        })
        try:
            rows = data['embeddings']
            if not isinstance(rows, list) or len(rows) != len(texts):
                raise JournalError('embedding_batch_incomplete')
            return [validate_vector(row) for row in rows]
        except (KeyError, TypeError, ValueError):
            raise JournalError('embedding_invalid_response') from None

    def close(self):
        self.client.close()
        self.embedding_client.close()
