-- ski/lease: Supabase schema. Paste into the SQL editor and run once.
-- Edit the seed row at the bottom first so you can sign in.

create extension if not exists pgcrypto;

create table members (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  email      text not null,
  phone      text not null,
  color      text,
  venmo      text,
  avatar     text check (avatar is null or length(avatar) < 60000),  -- small inline picture or 'emoji:…'
  active     boolean not null default true,
  part_time  boolean not null default false,         -- part-timers pay a lease into the pot; full-timers split it
  lease_cents int not null default 0,                -- a part-timer's lease for the season
  active_from date,                                  -- a part-timer's first bookable night
  active_until date,                                 -- and last bookable night (both included)
  is_admin   boolean not null default false,        -- can remove members, fix emails, set the guest fee
  theme      jsonb check (theme is null or length(theme::text) < 400),   -- light/dark and accent color, so it follows the person to every device
  created_at timestamptz not null default now()
);
create unique index members_email_key on members (lower(email));

create table stays (
  id         uuid primary key default gen_random_uuid(),
  member_id  uuid not null references members(id) on delete cascade,
  night      date not null,                       -- the night slept at the house
  guests     int  not null default 0 check (guests >= 0),
  host_away  boolean not null default false,        -- guests only: the member isn't sleeping there
  guest_names text[] not null default '{}',        -- one name per guest; guests = how many
  guest_paid  text[] not null default '{}',        -- guests whose fee for this night has been received
  guest_fee_cents int,                            -- per-guest rate when this night was booked
  note       text,
  created_at timestamptz not null default now(),
  unique (member_id, night)
);
create index stays_night_idx on stays (night);

create table expenses (
  id           uuid primary key default gen_random_uuid(),
  description  text not null,
  amount_cents int  not null check (amount_cents > 0),
  paid_by      uuid not null references members(id),
  split_among  uuid[] not null check (cardinality(split_among) > 0),  -- even split
  spent_on     date not null default current_date,
  from_pot     boolean not null default false,   -- a house bill that comes out of the season pot
  season       boolean not null default false,   -- part of the up-front season costs, shown there instead of in the payment history
  items        jsonb check (items is null or length(items::text) < 4000),   -- optional breakdown of a season cost: [{label, cents, refundable}]
  created_by   uuid references members(id) on delete set null,   -- who entered it; only they or an admin can change or delete it
  created_at   timestamptz not null default now()
);

create table payments (
  id           uuid primary key default gen_random_uuid(),
  from_member  uuid not null references members(id),
  to_member    uuid not null references members(id),
  amount_cents int  not null check (amount_cents > 0),
  paid_on      date not null default current_date,
  note         text,
  season       boolean not null default false,   -- a payment toward the up-front season costs
  created_by   uuid references members(id) on delete set null,   -- who entered it; only they or an admin can change or delete it
  created_at   timestamptz not null default now(),
  check (from_member <> to_member)
);

create table house (
  id            int primary key default 1 check (id = 1),   -- one row
  name          text,
  address       text,
  door_code     text,
  wifi_name     text,
  wifi_password text,
  beds          int not null default 8,
  guest_fee_cents int not null default 6000,     -- nightly fee per guest
  guest_collector uuid references members(id),   -- the member guests and part-timers pay directly
  lease_paid    uuid[] not null default '{}',    -- part-timers whose lease has been received
  pot_paid_out  boolean not null default false,  -- the season pot has been split between full-timers
  deposit_cents int not null default 44500,      -- security deposit each full-time member paid up front
  deposit_withheld_cents int not null default 0, -- total withheld from the deposits at season end
  listing_url   text,                            -- the rental listing, for general information
  lease_start   date,                            -- first night of the lease
  lease_end     date,                            -- move-out day; the last night is the one before
  notes         text
);
insert into house (id, name) values (1, 'Tahoe house');

-- Who counts as a member: the signed-in email is on the active list.
-- security definer so the check can read members without tripping its own policy.
create or replace function is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from members
    where lower(email) = lower(auth.jwt() ->> 'email') and active
  );
$$;

-- Trust model: any member can read and change anything, like a shared
-- spreadsheet. Everyone else, signed in or not, sees nothing.
do $$
declare t text;
begin
  foreach t in array array['members','stays','expenses','payments','house'] loop
    execute format('alter table %I enable row level security', t);
    execute format(
      'create policy "members only" on %I for all to authenticated using (is_member()) with check (is_member())', t);
  end loop;
