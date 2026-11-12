"""Local LangGraph coordinator; private chunks/vectors live in runtime handles."""
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from journal.chunks import CHUNK_TOKENS, OVERLAP_TOKENS, chunk_markdown, read_snapshot
from journal.model import MODEL
from journal.obsidian import JournalError


ARGUMENTS = {'chunk_file': 'file_path', 'embed_text': 'chunk_batch_handle', 'upsert': 'embedding_batch_handle'}
TOOLS = [{'type': 'function', 'function': {
    'name': name, 'description': description, 'parameters': {
        'type': 'object', 'properties': {ARGUMENTS[name]: {'type': 'string'}},
        'required': [ARGUMENTS[name]], 'additionalProperties': False,
    },
}} for name, description in [
    ('chunk_file', 'Read the authorized input.md and create deterministic original-text chunks.'),
    ('embed_text', 'Embed every chunk referenced by the chunk batch handle using the fixed local model.'),
    ('upsert', 'Validate and atomically persist the complete embedding batch, or validate only in dry-run mode.'),
]]
PROMPT = '''You coordinate a private Markdown vector updater. Choose exactly one
tool call for the next stage supplied by the application. Use the supplied
argument verbatim. Do not invent text, vectors, paths, or handles. No other work
is authorized. Call chunk_file, then embed_text, then upsert. Stop on failure.
Return the tool call without commentary or reasoning.'''


class UpdaterState(TypedDict, total=False):
    stage: str
    status: str
    attempt_count: int
    chunk_count: int
    embedded_count: int
    written_count: int
    messages: list
    pending: dict


def stage_message(stage, arguments):
    return {'role': 'user', 'content': json.dumps({'next_tool': stage, 'arguments': arguments})}


class Coordinator:
    def __init__(self, model): self.model = model

    def choose(self, stage, arguments, messages):
        data = self.model.request('POST', '/chat/completions', json={
            'model': MODEL, 'tools': TOOLS,
            'tool_choice': 'required',
            'messages': [{'role': 'system', 'content': PROMPT}, *messages,
                         stage_message(stage, arguments)],
        })
        try:
            choice = data['choices'][0]
            calls = choice['message']['tool_calls']
            if choice['finish_reason'] not in ('tool_calls', 'stop') or len(calls) != 1:
                raise JournalError('updater_invalid_tool_call')
            call = calls[0]
            function = call['function']
            if call.get('type') != 'function' or function['name'] != stage or json.loads(function['arguments']) != arguments:
                raise JournalError('updater_invalid_tool_call')
            # Replace provider IDs/content with bounded application-owned metadata.
            return {'id': 'stage_' + stage, 'type': 'function',
                    'function': {'name': stage, 'arguments': json.dumps(arguments)}}
        except (KeyError, IndexError, TypeError, ValueError):
            raise JournalError('updater_invalid_tool_call') from None


class UpdaterTools:
    def __init__(self, reference, root, model, storage, dry_run=False):
        self.reference, self.root = reference, root
        self.model, self.storage, self.dry_run = model, storage, dry_run
        self.stage = 'chunk_file'
        self.snapshot = None
        self.chunks = self.embeddings = None
        self.chunk_handle = self.embedding_handle = None
        self.generate_at = None

    def arguments(self):
        value = {'chunk_file': 'input.md', 'embed_text': self.chunk_handle, 'upsert': self.embedding_handle}[self.stage]
        return {ARGUMENTS[self.stage]: value}

    def call(self, name, arguments):
        if name != self.stage or arguments != self.arguments():
            raise JournalError('updater_stage_violation')
        if name == 'chunk_file':
            self.snapshot = read_snapshot(self.reference, self.root)
            if not self.snapshot.body.strip():
                self.stage = 'done'
                return {'status': 'skipped', 'chunk_count': 0, 'written_count': 0}
            self.storage.check_document(str(self.snapshot.path), self.snapshot.body)
            budget = min(CHUNK_TOKENS, self.model.context_length - 16)
            self.chunks = chunk_markdown(self.snapshot.body, self.model.count_tokens,
                                         budget, min(OVERLAP_TOKENS, budget // 4))
            if len(self.chunks) > 10000:
                raise JournalError('too_many_chunks')
            self.chunk_handle = secrets.token_urlsafe(18)
            self.stage = 'embed_text'
            return {'chunk_batch_handle': self.chunk_handle, 'chunk_count': len(self.chunks)}
        if name == 'embed_text':
            # Bounded HTTP batches avoid one unbounded model request per file.
            self.embeddings = []
            for start in range(0, len(self.chunks), 16):
                self.embeddings.extend(self.model.embed(self.chunks[start:start + 16]))
            if len(self.embeddings) != len(self.chunks):
                raise JournalError('embedding_batch_incomplete')
            self.embedding_handle = secrets.token_urlsafe(18)
            self.generate_at = dt.datetime.now(dt.timezone.utc).isoformat()
            self.stage = 'upsert'
            return {'embedding_batch_handle': self.embedding_handle, 'embedded_count': len(self.embeddings)}
        self.snapshot.unchanged()
        self.storage.check_document(str(self.snapshot.path), self.snapshot.body)
        count = 0 if self.dry_run else self.storage.replace(str(self.snapshot.path), self.snapshot.body,
                                                           self.embeddings, self.generate_at)
        self.stage = 'done'
        return {'status': 'succeeded', 'written_count': count}

    def clear(self):
        self.snapshot = self.chunks = self.embeddings = None
        self.chunk_handle = self.embedding_handle = None


def build_updater(tools, coordinator):
    def updater(state):
        if state.get('attempt_count', 0) >= 3:
            raise JournalError('updater_iteration_limit')
        call = coordinator.choose(tools.stage, tools.arguments(), state.get('messages', []))
        return {'pending': call, 'attempt_count': state.get('attempt_count', 0) + 1}

    def execute(state):
        call = state['pending']
        name = call['function']['name']
        arguments = json.loads(call['function']['arguments'])
        result = tools.call(name, arguments)
        messages = [*state.get('messages', []), stage_message(name, arguments),
                    {'role': 'assistant', 'content': '', 'tool_calls': [call]},
                    {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)}]
        counters = {key: value for key, value in result.items()
                    if key in ('chunk_count', 'embedded_count', 'written_count', 'status')}
        return {'stage': tools.stage, 'messages': messages, **counters}

    return (StateGraph(UpdaterState).add_node('updater', updater).add_node('tools', execute)
            .add_edge(START, 'updater').add_edge('updater', 'tools')
            .add_conditional_edges('tools', lambda state: END if state['stage'] == 'done' else 'updater')
            .compile())


def update_file(reference, root, model, storage, dry_run=False, coordinator=None):
    tools = UpdaterTools(reference, root, model, storage, dry_run)
    try:
        identity = str(Path(reference).resolve(strict=True))
        lockname = hashlib.sha256(identity.encode()).hexdigest()
        with (Path(tempfile.gettempdir()) / ('jag-ingest-' + lockname + '.lock')).open('a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise JournalError('already_running') from None
            result = build_updater(tools, coordinator or Coordinator(model)).invoke({}, {'recursion_limit': 8})
            return result['status'], result.get('chunk_count', 0), result.get('written_count', 0)
    except (OSError, RuntimeError):
        raise JournalError('read_failed') from None
    finally:
        tools.clear()
