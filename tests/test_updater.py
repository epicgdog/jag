import json
import tempfile
import unittest
from pathlib import Path

import httpx

from journal.model import LocalModel
from journal.obsidian import JournalError
from journal.updater import Coordinator, UpdaterTools, update_file
from test_vector_clients import VECTOR


class Model:
    context_length = 128
    count_tokens = staticmethod(len)
    def embed(self, texts): return [VECTOR[:] for _ in texts]


class Store:
    def __init__(self): self.writes = []; self.checks = 0
    def check_document(self, identity, content): self.checks += 1
    def replace(self, identity, content, vectors, generated):
        self.writes.append((identity, content, vectors))
        return len(vectors)


class Director:
    def __init__(self): self.calls = []
    def choose(self, stage, arguments, messages):
        self.calls.append((stage, arguments, messages))
        return {'id': stage, 'type': 'function', 'function': {'name': stage, 'arguments': json.dumps(arguments)}}


class UpdaterTests(unittest.TestCase):
    def test_compiled_graph_multiple_chunks_private_data_outside_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private-title.md'; path.write_text('PRIVATE_SENTINEL ' * 40)
            store, director = Store(), Director()
            status, chunks, written = update_file(path, directory, Model(), store, coordinator=director)
            self.assertEqual(status, 'succeeded'); self.assertGreater(chunks, 1); self.assertEqual(chunks, written)
            self.assertEqual([call[0] for call in director.calls], ['chunk_file', 'embed_text', 'upsert'])
            self.assertEqual([message['role'] for message in director.calls[1][2]],
                             ['user', 'assistant', 'tool'])
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(director.calls))
            self.assertNotIn('private-title', json.dumps(director.calls))
            self.assertEqual(len(store.writes), 1)

    def test_dry_run_and_empty_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.md'; path.write_text('Synthetic')
            store = Store()
            self.assertEqual(update_file(path, directory, Model(), store, True, Director()), ('succeeded', 1, 0))
            self.assertFalse(store.writes)
            path.write_text(' ')
            self.assertEqual(update_file(path, directory, Model(), store, coordinator=Director()), ('skipped', 0, 0))

    def test_tool_sequence_and_handle_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.md'; path.write_text('Synthetic')
            tools = UpdaterTools(path, directory, Model(), Store())
            with self.assertRaisesRegex(JournalError, 'updater_stage_violation'):
                tools.call('upsert', {})
            tools.call('chunk_file', {'file_path': 'input.md'})
            with self.assertRaisesRegex(JournalError, 'updater_stage_violation'):
                tools.call('embed_text', {'chunk_batch_handle': 'forged'})
            tools.clear(); self.assertIsNone(tools.snapshot)

    def test_failure_prevents_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.md'; path.write_text('Synthetic')
            for kind in ['parent', 'embedding', 'changed']:
                store = Store(); model = Model()
                if kind == 'parent':
                    def fail(*_): raise JournalError('parent_missing')
                    store.check_document = fail
                elif kind == 'embedding':
                    model.embed = lambda texts: []
                else:
                    def change(texts):
                        path.write_text('Changed synthetic')
                        return [VECTOR for _ in texts]
                    model.embed = change
                with self.subTest(kind=kind), self.assertRaises(JournalError):
                    update_file(path, directory, model, store, coordinator=Director())
                self.assertFalse(store.writes)
                path.write_text('Synthetic')

    def test_native_tool_call_contract_and_unsafe_response_rejection(self):
        arguments = {'file_path': 'input.md'}
        for valid in [True, False]:
            def handler(request):
                payload = json.loads(request.content)
                self.assertEqual(payload['model'], 'qwen3.5-9b-mlx')
                self.assertEqual(len(payload['tools']), 3)
                self.assertEqual(payload['tool_choice'], 'required')
                return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {
                    'content': 'ignored reasoning', 'tool_calls': [{'id': 'provider', 'type': 'function',
                    'function': {'name': 'chunk_file' if valid else 'upsert', 'arguments': json.dumps(arguments)}}]}}]})
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                coordinator = Coordinator(LocalModel(client=client))
                if valid:
                    call = coordinator.choose('chunk_file', arguments, [])
                    self.assertNotIn('ignored reasoning', json.dumps(call))
                else:
                    with self.assertRaisesRegex(JournalError, 'updater_invalid_tool_call'):
                        coordinator.choose('chunk_file', arguments, [])
