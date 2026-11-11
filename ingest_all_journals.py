"""Sequentially ingest a bounded Obsidian journal tree."""
import os
import sys
import time
from pathlib import Path
from ingest_journal import SafeParser
from journal.obsidian import JournalError
from journal.pipeline import DEFAULT_ROOT, clients, ingest, load_config

SHARED = {'model_unavailable', 'model_redirect', 'storage_unavailable', 'storage_configuration', 'invalid_model_endpoint'}

def discover(directory):
    try:
        root = Path(directory).resolve(strict=True)
        if not root.is_dir(): raise OSError()
        paths = set()
        def onerror(error): raise error
        for current, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(current)/d).is_symlink())
            for name in files:
                if name.startswith('.') or not name.lower().endswith('.md'): continue
                path = (Path(current)/name).resolve(strict=True)
                if not path.is_relative_to(root): raise JournalError('discovery_failed')
                if path.is_file(): paths.add(path)
        return root, sorted(paths, key=str)
    except (OSError, RuntimeError):
        raise JournalError('discovery_failed') from None

def run(root, paths, model, storage, output=print):
    total=len(paths); succeeded=skipped=failed=processed=0
    for index, path in enumerate(paths,1):
        start=time.monotonic()
        try:
            status,count=ingest(path,root,model,storage)
            if status == 'skipped': skipped += 1
            else: succeeded += 1
            output(f'{index}/{total} {status} tasks={count} seconds={time.monotonic()-start:.2f}')
        except KeyboardInterrupt:
            output(f'{index}/{total} interrupted')
            break
        except JournalError as error:
            failed += 1
            output(f'{index}/{total} failed code={error.args[0]} seconds={time.monotonic()-start:.2f}')
            if error.args[0] in SHARED:
                processed=index
                break
        except Exception:
            failed += 1
            output(f'{index}/{total} failed code=unexpected_error')
        processed=index
    output(f'discovered={total} succeeded={succeeded} skipped={skipped} failed={failed} unprocessed={total-processed}')
    return 1 if failed or processed < total else 0

def main(argv=None):
    parser=SafeParser(description=__doc__)
    parser.add_argument('--directory')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    model = storage = None
    try:
        load_config()
        root, paths=discover(args.directory or os.getenv('OBSIDIAN_JOURNAL_DIR',DEFAULT_ROOT))
        if not paths: return run(root, paths, None, None)
        model, storage=clients(args.dry_run)
        return run(root,paths,model,storage)
    except KeyboardInterrupt:
        print('failed code=interrupted',file=sys.stderr)
    except JournalError as error:
        print(f'failed code={error.args[0]}',file=sys.stderr)
    except Exception:
        print('failed code=unexpected_error',file=sys.stderr)
    finally:
        if model: model.client.close()
        if storage: storage.client.close()
    return 1
if __name__ == '__main__': raise SystemExit(main())
