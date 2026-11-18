-- Run once in the existing Supabase project's SQL editor (after 20261118_season_costs.sql, and safe to run twice).
-- Only the person who entered an expense or payment, or an admin, can change or delete it. The database now records who
-- entered each one, taken from their sign-in. Entries made before today have no recorded owner, so only admins can change
-- those. The member who collects can also look after pot expenses, as before.
alter table public.expenses add column if not exists created_by uuid references public.members(id) on delete set null;
alter table public.payments add column if not exists created_by uuid references public.members(id) on delete set null;
-- (these three come from the season costs update; repeated so this file also works on its own)
alter table public.expenses add column if not exists season boolean not null default false;
alter table public.expenses add column if not exists items jsonb check (items is null or length(items::text) < 4000);
alter table public.payments add column if not exists season boolean not null default false;

create or replace function expenses_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  signed_in  boolean := coalesce(auth.jwt() ->> 'email', '') <> '';
  privileged boolean := not signed_in or is_admin();
  me uuid;
begin
  if signed_in then
    select id into me from members where lower(email) = lower(auth.jwt() ->> 'email') and active limit 1;
  end if;
  -- Who entered it is recorded from the sign-in, never taken from the browser, and never changes afterwards.
  if tg_op = 'INSERT' and signed_in then new.created_by := me;
  elsif tg_op = 'UPDATE' then new.created_by := old.created_by;
  end if;
  -- Season costs (the up-front lease) are an admin call: nobody else can tag, untag, itemise, change, or delete them.
  if not privileged then
    if tg_op = 'INSERT' then new.season := false; new.items := null;
    elsif old.season then raise exception 'Only an admin can change a season cost';
    elsif tg_op = 'UPDATE' then new.season := false; new.items := old.items;
    end if;
  end if;
  -- Only whoever entered an expense, or an admin, can change or delete it. (The member who collects can also look after pot expenses.)
  if tg_op in ('UPDATE', 'DELETE') and not privileged then
    if not (old.created_by is not null and old.created_by = me) and not (old.from_pot and is_collector()) then
      raise exception 'Only the person who entered this, or an admin, can change it';
    end if;
  end if;
  if privileged or is_collector() then
    if tg_op = 'DELETE' then return old; end if; return new;
  end if;
  if tg_op = 'INSERT' then new.from_pot := false; return new; end if;
  if old.from_pot then raise exception 'Only an admin can change a pot expense'; end if;
  if tg_op = 'DELETE' then return old; end if;
  new.from_pot := false; return new;
end $$;
drop trigger if exists expenses_guard on expenses;
create trigger expenses_guard before insert or update or delete on expenses
  for each row execute function expenses_guard();

create or replace function payments_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  signed_in  boolean := coalesce(auth.jwt() ->> 'email', '') <> '';
  privileged boolean := not signed_in or is_admin();
  me uuid;
begin
  if signed_in then
    select id into me from members where lower(email) = lower(auth.jwt() ->> 'email') and active limit 1;
  end if;
  if tg_op = 'INSERT' and signed_in then new.created_by := me;
  elsif tg_op = 'UPDATE' then new.created_by := old.created_by;
  end if;
  if not privileged then
    if tg_op = 'INSERT' then new.season := false;
    elsif old.season then raise exception 'Only an admin can change a season cost payment';
    elsif tg_op = 'UPDATE' then new.season := false;
    end if;
    -- Only whoever entered a payment, or an admin, can change or delete it.
    if tg_op in ('UPDATE', 'DELETE') and not (old.created_by is not null and old.created_by = me) then
      raise exception 'Only the person who entered this, or an admin, can change it';
    end if;
  end if;
  if tg_op = 'DELETE' then return old; end if; return new;
end $$;
drop trigger if exists payments_guard on payments;
create trigger payments_guard before insert or update or delete on payments
  for each row execute function payments_guard();
