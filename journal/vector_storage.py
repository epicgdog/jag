"""Backend-only complete-set vector persistence; private content stays inside runtime."""
from journal.obsidian import JournalError
from journal.storage import Storage
from journal.vector_model import validate_vector


class VectorStorage(Storage):
    def ready(self):
        try:
            if self.rpc('vector_ingest_ready', {}).json() is not True:
                raise JournalError('storage_unavailable')
        except ValueError:
            raise JournalError('storage_unavailable') from None

    def check_document(self, identity, content):
        try:
            status = self.rpc('check_vector_document', {
                'p_source': 'obsidian', 'p_id': identity, 'p_content': content,
            }).json()
        except ValueError:
            raise JournalError('storage_unavailable') from None
        if status not in ('ready', 'parent_missing', 'parent_out_of_sync'):
            raise JournalError('storage_unavailable')
        if status != 'ready':
            raise JournalError(status)

    def replace(self, identity, content, embeddings, generate_at):
        if not embeddings or len(embeddings) > 10000:
            raise JournalError('embedding_batch_incomplete')
        values = [validate_vector(vector) for vector in embeddings]
        try:
            count = self.rpc('replace_vectors', {
                'p_source': 'obsidian', 'p_id': identity, 'p_content': content,
                'p_embeddings': values, 'p_generate_at': generate_at,
            }).json()
        except ValueError:
            raise JournalError('storage_unavailable') from None
        if type(count) is not int or count != len(values):
            raise JournalError('storage_unavailable')
        return count
