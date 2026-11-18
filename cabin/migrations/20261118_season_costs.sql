-- Run once in the existing Supabase project's SQL editor. Then run 20261118_entry_owners.sql, which replaces the two
-- guard rules below with versions that also cover who may change an entry. Don't run this file again after that one.
-- Season costs: lets an admin tag the up-front lease payment (and everyone's payments toward it) so it shows in its own
-- section on the Money tab instead of in the payment history. Tagging never changes anyone's balance.
alter table public.expenses add column if not exists season boolean not null default false;
alter table public.expenses add column if not exists items jsonb check (items is null or length(items::text) < 4000);
alter table public.payments add column if not exists season boolean not null default false;

-- Only an admin can tag, untag, itemise, change, or delete a season cost, even by talking to the database directly.
create or replace function expenses_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare privileged boolean := coalesce(auth.jwt() ->> 'email', '') = '' or is_admin();
begin
  -- Season costs (the up-front lease) are an admin call: nobody else can tag, untag, itemise, change, or delete them.
  if not privileged then
    if tg_op = 'INSERT' then new.season := false; new.items := null;
    elsif old.season then raise exception 'Only an admin can change a season cost';
    elsif tg_op = 'UPDATE' then new.season := false; new.items := old.items;
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
declare privileged boolean := coalesce(auth.jwt() ->> 'email', '') = '' or is_admin();
begin
  if not privileged then
    if tg_op = 'INSERT' then new.season := false;
    elsif old.season then raise exception 'Only an admin can change a season cost payment';
    elsif tg_op = 'UPDATE' then new.season := false;
    end if;
  end if;
  if tg_op = 'DELETE' then return old; end if; return new;
end $$;
drop trigger if exists payments_guard on payments;
create trigger payments_guard before insert or update or delete on payments
  for each row execute function payments_guard();
