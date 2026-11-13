# jag

Retrieve pages from the Journal Notion database.

## Setup

Put the integration token in `.env.local`:

```text
NOTION_API_KEY=secret_or_ntn_token_here
```

The Notion integration must be connected to the target database. Set
`NOTION_DATABASE_ID` in `.env.local` or pass its URL/ID with `--database`.

For a private backend sync to Supabase, fill in `SUPABASE_URL` and
`SUPABASE_SECRET_KEY` in `.env.local`. `SUPABASE_PUBLISHABLE_KEY` is optional
for client access using Supabase Auth and Row Level Security. Secret keys must
stay server-side. The existing `NOTION_API_TOKEN` is supported as a fallback.

## Usage

List every page in a database (the script follows Notion pagination):

```bash
uv run python main.py --database DATABASE_URL_OR_ID --output journal-pages.json
```

Print the pages directly:

```bash
uv run python main.py --database DATABASE_URL_OR_ID
```

Retrieve one page by ID:

```bash
uv run python main.py --page-id PAGE_ID
```

The output contains each page's properties and Notion page metadata. To get
the blocks/content inside a page, call `GET /v1/blocks/{page_id}/children`
after retrieving its page ID.

## Extract to-dos

Extract checkbox blocks from a page URL or ID, including nested blocks:

```bash
uv run python extract_todos.py "PAGE_URL_OR_ID"
uv run python extract_todos.py "PAGE_URL_OR_ID" --unchecked
```

Output is JSON containing each to-do's block ID, text, and checked status.
The integration must have access to the page. Pagination is handled automatically;
separate child pages and databases are not traversed.

## Journal agents and embeddings

Copy `.env.example` to `.env.local` and configure your own server and backend
credentials. Local configuration, journal exports, planning notes, and Supabase
CLI caches are ignored by Git.

`OLLAMA_BASE_URL` selects the explicitly authorized Ollama origin for both
`gemma4:e4b` agent chat and `embeddinggemma-2` embeddings. It defaults to
`http://localhost:11434`; alternate hosts must be configured in `.env.local`.
`OBSIDIAN_JOURNAL_DIR` optionally overrides `~/Documents/vaults/main/journal`.
No journal content, summaries, or vector values are printed by ingestion.

```bash
uv run python plan_query.py "What unfinished tasks did I record last week?"
uv run python update_vectors.py /absolute/path/to/journal.md --dry-run
uv run python ingest_all_vectors.py
```

Vector ingestion requires matching parent documents already imported through
the journal-ingestion workflow. See [database setup](supabase/README.md).
