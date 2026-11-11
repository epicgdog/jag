# Journal database migrations

These versioned migrations create `document`, `document_summary`, and `todo` in `public`. They are intended for the existing Supabase project; they do not provision or link a project. Apply the migration files in timestamp order.

A document is identified by `(source, id)`: an absolute Obsidian path or a lowercase hyphenated Notion page UUID. `document_date` is the entry date, not the import date. A summary is owned by a document and has conflict key `(document_source, document_id)`; when replacing it, update `generated_at` as well. A todo has conflict key `(document_source, document_id, id)`. Both dependent keys cascade on parent update and delete. Obsidian renames require an explicit parent key update. Failed reads must not cause deletion.

RLS is enabled without client policies. Only the private backend `service_role` has CRUD access; keep its secret key out of client applications. Updating a row sets `updated_at` to the transaction time.

## Local validation

Use an isolated disposable Supabase Postgres instance, never a database containing user data. Apply both files in `migrations/` in order, then run each `tests/database/*.test.sql` with pgTAP available (for example, `psql -v ON_ERROR_STOP=1 -f <file>`). Inspect the TAP output for failures as well as SQL errors. Tests use synthetic fixtures and roll back. Alternatively, where a separately configured local Supabase CLI environment already exists, use its database test runner after applying the migrations. No local CLI configuration is required for the SQL files.

## Hosted deployment, later

Review the migrations and target before applying. With the Supabase CLI authenticated and linked to the **existing** intended project, run `supabase db push` from the repository root after configuring the CLI for that project. Alternatively, use the CLI's documented database connection workflow. API URL and API keys alone do not authorize migration deployment. This milestone does not apply hosted changes.
