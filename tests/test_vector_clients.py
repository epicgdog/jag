import json
import math
import unittest
from unittest.mock import patch

import httpx

from journal.obsidian import JournalError
from journal.vector_model import EmbeddingModel, validate_vector
from journal.vector_storage import VectorStorage


VECTOR = [1.0] + [0.0] * 767


class VectorClientTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict('os.environ', {'OLLAMA_BASE_URL': 'http://localhost:11434'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def model(self, handler):
        return EmbeddingModel(client=httpx.Client(transport=httpx.MockTransport(handler)),
                              embedding_client=httpx.Client(transport=httpx.MockTransport(handler)))

    def handler(self, request):
        payload = json.loads(request.content)
        if request.url.path == '/api/show' and payload['model'] == 'gemma4:e4b':
            return httpx.Response(200, json={'capabilities': ['completion', 'tools']})
        if request.url.path == '/api/show':
            self.assertEqual(str(request.url), 'http://localhost:11434/api/show')
            self.assertEqual(payload['model'], 'embeddinggemma-2')
            return httpx.Response(200, json={'capabilities': ['embedding'], 'model_info': {
                'general.architecture': 'gemma3', 'gemma3.context_length': 128,
                'gemma3.embedding_length': 512,
            }})
        self.assertEqual(request.url.path, '/api/embed')
        self.assertFalse(payload['truncate'])
        return httpx.Response(200, json={'embeddings': [VECTOR for _ in payload['input']]})

    def test_ready_fixed_model_and_long_file_tokenization(self):
        from journal.chunks import chunk_markdown
        model = self.model(self.handler)
        try:
            model.ready()
            chunks = chunk_markdown('Synthetic paragraph.\n\n' * 30, model.count_tokens, 80, 8)
            self.assertGreater(len(chunks), 1)
            self.assertEqual(len(model.embed(chunks)), len(chunks))
            with self.assertRaisesRegex(JournalError, 'embedding_input_too_large'):
                model.embed(['x' * 200])
        finally: model.close()

    def test_vectors_reject_wrong_dimension_nonfinite_zero_and_bool(self):
        for vector in [[], [1, 0], [0.0] * 768, [math.nan] + VECTOR[1:],
                       [math.inf] + VECTOR[1:], [True] + VECTOR[1:]]:
            with self.subTest(kind=type(vector[0]).__name__ if vector else 'empty'):
                with self.assertRaises(JournalError): validate_vector(vector)
        self.assertEqual(validate_vector([2.0] + VECTOR[1:]), VECTOR)

    def test_incomplete_embedding_batches_and_order(self):
        model = self.model(lambda request: httpx.Response(200, json={'embeddings': [VECTOR]}))
        model.context_length = 128
        with self.assertRaisesRegex(JournalError, 'embedding_batch_incomplete'):
            model.embed(['synthetic one', 'synthetic two'])
        model.close()

    def test_non_embedding_model_fails_before_text_embedding(self):
        def handler(request):
            return httpx.Response(200, json={'capabilities': ['completion']})
        model = self.model(handler)
        try:
            with self.assertRaisesRegex(JournalError, 'embedding_configuration'):
                model.ready()
        finally:
            model.close()

    def test_storage_checks_parent_and_complete_write(self):
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            if request.url.path.endswith('check_vector_document'): return httpx.Response(200, json='ready')
            return httpx.Response(200, json=1)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            store = VectorStorage('https://synthetic.example', 'sb_secret_synthetic', client)
            store.check_document('/synthetic.md', 'Synthetic content')
            self.assertEqual(store.replace('/synthetic.md', 'Synthetic content', [VECTOR], '2026-01-01T00:00:00Z'), 1)
        self.assertEqual(requests[-1]['p_embeddings'], [VECTOR])

    def test_storage_safe_error_and_redirects(self):
        for status in [302, 500]:
            with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, text='PRIVATE_SENTINEL'))) as client:
                store = VectorStorage('https://synthetic.example', 'sb_secret_synthetic', client)
                with self.assertRaisesRegex(JournalError, '^storage_unavailable$'): store.ready()
