-- Narrow backend-only atomic document import. No dynamic SQL or deletion.
create function public.ingest_journal(p_document jsonb, p_summary jsonb, p_tasks jsonb)
returns void language plpgsql security invoker set search_path = pg_catalog as $$
declare task jsonb;
begin
  if jsonb_typeof(p_document) <> 'object' or jsonb_typeof(p_summary) <> 'object'
     or jsonb_typeof(p_tasks) <> 'array' or p_document is null or p_summary is null or p_tasks is null
     or nullif(btrim(p_document->>'source'), '') is null
     or nullif(btrim(p_document->>'id'), '') is null
     or nullif(btrim(p_document->>'document_date'), '') is null
     or nullif(btrim(p_document->>'content'), '') is null
     or nullif(btrim(p_summary->>'summary'), '') is null
     or nullif(btrim(p_summary->>'model'), '') is null
     or nullif(btrim(p_summary->>'generated_at'), '') is null then
    raise exception 'invalid input';
  end if;
  if exists (select 1 from jsonb_array_elements(p_tasks) t where jsonb_typeof(t) <> 'object'
      or nullif(btrim(t->>'id'), '') is null or nullif(btrim(t->>'text'), '') is null
      or jsonb_typeof(t->'checked') is distinct from 'boolean')
     or (select count(*) <> count(distinct t->>'id') from jsonb_array_elements(p_tasks) t) then
    raise exception 'invalid tasks';
  end if;
  insert into public.document (source,id,document_date,title,content,source_updated_at)
  values (p_document->>'source',p_document->>'id',(p_document->>'document_date')::date,p_document->>'title',p_document->>'content',(p_document->>'source_updated_at')::timestamptz)
  on conflict (source,id) do update set document_date=excluded.document_date,title=excluded.title,content=excluded.content,source_updated_at=excluded.source_updated_at;
  insert into public.document_summary (document_source,document_id,summary,model,generated_at)
  values (p_document->>'source',p_document->>'id',p_summary->>'summary',p_summary->>'model',(p_summary->>'generated_at')::timestamptz)
  on conflict (document_source,document_id) do update set summary=excluded.summary,model=excluded.model,generated_at=excluded.generated_at;
  for task in select value from jsonb_array_elements(p_tasks) loop
    insert into public.todo (document_source,document_id,id,text,checked)
    values (p_document->>'source',p_document->>'id',task->>'id',task->>'text',(task->>'checked')::boolean)
    on conflict (document_source,document_id,id) do update set text=excluded.text,checked=excluded.checked;
  end loop;
end; $$;

create function public.journal_ingest_ready() returns boolean
language sql stable security invoker set search_path = pg_catalog as $$
  select has_function_privilege(current_user, 'public.ingest_journal(jsonb,jsonb,jsonb)', 'EXECUTE')
    and has_table_privilege(current_user, 'public.document', 'INSERT,UPDATE')
    and has_table_privilege(current_user, 'public.document_summary', 'INSERT,UPDATE')
    and has_table_privilege(current_user, 'public.todo', 'INSERT,UPDATE');
$$;
revoke all on function public.ingest_journal(jsonb,jsonb,jsonb), public.journal_ingest_ready() from public, anon, authenticated;
grant execute on function public.ingest_journal(jsonb,jsonb,jsonb), public.journal_ingest_ready() to service_role;