end $$;

-- Profiles belong to their owner. Any member can add someone, but only you
-- can edit your own row; the admin can also correct an email or remove a member.
create or replace function is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from members
    where lower(email) = lower(auth.jwt() ->> 'email') and active and is_admin
  );
$$;

-- The member guests and part-timers pay.
create or replace function is_collector() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from house h join members m on m.id = h.guest_collector
    where lower(m.email) = lower(auth.jwt() ->> 'email') and m.active
  );
$$;

-- The signed-in person's member id, or null.
create or replace function my_member_id() returns uuid
language sql stable security definer set search_path = public as $$
  select id from members where lower(email) = lower(auth.jwt() ->> 'email') and active limit 1;
$$;
grant execute on function my_member_id() to authenticated;


drop policy if exists "members only" on members;
drop policy if exists "members read" on members;
drop policy if exists "members add" on members;
drop policy if exists "members edit own" on members;
create policy "members read" on members for select to authenticated using (is_member());
create policy "members add"  on members for insert to authenticated with check (is_admin());
create policy "members edit own" on members for update to authenticated
  using (is_admin() or lower(email) = lower(auth.jwt() ->> 'email'))
  with check (is_member());

-- Signed-in non-admins cannot change who is an admin, anyone's sign-in email,
-- whether someone is active, or who is part time and what their lease is. (Edits made in the Supabase dashboard are not affected.)
create or replace function members_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(auth.jwt() ->> 'email', '') <> '' and not is_admin() then
    if tg_op = 'INSERT' then
      new.is_admin := false; new.active := true; new.part_time := false; new.lease_cents := 0;
      new.active_from := null; new.active_until := null;
    else
      new.is_admin := old.is_admin; new.email := old.email; new.active := old.active;
      new.part_time := old.part_time; new.lease_cents := old.lease_cents;
      new.active_from := old.active_from; new.active_until := old.active_until;
    end if;
  end if;
  return new;
end $$;
drop trigger if exists members_guard on members;
create trigger members_guard before insert or update on members
  for each row execute function members_guard();

-- Any member can read the house; only admins can add or remove the row.
drop policy if exists "members only" on public.house;
drop policy if exists "house read" on public.house;
drop policy if exists "house edit" on public.house;
drop policy if exists "house add" on public.house;
drop policy if exists "house remove" on public.house;
create policy "house read"   on public.house for select to authenticated using (is_member());
create policy "house edit"   on public.house for update to authenticated using (is_member()) with check (is_member());
create policy "house add"    on public.house for insert to authenticated with check (is_admin());
create policy "house remove" on public.house for delete to authenticated using (is_admin());

-- Only admins can change house info and settings.
-- The collecting member can also mark a part-timer's lease as paid.
create or replace function house_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare paid uuid[] := new.lease_paid;
begin
  if coalesce(auth.jwt() ->> 'email', '') <> '' and not is_admin() then
    new := old;
    if is_collector() then new.lease_paid := paid; end if;
  end if;
  return new;
end $$;
drop trigger if exists house_guard on house;
create trigger house_guard before update on house
  for each row execute function house_guard();

-- You can add, change, or remove only your own nights (admins can change anyone's), inside the lease dates. The collecting
-- member can mark someone else's guests as paid, and nothing else. The guest fee is taken from House Info, not from the browser.
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

-- Whoever enters an expense or payment has to be part of it; anyone named in it can delete it; only whoever entered it
-- or an admin can change it. Only an admin or the collecting member can log, change, or delete a pot expense.
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

-- New Supabase projects no longer expose tables to the browser API by
-- default, so grant signed-in users access explicitly. Row-level security
-- above still decides which rows they get. Nothing is granted to anon.
grant select, insert, update, delete on members, stays, expenses, payments, house to authenticated;
grant execute on function is_member() to authenticated;
grant execute on function is_admin() to authenticated;
grant execute on function is_collector() to authenticated;

-- Calendar feed: one private token per member, read by the calendar edge function.
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
-- The calendar edge function reads with the secret key (the service_role role), which new projects don't grant by default.
grant select on public.calendar_tokens, public.members, public.stays, public.house to service_role;

-- Live updates: open pages hear about changes. Row-level security still applies.
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

-- Seed yourself, then add everyone else from the House tab.
insert into members (name, email, phone, color, is_admin)
values ('Your Name', 'you@example.com', '(530) 555-0100', '#39d0a4', true);
