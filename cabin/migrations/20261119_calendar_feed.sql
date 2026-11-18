-- Run once in the existing Supabase project's SQL editor (after 20261119_tighten_rules.sql; safe to run twice).
-- Calendar feed: each member can make a private link that their phone's calendar subscribes to. The link holds a
-- random token; the calendar edge function (cabin/supabase/functions/calendar) looks it up and returns that member's
-- nights. Only you can see or reset your own token, so nobody else in the house can read your link.
create table if not exists public.calendar_tokens (
  member_id  uuid primary key references public.members(id) on delete cascade,
  token      uuid not null unique default gen_random_uuid(),
  created_at timestamptz not null default now()
);
alter table public.calendar_tokens enable row level security;
drop policy if exists "own token" on public.calendar_tokens;
create policy "own token" on public.calendar_tokens for all to authenticated
  using (member_id = my_member_id()) with check (member_id = my_member_id());
grant select, insert, update, delete on public.calendar_tokens to authenticated;
