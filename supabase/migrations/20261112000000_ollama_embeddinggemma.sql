-- Switch to the user-authorized Ollama EmbeddingGemma model (768 dimensions).
-- Never truncate, pad, or reuse vectors from the previous embedding model.
-- Refuse conversion when vectors exist; re-embedding needs a separate reviewed rebuild.
do $$begin
  if exists (select 1 from public.vectors limit 1) then
    raise exception 'embedding_model_change_requires_empty_vectors_and_reembedding';
  end if;
end; $$;

alter table public.vectors alter column embedding type extensions.vector(768);

create or replace function public.replace_vectors(p_source text, p_id text, p_content text,
  p_embeddings jsonb, p_generate_at timestamptz)
returns integer language plpgsql security invoker set search_path = pg_catalog as $$
declare stored_content text; item jsonb; position integer := 0; value extensions.vector;
begin
  if p_content is null or length(btrim(p_content))=0 or p_generate_at is null
     or p_embeddings is null or jsonb_typeof(p_embeddings) <> 'array' then
    raise exception 'invalid_vector_batch';
  end if;
  if jsonb_array_length(p_embeddings) not between 1 and 10000 then
    raise exception 'invalid_vector_batch';
  end if;
  -- Locks against imports/other updater transactions; parent changes cannot race persistence.
  select content into stored_content from public.document where source=p_source and id=p_id for update;
  if not found then raise exception 'parent_missing'; end if;
  if stored_content is distinct from p_content then raise exception 'parent_out_of_sync'; end if;
  for item in select v from jsonb_array_elements(p_embeddings) as t(v) loop
    if jsonb_typeof(item) <> 'array' then raise exception 'invalid_vector_batch'; end if;
    value := item::text::extensions.vector;
    if extensions.vector_dims(value) <> 768 or extensions.vector_norm(value) <= 0 then
      raise exception 'invalid_embedding';
    end if;
    insert into public.vectors(document_source,document_id,chunk_index,embedding,generate_at)
    values(p_source,p_id,position,value,p_generate_at)
    on conflict(document_source,document_id,chunk_index) do update
      set embedding=excluded.embedding,generate_at=excluded.generate_at;
    position := position+1;
  end loop;
  delete from public.vectors where document_source=p_source and document_id=p_id and chunk_index >= position;
  return position;
end; $$;

create or replace function public.match_vectors(query_embedding extensions.vector, match_count integer default 10,
  min_similarity double precision default null, date_start date default null,
  date_end date default null, source_filter text default null)
returns table(document_source text, document_id text, chunk_index integer,
  similarity double precision, generate_at timestamptz)
language plpgsql stable security invoker set search_path = pg_catalog as $$
begin
  if query_embedding is null or extensions.vector_dims(query_embedding) <> 768
     or extensions.vector_norm(query_embedding) <= 0 then raise exception 'invalid_embedding'; end if;
  if match_count is null or match_count not between 1 and 100 then raise exception 'invalid_limit'; end if;
  if min_similarity is not null and not (min_similarity between -1 and 1) then raise exception 'invalid_threshold'; end if;
  if date_start > date_end then raise exception 'invalid_date_range'; end if;
  if source_filter is not null and source_filter not in ('obsidian','notion') then raise exception 'invalid_source'; end if;
  return query
  select v.document_source,v.document_id,v.chunk_index,
    1-(v.embedding operator(extensions.<=>) query_embedding),v.generate_at
  from public.vectors v join public.document d on d.source=v.document_source and d.id=v.document_id
  where (date_start is null or d.document_date >= date_start)
    and (date_end is null or d.document_date <= date_end)
    and (source_filter is null or d.source=source_filter)
    and (min_similarity is null or 1-(v.embedding operator(extensions.<=>) query_embedding) >= min_similarity)
  order by v.embedding operator(extensions.<=>) query_embedding,v.document_source,v.document_id,v.chunk_index
  limit match_count;
end; $$;
