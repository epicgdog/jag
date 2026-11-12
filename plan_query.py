"""Print a local journal retrieval plan; does not read journals or query Supabase."""
import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ingest_journal import SafeParser
from journal.obsidian import JournalError
from journal.planner import PlannerModel, build_planner


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('query', nargs='?', help='Omit to try queries interactively.')
    parser.add_argument('--date', type=dt.date.fromisoformat, help='Reference date (YYYY-MM-DD).')
    parser.add_argument('--timezone', default='America/Los_Angeles')
    args = parser.parse_args(argv)
    model = None
    try:
        ZoneInfo(args.timezone)
        model = PlannerModel()
        graph = build_planner(model)

        def run(query):
            state = {'query': query, 'timezone': args.timezone}
            if args.date:
                state['reference_date'] = args.date.isoformat()
            result = graph.invoke(state)
            print(json.dumps(result, indent=2, ensure_ascii=False))

        if args.query is not None:
            run(args.query)
        else:
            print('Enter a query; /quit or Ctrl-D exits. Each query is independent.')
            while True:
                try:
                    query = input('Query> ')
                except EOFError:
                    break
                if query.strip() == '/quit':
                    break
                if not query.strip():
                    continue
                try:
                    run(query)
                except JournalError as error:
                    print(f'failed code={error.args[0]}', file=sys.stderr)
        return 0
    except ZoneInfoNotFoundError:
        print('failed code=invalid_timezone', file=sys.stderr)
    except JournalError as error:
        print(f'failed code={error.args[0]}', file=sys.stderr)
    except KeyboardInterrupt:
        return 130
    except Exception:
        print('failed code=unexpected_error', file=sys.stderr)
    finally:
        if model:
            model.client.close()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
