# Journal ingestion

M2 uses local LM Studio at `http://localhost:1234/v1` with model `qwen3.5-9b-mlx` and the model's saved settings. Inference has no remote fallback. The conservative input budget is 12,000 UTF-8 bytes including the prompt; larger entries fail rather than being truncated. The application persists full journal content, summaries and tasks to Supabase on write runs.

Install dependencies with `uv sync`. Configure `.env.local` or environment variables: `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (or legacy `SUPABASE_SERVICE_ROLE_KEY`); Notion imports additionally require `NOTION_API_KEY` or `NOTION_API_TOKEN`. `OBSIDIAN_JOURNAL_DIR` defaults to `/Users/your-user/Documents/vaults/main/journal`. `LM_STUDIO_BASE_URL`, if set, must be `http://localhost:1234/v1`. Never commit credentials.

Review and deploy the versioned Supabase migrations through your normal deployment process, for example `supabase db push` after explicitly selecting the intended project. This was not run by implementation. The RPC is service-role-only; `journal_ingest_ready` checks permissions without reading or writing journal rows.

```sh
uv run python ingest_journal.py obsidian /absolute/path/to/journal/2025-12-31.md --dry-run
uv run python ingest_journal.py obsidian /absolute/path/to/journal/2025-12-31.md
uv run python ingest_all_journals.py --directory /absolute/path/to/journal --dry-run
uv run python ingest_all_journals.py --directory /absolute/path/to/journal
uv run python ingest_journal.py notion NOTION_PAGE_URL_OR_ID --date-property Date
uv run python ingest_journal.py notion NOTION_PAGE_URL_OR_ID --date 2025-12-31
```

Perform Obsidian imports first and resolve failures before importing Notion. Dry runs summarize locally but never write. Batch runs are sequential and continue after document-specific failures; shared service failures stop the run. Status output contains no paths or content. Re-runs regenerate summaries and upsert tasks, but do not delete tasks missing from the source. Obsidian task IDs prefer explicit block IDs; fallback IDs depend on normalized text and occurrence, so edits or reordering identical tasks can leave old rows. File renames create new document identities.

Dates come from explicit frontmatter, complete filename/title dates, and marked `Date:` or `Journal Date:` lines. Conflicts, missing dates and invalid dates fail. A single-file `--date YYYY-MM-DD` overrides all other date candidates, including a missing Notion date property. The batch has no global date override. Summaries contain their generation timestamp, while the document owns its entry date. Files must resolve inside the configured root; hidden files and directories are excluded from batch discovery.

Run synthetic tests with `uv run python -m unittest discover -s tests`. Database tests require a disposable Supabase-compatible PostgreSQL database with pgTAP available; run the SQL under `supabase/tests/database` only there. Do not use real journal data for development tests.

Model errors are reported without response text: `model_response_truncated`
means generation hit its limit; `model_response_reasoning` means thinking tags
were returned. There is no hard summary word limit; complete summaries are not
rejected because they exceed 120 words. Output-token limits in LM Studio are
separate from the input context window and do not map directly to word counts.
Summaries are requested and stored as one plain-text paragraph, without bullet
points. Formatting differences do not cause failures. Empty, incomplete, invalid JSON,
and malformed API responses have separate codes. Failed summaries are not saved.
