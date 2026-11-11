"""Ingest one journal without printing private content."""
import argparse
import os
import sys
import time
from journal.obsidian import JournalError
from journal.pipeline import DEFAULT_ROOT, clients, ingest

class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, 'error: invalid arguments\n')

def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('source', choices=['obsidian'])
    parser.add_argument('reference')
    parser.add_argument('--date')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    start = time.monotonic()
    model = storage = None
    try:
        model, storage = clients(args.dry_run)
        status, count = ingest(args.reference, os.getenv('OBSIDIAN_JOURNAL_DIR', DEFAULT_ROOT), model, storage, args.date)
        print(f'{status} tasks={count} seconds={time.monotonic()-start:.2f}')
        return 0
    except JournalError as error:
        print(f'failed code={error.args[0]}', file=sys.stderr)
    except Exception:
        print('failed code=unexpected_error', file=sys.stderr)
    finally:
        if model: model.client.close()
        if storage: storage.client.close()
    return 1
if __name__ == '__main__': raise SystemExit(main())
