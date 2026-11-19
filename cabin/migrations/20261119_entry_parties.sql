-- Run once in the existing Supabase project's SQL editor (after 20261119_tighten_rules.sql; safe to run twice).
-- Expenses and payments: whoever enters one has to be part of it (the payer or someone it's split between; for a
-- payment, the person paying or being paid), so nobody can put a charge on two other people's balances. Anyone named
-- in an entry can delete it, so a wrong charge on you is never stuck waiting for an admin. Editing stays with whoever
-- entered it or an admin. Pot expenses and season costs keep their own rules (collector or admin; admin only).
-- Nights: members can only book inside the lease dates.

create or replace function expenses_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  signed_in  boolean := coalesce(auth.jwt() ->> 'email', '') <> '';
  privileged boolean := not signed_in or is_admin();
  me uuid;
  collector boolean := false;
begin
  if signed_in then me := my_member_id(); collector := is_collector(); end if;
  -- Who entered it is recorded from the sign-in, never taken from the browser, and never changes afterwards.
  if tg_op = 'INSERT' and signed_in then new.created_by := me;
  elsif tg_op = 'UPDATE' then new.created_by := old.created_by;
  end if;
  if privileged then
    if tg_op = 'DELETE' then return old; end if; return new;
  end if;

  -- Season costs (the up-front lease) are an admin call: nobody else can tag, untag, itemise, change, or delete them.
  if tg_op = 'INSERT' then new.season := false; new.items := null;
  elsif old.season then raise exception 'Only an admin can change a season cost';
  elsif tg_op = 'UPDATE' then new.season := false; new.items := old.items;
  end if;
  -- Only an admin or the collecting member can log, change, or delete a pot expense.
  if not collector then
    if tg_op = 'INSERT' then new.from_pot := false;
    elsif old.from_pot then raise exception 'Only an admin can change a pot expense';
    elsif tg_op = 'UPDATE' then new.from_pot := false;
    end if;
  end if;

  if tg_op = 'DELETE' then
    if (old.created_by is not null and old.created_by = me) or (old.from_pot and collector)
       or (not old.from_pot and (old.paid_by = me or me = any(old.split_among))) then
      return old;
    end if;
    raise exception 'Only the person who entered this, someone in it, or an admin can delete it';
  end if;
  if tg_op = 'UPDATE' and not ((old.created_by is not null and old.created_by = me) or (old.from_pot and collector)) then
    raise exception 'Only the person who entered this, or an admin, can change it';
  end if;
  if not (new.from_pot and collector) and not (new.paid_by = me or me = any(new.split_among)) then
    raise exception 'You need to be the payer or one of the people it''s split between';
  end if;
  return new;
end $$;
drop trigger if exists expenses_guard on public.expenses;
create trigger expenses_guard before insert or update or delete on public.expenses
  for each row execute function expenses_guard();

create or replace function payments_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  signed_in  boolean := coalesce(auth.jwt() ->> 'email', '') <> '';
  privileged boolean := not signed_in or is_admin();
  me uuid;
begin
  if signed_in then me := my_member_id(); end if;
  if tg_op = 'INSERT' and signed_in then new.created_by := me;
  elsif tg_op = 'UPDATE' then new.created_by := old.created_by;
  end if;
  if privileged then
    if tg_op = 'DELETE' then return old; end if; return new;
  end if;

  if tg_op = 'INSERT' then new.season := false;
  elsif old.season then raise exception 'Only an admin can change a season cost payment';
  elsif tg_op = 'UPDATE' then new.season := false;
  end if;

  if tg_op = 'DELETE' then
    if (old.created_by is not null and old.created_by = me) or old.from_member = me or old.to_member = me then return old; end if;
    raise exception 'Only the person who entered this, someone in it, or an admin can delete it';
  end if;
  if tg_op = 'UPDATE' and not (old.created_by is not null and old.created_by = me) then
    raise exception 'Only the person who entered this, or an admin, can change it';
  end if;
  if new.from_member is distinct from me and new.to_member is distinct from me then
    raise exception 'You need to be the person paying or the person being paid';
  end if;
  return new;
end $$;
drop trigger if exists payments_guard on public.payments;
create trigger payments_guard before insert or update or delete on public.payments
  for each row execute function payments_guard();

create or replace function stays_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  signed_in boolean := coalesce(auth.jwt() ->> 'email', '') <> '';
  admin     boolean := signed_in and is_admin();
  me        uuid;
  m         members%rowtype;
  h         house%rowtype;
  rate      int;
  paid      text[];
begin
  if not signed_in or admin then
    if tg_op = 'DELETE' then return old; end if; return new;
  end if;
  me := my_member_id();

  -- Someone else's night: only the collecting member may touch it, and only to mark guests paid.
  if tg_op = 'DELETE' then
    if old.member_id is distinct from me then raise exception 'You can only remove your own nights'; end if;
    return old;
  end if;
  if tg_op = 'UPDATE' and old.member_id is distinct from me then
    if not is_collector() then raise exception 'You can only change your own nights'; end if;
    paid := new.guest_paid; new := old; new.guest_paid := paid;
    return new;
  end if;
  if new.member_id is distinct from me then raise exception 'You can only book nights for yourself'; end if;

  select * into h from house where id = 1;
  if tg_op = 'INSERT' or new.night is distinct from old.night then
    -- Only nights inside the lease (the end date is move-out day, so its night isn't included).
    if (h.lease_start is not null and new.night < h.lease_start) or (h.lease_end is not null and new.night >= h.lease_end) then
      raise exception 'That night is outside the lease';
    end if;
    -- A part-timer can only book nights inside their dates.
    select * into m from members where id = new.member_id;
    if m.part_time and ((m.active_from is not null and new.night < m.active_from)
                     or (m.active_until is not null and new.night > m.active_until))
       and not exists (select 1 from stays where member_id = new.member_id and night = new.night) then
      raise exception 'That night is outside this member''s part-time dates';
    end if;
  end if;

  -- The guest fee comes from House Info; a night that already had guests keeps its rate.
  rate := h.guest_fee_cents;
  if tg_op = 'UPDATE' and coalesce(old.guests, 0) > 0 and old.guest_fee_cents is not null then
    new.guest_fee_cents := old.guest_fee_cents;
  elsif coalesce(new.guests, 0) > 0 then
    new.guest_fee_cents := rate;
  elsif tg_op = 'UPDATE' then
    new.guest_fee_cents := old.guest_fee_cents;
  else
    new.guest_fee_cents := null;
  end if;

  -- Only the admin or the collecting member can mark a guest as paid.
  if not is_collector() then
    if tg_op = 'INSERT' then new.guest_paid := '{}'; else new.guest_paid := old.guest_paid; end if;
  end if;
  return new;
end $$;
drop trigger if exists stays_guard on public.stays;
create trigger stays_guard before insert or update or delete on public.stays
  for each row execute function stays_guard();
