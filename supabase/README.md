# Journal database migrations

These versioned migrations create `document`, `document_summary`, `todo`, and `vectors` in `public`. They are intended for the existing Supabase project; they do not provision or link a project. Apply the migration files in timestamp order.

A document is identified by `(source, id)`: an absolute Obsidian path or a lowercase hyphenated Notion page UUID. `document_date` is the entry date, not the import date. A summary is owned by a document and has conflict key `(document_source, document_id)`; when replacing it, update `generated_at` as well. A todo has conflict key `(document_source, document_id, id)`. Both dependent keys cascade on parent update and delete. Obsidian renames require an explicit parent key update. Failed reads must not cause deletion.

RLS is enabled without client policies. Only the private backend `service_role` has CRUD access; keep its secret key out of client applications. Updating a row sets `updated_at` to the transaction time.

The vector migration enables pgvector in the `extensions` schema and requires it
to be installed there. `vectors` has exactly `document_source`, `document_id`,
`chunk_index`, `embedding` (`vector(1024)`), and `generate_at`. Its composite key
identifies each page chunk. `replace_vectors` checks the parent content under a
row lock and atomically replaces a complete chunk set, including deleting surplus
old chunks. `match_vectors` returns cosine-ranked chunk identities and scores
with optional parent-date/source filters. Both RPCs are restricted to the backend.

## Local validation

Use an isolated disposable Supabase Postgres instance with pgvector, never a database containing user data. Apply all four files in `migrations/` in order, then run each `tests/database/*.test.sql` with pgTAP available (for example, `psql -v ON_ERROR_STOP=1 -f <file>`). Inspect the TAP output for failures as well as SQL errors. Tests use synthetic fixtures and roll back. Alternatively, where a separately configured local Supabase CLI environment already exists, use its database test runner after applying the migrations. No local CLI configuration is required for the SQL files.

The new vector pgTAP suite has not yet been executed locally: pulling a fresh
test image failed in the macOS Docker credential helper. Python tests use mocked
storage and do not substitute for SQL execution. Do not run fixture SQL against
the hosted journal database.

On November 11, 2026, authenticated Supabase CLI migration-history inspection
confirmed that project `jag` has migrations `20261111000000`–`20261111000002`
applied. Migration `20261111000003` remains pending. No hosted migration or
journal-data access was performed during this check.

## Hosted deployment, later

Review the migrations and target before applying. With the Supabase CLI authenticated and linked to the **existing** intended project, run `supabase db push` from the repository root after configuring the CLI for that project. Alternatively, use the CLI's documented database connection workflow. API URL and API keys alone do not authorize migration deployment. This milestone does not apply hosted changes.
