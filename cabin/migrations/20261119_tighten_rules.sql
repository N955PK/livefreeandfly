-- Run once in the existing Supabase project's SQL editor (after 20261118_entry_owners.sql; safe to run twice).
-- House: any member can read it, only admins can change, add, or remove the house row. The collecting member can still
-- mark a part-timer's lease as received.
-- Stays: you can add, change, or remove only your own nights (admins can change anyone's). The member who collects can
-- mark someone else's guests as paid, and nothing else on their night. The nightly guest fee is taken from House Info
-- by the database, so it can't be set from the browser; a night keeps the rate it was first booked at.

-- The signed-in person's member id, or null.
create or replace function my_member_id() returns uuid
language sql stable security definer set search_path = public as $$
  select id from members where lower(email) = lower(auth.jwt() ->> 'email') and active limit 1;
$$;
grant execute on function my_member_id() to authenticated;

drop policy if exists "members only" on public.house;
drop policy if exists "house read" on public.house;
drop policy if exists "house edit" on public.house;
drop policy if exists "house add" on public.house;
drop policy if exists "house remove" on public.house;
create policy "house read"   on public.house for select to authenticated using (is_member());
create policy "house edit"   on public.house for update to authenticated using (is_member()) with check (is_member());
create policy "house add"    on public.house for insert to authenticated with check (is_admin());
create policy "house remove" on public.house for delete to authenticated using (is_admin());

create or replace function stays_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  signed_in boolean := coalesce(auth.jwt() ->> 'email', '') <> '';
  admin     boolean := signed_in and is_admin();
  me        uuid;
  m         members%rowtype;
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

  -- A part-timer can only book nights inside their dates.
  if tg_op = 'INSERT' or new.night is distinct from old.night then
    select * into m from members where id = new.member_id;
    if m.part_time and ((m.active_from is not null and new.night < m.active_from)
                     or (m.active_until is not null and new.night > m.active_until))
       and not exists (select 1 from stays where member_id = new.member_id and night = new.night) then
      raise exception 'That night is outside this member''s part-time dates';
    end if;
  end if;

  -- The guest fee comes from House Info; a night that already had guests keeps its rate.
  select guest_fee_cents into rate from house where id = 1;
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
