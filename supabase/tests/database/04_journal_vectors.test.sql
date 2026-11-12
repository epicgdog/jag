begin;
create extension if not exists pgtap;
select no_plan();
create function pg_temp.v(x real, y real default 0) returns extensions.vector language sql as $$
  select (array[x,y] || array_fill(0::real,array[1022]))::extensions.vector;
$$;
insert into public.document(source,id,document_date,content) values
  ('obsidian','/synthetic/vectors-a.md','2026-09-01','Synthetic A'),
  ('obsidian','/synthetic/vectors-b.md','2026-10-01','Synthetic B');
select is((select count(*)::integer from information_schema.columns where table_schema='public' and table_name='vectors'),5,'exactly five columns');
select ok((select relrowsecurity from pg_class where oid='public.vectors'::regclass),'RLS enabled');
select ok(not has_table_privilege('anon','public.vectors','SELECT'),'anon denied');
select ok(not has_function_privilege('authenticated','public.match_vectors(extensions.vector,integer,double precision,date,date,text)','EXECUTE'),'client RPC denied');
select ok(has_function_privilege('service_role','public.replace_vectors(text,text,text,jsonb,timestamptz)','EXECUTE'),'backend write permitted');
select is(public.check_vector_document('obsidian','/synthetic/missing.md','x'),'parent_missing','missing parent');
select is(public.check_vector_document('obsidian','/synthetic/vectors-a.md','changed'),'parent_out_of_sync','changed parent');
select is(public.replace_vectors('obsidian','/synthetic/vectors-a.md','Synthetic A',
  jsonb_build_array(pg_temp.v(1)::text::jsonb,pg_temp.v(0,1)::text::jsonb),now()),2,'two chunks inserted');
select is(public.replace_vectors('obsidian','/synthetic/vectors-b.md','Synthetic B',
  jsonb_build_array(pg_temp.v(0,1)::text::jsonb),now()),1,'second page inserted');
select is((select document_id from public.match_vectors(pg_temp.v(1),1)), '/synthetic/vectors-a.md','cosine ranking');
select is((select count(*)::integer from public.match_vectors(pg_temp.v(1),10,0.9)),1,'threshold');
select is((select count(*)::integer from public.match_vectors(pg_temp.v(1),10,null,'2026-10-01','2026-10-31','obsidian')),1,'date/source before limit');
select is((select document_id from public.match_vectors(pg_temp.v(1),1,null,'2026-10-01','2026-10-31')), '/synthetic/vectors-b.md','filtered top one');
select throws_ok($$select * from public.match_vectors('[1,0]'::extensions.vector)$$,'P0001','invalid_embedding','dimension rejected');
select throws_ok($$select * from public.match_vectors(pg_temp.v(0))$$,'P0001','invalid_embedding','zero rejected');
select throws_ok($$select * from public.match_vectors(pg_temp.v(1),0)$$,'P0001','invalid_limit','limit rejected');
select throws_ok($$select * from public.match_vectors(pg_temp.v(1),10,2)$$,'P0001','invalid_threshold','threshold rejected');
select throws_ok($$select * from public.match_vectors(pg_temp.v(1),10,null,'2026-11-01','2026-01-01')$$,'P0001','invalid_date_range','dates rejected');
select throws_ok($$select * from public.match_vectors(pg_temp.v(1),10,null,null,null,'arbitrary')$$,'P0001','invalid_source','source rejected');
select throws_ok($$select public.replace_vectors('obsidian','/synthetic/vectors-a.md','changed',jsonb_build_array(pg_temp.v(1)::text::jsonb),now())$$,'P0001','parent_out_of_sync','snapshot guard');
select throws_ok($$select public.replace_vectors('obsidian','/synthetic/vectors-a.md','Synthetic A',jsonb_build_array(pg_temp.v(0,1)::text::jsonb,'[1,0]'::jsonb),now())$$,'P0001','invalid_embedding','bad later chunk rolls back');
select is((select count(*)::integer from public.vectors where document_id='/synthetic/vectors-a.md'),2,'prior set preserved');
select is((select similarity from public.match_vectors(pg_temp.v(1),1)),1::double precision,'prior first vector preserved');
select is(public.replace_vectors('obsidian','/synthetic/vectors-a.md','Synthetic A',jsonb_build_array(pg_temp.v(1)::text::jsonb),now()),1,'replace shorter set');
select is((select count(*)::integer from public.vectors where document_id='/synthetic/vectors-a.md'),1,'obsolete chunk removed without duplicates');
select throws_ok($$insert into public.vectors values('obsidian','/synthetic/missing.md',0,pg_temp.v(1),now())$$,'23503',null,'FK enforced');
update public.document set id='/synthetic/renamed.md' where id='/synthetic/vectors-a.md';
select is((select count(*)::integer from public.vectors where document_id='/synthetic/renamed.md'),1,'FK update cascades');
delete from public.document where id='/synthetic/renamed.md';
select is((select count(*)::integer from public.vectors where document_id='/synthetic/renamed.md'),0,'FK delete cascades');
set local role service_role;
select ok(public.vector_ingest_ready(),'backend readiness');
reset role;
select * from finish();
rollback;
