"""Update one Markdown file's vectors, reporting only safe status and counts."""
import os
import sys
import time

from ingest_journal import SafeParser
from journal.obsidian import JournalError
from journal.pipeline import DEFAULT_ROOT, load_config
from journal.updater import update_file
from journal.vector_model import EmbeddingModel
from journal.vector_storage import VectorStorage


def clients():
    load_config()
    model = EmbeddingModel(os.getenv('LM_STUDIO_BASE_URL', 'http://localhost:1234/v1'))
    storage = None
    try:
        model.ready()
        storage = VectorStorage(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_SECRET_KEY'))
        storage.ready()
        return model, storage
    except BaseException:
        model.close()
        if storage: storage.client.close()
        raise


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('file')
    parser.add_argument('--directory')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    model = storage = None
    try:
        model, storage = clients()
        start = time.monotonic()
        status, chunks, written = update_file(args.file, args.directory or os.getenv('OBSIDIAN_JOURNAL_DIR', DEFAULT_ROOT),
                                              model, storage, args.dry_run)
        print(f'{status} chunks={chunks} written={written} seconds={time.monotonic()-start:.2f}')
        return 0
    except KeyboardInterrupt:
        print('failed code=interrupted', file=sys.stderr)
    except JournalError as error:
        print(f'failed code={error.args[0]}', file=sys.stderr)
    except Exception:
        print('failed code=unexpected_error', file=sys.stderr)
    finally:
        if model: model.close()
        if storage: storage.client.close()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
