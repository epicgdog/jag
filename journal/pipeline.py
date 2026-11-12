"""Shared Obsidian ingestion and safe configuration."""
import fcntl
import hashlib
import os
import tempfile
from pathlib import Path
from journal.model import LocalModel
from journal.obsidian import JournalError, read_obsidian
from journal.storage import Storage

DEFAULT_ROOT = str(Path.home() / 'Documents/vaults/main/journal')

def load_config():
    path = Path(__file__).resolve().parent.parent / '.env.local'
    try:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))
    except OSError:
        raise JournalError('configuration_error') from None

def clients(dry_run):
    load_config()
    model = LocalModel(os.getenv('LM_STUDIO_BASE_URL', 'http://localhost:1234/v1'))
    storage = None
    try:
        model.ready()
        storage = None if dry_run else Storage(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_SECRET_KEY'))
        if storage: storage.ready()
        return model, storage
    except BaseException:
        model.client.close()
        if storage: storage.client.close()
        raise

def ingest(path, root, model, storage=None, override=None):
    # Resolve first so aliases share a lock; no document text is sent before locking.
    try:
        identity = str(Path(path).resolve(strict=True))
        lockname = hashlib.sha256(identity.encode()).hexdigest()
        lockpath = Path(tempfile.gettempdir()) / ('jag-ingest-' + lockname + '.lock')
        with lockpath.open('a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise JournalError('already_running') from None
            doc = read_obsidian(path, root, override)
            if doc.get('empty'): return 'skipped', 0
            summary = model.summarize(doc['document_date'], doc['content'])
            if storage: storage.save(doc, summary)
            return 'succeeded', len(doc['tasks'])
    except OSError:
        raise JournalError('read_failed') from None
