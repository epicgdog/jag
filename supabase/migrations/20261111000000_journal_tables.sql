-- External IDs are scoped by source; dates describe entries, not imports.
create table public.document (
  source text not null,
  id text not null,
  document_date date not null,
  title text,
  content text,
  source_updated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint document_pkey primary key (source, id),
  constraint document_source_check check (source in ('obsidian', 'notion')),
  constraint document_id_nonblank check (length(btrim(id)) > 0),
  constraint document_source_id_check check (
    (source = 'obsidian' and left(id, 1) = '/') or
    (source = 'notion' and id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
  )
);

-- Each dependent is owned by its document and follows changes to its key.
create table public.document_summary (
  document_source text not null,
  document_id text not null,
  summary text not null,
  model text,
  generated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint document_summary_pkey primary key (document_source, document_id),
  constraint document_summary_summary_nonblank check (length(btrim(summary)) > 0),
  constraint document_summary_document_fkey foreign key (document_source, document_id)
    references public.document (source, id) on update cascade on delete cascade
);

create table public.todo (
  document_source text not null,
  document_id text not null,
  id text not null,
  text text not null,
  checked boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint todo_pkey primary key (document_source, document_id, id),
  constraint todo_id_nonblank check (length(btrim(id)) > 0),
  constraint todo_text_nonblank check (length(btrim(text)) > 0),
  constraint todo_document_fkey foreign key (document_source, document_id)
    references public.document (source, id) on update cascade on delete cascade
);

comment on column public.document.id is 'Obsidian absolute path or lowercase hyphenated Notion page UUID; identity is scoped by source.';
comment on column public.document.document_date is 'Journal entry date, not the import date.';
comment on table public.document_summary is 'At most one current summary, owned by its document.';
comment on table public.todo is 'Tasks are owned by their document; IDs are stable within that document.';
