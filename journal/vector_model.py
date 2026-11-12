"""Fixed local embedding model, SDK tokenization, and checked OpenAI transport."""
import math

from journal.model import MODEL, LocalModel
from journal.obsidian import JournalError

DIMENSIONS = 1024
EMBEDDING_IDS = ('qwen3-embedding-0.6b-dwq', 'mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ')


def validate_vector(value):
    if not isinstance(value, list) or len(value) != DIMENSIONS:
        raise JournalError('invalid_embedding')
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in value):
        raise JournalError('invalid_embedding')
    norm = math.hypot(*value)
    if not math.isfinite(norm) or norm == 0:
        raise JournalError('invalid_embedding')
    return [x / norm for x in value]


class EmbeddingModel(LocalModel):
    def __init__(self, *args, sdk=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sdk = sdk
        self.handle = None
        self.model_id = None
        self.context_length = None

    def ready(self):
        super().ready()  # The coordinator must be available too.
        try:
            import lmstudio
            if self.sdk is None:
                self.sdk = lmstudio.Client(api_host='localhost:1234')
            if MODEL not in {model.identifier for model in self.sdk.llm.list_loaded()}:
                raise JournalError('model_unavailable')
            inventory = self.request('GET', '/models')['data']
            available = {item['id'] for item in inventory}
            loaded = {handle.identifier: handle for handle in self.sdk.embedding.list_loaded()}
            candidates = [identifier for identifier in EMBEDDING_IDS if identifier in available and identifier in loaded]
            if len(candidates) != 1:
                raise JournalError('embedding_model_not_loaded')
            self.model_id = candidates[0]
            self.handle = loaded[self.model_id]
            self.context_length = self.handle.get_context_length()
            if type(self.context_length) is not int or self.context_length < 32:
                raise JournalError('embedding_context_invalid')
            self.count_tokens('Synthetic configuration probe.')
            self.embed(['Synthetic configuration probe.'])
        except JournalError:
            raise
        except Exception:
            raise JournalError('embedding_configuration') from None

    def count_tokens(self, text):
        try:
            result = len(self.handle.tokenize(text))
            return result
        except JournalError:
            raise
        except Exception:
            raise JournalError('model_unavailable') from None

    def embed(self, texts):
        if not self.model_id or not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise JournalError('invalid_embedding_input')
        for text in texts:
            if self.count_tokens(text) >= self.context_length:
                raise JournalError('embedding_input_too_large')
        data = self.request('POST', '/embeddings', json={'model': self.model_id, 'input': texts})
        try:
            rows = data['data']
            if len(rows) != len(texts) or {row['index'] for row in rows} != set(range(len(texts))):
                raise JournalError('embedding_batch_incomplete')
            return [validate_vector(row['embedding']) for row in sorted(rows, key=lambda row: row['index'])]
        except (KeyError, TypeError, ValueError):
            raise JournalError('embedding_invalid_response') from None

    def close(self):
        self.client.close()
        if self.sdk:
            self.sdk.close()
