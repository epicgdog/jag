create index document_document_date_idx on public.document (document_date);
create index todo_pending_document_idx on public.todo (document_source, document_id) where checked = false;

create function public.set_journal_updated_at() returns trigger
language plpgsql set search_path = pg_catalog as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger document_set_updated_at before update on public.document
for each row execute function public.set_journal_updated_at();
create trigger document_summary_set_updated_at before update on public.document_summary
for each row execute function public.set_journal_updated_at();
create trigger todo_set_updated_at before update on public.todo
for each row execute function public.set_journal_updated_at();

alter table public.document enable row level security;
alter table public.document_summary enable row level security;
alter table public.todo enable row level security;

-- Backend-only access: service_role bypasses RLS; public client roles have no policies or CRUD grants.
revoke all on table public.document, public.document_summary, public.todo from public, anon, authenticated;
grant select, insert, update, delete on table public.document, public.document_summary, public.todo to service_role;
comment on table public.document is 'Private journal documents; access is reserved for the backend service role.';
