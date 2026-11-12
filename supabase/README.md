# Journal database migrations

These versioned migrations create `document`, `document_summary`, `todo`, and `vectors` in `public`. They are intended for the existing Supabase project; they do not provision or link a project. Apply the migration files in timestamp order.

A document is identified by `(source, id)`: an absolute Obsidian path or a lowercase hyphenated Notion page UUID. `document_date` is the entry date, not the import date. A summary is owned by a document and has conflict key `(document_source, document_id)`; when replacing it, update `generated_at` as well. A todo has conflict key `(document_source, document_id, id)`. Both dependent keys cascade on parent update and delete. Obsidian renames require an explicit parent key update. Failed reads must not cause deletion.

RLS is enabled without client policies. Only the private backend `service_role` has CRUD access; keep its secret key out of client applications. Updating a row sets `updated_at` to the transaction time.

The vector migration enables pgvector in the `extensions` schema and requires it
to be installed there. `vectors` has exactly `document_source`, `document_id`,
`chunk_index`, `embedding` (`vector(768)` after the EmbeddingGemma migration), and `generate_at`. Its composite key
identifies each page chunk. `replace_vectors` checks the parent content under a
row lock and atomically replaces a complete chunk set, including deleting surplus
old chunks. `match_vectors` returns cosine-ranked chunk identities and scores
with optional parent-date/source filters. Both RPCs are restricted to the backend.

## Local validation

Use an isolated disposable Supabase Postgres instance with pgvector, never a database containing user data. Apply all five files in `migrations/` in order, then run each `tests/database/*.test.sql` with pgTAP available (for example, `psql -v ON_ERROR_STOP=1 -f <file>`). Inspect the TAP output for failures as well as SQL errors. Tests use synthetic fixtures and roll back. Alternatively, where a separately configured local Supabase CLI environment already exists, use its database test runner after applying the migrations. No local CLI configuration is required for the SQL files.

All four SQL suites passed on November 12, 2026: 83 pgTAP checks in a fresh
native Supabase Postgres instance containing only synthetic fixtures. All five
migrations applied there successfully. The native runtime avoided the earlier
Docker credential-helper problem, and the disposable stack was destroyed after
testing. Python validation also passes (61 tests). Do not run fixture SQL against
the hosted journal database.

## Hosted deployment

The user-authorized deployment to `jag` (`YOUR_PROJECT_REF`) completed on
November 12, 2026. CLI migration history confirmed all five migration versions
are applied, through `20261112000000`. Schema-only checks confirmed the exact
five vector columns, `extensions.vector(768)`, RLS, 768-dimension function checks,
backend function grants, and denied client access. The application's backend
readiness RPC also returned true using the existing project credentials.
No journal rows were inspected or imported, and vault secrets/seed data were
not modified.

For future authorized deployments, authenticate the CLI or supply
`SUPABASE_ACCESS_TOKEN` through the environment, review the pending migrations,
and use an explicit project target, for example:

```bash
npx --yes supabase db push --remote=YOUR_PROJECT_REF --skip-vault
```

Keep tokens in local credential storage; never commit them or include their
values in deployment commands or logs.

## Ollama EmbeddingGemma configuration update

`20261112000000_ollama_embeddinggemma.sql` changes the vector column and RPC
dimension checks from 1024 to 768 for the user's `embeddinggemma-2` alias on
`http://127.0.0.1:11434`. The original migration is unchanged. The new
migration refuses to run if vectors already exist; a model change requires
re-embedding, not numeric truncation or padding. No rows are deleted by this
migration. The SQL fixtures now target the final 768-dimensional schema.

The user's later instruction authorized model testing and deployment. Both
Ollama models passed synthetic inference checks, the SQL suites passed in a
disposable database, and the migration is deployed. These checks did not access
real journal files or content.
