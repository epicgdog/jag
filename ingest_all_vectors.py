"""Sequentially update vectors for a bounded Obsidian journal tree."""
import os
import sys
import time

from ingest_all_journals import discover
from ingest_journal import SafeParser
from journal.obsidian import JournalError
from journal.pipeline import DEFAULT_ROOT, load_config
from journal.updater import update_file
from update_vectors import clients


SHARED = {
    'model_unavailable', 'model_redirect', 'invalid_model_endpoint',
    'embedding_model_not_loaded', 'embedding_configuration', 'embedding_context_invalid',
    'storage_unavailable', 'storage_configuration',
}


def run(root, paths, model, storage, dry_run=False, output=print):
    total = len(paths)
    succeeded = skipped = failed = processed = 0
    for index, path in enumerate(paths, 1):
        start = time.monotonic()
        try:
            status, chunks, written = update_file(path, root, model, storage, dry_run)
            if status == 'skipped':
                skipped += 1
            else:
                succeeded += 1
            output(f'{index}/{total} {status} chunks={chunks} written={written} seconds={time.monotonic()-start:.2f}')
        except KeyboardInterrupt:
            output(f'{index}/{total} interrupted')
            break
        except JournalError as error:
            failed += 1
            output(f'{index}/{total} failed code={error.args[0]} seconds={time.monotonic()-start:.2f}')
            if error.args[0] in SHARED:
                processed = index
                break
        except Exception:
            failed += 1
            output(f'{index}/{total} failed code=unexpected_error')
        processed = index
    output(f'discovered={total} succeeded={succeeded} skipped={skipped} failed={failed} unprocessed={total-processed}')
    return 1 if failed or processed < total else 0


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('--directory')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    model = storage = None
    try:
        load_config()
        root, paths = discover(args.directory or os.getenv('OBSIDIAN_JOURNAL_DIR', DEFAULT_ROOT))
        if not paths:
            return run(root, paths, None, None, args.dry_run)
        model, storage = clients()
        return run(root, paths, model, storage, args.dry_run)
    except KeyboardInterrupt:
        print('failed code=interrupted', file=sys.stderr)
    except JournalError as error:
        print(f'failed code={error.args[0]}', file=sys.stderr)
    except Exception:
        print('failed code=unexpected_error', file=sys.stderr)
    finally:
        if model:
            model.close()
        if storage:
            storage.client.close()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
