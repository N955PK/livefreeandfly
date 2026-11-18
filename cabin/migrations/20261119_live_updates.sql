-- Run once in the existing Supabase project's SQL editor (safe to run twice).
-- Live updates: Supabase tells open pages whenever a night, expense, payment, member, or the house changes, so
-- everyone's screen refreshes on its own. Row-level security still decides who hears about what.
do $$
declare t text;
begin
  if not exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    create publication supabase_realtime;
  end if;
  foreach t in array array['members','stays','expenses','payments','house'] loop
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;
